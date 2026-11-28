# Path, Files và thao tác tệp thư mục bằng NIO.2

Khi ứng dụng Java làm việc với tệp cấu hình, báo cáo, dữ liệu tải lên hoặc thư mục lưu trữ, vấn đề không chỉ là đọc và ghi chuỗi. Ứng dụng cần xây dựng đường dẫn đúng trên nhiều hệ điều hành, lựa chọn chế độ tạo/ghi tệp, xử lý lỗi I/O, đóng tài nguyên, và tránh các giả định sai về symbolic link hay thứ tự duyệt thư mục.

Trong Java 27, hai API nền tảng của **NIO.2** thuộc gói `java.nio.file` vẫn là:

- `Path`: mô tả một đường dẫn bên trong một file system, hỗ trợ kết hợp, phân rã, chuẩn hóa và chuyển thành đường dẫn tuyệt đối.
- `Files`: tập hợp các phương thức tĩnh để **tác động lên hệ thống tệp**: kiểm tra thuộc tính, tạo, đọc, ghi, sao chép, di chuyển, xóa và duyệt thư mục.

NIO.2 xuất hiện từ Java 7 và vẫn là một API hiện hành được hỗ trợ trong Java 27. Một số tiện ích như `Path.of`, `Files.readString` và `Files.writeString` được bổ sung sau đó, nhưng đều là tính năng ổn định. Bài viết tập trung vào cách dùng hiện đại của API, không dựa trên hành vi cũ hoặc tính năng preview.

## 1. Phân biệt Path và Files

`Path` mô tả **vị trí logic** của một tệp hoặc thư mục. Tạo đối tượng `Path` thông thường **không** tạo tệp trên ổ đĩa và cũng không yêu cầu đích tồn tại.

```java
import java.nio.file.Path;

Path report = Path.of("data", "reports", "summary.txt");

System.out.println(report.getFileName()); // summary.txt
System.out.println(report.getParent());   // data/reports (trên hệ Unix)
```

Khi cần thực sự tạo hoặc truy cập tệp, dùng `Files`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.io.IOException;

Path report = Path.of("data", "reports", "summary.txt");

Files.createDirectories(report.getParent());
Files.writeString(report, "Báo cáo Java 27\n", StandardCharsets.UTF_8);

String content = Files.readString(report, StandardCharsets.UTF_8);
System.out.println(content);
```

Đoạn mã tạo các thư mục cha chưa tồn tại rồi ghi văn bản UTF-8. **Lưu ý:** đây là ví dụ có tác động lên thư mục `data/reports` tương đối với *working directory* của tiến trình. Hãy chọn nơi lưu thích hợp, kiểm soát quyền ghi và tránh ghi đè tệp nghiệp vụ ngoài ý muốn.

`Path` không đồng nhất với `String`. Nó có quy tắc thành phần và phân tách đường dẫn tùy file system. Nên truyền đối tượng `Path` qua các tầng mã thay vì nối các chuỗi đường dẫn bằng dấu `/` hoặc `\\` thủ công.

### Nhóm API thường dùng

| Nhiệm vụ | API |
|---|---|
| Tạo đối tượng đường dẫn | `Path.of(...)` |
| Ghép đường dẫn | `resolve(...)`, `resolveSibling(...)` |
| Lấy thành phần | `getFileName()`, `getParent()`, `getRoot()` |
| Chuẩn hóa cú pháp | `normalize()` |
| Lấy đường dẫn tuyệt đối | `toAbsolutePath()` |
| Lấy đường dẫn thật của tệp có tồn tại | `toRealPath(...)` |
| Kiểm tra tệp, thư mục | `Files.isRegularFile(...)`, `Files.isDirectory(...)` |
| Đọc, ghi văn bản nhỏ | `Files.readString(...)`, `Files.writeString(...)` |
| Duyệt thư mục | `Files.list(...)`, `Files.walk(...)`, `Files.walkFileTree(...)` |
| Sao chép, di chuyển, xóa | `Files.copy(...)`, `Files.move(...)`, `Files.delete(...)` |

## 2. Khởi tạo và phân tích đường dẫn

Có thể tạo đường dẫn từ một hoặc nhiều chuỗi:

```java
Path root = Path.of("workspace");
Path logs = Path.of("workspace", "logs");
Path today = logs.resolve("app.log");

System.out.println(today.getFileName()); // app.log
System.out.println(today.getParent());   // workspace/logs (trên Unix)
```

Cách viết `Path.of("workspace", "logs", "app.log")` giúp API chọn dấu phân cách của file system tương ứng. Chuỗi biểu diễn khi in ra có thể khác giữa Windows và Linux/macOS; đừng viết kiểm thử giả định luôn có dấu `/`.

Một `Path` có thể là:

- **Tương đối**, ví dụ `Path.of("logs", "app.log")`, được diễn giải dựa trên working directory khi truy cập.
- **Tuyệt đối**, ví dụ `Path.of("/opt/app/data")` trên một hệ Unix. Cú pháp đường dẫn tuyệt đối phụ thuộc nền tảng; đường dẫn Unix trên Windows không nên được giả định là có cùng ý nghĩa.

Các phương thức phân tích:

```java
Path file = Path.of("incoming", "2026", "orders.csv");

Path name = file.getFileName();  // orders.csv
Path parent = file.getParent();  // incoming/2026 (trên Unix)
int components = file.getNameCount(); // 3
```

`getParent()` hoặc `getRoot()` có thể trả về `null` nếu đường dẫn không có thành phần tương ứng. Chẳng hạn, một đường dẫn chỉ gồm tên tệp tương đối thường không có parent.

### Ghép đường dẫn với resolve

```java
Path base = Path.of("data");
Path path = base.resolve("exports").resolve("report.csv");
```

`resolve` coi đường dẫn bên trái là gốc để gắn đường dẫn tương đối bên phải. **Nếu đối số bên phải là đường dẫn tuyệt đối**, quy tắc trên file system mặc định có thể khiến nó thay thế phần bên trái, thay vì được ghép vào base. Vì vậy, không được đưa nguyên văn đường dẫn không đáng tin cậy vào `resolve` rồi mặc định rằng nó luôn nằm dưới thư mục cho phép.

`resolveSibling` tạo đường dẫn mới cùng cấp với đường dẫn ban đầu:

```java
Path original = Path.of("reports", "draft.txt");
Path renamed = original.resolveSibling("final.txt");
// reports/final.txt (trên Unix)
```

Chỉ tạo ra `Path` mới chưa đổi tên tệp. Để đổi tên thực sự, dùng `Files.move(original, renamed)`.

## 3. normalize, toAbsolutePath, toRealPath: ba việc khác nhau

Ba phương thức trông gần giống nhưng có ý nghĩa rất khác nhau.

```java
Path raw = Path.of("reports", ".", "2026", "..", "summary.txt");

System.out.println(raw.normalize());
// reports/summary.txt (trên Unix)
```

`normalize()` là thao tác **cú pháp**: loại các thành phần dư thừa như `.` và các cặp tên/`..` có thể rút gọn. Nó không kiểm tra tệp tồn tại, không đọc ổ đĩa và không giải quyết symbolic link.

```java
Path relative = Path.of("reports", "summary.txt");
Path absolute = relative.toAbsolutePath();
```

`toAbsolutePath()` trả đường dẫn tuyệt đối theo ngữ cảnh của file system, thường dựa vào working directory. Nó **không** cam kết tệp tồn tại hoặc đã giải quyết symbolic link.

```java
import java.io.IOException;

Path existing = Path.of("reports", "summary.txt");

try {
    Path real = existing.toRealPath();
    System.out.println(real);
} catch (IOException exception) {
    System.err.println("Không lấy được đường dẫn thật: " + exception.getMessage());
}
```

`toRealPath()` truy cập file system, yêu cầu đích tồn tại và theo mặc định xử lý symbolic link để tìm đường dẫn thực tế. Nó có thể ném `IOException`.

| Phương thức | Truy cập file system? | Yêu cầu tệp tồn tại? | Mục đích |
|---|---|---|---|
| `normalize()` | Không | Không | Rút gọn các thành phần đường dẫn về mặt cú pháp |
| `toAbsolutePath()` | Thông thường không cần kiểm tra tồn tại | Không | Lấy biểu diễn tuyệt đối |
| `toRealPath()` | Có | Có | Xác định đường dẫn thực tế theo quy tắc provider |

Không xem `normalize()` là cơ chế bảo mật chống path traversal. Nếu một thành phần là symbolic link, phép rút gọn `..` thuần cú pháp có thể không tương đương việc truy cập thật qua link đó.

### relativize: lấy đường dẫn tương đối giữa hai vị trí

```java
Path base = Path.of("reports");
Path file = Path.of("reports", "2026", "summary.csv");

Path relativeToBase = base.relativize(file);
// 2026/summary.csv (trên Unix)
```

Hai đường dẫn phải có thể relativize với nhau theo quy tắc của file system/provider. Trộn đường dẫn thuộc các provider khác nhau hoặc một đường dẫn tương đối với một đường dẫn tuyệt đối có thể gây `IllegalArgumentException`.

## 4. Tạo file và thư mục

### createDirectory và createDirectories

```java
Path dir = Path.of("output", "2026", "reports");

// Tạo toàn bộ chuỗi thư mục cha chưa tồn tại:
Files.createDirectories(dir);
```

`Files.createDirectory(dir)` chỉ tạo đúng một thư mục và thông thường yêu cầu parent đã tồn tại. Nếu đích đã tồn tại, nó thất bại. `Files.createDirectories(dir)` tạo các parent chưa có và thành công cả khi đường dẫn đích đã là thư mục phù hợp.

```java
Files.createDirectories(Path.of("output", "2026"));
Files.createDirectory(Path.of("output", "2026", "archive"));
```

`createDirectories` không phải một transaction: nếu lỗi giữa chừng, một số parent có thể đã được tạo. Ngoài ra, nếu có một tệp thường chặn đường dẫn, thao tác có thể thất bại.

### createFile và tạo mới không ghi đè

```java
Path file = Path.of("output", "new.txt");
Files.createDirectories(file.getParent());
Files.createFile(file);
```

`createFile` tạo file trống và thất bại nếu đích đã tồn tại. Kiểm tra sự tồn tại rồi mới tạo là một chuỗi dễ gặp **race condition**:

```java
// KHÔNG NÊN dựa vào mẫu sau để bảo đảm tạo độc quyền:
// if (Files.notExists(file)) {
//     Files.createFile(file);
// }
```

Giữa bước kiểm tra và bước tạo, một tiến trình khác có thể tạo cùng file. Hãy gọi trực tiếp `Files.createFile` hoặc dùng `CREATE_NEW`, rồi xử lý `FileAlreadyExistsException`.

```java
import static java.nio.file.StandardOpenOption.CREATE_NEW;
import static java.nio.file.StandardOpenOption.WRITE;
import java.nio.charset.StandardCharsets;

Files.writeString(
    Path.of("output", "report.txt"),
    "Báo cáo mới\n",
    StandardCharsets.UTF_8,
    CREATE_NEW, WRITE
);
```

`CREATE_NEW` kiểm tra việc tồn tại và tạo file như một thao tác nguyên tử theo hợp đồng API; điều này phù hợp hơn với yêu cầu tránh ghi đè dữ liệu so với kiểm tra trước rồi mở tệp.

## 5. Đọc và ghi văn bản với UTF-8

Với tệp văn bản nhỏ hoặc trung bình, `Files.readString` và `Files.writeString` là lựa chọn đơn giản:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path notes = Path.of("notes.txt");

Files.writeString(notes, "Xin chào Java 27\n", StandardCharsets.UTF_8);
String content = Files.readString(notes, StandardCharsets.UTF_8);
```

Các overload không khai báo charset của `readString`/`writeString` mặc định dùng **UTF-8**, không phải charset mặc định của hệ điều hành. Tuy vậy, ghi `StandardCharsets.UTF_8` tường minh có thể làm hợp đồng dữ liệu dễ nhận biết hơn, đặc biệt khi trao đổi với hệ thống khác.

`readString` giữ các ký tự kết thúc dòng trong nội dung. `writeString` không tự thêm ký tự xuống dòng: muốn có `LF`, phải đưa `"\n"` vào chuỗi.

### Chế độ mở file khi ghi

Mặc định, `Files.writeString(path, text)` tạo file khi chưa có và ghi đè nội dung của file đã tồn tại (mở để ghi với `CREATE` và `TRUNCATE_EXISTING`). Khi yêu cầu khác, cung cấp `StandardOpenOption`:

| Option | Ý nghĩa thường gặp |
|---|---|
| `CREATE` | Tạo file nếu chưa tồn tại |
| `CREATE_NEW` | Tạo độc quyền; thất bại nếu đã tồn tại |
| `TRUNCATE_EXISTING` | Cắt nội dung cũ khi mở để ghi |
| `APPEND` | Ghi tiếp ở cuối file |
| `WRITE` | Mở để ghi |
| `READ` | Mở để đọc trong các API tương thích |
| `SYNC`, `DSYNC` | Yêu cầu đồng bộ một số thay đổi xuống thiết bị lưu trữ theo hợp đồng provider |

Ví dụ nối thêm vào một file **đã tồn tại**:

```java
import static java.nio.file.StandardOpenOption.APPEND;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(notes, "Dòng tiếp theo\n",
                  StandardCharsets.UTF_8, APPEND, WRITE);
```

Nếu muốn tạo khi chưa tồn tại *và* nối thêm nếu đã có:

```java
import static java.nio.file.StandardOpenOption.CREATE;

Files.writeString(notes, "Dòng mới\n",
                  StandardCharsets.UTF_8, CREATE, APPEND, WRITE);
```

Không nhầm `APPEND` với `TRUNCATE_EXISTING`. Hãy chọn rõ hợp đồng ghi mới, thay thế hay nối thêm; nhất là với file cấu hình, nhật ký và báo cáo.

### Đọc từng dòng và giới hạn bộ nhớ

`Files.readAllLines(path, charset)` trả về một `List<String>`; `Files.readString` trả về toàn bộ nội dung dạng `String`. Cả hai có thể tiêu thụ rất nhiều bộ nhớ nếu file lớn.

Để xử lý nhiều dòng mà không nạp tất cả vào một danh sách:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path log = Path.of("app.log");

try (var lines = Files.lines(log, StandardCharsets.UTF_8)) {
    long errorCount = lines
        .filter(line -> line.contains("ERROR"))
        .count();

    System.out.println("Số dòng lỗi: " + errorCount);
}
```

`Files.lines` trả về `Stream<String>` đọc dữ liệu khi tiêu thụ stream và **cần được đóng** bằng try-with-resources. Các lỗi I/O trong quá trình đọc lazy có thể được bọc trong `UncheckedIOException`.

Nếu cần đọc theo giao thức có cấu trúc hoặc quản lý từng dòng sâu hơn:

```java
try (var reader = Files.newBufferedReader(
        log, StandardCharsets.UTF_8)) {

    for (String line; (line = reader.readLine()) != null; ) {
        System.out.println(line);
    }
}
```

`BufferedReader` cần được đóng. Try-with-resources bảo đảm đóng khi rời khối kể cả có ngoại lệ, giúp tránh giữ file handle không cần thiết.

## 6. Tệp nhị phân và I/O theo luồng

Không nên giải mã dữ liệu nhị phân (ảnh, PDF, ZIP) thành `String` tùy tiện. Dùng API xử lý byte:

```java
Path source = Path.of("picture.png");

// Chỉ phù hợp nếu file đủ nhỏ để nằm trong bộ nhớ:
byte[] bytes = Files.readAllBytes(source);
System.out.println(bytes.length);
```

Với dữ liệu lớn, dùng stream:

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("large-input.bin");
Path output = Path.of("large-output.bin");

try (InputStream in = Files.newInputStream(input);
     OutputStream out = Files.newOutputStream(output)) {

    in.transferTo(out);
}
```

`InputStream.transferTo` chuyển các byte từ input sang output; các stream cần được đóng sau khi dùng. `Files.newOutputStream(output)` mặc định tạo file nếu chưa có và ghi đè nội dung cũ của file đã có, nên không dùng với đường dẫn quan trọng nếu chưa có ý định thay thế.

Nếu mục tiêu chỉ là sao chép toàn bộ file, `Files.copy(source, output)` thường trực tiếp hơn; ví dụ mở hai stream hữu ích khi phải kiểm soát hoặc biến đổi luồng byte.

### Định dạng byte thành văn bản

Nếu file có encoding khác UTF-8, phải chỉ ra charset thực tế:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

String utf8 = Files.readString(Path.of("utf8.txt"),
                              StandardCharsets.UTF_8);

// Chỉ khi file thực sự được mã hóa theo ISO-8859-1:
String latin1 = Files.readString(
    Path.of("latin1.txt"), StandardCharsets.ISO_8859_1);
```

Đừng thay đổi charset theo kiểu thử-ngẫu-nhiên rồi coi chuỗi “đọc được” là đúng. Sai encoding có thể làm mất hoặc biến dạng dữ liệu. Định dạng như JSON, XML hoặc CSV còn có quy tắc riêng về escape, cấu trúc và ký tự phân cách.

## 7. Kiểm tra sự tồn tại và đọc metadata

`Files` cung cấp nhiều phương thức để kiểm tra tệp:

```java
Path path = Path.of("data", "report.csv");

boolean exists = Files.exists(path);
boolean regularFile = Files.isRegularFile(path);
boolean directory = Files.isDirectory(path);
boolean readable = Files.isReadable(path);
```

**Lưu ý quan trọng:** `Files.exists(path)` và `Files.notExists(path)` **không phải phủ định logic tuyệt đối** của nhau. Nếu Java không thể xác định trạng thái (chẳng hạn do lỗi truy cập), **cả hai đều có thể trả về `false`**.

Ngoài ra, các kết quả kiểm tra chỉ phản ánh một thời điểm. Một tệp có thể bị tạo, đổi, xóa hoặc thay thế ngay sau đó. Với thao tác quan trọng, hãy gọi API thật và xử lý ngoại lệ thay vì giả định `exists`/`isWritable` bảo đảm thao tác sau chắc chắn thành công.

### BasicFileAttributes

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

Path file = Path.of("data", "report.csv");

BasicFileAttributes attrs =
    Files.readAttributes(file, BasicFileAttributes.class);

System.out.println(attrs.isRegularFile());
System.out.println(attrs.size());
System.out.println(attrs.lastModifiedTime());
```

`BasicFileAttributes` cung cấp thông tin cơ bản như loại tệp, kích thước, thời gian tạo, thời gian sửa và `fileKey()` (nếu provider hỗ trợ). Một số giá trị thời gian hoặc độ phân giải thuộc tính có thể khác nhau giữa các file system.

`Files.size(path)` cũng trả về kích thước file theo byte; không dùng nó để suy ra số ký tự Unicode của văn bản. Với symbolic link, nếu yêu cầu kiểm tra chính bản thân link, truyền `LinkOption.NOFOLLOW_LINKS` cho API có hỗ trợ.

Các quyền truy cập cũng phụ thuộc nền tảng. Ví dụ `Files.getPosixFilePermissions` chỉ phù hợp với file store hỗ trợ thuộc tính POSIX; không giả định mọi file system Windows đều hỗ trợ.

## 8. Duyệt thư mục bằng list, walk và find

### Files.list: liệt kê một cấp

```java
Path directory = Path.of("reports");

try (var entries = Files.list(directory)) {
    entries
        .map(path -> path.getFileName().toString())
        .sorted()
        .forEach(System.out::println);
}
```

`Files.list` trả về stream các entry **trực tiếp** trong thư mục, không tự đi sâu vào các thư mục con. Không có cam kết thứ tự duyệt, nên ví dụ dùng `sorted()` để có kết quả hiển thị ổn định.

Vì stream giữ một tài nguyên thư mục đang mở, **bắt buộc đóng** bằng try-with-resources hoặc cơ chế tương đương. Không nên trả một stream từ `Files.list` ra ngoài phạm vi tài nguyên đã đóng rồi mới cố tiêu thụ nó.

### Files.walk: duyệt cây thư mục theo nhiều cấp

```java
Path root = Path.of("reports");

try (var paths = Files.walk(root)) {
    var files = paths
        .filter(Files::isRegularFile)
        .filter(path -> path.getFileName().toString().endsWith(".csv"))
        .sorted()
        .toList();

    files.forEach(System.out::println);
}
```

`Files.walk` duyệt cây theo chiều sâu, mặc định **không theo symbolic link đến thư mục đích**. Stream chứa cả chính `root`. Dùng `Files.walk(root, maxDepth)` để giới hạn độ sâu khi cần.

Nếu bật `FileVisitOption.FOLLOW_LINKS`, cần cân nhắc quyền truy cập, khả năng duyệt ra ngoài cây mong muốn và chu trình symbolic link. Đối với tập dữ liệu lớn, `.toList()` trong ví dụ cũng giữ mọi kết quả trong bộ nhớ; thay bằng xử lý tuần tự trên stream nếu không cần giữ danh sách.

### Files.find và walkFileTree

`Files.find` giúp tìm tệp bằng một predicate nhận cả `Path` và `BasicFileAttributes`:

```java
try (var found = Files.find(
        root,
        3,
        (path, attrs) -> attrs.isRegularFile()
            && path.getFileName().toString().endsWith(".log"))) {

    found.forEach(System.out::println);
}
```

`Files.find` có thể tránh đọc lại attributes so với việc gọi `Files.walk(...).filter(path -> Files.readAttributes(...))` cho từng phần tử.

Khi cần kiểm soát lỗi theo từng thư mục, giới hạn độ sâu và xử lý trước/sau khi vào thư mục, dùng `Files.walkFileTree` cùng `FileVisitor`/`SimpleFileVisitor`:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

Path tree = Path.of("reports");

Files.walkFileTree(tree, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
            throws IOException {
        if (attrs.isRegularFile()) {
            System.out.println(file);
        }
        return FileVisitResult.CONTINUE;
    }
});
```

Nếu bài toán chỉ là lấy vài tên file trực tiếp trong một thư mục, `Files.list` đơn giản hơn. Nếu cần duyệt cây phức tạp hoặc xử lý lỗi theo entry, `walkFileTree` giúp biểu diễn rõ hơn.

## 9. Sao chép, di chuyển và đổi tên

### Files.copy

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path source = Path.of("data", "source.txt");
Path backup = Path.of("backup", "source.txt");

Files.createDirectories(backup.getParent());
Files.copy(source, backup);
```

Theo mặc định, `Files.copy` thất bại nếu đích đã tồn tại (trừ trường hợp source và target là cùng tệp theo quy tắc API). Nếu chủ đích muốn thay thế file đích:

```java
Files.copy(source, backup, StandardCopyOption.REPLACE_EXISTING);
```

Có thể yêu cầu sao chép thuộc tính phù hợp bằng `COPY_ATTRIBUTES`, nhưng tập thuộc tính và độ chính xác thời gian sao chép phụ thuộc file system.

**Sao chép thư mục không đồng nghĩa sao chép đệ quy:** `Files.copy` cho một đường dẫn thư mục chỉ tạo bản sao thư mục ở đích theo hợp đồng API, không tự sao chép mọi tệp con. Để copy cả cây cần chủ động xây dựng thuật toán phù hợp hoặc dùng `walkFileTree`.

### Files.move

```java
Path draft = Path.of("data", "draft.txt");
Path finalName = Path.of("data", "final.txt");

Files.move(draft, finalName);
```

`Files.move` dùng để đổi tên hoặc di chuyển file; đường dẫn cũ thường không còn trỏ đến file đó sau khi di chuyển thành công. Thao tác di chuyển qua hai file store có thể có hạn chế khác với rename trong cùng file store.

```java
Files.move(
    draft,
    finalName,
    StandardCopyOption.REPLACE_EXISTING
);
```

Chỉ dùng `REPLACE_EXISTING` khi có chủ đích cho phép thay thế dữ liệu ở đích.

### ATOMIC_MOVE và giới hạn

```java
Files.move(
    draft,
    finalName,
    StandardCopyOption.ATOMIC_MOVE
);
```

`ATOMIC_MOVE` yêu cầu một thao tác di chuyển nguyên tử theo file system. Nếu provider không hỗ trợ, có thể ném `AtomicMoveNotSupportedException`. Đừng mặc định mọi file system, mọi ổ đĩa và mọi kiểu tệp đều hỗ trợ.

Khi `ATOMIC_MOVE` xuất hiện, các option khác có thể bị bỏ qua theo đặc tả; đặc biệt, việc xử lý **target đã tồn tại** là phụ thuộc implementation. Không thể lấy `ATOMIC_MOVE` kết hợp `REPLACE_EXISTING` làm một cam kết thay thế nguyên tử trên mọi hệ điều hành.

## 10. Xóa file và thư mục an toàn

```java
Files.delete(Path.of("data", "obsolete.txt"));
```

`delete` ném ngoại lệ khi đích không tồn tại hoặc không thể xóa. `deleteIfExists` trả về `false` nếu đích không có, nhưng vẫn có thể ném `IOException` trong các tình huống khác.

```java
boolean removed = Files.deleteIfExists(
    Path.of("data", "obsolete.txt")
);
```

Muốn xóa một thư mục bằng `Files.delete` thì thư mục thường phải **rỗng**. Nếu thư mục không rỗng, hệ thống có thể ném `DirectoryNotEmptyException`. Không có cơ chế `Files.deleteDirectoryRecursively` mặc định để người dùng vô tình xóa mọi dữ liệu.

Khi thật sự cần xóa một cây thư mục, phải có logic đệ quy hoặc `walkFileTree`, xóa tệp con trước rồi xóa thư mục cha. Chỉ thực hiện thao tác này trên vùng dữ liệu **được xác định chắc chắn và thuộc quyền quản lý của ứng dụng**. Với đường dẫn do người dùng đưa vào, cần bảo vệ nghiêm ngặt khỏi path traversal và symbolic link.

Nếu `Path` trỏ đến symbolic link, `Files.delete` xóa **bản thân link**, không xóa tệp đích mà link tham chiếu tới.

## 11. Symbolic link và các tình huống dễ nhầm

Symbolic link là một entry trong file system trỏ đến vị trí khác. Tùy phương thức và option, API có thể thao tác lên link hoặc đối tượng đích.

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

Path link = Path.of("data", "current");

boolean isLink = Files.isSymbolicLink(link);

boolean targetIsDirectory = Files.isDirectory(link);
// Mặc định thường đi theo symbolic link.

boolean entryItselfIsDirectory =
    Files.isDirectory(link, LinkOption.NOFOLLOW_LINKS);
// Kiểm tra bản thân entry, không đi theo link.
```

Dùng `Files.readSymbolicLink(link)` để lấy đường dẫn đích được lưu trong link khi provider hỗ trợ; đường dẫn trả về có thể là tương đối và chưa chắc đích tồn tại.

Không dùng `Path.normalize()` như biện pháp đảm bảo file nằm trong một thư mục an toàn. Ví dụ:

```java
Path base = Path.of("uploads").toAbsolutePath().normalize();
Path candidate = base.resolve(userSuppliedName).normalize();

if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Đường dẫn nằm ngoài vùng cho phép");
}
```

Đây là **kiểm tra ranh giới về mặt cú pháp** hữu ích trong một số luồng xử lý, nhưng không đủ làm security boundary đối với dữ liệu không đáng tin cậy: một symbolic link bên trong `uploads` vẫn có thể dẫn ra ngoài, và file system có thể thay đổi giữa lúc kiểm tra và lúc mở.

Với yêu cầu an ninh cao, cần thiết kế cơ chế truy cập theo thư mục tin cậy, quyền hệ điều hành, hạn chế symbolic link và cân nhắc `SecureDirectoryStream` khi provider hỗ trợ. Không tự tuyên bố rằng một phép `startsWith` đã giải quyết hoàn toàn directory traversal hay TOCTOU.

## 12. Lỗi I/O và try-with-resources

Hầu hết thao tác thực sự truy cập file system có thể thất bại: tệp bị xóa, không đủ quyền, thiếu dung lượng, sai kiểu file, không hỗ trợ option hoặc đường dẫn không hợp lệ.

Một số ngoại lệ thường gặp:

| Ngoại lệ | Tình huống |
|---|---|
| `NoSuchFileException` | Đường dẫn nguồn/đích cần thiết không tồn tại |
| `FileAlreadyExistsException` | Tạo file mới nhưng đích đã tồn tại |
| `AccessDeniedException` | File system không cho phép truy cập |
| `DirectoryNotEmptyException` | Xóa thư mục vẫn có entry |
| `AtomicMoveNotSupportedException` | Không hỗ trợ atomic move theo yêu cầu |
| `FileSystemException` | Lỗi file system có chi tiết về file và lý do |
| `IOException` | Lỗi I/O tổng quát, bao gồm các lỗi chuyên biệt bên trên |

Ví dụ xử lý phân biệt trường hợp file không tồn tại và lỗi khác:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path config = Path.of("config", "app.properties");

try {
    String text = Files.readString(config, StandardCharsets.UTF_8);
    System.out.println(text);
} catch (NoSuchFileException exception) {
    System.err.println("Chưa có tệp cấu hình: " + exception.getFile());
} catch (IOException exception) {
    System.err.println("Không đọc được cấu hình: " + exception.getMessage());
    throw exception;
}
```

Không bắt `IOException` rồi trả về một chuỗi rỗng tùy tiện nếu chuỗi rỗng có thể bị hiểu thành dữ liệu hợp lệ. Khi lỗi có ý nghĩa cần caller xử lý, hãy truyền lỗi ra ngoài hoặc chuyển thành một kiểu kết quả phù hợp với hợp đồng ứng dụng.

**Try-with-resources** cần dùng cho `InputStream`, `OutputStream`, `BufferedReader`, `BufferedWriter`, các stream từ `Files.list`, `Files.walk`, `Files.find` và `Files.lines`. Riêng `readString`/`writeString` tự quản lý tài nguyên I/O bên trong nên không yêu cầu caller đóng đối tượng kết quả.

## 13. Ghi thay thế file: tránh để lại nội dung dở dang

Ghi trực tiếp vào một file đang chứa dữ liệu quan trọng bằng chế độ `TRUNCATE_EXISTING` có thể khiến file bị cắt và chỉ ghi được một phần nếu tiến trình gặp lỗi. Một chiến lược phổ biến là ghi vào **file tạm cùng thư mục**, rồi chuyển sang đích:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

static void replaceText(Path target, String content) throws IOException {
    Path absolute = target.toAbsolutePath();
    Path parent = absolute.getParent();

    Files.createDirectories(parent);

    Path temporary = Files.createTempFile(parent, ".saving-", ".tmp");
    try {
        Files.writeString(
            temporary,
            content,
            StandardCharsets.UTF_8,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING
        );

        try {
            Files.move(
                temporary,
                absolute,
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING
            );
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(
                temporary,
                absolute,
                StandardCopyOption.REPLACE_EXISTING
            );
        }
    } finally {
        Files.deleteIfExists(temporary);
    }
}
```

Đây là **mẫu minh họa** cho thao tác thay thế tệp có kiểm soát, không phải một giao dịch hoàn chỉnh. Khi provider hỗ trợ `ATOMIC_MOVE`, cách xử lý trường hợp đích đã tồn tại có thể khác nhau giữa các file system; lệnh có thể thất bại thay vì thay thế. Nhánh fallback dùng `REPLACE_EXISTING` **không còn bảo đảm atomic**.

Ngoài ra, atomic rename không đồng nghĩa với khả năng khôi phục sau khi mất điện; nếu cần cam kết về durability, đồng bộ dữ liệu và thư mục cần được thiết kế theo hệ điều hành và yêu cầu lưu trữ. Với cấu hình có nhiều file phải cập nhật cùng lúc, một lần move cũng không tạo transaction xuyên nhiều tệp.

Nếu một hệ thống khác có thể thay đổi `target` đồng thời, cần thêm chiến lược điều phối hoặc kiểm soát phiên bản, không chỉ dùng file tạm.

## 14. Chương trình thực hành hoàn chỉnh

Chương trình sau tự tạo một **thư mục tạm riêng**, ghi hai dòng UTF-8, sao chép và đổi tên file, liệt kê thư mục, so sánh nội dung, rồi chỉ dọn dẹp chính cây thư mục tạm mà nó đã tạo. Điều này giúp thực hành mà không chủ động đụng vào tệp nghiệp vụ có sẵn.

Lưu thành `Nio2FileDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;

public class Nio2FileDemo {

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("java27-nio2-");

        try {
            Path reports = Files.createDirectories(root.resolve("reports"));
            Path source = reports.resolve("notes.txt");

            Files.writeString(
                source,
                "Xin chào Java 27\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
            );

            Files.writeString(
                source,
                "Dòng thứ hai\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.APPEND,
                StandardOpenOption.WRITE
            );

            String content = Files.readString(source, StandardCharsets.UTF_8);
            System.out.println("Số dòng: " + content.lines().count());

            Path copied = reports.resolve("copy.txt");
            Files.copy(source, copied);

            Path archived = reports.resolve("archived.txt");
            Files.move(copied, archived);

            try (var entries = Files.list(reports)) {
                var names = entries
                    .map(path -> path.getFileName().toString())
                    .sorted()
                    .toList();
                System.out.println("Tệp: " + names);
            }

            System.out.println(
                "Cùng nội dung: " + (Files.mismatch(source, archived) == -1L)
            );
        } finally {
            // root do chính chương trình vừa tạo; không thay bằng đường
            // dẫn bên ngoài hoặc đường dẫn từ người dùng không tin cậy.
            try (var paths = Files.walk(root)) {
                var ownedEntries = paths
                    .sorted(Comparator.reverseOrder())
                    .toList();

                for (var path : ownedEntries) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Chạy với JDK 27:

```shell
javac Nio2FileDemo.java
java Nio2FileDemo
```

Kết quả dự kiến:

```text
Số dòng: 2
Tệp: [archived.txt, notes.txt]
Cùng nội dung: true
```

`Files.mismatch(a, b)` trả `-1` nếu hai tệp có cùng nội dung byte; nếu khác nhau, nó trả vị trí byte khác đầu tiên. Trong `finally`, các đường dẫn được sắp theo thứ tự ngược để xóa tệp và thư mục con trước khi xóa thư mục cha. Đoạn dọn dẹp này chỉ an toàn nhờ `root` được tạo bởi `Files.createTempDirectory` ngay trong chương trình; **không** sao chép nguyên mẫu để xóa một đường dẫn tùy ý.

Nếu thao tác dọn dẹp cũng thất bại, `IOException` sẽ được báo ra caller. Trong hệ thống thực tế cần cân nhắc cách ghi nhận ngoại lệ, giữ lại tệp để điều tra và bảo đảm lỗi cleanup không làm mất thông tin về lỗi chính.

## 15. Chọn API và tránh những hiểu lầm phổ biến

| Nhu cầu | Lựa chọn phù hợp | Điều cần nhớ |
|---|---|---|
| Xây đường dẫn tương thích file system | `Path.of` và `resolve` | Không ghép chuỗi `/` thủ công |
| Tạo thư mục nhiều cấp | `Files.createDirectories` | Không bảo đảm rollback mọi thư mục khi lỗi |
| Tạo file nhưng không ghi đè | `Files.createFile` hoặc `CREATE_NEW` | Tránh kiểm tra `exists` rồi tạo |
| Đọc tệp UTF-8 nhỏ | `Files.readString` | Toàn bộ nội dung vào bộ nhớ |
| Ghi nội dung văn bản | `Files.writeString` | Chọn CREATE_NEW/APPEND/TRUNCATE rõ ràng |
| Đọc file log lớn | `Files.lines` hoặc `newBufferedReader` | Đóng stream/reader đúng cách |
| Sao chép toàn bộ file | `Files.copy` | Không copy đệ quy cả cây thư mục |
| Đổi tên hay di chuyển | `Files.move` | Kiểm tra chính sách thay thế và atomic |
| Liệt kê một cấp | `Files.list` | Không bảo đảm thứ tự, phải đóng stream |
| Duyệt nhiều cấp | `Files.walk`, `walkFileTree` | Cẩn thận symbolic link và quyền |
| Xem thông tin tệp | `Files.readAttributes` | Thuộc tính phụ thuộc file store |
| Xóa một entry | `Files.deleteIfExists` | Thư mục thường phải rỗng |
| Tệp tạm | `Files.createTempFile/Directory` | Quy hoạch vòng đời và cleanup |
| Dữ liệu không tin cậy | Kiểm tra đường dẫn + biện pháp file-system-aware | `normalize` không tự chặn symlink/race |

### Checklist trước khi đưa chức năng I/O vào sản phẩm

1. **Đường dẫn xuất phát từ đâu?** Working directory, cấu hình tin cậy hay input người dùng?
2. **File có thể rất lớn không?** Có cần đọc streaming thay vì `readString`/`readAllBytes`?
3. **Charset được xác định chưa?** Với văn bản, UTF-8 thường là lựa chọn tốt; không tự suy encoding theo máy.
4. **File đã tồn tại thì sao?** Từ chối, nối thêm, thay thế hay tạo phiên bản mới?
5. **Cần tính nguyên tử hoặc độ bền dữ liệu tới mức nào?** Atomic move không đồng nghĩa transaction/durability.
6. **Tài nguyên nào phải đóng?** Reader, writer, input/output stream, directory stream.
7. **Có symbolic link, path traversal, race condition hoặc quyền hạn file system không?**
8. **Có cần thứ tự hiển thị ổn định không?** Liệt kê file rồi `sorted` thay vì dựa vào thứ tự của file system.
9. **Khi lỗi xảy ra, caller phải biết gì?** Giữ nguyên nguyên nhân `IOException`, không nuốt lỗi.
10. **Nếu tạo file tạm, ai chịu trách nhiệm dọn dẹp?** Chỉ xóa dữ liệu trong vùng do ứng dụng sở hữu.

## 16. Bài tập tự kiểm tra

**Bài 1 — Cấu trúc thư mục:** Từ `Path.of("storage")`, tạo `storage/2026/reports/monthly.txt` bằng `resolve`; tạo thư mục cha với `Files.createDirectories`; ghi chuỗi UTF-8 mà không được ghi đè tệp đã tồn tại.

**Bài 2 — Đếm dòng log:** Viết phương thức nhận `Path` và trả số dòng chứa `WARN` bằng `Files.lines`. Dùng try-with-resources và khai báo `throws IOException`.

**Bài 3 — Đổi tên file:** Giả sử `draft.txt` tồn tại. Viết `Files.move` để đổi thành `final.txt` trong cùng thư mục mà không ghi đè đích. Nếu `final.txt` đã tồn tại, bạn mong đợi điều gì?

**Bài 4 — Path normalization:** So sánh `Path.of("a", "b", "..", "c").normalize()` với `toRealPath()`. Trường hợp nào cần truy cập file system?

**Bài 5 — Symbolic link:** Vì sao `base.resolve(input).normalize().startsWith(base)` chưa đủ để bảo vệ file upload? Nêu ít nhất một tình huống liên quan tới symbolic link.

**Bài 6 — File lớn:** Một file log dài nhiều GB. Vì sao `Files.readAllLines` không phù hợp? Hãy nêu API đọc tuần tự thích hợp.

### Đáp án gợi ý

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path base = Path.of("storage");
Path monthly = base.resolve("2026")
    .resolve("reports")
    .resolve("monthly.txt");

Files.createDirectories(monthly.getParent());
Files.writeString(
    monthly, "Tổng kết tháng\n", StandardCharsets.UTF_8,
    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE
);

static long countWarnings(Path file) throws IOException {
    try (var lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.filter(line -> line.contains("WARN")).count();
    }
}
```

Với bài 3, dùng `Files.move(draft, finalName)` mà không truyền `REPLACE_EXISTING`; nếu đích tồn tại, thao tác mặc định thất bại thay vì được phép ghi đè. Với bài 4, `normalize` chỉ rút gọn đường dẫn ở mức cú pháp còn `toRealPath` truy cập file system và yêu cầu đích tồn tại. Bài 5 yêu cầu nhận biết symbolic link bên trong base có thể dẫn tới file nằm ngoài base. Bài 6 dùng `Files.lines` hoặc `Files.newBufferedReader` để đọc dần thay vì nạp tất cả vào bộ nhớ.

## 17. Tổng kết

Trong Java 27, `Path` là cách biểu diễn đường dẫn hiện đại, còn `Files` cung cấp các thao tác tệp và thư mục của NIO.2. Khi thiết kế I/O, cần phân biệt rõ **mô tả đường dẫn** với **truy cập file system**, lựa chọn chế độ mở file, charset, cách xử lý tài nguyên và chính sách lỗi.

Những nguyên tắc quan trọng nhất là: dùng `Path.of`/`resolve` để xây đường dẫn; dùng `Files` cho thao tác thực tế; đọc tuần tự khi file lớn; luôn đóng stream/reader và directory stream; không giả định thứ tự duyệt; không coi `Files.exists` hoặc `Path.normalize` là bảo đảm an ninh; và xác định rõ khi nào được phép thay thế, di chuyển hoặc xóa dữ liệu. Làm đúng các điểm này sẽ giúp mã I/O dễ bảo trì và hoạt động đáng tin cậy hơn trên nhiều file system.

## Tài liệu tham khảo

- [Java SE 27 API — Path](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html): tạo, tách, kết hợp, normalize, toAbsolutePath và toRealPath.
- [Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): tạo file/thư mục, readString/writeString, copy/move/delete, list/walk/find, metadata.
- [Java SE 27 API — StandardOpenOption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW, CREATE, APPEND, TRUNCATE_EXISTING, SYNC và DSYNC.
- [Java SE 27 API — StandardCopyOption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/StandardCopyOption.html): REPLACE_EXISTING, COPY_ATTRIBUTES và ATOMIC_MOVE.
- [Java SE 27 API — LinkOption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/LinkOption.html): NOFOLLOW_LINKS và ngữ nghĩa symbolic link.
- [Java SE 27 API — BasicFileAttributes](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): các thuộc tính cơ bản của file.
- [Java SE 27 API — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): xử lý tệp và thư mục trong quá trình duyệt cây.
- [Java SE 27 API — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác theo directory entry để giảm một số rủi ro race condition khi provider hỗ trợ.
- [Java SE 27 API — StandardCharsets](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn, bao gồm UTF-8.
