# Path và Files trong thao tác tệp trên Java 17

Trong Java 17, API hiện đại để làm việc với đường dẫn và tệp nằm chủ yếu trong package `java.nio.file`. Hai kiểu quan trọng nhất là:

- **`Path`** mô tả đường dẫn đến tệp hoặc thư mục. Nó giúp ghép, tách, chuẩn hóa và so sánh đường dẫn theo hệ thống tệp.
- **`Files`** cung cấp các thao tác thực tế trên hệ thống tệp: kiểm tra thuộc tính, đọc/ghi nội dung, tạo thư mục, sao chép, di chuyển, xóa và duyệt cây thư mục.

`Path` là đối tượng mô tả vị trí; `Files` là lớp tiện ích thực hiện thao tác tại vị trí đó.

```text
Path
 │
 ├── of / resolve / normalize / relativize
 │       thao tác với cấu trúc đường dẫn
 │
 └── được truyền cho Files
          ├── exists / isDirectory / size
          ├── readString / writeString
          ├── copy / move / delete
          └── list / walk / readAttributes
```

Bài này dùng API chuẩn còn áp dụng trong Java 17, ưu tiên `Path.of` và `Files`. Không cần ghép chuỗi đường dẫn thủ công hoặc dựa vào API cũ `java.io.File` cho mã mới.

## 1. Vì sao nên dùng Path và Files?

Một cách dễ gặp là ghép đường dẫn bằng chuỗi:

```java
String file = "data" + "/" + "reports" + "/" + "summary.txt";
```

Cách này có một số vấn đề:

- Dấu phân cách đường dẫn có thể khác giữa Windows và Unix-like systems.
- Khó phân biệt đường dẫn tương đối, tuyệt đối và thành phần đường dẫn.
- Các thao tác file vẫn cần xử lý ngoại lệ và kiểm tra loại tệp.
- Ghép chuỗi tùy tiện dễ tạo đường dẫn sai hoặc lỗ hổng path traversal khi có đầu vào bên ngoài.

Với `Path`:

```java
import java.nio.file.Path;

Path file = Path.of("data", "reports", "summary.txt");
System.out.println(file);
```

`Path.of` tạo một đối tượng `Path` từ một hoặc nhiều thành phần. Provider của hệ thống tệp mặc định sẽ diễn giải cú pháp đường dẫn phù hợp với nền tảng.

Các lợi ích chính:

1. **Độc lập cách ghép đường dẫn:** dùng `resolve` thay vì tự thêm `/` hoặc `\\`.
2. **Có API chuyên dụng:** lấy tên tệp, thư mục cha, root, số thành phần, chuẩn hóa.
3. **Kết hợp tự nhiên với Files:** hầu hết phương thức của `Files` nhận `Path`.
4. **Dễ kiểm thử:** có thể tạo thư mục tạm hoặc dùng thư mục fixture.
5. **Rõ ràng về lỗi:** các thao tác file khai báo hoặc ném `IOException` và các kiểu lỗi cụ thể.

## 2. Tạo Path bằng Path.of

`Path` là interface. Cách thông dụng trong Java 17 là gọi static factory `Path.of`:

```java
import java.nio.file.Path;

Path relative = Path.of("documents", "notes.txt");
Path absolute = Path.of("C:\\", "work", "project", "README.md");
```

Trên Windows, một đường dẫn tuyệt đối có thể có dạng `C:\\work\\project\\README.md`. Trên Linux/macOS, đường dẫn tuyệt đối thường bắt đầu bằng `/`, ví dụ `/home/dev/project/README.md`.

Có thể truyền cả chuỗi:

```java
Path path = Path.of("data/reports/summary.txt");
```

Cú pháp phân cách được diễn giải theo hệ thống tệp đang dùng. Khi cần tạo đường dẫn có cấu trúc, dạng nhiều thành phần `Path.of("data", "reports", "summary.txt")` thường dễ đọc và ít phụ thuộc dấu phân cách hơn.

### 2.1. Path.of và Paths.get

`Paths.get(...)` vẫn là API hợp lệ trong Java 17; nó cũng tạo `Path`. Với mã mới, `Path.of(...)` thường là lựa chọn ngắn gọn và trực tiếp hơn:

```java
Path first = Path.of("data", "input.txt");
Path second = java.nio.file.Paths.get("data", "input.txt");
```

Hai cách trên có cùng mục đích. Không cần thay toàn bộ mã đang hoạt động chỉ vì thấy `Paths.get`; đây không phải API bị loại bỏ trong Java 17.

### 2.2. Path không có nghĩa tệp chắc chắn tồn tại

```java
Path path = Path.of("data", "input.txt");
```

Dòng trên chỉ tạo đối tượng mô tả đường dẫn. Nó **không tạo file**, không kiểm tra file tồn tại và cũng không đọc đĩa.

Chỉ khi gọi các thao tác như `Files.exists(path)`, `Files.readString(path)` hoặc `Files.createFile(path)`, chương trình mới tương tác với hệ thống tệp.

### 2.3. Path là immutable

Các phép toán trên `Path` tạo ra một `Path` mới, không sửa đối tượng ban đầu:

```java
Path base = Path.of("data");
Path report = base.resolve("report.txt");

System.out.println(base);   // data
System.out.println(report); // data/report.txt (dạng hiển thị tùy OS)
```

Có thể tái sử dụng `base` cho nhiều đường dẫn khác nhau mà không sợ lần `resolve` trước làm thay đổi nó.

## 3. Phân biệt đường dẫn tương đối và tuyệt đối

### 3.1. Đường dẫn tương đối

Đường dẫn tương đối không bắt đầu từ root của hệ thống tệp:

```java
Path path = Path.of("data", "report.txt");

System.out.println(path.isAbsolute()); // false
```

Nó được diễn giải tương đối với thư mục làm việc hiện tại (working directory) khi cần chuyển thành đường dẫn tuyệt đối hoặc thực hiện thao tác trên file.

Working directory thường là thư mục mà tiến trình Java được khởi chạy; nó có thể khác thư mục chứa file nguồn Java hoặc thư mục chứa JAR.

### 3.2. Đường dẫn tuyệt đối

Đường dẫn tuyệt đối xác định vị trí từ root của filesystem:

```java
Path absolute = Path.of("/var/app/data/report.txt");

System.out.println(absolute.isAbsolute()); // true trên Unix-like
```

Ví dụ trên là đường dẫn kiểu Unix. Không dùng chuỗi đó như đường dẫn Windows và ngược lại.

### 3.3. Chuyển sang đường dẫn tuyệt đối

`toAbsolutePath()` tạo một đường dẫn tuyệt đối dựa trên working directory nếu đường dẫn ban đầu là tương đối:

```java
Path relative = Path.of("data", "report.txt");
Path absolute = relative.toAbsolutePath();

System.out.println(absolute);
```

Phương thức này **không bảo đảm** đường dẫn đã tồn tại, không tự tạo thư mục và không phải lúc nào cũng phân giải symbolic link. Nó tạo biểu diễn tuyệt đối theo filesystem hiện tại.

### 3.4. Xem các thành phần của Path

```java
Path path = Path.of("reports", "2025", "summary.csv");

System.out.println(path.getFileName());  // summary.csv
System.out.println(path.getParent());    // reports/2025
System.out.println(path.getRoot());      // null nếu là relative path
System.out.println(path.getNameCount()); // số thành phần tên
System.out.println(path.getName(0));     // reports
System.out.println(path.isAbsolute());   // false
```

Lưu ý:

- `getFileName()` trả thành phần cuối, không nhất thiết là một file; nó có thể là tên thư mục.
- `getParent()` trả parent hoặc `null` nếu không có parent.
- `getRoot()` trả root của đường dẫn tuyệt đối; với relative path thường là `null`.
- `getNameCount()` đếm thành phần tên, không tính root.
- `getName(i)` lấy một thành phần theo chỉ số bắt đầu từ 0.

Không nên giả định một đường dẫn luôn có ít nhất một thành phần. Hãy kiểm tra `getNameCount()` và xử lý `null` khi dùng các phương thức có thể không trả kết quả.

## 4. resolve, resolveSibling và relativize

Đây là nhóm thao tác quan trọng nhất khi xây dựng đường dẫn.

### 4.1. resolve — nối thành phần vào đường dẫn gốc

`resolve` ghép một đường dẫn con vào đường dẫn hiện tại:

```java
Path root = Path.of("data");
Path report = root.resolve("reports");
Path file = report.resolve("summary.txt");

System.out.println(file);
```

Sơ đồ:

```text
data
  └── reports
        └── summary.txt
```

Có thể truyền nhiều thành phần bằng cách tạo một Path trước:

```java
Path file = Path.of("data")
        .resolve(Path.of("reports", "2025", "summary.csv"));
```

Nếu đối số của `resolve` là đường dẫn tuyệt đối, nó được trả về làm kết quả thay vì nối vào đường dẫn gốc:

```java
Path base = Path.of("data");
Path absolute = Path.of("/tmp/output.txt");

System.out.println(base.resolve(absolute)); // /tmp/output.txt trên Unix
```

Vì vậy, khi ghép đường dẫn từ dữ liệu người dùng, cần kiểm tra đầu vào có phải absolute path hay không; không được mặc định `resolve` luôn giữ kết quả bên trong base.

### 4.2. resolveSibling — thay thành phần cuối

`resolveSibling` tạo đường dẫn cùng parent nhưng thay phần cuối bằng tên/đường dẫn mới:

```java
Path source = Path.of("data", "report.txt");
Path backup = source.resolveSibling("report.txt.bak");

System.out.println(backup); // data/report.txt.bak
```

Thường dùng khi tạo tên file tạm, file backup hoặc file kết quả bên cạnh file gốc.

### 4.3. relativize — tính đường dẫn tương đối giữa hai Path

`relativize` tính đường dẫn từ một base tới một target:

```java
Path base = Path.of("data", "reports");
Path target = Path.of("data", "exports", "summary.csv");

Path relative = base.relativize(target);

System.out.println(relative); // ../exports/summary.csv
```

Nó không đọc filesystem và không kiểm tra đường dẫn đích có tồn tại. Đây là phép tính dựa trên cấu trúc path.

Hai path cần thuộc cùng filesystem/provider và phải có root tương thích. Trên Windows, hai đường dẫn thuộc hai drive khác nhau không thể luôn relativize được; có thể ném `IllegalArgumentException`.

### 4.4. normalize — chuẩn hóa dấu chấm và dấu hai chấm

`normalize` loại bỏ các thành phần dư về mặt cú pháp như `.` và có thể rút gọn cặp `name/..`:

```java
Path path = Path.of("data", "reports", "..", "exports", ".", "summary.csv");

Path normalized = path.normalize();

System.out.println(normalized); // data/exports/summary.csv
```

`normalize` chỉ thao tác với biểu diễn đường dẫn, **không truy cập filesystem**. Nó không xác nhận tệp tồn tại và không giải quyết symbolic link.

Điều này quan trọng khi có symbolic link: rút gọn `link/..` về mặt văn bản không phải lúc nào cũng tương đương với việc đi theo link thật rồi quay về parent. Không dùng `normalize` như một cách xác thực bảo mật hoàn chỉnh.

## 5. toRealPath và symbolic link

`toRealPath()` truy cập filesystem để lấy đường dẫn thực của một đối tượng tồn tại:

```java
Path real = Path.of("data", "report.txt").toRealPath();
System.out.println(real);
```

Thông thường, phương thức:

- Chuyển đường dẫn thành absolute path.
- Xác nhận đối tượng tồn tại.
- Loại bỏ thành phần dư và phân giải symbolic link theo mặc định.
- Có thể phát sinh `IOException` nếu không tìm thấy, không truy cập được hoặc filesystem gặp lỗi.

Có thể yêu cầu không theo symbolic link cuối cùng bằng `LinkOption.NOFOLLOW_LINKS`:

```java
import java.nio.file.LinkOption;

Path realWithoutFollowingFinalLink =
        Path.of("data", "shortcut").toRealPath(LinkOption.NOFOLLOW_LINKS);
```

Tùy filesystem và cấu trúc link, các thành phần trung gian vẫn có thể được xử lý theo quy tắc của provider; hãy xem Javadoc khi cần kiểm soát chính xác symbolic link.

### 5.1. Phân biệt ba phương thức

| Phương thức | Có truy cập filesystem? | Có yêu cầu file tồn tại? | Xử lý symbolic link |
|---|---|---|---|
| `normalize()` | Không | Không | Không phân giải |
| `toAbsolutePath()` | Dựa vào filesystem/working directory | Không | Không bảo đảm phân giải link |
| `toRealPath()` | Có | Có | Mặc định phân giải link |

Không đồng nhất đường dẫn tuyệt đối với đường dẫn thực. Một absolute path vẫn có thể chứa thành phần symbolic link hoặc tên chưa chuẩn hóa.

## 6. Kiểm tra tệp và thư mục bằng Files

`java.nio.file.Files` là lớp tiện ích chứa các phương thức static để thao tác trên filesystem.

### 6.1. Kiểm tra tồn tại

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "report.txt");

if (Files.exists(path)) {
    System.out.println("Path tồn tại");
} else {
    System.out.println("Không tìm thấy hoặc không xác định được");
}
```

Điểm cần nhớ: `Files.exists` trả `false` cả khi provider không thể xác định sự tồn tại do thiếu quyền hoặc lỗi khác. Nó không phải bảo đảm rằng thao tác tiếp theo chắc chắn thành công.

`Files.notExists(path)` cũng có thể trả `false` nếu không thể xác định. Vì vậy, trường hợp cả `exists` và `notExists` đều `false` có nghĩa là trạng thái chưa xác định.

Đừng viết logic quan trọng kiểu “check exists rồi mới write” với kỳ vọng tránh được mọi race condition. Giữa bước kiểm tra và bước thao tác, một tiến trình khác có thể thay đổi filesystem. Hãy gọi thao tác mong muốn và xử lý exception thực tế.

### 6.2. Kiểm tra loại đối tượng

```java
if (Files.isRegularFile(path)) {
    System.out.println("Tệp thông thường");
}

if (Files.isDirectory(path)) {
    System.out.println("Thư mục");
}

if (Files.isSymbolicLink(path)) {
    System.out.println("Symbolic link");
}
```

Các phương thức `isRegularFile` và `isDirectory` mặc định theo symbolic link. Nếu cần xét chính link thay vì đối tượng đích, truyền `LinkOption.NOFOLLOW_LINKS`:

```java
boolean isDirectoryWithoutFollowing =
        Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS);
```

Với `NOFOLLOW_LINKS`, một symbolic link không được coi là thư mục đích trong phép kiểm tra này.

### 6.3. Kiểm tra quyền truy cập

```java
System.out.println(Files.isReadable(path));
System.out.println(Files.isWritable(path));
System.out.println(Files.isExecutable(path));
```

Các phương thức này là thông tin tham khảo tại thời điểm kiểm tra. Quyền có thể thay đổi trước khi thao tác; filesystem, user đang chạy và chính sách hệ điều hành đều ảnh hưởng kết quả.

### 6.4. Kích thước và thời gian sửa đổi

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;

Path path = Path.of("data", "report.txt");

long size = Files.size(path);
FileTime modified = Files.getLastModifiedTime(path);

System.out.println("Bytes: " + size);
System.out.println("Modified: " + modified);
```

`Files.size` trả kích thước tính bằng byte, không phải số ký tự. Với file nén, sparse file hoặc filesystem đặc biệt, kích thước logic và dung lượng vật lý có thể khác nhau.

Các thao tác đọc metadata có thể ném `IOException` hoặc `SecurityException` tùy môi trường.

## 7. Đọc nội dung văn bản với Files và UTF-8

Trong Java 17, `Files.readString` và `Files.writeString` là API tiện dụng (có từ Java 11). Nên chỉ định charset rõ ràng để dữ liệu nhất quán giữa máy phát triển, server và container.

### 7.1. Đọc toàn bộ tệp thành String

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "message.txt");

String content = Files.readString(path, StandardCharsets.UTF_8);

System.out.println(content);
```

`readString` đọc toàn bộ nội dung file thành một `String`. Vì vậy, nó phù hợp với file văn bản có kích thước vừa phải. Không nên dùng cho file rất lớn nếu không muốn giữ toàn bộ nội dung trong bộ nhớ.

Java 17 cũng có overload `Files.readString(path)` dùng UTF-8 theo hợp đồng API; truyền `StandardCharsets.UTF_8` tường minh vẫn làm ý định của chương trình rõ ràng hơn.

### 7.2. Ghi String vào tệp

```java
String content = """
        Java 17
        Path and Files
        UTF-8
        """;

Path output = Path.of("data", "message.txt");

Files.writeString(output, content, StandardCharsets.UTF_8);
```

Overload cơ bản tạo file nếu chưa tồn tại và ghi nội dung, thay thế nội dung cũ. Nếu file đã tồn tại, nội dung trước đó bị truncate.

Nếu muốn kiểm soát rõ các tùy chọn:

```java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        output,
        content,
        StandardCharsets.UTF_8,
        CREATE,
        TRUNCATE_EXISTING,
        WRITE
);
```

Đừng dùng overload mặc định nếu nghiệp vụ yêu cầu **không được ghi đè** file đã có. Trong trường hợp đó, chọn option phù hợp hoặc tạo file bằng `CREATE_NEW`.

### 7.3. Thêm nội dung vào cuối file

```java
import static java.nio.file.StandardOpenOption.APPEND;
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        output,
        "A new log line\n",
        StandardCharsets.UTF_8,
        CREATE,
        WRITE,
        APPEND
);
```

`APPEND` ghi nội dung vào cuối file nếu filesystem hỗ trợ thao tác này. Khi nhiều thread hoặc process cùng ghi, không mặc định rằng các lần ghi lớn sẽ luôn được ghép thành từng record nguyên tử. Với log đồng thời, nên dùng logging framework hoặc cơ chế đồng bộ phù hợp.

### 7.4. Đọc file từng dòng

Nếu file lớn hoặc cần xử lý tuần tự, dùng `BufferedReader`:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "users.txt");

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

`try-with-resources` tự đóng reader kể cả khi đọc gặp lỗi. Đây là cách nên dùng cho tài nguyên file mở trong chương trình.

### 7.5. Files.lines — xử lý file bằng Stream

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "users.txt");

try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank())
         .forEach(System.out::println);
}
```

Stream trả về từ `Files.lines` giữ tài nguyên file mở. Vì vậy phải đóng stream bằng `try-with-resources`, kể cả khi pipeline kết thúc bằng terminal operation.

Không nên giữ stream này trong field hoặc trả nó ra khỏi phương thức mà không xác định rõ ai chịu trách nhiệm đóng.

## 8. Đọc và ghi byte cho file nhị phân

Không phải file nào cũng là văn bản. Ảnh, PDF, file nén và dữ liệu mã hóa cần được xử lý như byte.

### 8.1. Đọc toàn bộ byte

```java
byte[] data = Files.readAllBytes(Path.of("data", "image.png"));
```

Phù hợp với file nhỏ hoặc vừa. Với file lớn, đọc toàn bộ vào `byte[]` có thể gây tốn bộ nhớ.

### 8.2. Ghi byte

```java
byte[] data = {0x01, 0x02, 0x03, 0x04};

Files.write(
        Path.of("data", "binary.dat"),
        data
);
```

`Files.write` với `byte[]` không áp dụng charset. Nó ghi đúng các byte đã cho.

### 8.3. Dùng stream cho file lớn

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("data", "large.bin");
Path target = Path.of("backup", "large.bin");

Files.createDirectories(target.getParent());

try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
```

Có thể dùng `Files.copy(source, target)` nếu chỉ cần sao chép tệp; stream phù hợp khi cần xử lý nội dung trong quá trình truyền, chẳng hạn tính hash, lọc hoặc mã hóa.

## 9. Tạo file và thư mục

### 9.1. Tạo một thư mục

```java
Path directory = Path.of("data", "reports");

Files.createDirectory(directory);
```

`createDirectory` chỉ tạo **một thư mục cuối**. Parent phải tồn tại; nếu thư mục đã có, thao tác thường ném `FileAlreadyExistsException`.

### 9.2. Tạo toàn bộ thư mục cha

```java
Path directory = Path.of("output", "2025", "monthly");

Files.createDirectories(directory);
```

`createDirectories` tạo cả các thư mục cha còn thiếu. Nếu thư mục đã tồn tại, phương thức không báo lỗi chỉ vì nó đã tồn tại; tuy nhiên nếu một thành phần hiện tại không phải directory, thao tác vẫn có thể thất bại.

Đây là cách thường dùng trước khi ghi file vào một cấu trúc thư mục mới:

```java
Path output = Path.of("build", "reports", "summary.txt");
Files.createDirectories(output.getParent());
Files.writeString(output, "Report", StandardCharsets.UTF_8);
```

### 9.3. Tạo file mới

```java
Path file = Path.of("data", "new.txt");

Files.createFile(file);
```

`createFile` tạo file rỗng và thất bại nếu đường dẫn đã tồn tại. Nó hữu ích khi cần bảo đảm không ghi đè một file có sẵn.

### 9.4. Tạo file tạm và thư mục tạm

```java
Path tempFile = Files.createTempFile("app-", ".tmp");
Path tempDirectory = Files.createTempDirectory("app-work-");

System.out.println(tempFile);
System.out.println(tempDirectory);
```

Có thể chỉ định thư mục cha:

```java
Path workDir = Path.of("build", "tmp");
Files.createDirectories(workDir);

Path temp = Files.createTempFile(
        workDir,
        "report-",
        ".tmp"
);
```

Tên được tạo duy nhất trong phạm vi cơ chế của provider. File tạm vẫn là tài nguyên trên đĩa; ứng dụng phải có chính sách dọn dẹp phù hợp, đặc biệt khi tiến trình có thể bị dừng bất thường.

## 10. Sao chép, di chuyển và xóa

### 10.1. Copy — sao chép file

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path source = Path.of("data", "report.txt");
Path target = Path.of("backup", "report.txt");

Files.createDirectories(target.getParent());

Files.copy(source, target);
```

Mặc định, `Files.copy` không ghi đè đích đã tồn tại. Nếu muốn thay thế:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING
);
```

Có thể yêu cầu sao chép thuộc tính cơ bản nếu provider hỗ trợ:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);
```

`COPY_ATTRIBUTES` yêu cầu copy các thuộc tính file; mức hỗ trợ cụ thể phụ thuộc filesystem/provider.

Với symbolic link, mặc định thao tác copy thường theo link và copy đối tượng đích. Nếu muốn copy chính link, có thể dùng `LinkOption.NOFOLLOW_LINKS`; hành vi chi tiết phụ thuộc provider.

### 10.2. Move — di chuyển hoặc đổi tên

```java
Path source = Path.of("data", "draft.txt");
Path target = Path.of("data", "final.txt");

Files.move(source, target);
```

Nếu đích đã tồn tại, thao tác mặc định không ghi đè. Có thể yêu cầu thay thế:

```java
Files.move(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING
);
```

Nếu nguồn và đích ở cùng filesystem, move thường có thể được thực hiện như thao tác đổi tên. Nếu khác filesystem, provider có thể phải copy rồi xóa hoặc báo lỗi tùy trường hợp.

### 10.3. Atomic move

Khi cập nhật file cấu hình hoặc file kết quả, có thể muốn người đọc chỉ thấy phiên bản cũ hoặc phiên bản mới, không thấy file ghi dở. Có thể yêu cầu `ATOMIC_MOVE`:

```java
Files.move(
        temporaryFile,
        destination,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING
);
```

Nếu filesystem không hỗ trợ, có thể ném `AtomicMoveNotSupportedException`. Không tự giả định atomic move hoạt động trên mọi filesystem hoặc qua mọi mount/network share.

Một quy trình thường dùng:

1. Tạo file tạm trong cùng thư mục/filesystem với đích.
2. Ghi đầy đủ nội dung vào file tạm.
3. Đóng stream/writer.
4. Di chuyển file tạm sang đích bằng `ATOMIC_MOVE` nếu provider hỗ trợ.
5. Xử lý ngoại lệ và dọn file tạm còn sót.

Việc tạo file tạm trên cùng filesystem làm tăng khả năng atomic move được hỗ trợ. Tính bền vững khi mất điện hoặc lỗi phần cứng còn phụ thuộc flush/fsync và filesystem; atomic rename không đồng nghĩa dữ liệu đã được ghi bền vững xuống thiết bị.

### 10.4. Delete và deleteIfExists

```java
Files.delete(Path.of("data", "old.txt"));
```

`delete` ném `NoSuchFileException` nếu đường dẫn không tồn tại. Để xóa nếu có và không lỗi chỉ vì file vắng mặt:

```java
boolean deleted = Files.deleteIfExists(Path.of("data", "old.txt"));
System.out.println(deleted);
```

`deleteIfExists` trả `true` nếu đã xóa, `false` nếu không có đối tượng để xóa.

Thư mục chỉ xóa được khi rỗng. Nếu còn file con, thao tác thường ném `DirectoryNotEmptyException`.

**Cẩn thận:** xóa file là thao tác có tác động thật lên dữ liệu. Trước khi xóa theo danh sách hoặc pattern, hãy xác định chính xác phạm vi và tránh để đường dẫn do người dùng nhập quyết định tùy tiện.

## 11. Liệt kê nội dung thư mục

### 11.1. Files.list — các phần tử trực tiếp

```java
Path directory = Path.of("data");

try (var entries = Files.list(directory)) {
    entries.forEach(System.out::println);
}
```

`Files.list` chỉ liệt kê các phần tử trực tiếp bên trong thư mục, không đi sâu vào thư mục con.

Kết quả là `Stream<Path>` và cần được đóng. Dùng `try-with-resources` như ví dụ.

### 11.2. Lọc theo phần mở rộng

```java
try (var entries = Files.list(Path.of("data"))) {
    entries.filter(Files::isRegularFile)
           .filter(path -> path.getFileName().toString().endsWith(".txt"))
           .forEach(System.out::println);
}
```

Đây là cách đơn giản để tìm file văn bản ở một cấp thư mục. So sánh phần mở rộng theo chữ hoa/chữ thường tùy quy ước ứng dụng; không phải filesystem nào cũng phân biệt hoa thường giống nhau.

### 11.3. DirectoryStream

Nếu cần duyệt từng phần tử theo kiểu iterator, dùng `DirectoryStream`:

```java
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path directory = Path.of("data");

try (DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory, "*.txt")) {
    for (Path entry : stream) {
        System.out.println(entry);
    }
}
```

Filter glob `*.txt` giúp giới hạn phần tử theo tên. `DirectoryStream` cũng là tài nguyên cần đóng.

## 12. Duyệt cây thư mục với Files.walk

`Files.walk` tạo stream đi qua một cây thư mục theo chiều sâu (depth-first). Mặc định nó không theo symbolic link.

```java
Path root = Path.of("project");

try (var paths = Files.walk(root)) {
    paths.forEach(System.out::println);
}
```

### 12.1. Giới hạn độ sâu

```java
try (var paths = Files.walk(Path.of("project"), 2)) {
    paths.forEach(System.out::println);
}
```

Độ sâu 0 là chính root; độ sâu 1 là các phần tử trực tiếp; độ sâu 2 đi thêm một cấp.

### 12.2. Chỉ tìm file .java

```java
try (var paths = Files.walk(Path.of("src"))) {
    paths.filter(Files::isRegularFile)
         .filter(path -> path.toString().endsWith(".java"))
         .forEach(System.out::println);
}
```

### 12.3. Files.find — lọc kèm thuộc tính

`Files.find` cho predicate nhận cả `Path` và `BasicFileAttributes`:

```java
import java.nio.file.attribute.BasicFileAttributes;

try (var found = Files.find(
        Path.of("project"),
        10,
        (path, attrs) -> attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".log")
)) {
    found.forEach(System.out::println);
}
```

Nếu cần nhiều thuộc tính, predicate có thể dùng `attrs.size()`, `attrs.lastModifiedTime()`, v.v. Điều này tránh phải gọi nhiều truy vấn metadata riêng cho từng path.

### 12.4. Files.walk và symbolic link

Mặc định `Files.walk` không đi theo symbolic link. Nếu truyền `FileVisitOption.FOLLOW_LINKS`, nó có thể đi vào các link và phải xử lý vòng lặp filesystem.

```java
import java.nio.file.FileVisitOption;

try (var paths = Files.walk(
        Path.of("project"),
        FileVisitOption.FOLLOW_LINKS
)) {
    paths.forEach(System.out::println);
}
```

Đi theo symbolic link có thể dẫn ra ngoài thư mục gốc hoặc tạo chu trình. Nếu không thực sự cần, giữ mặc định dễ dự đoán hơn.

## 13. Files.walkFileTree cho thao tác duyệt nâng cao

Khi cần xử lý riêng lúc vào thư mục, gặp file, lỗi truy cập hoặc kết thúc thư mục, dùng `Files.walkFileTree` với `FileVisitor`.

Ví dụ chỉ in các file thông thường:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

Path root = Path.of("project");

Files.walkFileTree(root, new SimpleFileVisitor<>() {
    @Override
    public FileVisitResult visitFile(
            Path file,
            BasicFileAttributes attrs
    ) {
        if (attrs.isRegularFile()) {
            System.out.println(file);
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFileFailed(
            Path file,
            IOException exc
    ) {
        System.err.println("Cannot visit " + file + ": " + exc);
        return FileVisitResult.CONTINUE;
    }
});
```

Các callback quan trọng:

| Callback | Thời điểm |
|---|---|
| `preVisitDirectory` | Trước khi duyệt nội dung thư mục |
| `visitFile` | Khi gặp một file hoặc link không được theo |
| `visitFileFailed` | Khi không truy cập được một path |
| `postVisitDirectory` | Sau khi duyệt xong một thư mục |

`FileVisitResult` điều khiển quá trình:

- `CONTINUE`: tiếp tục.
- `SKIP_SUBTREE`: bỏ qua phần còn lại của thư mục hiện tại.
- `SKIP_SIBLINGS`: bỏ qua các phần tử cùng cấp còn lại.
- `TERMINATE`: dừng toàn bộ quá trình.

Dùng API này khi cần xây dựng công cụ backup, kiểm kê file, dọn dẹp thư mục hoặc báo cáo lỗi duyệt cây chi tiết.

## 14. Đọc thuộc tính bằng BasicFileAttributes

`Files.readAttributes` cho phép đọc một nhóm metadata trong một lần gọi:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

Path path = Path.of("data", "report.txt");

BasicFileAttributes attrs = Files.readAttributes(
        path,
        BasicFileAttributes.class
);

System.out.println("Regular file: " + attrs.isRegularFile());
System.out.println("Directory: " + attrs.isDirectory());
System.out.println("Symbolic link: " + attrs.isSymbolicLink());
System.out.println("Size: " + attrs.size());
System.out.println("Created: " + attrs.creationTime());
System.out.println("Modified: " + attrs.lastModifiedTime());
System.out.println("Accessed: " + attrs.lastAccessTime());
```

`BasicFileAttributes` là bộ thuộc tính cơ bản được hỗ trợ rộng rãi. Filesystem có thể cung cấp thêm thuộc tính qua view khác như POSIX hoặc DOS, nhưng không nên giả định mọi hệ điều hành đều hỗ trợ cùng tập thuộc tính.

Có thể yêu cầu đọc thuộc tính của symbolic link thay vì đối tượng đích:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);
```

Thời gian tạo file không được mọi filesystem hỗ trợ chính xác như nhau; timestamp có thể bị làm tròn hoặc không có giá trị đáng tin cậy. Không dùng metadata timestamp như một nguồn bảo đảm duy nhất cho tính toàn vẹn hoặc thứ tự sự kiện.

## 15. Charset và dữ liệu tệp

Vì bài thuộc chủ đề tệp và mã hóa ký tự, cần phân biệt **đọc byte** với **đọc văn bản**.

### 15.1. Text file: quy định UTF-8 ở cả hai đầu

```java
Path path = Path.of("data", "vietnamese.txt");

Files.writeString(
        path,
        "Xin chào, Java 17!",
        StandardCharsets.UTF_8
);

String restored = Files.readString(path, StandardCharsets.UTF_8);
```

Khi đọc file từ hệ thống khác, chỉ dùng UTF-8 nếu định dạng/giao thức quy định UTF-8. Nếu file được tạo bằng charset khác, phải chọn đúng charset của file đó.

### 15.2. Byte không tự cho biết charset

```java
byte[] bytes = Files.readAllBytes(Path.of("data", "message.txt"));

String text = new String(bytes, StandardCharsets.UTF_8);
```

`readAllBytes` chỉ lấy byte. Việc diễn giải thành chữ do `new String(bytes, charset)` thực hiện. Nếu chọn sai charset, byte vẫn đọc thành công nhưng nội dung văn bản có thể sai.

### 15.3. Khi cần phát hiện dữ liệu UTF-8 lỗi

`new String(bytes, UTF_8)` có thể thay dãy byte lỗi bằng ký tự thay thế. Nếu ứng dụng cần từ chối file không phải UTF-8 hợp lệ, dùng decoder với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Với file lớn, không nên dùng `readAllBytes` như ví dụ; hãy dùng decoder trên stream/buffer theo từng phần. Ví dụ này tập trung minh họa chính sách phát hiện dữ liệu lỗi.

### 15.4. File nhị phân không được chuyển thành String tùy tiện

Không nên đọc ảnh, PDF, ZIP hoặc ciphertext thành `String` bằng UTF-8 rồi ghi ngược lại. Một số byte không phải chuỗi UTF-8 hợp lệ; quá trình decode có thể thay thế hoặc làm mất dữ liệu.

Với file nhị phân, dùng `byte[]`, `InputStream`, `OutputStream` hoặc channel.

## 16. Xử lý exception khi thao tác file

Các phương thức `Files` thường ném `IOException` hoặc kiểu con của nó. Không nên bỏ qua lỗi chỉ để chương trình tiếp tục.

| Exception | Tình huống thường gặp |
|---|---|
| `NoSuchFileException` | Không tìm thấy file hoặc thành phần đường dẫn |
| `FileAlreadyExistsException` | Tạo file/thư mục đã tồn tại |
| `AccessDeniedException` | Không đủ quyền hoặc bị hệ điều hành từ chối |
| `DirectoryNotEmptyException` | Xóa thư mục vẫn còn nội dung |
| `AtomicMoveNotSupportedException` | Filesystem không hỗ trợ yêu cầu atomic move |
| `FileSystemException` | Lỗi filesystem cụ thể, có thể kèm file và lý do |
| `InvalidPathException` | Chuỗi không tạo được Path hợp lệ; là runtime exception |

Ví dụ xử lý:

```java
try {
    String content = Files.readString(
            Path.of("data", "config.txt"),
            StandardCharsets.UTF_8
    );
    System.out.println(content);
} catch (NoSuchFileException ex) {
    System.err.println("Không tìm thấy file: " + ex.getFile());
} catch (AccessDeniedException ex) {
    System.err.println("Không có quyền đọc file: " + ex.getFile());
} catch (IOException ex) {
    System.err.println("Lỗi đọc file: " + ex.getMessage());
}
```

Đặt các exception cụ thể trước exception cha `IOException` để nhánh xử lý chi tiết có thể được chạy.

Với một tác vụ file đơn giản, có thể khai báo `throws IOException` để caller xử lý. Chọn cách nào tùy tầng nào có đủ ngữ cảnh để phục hồi hoặc thông báo lỗi có ý nghĩa.

### 16.1. Không dùng exists để thay thế xử lý exception

Mẫu dễ mắc race condition:

```java
if (Files.exists(path)) {
    String text = Files.readString(path);
}
```

Giữa lúc kiểm tra và lúc đọc, file có thể bị xóa, đổi quyền hoặc thay thế. Vì vậy vẫn phải xử lý exception từ `readString`.

Khi mục tiêu là đọc, cách rõ ràng thường là thực hiện đọc và xử lý `NoSuchFileException`/`IOException` phù hợp.

## 17. Path traversal và kiểm tra đường dẫn từ dữ liệu bên ngoài

Nếu ứng dụng cho phép người dùng chọn tên file, không ghép chuỗi trực tiếp:

```java
// Không an toàn nếu userInput do người dùng kiểm soát.
Path file = Path.of("uploads/" + userInput);
```

Một đầu vào như `../../secrets.txt` có thể khiến ứng dụng truy cập ngoài thư mục dự định. Đây là lỗi **path traversal**.

### 17.1. Chuẩn hóa và kiểm tra nằm trong thư mục gốc

Một bước kiểm tra cơ bản:

```java
Path base = Path.of("uploads").toAbsolutePath().normalize();

Path candidate = base.resolve(userInput).normalize();

if (!candidate.startsWith(base)) {
    throw new SecurityException("Path escapes upload directory");
}
```

`startsWith(Path)` so sánh theo thành phần đường dẫn, phù hợp hơn so với `candidate.toString().startsWith(base.toString())`. So sánh chuỗi có thể nhầm `/srv/uploads-evil` là con của `/srv/uploads`.

Nhưng kiểm tra lexical bằng `normalize` **chưa đủ để chống mọi tấn công** nếu kẻ khác có thể tạo hoặc thay symbolic link bên trong thư mục.

### 17.2. Lưu ý symbolic link và race condition

Trong hệ thống có yêu cầu bảo mật cao:

- Xác định thư mục gốc thực bằng `toRealPath`.
- Kiểm tra các thư mục cha thực tế, tránh để symbolic link dẫn ra ngoài.
- Không tin một lần kiểm tra path rồi mặc định trạng thái filesystem không thay đổi.
- Cân nhắc `SecureDirectoryStream` nếu provider hỗ trợ và cần thao tác tương đối an toàn trong thư mục đã mở.
- Giới hạn quyền ghi của tiến trình và quyền tạo symbolic link trong thư mục upload.

Ví dụ dưới đây minh họa thêm việc kiểm tra parent đã tồn tại trước khi tạo file:

```java
Path baseReal = Path.of("uploads").toRealPath();
Path candidate = baseReal.resolve(userInput).normalize();

if (!candidate.startsWith(baseReal)) {
    throw new SecurityException("Path escapes upload directory");
}

Path parentReal = candidate.getParent().toRealPath();

if (!parentReal.startsWith(baseReal)) {
    throw new SecurityException("Parent escapes upload directory");
}

Path safeCandidate = parentReal.resolve(candidate.getFileName());
```

Đây vẫn là ví dụ minh họa, không phải một cơ chế chống race condition hoàn chỉnh cho mọi threat model. Nếu thư mục có thể bị tiến trình không tin cậy sửa đồng thời, cần thiết kế thao tác dựa trên directory handle/provider phù hợp thay vì dựa vào nhiều bước kiểm tra tên đường dẫn.

## 18. Một số lưu ý về filesystem và tính di động

### 18.1. Dấu phân cách

Đừng tự giả định dấu phân cách là `/`. Có thể lấy separator của filesystem mặc định:

```java
String separator = java.nio.file.FileSystems.getDefault().getSeparator();
System.out.println(separator);
```

Tuy nhiên, khi ghép thành phần, hãy dùng `Path.of` và `resolve` thay vì tự nối separator.

### 18.2. Chữ hoa/thường trong tên file

Windows thường xử lý tên file không phân biệt hoa thường theo cấu hình phổ biến, còn Linux thường phân biệt. macOS có thể phụ thuộc filesystem và cách format volume.

Không viết ứng dụng giả định `Report.txt` và `report.txt` luôn là hai file riêng biệt hoặc luôn là cùng một file. Nếu cần portability, đặt quy tắc đặt tên nhất quán.

### 18.3. Tên file có ký tự đặc biệt

Một số ký tự bị cấm hoặc có ý nghĩa đặc biệt trên một số hệ điều hành (ví dụ dấu hai chấm trong tên thành phần Windows). `Path.of` có thể ném `InvalidPathException` nếu cú pháp không hợp lệ cho provider.

Không nên lấy tên file nguyên trạng từ người dùng mà không có chính sách lọc/chuẩn hóa phù hợp.

### 18.4. File permission không đồng nhất

`Files.isReadable` hoặc `Files.isWritable` là phép kiểm tra thuận tiện, nhưng quyền truy cập thực tế phụ thuộc user, ACL, mount, filesystem và chính sách hệ điều hành. Không giả định POSIX permission có trên Windows hoặc mọi provider.

### 18.5. Network filesystem và container

Trên network share, volume container hoặc filesystem ảo, một số thuộc tính và thao tác có thể có hành vi khác filesystem local. Atomic move, file lock, timestamp và quyền truy cập cần được xác minh theo môi trường triển khai.

## 19. Ví dụ hoàn chỉnh: đọc, ghi và sao lưu một file UTF-8

Tạo file `FileManagerDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class FileManagerDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Path.of("workspace", "reports");
        Path source = directory.resolve("summary.txt");
        Path backup = directory.resolve("summary.txt.bak");

        // Tạo thư mục cha nếu chưa tồn tại.
        Files.createDirectories(directory);

        // Ghi nội dung UTF-8.
        String content = """
                Java 17
                Path and Files
                Thao tác tệp an toàn
                """;

        Files.writeString(source, content, StandardCharsets.UTF_8);

        // Đọc lại nội dung bằng cùng charset.
        String loaded = Files.readString(source, StandardCharsets.UTF_8);
        System.out.println(loaded);

        // Sao lưu và thay thế backup cũ nếu có.
        Files.copy(
                source,
                backup,
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.COPY_ATTRIBUTES
        );

        // Hiển thị thuộc tính.
        System.out.println("Size: " + Files.size(source));
        System.out.println("Exists: " + Files.exists(backup));

        // Liệt kê file trực tiếp trong thư mục.
        try (var files = Files.list(directory)) {
            files.forEach(System.out::println);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 FileManagerDemo.java
java FileManagerDemo
```

Ví dụ minh họa các thao tác cơ bản trong một quy trình:

1. Dùng `Path.of` để tạo đường dẫn.
2. Dùng `resolve` để tạo đường dẫn file con.
3. Dùng `createDirectories` để chuẩn bị thư mục.
4. Dùng `writeString`/`readString` với UTF-8.
5. Dùng `copy` để sao lưu.
6. Dùng `size` và `exists` để xem thuộc tính.
7. Dùng `Files.list` để duyệt thư mục và đóng stream đúng cách.

## 20. Bảng tra cứu API Path và Files trong Java 17

| Nhu cầu | API |
|---|---|
| Tạo đường dẫn | `Path.of(...)` |
| Lấy parent / tên cuối | `getParent()` / `getFileName()` |
| Kiểm tra absolute | `isAbsolute()` |
| Chuyển absolute | `toAbsolutePath()` |
| Chuẩn hóa `.` và `..` | `normalize()` |
| Ghép đường dẫn con | `resolve(...)` |
| Thay thành phần cuối | `resolveSibling(...)` |
| Tính path tương đối | `relativize(...)` |
| Phân giải path thực | `toRealPath(...)` |
| Kiểm tra tồn tại | `Files.exists(...)` |
| Kiểm tra file/thư mục/link | `Files.isRegularFile` / `isDirectory` / `isSymbolicLink` |
| Đọc text UTF-8 | `Files.readString(path, UTF_8)` |
| Ghi text UTF-8 | `Files.writeString(path, text, UTF_8)` |
| Đọc byte | `Files.readAllBytes(...)` |
| Ghi byte | `Files.write(...)` |
| Đọc từng dòng | `Files.newBufferedReader(...)` / `Files.lines(...)` |
| Tạo thư mục cha | `Files.createDirectories(...)` |
| Tạo file rỗng | `Files.createFile(...)` |
| Tạo file tạm | `Files.createTempFile(...)` |
| Copy | `Files.copy(...)` |
| Move/rename | `Files.move(...)` |
| Xóa | `Files.delete(...)` / `deleteIfExists(...)` |
| Liệt kê một cấp | `Files.list(...)` / `newDirectoryStream(...)` |
| Duyệt cây thư mục | `Files.walk(...)` / `walkFileTree(...)` |
| Đọc metadata | `Files.size(...)` / `readAttributes(...)` |

## 21. Bài tập tự luyện

### Bài 1 — Xây dựng Path không phụ thuộc separator

Tạo đường dẫn tới file `data/logs/app.log` mà không tự nối dấu gạch chéo.

**Đáp án:**

```java
Path log = Path.of("data", "logs", "app.log");
```

### Bài 2 — Ghép đường dẫn và chuẩn hóa

Cho:

```java
Path base = Path.of("project", "src");
Path target = base.resolve(Path.of("main", "..", "test", "Demo.java"));
System.out.println(target.normalize());
```

**Đáp án:** `project/src/test/Demo.java` (dấu phân cách hiển thị phụ thuộc OS).

### Bài 3 — Ghi và đọc văn bản tiếng Việt

Viết `"Chào Java 17"` vào file rồi đọc lại mà không phụ thuộc charset mặc định.

**Đáp án:**

```java
Path file = Path.of("hello.txt");

Files.writeString(file, "Chào Java 17", StandardCharsets.UTF_8);
String text = Files.readString(file, StandardCharsets.UTF_8);
```

### Bài 4 — Liệt kê file .txt trong thư mục

Dùng `Files.list`, chỉ giữ regular file có tên kết thúc bằng `.txt` và đóng stream đúng cách.

**Đáp án:**

```java
try (var entries = Files.list(Path.of("data"))) {
    entries.filter(Files::isRegularFile)
           .filter(path -> path.getFileName().toString().endsWith(".txt"))
           .forEach(System.out::println);
}
```

### Bài 5 — Vì sao normalize không chống được symbolic link?

**Đáp án:** `normalize` chỉ rút gọn thành phần đường dẫn theo cú pháp. Nó không truy cập filesystem, không biết link đang trỏ tới đâu và không bảo đảm path nằm trong thư mục thực dự định. Với yêu cầu bảo mật, cần xem xét đường dẫn thực, symbolic link và race condition.

### Bài 6 — Chọn readString hay stream?

Một file log có dung lượng vài gigabyte cần xử lý tuần tự từng dòng. Nên chọn gì?

**Đáp án:** Dùng `Files.lines` hoặc `Files.newBufferedReader` trong `try-with-resources`. `readString` sẽ nạp toàn bộ nội dung vào bộ nhớ, không phù hợp với file rất lớn.

### Bài 7 — Copy hay move?

Bạn muốn tạo một bản backup và vẫn giữ file gốc.

**Đáp án:** Dùng `Files.copy`. `Files.move` chuyển file nguồn sang đích, nên file gốc không còn ở vị trí ban đầu sau khi move thành công.

## 22. Ghi nhớ

- **`Path` mô tả đường dẫn; `Files` thực hiện thao tác trên filesystem.**
- Dùng `Path.of` và `resolve` để tạo đường dẫn; tránh ghép chuỗi separator thủ công.
- `normalize` chỉ chuẩn hóa cấu trúc path; `toRealPath` truy cập filesystem và mặc định phân giải symbolic link.
- `exists` không bảo đảm thao tác tiếp theo thành công; hãy xử lý exception từ thao tác thực tế.
- Với văn bản, chỉ định charset rõ ràng, thường là `StandardCharsets.UTF_8`.
- Với file nhị phân, dùng byte array hoặc stream; không chuyển tùy tiện thành String.
- `Files.lines`, `Files.list` và `Files.walk` trả stream giữ tài nguyên; đóng bằng `try-with-resources`.
- Copy, move và delete có các option riêng; không giả định atomic move được hỗ trợ trên mọi filesystem.
- Khi nhận path từ người dùng, kiểm tra path traversal và symbolic link theo threat model; `normalize` một mình không phải biện pháp bảo mật hoàn chỉnh.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 API — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html).
- [Java SE 17 API — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [Java SE 17 API — `java.nio.file.StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).
- [Java SE 17 API — `java.nio.file.StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- [Java SE 17 API — `java.nio.file.DirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html).
- [Java SE 17 API — `java.nio.file.FileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html).
- [Java SE 17 API — `java.nio.file.attribute.BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html).
- [Java SE 17 API — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).

