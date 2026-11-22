# Quan hệ giữa `Path` và `FileSystem` tạo ra nó

## 1. Ý tưởng cốt lõi

Trong Java NIO.2 (`java.nio.file`), một `Path` không chỉ là chuỗi mô tả vị trí. Nó là **đối tượng đường dẫn thuộc về một `FileSystem` cụ thể**. `FileSystem` quyết định cách phân tích tên, dấu phân cách, đường dẫn gốc và một số quy tắc thao tác với đường dẫn đó.

- `FileSystem`: mô hình của một hệ thống tệp, chẳng hạn hệ thống tệp mặc định của máy hoặc một tệp ZIP được mở như hệ thống tệp.
- `Path`: vị trí của tệp/thư mục *bên trong* hệ thống tệp đó; bản thân `Path` không đảm bảo tệp thực tế tồn tại.
- `FileSystemProvider`: thành phần cung cấp triển khai cho loại hệ thống tệp tương ứng, ví dụ provider mặc định với scheme `file` hoặc ZIP filesystem provider với scheme `jar`.

Quan hệ cốt lõi:

~~~text
FileSystemProvider (triển khai cách truy cập)
          |
          +--> FileSystem A --> Path A1, Path A2, ...
          |
          +--> FileSystem B --> Path B1, Path B2, ...
~~~

**Một `Path` luôn gắn với một `FileSystem` thông qua `path.getFileSystem()`.** Một provider có thể quản lý nhiều `FileSystem`; nhiều `Path` có thể cùng thuộc một `FileSystem`. Ngay cả khi hai đường dẫn có `toString()` giống nhau, chúng chưa chắc nói đến cùng đối tượng tệp nếu thuộc các hệ thống tệp khác nhau.

Ví dụ, `/docs/readme.md` trong ZIP không phải `/docs/readme.md` trên ổ đĩa máy, dù dạng chữ trông tương tự.

## 2. Tạo `Path` từ đâu thì thuộc `FileSystem` đó

### Đường dẫn hệ thống tệp mặc định

~~~java
Path p = Path.of("documents", "report.txt");
FileSystem owner = p.getFileSystem();
FileSystem defaultFs = FileSystems.getDefault();

System.out.println(owner == defaultFs); // true trên JDK thông thường
~~~

`Path.of(String, String...)` (tương tự `Paths.get(String, String...)`) sử dụng **hệ thống tệp mặc định**. `FileSystems.getDefault()` trả về hệ thống tệp mặc định của tiến trình. Đường dẫn có thể tương đối hay tuyệt đối; hai tính chất này không thay đổi hệ thống tệp sở hữu nó.

### Đường dẫn được tạo rõ ràng từ một `FileSystem`

~~~java
Path p = someFileSystem.getPath("/docs/report.txt");
FileSystem owner = p.getFileSystem();
~~~

Ở đây `p` thuộc `someFileSystem`. Việc gọi `getPath` chưa tạo ra tệp. Cú pháp `"/docs/report.txt"` được hệ thống tệp cụ thể diễn giải; không nên coi nó là đường dẫn hệ điều hành trong mọi trường hợp.

### Đường dẫn từ URI

`Path.of(URI)` lựa chọn provider qua scheme của URI. Với scheme `file`, thao tác này thường tạo đường dẫn trên hệ thống tệp mặc định. Với một URI kiểu `jar:file:...!/entry`, hệ thống tệp ZIP tương ứng thường phải được mở/đăng ký trước thì việc lấy `Path` mới thực hiện được; nếu không có provider hay hệ thống tệp thích hợp có thể phát sinh `ProviderNotFoundException` hoặc `FileSystemNotFoundException`. Cách dễ kiểm soát nhất khi đã cầm đối tượng `FileSystem` là dùng chính `fs.getPath(...)`.

**Không tự suy luận hệ thống tệp từ chuỗi `path.toString()`.** Hãy hỏi trực tiếp `path.getFileSystem()` và khi cần hỏi thêm `path.getFileSystem().provider()`.

## 3. Hai lớp quan hệ cần phân biệt

| Kiểm tra | Điều xác nhận | Điều không tự suy ra |
| --- | --- | --- |
| `a.getFileSystem() == b.getFileSystem()` | Cùng một đối tượng `FileSystem` trong tiến trình | Cùng tệp hoặc cùng vị trí |
| `a.getFileSystem().provider() == b.getFileSystem().provider()` | Cùng một đối tượng provider | Cùng hệ thống tệp |
| `a.equals(b)` | Hai đối tượng đường dẫn bằng nhau theo quy tắc của triển khai `Path` | Chắc chắn cùng tệp vật lý trong mọi tình huống |
| `Files.isSameFile(a, b)` | API thử xác định hai đường dẫn chỉ cùng một tệp đang tồn tại | Không cần truy cập I/O hay luôn có kết quả với mọi provider |

Ví dụ: hai ZIP khác nhau có thể được mở bởi **cùng ZIP provider**, nhưng mỗi ZIP tạo thành **một `FileSystem` riêng**. Mỗi hệ thống tệp đều có `/docs/guide.txt` của nó; hai đường dẫn đó độc lập. Ngược lại, hai tên khác nhau trong cùng hệ thống tệp vẫn có thể cùng chỉ vào một tệp vì symbolic link/hard link; `Path.equals` không thay thế kiểm tra danh tính tệp.

`==` ở hai hàng đầu là phép so sánh **danh tính đối tượng**. Khi cần đánh giá tính bằng nhau của đường dẫn, dùng `equals` theo ngữ nghĩa của provider; khi cần kiểm tra hai đường dẫn trỏ cùng tệp hiện hữu, cân nhắc `Files.isSameFile` và xử lý `IOException`.

## 4. Các phép biến đổi `Path` giữ nguyên hệ thống tệp

Những phép xử lý tên trên một `Path` như `getParent()`, `getFileName()`, `subpath(...)`, `normalize()`, `toAbsolutePath()` và `resolve(String)` tạo đường dẫn kết quả trong **cùng `FileSystem`** với đường dẫn ban đầu (trừ trường hợp API trả `null`, ví dụ `getParent()` của một đường dẫn không có cha).

~~~java
Path base = Path.of("data", "reports");
Path child = base.resolve("daily.txt");
Path absolute = child.toAbsolutePath().normalize();

System.out.println(base.getFileSystem() == child.getFileSystem());    // true
System.out.println(base.getFileSystem() == absolute.getFileSystem()); // true
~~~

`normalize()` chỉ đơn giản hóa các thành phần tên như `.` và `..` theo cú pháp; nó **không** xác minh tồn tại, theo dõi symbolic link hay bảo đảm hai đường dẫn truy cập cùng tệp. `toAbsolutePath()` chuyển cách biểu diễn từ tương đối sang tuyệt đối theo ngữ cảnh của hệ thống tệp đang dùng; nó không chuyển đường dẫn sang hệ thống tệp khác.

Đặc biệt, `Path.resolve(Path other)` và `Path.relativize(Path other)` cần các đường dẫn tương thích theo quy tắc triển khai. Trộn `Path` của provider khác thường dẫn đến `ProviderMismatchException`. `relativize` còn có thể ném `IllegalArgumentException` khi không thể tạo quan hệ tương đối phù hợp (chẳng hạn khác loại tuyệt đối/tương đối trên provider thông thường).

## 5. Ví dụ chạy được: hệ thống tệp mặc định và ZIP filesystem

Chương trình Java 17+ dưới đây tạo một tệp ZIP tạm thời, mở nó bằng ZIP provider có sẵn trong bản JDK thông dụng (`jdk.zipfs`), tạo tệp *bên trong ZIP* rồi so sánh nguồn gốc của các `Path`. Tên tệp ZIP ngẫu nhiên không được in ra nên stdout ổn định.

Lưu thành `PathFileSystemDemo.java`:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class PathFileSystemDemo {
    public static void main(String[] args) throws IOException {
        Path hostPath = Path.of("notes.txt");
        FileSystem defaultFs = FileSystems.getDefault();
        System.out.println("host belongs to default: "
                + (hostPath.getFileSystem() == defaultFs));

        Path archive = Files.createTempFile("path-fs-demo-", ".zip");
        // ZIP provider cần tệp ZIP mới khi dùng create=true.
        Files.delete(archive);

        try {
            URI jarUri = URI.create("jar:" + archive.toUri());
            FileSystem zipFs = FileSystems.newFileSystem(
                    jarUri, Map.of("create", "true"));

            try (zipFs) {
                Path insideZip = zipFs.getPath("/docs/hello.txt");
                Files.createDirectories(insideZip.getParent());
                Files.writeString(insideZip, "Xin chao NIO.2");

                System.out.println("zip path belongs to zipFs: "
                        + (insideZip.getFileSystem() == zipFs));
                System.out.println("same filesystem: "
                        + (hostPath.getFileSystem() == insideZip.getFileSystem()));
                System.out.println("zip content: " + Files.readString(insideZip));

                try {
                    insideZip.resolve(hostPath);
                    System.out.println("unexpected resolve success");
                } catch (ProviderMismatchException expected) {
                    System.out.println("cross-provider resolve rejected: true");
                }
            }

            System.out.println("zip filesystem open: " + zipFs.isOpen());
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên có module `jdk.zipfs`:

~~~bash
javac PathFileSystemDemo.java
java PathFileSystemDemo
~~~

Stdout:

~~~text
host belongs to default: true
zip path belongs to zipFs: true
same filesystem: false
zip content: Xin chao NIO.2
cross-provider resolve rejected: true
zip filesystem open: false
~~~

Đọc ví dụ theo thứ tự:

1. `hostPath` sinh từ `Path.of(String)` nên thuộc hệ thống tệp mặc định, dù tệp `notes.txt` **không cần tồn tại**.
2. `jarUri` trỏ đến **chính tệp ZIP trên ổ đĩa**, còn `zipFs.getPath("/docs/hello.txt")` biểu diễn **một entry bên trong ZIP**. Đây là hai tầng địa chỉ khác nhau.
3. `Files.createDirectories` và `Files.writeString` hoạt động theo provider của `insideZip`; dữ liệu được ghi thành entry ZIP, không thành thư mục `/docs` trên ổ đĩa mặc định.
4. `insideZip.resolve(hostPath)` bị từ chối vì đối số `hostPath` thuộc default provider, khác ZIP provider. Nếu chỉ cần nối *tên tương đối* trong ZIP, dùng `insideZip.getParent().resolve("another.txt")` hoặc `zipFs.getPath(...)`.
5. `try (zipFs)` đóng ZIP filesystem và hoàn tất cập nhật tệp ZIP. `zipFs.isOpen()` lúc đó là `false`; các thao tác I/O mới trên `Path` thuộc hệ thống tệp đã đóng có thể ném `ClosedFileSystemException`.
6. `finally` dọn tệp ZIP tạm. Đóng và dọn tài nguyên cần có ngay cả khi xuất hiện ngoại lệ ở giữa.

**Giới hạn của ví dụ:** bản JRE tùy biến có thể thiếu `jdk.zipfs`, khi đó không thể chạy phần ZIP provider nếu không bổ sung module. Trong JDK tiêu chuẩn, ví dụ chạy độc lập, không cần thư viện ngoài.

## 6. Khi phối hợp hai hệ thống tệp

Có hai thao tác khác nhau rất dễ bị nhầm:

**Ghép hoặc tính đường dẫn tương đối**: xử lý *tên* trong một hệ thống tệp. Hãy tạo cả hai toán hạng bằng cùng `FileSystem` nếu dùng `resolve(Path)` hoặc `relativize(Path)`; hoặc dùng chuỗi tương đối khi có ý định tạo tên con trong hệ thống tệp đích.

**Sao chép dữ liệu giữa hai hệ thống tệp**: `Files.copy(source, target, options...)` nhận một đường dẫn nguồn và một đường dẫn đích có thể thuộc các provider khác nhau. API thực hiện thao tác sao chép theo khả năng của các provider, có thể phát sinh `IOException` hoặc lỗi tùy chọn/thuộc tính không được hỗ trợ. Trường hợp từ ZIP sang ổ đĩa:

~~~java
// insideZip thuộc zipFs, destination thuộc hệ thống tệp mặc định.
// Phải chạy đoạn này khi zipFs vẫn đang mở.
Path destination = Path.of("exported-hello.txt");
Files.copy(insideZip, destination);
~~~

Đây là **đoạn mã minh họa đặt bên trong khối `try (zipFs)`** của ví dụ ở trên, không phải một chương trình độc lập. Với một chương trình chạy lại nhiều lần, nhớ quản lý việc tệp đích đã tồn tại (ví dụ dùng `StandardCopyOption.REPLACE_EXISTING` nếu thực sự muốn thay thế).

`Files.move` giữa các provider có giới hạn khác với đổi tên nội bộ: việc di chuyển có thể được thực hiện bằng sao chép rồi xóa, không mang tính nguyên tử; yêu cầu `ATOMIC_MOVE` có thể gây `AtomicMoveNotSupportedException`. Không giả định rằng mọi thao tác trên `Path` đều an toàn hoặc có cùng hiệu năng khi đi qua hệ thống tệp khác nhau.

## 7. Quy tắc phụ thuộc `FileSystem`

Ngoài ownership, `FileSystem` ảnh hưởng đến các quy tắc và khả năng sau:

- **Phân tách tên**: `fs.getSeparator()` có thể là `/` hoặc `\` tùy provider/hệ điều hành; không hardcode đường dẫn hệ điều hành cho mọi provider.
- **Root và đường dẫn tuyệt đối**: `fs.getRootDirectories()` và `path.getRoot()` được diễn giải riêng theo hệ thống tệp; một đường dẫn ZIP có gốc `/` dù ZIP chỉ là một file trên máy.
- **Path matcher**: `fs.getPathMatcher("glob:*.txt")` tạo matcher theo cú pháp và đặc tính provider; kết quả phụ thuộc quy tắc của hệ thống tệp.
- **Thuộc tính file**: `fs.supportedFileAttributeViews()` cho biết các view được hỗ trợ; các provider không nhất thiết hỗ trợ giống nhau các thuộc tính POSIX, DOS, owner hay ACL.
- **Trạng thái/truy cập**: `fs.isOpen()`, `fs.isReadOnly()` và các lời gọi `Files.*` có thể dẫn đến `ClosedFileSystemException`, `ReadOnlyFileSystemException` hoặc `IOException` trong hoàn cảnh tương ứng.

Tất cả đều là lý do để truyền `Path` hoặc `FileSystem` cho hàm thư viện thay vì chỉ truyền một chuỗi rồi tái tạo đường dẫn bằng hệ thống tệp mặc định ở lớp bên trong.

Ví dụ, hàm nhận `Path root` nên viết:

~~~java
Path output = root.resolve("output.txt");
~~~

Cách này giữ `output` trong hệ thống tệp sở hữu `root`. Nếu thay bằng `Path.of(root.toString(), "output.txt")`, đoạn code vô tình **gắn đường dẫn mới vào hệ thống tệp mặc định** và có thể gây lỗi khi `root` nằm trong ZIP hoặc provider khác.

## 8. Vòng đời `FileSystem` và xử lý lỗi

- `FileSystems.getDefault()` quản lý hệ thống tệp mặc định cho ứng dụng. **Không tự đóng** default filesystem; lời gọi `close()` trên triển khai mặc định thông dụng có thể ném `UnsupportedOperationException`.
- Hệ thống tệp mở thêm bằng `FileSystems.newFileSystem(...)` thường do code của bạn quản lý vòng đời và nên đóng bằng `try-with-resources` khi hoàn tất. Đừng trả `Path` từ ZIP filesystem ra khỏi scope rồi đóng filesystem trước khi caller truy cập dữ liệu.
- Nếu mở hai lần cùng URI của một hệ thống tệp đã đăng ký, tùy provider có thể nhận `FileSystemAlreadyExistsException`. `FileSystems.getFileSystem(uri)` tìm một hệ thống tệp đã đăng ký, nhưng sẽ có `FileSystemNotFoundException` khi chưa có.
- Khi nhận `Path` từ bên ngoài, kiểm tra bằng `path.getFileSystem()` nếu API yêu cầu một filesystem nhất định; nếu API có thể xử lý provider bất kỳ, giữ nguyên `Path` của caller, không chuyển qua `toString()` rồi `Path.of(...)`.

**Cần phân biệt ba loại lỗi:** `ProviderMismatchException` (kết hợp hai `Path` không tương thích), `FileSystemNotFoundException` (không tìm được filesystem đã được đăng ký cho URI), và `ClosedFileSystemException` (sử dụng tài nguyên của filesystem đã đóng). Chúng chỉ ra những vấn đề khác nhau nên cách khắc phục cũng khác nhau.

## 9. Câu hỏi tự kiểm tra

1. Nếu hai đường dẫn đều in ra `/config/app.yml`, có thể kết luận chúng chỉ cùng tệp không? **Không**: cần biết `FileSystem` và có thể cần kiểm tra file thực tế.
2. Vì sao `zipFs.getPath("/x.txt")` không thể thay tùy tiện bằng `Path.of("/x.txt")`? Vì cách thứ hai tạo `Path` thuộc filesystem mặc định, không phải ZIP.
3. `normalize()`, `resolve(String)` có chuyển một đường dẫn ZIP thành đường dẫn host không? **Không**: chúng giữ filesystem sở hữu.
4. Muốn đưa nội dung từ `Path` trong ZIP ra ổ đĩa, nên ghép path hay sao chép? Dùng `Files.copy` với `target` được tạo trong filesystem đích và xử lý lỗi, vòng đời tài nguyên.
5. Nên nhận `String path` hay `Path path` trong API thao tác tệp đa provider? Thường là **`Path`**, vì nó giữ cả cấu trúc tên và thông tin hệ thống tệp sở hữu.

**Ghi nhớ:** `Path` mang theo danh tính `FileSystem` đã tạo ra nó. Việc xử lý *tên đường dẫn* phải tôn trọng danh tính này; việc *chuyển dữ liệu* giữa các hệ thống tệp cần sử dụng API I/O tương ứng.
