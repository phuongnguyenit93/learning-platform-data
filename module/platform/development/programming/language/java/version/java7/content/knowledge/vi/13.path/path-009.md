# Tương tác với File tại ranh giới thư viện: kết nối Path và java.io.File an toàn

**Chủ đề:** Java 7 — Path  
**Bài học:** Tương tác với File tại ranh giới thư viện  
**Môi trường thực hành:** Java 17+; các nguyên tắc liên quan `java.nio.file.Path`, `java.io.File`, `Files`, `URI` và filesystem providers vẫn áp dụng trong Java hiện đại.

## 1. Vấn đề: mã mới dùng Path, thư viện vẫn nhận File

Trong một ứng dụng Java hiện đại, phần lớn xử lý tệp nên được thiết kế quanh `java.nio.file.Path` và `java.nio.file.Files`: chúng tách việc mô tả vị trí khỏi thao tác I/O, làm việc với provider, và cung cấp các phương thức đọc/ghi, copy, move và xử lý thuộc tính có ngoại lệ rõ ràng.

Nhưng nhiều thư viện, kể cả API hiện hành trong JDK, vẫn có chữ ký nhận `java.io.File`:

- `javax.imageio.ImageIO.read(File)` và `ImageIO.write(..., File)`.
- `java.util.zip.ZipFile(File)`.
- `new FileInputStream(File)` hoặc `new FileOutputStream(File)`.
- `ProcessBuilder.directory(File)`.
- Các SDK, plugin, thư viện xử lý tài liệu, ảnh và công cụ build có API nhận `File` theo hợp đồng của chúng.

**`File` không phải một kiểu đã bị loại bỏ hay không còn dùng được.** Việc “ưu tiên Path” trong code mới không đồng nghĩa với việc phải viết lại mọi API của thư viện bên ngoài.

Câu hỏi quan trọng là: **đổi biểu diễn tại ranh giới như thế nào, khi nào phép đổi hợp lệ, và ai chịu trách nhiệm với vòng đời/tính an toàn của tài nguyên?**

Một thiết kế dễ bảo trì thường có cấu trúc:

```text
Đầu vào/Domain/Application                Adapter                 Thư viện
Path, Files, metadata, validation --> path.toFile() --> API nhận File
                                     <-- file.toPath() <-- API trả File

Lưu ý: chỉ đổi được sang File với Path thuộc default filesystem.
```

Giữ `Path` ở lõi ứng dụng và chuyển sang `File` **tại điểm gọi thư viện**. Không phải cứ thấy `File` trong một phương thức là phải bắt cả ứng dụng chuyển sang `File`.

## 2. Ba kiểu cần phân biệt: File, Path và URI

| Kiểu | Vai trò | Khả năng chính | Giới hạn |
| --- | --- | --- | --- |
| `java.io.File` | Biểu diễn **abstract pathname** của file/thư mục trong default filesystem | Phù hợp với API thư viện nhận `File`; có `toPath()` | Không biểu diễn trực tiếp `Path` của ZIP/provider khác; nhiều API cũ chỉ trả boolean |
| `java.nio.file.Path` | Biểu diễn đường dẫn thuộc một `FileSystem` cụ thể | `resolve`, `normalize`, `relativize`, `toUri`; dùng với `Files` | Không phải mọi `Path` có thể chuyển thành `File` |
| `java.net.URI` | Biểu diễn tên tài nguyên theo **scheme và cú pháp URI** | `file:`, `jar:`, `https:`, percent-encoding | Không phải mọi URI là đường dẫn tệp; `https:` không phải file local |

**Ba đối tượng này chủ yếu mô tả vị trí, không phải một luồng dữ liệu đang mở.** Việc tạo `new File("data.txt")` hoặc `Path.of("data.txt")` không tự tạo file, không mở file descriptor, không bảo đảm tệp tồn tại.

Một chương trình có thể giữ cả `Path` và `File` trỏ đến **cùng vị trí** mà vẫn chưa có tệp thật. Việc truy cập tệp xảy ra ở `Files.readString`, `FileInputStream`, `ImageIO.read`, `ZipFile` hoặc API I/O thực tế.

### 2.1. Cặp chuyển đổi quan trọng

```java
Path path = Path.of("documents", "report.txt");

File file = path.toFile(); // Chỉ khi path thuộc default filesystem.
Path again = file.toPath();
```

Đây là đoạn mã minh họa trong method với import `java.io.File` và `java.nio.file.Path`.

- `Path.toFile()` tạo đối tượng `File` tương ứng với path **khi Path thuộc default filesystem**. Nếu Path thuộc filesystem khác, có thể ném `UnsupportedOperationException`.
- `File.toPath()` tạo một `Path` thuộc **default filesystem** tương ứng với pathname mà `File` chứa.
- Hai phép chuyển đổi **không đọc nội dung**, không tự thay encoding và không cấp quyền truy cập file.
- Chúng cũng không tự chuyển một relative path thành canonical path hay loại bỏ symbolic link.

**Đừng biến phép đổi kiểu thành phép kiểm tra an toàn:** `path.toFile()` có thể thành công dù tệp không tồn tại, dù tên tệp thuộc vùng cấm của nghiệp vụ, hoặc dù khi mở sau này bạn sẽ gặp `AccessDeniedException`.

## 3. Ví dụ đầu tiên: File và Path trỏ cùng một vị trí

Tạo file `FilePathRoundTripDemo.java`:

```java
import java.io.File;
import java.net.URI;
import java.nio.file.Path;

public class FilePathRoundTripDemo {
    public static void main(String[] args) {
        Path relative = Path.of(
                "documents", "báo cáo 2026.txt");
        File legacy = relative.toFile();
        Path fromLegacy = legacy.toPath();

        Path absolute =
                relative.toAbsolutePath().normalize();
        URI fileUri = absolute.toUri();
        Path fromUri = Path.of(fileUri);
        File fileFromUri = new File(fileUri);

        System.out.println(
                "relative=" + !relative.isAbsolute());
        System.out.println(
                "path-file-path="
                + relative.equals(fromLegacy));
        System.out.println(
                "uri-scheme=" + fileUri.getScheme());
        System.out.println(
                "uri-roundtrip=" + absolute.equals(fromUri));
        System.out.println(
                "file-uri-roundtrip="
                + fileFromUri.toPath().equals(absolute));
        System.out.println(
                "escaped-space="
                + fileUri.toASCIIString().contains("%20"));
        System.out.println(
                "escaped-unicode="
                + fileUri.toASCIIString().contains("%C3%A1"));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all FilePathRoundTripDemo.java
java FilePathRoundTripDemo
```

**stdout chính xác:**

```text
relative=true
path-file-path=true
uri-scheme=file
uri-roundtrip=true
file-uri-roundtrip=true
escaped-space=true
escaped-unicode=true
```

Giải thích:

1. `relative` không có root, nên là đường dẫn tương đối.
2. `relative.toFile().toPath()` vẫn mô tả cùng tên đường dẫn trong default filesystem.
3. `toAbsolutePath().normalize()` tạo đường dẫn tuyệt đối theo working directory, nhưng **không xác minh** tệp đã tồn tại.
4. `absolute.toUri()` tạo `file:` URI. `Path.of(fileUri)` và `new File(fileUri)` là các cách chuyển một **file URI phù hợp** trở lại đường dẫn của default filesystem.
5. `URI.toASCIIString()` dùng percent-encoding cho dấu cách và ký tự không thuộc ASCII; ví dụ kiểm tra `%20` và `%C3%A1` mà không phụ thuộc đường dẫn làm việc cụ thể.
6. Chương trình **không tạo file trên ổ đĩa**. Mọi kết quả ở đây thuộc về phép chuyển đổi/biểu diễn path.

**Phân biệt:** `new File(URI)` có các điều kiện đối với URI `file` (ví dụ không chấp nhận một URI `https` thay thế). `new File(String)` lại nhận **tên đường dẫn**, không phải URI string. Đừng dùng `new File(uri.toString())` như phép chuyển đổi `URI → File`.

## 4. Chọn nơi đặt adapter khi thư viện bắt buộc nhận File

Giả sử application của bạn chỉ muốn trao đổi `Path`:

```java
public void exportReport(Path output, String content)
        throws IOException {
    thirdPartyExporter.write(output.toFile(), content);
}
```

Đây là **snippet**; `thirdPartyExporter` là đối tượng thư viện giả định. Vị trí gọi `toFile()` chính là **boundary adapter**. Nó rõ ràng hơn việc chuyển toàn bộ tham số của các service và domain classes sang `File` chỉ vì một thư viện ở tầng cuối nhận kiểu đó.

Nên tách:

- **Core/application:** dùng `Path` để xác định vị trí, cấu hình, resolve thư mục và quyết định file được phép sử dụng.
- **Adapter:** chuyển sang `File` khi provider phù hợp, áp dụng policy và gọi thư viện.
- **Thư viện:** chịu trách nhiệm xử lý nội dung theo hợp đồng của API `write(File,...)`.
- **Caller/owner:** quyết định thời điểm dọn tệp tạm và đóng các handle đang mở theo contract.

Không lạm dụng việc biến `File` trở lại `Path` rồi lại thành `File` qua nhiều tầng. Nếu có `File` do thư viện trả về, thông thường **chuyển sang `file.toPath()` một lần tại ranh giới trở lại** và tiếp tục dùng `Files`.

### 4.1. Ví dụ đầy đủ: adapter cho thư viện chỉ nhận File

Để minh họa không cần thư viện bên ngoài, chương trình tạo một **File-only library giả lập**, sử dụng chữ ký mà nhiều thư viện đang có.

Tạo `LegacyFileAdapterDemo.java`:

```java
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LegacyFileAdapterDemo {
    static final class FileOnlyLibrary {
        static void write(File target, String content)
                throws IOException {
            try (Writer writer = new OutputStreamWriter(
                    new FileOutputStream(target),
                    StandardCharsets.UTF_8)) {
                writer.write(content);
            }
        }
    }

    // Application vẫn expose Path, chỉ đổi ở boundary.
    static void export(Path destination, String content)
            throws IOException {
        Files.createDirectories(destination.getParent());
        FileOnlyLibrary.write(destination.toFile(), content);
    }

    public static void main(String[] args)
            throws IOException {
        Path temp = Files.createTempDirectory(
                "file-path-adapter-");
        Path destination = temp.resolve("out")
                .resolve("report.txt");

        try {
            export(destination, "Xin chào Java");
            System.out.println(
                    "file-created="
                    + Files.isRegularFile(destination));
            System.out.println(
                    "content-ok="
                    + Files.readString(
                        destination, StandardCharsets.UTF_8)
                            .equals("Xin chào Java"));
            System.out.println(
                    "path-preserved="
                    + destination.toFile().toPath()
                            .equals(destination));
        } finally {
            Files.deleteIfExists(destination);
            Files.deleteIfExists(destination.getParent());
            Files.deleteIfExists(temp);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LegacyFileAdapterDemo.java
java LegacyFileAdapterDemo
```

```text
file-created=true
content-ok=true
path-preserved=true
```

**Phân tích:** `export(Path, String)` giữ public API hiện đại, tạo thư mục cha bằng `Files` rồi **chỉ tại lời gọi thư viện** mới chuyển `destination.toFile()`. Thư viện tự mở writer và đóng nó trong `try-with-resources`. Caller vẫn có trách nhiệm dọn **đường dẫn tệp tạm** sau khi công việc hoàn tất.

Trong ứng dụng thực:

- Không tự đổi charset trong adapter nếu thư viện/định dạng đã quy định encoding riêng. Với văn bản mới do bạn thiết kế, UTF-8 là lựa chọn phù hợp.
- Nếu thư viện ghi async, lời gọi `write(File)` có thể **trả về trước khi việc ghi kết thúc**. Khi đó không được xóa file tạm sớm; cần theo lifecycle thực tế do thư viện công bố.
- Nếu thư viện có thể tạo thư mục/tệp tự nó, tránh logic trùng lặp không cần thiết. Ví dụ này kiểm soát thư mục để làm rõ bước I/O.
- Nên kiểm thử cả failure path: disk full, thiếu quyền, thư viện báo lỗi, và việc dọn tài nguyên/tệp được kích hoạt đúng lúc.

**Tên `LegacyFileAdapterDemo` chỉ mô tả dạng API nhận `File`**, không kết luận API `File` đã lỗi thời hoặc cần bị thay bằng một phương thức không tồn tại.

## 5. File không phải handle: ownership và vòng đời vẫn thuộc thư viện

Một biến `File` chỉ chứa đường dẫn. Nó **không phải** `InputStream`, `ZipFile` hay `FileSystem` đang mở. Nó không triển khai `AutoCloseable` và bạn không cần đặt chính đối tượng `File` vào `try-with-resources`.

Chỉ những đối tượng **đang giữ tài nguyên thực** mới có vòng đời đóng rõ:

| Loại object | Có giữ handle để close? | Lưu ý |
| --- | --- | --- |
| `File` | Không, chỉ là pathname | Không có `close()`; có thể trỏ tới tệp không tồn tại |
| `Path` | Không, chỉ là pathname trong provider | Không có `close()`; dùng `Files` để làm I/O |
| `FileInputStream` / `FileOutputStream` | Có | Đóng bằng TWR; có constructor nhận `File` |
| `BufferedReader` / `BufferedWriter` | Có | Đóng theo scope; wrapper thường đóng nguồn bên dưới |
| `ZipFile` | Có | Đóng sau khi đọc entry để giải phóng archive handle |
| `FileSystem` của ZIP provider | Có | `close()` khi không còn dùng `Path`/stream nội bộ |
| Một object SDK chỉ lưu `File` rồi xử lý về sau | Phụ thuộc contract thư viện | Không xóa nguồn trước khi SDK xử lý xong |

Điều này giúp tránh hai lỗi trái ngược:

- **Rò rỉ resource:** tưởng rằng chỉ cần `Path`/`File` ra khỏi scope thì stream tự được đóng.
- **Xóa quá sớm:** API thư viện giữ tham chiếu tới `File` để xử lý về sau, nhưng application xóa file ngay khi hàm trả về.

### 5.1. Ví dụ gọi FileInputStream tại một boundary

```java
try (InputStream input =
        new FileInputStream(path.toFile())) {
    byte[] firstBytes = input.readNBytes(16);
    // Xử lý firstBytes...
}
```

Đây là **snippet**, giả sử `path` thuộc default filesystem, có import `FileInputStream`/`InputStream` và xử lý `IOException`. `try-with-resources` chịu trách nhiệm đóng **InputStream**, không đóng `File`.

Nếu chỉ cần đọc nội dung theo `Path`, thường đơn giản hơn là dùng `Files.newInputStream(path)` hoặc `Files.readString(path, charset)` mà **không chuyển sang File**. Chỉ dùng adapter khi một API thực sự yêu cầu `File`.

## 6. Ranh giới File và Path không thay đổi I/O semantics

Sau khi đổi `File → Path`, vẫn có những câu hỏi phải quyết định:

- Tệp có thể không tồn tại không?
- Khi đọc, có cần decode theo charset cụ thể không?
- Việc ghi có được tạo file mới, ghi đè hoặc append không?
- Quyền truy cập, symbolic link, concurrent writers được xử lý thế nào?
- Có cần báo lỗi I/O cụ thể cho caller không?
- Đường dẫn có được phép nằm bên ngoài thư mục dự kiến không?

Đổi object biểu diễn không giải quyết những câu hỏi này. Ví dụ `Files.readString(path, UTF_8)` có thể ném `NoSuchFileException`, `AccessDeniedException` hoặc các `IOException` khác dù `path.toFile()` đã thành công.

### 6.1. So sánh API File và Files

| Tình huống | API trên File | API thường ưu tiên trên Path |
| --- | --- | --- |
| Kiểm tra tồn tại | `file.exists()` | `Files.exists(path)` (đều có giới hạn khi không xác định được trạng thái) |
| Kiểm tra file thường | `file.isFile()` | `Files.isRegularFile(path)` |
| Lấy kích thước | `file.length()` (có thể trả 0 khi không tồn tại hoặc có lỗi) | `Files.size(path)`, báo `IOException` |
| Xóa | `file.delete()` trả boolean | `Files.delete(path)` ném lỗi I/O hoặc `Files.deleteIfExists(path)` trả boolean và vẫn có thể ném I/O |
| Đổi tên/move | `file.renameTo(dest)` trả boolean với giới hạn theo hệ thống | `Files.move(source, target, options...)` có ngoại lệ rõ hơn |
| Liệt kê thư mục | `file.listFiles(...)` có thể trả `null` | `Files.list(path)` trả stream cần đóng, báo IOException ở các bước phù hợp |
| Đọc nội dung tệp UTF-8 | Cần stream/reader thích hợp | `Files.readString(path, UTF_8)` cho file phù hợp dung lượng |
| Đọc thuộc tính | Các API `File` cơ bản | `Files.readAttributes`, `Files.getLastModifiedTime` |

Không phải API `Files` nào cũng có semantics hay bảo đảm race-free tuyệt đối. Ví dụ `Files.exists` có thể trả false khi **không thể xác định** trạng thái; dùng nó như thao tác “nếu chưa tồn tại thì tạo” vẫn có nguy cơ TOCTOU. Với thao tác ghi, hãy sử dụng option như `CREATE_NEW` khi cần từ chối đè file có sẵn và dựa vào atomicity được provider bảo đảm.

### 6.2. Ví dụ runnable: boolean vs IOException

Tạo `FileApiBehaviorDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class FileApiBehaviorDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory(
                "file-api-behavior-");
        Path path = dir.resolve("not-yet-created.txt");

        try {
            System.out.println(
                    "file-exists=" + path.toFile().exists());
            System.out.println(
                    "nio-exists=" + Files.exists(path));

            try {
                Files.readString(
                        path, StandardCharsets.UTF_8);
                System.out.println("unexpected-read");
            } catch (NoSuchFileException ex) {
                System.out.println("read-error=NoSuchFile");
            }

            Files.writeString(
                    path, "ABC", StandardCharsets.UTF_8);
            System.out.println(
                    "file-is-file=" + path.toFile().isFile());
            System.out.println(
                    "nio-size=" + Files.size(path));

            Files.delete(path);
            System.out.println(
                    "after-delete=" + Files.notExists(path));
        } finally {
            Files.deleteIfExists(path);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FileApiBehaviorDemo.java
java FileApiBehaviorDemo
```

```text
file-exists=false
nio-exists=false
read-error=NoSuchFile
file-is-file=true
nio-size=3
after-delete=true
```

Kết quả đến từ một thư mục tạm mới tạo, nên đường dẫn `not-yet-created.txt` ban đầu chưa tồn tại. `File.exists()`/`Files.exists` trả false, nhưng chỉ khi `Files.readString` mới xuất hiện ngoại lệ cụ thể của thao tác đọc. Sau khi ghi `"ABC"` với UTF-8, tệp có 3 byte.

**Không suy rộng ví dụ thành quy tắc:** trong production, `exists()==false` không phải bằng chứng tuyệt đối rằng file không có trên mọi filesystem và cũng không phải khóa chống thay đổi đồng thời. Ưu tiên **thực hiện chính thao tác cần thiết và xử lý exception**.

## 7. File trả về từ thư viện: chuyển lại sang Path thế nào?

Một API có thể trả `File`:

```java
File outputFile = library.getOutputFile();
Path outputPath = outputFile.toPath();
```

Đây là **snippet**. Với `File` nhận được, `toPath()` luôn là cách hợp lý để bước vào NIO. Nhưng cần kiểm tra hợp đồng:

- `library.getOutputFile()` có thể trả `null` không? Nếu có, kiểm tra `null` trước khi gọi `toPath()`.
- Đường dẫn có thể là **relative** không? `file.toPath().isAbsolute()` có thể false.
- Thư viện đã thực sự ghi xong chưa, hay trả về một vị trí sẽ được sử dụng sau?
- Ai có trách nhiệm **xóa** tệp hoặc dọn thư mục tạm?
- File do thư viện cung cấp có được tin cậy để đọc/ghi hay cần kiểm tra root/permission?

Ví dụ normalize theo ứng dụng:

```java
Path resolved = outputFile.toPath()
        .toAbsolutePath()
        .normalize();
```

Nhưng `toAbsolutePath().normalize()` vẫn chỉ là phép biến đổi đường dẫn theo cú pháp. Nó **không** đảm bảo file tồn tại, không tự giải quyết symbolic link và không cấp phép truy cập.

**Đừng xóa tệp vừa được thư viện cung cấp** chỉ vì ứng dụng đã xong việc riêng của mình; cần biết ownership của thư mục/tệp đó. Nếu bên khác còn giữ handle hoặc đang ghi async, xóa sớm có thể làm hỏng workflow.

## 8. Provider boundary: Path không phải lúc nào cũng chuyển được sang File

Đây là giới hạn quan trọng nhất của `Path.toFile()`.

`java.io.File` được thiết kế quanh các pathname của **default filesystem**. Trong khi đó, `Path` là giao diện thuộc một `FileSystem` do provider cung cấp. Ví dụ ZIP/JAR provider cho phép nhìn vào một archive như một filesystem riêng:

```text
Default filesystem: /tmp/archive.zip
ZIP filesystem:     /docs/report.txt  (bên trong archive)
```

Cả hai có thể được biểu diễn bằng `Path`, nhưng `/docs/report.txt` ở ZIP filesystem **không phải một file path riêng trên ổ đĩa mặc định**. Vì vậy `zipEntry.toFile()` không thể tạo một `File` mặc định tương đương cho entry đó.

**Hợp đồng Java:** `Path.toFile()` chỉ được hỗ trợ nếu path thuộc **default provider**; nếu không, `UnsupportedOperationException` là hành vi cần dự kiến.

### 8.1. Cách làm đúng khi thư viện chỉ nhận File nhưng dữ liệu nằm trong ZIP

Nếu thư viện thật sự chỉ nhận `File` của default filesystem:

1. Duy trì `Path` trong ZIP filesystem để tìm entry.
2. Tạo một **tệp tạm** trong default filesystem bằng `Files.createTempFile` hoặc đường dẫn tạm phù hợp.
3. Copy **nội dung** ZIP entry sang tệp tạm bằng `Files.copy`.
4. Chuyển `tempPath.toFile()` tại adapter và gọi thư viện.
5. Giữ tệp tạm tồn tại **cho đến khi thư viện đã sử dụng xong**.
6. Dọn tệp tạm và đóng ZIP `FileSystem` khi kết thúc ownership.

Đây là **materialization**, không phải “cast đường dẫn”. Một provider có thể có API riêng hỗ trợ làm việc trực tiếp với `Path` hoặc `InputStream`; hãy ưu tiên overload đó nếu thư viện có cung cấp để tránh copy dư thừa.

### 8.2. Ví dụ runnable: ZIP Path.toFile() bị từ chối

Tạo `ZipFileBoundaryDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipFileBoundaryDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory(
                "zip-file-boundary-");
        Path archive = dir.resolve("archive.zip");
        Path extracted = dir.resolve("extracted.txt");

        try {
            URI zipUri = URI.create(
                    "jar:" + archive.toUri().toASCIIString());

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {
                Path inside = zip.getPath(
                        "/docs", "note.txt");
                Files.createDirectories(inside.getParent());
                Files.writeString(
                        inside, "inside zip",
                        StandardCharsets.UTF_8);

                System.out.println(
                        "nondefault="
                        + (inside.getFileSystem()
                            != FileSystems.getDefault()));

                try {
                    inside.toFile();
                    System.out.println("unexpected-to-file");
                } catch (UnsupportedOperationException ex) {
                    System.out.println("to-file-rejected");
                }

                System.out.println(
                        "uri-path-roundtrip="
                        + Path.of(inside.toUri()).equals(inside));

                Files.copy(inside, extracted);
                System.out.println(
                        "extracted-is-file="
                        + Files.isRegularFile(
                            extracted.toFile().toPath()));
                System.out.println(
                        "content-ok="
                        + Files.readString(
                            extracted, StandardCharsets.UTF_8)
                            .equals("inside zip"));
            }
        } finally {
            Files.deleteIfExists(extracted);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipFileBoundaryDemo.java
java ZipFileBoundaryDemo
```

```text
nondefault=true
to-file-rejected
uri-path-roundtrip=true
extracted-is-file=true
content-ok=true
```

**Giải thích:**

- `inside` thuộc ZIP provider, không phải default filesystem; `inside.toFile()` thất bại có chủ đích.
- `Path.of(inside.toUri())` hoạt động trong ví dụ **khi ZIP FileSystem đang mở** và provider tương ứng khả dụng.
- `Files.copy(inside, extracted)` chuyển **nội dung** của entry sang đường dẫn trên default filesystem. Bây giờ `extracted.toFile()` hợp lệ và có thể đưa cho API thư viện nhận `File`.
- `FileSystem` ZIP được đóng trong TWR. Các file tạm được dọn ở `finally` sau khi hoàn thành.
- Cơ chế ZIP filesystem yêu cầu ZIP provider phù hợp trong runtime. JDK đầy đủ phổ biến có provider này; runtime image được tùy biến có thể không có.

**An toàn với ZIP không đáng tin:** ví dụ dùng một tên entry cố định do code tạo. Khi trích xuất nhiều entry đến filesystem mặc định, phải chống *Zip Slip* (entry có `..`, đường dẫn tuyệt đối, hoặc mục tiêu thoát khỏi thư mục đích), giới hạn kích thước giải nén, số entry và symlink. `Files.copy` không tự biến mọi đường dẫn extraction do client điều khiển thành an toàn.

## 9. Một thư viện JDK thật sự còn nhận File: ImageIO

`javax.imageio.ImageIO` có overload nhận `File` để đọc/ghi ảnh. Đây là ví dụ tự nhiên của **API thư viện hiện hành** mà mã ứng dụng có thể tiếp tục dùng `Path` ở phần còn lại.

### 9.1. Ví dụ runnable: Path → File ở ImageIO boundary

Tạo `ImageIoFileBoundaryDemo.java`:

```java
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.imageio.ImageIO;

public class ImageIoFileBoundaryDemo {
    public static void main(String[] args)
            throws IOException {
        Path imagePath = Files.createTempFile(
                "imageio-file-boundary-", ".png");

        try {
            BufferedImage source = new BufferedImage(
                    2, 3, BufferedImage.TYPE_INT_RGB);

            boolean written = ImageIO.write(
                    source, "png", imagePath.toFile());
            if (!written) {
                throw new IOException(
                        "No PNG ImageIO writer available");
            }

            BufferedImage decoded = ImageIO.read(
                    imagePath.toFile());

            System.out.println("written=" + written);
            System.out.println(
                    "image-size="
                    + decoded.getWidth()
                    + "x" + decoded.getHeight());
            System.out.println(
                    "path-roundtrip="
                    + imagePath.toFile().toPath()
                            .equals(imagePath));
        } finally {
            Files.deleteIfExists(imagePath);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ImageIoFileBoundaryDemo.java
java ImageIoFileBoundaryDemo
```

```text
written=true
image-size=2x3
path-roundtrip=true
```

Ở đây application khởi tạo tệp tạm qua `Files` và giao **chỉ đối tượng File** cho `ImageIO.write/read`. Tệp thực vẫn có thể tiếp tục được quản lý bằng `Path`. Ví dụ chạy trên JDK đầy đủ có module `java.desktop` và ImageIO PNG reader/writer.

**Giới hạn cần nhớ:** `ImageIO.read` có thể trả `null` khi không có reader phù hợp cho nội dung; code ứng dụng phải xử lý trường hợp đó. Ví dụ tự tạo file PNG hợp lệ ngay trước khi đọc nên dự kiến nhận một ảnh.

Nếu API của thư viện có overload nhận `InputStream`/`OutputStream` hay `ImageInputStream`/`ImageOutputStream`, bạn có thể cân nhắc chúng để xử lý dữ liệu **không ở default filesystem** mà không cần materialize toàn bộ thành tệp. Nhưng phải hiểu đúng **ownership, đóng stream và điều kiện seek** theo JavaDoc thư viện.

## 10. Liệt kê thư mục: FileFilter và Files.list

Một thư viện có thể yêu cầu `File` hoặc trả mảng `File[]` từ `listFiles`. Mã mới có thể tiếp tục dùng `Path` và chuyển đổi tại adapter.

Có hai phong cách hay gặp:

```java
File[] files = dir.toFile().listFiles(
        (parent, name) -> name.endsWith(".txt"));
```

và:

```java
try (Stream<Path> entries = Files.list(dir)) {
    // filter, map, collect...
}
```

Đây là snippets; `dir` thuộc default provider, có các import phù hợp. Khác biệt quan trọng:

- `File.listFiles` có thể trả **`null`** nếu không phải thư mục hoặc gặp lỗi I/O; đừng dereference mảng không kiểm tra.
- `Files.list` có thể ném `IOException` khi mở; stream được trả về có tài nguyên filesystem, nên phải **đóng** bằng TWR.
- Thứ tự liệt kê **không được bảo đảm** trong mọi trường hợp; nếu kết quả cần ổn định, hãy sort rõ ràng.
- Việc gọi `listFiles` hoặc `Files.list` trong môi trường nhiều thread/process có thể thấy trạng thái thư mục thay đổi. Không xem danh sách như snapshot giao dịch.

### 10.1. Ví dụ runnable: hai API cho cùng kết quả

Tạo `DirectoryFileAdapterDemo.java`:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class DirectoryFileAdapterDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory(
                "directory-file-adapter-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");
        Path other = dir.resolve("ignore.csv");

        try {
            Files.writeString(a, "A", StandardCharsets.UTF_8);
            Files.writeString(b, "B", StandardCharsets.UTF_8);
            Files.writeString(
                    other, "skip", StandardCharsets.UTF_8);

            File[] fromFile = dir.toFile().listFiles(
                    (parent, name) -> name.endsWith(".txt"));
            if (fromFile == null) {
                throw new IOException("Cannot list directory");
            }

            List<String> legacyNames =
                    Arrays.stream(fromFile)
                    .map(File::getName)
                    .sorted()
                    .toList();

            List<String> nioNames;
            try (Stream<Path> entries = Files.list(dir)) {
                nioNames = entries
                        .filter(Files::isRegularFile)
                        .map(p -> p.getFileName().toString())
                        .filter(name -> name.endsWith(".txt"))
                        .sorted()
                        .toList();
            }

            System.out.println(
                    "file-names=" + legacyNames);
            System.out.println(
                    "path-names=" + nioNames);
            System.out.println(
                    "same=" + legacyNames.equals(nioNames));
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(other);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DirectoryFileAdapterDemo.java
java DirectoryFileAdapterDemo
```

```text
file-names=[a.txt, b.txt]
path-names=[a.txt, b.txt]
same=true
```

**Điểm cần hiểu:**

1. `FileFilter`/`FilenameFilter` là API Java vẫn hoạt động. Không cần “cấm File” chỉ vì code mới ưu tiên `Path`.
2. `Files.list` tạo một stream phải đóng. Trong ví dụ, `try-with-resources` bảo vệ stream ngay cả khi filter/collect xảy ra lỗi.
3. So sánh kết quả sau khi sort để không phụ thuộc thứ tự do filesystem trả.
4. `Files.isRegularFile` trong predicate còn có các lựa chọn liên quan symbolic link. Code production cần xác định có muốn theo link, bỏ link hay từ chối.
5. `Files.list` không tự xử lý mọi ngoại lệ phát sinh **khi đang lặp stream** dưới dạng checked `IOException`; một số lỗi I/O trong quá trình duyệt được đóng gói thành `UncheckedIOException`. Đừng chỉ chuẩn bị xử lý lỗi lúc mở stream.

## 11. File URI và đường dẫn File: không tự trộn chuỗi

`File.toURI()` trả URI mô tả vị trí file, còn `File.toPath()` trả `Path`. Khi đã có một `Path` và muốn có URI, dùng `path.toUri()`.

```java
File file = Path.of(
        "documents", "annual report.txt").toFile();

URI uri = file.toURI();
Path fromUri = Path.of(uri);
```

Đây là snippet. Không làm:

```java
// Không nên:
// File wrong = new File(uri.toString());
// Path wrongPath = Path.of("file:///tmp/annual%20report.txt");
```

Overload nhận `String` xử lý chuỗi như pathname theo default provider, **không parse URI theo scheme**. Một tên file thật có dấu `%` không đồng nghĩa với escape sequence `%20` trong URI.

### 11.1. Ví dụ runnable: file URI khác web URI

Tạo `FileUriBoundaryDemo.java`:

```java
import java.io.File;
import java.net.URI;
import java.nio.file.Path;

public class FileUriBoundaryDemo {
    public static void main(String[] args) {
        Path path = Path.of(
                "documents", "annual report.txt")
                .toAbsolutePath().normalize();
        URI fileUri = path.toUri();
        File file = new File(fileUri);

        System.out.println(
                "scheme=" + fileUri.getScheme());
        System.out.println(
                "escaped-space="
                + fileUri.toASCIIString().contains("%20"));
        System.out.println(
                "file-meaning-preserved="
                + file.toPath().equals(path));

        URI webUri = URI.create(
                "https://example.org/annual%20report.txt");
        try {
            new File(webUri);
            System.out.println("unexpected-web-file");
        } catch (IllegalArgumentException ex) {
            System.out.println("web-uri-rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FileUriBoundaryDemo.java
java FileUriBoundaryDemo
```

```text
scheme=file
escaped-space=true
file-meaning-preserved=true
web-uri-rejected
```

Một URI `https` cần HTTP client phù hợp nếu muốn tải dữ liệu; `new File(webUri)` và `Path.of(webUri)` không phải cách tải HTTP. Khi một thư viện trả string có dạng URL, đừng vội tạo `File` từ string đó mà chưa biết API định nghĩa string là **tên đường dẫn** hay **URI**.

## 12. Kiểm soát quyền và path traversal trước khi chuyển cho thư viện

Khi thư viện nhận `File`, nó thường sẽ mở/ghi tệp theo đường dẫn được truyền. Nếu đường dẫn bắt nguồn từ input không đáng tin, việc đổi `Path → File` **không hề lọc được dữ liệu nguy hiểm**.

Ví dụ:

```java
File destination = storageRoot
        .resolve(userInput)
        .toFile();
```

Đây là snippet; nếu `userInput` chứa `..`, là absolute path hoặc trỏ qua symlink, code có thể đọc/ghi sai vị trí. Không nên coi `resolve` hoặc `toFile` là bước xác minh an toàn.

Một lớp kiểm tra **cú pháp** ban đầu nên:

1. Xác định thư mục gốc tin cậy thành `Path` tuyệt đối và normalize.
2. Chỉ nhận đường dẫn tương đối theo policy; từ chối absolute path.
3. `resolve` dưới root và `normalize()`.
4. Xác nhận kết quả `startsWith(root)` theo **các thành phần Path**, không dùng String prefix.
5. Với thao tác thật, cần xử lý thêm symbolic links, permissions, race/TOCTOU và quy tắc của filesystem.

### 12.1. Ví dụ runnable: kiểm tra lexical boundary

Tạo `SafeFileBoundaryDemo.java`:

```java
import java.nio.file.Path;

public class SafeFileBoundaryDemo {
    static Path withinRoot(Path trustedRoot, String input) {
        Path relative = Path.of(input);
        if (relative.isAbsolute()) {
            throw new IllegalArgumentException(
                    "absolute-path");
        }

        Path root = trustedRoot.toAbsolutePath().normalize();
        Path candidate = root.resolve(relative).normalize();

        if (!candidate.startsWith(root)) {
            throw new IllegalArgumentException(
                    "outside-root");
        }
        return candidate;
    }

    public static void main(String[] args) {
        Path root = Path.of("storage", "uploads");

        Path valid = withinRoot(
                root, "photos/avatar.png");
        Path normalized = withinRoot(
                root, "tmp/../photos/avatar.png");

        System.out.println(
                "under-root="
                + valid.startsWith(
                    root.toAbsolutePath().normalize()));
        System.out.println(
                "same-normalized="
                + valid.equals(normalized));

        try {
            withinRoot(root, "../secret.txt");
            System.out.println("unexpected-traversal");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "traversal-rejected="
                    + ex.getMessage());
        }

        try {
            withinRoot(
                    root, root.toAbsolutePath()
                            .resolve("secret.txt").toString());
            System.out.println("unexpected-absolute");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "absolute-rejected="
                    + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SafeFileBoundaryDemo.java
java SafeFileBoundaryDemo
```

```text
under-root=true
same-normalized=true
traversal-rejected=outside-root
absolute-rejected=absolute-path
```

**Cảnh báo bảo mật:** đây chỉ là **lexical validation**. Nếu `storage/uploads/photos` là symbolic link trỏ ra ngoài root hoặc một tác nhân khác thay đổi thư mục giữa lúc kiểm tra và lúc mở, `normalize + startsWith` không bảo đảm tệp cuối cùng nằm dưới thư mục tin cậy.

Với hệ thống xử lý upload/tài liệu nhạy cảm:

- Ưu tiên **server-generated filename/opaque ID**, không để client quyết định arbitrary path.
- Hạn chế quyền file-system cho process và thư mục đích.
- Xác định chính sách symbolic link, filesystem mounts, Windows junctions/reparse points và alias đường dẫn.
- Xem xét `SecureDirectoryStream` khi provider hỗ trợ thao tác tương đối dựa trên directory handle, cùng chính sách chống TOCTOU.
- Dùng `CREATE_NEW`/các option phù hợp nếu không được ghi đè tệp có sẵn, xử lý lỗi khi trạng thái filesystem thay đổi.
- Với file URI từ bên ngoài, xác minh scheme/authority và chỉ cho phép vị trí theo policy; không tự tin rằng URL-encoding đã ngăn traversal.

Nếu thư viện có phương thức cho phép nhận `InputStream` thay vì `File`, đôi khi adapter có thể mở stream dưới quyền kiểm soát của mình. Tuy nhiên, cần xác minh rằng library **không đòi đường dẫn thật** cho random access và ai sẽ đóng stream.

## 13. Không cần ép tất cả API sang File

Một số cách thiết kế không cần tạo `File`:

- Nếu thư viện **nhận `Path` trực tiếp**, dùng `Path`, không có lý do tạo File trung gian.
- Nếu thư viện nhận `InputStream` và dữ liệu có thể đọc streaming, có thể dùng `Files.newInputStream(path)` rồi quản lý close theo contract.
- Nếu thư viện nhận `ByteBuffer`/`byte[]` và dữ liệu nhỏ, có thể đọc thành byte theo ràng buộc kích thước; tránh nạp file rất lớn tùy tiện.
- Nếu dữ liệu đến từ ZIP/JAR/cloud/provider không mặc định, ưu tiên overload hỗ trợ `Path` hoặc stream thay vì materialize tệp nếu API có sẵn.
- Nếu chỉ lưu **định danh** một tài liệu, ứng dụng có thể lưu ID hay URI thay vì luôn truyền một file path cục bộ.
- Nếu chỉ đọc nội dung văn bản vừa và nhỏ, `Files.readString(path, StandardCharsets.UTF_8)` đơn giản hơn mở `FileInputStream` chỉ để bọc vào reader.

**Khi nào vẫn cần File?** Khi đó là chữ ký hợp đồng thực tế của thư viện và đầu vào là file nằm trên default filesystem. Tại boundary đó, `path.toFile()` là API chuẩn, không phải hack.

### 13.1. API accept File so với API accept Path

Một thư viện có thể giữ overload:

```java
void process(File file) throws IOException;
void process(Path path) throws IOException;
```

Đây là **chữ ký minh họa**. Nếu cung cấp cả hai overload, tác giả thư viện nên tài liệu hóa:

- Overload `Path` có hỗ trợ provider không mặc định hay chỉ gọi `path.toFile()` bên trong?
- Symlink semantics, directory vs regular file, exceptions.
- Ai tạo/xóa output file, ai đóng stream?
- Có cần seek/random access hoặc file descriptor trên default filesystem?
- Có sử dụng đường dẫn **bất đồng bộ** sau khi method trả về?
- Charset, size limits và định dạng dữ liệu.

Chỉ có overload nhận `Path` **không tự bảo đảm** thư viện hoạt động với ZIP filesystem. Nếu nội bộ nó ép `path.toFile()`, giới hạn provider vẫn tồn tại — API cần ghi rõ.

## 14. Testing tại ranh giới thư viện

Test nên tập trung vào **hợp đồng giao tiếp**, không chỉ biết conversion có biên dịch:

| Trường hợp | Mục tiêu kiểm chứng |
| --- | --- |
| `Path` của default filesystem → `File` → `Path` | Không thay đổi ý nghĩa pathname |
| Relative Path | Adapter không tự giả định nó đã absolute; xác định working directory |
| File path có dấu cách và Unicode | Không tự nối URI string/escape sai |
| File chưa tồn tại | Conversion thành công nhưng I/O báo lỗi thích hợp |
| File nằm trong ZIP provider | `toFile` bị từ chối; có đường materialize/stream fallback |
| Library chỉ nhận File | Boundary adapter chuyển đúng nơi, không rò rỉ thư viện vào domain |
| Library xử lý async | Không xóa file tạm trước khi hoàn thành |
| Stream/ZipFile/FileSystem | Đóng đúng owner, không rò rỉ handle |
| File output thuộc root được phép | Validate lexical, đồng thời có chính sách symlink/race |
| Directory listing | Check null khi `listFiles`; đóng `Files.list` stream; sort khi cần ổn định |
| File move/delete | Phân biệt boolean failure với `IOException` cụ thể |
| Tệp lớn hoặc dữ liệu lỗi charset | Không đọc hết tùy tiện; có giới hạn và encoding contract |

**Kiểm thử trên OS đích** nếu phải hỗ trợ Windows/macOS/Linux. Cùng một logic path có thể gặp dấu phân tách, case sensitivity, UNC, drive letter, permissions và symbolic link khác nhau. Đừng hard-code `C:\...` vào unit test được thiết kế để chạy cả Linux.

### 14.1. Các quy tắc tránh test không ổn định

- Dùng `Files.createTempDirectory`/`Files.createTempFile` thay vì thư mục cố định trong repo.
- Không kiểm tra chính xác toàn bộ đường dẫn tuyệt đối trong stdout, vì working directory và ổ đĩa khác nhau.
- Dùng `Files.deleteIfExists` trong `finally`, nhưng vẫn cần đảm bảo tất cả stream/provider đã được đóng trước khi xóa.
- Test encoding qua equality/bytes, đừng phụ thuộc vào terminal có hiển thị đúng chữ có dấu.
- Với chương trình có tệp tạm và directory listing, sort output trước khi so sánh.
- Khi kiểm thử symlink, chỉ chạy nếu filesystem/quyền của môi trường hỗ trợ; không suy một kết quả duy nhất cho mọi hệ điều hành.
- Kiểm tra false/IOException ở tình huống thật, không dùng `File.exists` như giả lập “không có quyền” nếu môi trường không đảm bảo.

## 15. Những lỗi thường gặp

| Sai lầm | Tại sao sai | Cách đúng |
| --- | --- | --- |
| “`File` đã lỗi thời nên không thể dùng” | Nhiều thư viện/JDK API hiện hành vẫn nhận `File` | Giữ `Path` trong core, dùng `toFile` ở boundary cần thiết |
| “Mọi `Path` đều có `toFile()`” | Path của provider khác default có thể không chuyển | Dùng stream/Path API hoặc materialize dữ liệu |
| “`new File(pathString)` tạo file” | Chỉ tạo abstract pathname | Dùng API I/O để mở/tạo file |
| “`Path.toFile()` đã kiểm tra file tồn tại” | Không có I/O validation | Gọi thao tác `Files` thích hợp và xử lý exception |
| “`new File(uri.toString())` tương đương `new File(uri)`” | URI string không phải pathname string | Dùng `new File(fileUri)` theo contract hoặc `Path.of(fileUri)` |
| “`Path.of(httpsUri)` tải file” | Không phải HTTP client | Dùng client/network API thích hợp |
| “Tạo adapter ở mọi tầng cho chắc” | Lan truyền File/Path conversion không cần thiết | Tập trung chuyển đổi tại boundary |
| “`file.exists()` đủ để chống race” | Trạng thái có thể đổi ngay sau check | Chọn thao tác atomic/provider-aware phù hợp và xử lý ngoại lệ |
| “`file.delete()` sẽ giải thích lỗi xóa” | Trả boolean, ít thông tin lỗi | Dùng `Files.delete` nếu cần lỗi I/O rõ |
| “`File.length()` luôn là kích thước đáng tin” | Có thể trả 0 khi file không có/lỗi | Dùng `Files.size` và xử lý IOException |
| “Trả một File nghĩa là hoàn tất ghi async” | Thư viện có thể dùng pathname về sau | Theo lifecycle/contract thư viện |
| “ZIP entry Path là File local” | ZIP là filesystem provider riêng | Materialize hoặc dùng stream/Path overload |
| “`normalize().startsWith(root)` đủ bảo mật” | Symlink, junction, TOCTOU, mount points | Tăng cường kiểm soát filesystem và permissions |
| “`Files.list` là Stream thuần, không cần close” | Stream có directory handle | Dùng TWR |
| “Chuyển sang File sẽ đổi charset” | Charset thuộc thao tác encode/decode, không thuộc tên path | Chỉ rõ charset tại I/O boundary |
| “Mọi file trả bởi thư viện đều thuộc quyền xóa của caller” | Ownership có thể thuộc framework/SDK | Theo hợp đồng và cleanup policy |

## 16. Bài tập thực hành

**Bài 1 — Conversion.** Chạy `FilePathRoundTripDemo`. Thử tên có dấu `#` và khoảng trắng, quan sát `toASCIIString()`. Giải thích tại sao `File.toPath` khác với việc parse text URI.

**Bài 2 — Adapter thực tế.** Chạy `LegacyFileAdapterDemo`. Hãy tạo interface `ReportExporter` nhận `Path` và một implementation gọi một API chỉ nhận `File`; unit test chứng minh logic ứng dụng không phụ thuộc kiểu `File`.

**Bài 3 — Files vs File.** Chạy `FileApiBehaviorDemo`. Thử đọc file chưa tồn tại, đổi đường dẫn thành thư mục và xử lý lỗi theo từng thao tác, không dùng `exists` để tự suy ra mọi lý do thất bại.

**Bài 4 — ZIP provider.** Chạy `ZipFileBoundaryDemo`. Vì sao `inside.toFile()` thất bại? Thử viết một adapter nhận `Path` bất kỳ: nếu thuộc default filesystem thì truyền `toFile` trực tiếp, nếu không thì materialize vào file tạm. Đừng xóa file tạm trước khi thư viện xử lý xong.

**Bài 5 — ImageIO.** Chạy `ImageIoFileBoundaryDemo`. Thay `ImageIO.read(File)` bằng overload stream và xác định ai đóng stream; so sánh chi phí/khả năng hoạt động với ZIP Path.

**Bài 6 — Directory listing.** Chạy `DirectoryFileAdapterDemo`. Thử lọc theo extension không phân biệt chữ hoa/chữ thường nhưng làm rõ locale/filename rules; kiểm tra `listFiles` có thể null và bảo đảm `Files.list` stream được đóng.

**Bài 7 — Bảo mật đường dẫn.** Chạy `SafeFileBoundaryDemo`. Thử `"../../outside.txt"` và một đường dẫn tuyệt đối. Nêu ba rủi ro mà lexical check chưa giải quyết khi có symlink hoặc directory bị thay đổi đồng thời.

**Bài 8 — Contract.** Viết JavaDoc cho phương thức `Path export(Path target)` và một adapter `File toLibraryFile(Path input)`. Nêu rõ ownership của file tạm, thời điểm đóng handle, provider được hỗ trợ và có xử lý async hay không.

**Bài 9 — Test đa nền tảng.** Thiết kế kiểm thử không hard-code `/tmp` hay `C:\temp`: tạo temp path, đổi File/Path, ghi/đọc, dùng URI và xác minh byte thay vì dựa vào text hiển thị.

## 17. Kết luận

- **`File` và `Path` đều còn hợp lệ**. `Path` phù hợp làm API nội bộ mới; `File` tiếp tục là input/output của nhiều thư viện hiện hành.
- **`file.toPath()`** chuyển pathname của File sang `Path` thuộc default filesystem.
- **`path.toFile()`** chuyển `Path` thuộc default filesystem sang `File`; với ZIP/JAR hoặc provider không mặc định, có thể ném `UnsupportedOperationException`.
- **Đổi biểu diễn không thực hiện I/O, không đổi charset, không mở/đóng resource và không xác minh quyền truy cập.**
- Khi thư viện yêu cầu `File` nhưng dữ liệu đến từ provider khác, **dùng overload Path/stream hoặc materialize nội dung ra file local** rồi dọn sau khi thư viện đã dùng xong.
- **Không nhầm URI với pathname**: `new File(fileUri)`/`Path.of(fileUri)` khác `new File(uri.toString())`, và `https:` không phải đường dẫn file local.
- **Ownership và security vẫn cần thiết**: đúng scope I/O, đóng stream/provider, không xóa tệp tạm sớm, validate input và kiểm soát symlink/race.
- Với Java 17+, đây là cách thực tế để **tương tác với thư viện chỉ hỗ trợ File mà không làm mất lợi ích của NIO.2**.

## Tài liệu chính thức

- [Path — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `toFile()`, `toUri()`, `resolve()` và giới hạn provider.
- [File — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/File.html): `toPath()`, `toURI()`, constructors, `listFiles`, `delete` và `renameTo`.
- [Files — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `copy`, `move`, `list`, I/O exceptions.
- [FileSystems — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): tạo/mở filesystem và provider.
- [ImageIO — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/javax/imageio/ImageIO.html): các overload `read(File)`/`write(...,File)` hiện hành.
- [URI — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): scheme, percent-encoding, chuyển URI cho file paths.
