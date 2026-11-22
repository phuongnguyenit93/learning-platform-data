# Thực hành: Đọc và ghi cấu hình với Path.of, Files.readString, Files.writeString (Java 11+)

Bài thực hành này sử dụng các API hiện vẫn có mặt trong Java hiện đại: `Path.of` để xác định vị trí tệp, `Files.readString` để đọc toàn bộ nội dung văn bản và `Files.writeString` để tạo/cập nhật nội dung. Ví dụ sử dụng Java 11 trở lên, mã hóa UTF-8, và định dạng `.properties` đơn giản. Các thao tác đọc/ghi tệp làm việc với chuỗi văn bản; định dạng, quy tắc kiểm tra và dữ liệu cấu hình được xử lý riêng.

## 1. Mục tiêu và trường hợp áp dụng

Sau bài này, bạn có thể:

1. Tạo `Path` trỏ tới file cấu hình theo cách phù hợp với hệ điều hành.
2. Tạo thư mục chứa file, đọc chuỗi UTF-8 và ghi lại chuỗi đó với chế độ mở tệp được chọn rõ ràng.
3. Đọc giá trị từ `.properties`, kiểm tra cấu hình bắt buộc và cập nhật một thuộc tính.
4. Phân biệt ghi đè, tạo mới, ghi nối; xử lý lỗi tệp, mã hóa, kích thước và nguy cơ ghi hỏng.
5. Biết khi nào cần ghi an toàn bằng tệp tạm và thay thế tệp đích.

Cách này phù hợp với file cấu hình **văn bản, kích thước nhỏ hoặc vừa**, chẳng hạn cài đặt phát triển cục bộ hay thông số ứng dụng. `Files.readString` nạp toàn bộ file vào bộ nhớ; với dữ liệu lớn hoặc luồng liên tục, dùng `Files.newBufferedReader`/`Files.newBufferedWriter` và xử lý từng phần.

## 2. Ba API cốt lõi

### `Path.of(...)`: xác định file

~~~java
Path config = Path.of("config", "app.properties");
Path absolute = config.toAbsolutePath().normalize();
~~~

- `Path.of("config", "app.properties")` kết hợp các thành phần tên đường dẫn bằng quy tắc của hệ điều hành, nên không cần tự nối `/` hay `\`.
- Đây là đường dẫn **tương đối**: chương trình tìm `config/app.properties` dưới thư mục làm việc hiện tại (`user.dir`). Chạy từ thư mục khác có thể dẫn đến file khác hoặc lỗi không tìm thấy.
- `toAbsolutePath()` giúp nhìn rõ đường dẫn được dùng, còn `normalize()` rút gọn các phần `.` hoặc `..` theo cú pháp. Nó không tự bảo đảm rằng đường dẫn do người dùng cung cấp là an toàn trước traversal hoặc symbolic link.
- `Path.of("app.properties").getParent()` có thể trả về `null`. Chỉ gọi `Files.createDirectories(parent)` khi `parent != null`.

### `Files.readString(...)`: đọc toàn bộ tệp

~~~java
String text = Files.readString(config, StandardCharsets.UTF_8);
~~~

- Đọc toàn bộ dữ liệu từ `config` rồi giải mã thành `String` bằng UTF-8. Quá tải bộ nhớ là rủi ro nếu file quá lớn.
- Overload `Files.readString(config)` cũng dùng UTF-8. Ghi rõ `StandardCharsets.UTF_8` trong ví dụ để làm rõ hợp đồng mã hóa với file.
- Hàm giữ lại ký tự xuống dòng có sẵn trong file, không tự xóa khoảng trắng và không tự phân tích cú pháp cấu hình.
- Có thể phát sinh `IOException`, như file không tồn tại, không đủ quyền hoặc nội dung byte không giải mã được bằng charset đã chọn.

### `Files.writeString(...)`: tạo hoặc cập nhật tệp

~~~java
Files.writeString(config, text, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
~~~

- Mã hóa `text` sang UTF-8 và ghi vào tệp đích. Không tự bổ sung ký tự xuống dòng; nội dung lưu đúng theo chuỗi đưa vào.
- Các tùy chọn trên nghĩa là tạo file nếu chưa tồn tại, xóa nội dung cũ nếu file đã tồn tại và mở file để ghi.
- Nếu không chỉ định bất kỳ `OpenOption` nào, hành vi mặc định cũng tương đương `CREATE`, `TRUNCATE_EXISTING`, `WRITE`.
- `writeString` chỉ tạo file; nó **không tự tạo thư mục cha**. Gọi `Files.createDirectories` trước khi ghi nếu cần.
- Lỗi có thể xuất hiện sau khi file đã bị cắt ngắn hoặc chỉ mới được ghi một phần. Với cấu hình quan trọng, xem kỹ phần ghi an toàn bên dưới.

## 3. Ví dụ chạy được: ghi, đọc, kiểm tra và cập nhật `app.properties`

Chương trình sau chủ động tạo/ghi đè `demo-config/app.properties` mỗi lần chạy để kết quả thực hành có thể lặp lại. **Chỉ chạy với thư mục thực hành này; không trỏ chương trình mẫu vào cấu hình đang dùng trong môi trường thật.**

Đặt file `ConfigFileDemo.java` với nội dung:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Properties;

public final class ConfigFileDemo {
    public static void main(String[] args) throws IOException {
        Path configPath = Path.of("demo-config", "app.properties");

        Path parent = configPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        // Bước 1: Tạo cấu hình mẫu dưới dạng chuỗi UTF-8.
        String initialText = "# Config demo UTF-8\n"
                + "app.name=Demo Java 11\n"
                + "server.port=8080\n"
                + "feature.enabled=false\n";

        Files.writeString(configPath, initialText, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);

        // Bước 2: Đọc lại toàn bộ nội dung.
        String readText = Files.readString(configPath, StandardCharsets.UTF_8);

        // Bước 3: Chuyển văn bản .properties thành các cặp khóa/giá trị.
        Properties properties = new Properties();
        try (StringReader reader = new StringReader(readText)) {
            properties.load(reader);
        }

        String name = required(properties, "app.name");
        int port = parsePort(required(properties, "server.port"));
        boolean enabled = parseBoolean(required(properties, "feature.enabled"));

        System.out.println("app.name=" + name);
        System.out.println("server.port=" + port);
        System.out.println("feature.enabled=" + enabled);

        // Bước 4: Cập nhật giá trị và chuyển Properties thành chuỗi.
        properties.setProperty("feature.enabled", "true");
        StringWriter writer = new StringWriter();
        properties.store(writer, "Updated by ConfigFileDemo");

        // Bước 5: Ghi lại nội dung UTF-8.
        Files.writeString(configPath, writer.toString(), StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);

        System.out.println("written.feature.enabled="
                + properties.getProperty("feature.enabled"));
    }

    private static String required(Properties properties, String key) {
        String value = properties.getProperty(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu hoặc rỗng: " + key);
        }
        return value.trim();
    }

    private static int parsePort(String raw) {
        final int port;
        try {
            port = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "server.port phải là số nguyên: " + raw, e);
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "server.port phải trong khoảng 1..65535");
        }
        return port;
    }

    private static boolean parseBoolean(String raw) {
        if ("true".equalsIgnoreCase(raw)) {
            return true;
        }
        if ("false".equalsIgnoreCase(raw)) {
            return false;
        }
        throw new IllegalArgumentException(
                "feature.enabled chỉ nhận true hoặc false");
    }
}
~~~

Biên dịch và chạy ở thư mục chứa `ConfigFileDemo.java`, sử dụng JDK 11 hoặc mới hơn:

~~~bash
javac --release 11 ConfigFileDemo.java
java ConfigFileDemo
~~~

**Kết quả stdout chính xác:**

~~~text
app.name=Demo Java 11
server.port=8080
feature.enabled=false
written.feature.enabled=true
~~~

Sau khi chạy, file `demo-config/app.properties` chứa các thuộc tính đã lưu, trong đó `feature.enabled=true`. `Properties.store(Writer, ...)` có thể thêm dòng chú thích/thời điểm ghi, đổi thứ tự khóa và cách escape; do đó không dự đoán nguyên văn toàn bộ file đầu ra hay dùng so sánh byte để kiểm tra ví dụ này. Việc dùng `StringReader`/`StringWriter` cho phép `Properties` xử lý văn bản Unicode đã đọc/ghi bằng UTF-8; nó khác với cách mã hóa áp dụng cho các overload nhận `InputStream`/`OutputStream`.

### Vì sao cần `Properties`?

`Files.readString` chỉ trả về nội dung thô, không hiểu khóa `server.port` là gì. `Properties.load(Reader)` hiểu cú pháp file `.properties`: phân tách khóa và giá trị, comment, escape, ký tự nối dòng. `Properties.store(Writer, ...)` ghi lại cấu hình ở định dạng có thể đọc được bởi `load(Reader)`. Với JSON, YAML, TOML hoặc định dạng tùy chỉnh, hãy dùng parser/serializer phù hợp, **không** dùng `split("=")` để giả định mọi cấu hình có cú pháp giống nhau.

Cần chọn cách cập nhật theo nhu cầu: nếu thứ tự, bình luận hoặc cách định dạng gốc do con người duy trì phải được giữ nguyên, `Properties.store` không đảm bảo bảo toàn những chi tiết đó; hãy sử dụng công cụ chỉnh sửa định dạng có khả năng giữ lại cấu trúc hoặc thiết kế thao tác ghi phù hợp.

## 4. Chọn chế độ ghi đúng mục đích

| Nhu cầu | Ví dụ options | Ý nghĩa |
| --- | --- | --- |
| Tạo mới hoặc thay thế toàn bộ file | `CREATE, TRUNCATE_EXISTING, WRITE` | Tạo nếu thiếu; file cũ bị ghi đè |
| Chỉ tạo file mới | `CREATE_NEW, WRITE` | Báo lỗi nếu file đã tồn tại |
| Chỉ ghi đè file đang có | `TRUNCATE_EXISTING, WRITE` | Không tạo file mới; yêu cầu file đã tồn tại |
| Ghi nối | `CREATE, APPEND` | Thêm chuỗi vào cuối, tạo nếu thiếu |

Ví dụ minh họa độc lập về cách ghi nối, **chỉ dùng khi định dạng file cho phép nối**:

~~~java
Files.writeString(Path.of("logs", "config-changes.txt"),
        "feature.enabled=true\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

Trước đoạn trên, phải tạo thư mục `logs` nếu chưa có. Với `.properties`, nối thêm một khóa trùng tên có thể gây nhầm lẫn và phụ thuộc quy tắc đọc; thao tác cập nhật thuộc tính nên đọc → phân tích → sửa dữ liệu → ghi lại theo chính sách đã chọn, không đơn giản append vào cuối.

**Chú ý:** `APPEND` và `TRUNCATE_EXISTING` không đi cùng nhau; lỗi thao tác ghi không được xem là thành công. Nếu file phải được tạo đúng một lần, dùng `CREATE_NEW` thay cho kiểm tra `Files.exists` rồi ghi, vì việc kiểm tra và tạo riêng có thể xảy ra race condition.

## 5. Quy trình áp dụng cho file cấu hình thực tế

1. **Xác định nguồn đường dẫn:** nhận từ tham số chương trình, biến môi trường hoặc một vị trí cấu hình đã quy định. Ví dụ: `Path.of("config", "app.properties")`. Đừng dựa vào thư mục làm việc ngầm nếu môi trường chạy có thể thay đổi.
2. **Thống nhất charset:** UTF-8 là lựa chọn thông dụng cho file văn bản mới. Dùng cùng charset cho cả đọc và ghi; nếu file có mã hóa khác, cần biết rõ nó trước khi chuyển đổi.
3. **Đọc và parse đúng định dạng:** `Files.readString` trả chuỗi; sau đó dùng `Properties.load(new StringReader(text))` với `.properties` hoặc parser tương ứng.
4. **Kiểm tra dữ liệu trước khi sử dụng:** khóa bắt buộc, số nguyên và khoảng hợp lệ, boolean chính xác, giá trị được phép, đường dẫn tham chiếu và quy tắc nghiệp vụ.
5. **Chỉ ghi khi thực sự cần:** xác định rõ đây là thao tác tạo mới, thay thế hay cập nhật. Tránh đưa mật khẩu/token vào log hoặc commit cấu hình nhạy cảm lên repository.
6. **Nếu file quan trọng, ghi qua file tạm rồi thay thế:** tránh làm mất phiên bản cũ khi quá trình ghi bị dừng giữa chừng. Với nhiều tiến trình cùng sửa, cần thêm chiến lược đồng bộ/kiểm soát phiên bản.

Đoạn mã đọc file sẵn có mà không tự tạo file (một đoạn minh họa, đặt trong method có xử lý `IOException`):

~~~java
Path configPath = Path.of("config", "app.properties");
String text = Files.readString(configPath, StandardCharsets.UTF_8);
Properties settings = new Properties();
settings.load(new StringReader(text));
String portText = settings.getProperty("server.port");
~~~

Đoạn này sẽ phát sinh lỗi đọc nếu file không tồn tại. Đó thường là hành vi tốt với cấu hình **bắt buộc**: ứng dụng báo rõ thiếu cấu hình thay vì âm thầm tạo file trống rồi chạy với dữ liệu không hợp lệ. Hãy xử lý lỗi và cung cấp thông báo có thể hành động được ở tầng khởi động ứng dụng.

## 6. Ghi thay thế an toàn hơn bằng file tạm

Vì `TRUNCATE_EXISTING` cắt ngắn file cũ trước khi hoàn thành ghi, với file cấu hình quan trọng có thể dùng chu trình: tạo file tạm trong **cùng thư mục** → ghi xong file tạm → chuyển/đổi tên thành file đích. Ví dụ dưới đây là **một method hỗ trợ**, không phải chương trình độc lập:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

static void replaceConfig(Path destination, String content) throws IOException {
    Path target = destination.toAbsolutePath().normalize();
    Path directory = target.getParent();
    Files.createDirectories(directory);

    Path temporary = Files.createTempFile(directory, ".config-", ".tmp");
    try {
        Files.writeString(temporary, content, StandardCharsets.UTF_8,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);

        try {
            Files.move(temporary, target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(temporary, target,
                    StandardCopyOption.REPLACE_EXISTING);
        }
    } finally {
        Files.deleteIfExists(temporary);
    }
}
~~~

- `ATOMIC_MOVE` phụ thuộc file system và provider; nếu không được hỗ trợ, đoạn mã chuyển sang `REPLACE_EXISTING`, **không còn bảo đảm thay thế nguyên tử**. Cần thiết kế chính sách lỗi/backup phù hợp với mức độ quan trọng của cấu hình.
- Nếu tiến trình khác cùng ghi, thao tác chuyển tệp không giải quyết được xung đột thay đổi; cần lock, version check hoặc một cơ chế điều phối. Nó cũng không tự đảm bảo mọi byte đã được đồng bộ xuống thiết bị lưu trữ khi mất điện.
- Nếu tệp có quyền truy cập hoặc thuộc tính đặc biệt, việc tạo file tạm và thay thế có thể thay đổi các thuộc tính đó. Hãy kiểm tra yêu cầu quyền và cách triển khai trên hệ thống thật.
- Đừng coi `normalize()` là cơ chế chống path traversal/symlink khi `destination` đến từ đầu vào không đáng tin; phải giới hạn vùng truy cập và kiểm tra thực thể đường dẫn theo chính sách an toàn.

## 7. Các lỗi dễ gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` khi đọc | Chưa có file; thư mục làm việc khác kỳ vọng | In đường dẫn tuyệt đối để chẩn đoán; cấp file cấu hình đúng vị trí |
| `AccessDeniedException` hoặc `IOException` | Không đủ quyền, file/ổ đĩa gặp lỗi | Kiểm tra quyền và môi trường; báo lỗi cụ thể, không nuốt exception |
| Không có thư mục khi ghi | `writeString` không tạo thư mục cha | `Files.createDirectories(parent)` sau khi kiểm tra `parent != null` |
| Ký tự tiếng Việt lỗi, đọc thất bại | Charset file không khớp charset truyền vào | Thống nhất UTF-8 cho file mới, chuyển đổi dữ liệu cũ đúng cách |
| File cũ biến mất sau lần chạy | `TRUNCATE_EXISTING` ghi đè nội dung | Chọn `CREATE_NEW` hoặc cơ chế backup/ghi qua file tạm |
| Giá trị `port`/`enabled` sai nhưng chương trình vẫn chạy | Thiếu validation; dùng `Boolean.parseBoolean` một cách lỏng lẻo | Bắt buộc khóa, kiểm tra khoảng số và chuỗi `true/false` rõ ràng |
| Comment/thứ tự của `.properties` thay đổi | `Properties.store` tuần tự hóa lại nội dung | Không dùng phương thức này nếu cần giữ nguyên biểu diễn gốc |
| Đọc file cấu hình rất lớn tốn bộ nhớ | `readString` nạp cả file | Sử dụng API đọc theo luồng và xử lý tăng dần |

Đừng bắt `IOException` rồi trả về chuỗi rỗng một cách mặc định: hành vi này che giấu lỗi và dễ khiến cấu hình sai được xem như hợp lệ. Trả về giá trị mặc định chỉ khi đã định nghĩa rõ chính sách cho khóa hoặc file tùy chọn.

## 8. Bài tập tự thực hành và cách kiểm chứng

1. Chạy `ConfigFileDemo`, xác nhận bốn dòng stdout ở trên và mở `demo-config/app.properties` để xem giá trị cập nhật.
2. Thay `server.port=8080` trong `initialText` thành `server.port=70000`. Chạy lại và kiểm tra chương trình từ chối giá trị ngoài khoảng hợp lệ.
3. Thay `feature.enabled=false` thành `feature.enabled=maybe`. Chạy lại và kiểm tra việc kiểm tra boolean báo lỗi rõ ràng.
4. Đổi `StandardOpenOption.TRUNCATE_EXISTING` trong bước tạo file mẫu thành `CREATE_NEW` (đồng thời không dùng `CREATE`). Chạy lần đầu khi file chưa tồn tại và chạy lần hai khi file đã tồn tại để hiểu `FileAlreadyExistsException`. Có thể xóa riêng thư mục thực hành giữa các lần thử.
5. Tách phần đọc/parse/validation và phần ghi thành các method riêng, sau đó cho chương trình nhận đường dẫn cấu hình từ `args[0]`. Quy định trường hợp thiếu đối số và trường hợp không tìm được file.
6. Thử dùng `replaceConfig` với một file mẫu riêng; đánh giá trường hợp file system không hỗ trợ atomic move và cách truyền lỗi về nơi gọi.

**Tiêu chí hoàn thành:** Bạn chỉ ra được đường dẫn thực tế, đọc/ghi đúng UTF-8, phân biệt thao tác ghi đè với tạo mới, không bỏ qua lỗi cấu hình, biết giới hạn của `Properties.store`, và giải thích được vì sao file cấu hình quan trọng nên được ghi qua tệp tạm trước khi thay thế.

## 9. Tài liệu API chính thức để tra cứu

- [Path (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html): `Path.of`, đường dẫn và `normalize`.
- [Files (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `createDirectories`, `createTempFile`, `move`.
- [StandardOpenOption (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/StandardOpenOption.html): ý nghĩa của `CREATE`, `CREATE_NEW`, `TRUNCATE_EXISTING`, `APPEND` và `WRITE`.
- [Properties (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Properties.html): `load(Reader)`, `store(Writer, String)` và cú pháp `.properties`.

Các phương thức trọng tâm đã có từ Java 11 và vẫn hiện diện trong tài liệu Java SE 25; chương trình mẫu không yêu cầu cú pháp hoặc thư viện được bổ sung sau Java 11.