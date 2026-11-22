# Khi nào nên ưu tiên `Path` và `Files` thay cho `java.io.File`?

Trong Java, cả `java.io.File` lẫn bộ API `java.nio.file` đều có thể đại diện cho tên đường dẫn tới file/thư mục và hỗ trợ những thao tác phổ biến trên hệ thống file. Tuy nhiên, khi viết **mã Java mới trên Java 17+**, phần lớn tình huống làm việc với file và thư mục nên **ưu tiên `Path` + `Files`** thay vì khởi tạo `File` rồi gọi các phương thức truyền thống.

Lý do không chỉ là cú pháp ngắn hơn. NIO.2 (xuất hiện từ Java 7) đem lại mô hình đường dẫn rõ ràng, thao tác file có ngoại lệ chứa nguyên nhân, lựa chọn tham số cho copy/move, API đọc/ghi hiện đại, thuộc tính file, duyệt cây thư mục, symbolic link, trình quan sát thay đổi thư mục và khả năng làm việc với các **file system provider** khác nhau.

Điều này **không có nghĩa `File` đã không còn dùng được**, hoặc tất cả dự án phải xóa ngay `java.io.File`. Mục tiêu là nhận biết khi nào `Path` + `Files` giúp giải quyết đúng bài toán, khi nào vẫn phải dùng `File` để tương thích và cách chuyển đổi an toàn giữa chúng.

## 1. `File`, `Path`, `Files` khác nhau ở vai trò nào?

### `java.io.File` — biểu diễn đường dẫn với API truyền thống

Một đối tượng `File` đại diện cho **tên đường dẫn trừu tượng** (abstract pathname). Nó có thể trỏ tới file, thư mục, đường dẫn chưa tồn tại hoặc vị trí không truy cập được. Việc tạo đối tượng `new File("report.txt")` **không tự tạo file thật** trên đĩa.

`File` kết hợp khá nhiều chức năng trong một lớp: thao tác tên đường dẫn (`getName()`, `getParentFile()`), kiểm tra (`exists()`, `isFile()`), tạo file/thư mục (`createNewFile()`, `mkdirs()`), xóa (`delete()`), đổi tên (`renameTo()`), liệt kê (`listFiles()`), v.v.

API này vẫn được sử dụng rộng rãi bởi thư viện và mã cũ, nhưng có một số nhược điểm:

- Nhiều phép toán trả về **`boolean`**: khi `delete()` hay `renameTo()` trả `false`, caller không nhận ngay ngoại lệ giải thích file không tồn tại, thiếu quyền, file đang được sử dụng hay do filesystem không hỗ trợ.
- Một số API liệt kê trả `null` nếu không phải thư mục **hoặc** khi xảy ra lỗi I/O; cần thêm logic để phân biệt.
- Cơ chế xử lý symbolic link, thuộc tính và copy/move đa dạng không đồng đều như NIO.2.
- `File` chủ yếu gắn với filesystem mặc định của môi trường, không mang mô hình provider tổng quát như `Path`.

### `java.nio.file.Path` — biểu diễn một đường dẫn

`Path` là **interface** thể hiện một vị trí trong filesystem: tên, phần tử đường dẫn, đường dẫn tương đối/tuyệt đối, thao tác `resolve`, `relativize`, `normalize`, `toAbsolutePath`, v.v.

Ví dụ:

```java
Path source = Path.of("data", "report.txt");
Path backup = source.resolveSibling("report.bak");
```

Đây là **đoạn minh họa**, cần import `java.nio.file.Path`. Tương tự `File`, việc tạo một `Path` **không đọc, ghi hoặc kiểm tra** file có thật. `Path` cũng không giữ một file descriptor đã mở.

`Path.of(...)` có từ **Java 11**, còn `Paths.get(...)` có từ **Java 7**. Trong Java 17, `Path.of` thường gọn và đủ dùng.

### `java.nio.file.Files` — các thao tác trên file, thư mục và thuộc tính

`Files` là lớp tiện ích gồm nhiều phương thức tĩnh nhận `Path`:

```java
Files.createDirectories(directory);
Files.writeString(file, "Hello", StandardCharsets.UTF_8);
String text = Files.readString(file, StandardCharsets.UTF_8);
Files.copy(source, destination);
Files.move(oldPath, newPath);
Files.delete(file);
```

Đây là **mã minh họa**, cần các biến được định nghĩa, `IOException` được xử lý và import `java.nio.file.Files`, `java.nio.charset.StandardCharsets`. Các thao tác thật trên filesystem có thể ném ngoại lệ như `NoSuchFileException`, `FileAlreadyExistsException` hay `AccessDeniedException` (tùy provider), giúp caller phản ứng đúng hơn so với một giá trị `false` không rõ nguyên nhân.

> **Quy tắc thực hành:** Dùng **`Path` để mang đường dẫn**, **`Files` để thực hiện thao tác**, và các lớp stream/channel/reader/writer phù hợp khi cần truyền dữ liệu. `Path` + `Files` không phải tên gọi thay thế cho toàn bộ Java NIO không chặn (*non-blocking I/O*); các thao tác `Files` thường vẫn là **blocking I/O**.

## 2. So sánh để chọn API

| Nhu cầu | Cách truyền thống | Cách thường ưu tiên với Java 17+ | Lợi ích chính |
|---|---|---|---|
| Tạo đối tượng đường dẫn | `new File("data/report.txt")` | `Path.of("data", "report.txt")` | API đường dẫn rõ ràng, provider-aware |
| Tạo thư mục và các thư mục cha | `file.mkdirs()` | `Files.createDirectories(path)` | Ngoại lệ khi thất bại, không chỉ `false` |
| Tạo file trống mới | `file.createNewFile()` | `Files.createFile(path)` | Báo file đã tồn tại qua `FileAlreadyExistsException` |
| Kiểm tra loại đường dẫn | `isFile()`, `isDirectory()` | `Files.isRegularFile`, `Files.isDirectory` | Có lựa chọn xử lý symbolic link |
| Đọc file text nhỏ | Mở `FileReader`/`BufferedReader` | `Files.readString(path, UTF_8)` | Gọn, charset tường minh |
| Ghi file text nhỏ | Mở `FileWriter` | `Files.writeString(path, text, UTF_8)` | Tùy chọn tạo/ghi đè/thêm |
| Đọc file lớn theo luồng | `FileInputStream` hoặc `BufferedReader` | `Files.newInputStream` / `Files.newBufferedReader` | Kết hợp đường dẫn, charset và stream |
| Sao chép file | Tự viết vòng lặp input/output | `Files.copy(source, target, options...)` | Có tùy chọn và ngoại lệ |
| Di chuyển/đổi tên | `renameTo` | `Files.move(source, target, options...)` | API rõ nghĩa, tùy chọn atomic khi được hỗ trợ |
| Xóa file | `delete()` trả boolean | `Files.delete(path)` / `deleteIfExists(path)` | Phân biệt trường hợp không tồn tại và lỗi |
| Liệt kê thư mục | `listFiles()` | `Files.list(dir)` / `newDirectoryStream(dir)` | Stream/filter linh hoạt, nhớ đóng |
| Duyệt cây thư mục | Viết recursion bằng `listFiles` | `Files.walk` / `walkFileTree` | Visitor, kiểm soát vòng đời và lỗi |
| Đọc metadata | `length()` / `lastModified()` | `Files.size` / `readAttributes` | Thuộc tính phong phú hơn |
| Symbolic link | Khả năng hạn chế | `Files.isSymbolicLink`, `readSymbolicLink`, `NOFOLLOW_LINKS` | Kiểm soát có chủ đích |
| Theo dõi thay đổi thư mục | Tự polling | `WatchService` | Nhận sự kiện, có giới hạn provider |

**Không dùng bảng như quy tắc tuyệt đối.** Nếu API thư viện bắt buộc `File`, truyền `File` là hợp lý. Với filesystem ảo hoặc provider đặc biệt, `Path` mới là mô hình đúng; `Path.toFile()` có thể không hỗ trợ.

## 3. Khi nào `Path` + `Files` là lựa chọn ưu tiên?

### 3.1 Khi bắt đầu một chức năng thao tác file mới

Nếu service cần đọc, ghi, sao chép, di chuyển hoặc kiểm tra file, API `Files` thường giảm lượng boilerplate. Ví dụ thay vì xây dựng chuỗi đường dẫn bằng dấu `"/"` hoặc `"\\"` theo nền tảng:

```java
Path directory = Path.of("data", "reports");
Path report = directory.resolve("october.txt");
```

`Path` diễn giải dấu phân cách dựa trên filesystem tương ứng. Không cần tự nối `"data/" + name` và hy vọng hoạt động ở mọi nơi.

### 3.2 Khi cần biết **vì sao** thao tác thất bại

`File.delete()` trả `false` khi không xóa được. `Files.delete(path)` khai báo `throws IOException` và có thể ném những lớp chuyên biệt như `NoSuchFileException` hoặc `DirectoryNotEmptyException`. Caller có thể phân biệt:

- File không tồn tại: bỏ qua nếu nghiệp vụ cho phép, hoặc báo lỗi cụ thể.
- Thư mục không rỗng: quyết định có cần thao tác đệ quy không; `Files.delete` **không tự xóa đệ quy**.
- Không đủ quyền hoặc filesystem từ chối: báo lỗi vận hành và không giả làm “không có file”.

**Lưu ý:** những exception cụ thể còn tùy hệ điều hành/file system provider; không có bảo đảm mọi nền tảng sẽ ném đúng một subtype giống nhau trong mọi tình huống. Vẫn phải xử lý `IOException` tổng quát.

### 3.3 Khi phải quản lý tạo thư mục, ghi file với options

`Files.createDirectories(path)` tạo các thư mục cha cần thiết; nếu đường dẫn đã là thư mục thì thao tác có thể thành công. Khác với `Files.createDirectory(path)`, nó hỗ trợ nhiều cấp chưa tồn tại.

`Files.writeString`/`write` hỗ trợ `StandardOpenOption` rõ ràng. Ví dụ:

- Mặc định của `Files.writeString(path, text, charset)` là tạo file nếu chưa có hoặc cắt nội dung file cũ rồi ghi mới.
- `CREATE_NEW`: chỉ tạo nếu chưa có, báo lỗi nếu đường dẫn đã tồn tại (dùng khi không muốn ghi đè).
- `APPEND`: thêm nội dung vào cuối; cần cân nhắc newline và tương thích option.
- `TRUNCATE_EXISTING`: rút file về độ dài 0 khi mở để ghi nếu được chọn.
- `WRITE`: mở để ghi.

**Đừng gọi `writeString` mà không xét khả năng ghi đè nội dung cũ.** Với cấu hình hay dữ liệu quan trọng, chọn `CREATE_NEW` hoặc chiến lược file tạm theo yêu cầu.

### 3.4 Khi cần copy/move với semantics có chủ đích

`Files.copy` và `Files.move` hỗ trợ các option như `StandardCopyOption.REPLACE_EXISTING` (thay thế đích trong phạm vi contract) và `StandardCopyOption.COPY_ATTRIBUTES` (khi áp dụng cho copy, với giới hạn provider).

`StandardCopyOption.ATOMIC_MOVE` yêu cầu một thao tác move nguyên tử nếu provider/filesystem hỗ trợ; có thể ném `AtomicMoveNotSupportedException` khi không hỗ trợ. **Không giả định atomic move luôn sẵn**, đặc biệt qua filesystem khác nhau. Nếu fallback sang move thường thì phải hiểu rằng nó **không còn đảm bảo atomicity**.

Phân biệt:

- **Copy:** giữ nguồn và tạo bản sao đích; `Files.copy(source, target)` không tự copy toàn bộ cây thư mục đệ quy. Copy một đường dẫn thư mục theo API thông thường không có nghĩa toàn bộ nội dung con đều được copy.
- **Move:** chuyển đường dẫn hoặc nội dung theo hành vi provider; không đồng nghĩa “copy rồi delete” luôn an toàn hay nguyên tử.
- **Replace existing:** cần cân nhắc ghi đè tài nguyên đích, không tự bật chỉ vì code ngắn hơn.

### 3.5 Khi cần thuộc tính file, symbolic link và filesystem khác nhau

`Files.readAttributes`, `Files.getLastModifiedTime`, `Files.size`, `Files.getOwner` và các API attribute view giúp lấy thông tin đa dạng hơn `File.length()` hoặc `lastModified()`. Thuộc tính khả dụng phụ thuộc filesystem và provider.

`Files.isSymbolicLink(path)` xác định đường dẫn là symbolic link; `NOFOLLOW_LINKS` là tùy chọn dùng trong các thao tác hỗ trợ để không tự theo link. Điều này quan trọng cho chức năng dọn thư mục, sao lưu, đồng bộ và thao tác trên đường dẫn đến từ bên ngoài.

`Path` gắn với một `FileSystem` và provider. NIO.2 có thể làm việc với các filesystem provider khác (ví dụ ZIP filesystem khi có provider tương ứng), trong khi `java.io.File` thường chỉ làm việc với filesystem mặc định.

## 4. `Path` biểu diễn tên, không bảo đảm file tồn tại

Các phương thức của `Path` chủ yếu biến đổi **cú pháp đường dẫn**, không đụng đĩa:

- `getFileName()`: lấy thành phần tên cuối.
- `getParent()`: lấy phần đường dẫn cha (có thể `null`).
- `getRoot()`: lấy root (có thể `null`).
- `resolve(other)`: kết hợp đường dẫn; nếu `other` là đường dẫn tuyệt đối, `resolve` thường trả đường dẫn tuyệt đối đó.
- `resolveSibling(other)`: thay tên cuối bằng đường dẫn sibling bên cùng cha.
- `normalize()`: loại bỏ các đoạn `.` và giải quyết `..` theo cú pháp, **không truy cập filesystem**.
- `toAbsolutePath()`: tạo đường dẫn tuyệt đối theo filesystem/context của provider, không chứng minh file tồn tại.
- `toRealPath(...)`: truy cập filesystem để lấy đường dẫn thực của một mục **đang tồn tại**, thường giải quyết symbolic link theo options, và có thể ném `IOException`.
- `relativize(other)`: tạo quan hệ tương đối giữa hai `Path` tương thích; có thể lỗi khi trộn root/tuyệt đối/tương đối không tương thích.

### Ví dụ 1 — `resolve`, `normalize`, `resolveSibling`, `relativize`

Tạo tệp `PathSemanticsDemo.java`:

```java
import java.nio.file.Path;

public class PathSemanticsDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "data").toAbsolutePath().normalize();
        Path report = base.resolve("..").resolve("report.txt").normalize();

        System.out.println("is absolute=" + report.isAbsolute());
        System.out.println("filename=" + report.getFileName());
        System.out.println("parent ends workspace="
                + report.getParent().endsWith("workspace"));
        System.out.println("resolveSibling matches="
                + report.equals(base.resolveSibling("report.txt")));
        System.out.println("relative name=" + report.getParent().relativize(report));
    }
}
```

Biên dịch/chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 PathSemanticsDemo.java
java PathSemanticsDemo
```

Kết quả:

```text
is absolute=true
filename=report.txt
parent ends workspace=true
resolveSibling matches=true
relative name=report.txt
```

Ví dụ không cần file `report.txt` có thật. `base` là đường dẫn tuyệt đối từ thư mục làm việc hiện tại, `resolve("..")` tạo đoạn cha theo cú pháp và `normalize()` loại bỏ đoạn thừa.

`Path.equals` so sánh đường dẫn **theo quy tắc equality của provider**, không nhất thiết tương đương “hai đường dẫn trỏ cùng file thật”. Ví dụ đường dẫn qua symbolic link hoặc tên khác kiểu case vẫn có thể cần `Files.isSameFile(a, b)` nếu muốn hỏi hai đường dẫn đang tồn tại có chỉ cùng một file hay không.

**Điều kiện quan trọng:** `normalize()` **không phải kiểm tra an ninh**. Nếu tồn tại symbolic link giữa các đoạn đường dẫn, kết quả chuẩn hóa cú pháp có thể khác đường đi vật lý. Không dùng nó một mình để xác nhận dữ liệu tải lên vẫn nằm trong thư mục được phép.

## 5. Ví dụ 2 — làm việc với file thật bằng `Files`

Tạo tệp `FilesCrudDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.stream.Stream;

public class FilesCrudDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("path-files-");
        try {
            Path folder = Files.createDirectories(root.resolve("docs/notes"));
            Path source = folder.resolve("note.txt");
            String content = "Xin chào Java\n";
            Files.writeString(source, content, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            Path copy = root.resolve("copy.txt");
            Files.copy(source, copy);
            Path moved = root.resolve("moved.txt");
            Files.move(copy, moved);

            System.out.println("folder directory=" + Files.isDirectory(folder));
            System.out.println("UTF-8 round trip="
                    + content.equals(Files.readString(source, StandardCharsets.UTF_8)));
            System.out.println("copy remains=" + Files.exists(copy));
            System.out.println("moved regular file=" + Files.isRegularFile(moved));
            System.out.println("contents equal="
                    + Files.readString(source, StandardCharsets.UTF_8)
                        .equals(Files.readString(moved, StandardCharsets.UTF_8)));
            System.out.println("file size positive=" + (Files.size(source) > 0));
            try (Stream<Path> walk = Files.walk(root)) {
                System.out.println("regular files=" + walk.filter(Files::isRegularFile).count());
            }
        } finally {
            try (Stream<Path> walk = Files.walk(root)) {
                walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FilesCrudDemo.java
java FilesCrudDemo
```

```text
folder directory=true
UTF-8 round trip=true
copy remains=false
moved regular file=true
contents equal=true
file size positive=true
regular files=2
```

**Giải thích theo thứ tự:**

1. `Files.createTempDirectory` tạo thư mục tạm riêng; tên thực tế có hậu tố ngẫu nhiên, nhưng ví dụ không in đường dẫn nên stdout ổn định.
2. `Files.createDirectories` tạo cả `docs` và `notes` bên trong thư mục tạm.
3. `Files.writeString` ghi tiếng Việt với `UTF-8` và `CREATE_NEW`, để không âm thầm ghi đè file `note.txt`.
4. `Files.copy` tạo file `copy.txt`. Sau `Files.move(copy, moved)`, đường dẫn `copy.txt` không còn, còn `moved.txt` là file hợp lệ.
5. `Files.readString` lấy nội dung text từ cả hai file và xác nhận dữ liệu không đổi. `Files.size(source)` cho số **byte**, không phải số `char` của Java.
6. `Files.walk(root)` duyệt toàn cây, lọc file thường và thấy hai file: `note.txt`, `moved.txt`.
7. Khối `finally` dọn file/thư mục tạm theo thứ tự sâu lên nông bằng `Comparator.reverseOrder()`; phương thức `walk` được đóng trong `try-with-resources`.

Mặc dù ví dụ có import `StandardCopyOption` để dễ mở rộng, demo này **không sử dụng** `REPLACE_EXISTING`: nếu đích đã tồn tại, thao tác copy/move thông thường có thể thất bại thay vì ghi đè. Với một cây thư mục do người dùng chỉ định, việc xóa đệ quy là hành động nguy hiểm; ví dụ chỉ dọn một thư mục tạm **do chính nó vừa tạo**, không phải mã xóa một đường dẫn tùy ý.

**Khả năng tương thích:** file trong ví dụ được tạo trên filesystem mặc định, nên hành vi phù hợp với Java 17 ở môi trường thông thường. Vẫn có thể phát sinh `IOException` nếu môi trường từ chối ghi/xóa hoặc hết dung lượng; chương trình không cam kết thao tác filesystem luôn thành công.

## 6. `Files.readString`, `writeString` và dữ liệu lớn

### Đọc hoặc ghi file text nhỏ

Với Java 11+:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa**: phải khai báo `Path path`, import `Files`/`StandardCharsets` và xử lý `IOException`. Nó phù hợp với cấu hình, tệp văn bản nhỏ, snapshot có kích thước vừa phải.

Nếu cần đọc từng dòng của file lớn, chọn `Files.newBufferedReader(path, UTF_8)` hoặc `Files.lines(path, UTF_8)`, chứ không nhất thiết đưa toàn bộ file vào một chuỗi. Nếu cần xử lý file nhị phân, chọn `Files.newInputStream`, `Files.newOutputStream` hoặc `Files.newByteChannel`.

### API streaming phải được đóng

Ví dụ đọc từng dòng:

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank()).forEach(System.out::println);
}
```

Đây là **đoạn minh họa**, cần import `java.util.stream.Stream`, `Path`, `Files` và charset tương ứng. `Files.lines` giữ tài nguyên file bên dưới; **gọi terminal operation không thay thế close**. Dùng `try-with-resources` để đóng stream.

Tương tự, `Files.list(dir)`, `Files.walk(dir)` và `Files.find(...)` trả stream gắn với tài nguyên hệ thống. Việc quên đóng gây rò rỉ descriptor hoặc handle, đặc biệt khi service hoạt động liên tục.

### Byte I/O và charset là hai vấn đề khác nhau

`Path` và `Files` không tự biến dữ liệu nhị phân thành text. Khi đọc văn bản, chỉ định charset phù hợp (thường `StandardCharsets.UTF_8`); khi đọc ảnh/ZIP, xử lý byte.

Đừng dùng `String.length()` để tính số byte file UTF-8; một ký tự tiếng Việt hoặc emoji có thể cần nhiều byte. `Files.size(path)` đo **số byte** của file, còn `String.length()` đo **UTF-16 code unit** của chuỗi.

## 7. Ví dụ 3 — tương thích `java.io.File` khi thư viện cũ yêu cầu

Tạo tệp `FileInteropDemo.java`:

```java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class FileInteropDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("interop-");
        try {
            Path child = root.resolve("report.txt");
            File legacy = child.toFile();
            System.out.println("same path=" + legacy.toPath().equals(child));
            System.out.println("before create=" + Files.exists(child));
            Files.writeString(child, "report", StandardCharsets.UTF_8);
            System.out.println("after create=" + legacy.isFile());
            System.out.println("legacy name=" + legacy.getName());
            System.out.println("read=" + Files.readString(child, StandardCharsets.UTF_8));
            try {
                Files.readString(root.resolve("missing.txt"));
            } catch (NoSuchFileException e) {
                System.out.println("missing exception=" + e.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(root.resolve("report.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileInteropDemo.java
java FileInteropDemo
```

```text
same path=true
before create=false
after create=true
legacy name=report.txt
read=report
missing exception=NoSuchFileException
```

Trong ví dụ, `root` thuộc filesystem mặc định nên `child.toFile()` hợp lệ. `File.toPath()` chuyển lại sang biểu diễn `Path` và kết quả so sánh cùng đường dẫn.

**`Path.toFile()` không phổ quát**: nếu `Path` thuộc file system provider khác filesystem mặc định, phương thức có thể ném `UnsupportedOperationException`. Do đó **đừng chuyển sang `File` trừ khi bạn thực sự cần API cũ**.

**`Files.exists(path)` không phải kiểm tra chắc chắn:** phương thức có thể trả `false` nếu không thể xác định trạng thái tồn tại (ví dụ thiếu quyền). Khi thực hiện thao tác có yêu cầu file tồn tại, hãy gọi trực tiếp `Files.readString`, `Files.newInputStream` hoặc API cụ thể và **xử lý IOException**, thay vì mặc định tin vào một kết quả `exists` trước đó.

## 8. Các lựa chọn thao tác đường dẫn quan trọng

### `Path.of` và đường dẫn tương đối

`Path.of("data", "output.txt")` tạo đường dẫn **tương đối** với bối cảnh làm việc của filesystem; trên filesystem mặc định thường là thư mục làm việc của tiến trình. Trên IDE, terminal, test runner và môi trường triển khai, working directory có thể khác nhau.

Khi file phải nằm trong một thư mục cấu hình, hãy xác định root và dùng `resolve` trên root đó thay vì dựa vào một đường dẫn tương đối chưa biết ý nghĩa.

`Path.of("data/output.txt").toAbsolutePath()` không tự xác minh file tồn tại, còn `toRealPath()` thường yêu cầu đối tượng file có tồn tại và truy cập được.

### `normalize`, `toAbsolutePath` và `toRealPath`

| Phương thức | Tính chất | Có truy cập filesystem? |
|---|---|---|
| `normalize()` | Tinh gọn `.`, `..` theo cú pháp | Không |
| `toAbsolutePath()` | Chuyển sang đường dẫn tuyệt đối theo provider | Thường không kiểm tra tồn tại |
| `toRealPath()` | Lấy đường dẫn thực, xử lý link theo options | Có; thường cần mục tồn tại |
| `Files.isSameFile(a, b)` | Hỏi hai đường dẫn hiện tại có trỏ cùng file không | Có thể truy cập filesystem |

**Đường dẫn chuẩn hóa không đồng nghĩa đường dẫn an toàn.** Ví dụ ứng dụng có một thư mục upload được phép mà người dùng kiểm soát một phần của đường dẫn; đường dẫn chứa `..` có thể thoát khỏi root. Ngay cả sau `normalize`, một symbolic link bên trong root có thể trỏ ra ngoài.

Không dùng kiểm tra chuỗi thuần như `candidate.toString().startsWith(root.toString())` để quyết định một đường dẫn có thuộc root hay không: chuỗi `/data/uploads2` cũng bắt đầu bằng `/data/uploads`. `Path.startsWith(other)` so sánh theo **thành phần đường dẫn**, tốt hơn kiểm tra tiền tố chuỗi, nhưng **vẫn không loại được nguy cơ symlink hoặc thay đổi đồng thời**.

## 9. Symbolic link: một lý do lớn để dùng `Path` + `Files`

**Symbolic link** (liên kết biểu tượng) là một mục filesystem tham chiếu tới đường dẫn khác. Khi đường dẫn trỏ tới symlink, thao tác theo link hay thao tác **chính symlink** có thể cho kết quả rất khác nhau.

Các API cần biết:

- `Files.isSymbolicLink(path)`: kiểm tra đối tượng đang được coi là symbolic link.
- `Files.readSymbolicLink(path)`: đọc nội dung đường dẫn mà symlink lưu.
- `Files.createSymbolicLink(link, target)`: tạo symlink, có thể cần quyền/điều kiện môi trường.
- `LinkOption.NOFOLLOW_LINKS`: truyền ở các thao tác hỗ trợ để không theo symbolic link.
- `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)`: lấy attributes của link thay vì đối tượng đích khi cần.
- `Path.toRealPath(...)`: lấy đường dẫn thực dựa trên filesystem; mặc định thường resolve link nếu không dùng `NOFOLLOW_LINKS`.

**Khi nào cần lưu ý nhất?** Quét upload, xóa file, đồng bộ, sao lưu, đọc đường dẫn do user cung cấp, giới hạn thao tác trong một root được phép.

Ví dụ logic bảo vệ chỉ bằng:

```java
Path candidate = root.resolve(userInput).normalize();
if (!candidate.startsWith(root)) {
    throw new SecurityException("Outside root");
}
```

là **minh họa chưa đủ an toàn để triển khai trực tiếp**. Nó chỉ chặn một lớp đường dẫn thoát root theo cú pháp nếu `root` đã cùng loại/định dạng và chuẩn hóa thích hợp. Nó **không** chặn symlink dẫn ra ngoài root hoặc tấn công thay đổi liên kết giữa lần kiểm tra và thao tác (*TOCTOU*).

Trong quy trình nhạy cảm, phải xác định threat model, dùng các kiểm tra đường dẫn thực thích hợp khi mục tồn tại, tránh follow link không cần thiết và khi khả dụng dùng thao tác tương đối với directory handle an toàn (ví dụ `SecureDirectoryStream` nếu provider hỗ trợ). Việc bảo vệ khỏi race đòi hỏi thiết kế filesystem rõ ràng, không có một lời gọi `normalize()` nào tự giải quyết hết.

## 10. Tạo, xóa và duyệt thư mục đúng cách

### Tạo thư mục

`Files.createDirectory(path)` tạo **một** thư mục, đòi hỏi cha phù hợp phải tồn tại. `Files.createDirectories(path)` có thể tạo cả chuỗi cha còn thiếu.

Lưu ý `createDirectories` không có nghĩa thao tác nhiều cấp hoàn toàn nguyên tử: nếu lỗi giữa chừng, một số thư mục cha có thể đã được tạo.

### Xóa

`Files.delete(path)` xóa một file, symlink hoặc thư mục rỗng; với thư mục còn con, nó **không tự động xóa đệ quy**. `Files.deleteIfExists(path)` bỏ qua tình huống đường dẫn không tồn tại, nhưng vẫn có thể ném `IOException` đối với lỗi khác.

Xóa cả cây thư mục phải có logic rõ quyền sở hữu và thứ tự xóa. Khi dữ liệu thuộc người dùng hoặc chứa symlink, càng cần kiểm soát. **Không sao chép ví dụ cleanup một thư mục tạm vào một chức năng xóa đường dẫn bất kỳ lấy từ form.**

### Duyệt một cấp so với đệ quy

- `Files.list(dir)`: các mục trực tiếp trong thư mục, không tự duyệt sâu.
- `Files.newDirectoryStream(dir)`: iterator directory entry, hữu ích khi cần duyệt thư mục có kiểm soát.
- `Files.walk(dir)`: stream đi qua cây thư mục, theo depth-first trong một số chi tiết traversal, có tùy chọn độ sâu.
- `Files.walkFileTree(root, visitor)`: callback visitor, kiểm soát vào/ra thư mục và xử lý lỗi I/O theo từng mục; hợp lý cho copy/delete tree hoặc công cụ quét có nhiều nhánh xử lý.

Không tự sử dụng `Files.walk(root)` rồi ép duyệt toàn bộ cây nhiều triệu file chỉ để kiểm tra một tên cụ thể khi có thuật toán gọn hơn. Hãy đóng stream và cân nhắc độ sâu, quyền truy cập, symbolic link, chu trình và chiến lược xử lý exception.

### Khi cần quan sát thay đổi filesystem

`WatchService` có thể theo dõi sự kiện tạo, xóa, sửa trong thư mục trên provider hỗ trợ. Nó không phải giải pháp đồng bộ tuyệt đối: event có thể bị gộp, bỏ sót trong một số điều kiện hoặc nhận `OVERFLOW`; cần có cơ chế quét lại nếu ứng dụng đòi hỏi trạng thái chính xác. Đừng hiểu WatchService là “giám sát tất cả thư mục con” mặc định; thường phải đăng ký những thư mục cụ thể theo thiết kế.

## 11. Tránh lỗi TOCTOU: “kiểm tra trước rồi làm” không bảo đảm

**TOCTOU** (*time-of-check to time-of-use*) là lỗi khi trạng thái hệ thống thay đổi giữa bước kiểm tra và thao tác. Ví dụ:

```java
if (!Files.exists(target)) {
    Files.writeString(target, text);
}
```

Đây là **mã minh họa về cách làm có race**, không phải giải pháp an toàn. Một thread/process khác có thể tạo `target` ngay sau khi `exists` trả `false` và trước lúc `writeString`; khi đó phương thức ghi mặc định có thể **ghi đè** file mới tạo.

Nếu ý định là **chỉ tạo mới khi chưa tồn tại**, dùng `CREATE_NEW` để filesystem thực hiện điều kiện tạo file theo semantics của operation:

```java
Files.writeString(target, text, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
```

Đây là **đoạn minh họa** cần có `target`, `text` và xử lý `IOException`. Với dữ liệu không tin cậy và symlink, vẫn phải xem xét quyền trên thư mục cha, provider và toàn bộ mô hình bảo vệ.

Tương tự, `Files.exists`/`isRegularFile`/`isReadable` chỉ là các **truy vấn trạng thái tại một thời điểm**; sau đó file có thể bị xóa, đổi quyền hoặc thay thế. Với tác vụ cần kết quả chính xác, thực hiện operation cần thiết và xử lý ngoại lệ.

## 12. Ghi file an toàn và tính nguyên tử

Nếu chương trình ghi trực tiếp vào file cấu hình hay tài liệu quan trọng, sự cố giữa chừng có thể để lại file dở dang. `Files.writeString` không mặc nhiên tạo một transaction ghi tất-cả-hoặc-không-gì.

Một chiến lược phổ biến:

1. Tạo một file tạm **trong cùng thư mục hoặc filesystem đích** nếu phù hợp.
2. Ghi nội dung mới vào file tạm, đóng/flush nguồn ghi.
3. Validate nội dung hoặc kiểm tra checksum theo yêu cầu.
4. Di chuyển file tạm tới đích, có thể yêu cầu `ATOMIC_MOVE` khi filesystem hỗ trợ.
5. Nếu `ATOMIC_MOVE` không được hỗ trợ, quyết định rõ **từ chối thao tác** hay **fallback không nguyên tử**, dựa trên yêu cầu.
6. Dọn file tạm nếu thất bại; cân nhắc quyền, attributes và khôi phục sau sự cố.

Mẫu minh họa, **không phải một chương trình độc lập**:

```java
Path temporary = Files.createTempFile(target.getParent(), "write-", ".tmp");
try {
    Files.writeString(temporary, text, StandardCharsets.UTF_8);
    Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
} finally {
    Files.deleteIfExists(temporary);
}
```

Đoạn trên cần import `Path`, `Files`, `StandardCharsets` và `StandardCopyOption`, cần `target.getParent()` là thư mục tồn tại và các biến đã xác định. Nó **không** bao hàm chính sách thay thế file đích và không có fallback. `ATOMIC_MOVE` có thể ném `AtomicMoveNotSupportedException`. **Atomic rename không đồng nghĩa dữ liệu đã bền vững trên ổ đĩa sau mất điện**; durability thực sự có thể cần đồng bộ file/thư mục và cơ chế phù hợp với filesystem.

Đừng tự coi `REPLACE_EXISTING` + `ATOMIC_MOVE` luôn có cùng ngữ nghĩa thay thế ở mọi provider. Với mục tiêu ghi file quan trọng, phải kiểm tra hỗ trợ và contract thực tế.

## 13. `File` vẫn phù hợp ở đâu?

### 13.1 API thư viện cũ yêu cầu `File`

Nhiều thư viện, framework, công cụ test hoặc legacy SDK có constructor như `SomeLibrary(File source)`. Nếu bạn đã có `Path` trên filesystem mặc định, có thể dùng `path.toFile()` ở ranh giới tích hợp.

Nếu nhận `File` từ API cũ, gọi `file.toPath()` và tiếp tục thao tác bằng `Files`. Đây là quá trình **chuyển đổi đơn giản khi tương thích**; không cần thiết viết lại tất cả dữ liệu qua stream trung gian.

### 13.2 Đang bảo trì hệ thống dùng `File` nhất quán

Một module ổn định có API public sử dụng `File` và hàng trăm call site không bắt buộc chuyển toàn bộ cùng lúc. Khi bổ sung chức năng mới đòi hỏi copy/move, metadata, symlink hay ngoại lệ cụ thể, có thể chuyển `File` sang `Path` cục bộ rồi dùng `Files`, thay vì thay đổi public API và gây migration lớn.

### 13.3 Khi nhu cầu đơn giản và contract đã đủ

`File` không “sai” nếu logic thực sự chỉ cần kiểm tra một đường dẫn trong một test hay tích hợp legacy. Quan trọng là **hiểu semantics** của `exists`, `delete`, `renameTo`, và các trường hợp thất bại, chứ không phải áp dụng một lệnh cấm tuyệt đối.

### 13.4 Java phiên bản rất cũ

`Path`/`Files` xuất hiện từ Java 7, còn `Path.of` và `Files.readString/writeString` từ Java 11. Dự án bị ràng buộc với Java 6 hoặc cũ hơn không có NIO.2 chuẩn. Nhưng với **Java 17+**, thông thường không có lý do kỹ thuật để tiếp tục dùng toàn bộ thao tác file mới bằng `File` chỉ vì tương thích phiên bản Java.

## 14. Các lưu ý về provider và tính di động

**`Path` không phải chỉ là chuỗi.** Một `Path` thuộc một `FileSystem` có provider và quy tắc riêng. Hai đường dẫn từ provider hoặc filesystem khác nhau có thể không tương thích với một số thao tác kết hợp, so sánh hoặc di chuyển.

Một số điểm cần nhớ:

- `Path.of(...)` tạo `Path` ở **default filesystem** của runtime.
- `FileSystem.getPath(...)` có thể tạo `Path` của provider cụ thể.
- `File.toPath()` làm việc với `File` và filesystem mặc định.
- `Path.toFile()` có thể ném `UnsupportedOperationException` với `Path` từ provider không phải default.
- Một số phương thức `Files` có thể ném `UnsupportedOperationException`, `IOException` hoặc ngoại lệ tương ứng nếu feature không được hỗ trợ.
- Tính năng POSIX file permissions, owner/group, ACL hoặc extended attributes không đồng đều giữa Windows/Linux/filesystem ảo.
- Symlink creation có thể cần quyền đặc biệt. Đừng giả định test tạo symlink hoạt động trên mọi máy.
- `Files.copy` giữa provider khác nhau phụ thuộc contract, có thể thiếu metadata hoặc thất bại; kiểm tra mục tiêu của hệ thống thay vì suy luận chung.

API `Path` và `Files` **giúp làm rõ ranh giới filesystem**, nhưng không tự bảo đảm tất cả thao tác chạy đồng nhất trên mọi provider. Khi làm công cụ đa hệ điều hành, viết test với filesystem và permission thực tế quan trọng không kém việc chọn API.

## 15. Những lỗi phổ biến khi chuyển từ `File` sang `Path`/`Files`

1. **Nghĩ tạo `Path` là tạo file:** `Path.of("x.txt")` chỉ tạo một đối tượng đường dẫn; phải gọi `Files.createFile`, `writeString`, v.v.
2. **Coi `normalize` là đường dẫn thực:** nó chỉ biến đổi cú pháp, không resolve symlink hoặc bảo đảm mục tồn tại.
3. **Dựa vào working directory mà không biết:** đường dẫn tương đối có thể trỏ khác nơi giữa IDE và production.
4. **Đọc toàn bộ file lớn bằng `Files.readString`:** dễ tốn bộ nhớ; dùng buffered reader/stream khi xử lý dữ liệu lớn.
5. **Quên đóng `Files.lines`/`list`/`walk`:** stream có tài nguyên hệ thống; dùng `try-with-resources`.
6. **Tin rằng `Files.copy(dir, target)` sao chép đệ quy:** thao tác copy trên mục thư mục **không** tự copy toàn bộ con; cần chiến lược tree traversal.
7. **Tưởng `Files.delete` sẽ xóa thư mục không rỗng:** phương thức không tự dọn toàn cây.
8. **Dùng `Files.exists` rồi ghi mà không chọn option:** tạo race và có nguy cơ ghi đè dữ liệu; dùng `CREATE_NEW` khi cần điều kiện chỉ-tạo-mới.
9. **Tưởng `Files.exists(path) == false` chứng minh chắc chắn file không tồn tại:** có thể do không xác định được trạng thái; gọi thao tác và xử lý ngoại lệ.
10. **Bật `REPLACE_EXISTING` vô thức:** dễ làm mất dữ liệu đã có.
11. **Giả định `ATOMIC_MOVE` luôn được hỗ trợ:** phải xử lý `AtomicMoveNotSupportedException` và quyết định fallback hợp lý.
12. **Tin rằng atomic move bảo đảm durability:** rename atomic và flush/fsync là hai yêu cầu khác nhau.
13. **Chuyển mọi `Path` thành `File`:** provider không mặc định có thể không hỗ trợ `toFile()`.
14. **Quét/xóa thư mục theo đường dẫn do user cung cấp mà bỏ qua symlink:** có thể dẫn ra ngoài vùng được phép; cần threat model và kiểm soát race.
15. **Đọc text mà không quản lý charset:** dùng `StandardCharsets.UTF_8` hoặc charset do định dạng quy định; đừng coi filename extension quyết định encoding.
16. **Không kiểm soát lỗi filesystem:** permission, path không tồn tại, file bị thay đổi hoặc khóa có thể khiến thao tác thất bại; đừng gom mọi lỗi thành “không có file”.
17. **Quên khác biệt file metadata và file content:** `Files.size` trả byte, `String.length()` trả UTF-16 code units.
18. **Chỉ test trên một hệ điều hành:** phân cách đường dẫn, ký tự hợp lệ trong tên file, case sensitivity, symbolic link và quyền có thể khác.
19. **Kết luận `Files` là non-blocking I/O:** đây là API filesystem tiện ích; đọc/ghi đồng bộ thường vẫn có thể chặn thread.
20. **Dùng `isSameFile` thay cho so sánh cú pháp khi chỉ muốn so tên:** `isSameFile` có thể đụng filesystem và ném `IOException`; `Path.equals` có nghĩa khác.

## 16. Checklist lựa chọn nhanh

| Nếu ứng dụng cần... | Ưu tiên... | Vì sao |
|---|---|---|
| Code Java 17 mới xử lý đường dẫn/file | `Path` + `Files` | API rõ nghĩa, options, ngoại lệ |
| Chuyển đường dẫn cha/con hoặc tương đối | `resolve`, `relativize`, `normalize` | Không phải nối chuỗi thủ công |
| Đọc/ghi file text nhỏ | `Files.readString/writeString` | Ngắn gọn, charset rõ |
| Đọc file text lớn theo dòng | `Files.newBufferedReader` hoặc `Files.lines` | Tránh giữ toàn bộ file trong RAM |
| Sao chép/di chuyển/xóa | `Files.copy/move/delete` | Có lựa chọn và mô tả lỗi |
| Duyệt, lọc hoặc thao tác cây thư mục | `Files.list/walk/walkFileTree` | Phù hợp cho cấu trúc cây, xử lý lỗi |
| Xem attributes hoặc xử lý symbolic link | `Files.readAttributes`, `LinkOption` | Thông tin rõ hơn |
| Phát hiện thay đổi thư mục | `WatchService` | Hệ thống sự kiện có giới hạn |
| Tích hợp thư viện chỉ nhận `java.io.File` | `path.toFile()` nếu hỗ trợ | Giữ tương thích |
| Nhận `File` từ thư viện cũ rồi thao tác mới | `file.toPath()` + `Files` | Dễ tăng tính rõ ràng mà không migration toàn bộ |
| Tạo file chỉ khi chưa tồn tại | `Files.writeString(..., CREATE_NEW, WRITE)` | Tránh check-then-write race |
| Ghi file quan trọng không công bố bản dở dang | File tạm + validate + move có kiểm tra | Rõ chiến lược nguyên tử và lỗi |

## 17. Tự kiểm tra kiến thức

**Câu 1.** Dùng `Path.of("notes.txt")` có tạo file trên đĩa không?  
**Đáp án:** không. `Path` chỉ là đại diện đường dẫn. Phải gọi một API như `Files.createFile` hoặc `Files.writeString` để tác động lên filesystem.

**Câu 2.** Một lệnh `file.delete()` trả `false`; tại sao `Files.delete(path)` thường có ích hơn?  
**Đáp án:** `Files.delete` có thể ném `IOException`/subtype cụ thể và giúp biết lỗi do file vắng mặt, thư mục chưa rỗng hay lý do khác (tùy provider).

**Câu 3.** `Files.copy(sourceDirectory, targetDirectory)` có copy toàn bộ cây con không?  
**Đáp án:** không. Cần thiết kế sao chép đệ quy riêng khi muốn copy toàn cây.

**Câu 4.** `Files.readString(path, UTF_8)` thích hợp cho file 100 GB không?  
**Đáp án:** thông thường không, vì đưa dữ liệu vào bộ nhớ. Nên dùng buffered reader, stream hoặc xử lý theo khối.

**Câu 5.** `Files.exists(path) == false` rồi gọi `Files.writeString(path, data)` có bảo đảm không ghi đè file được tạo đồng thời không?  
**Đáp án:** không. Có TOCTOU; dùng `CREATE_NEW` nếu chỉ được tạo khi chưa tồn tại.

**Câu 6.** Vì sao `normalize()` không đủ bảo đảm một đường dẫn con nằm trong root upload?  
**Đáp án:** nó chỉ xử lý `.` và `..` theo cú pháp; symbolic link và thay đổi đồng thời của filesystem có thể đưa thao tác tới vị trí khác.

**Câu 7.** `Path.toFile()` có chắc chạy với ZIP filesystem không?  
**Đáp án:** không. `Path` từ provider không mặc định có thể không hỗ trợ chuyển sang `File`.

**Câu 8.** `Files.move(source, target, ATOMIC_MOVE)` báo `AtomicMoveNotSupportedException` thì nên làm gì?  
**Đáp án:** tùy yêu cầu: thất bại có kiểm soát nếu atomicity bắt buộc, hoặc quyết định fallback không nguyên tử và thông báo/thiết kế xử lý trạng thái trung gian.

**Câu 9.** Lúc nào vẫn hợp lý dùng `java.io.File`?  
**Đáp án:** khi API legacy yêu cầu `File`, dự án chưa cần migration lớn hoặc nhu cầu nhỏ có contract rõ; có thể chuyển sang `Path` tại ranh giới cần chức năng NIO.2.

**Câu 10.** `Files.walk(dir).count()` xong là stream tự đóng chưa?  
**Đáp án:** không nên giả định. Stream của `Files.walk` có tài nguyên, phải đóng trong `try-with-resources`.

## Kết luận

Với **Java 17+**, hãy coi **`Path` + `Files` là lựa chọn mặc định** cho mã mới xử lý đường dẫn, file và thư mục. `Path` mô tả vị trí và thao tác đường dẫn, còn `Files` xử lý filesystem với API rõ nghĩa, ngoại lệ phong phú, lựa chọn tạo/copy/move, metadata và duyệt cây. `java.io.File` vẫn hữu ích ở **ranh giới tương thích legacy**; có thể chuyển bằng `file.toPath()` hoặc `path.toFile()` khi provider hỗ trợ.

Điều quan trọng hơn tên API là hiểu hợp đồng: **tạo đường dẫn khác tạo file; truy vấn trạng thái khác thao tác thật; `normalize` khác đường dẫn thực; copy thư mục khác copy đệ quy; atomic move khác durability; stream có tài nguyên phải đóng**. Khi dùng đúng các nguyên tắc đó, `Path` và `Files` giúp mã Java dễ đọc, dễ kiểm soát lỗi và dễ mở rộng hơn.

### Tài liệu Java SE 17

- [`Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html) và [`Paths`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html)
- [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`java.io.File`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html)
- [`StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [`StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [`LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html), [`FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [`BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
- [`WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
