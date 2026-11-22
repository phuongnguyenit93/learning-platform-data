# Đường dẫn tương đối, tuyệt đối và File System Provider trong Java 11+

## 1. Vì sao phải hiểu đúng đường dẫn khi thao tác tệp văn bản?

Khi chương trình đọc hoặc ghi tệp, chuỗi `"notes.txt"` chưa đủ để xác định tệp nằm ở đâu: kết quả còn phụ thuộc vào **hệ thống tệp**, **thư mục làm việc** và cách đường dẫn được diễn giải. Java NIO.2 biểu diễn đường dẫn bằng `java.nio.file.Path`, cung cấp các thao tác như `resolve`, `normalize`, `toAbsolutePath` và `toRealPath`.

Ba khái niệm cốt lõi:

- **Đường dẫn tương đối (relative path):** Chưa có gốc đầy đủ; cần kết hợp với một vị trí cơ sở để tìm tệp.
- **Đường dẫn tuyệt đối (absolute path):** Có gốc theo quy tắc của hệ thống tệp tương ứng. Nó mô tả một vị trí mà không cần ghép thêm đường dẫn cơ sở, nhưng **không đảm bảo tệp tồn tại**.
- **File System Provider:** Thành phần cung cấp cách Java tạo, hiểu và thao tác với hệ thống tệp. Ví dụ, hệ thống tệp mặc định thường dùng scheme `file`; nhà cung cấp ZIP/JAR có scheme `jar` và cho phép xem nội dung tệp ZIP/JAR dưới dạng một cây thư mục.

Trong Java 11, ưu tiên `Path.of(...)` để tạo đường dẫn trên hệ thống tệp mặc định, `Files` để thực hiện I/O. Các API này vẫn được duy trì trên các phiên bản Java hiện đại; không cần ghép thủ công toàn bộ đường dẫn bằng chuỗi.

## 2. Phân biệt đường dẫn tương đối và tuyệt đối

Ví dụ trên hệ thống Unix-like:

~~~text
Tương đối:  docs/readme.txt
Tuyệt đối: /home/app/project/docs/readme.txt
~~~

Ví dụ trên một hệ thống Windows:

~~~text
Tương đối:  docs\readme.txt
Tuyệt đối: C:\work\project\docs\readme.txt
~~~

Hai đường dẫn tuyệt đối trên chỉ là **ví dụ về cú pháp**, không phải đường dẫn chắc chắn có trên máy. Quy tắc phân biệt gốc, dấu phân cách, ổ đĩa, đường dẫn mạng và phân biệt chữ hoa/thường tùy file-system provider và nền tảng. Trên Windows còn có các dạng như `C:notes.txt` mang tính tương đối theo ổ đĩa; **không suy đoán tính tuyệt đối chỉ bằng việc nhìn thấy dấu `:` hoặc `/`**.

Dùng API để kiểm tra:

~~~java
Path relative = Path.of("docs", "readme.txt");
System.out.println(relative.isAbsolute());  // false trên default FS thông thường

Path absolute = relative.toAbsolutePath();
System.out.println(absolute.isAbsolute());  // true
~~~

Đây là **đoạn minh họa**, cần đặt trong một lớp/phương thức Java và import `java.nio.file.Path` để chạy độc lập.

### Thư mục làm việc không phải thư mục mã nguồn

Với `Path.of("docs", "readme.txt")`, Java hiểu đường dẫn tương đối theo ngữ cảnh của **file system mặc định và tiến trình đang chạy**. Trong tình huống thông dụng, nó liên hệ với thư mục làm việc (`user.dir`), nơi chương trình được khởi chạy.

~~~java
System.out.println(System.getProperty("user.dir"));
Path file = Path.of("docs", "readme.txt");
System.out.println(file.toAbsolutePath());
~~~

Kết quả phụ thuộc máy chạy, cấu hình IDE, terminal, container hoặc service. Thư mục tương đối **không mặc nhiên là thư mục có tệp `.java`, `.class` hoặc `.jar`**. Chạy cùng chương trình từ hai working directory khác nhau có thể làm nó tìm hai tệp khác nhau.

**Cách thiết kế dễ kiểm soát:** Nhận một `Path baseDir` từ cấu hình hoặc tham số chương trình rồi tính `baseDir.resolve("docs").resolve("readme.txt")`. Nếu làm thư viện, nhận `Path` từ caller giúp giữ đúng hệ thống tệp mà caller đang dùng, thay vì âm thầm gọi `Path.of(String)` và mặc định chuyển sang file system của máy.

## 3. Các thao tác `Path` cần nắm

| API | Ý nghĩa | Có truy cập tệp thật không? |
| --- | --- | --- |
| `Path.of("docs", "readme.txt")` | Tạo `Path` trên default file system (Java 11+) | Không |
| `path.isAbsolute()` | Kiểm tra đường dẫn có gốc đầy đủ theo provider | Không |
| `base.resolve(child)` | Ghép đường dẫn con vào một đường dẫn cơ sở | Không |
| `base.relativize(target)` | Tính đường dẫn từ base đến target (nếu tương thích) | Không |
| `path.normalize()` | Loại thành phần `.`/`..` dư thừa theo quy tắc đường dẫn | Không |
| `path.toAbsolutePath()` | Chuyển thành đường dẫn tuyệt đối theo file system | Thường không kiểm tra tệp tồn tại |
| `path.toRealPath()` | Tìm đường dẫn thực của **tệp đang tồn tại** | Có; có thể ném `IOException` |
| `path.getFileSystem()` | Trả về `FileSystem` đã tạo `Path` | Không |
| `path.toUri()` | Biểu diễn địa chỉ bằng URI do provider quy định | Tùy provider |

### `resolve`: ghép đường dẫn với vị trí cơ sở

~~~java
Path base = Path.of("workspace");
Path file = base.resolve(Path.of("docs", "notes.txt"));
// Đường dẫn logic: workspace/docs/notes.txt (dấu phân cách tùy OS)
~~~

Nếu đối số đưa vào `resolve` **là đường dẫn tuyệt đối**, API có thể trả lại chính đường dẫn tuyệt đối đó, bỏ qua base; vì thế không được dùng `resolve` như phép bảo đảm rằng kết quả luôn nằm dưới base. Cần kiểm tra, xử lý đầu vào theo chính sách truy cập tệp.

### `normalize`: biến đổi từ vựng, không kiểm tra hiện trạng

~~~java
Path path = Path.of("docs", "..", "docs", ".", "notes.txt");
Path normalized = path.normalize();
// Đường dẫn logic: docs/notes.txt
~~~

`normalize()` loại các đoạn dư thừa **theo cú pháp**, không truy cập đĩa, không xác nhận tồn tại, không “sửa” liên kết tượng trưng và không xác thực quyền truy cập. Nếu `docs` hoặc thư mục trung gian là symbolic link, bỏ `..` có thể dẫn đến một vị trí khác với cách hệ thống tệp thực tế diễn giải đường dẫn ban đầu.

Đừng nhầm `Path.normalize()` với **chuẩn hóa Unicode của nội dung tệp** (ví dụ `java.text.Normalizer`). Một hàm xử lý **cấu trúc đường dẫn**, hàm kia xử lý **chuỗi văn bản**.

### `toAbsolutePath` và `toRealPath` khác nhau ở đâu?

~~~java
Path candidate = Path.of("docs", "notes.txt");
Path absolute = candidate.toAbsolutePath();  // Không bắt buộc tồn tại.
Path real = candidate.toRealPath();          // Phải tồn tại; có thể IOException.
~~~

Đoạn trên là **mã minh họa**: muốn chạy không lỗi với `toRealPath()`, phải tạo tệp trước hoặc chỉ ra một tệp thực sự tồn tại.

- `toAbsolutePath()` chuyển đường dẫn sang dạng tuyệt đối, thường dựa vào working directory của default file system. Nó **không đảm bảo** vị trí đó có tệp.
- `toRealPath()` yêu cầu truy cập hệ thống tệp, chuẩn hóa đường dẫn thực và mặc định **theo symbolic link** để xác định đích cuối; có thể báo `NoSuchFileException`, `AccessDeniedException` hoặc `IOException` khác.
- Nếu gọi `toRealPath(LinkOption.NOFOLLOW_LINKS)`, Java được yêu cầu **không theo symbolic link** khi xác định đường dẫn thực. Ngữ nghĩa chính xác còn phụ thuộc provider; đây không phải cách tự động giải quyết mọi rủi ro liên quan symlink.
- `Path.equals` so sánh đối tượng đường dẫn theo quy tắc provider; hai đường dẫn khác cách viết vẫn có thể trỏ cùng một tệp. Khi tệp thực sự tồn tại và cần kiểm tra nhận dạng thực, cân nhắc `Files.isSameFile(a, b)` và xử lý `IOException`.

### `relativize`: lấy đường đi từ một vị trí đến vị trí khác

~~~java
Path base = Path.of("workspace", "docs");
Path target = Path.of("workspace", "images", "logo.png");
Path rel = base.relativize(target);
// Kết quả về mặt thành phần: ../images/logo.png
~~~

`relativize` là phép tính đường dẫn, không yêu cầu tệp tồn tại. Nó cần hai `Path` tương thích về provider và loại gốc. Không thể tùy tiện gọi giữa một path tương đối và một path tuyệt đối hoặc giữa default file system với ZIP file system; các trường hợp không tương thích có thể ném `IllegalArgumentException` hoặc lỗi provider tương ứng.

## 4. File System Provider: đường dẫn thuộc về hệ thống tệp nào?

Trong Java NIO.2:

~~~text
FileSystemProvider (triển khai thao tác file system)
        |
        v
FileSystem (hệ thống tệp cụ thể, vòng đời riêng)
        |
        v
Path (địa chỉ trong hệ thống tệp đó)
        |
        v
Files.readString / writeString / copy / move / ...
        |
        v
Provider thực hiện thao tác phù hợp
~~~

Các lớp/kiểu quan trọng:

- `java.nio.file.spi.FileSystemProvider`: lớp SPI (*Service Provider Interface*) đại diện cách truy cập hệ thống tệp, được định danh bằng **URI scheme** như `file` hoặc `jar`.
- `java.nio.file.FileSystem`: không gian đường dẫn với root, separator, thuộc tính, hỗ trợ read/write và vòng đời; một provider có thể cung cấp một hoặc nhiều `FileSystem`.
- `java.nio.file.Path`: đối tượng đường dẫn do một `FileSystem` tạo ra; `path.getFileSystem().provider()` cho biết provider tương ứng.
- `java.nio.file.Files`: các thao tác I/O cấp cao. Nhiều thao tác được ủy quyền cho provider của `Path`. Provider có thể có giới hạn riêng về thuộc tính hoặc hoạt động hỗ trợ.

Ví dụ hai scheme hữu ích:

| Provider/file system | Scheme thường gặp | Cách tạo `Path` | Mục đích |
| --- | --- | --- | --- |
| Default provider của hệ điều hành | `file` | `Path.of("docs", "notes.txt")` hoặc `FileSystems.getDefault().getPath(...)` | Thư mục/tệp trên ổ đĩa hệ điều hành |
| ZIP/JAR file system của JDK (module `jdk.zipfs`) | `jar` | Mở `FileSystem` bằng `FileSystems.newFileSystem(...)`, rồi `zipfs.getPath("/docs/notes.txt")` | Đọc/ghi nội dung ZIP/JAR qua API `Files` |

**Đường dẫn kiểu `/docs/notes.txt` trong ZIP thuộc về ZIP file system, không phải root `/docs` ngoài ổ đĩa.** Hai `Path` có thể có tên hiển thị tương tự nhau nhưng thuộc những không gian tệp khác nhau. Luôn giữ đúng `FileSystem` khi thao tác tệp.

Đối với code thư viện cần hoạt động với nhiều provider, hãy nhận một `Path` đầu vào và dùng `basePath.resolve("child")` hoặc `basePath.getFileSystem().getPath(...)`. Cách này giữ context của provider. `Path.of(String)` mặc định dùng default provider nên **không** tự nhảy vào ZIP file system mà bạn đang mở.

Đừng cố chuyển tùy tiện mọi `Path` sang `java.io.File`: `Path.toFile()` phù hợp với default provider nhưng có thể **không được hỗ trợ** với provider như ZIP/JAR.

## 5. Ví dụ chạy độc lập: đọc/ghi UTF-8 qua hai provider

Ví dụ sau tự tạo một thư mục tạm, ghi một tệp văn bản ở default file system, tạo một ZIP file system bằng provider `jar`, đọc lại dữ liệu từ cả hai rồi dọn đúng các tệp tạm đã tạo.

**Yêu cầu:** JDK 11 trở lên, có module `jdk.zipfs` (thường có trong bản JDK đầy đủ; một runtime tạo bằng `jlink` có thể không chứa module này). Hệ thống tệp tạm cần cho phép tạo, đọc và xóa tệp.

Tạo tệp **PathProviderLesson.java**:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class PathProviderLesson {
    public static void main(String[] args) throws IOException {
        Path relative = Path.of("docs", "..", "docs", "note.txt");
        System.out.println("relative=" + !relative.isAbsolute());
        System.out.println("normalized=" +
                relative.normalize().equals(Path.of("docs", "note.txt")));

        Path root = Files.createTempDirectory("path-provider-demo-");
        try {
            Path note = root.resolve(relative.normalize());
            Files.createDirectories(note.getParent());
            Files.writeString(note, "Xin chào Java 11", StandardCharsets.UTF_8);

            System.out.println("absolute=" + note.toAbsolutePath().isAbsolute());
            System.out.println("fileScheme=" +
                    note.getFileSystem().provider().getScheme());
            System.out.println("realSame=" +
                    Files.isSameFile(note, note.toRealPath()));
            System.out.println("readMatch=" +
                    Files.readString(note, StandardCharsets.UTF_8)
                            .equals("Xin chào Java 11"));

            Path archive = root.resolve("notes.zip");
            URI jarUri = URI.create("jar:" + archive.toUri());
            try (FileSystem zipfs = FileSystems.newFileSystem(
                    jarUri, Map.of("create", "true"))) {
                Path inZip = zipfs.getPath("/docs/note.txt");
                Files.createDirectories(inZip.getParent());
                Files.writeString(inZip, "Trong ZIP", StandardCharsets.UTF_8);
                System.out.println("zipScheme=" +
                        inZip.getFileSystem().provider().getScheme());
                System.out.println("zipReadMatch=" +
                        Files.readString(inZip, StandardCharsets.UTF_8)
                                .equals("Trong ZIP"));
                System.out.println("differentFS=" +
                        !note.getFileSystem().equals(inZip.getFileSystem()));
                System.out.println("zipAbsolute=" + inZip.isAbsolute());
            }
        } finally {
            Files.deleteIfExists(root.resolve("notes.zip"));
            Files.deleteIfExists(root.resolve("docs").resolve("note.txt"));
            Files.deleteIfExists(root.resolve("docs"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch bằng JDK hỗ trợ Java 11, rồi chạy:

~~~bash
javac --release 11 PathProviderLesson.java
java PathProviderLesson
~~~

**stdout chính xác khi các điều kiện ở trên được đáp ứng:**

~~~text
relative=true
normalized=true
absolute=true
fileScheme=file
realSame=true
readMatch=true
zipScheme=jar
zipReadMatch=true
differentFS=true
zipAbsolute=true
~~~

Mã trên đã được kiểm chứng bằng JDK hiện đại với tùy chọn biên dịch `--release 11`. Kết quả chỉ in ra các phép kiểm tra đúng/sai và URI scheme, không in đường dẫn thư mục tạm (vốn thay đổi theo máy).

**Điểm cần chú ý trong ví dụ:**

1. `relative` chưa mang gốc; `relative.normalize()` loại đoạn `docs/..` và cho tên `docs/note.txt`. Hàm này không truy cập đĩa.
2. `Files.createTempDirectory(...)` cấp một thư mục làm việc tạm trong default file system; dùng `root.resolve(...)` để có đường dẫn rõ ràng và tránh phụ thuộc vào thư mục khởi chạy cho tệp được viết.
3. `Files.createDirectories(note.getParent())` tạo các thư mục cha cần thiết; nếu thư mục đã tồn tại, API vẫn có thể dùng theo hợp đồng của nó.
4. `Files.writeString(..., StandardCharsets.UTF_8)` và `Files.readString(..., StandardCharsets.UTF_8)` ghi/đọc văn bản một cách rõ ràng với UTF-8; không nên dựa vào charset mặc định khi hợp đồng dữ liệu yêu cầu UTF-8.
5. `note.toRealPath()` chạy được vì đã tạo tệp. `Files.isSameFile(...)` xác nhận hai đường dẫn trong ví dụ trỏ cùng tệp.
6. `URI.create("jar:" + archive.toUri())` tạo URI cho ZIP provider; `Map.of("create", "true")` yêu cầu tạo ZIP mới. Cú pháp ZIP URI và tùy chọn này thuộc `jdk.zipfs`.
7. `zipfs.getPath("/docs/note.txt")` tạo đường dẫn **bên trong ZIP**. `Files.writeString` và `readString` vẫn hoạt động nhờ provider của ZIP.
8. `try (FileSystem zipfs = ...)` đảm bảo đóng ZIP file system. Việc đóng giúp giải phóng tài nguyên và hoàn tất các thao tác mà provider cần thực hiện trên archive.
9. Khối `finally` xóa các tên tệp tạm mà ví dụ tạo ra; trong ứng dụng thực tế cần quản lý cleanup và xử lý lỗi theo yêu cầu của hệ thống, không tự ý xóa dữ liệu người dùng.

**Cảnh báo về ghi đè:** `Files.writeString(path, text, charset)` mặc định tạo tệp nếu chưa có, còn nếu đã tồn tại thì **mở để ghi đè/truncate nội dung**. Khi dữ liệu sẵn có phải được bảo toàn, hãy chọn các `OpenOption` phù hợp (ví dụ `StandardOpenOption.CREATE_NEW` để từ chối nếu tệp đã tồn tại), đồng thời thiết kế cơ chế ghi an toàn với lỗi và đồng thời truy cập.

## 6. Đường dẫn, URI và provider khác nhau như thế nào?

- **Đường dẫn (`Path`):** đối tượng Java diễn giải theo một file system cụ thể, có thể tương đối hoặc tuyệt đối.
- **URI (`java.net.URI`):** địa chỉ có scheme, ví dụ `file:///...` hoặc `jar:file:///...!/docs/note.txt`; chuỗi URI không phải cú pháp đường dẫn OS thông thường.
- **Provider:** thành phần gắn scheme với cách tạo file system và thao tác trên `Path`.

Với default provider, Java hỗ trợ:

~~~java
Path p = Path.of("docs", "notes.txt");
URI uri = p.toUri();
Path q = Path.of(uri);
~~~

Đây là đoạn minh họa (cần `import java.net.URI;` và `import java.nio.file.Path;`). `p` có thể tương đối trong khi URI thường là tuyệt đối; `q` vì vậy có thể là đường dẫn tuyệt đối. Đừng mặc định `p.equals(q)` sẽ là `true`.

Đối với URI kiểu `jar:...`, provider tương ứng thường cần **ZIP file system đang được mở** trước khi tạo path đến một entry. Nếu chưa có file system hoặc provider không được cài, `Path.of(uri)` có thể ném `FileSystemNotFoundException`; các thao tác mở có thể báo thiếu provider hoặc tùy chọn không hỗ trợ. Đối với các file system tùy biến, cấu trúc URI và quy tắc hoạt động là **provider-specific**.

## 7. Lỗi thường gặp, cách nhận biết và sửa

| Hiện tượng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Ghép đường dẫn sai base, tệp không tồn tại | Log đường dẫn đã xác định, kiểm tra working directory và đầu vào |
| `AccessDeniedException` | Quyền truy cập của tiến trình không đủ | Kiểm tra quyền trên tệp/thư mục và môi trường chạy |
| `Path.of("notes.txt")` hoạt động trong IDE nhưng lỗi khi chạy service | Working directory khác nhau | Truyền baseDir từ cấu hình; `resolve` theo baseDir |
| `toAbsolutePath()` trả về đường dẫn nhưng đọc vẫn lỗi | Absolute không đảm bảo tồn tại/quyền | Dùng `Files` để truy cập và xử lý IOException |
| `normalize()` không “sửa” file thực tế | Đây là biến đổi cú pháp, không thực hiện I/O | Chỉ dùng normalize để thao tác tên; dùng `toRealPath` khi cần kiểm tra tệp tồn tại |
| `zipfs.getPath(...)` bị hiểu nhầm là đường dẫn máy | `Path` thuộc ZIP provider | Giữ path theo đúng file system |
| `Path.of(String)` trỏ ngoài ZIP | `Path.of(String)` sử dụng default file system | Dùng `zipfs.getPath(...)` hoặc `pathTrongZip.resolve(...)` |
| `ProviderNotFoundException` / `FileSystemNotFoundException` | Chưa cài/mở provider tương ứng | Kiểm tra `jdk.zipfs` hoặc runtime, mở file system trước |
| Không xóa hoặc sửa được tệp ZIP khi đang dùng | ZIP file system còn mở hoặc tệp đang bị giữ | Dùng try-with-resources đóng ZIP file system và quản lý luồng/tài nguyên |
| `ProviderMismatchException` hay lỗi khi `relativize` | Dùng `Path` từ các provider khác nhau hoặc đường dẫn không tương thích | Không trộn hệ thống tệp; chuyển dữ liệu qua `Files` nếu muốn sao chép |

Thông báo cụ thể và cơ chế quyền truy cập thay đổi theo hệ điều hành và provider; không dựa vào một chuỗi lỗi duy nhất để suy ra nguyên nhân tuyệt đối.

## 8. Tránh path traversal và hiểu đúng liên kết tượng trưng

Nếu đường dẫn con được lấy từ người dùng, tuyệt đối không mặc định rằng:

~~~java
Path requested = base.resolve(userInput).normalize();
~~~

sẽ luôn nằm dưới `base`. Các đầu vào như `../private.txt` hoặc một đường dẫn tuyệt đối có thể thoát khỏi vị trí dự định. Thêm nữa, **symlink** có thể dẫn ra ngoài ngay cả khi chuỗi đường dẫn nhìn có vẻ còn trong base.

Với **tệp đã tồn tại**, có thể minh họa hai bước kiểm tra sau, với `base` là thư mục có thật và `userInput` là đầu vào:

~~~java
Path rootReal = base.toRealPath();
Path requested = rootReal.resolve(userInput).normalize();

if (!requested.startsWith(rootReal)) {
    throw new IllegalArgumentException("path outside base");
}

Path actual = requested.toRealPath(); // Kiểm tra tồn tại; theo symlink.
if (!actual.startsWith(rootReal)) {
    throw new IllegalArgumentException("symlink outside base");
}
~~~

Đây chỉ là **mã minh họa cách phát hiện các trường hợp thoát khỏi thư mục ở thời điểm kiểm tra**. Nó **không đủ để bảo đảm an toàn khi có tiến trình khác sửa symbolic link/thư mục đồng thời** (rủi ro *time-of-check/time-of-use*). Với I/O thực sự dựa vào đường dẫn không đáng tin, thiết kế cần giới hạn quyền hệ điều hành, giảm quyền của tiến trình, áp dụng cơ chế mở tệp phù hợp, và cân nhắc `SecureDirectoryStream` khi provider hỗ trợ. Với **tệp chuẩn bị tạo mới**, `toRealPath()` của tệp chưa tồn tại sẽ báo lỗi, cần một chiến lược khác xử lý thư mục cha và điều kiện race.

**Đừng so sánh đường dẫn bằng tiền tố chuỗi** như `requested.toString().startsWith(base.toString())`: `/data/users` cũng là tiền tố của `/data/users2`. Khi cần so sánh cấu trúc đường dẫn, dùng `Path.startsWith(Path)` cùng file system, rồi vẫn giải quyết symlink/race theo nhu cầu bảo mật.

## 9. Tình huống thực tế khi đọc tệp văn bản

Giả sử chương trình phải đọc `config/settings.txt` trong thư mục do ứng dụng quản lý. Tránh viết:

~~~java
String text = Files.readString(Path.of("config/settings.txt"));
~~~

nếu không biết working directory của tiến trình lúc chạy. Thay bằng một root rõ ràng:

~~~java
Path appDataRoot = Path.of("/path/to/app-data"); // Cần cấu hình cho từng OS.
Path file = appDataRoot.resolve("config").resolve("settings.txt");
String text = Files.readString(file, StandardCharsets.UTF_8);
~~~

Đây là **mẫu minh họa**, không phải chương trình độc lập. `/path/to/app-data` là placeholder đường dẫn ví dụ; trong ứng dụng thực tế phải truyền đường dẫn thư mục từ cấu hình và kiểm tra quyền truy cập. Trên Windows, thay root bằng đường dẫn hợp lệ của Windows.

Nếu chỉ cần đọc classpath resource được đóng gói bên trong JAR, `Path.of("...")` trên máy không có nghĩa là entry trong JAR; hãy dùng cơ chế đọc resource của class loader (`getResourceAsStream`) khi phù hợp. Việc đọc ZIP file system qua `jdk.zipfs` là lựa chọn khi cần coi archive như hệ thống tệp, không phải điều kiện bắt buộc cho mọi lần đọc tài nguyên đóng gói.

Một quy trình đọc tệp văn bản có thể thực hiện theo thứ tự: nhận baseDir rõ ràng → xây `Path` đúng provider → xác thực đầu vào/giới hạn truy cập nếu cần → đọc bằng `Files.readString(..., UTF_8)` → xử lý lỗi I/O → đóng mọi resource mở thủ công. Với file lớn, đừng dùng `readString` để nạp toàn bộ vào RAM nếu không cần; sử dụng streaming reader (`Files.newBufferedReader`) hoặc luồng xử lý phù hợp.

## 10. Checklist kiến thức cần nhớ

1. **`Path` là địa chỉ trong một `FileSystem` cụ thể**, không chỉ là chuỗi ký tự.
2. **Relative** cần cơ sở để xác định vị trí; **absolute** đủ gốc nhưng không chứng minh tồn tại.
3. Với Java 11+, `Path.of(...)` tạo path theo default file system; muốn giữ context provider khác, dùng `fileSystem.getPath(...)` hoặc `existingPath.resolve(...)`.
4. `resolve` ghép path, `relativize` tạo đường đi tương đối, `normalize` xử lý cấu trúc từ vựng.
5. `toAbsolutePath` không kiểm tra sự tồn tại; `toRealPath` truy cập hệ thống tệp và thường theo symlink mặc định.
6. `path.getFileSystem().provider().getScheme()` cho biết provider (ví dụ `file` và `jar`).
7. `Files.readString/writeString` hỗ trợ văn bản UTF-8; chú ý chính sách ghi đè, lỗi I/O và tệp lớn.
8. Path bên trong ZIP/JAR không thuộc default file system; cần `jdk.zipfs` khi dùng ZIP provider.
9. Không dùng `normalize` hoặc `startsWith` đơn độc như biện pháp chống path traversal đáng tin cậy dưới điều kiện có symlink/race.
10. Cấu hình thư mục cơ sở rõ ràng, dùng dấu phân cách qua `Path`, đóng `FileSystem`/stream đúng vòng đời.

**Kết luận:** Trong Java 11 và các bản Java hiện hành, hãy mô hình hóa vị trí tệp bằng `Path`, phân biệt thao tác cú pháp với kiểm tra tệp tồn tại, và giữ nguyên file-system provider của đường dẫn khi đọc/ghi văn bản. Nhờ đó chương trình rõ ràng hơn về vị trí tệp, dùng được cả default file system và provider chuyên biệt, đồng thời giảm những lỗi do working directory hoặc chuyển đổi đường dẫn tùy tiện.

## Tài liệu chuẩn hiện hành

- [Oracle Java SE 25 — `Path`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html): `Path.of`, `resolve`, `normalize`, `toAbsolutePath`, `toRealPath`, `getFileSystem`.
- [Oracle Java SE 25 — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): thao tác đọc/ghi/copy/di chuyển, xử lý I/O.
- [Oracle Java SE 25 — `FileSystems`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileSystems.html): file system mặc định, nạp provider và tạo `FileSystem`.
- [Oracle Java SE 25 — `FileSystemProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): vai trò SPI và scheme `file`.
- [Oracle Java SE 25 — module `jdk.zipfs`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.zipfs/module-summary.html): ZIP/JAR file system và scheme `jar`.

Tất cả ví dụ sử dụng API còn được hỗ trợ, ưu tiên `Path.of` (Java 11+) và tính năng NIO.2 hiện hành; không yêu cầu công nghệ legacy hay API bị loại bỏ.