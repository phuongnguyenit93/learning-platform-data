# Files.createFile, createDirectory và createDirectories trong Java

Trong Java NIO.2, lớp `java.nio.file.Files` cung cấp ba thao tác thường gặp để **tạo tài nguyên mới** trên hệ thống tệp:

- `Files.createFile(path)`: tạo **một tệp trống**.
- `Files.createDirectory(path)`: tạo **một thư mục**; các thư mục cha phải tồn tại.
- `Files.createDirectories(path)`: tạo **thư mục được chỉ định và những thư mục cha còn thiếu**; không coi việc đích đã là thư mục hợp lệ là lỗi.

Tên ba phương thức rất giống nhau nhưng khác đáng kể ở loại tài nguyên, yêu cầu về thư mục cha, việc cho phép đích đã tồn tại và mức độ nguyên tử (atomicity). Chọn sai dễ tạo ra `FileAlreadyExistsException`, `NoSuchFileException` hoặc một cây thư mục chỉ được tạo một phần.

Bài học sử dụng `Path`/`Files` trên Java 17+ và các ví dụ tạo tài nguyên trong thư mục tạm để không đụng tới dữ liệu của người dùng.

## 1. Bảng phân biệt nhanh

| API | Tài nguyên được tạo | Có tạo thư mục cha còn thiếu? | Nếu đích đã tồn tại? | Dữ liệu ban đầu |
|---|---|---|---|---|
| `Files.createFile(path)` | Tệp thông thường | **Không** | Thất bại; thường là `FileAlreadyExistsException` | Tệp rỗng, kích thước 0 byte |
| `Files.createDirectory(path)` | Một thư mục | **Không** | Thất bại; thường là `FileAlreadyExistsException` | Thư mục mới rỗng |
| `Files.createDirectories(path)` | Một hoặc nhiều thư mục còn thiếu | **Có** | Thành công nếu đích đã là một thư mục phù hợp; thất bại nếu đích là tệp không phải thư mục | Các thư mục mới rỗng |

Cả ba phương thức đều trả về đối tượng `Path` tương ứng với đường dẫn đã truyền, giúp dùng tiếp trong chương trình. Các phương thức đều có thể ném `IOException` hoặc những ngoại lệ con tùy điều kiện thực tế.

**Quan trọng:** `createFile` không tạo nội dung văn bản, không ghi header, không mở sẵn một `OutputStream` cho người gọi. Nếu muốn ghi dữ liệu ngay khi tạo, có thể dùng `Files.writeString`/`Files.newOutputStream` với các `StandardOpenOption` phù hợp.

## 2. Path chỉ mô tả vị trí; Files mới tương tác với đĩa

`Path` là đối tượng biểu diễn đường dẫn. Chỉ tạo `Path` không tạo tệp/thư mục thật:

~~~java
// Mảnh mã minh họa; cần import java.nio.file.Path.
Path file = Path.of("data", "report.txt");
// Chưa có thao tác tạo file nào xảy ra ở đây.
~~~

Khi gọi `Files.createFile(file)`, Java mới yêu cầu file system tạo tài nguyên tương ứng. Đường dẫn có thể là:

- **Tương đối:** `Path.of("data", "report.txt")`, được diễn giải theo thư mục làm việc hoặc ngữ cảnh provider.
- **Tuyệt đối:** ví dụ `Path.of("data").toAbsolutePath().resolve("report.txt")`.
- **Đường dẫn từ provider khác:** ZIP file system, virtual file system hoặc file system tùy biến. Chúng có thể áp quy tắc khác về quyền, root, tên, khả năng hỗ trợ thuộc tính và thông báo lỗi.

Không tự nối `"/"` hoặc `"\\"` để tạo đường dẫn đa nền tảng. `Path.of("a", "b", "c")` và `resolve(...)` biểu diễn các thành phần theo provider tương ứng.

## 3. Files.createFile: chỉ tạo đúng một tệp trống

Chữ ký thông dụng:

~~~java
public static Path createFile(
        Path path, FileAttribute<?>... attrs) throws IOException
~~~

`attrs` là tham số tùy chọn để gán thuộc tính khi tạo, ví dụ quyền truy cập trên hệ thống hỗ trợ POSIX. Nếu chưa cần cấu hình thuộc tính, chỉ gọi `Files.createFile(path)`.

Ví dụ:

~~~java
// Mảnh mã minh họa; thư mục logs phải tồn tại trước.
Path file = Path.of("logs", "app.log");
Files.createFile(file);
~~~

### Hành vi cần ghi nhớ

1. Tạo **một tệp mới, trống**, tại đúng `path`; không tạo thư mục cha `logs` nếu nó chưa có.
2. Thao tác kiểm tra tên chưa tồn tại và tạo tệp được thực hiện **nguyên tử đối với các thao tác file system khác có tác động lên cùng thư mục** theo hợp đồng `Files.createFile`. Điều này giúp tránh kiểu race “kiểm tra `exists` trước, rồi mới create”.
3. Nếu tên đích đã được dùng bởi tệp hoặc thư mục, thao tác thất bại. `FileAlreadyExistsException` là loại lỗi thường gặp và là ngoại lệ cụ thể có thể được provider sử dụng.
4. Nếu thư mục cha không có hoặc không phải thư mục hợp lệ, thao tác thất bại; thường gặp `NoSuchFileException` hoặc ngoại lệ I/O khác tùy file system.
5. Không tự tạo thư mục cha, không ghi byte vào file, không mở luồng ghi trả về cho người gọi.
6. Tệp tồn tại trên đĩa sau khi phương thức trả về thành công; muốn xóa cần thao tác riêng (`Files.delete` hoặc `Files.deleteIfExists`).

Hãy phân biệt **tạo tệp** với **mở tệp để ghi**:

~~~java
// Mảnh mã minh họa: file là Path đã xác định.
Files.createFile(file);        // Tạo tệp rỗng; lỗi nếu đã tồn tại.
Files.writeString(file, "Hi"); // Ghi dữ liệu với các open option mặc định.
~~~

Hai thao tác riêng có thể bị tác nhân khác can thiệp giữa chúng. Nếu nghiệp vụ là **tạo mới và ghi ngay, không cho ghi đè**, cân nhắc mở tệp trực tiếp với `StandardOpenOption.CREATE_NEW` thay vì tạo trước rồi mới mở.

## 4. Files.createDirectory: tạo một cấp, cha bắt buộc đã tồn tại

Chữ ký tương tự:

~~~java
public static Path createDirectory(
        Path dir, FileAttribute<?>... attrs) throws IOException
~~~

Ví dụ:

~~~java
// Mảnh mã minh họa; thư mục work phải tồn tại.
Files.createDirectory(Path.of("work", "reports"));
~~~

Nếu `work` tồn tại và cho phép tạo con, phương thức tạo đúng thư mục `reports`. Nếu `work` chưa tồn tại, `createDirectory` không âm thầm sinh ra `work`: thao tác sẽ thất bại.

Ví dụ với nhiều cấp:

~~~text
workspace/
    (chưa có thư mục 'images')
~~~

Gọi:

~~~java
Files.createDirectory(Path.of("workspace", "images", "icons"));
~~~

sẽ thất bại khi `workspace/images` chưa tồn tại. `createDirectory` chỉ tạo cấp cuối cùng; nó không có cơ chế sinh toàn bộ chuỗi thư mục cha.

Nếu đích đã tồn tại, kể cả khi chính nó là một thư mục hợp lệ, `createDirectory` vẫn không coi đây là yêu cầu “đảm bảo thư mục có mặt”. Nó cần tạo thư mục **mới** và thường ném `FileAlreadyExistsException` khi không tạo được vì trùng tên.

## 5. Files.createDirectories: tạo cả các thư mục cha còn thiếu

`Files.createDirectories(dir)` là lựa chọn khi cần bảo đảm tồn tại một cây thư mục theo đường dẫn, chẳng hạn `data/2026/reports`:

~~~java
// Mảnh mã minh họa:
Path reports = Path.of("data", "2026", "reports");
Files.createDirectories(reports);
~~~

Nếu `data` và `data/2026` còn thiếu, phương thức lần lượt tạo những thư mục cần thiết; nếu một hoặc nhiều cấp đã tồn tại dưới dạng thư mục, chúng có thể được tái sử dụng.

### Điểm khác quan trọng với createDirectory

- Nếu thư mục đích **đã tồn tại và là thư mục hợp lệ**, `createDirectories` thường hoàn thành bình thường, không buộc báo lỗi.
- Nếu một thành phần cần dùng làm thư mục **thực chất là một tệp thường**, không thể tạo thư mục con xuyên qua nó; phương thức thất bại.
- Nếu không đủ quyền, đường dẫn không hợp lệ, thiết bị lưu trữ lỗi hoặc gặp provider không hỗ trợ thao tác, vẫn có thể ném ngoại lệ.
- **Không nguyên tử đối với toàn bộ cây**: nếu đang tạo nhiều cấp và thất bại ở một cấp sau, **một số thư mục cha có thể đã được tạo**. Không có rollback tự động xóa những cấp đã thành công.

Vì vậy `createDirectories` phù hợp để chuẩn bị cấu trúc thư mục thông thường, nhưng không phải “transaction” bảo đảm tất cả-or-không-gì-cả. Nếu cần dọn dẹp sau lỗi, phải xác định rõ thư mục nào do chính lần chạy tạo và liệu còn tác vụ khác đang dùng chúng.

## 6. Ví dụ chạy được: cả ba phương thức

Tạo file **`CreatePathsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreatePathsDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-demo-");
        Path reports = root.resolve("reports");
        Path nested = root.resolve("data").resolve("2026").resolve("exports");
        Path report = reports.resolve("summary.txt");

        try {
            Files.createDirectory(reports);
            System.out.println("reportsDir=" + Files.isDirectory(reports));

            Files.createDirectories(nested);
            System.out.println("nestedDir=" + Files.isDirectory(nested));

            Files.createFile(report);
            System.out.println("fileExists=" + Files.isRegularFile(report));
            System.out.println("fileSize=" + Files.size(report));

            // Đích đã là thư mục: không phải lỗi với createDirectories.
            Files.createDirectories(nested);
            System.out.println("nestedAgain=" + Files.isDirectory(nested));

            try {
                Files.createFile(report);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("duplicateFile=FileAlreadyExistsException");
            }
        } finally {
            Files.deleteIfExists(report);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(nested.getParent());
            Files.deleteIfExists(nested.getParent().getParent());
            Files.deleteIfExists(reports);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 CreatePathsDemo.java
java CreatePathsDemo
~~~

Stdout trên hệ thống tệp mặc định thông dụng:

~~~text
reportsDir=true
nestedDir=true
fileExists=true
fileSize=0
nestedAgain=true
duplicateFile=FileAlreadyExistsException
~~~

Giải thích:

1. `Files.createTempDirectory(...)` tạo thư mục tạm có tên duy nhất; chương trình không đoán một đường dẫn cố định có thể đã tồn tại.
2. `createDirectory(reports)` tạo một cấp `reports` vì cha `root` đã có.
3. `createDirectories(nested)` tạo ba cấp `data/2026/exports` nếu cần.
4. `createFile(report)` tạo tệp `summary.txt` với kích thước ban đầu 0 byte.
5. Gọi `createDirectories(nested)` lần thứ hai vẫn được vì `nested` đang là thư mục.
6. Gọi `createFile(report)` lần thứ hai không được vì tên tệp đã tồn tại; trên default file system lỗi cụ thể là `FileAlreadyExistsException`.
7. `finally` xóa tệp trước, rồi lần lượt xóa các thư mục từ sâu lên nông. `Files.deleteIfExists` **không xóa đệ quy** một thư mục không rỗng; các bước chủ ý được viết theo thứ tự thích hợp.

Nếu chương trình có tác nhân khác đồng thời sửa vùng tạm hoặc thiếu quyền hệ thống, mọi ví dụ thao tác tệp đều có thể thất bại vì lý do I/O; stdout ở đây dành cho môi trường chạy được với file system bình thường.

## 7. Ví dụ đối chiếu: thư mục cha thiếu và tên đích đã tồn tại

Giả sử `root` là một thư mục hiện có. Phương thức `createFile(root/missing/a.txt)` không thể tự tạo `missing`, và `createDirectory(root/missing/leaf)` cũng không thể tự tạo `missing`.

Tạo file **`CreateFailuresDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.NoSuchFileException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateFailuresDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-errors-");
        Path missing = root.resolve("missing");
        Path file = root.resolve("marker.txt");

        try {
            try {
                Files.createFile(missing.resolve("a.txt"));
            } catch (NoSuchFileException ex) {
                System.out.println("createFile: missing parent");
            }

            try {
                Files.createDirectory(missing.resolve("leaf"));
            } catch (NoSuchFileException ex) {
                System.out.println("createDirectory: missing parent");
            }

            Files.createDirectories(missing.resolve("leaf"));
            System.out.println("createDirectories: nested exists="
                    + Files.isDirectory(missing.resolve("leaf")));

            Files.createFile(file);
            try {
                Files.createDirectory(file);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("createDirectory: target exists");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(missing.resolve("leaf"));
            Files.deleteIfExists(missing);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreateFailuresDemo.java
java CreateFailuresDemo
~~~

Stdout với default file system Unix/Windows:

~~~text
createFile: missing parent
createDirectory: missing parent
createDirectories: nested exists=true
createDirectory: target exists
~~~

Đây là minh họa các ngoại lệ chuyên biệt phổ biến; **hợp đồng của một số ngoại lệ cụ thể được Javadoc ghi là tùy chọn theo triển khai**. Trong ứng dụng hỗ trợ nhiều provider, vẫn cần xử lý `IOException` khi không nhận đúng subclass mong đợi.

Không viết logic dựa duy nhất vào thông báo ngoại lệ (message) vì nội dung có thể tùy OS/ngôn ngữ/triển khai; ưu tiên loại ngoại lệ, trạng thái ứng dụng và thao tác đã yêu cầu.

## 8. Thao tác nguyên tử và lỗi race: “check rồi create” không an toàn

Mẫu code có vấn đề:

~~~java
// Mảnh mã minh họa; không an toàn trước cạnh tranh đồng thời.
if (Files.notExists(file)) {
    Files.createFile(file);
}
~~~

Giữa `Files.notExists(file)` và `Files.createFile(file)`, một thread/process khác có thể tạo chính tệp đó. `Files.notExists` chỉ phản ánh quan sát tại thời điểm kiểm tra; hơn nữa, `exists/notExists` không phải hai phép phủ định hoàn hảo trong trường hợp không thể xác minh sự tồn tại.

Nếu mục tiêu là “tạo tệp mới, không bao giờ ghi đè dữ liệu hiện có”, gọi trực tiếp `Files.createFile(file)` rồi xử lý ngoại lệ thích hợp. Theo hợp đồng, hành động kiểm tra tên và tạo tệp của `createFile` là nguyên tử đối với thao tác file system khác ảnh hưởng đến thư mục.

Tương tự, `Files.createDirectory(dir)` yêu cầu tạo **một thư mục mới**, không dùng mẫu “nếu không tồn tại thì tạo” để suy ra chắc chắn sẽ thành công. Nếu chấp nhận “thư mục đã tồn tại” là trạng thái hợp lệ, `Files.createDirectories(dir)` thường đúng ý định hơn.

Tuy nhiên, nguyên tử của **tạo một đối tượng** không phải nguyên tử của **một chuỗi nhiều đối tượng**. `createDirectories(a/b/c)` có thể để lại `a` hoặc `a/b` sau khi lỗi tại cấp sâu hơn. Khi cleanup, không được xóa bừa thư mục mà thread/process khác đã tạo hoặc đang dùng.

## 9. Muốn vừa tạo file vừa ghi nội dung: dùng CREATE_NEW

Nếu cần ghi byte/text vào một file **chỉ khi file chưa tồn tại**, có thể yêu cầu API mở/ghi dùng `StandardOpenOption.CREATE_NEW`. Nó gộp chính sách tạo mới với thao tác mở trong một quy trình, tránh hai lời gọi `createFile` rồi `writeString` có khoảng trống race.

Tạo file **`CreateAndWriteDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CreateAndWriteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("fresh-write-");
        Path file = root.resolve("result.txt");

        try {
            Files.writeString(
                    file,
                    "Hello\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            System.out.println("content="
                    + Files.readString(file, StandardCharsets.UTF_8).strip());

            try {
                Files.writeString(
                        file,
                        "Overwrite?",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("secondWrite=refused");
            }
            System.out.println("unchanged="
                    + Files.readString(file, StandardCharsets.UTF_8)
                            .equals("Hello\n"));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreateAndWriteDemo.java
java CreateAndWriteDemo
~~~

Stdout:

~~~text
content=Hello
secondWrite=refused
unchanged=true
~~~

Kết quả minh họa:

- Lần ghi đầu tạo tệp với nội dung UTF-8. `CREATE_NEW` yêu cầu tạo mới và không cho dùng một file đã tồn tại làm đích.
- Lần ghi thứ hai bị từ chối, nên dữ liệu `Hello\n` vẫn nguyên vẹn.
- `WRITE` diễn đạt mục đích ghi. Khi ghi text bằng `Files.writeString`, phải chọn charset tường minh theo định dạng cần lưu (ở đây là UTF-8).
- Nếu chỉ dùng `Files.writeString(file, text)` mà không chọn options, API mặc định có thể tạo tệp chưa tồn tại nhưng **truncate** tệp đã có. Nó **không** mang ý nghĩa “chỉ tạo mới”.
- Cần thư mục cha có sẵn. Nếu cha chưa có, hãy tạo cấu trúc thư mục bằng `createDirectories(parent)` với đúng chính sách trước khi ghi.

Một lựa chọn khác là `Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)` rồi ghi byte theo khối khi dữ liệu lớn, nhưng phải đóng stream bằng `try-with-resources`.

## 10. Thuộc tính ban đầu và quyền truy cập

Cả ba phương thức tạo tệp/thư mục có tham số biến đổi `FileAttribute<?>... attrs`. Mục tiêu là đặt những thuộc tính hỗ trợ **ngay khi tạo**, tránh có một khoảng thời gian tài nguyên đã tồn tại với quyền mặc định không mong muốn.

Ví dụ trên file system hỗ trợ POSIX:

~~~java
// Mảnh mã minh họa; chỉ dùng khi file system hỗ trợ POSIX.
import java.nio.file.attribute.PosixFilePermissions;
import java.nio.file.attribute.FileAttribute;

FileAttribute<?> privateDir =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rwx------"));
Files.createDirectory(path, privateDir);
~~~

Đoạn trên **không phải một chương trình Java hoàn chỉnh**: `import` phải được đặt đầu file, và biến `path` phải được khai báo. Mục đích là cho thấy tạo một thư mục với bộ quyền POSIX `rwx------` (chỉ chủ sở hữu được đọc/ghi/truy cập theo ý nghĩa POSIX). Trên Windows/default provider không hỗ trợ view POSIX, cách này có thể không phù hợp hoặc ném `UnsupportedOperationException`; không suy diễn rằng mọi provider đều dùng quyền POSIX.

Với `createDirectories(path, attrs)`, thuộc tính được đưa vào các lần tạo thư mục theo hợp đồng API, nhưng tập thuộc tính được hỗ trợ và quyền hiệu lực còn chịu tác động của provider, ACL, umask và quy tắc hệ điều hành. **Hãy xác minh quyền thực tế nếu ứng dụng xử lý dữ liệu nhạy cảm.**

Mặt khác, nếu tài nguyên **đã tồn tại**, `createDirectories` không phải API cập nhật quyền của thư mục cũ. Muốn đổi quyền phải dùng API thuộc tính khác với kiểm soát quyền phù hợp.

## 11. Đường dẫn đã tồn tại và symbolic link

Khi kiểm tra trạng thái, phân biệt:

- **Tệp thường** tại đích: `createFile`/`createDirectory` không thể tạo thêm đối tượng mới cùng tên; `createDirectories` không thể coi tệp là thư mục.
- **Thư mục đã tồn tại**: `createDirectories` có thể thành công mà không tạo lại; `createDirectory` yêu cầu mới nên thất bại.
- **Symbolic link**: đường dẫn có thể là link trỏ đến tệp hoặc thư mục khác. Các phép kiểm tra như `Files.isDirectory(path)` mặc định có thể **đi theo link**; chính sách follow link cần được xác định theo nghiệp vụ và API.
- **Broken symbolic link**: đường dẫn link tồn tại ở mức tên, nhưng đích của link có thể không có. Không đánh đồng với một chỗ trống an toàn để tạo file mới.

Nếu chương trình xử lý path do người dùng không đáng tin cung cấp, đừng dùng một chuỗi `exists`/`normalize`/`createDirectories` rồi mặc nhiên kết luận an toàn. Có rủi ro **TOCTOU** (kiểm tra rồi sử dụng sau), symbolic link thay đổi giữa các thao tác, hoặc thư mục cha trỏ ra ngoài vùng cho phép.

Ví dụ một ứng dụng chỉ được phép ghi trong `workspace` cần có chính sách rõ ràng về đường dẫn tuyệt đối, `..`, symlink, quyền, đối tượng đã tồn tại và thời điểm mở tệp. Phép kiểm tra lexical `candidate.normalize().startsWith(base)` hữu ích nhưng **không đủ một mình** để bảo vệ hệ thống tệp chống đối tượng cạnh tranh thay đổi symlink.

## 12. Xử lý ngoại lệ và chính sách retry

Các ngoại lệ thường gặp:

| Ngoại lệ/tình huống | Nguồn nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `FileAlreadyExistsException` | `createFile`/`createDirectory` bị trùng tên | Từ chối hoặc chọn tên khác; đừng tự ghi đè |
| `NoSuchFileException` | Thiếu thư mục cha hoặc thành phần đường dẫn | Xác minh cha; dùng `createDirectories` nếu nghiệp vụ cho phép |
| `AccessDeniedException` | Thiếu quyền đọc/ghi/tạo tại vị trí | Điều chỉnh quyền hoặc báo lỗi; không retry vô hạn |
| `SecurityException` | SecurityManager hoặc chính sách bảo mật triển khai có thể từ chối | Xử lý theo chính sách quyền của ứng dụng |
| `UnsupportedOperationException` | Provider không hỗ trợ thuộc tính yêu cầu khi tạo | Chọn tập thuộc tính tương thích hoặc xử lý riêng theo platform |
| `IOException` khác | Không đủ dung lượng, đích không phải thư mục, I/O failure, race, tài nguyên bị thay đổi | Ghi log đúng ngữ cảnh, không giả định chỉ có một nguyên nhân |

Các subclass cụ thể đôi khi là **optional specific exception** trong Javadoc, vì thế khi cần hỗ trợ provider bất kỳ, phải có nhánh xử lý `IOException` chung. Không xử lý lỗi bằng cách bắt hết rồi bỏ qua hoặc tạo một cây thư mục bất kể mục đích ban đầu.

Đặc biệt với `createDirectories`: khi có lỗi ở giữa, một số cấp có thể tồn tại. Khi retry, phương thức thường tiếp tục được nếu các cấp đó là thư mục phù hợp. Nhưng nếu đã có tệp không phải thư mục ở một cấp hoặc trạng thái file system biến đổi, retry có thể vẫn thất bại. Vì thế **retry phải có lý do, giới hạn và chiến lược cleanup/rollback phù hợp**.

## 13. Những nhầm lẫn phổ biến

1. **Nhầm `Path.of(...)` với thao tác tạo tệp:** `Path.of` chỉ biểu diễn đường dẫn, không đụng tới file system.
2. **Dùng `createFile` rồi mong nó tự sinh thư mục cha:** không có; tạo cha riêng nếu được phép.
3. **Dùng `createDirectory` để tạo `a/b/c` khi `a/b` chưa tồn tại:** phải dùng `createDirectories` hoặc tạo từng cấp.
4. **Cho rằng `createDirectories` chỉ tạo khi đích không có và luôn báo lỗi nếu gọi lần hai:** nếu đích vẫn là thư mục, lời gọi lặp có thể thành công.
5. **Cho rằng `createDirectories` là transaction:** không có rollback toàn bộ khi một cấp tạo thất bại.
6. **Kiểm tra `Files.notExists` trước rồi tin rằng không còn race:** trạng thái có thể đổi giữa hai lời gọi.
7. **Dùng `createFile` để mở ghi vào tệp đã tồn tại:** thao tác tạo mới không dùng để overwrite hoặc append. Phải chọn API ghi cùng `OpenOption` đúng chính sách.
8. **Dùng `Files.writeString(path, text)` nhưng tưởng nó từ chối overwrite:** mặc định có thể truncate; dùng `CREATE_NEW` khi cần không ghi đè.
9. **Bắt `FileAlreadyExistsException` rồi giả định đích chắc chắn là thư mục:** có thể đích là tệp, symlink hoặc loại đối tượng khác; cần xác minh đúng chính sách.
10. **Chọn quyền POSIX cho mọi hệ điều hành:** provider có thể không hỗ trợ; cần kiểm tra khả năng và cơ chế permission/ACL.
11. **Dùng `deleteIfExists(dir)` với thư mục còn chứa con:** đây không phải xóa cây đệ quy.
12. **Cho rằng mã kiểm tra lexical của path đã chống mọi symbolic link:** bảo vệ file system thực tế cần thiết kế kiểm tra và mở an toàn theo hoàn cảnh.

## 14. Cách lựa chọn nhanh theo yêu cầu

**Tạo tệp mới nhưng không ghi nội dung:** chọn `Files.createFile(path)`. Nếu có file từ trước, trả lỗi rõ ràng; không âm thầm xóa.

**Tạo đúng một thư mục mới bên trong cha đã có:** chọn `Files.createDirectory(dir)`. Nếu đích đã có và nghiệp vụ coi đó là lỗi, giữ nguyên ngoại lệ.

**Chuẩn bị đường dẫn thư mục nhiều cấp hoặc bảo đảm thư mục hiện có:** chọn `Files.createDirectories(dir)`. Nhưng nhớ trường hợp file nằm ở một cấp là lỗi, và tạo nhiều cấp có thể thành công một phần.

**Tạo tệp mới rồi ghi luôn với chính sách chống ghi đè:** chọn `Files.writeString(..., CREATE_NEW, WRITE)` hoặc `newOutputStream(..., CREATE_NEW, WRITE)`. Đây thường rõ nghĩa và giảm khoảng trống race hơn hai thao tác tạo + mở ghi riêng.

**Tạo dữ liệu tạm:** chọn `Files.createTempFile(...)` cho file hoặc `Files.createTempDirectory(...)` cho thư mục. Các API tạm tự chọn tên để giảm nguy cơ đụng tên, nhưng ứng dụng vẫn phải đóng tài nguyên và dọn khi phù hợp.

**Ứng dụng có nhiều tiến trình hoặc dữ liệu nhạy cảm:** xác định permission, owner, symlink, lifecycle và xử lý TOCTOU; ba phương thức tạo này không thay thế một cơ chế giao dịch hay phân quyền tệp đầy đủ.

## 15. Ghi nhớ cốt lõi

- `createFile` **tạo đúng một tệp trống** và **không tạo cha**.
- `createDirectory` **tạo đúng một thư mục mới**, đòi hỏi cha đã tồn tại.
- `createDirectories` **tạo các thư mục còn thiếu theo chuỗi**, chấp nhận thư mục đích đã tồn tại nhưng **không nguyên tử cho toàn bộ chuỗi**.
- Khi tên file đã có, đừng tự kiểm tra rồi ghi đè; sử dụng cơ chế tạo mới/ngăn ghi đè phù hợp như `CREATE_NEW`.
- File system có thể từ chối vì thiếu quyền, xung đột loại tài nguyên, symlink và I/O; xử lý lỗi cụ thể khi có thể nhưng luôn hiểu nguồn ngoại lệ.
- Với ví dụ hoặc test, tạo thư mục tạm, thao tác trong đó và cleanup từ dưới lên; với dữ liệu thật, không xóa ngoài phạm vi sở hữu.

### Tài liệu tham khảo

- [Java 17 — Files.createFile/createDirectory/createDirectories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [Java 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Java 17 — FileAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttribute.html)
