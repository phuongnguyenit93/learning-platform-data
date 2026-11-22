# Tạo Path bằng Path.of, Paths.get và FileSystem trong Java Core I/O

> **Ngữ cảnh:** Java Core → I/O → **Path**. Bài học phân biệt ba cách tạo đối tượng `java.nio.file.Path`: `Path.of(...)`, `Paths.get(...)` và `FileSystem.getPath(...)`; giải thích default file system, file system provider, xử lý URI, đường dẫn trong ZIP, thao tác path an toàn và lựa chọn API theo phiên bản JDK. Các ví dụ hoàn chỉnh biên dịch/chạy bằng Java 17, trừ khi ghi rõ.

## 1. Path là gì? Tạo Path không đồng nghĩa tạo tệp

`Path` trong package `java.nio.file` đại diện **vị trí định danh của một đường dẫn trong một file system cụ thể**. Nó mô tả cấu trúc tên file/thư mục mà **file system provider** hiểu: tên thành phần, gốc, đường dẫn tương đối hay tuyệt đối, cách nối/chuẩn hóa và cách chuyển đổi.

Ví dụ:

~~~java
import java.nio.file.Path;

Path report = Path.of("reports", "2026", "summary.csv");
~~~

Đây là **fragment** đặt trong một method. Nó tạo một đối tượng `Path` tương đối trỏ tới vị trí logic `reports/2026/summary.csv` trên hệ thống dùng dấu phân tách `/`; trên Windows cách thể hiện khi gọi `toString()` có thể khác. **Lệnh trên không tạo directory hay file, không kiểm tra tệp tồn tại và không mở handle I/O**.

Để tương tác filesystem thực tế, mới dùng `java.nio.file.Files` như:

~~~java
// Fragment: path là Path hợp lệ; method xử lý IOException.
boolean exists = Files.exists(path);
Files.createDirectories(path.getParent());
Files.writeString(path, "Hello", StandardCharsets.UTF_8);
~~~

Fragment cần import `java.nio.file.Files` và `java.nio.charset.StandardCharsets`. **Không đánh đồng** việc tạo `Path` (thuần biểu diễn) với tạo file `Files.createFile(...)`, tạo thư mục `Files.createDirectories(...)` hoặc mở stream.

### FileSystem có vai trò gì?

Một `FileSystem` là môi trường diễn giải các `Path`. File system **mặc định** thường phản ánh hệ thống file mà JVM được chạy trên đó; một provider khác có thể đại diện cho file ZIP/JAR, filesystem ảo hoặc lưu trữ ngoài (nếu có provider thích hợp).

~~~text
String / URI
    |
    +--> Path.of("...", "...") -----------+
    |                                     |
    +--> Paths.get("...", "...") ---------+--> default FileSystem --> Path
    |                                     |
    +--> FileSystems.getDefault()
              .getPath("...", "...") -----+

    +--> FileSystem khác (ví dụ ZIP)
              .getPath("/docs/file.txt") ----> Path thuộc ZIP FileSystem

Path + Files API --> thao tác thật lên filesystem tương ứng
~~~

`Path` không tự chứa toàn bộ dữ liệu tệp; `Files` chuyển các thao tác file cho provider của path. Vì thế cùng cú pháp `getPath` nhưng đường dẫn trên disk và đường dẫn **bên trong ZIP** có thể đại diện cho hai không gian khác nhau.

## 2. Ba API tạo Path và mối quan hệ giữa chúng

| API | Từ JDK | Môi trường file system | Khi nào chọn? |
| --- | --- | --- | --- |
| `Path.of(String first, String... more)` | **Java 11** | Default FileSystem | Lựa chọn ngắn gọn cho ứng dụng Java 11+ sử dụng filesystem mặc định. |
| `Paths.get(String first, String... more)` | **Java 7** | Default FileSystem | Tương thích source với Java 7/8 và codebase cũ; vẫn hợp lệ trên JDK mới. |
| `FileSystems.getDefault().getPath(String first, String... more)` | **Java 7** | Default FileSystem được chỉ định rõ | Khi muốn thể hiện rõ provider mặc định hoặc đã có biến FileSystem. |
| `someFileSystem.getPath(String first, String... more)` | **Java 7** | FileSystem chính là `someFileSystem` | Khi xây dựng path **trong ZIP** hoặc provider tùy biến, không giả định filesystem mặc định. |
| `Path.of(URI uri)` | **Java 11** | Provider được tìm qua **scheme** của URI | Chuyển URI phù hợp (ví dụ `file:`) thành Path khi provider tồn tại. |
| `Paths.get(URI uri)` | **Java 7** | Provider theo URI | API lâu đời tương đương mục đích trên, hữu ích khi yêu cầu Java 8. |

Điểm quan trọng: `Path.of(String, String...)` và `Paths.get(String, String...)` trên Java 11+ tạo `Path` bằng **default FileSystem**; triển khai hiện đại của `Paths.get` ủy quyền cho `Path.of`. Không có cơ chế “nhanh hơn” đáng để chọn chỉ vì tên. Chọn theo **minimum JDK**, tính rõ ràng và khả năng tái sử dụng với filesystem khác.

### 2.1. `Path.of("...")`

~~~java
Path file = Path.of("data.txt");
Path nested = Path.of("input", "archive", "2026.json");
Path absolute = Path.of(System.getProperty("user.home"), "notes.txt");
~~~

Đây là fragment. `Path.of(first, more...)` yêu cầu `first` và tùy ý những chuỗi `more`; các thành phần không rỗng được ghép theo **quy tắc của default provider**. Trên Unix thường dùng dấu `/`; Windows có cú pháp drive, UNC và dấu phân tách riêng. API không yêu cầu bạn nối chuỗi thủ công bằng `"/"` hay `"\\"`.

**Một đường dẫn tuyệt đối chỉ vì có chuỗi dài chưa chắc hợp lệ trên mọi OS.** Ví dụ `Path.of("/tmp", "file.txt")` mang ngữ nghĩa gốc Unix nhưng trên Windows có thể diễn giải khác. Code cross-platform nên nhận gốc từ cấu hình, `Path` do caller truyền, hoặc API môi trường, sau đó dùng `resolve`.

### 2.2. `Paths.get("...")`

~~~java
import java.nio.file.Path;
import java.nio.file.Paths;

Path a = Paths.get("docs", "readme.md");
Path b = Path.of("docs", "readme.md"); // Chỉ có từ Java 11.
System.out.println(a.equals(b));     // true với default provider.
~~~

Nếu project phải chạy/biên dịch với Java 8, chỉ dùng `Paths.get` và không viết `Path.of`. Ngược lại, ứng dụng Java 17 có thể dùng cả hai; `Paths.get` **không bị loại bỏ** khỏi Java SE.

### 2.3. `FileSystem.getPath("...")`

~~~java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

FileSystem defaultFs = FileSystems.getDefault();
Path document = defaultFs.getPath("docs", "readme.md");
~~~

Cũng là fragment. Tác dụng quan trọng là **nguồn FileSystem có thể khác default**:

~~~java
// Fragment: zipFs là FileSystem đã mở từ ZIP provider.
Path member = zipFs.getPath("/docs", "readme.md");
~~~

Path `member` đại diện thành phần bên trong ZIP, **không phải** file `/docs/readme.md` trên ổ đĩa máy chủ. Những API như `Files.exists(member)`, `Files.readString(member)` sẽ dùng provider của ZIP filesystem đó.

**Tránh sai lầm phổ biến:** khi nhận một `Path root` do caller cung cấp, nhưng method lại gọi `Path.of("child.txt")` rồi giả định nó nằm trên cùng filesystem với `root`. `Path.of` dùng default, trong khi `root` có thể thuộc ZIP hoặc một provider khác. Nên dùng `root.resolve("child.txt")` hoặc `root.getFileSystem().getPath(...)` tùy ý nghĩa mong muốn.

## 3. Ví dụ độc lập: đối chiếu ba factory trên default file system

Tạo file **`PathFactoriesDemo.java`**:

~~~java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.Paths;

public class PathFactoriesDemo {
    public static void main(String[] args) {
        Path modern = Path.of("docs", "guide.md");
        Path legacy = Paths.get("docs", "guide.md");
        Path fromFs = FileSystems.getDefault()
                .getPath("docs", "guide.md");

        Path messy = Path.of("docs", ".", "draft", "..", "guide.md");

        System.out.println("equivalent="
                + (modern.equals(legacy) && modern.equals(fromFs)));
        System.out.println("relative=" + !modern.isAbsolute());
        System.out.println("names=" + modern.getNameCount());
        System.out.println("filename=" + modern.getFileName());
        System.out.println("parent=" + modern.getParent().getFileName());
        System.out.println("normalized=" + messy.normalize().equals(modern));
        System.out.println("uriRoundTrip="
                + Path.of(modern.toAbsolutePath().toUri())
                    .equals(modern.toAbsolutePath()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PathFactoriesDemo.java
java PathFactoriesDemo
~~~

**Stdout đã kiểm tra:**

~~~text
equivalent=true
relative=true
names=2
filename=guide.md
parent=docs
normalized=true
uriRoundTrip=true
~~~

Vì ví dụ chỉ in dữ kiện cấu trúc và so sánh boolean, không in `Path.toString()` chứa separator nền tảng, stdout được thiết kế ổn định giữa các hệ thống tệp mặc định thông thường. Đây là minh họa với đường dẫn đơn giản hợp lệ; kết quả có thể khác trong provider mặc định bất thường có quy tắc tên khác.

Giải thích:

1. Ba lời gọi cùng nhận tên `docs` và `guide.md` trên default FileSystem nên Path tương ứng bằng nhau.
2. `isAbsolute()` trả `false` với đường dẫn không có root.
3. `getNameCount()` đếm số thành phần, **không** đếm số byte, thư mục tồn tại hoặc slash. `getFileName()` lấy thành phần cuối.
4. `normalize()` loại `.` và xử lý cặp tên + `..` **về mặt từ vựng**. Nó không xác minh đường dẫn có thật.
5. `toAbsolutePath().toUri()` chuyển sang file URI; `Path.of(uri)` dựng lại Path theo provider phù hợp. Round-trip với default provider có bảo đảm theo Javadoc của `Path` trong cùng JVM theo các điều kiện nêu ở đó.

## 4. Đường dẫn tương đối và tuyệt đối

Một `Path` có thể **relative** hoặc **absolute**:

- `Path.of("data", "users.csv")`: relative; được diễn giải trong ngữ cảnh default directory khi dùng cho I/O.
- `Path.of("data", "users.csv").toAbsolutePath()`: tạo một đường dẫn tuyệt đối tương ứng theo provider, thường dựa vào thư mục làm việc của tiến trình.
- `Path.of("data", "users.csv").toRealPath()`: cố truy vấn filesystem thực để xác định real path; cần tệp tồn tại và có quyền truy cập. Mặc định nó có thể giải quyết symbolic links; tùy chọn `LinkOption.NOFOLLOW_LINKS` thay đổi cách xử lý liên kết.
- `Path.of(".").toAbsolutePath().normalize()`: thường dùng để xem thư mục làm việc dưới dạng absolute path đã đơn giản hóa về mặt từ vựng.

Không hard-code một đường dẫn tuyệt đối như `C:\data\...` hay `/home/worker/...` cho mọi OS. Giá trị `user.dir` là thuộc tính JVM thường phản ánh working directory lúc launch; đừng viết chương trình dựa vào khả năng đổi `System.setProperty("user.dir", "...")` để điều khiển mọi thao tác relative path tại runtime.

### 4.1. `toAbsolutePath()` không phải `toRealPath()`

| API | Có truy vấn tệp tồn tại? | Có loại `.` / `..`? | Giải quyết symbolic links? |
| --- | --- | --- | --- |
| `toAbsolutePath()` | Không phải kiểm tra tồn tại | Không nhất thiết loại mọi thành phần thừa | Không thực hiện symlink resolution |
| `normalize()` | Không | Có, **lexical** theo quy tắc Path | Không |
| `toAbsolutePath().normalize()` | Không | Có | Không |
| `toRealPath(...)` | Có thể thực hiện filesystem I/O và đòi đường dẫn tồn tại | Trả real/absolute path theo hợp đồng provider | Theo mặc định có thể resolve symlink; `NOFOLLOW_LINKS` đổi hành vi |

**Cảnh báo:** `normalize()` đôi khi **thay đổi đối tượng mà đường dẫn thực chỉ tới** nếu đường dẫn có symbolic links. Ví dụ một tên nằm trước `..` lại là symlink tới nơi khác; bỏ cặp từ vựng chưa chắc tương đương đi thực tế qua symlink. Không sử dụng `normalize()` như bằng chứng hoàn chỉnh rằng dữ liệu từ người dùng chỉ nằm trong thư mục được cho phép.

### 4.2. `resolve`, `resolveSibling`, `relativize`

~~~java
// Fragment: base thuộc một FileSystem cụ thể.
Path base = Path.of("app", "data");
Path child = base.resolve("users.csv");
Path sibling = child.resolveSibling("roles.csv");
Path relative = base.relativize(child);
~~~

Khi xuất text trên Unix, chúng thường được thể hiện như `app/data/users.csv`, `app/data/roles.csv` và `users.csv`. Để portable, nên so sánh thành phần hoặc Path trực tiếp, không so sánh string có dấu slash cố định.

- `base.resolve(other)` tạo path bằng cách nối `other` dưới `base` nếu `other` là đường dẫn tương đối; nếu `other` là đường dẫn tuyệt đối, kết quả phụ thuộc quy tắc `resolve` của provider (default provider thường trả lại `other`).
- `resolveSibling(name)` thay thành phần cuối bằng tên mới trong cùng thư mục cha.
- `relativize(other)` tạo đường đi tương đối từ path này đến path khác; thường cần cùng provider/FileSystem và cùng tính absolute/relative. Đừng trộn `absolute` và `relative` tùy tiện.
- Đường dẫn có dấu `..` cần tính lại và kiểm tra ngữ nghĩa, đặc biệt với input không tin cậy.

## 5. FileSystem mặc định và FileSystem bất kỳ

Lấy filesystem mặc định:

~~~java
FileSystem fs = FileSystems.getDefault();
Path data = fs.getPath("data", "input.txt");

System.out.println(data.getFileSystem() == fs); // true
~~~

Đây là fragment. `getDefault()` có thể được cấu hình thông qua default provider đặc biệt khi JVM khởi động, nhưng với phần lớn ứng dụng desktop/server, nó là hệ thống file của OS. Cách nó diễn giải absolute path, separators, case sensitivity và tên không hợp lệ là thuộc filesystem/provider cụ thể.

Một `FileSystem` còn cung cấp:

| API | Công dụng |
| --- | --- |
| `getPath(first,more)` | Tạo path thuộc chính filesystem đó. |
| `getRootDirectories()` | Liệt kê các root mà provider biết, không nhất thiết giống ổ `C:` trên mọi OS. |
| `getSeparator()` | Dấu phân tách tên theo provider; không nên hard-code slash để giả lập file system. |
| `getFileStores()` | Các file store đang được provider trình bày, thông tin có thể thay đổi theo thời gian. |
| `getPathMatcher("glob:...")` | Tạo bộ so mẫu tên path theo glob/regex hỗ trợ bởi provider. |
| `isOpen()` | Kiểm tra trạng thái filesystem có thể đóng; mặc định thường được quản lý bởi JVM. |
| `close()` | Giải phóng tài nguyên filesystem **mở riêng**; không tự ý đóng filesystem mặc định. |

**Vòng đời:** `FileSystems.getDefault()` do JVM quản lý; JavaDocs nêu default filesystem không thể đóng, gọi `close()` với nó gây `UnsupportedOperationException`. Ngược lại, `FileSystems.newFileSystem(...)` tạo filesystem riêng như ZIPFS và thường phải được đóng bằng try-with-resources để flush/giải phóng handle. Sau khi close ZIPFS, những `Path` thuộc filesystem đó không còn có thể dùng cho Files I/O như lúc còn mở.

## 6. Đường dẫn từ URI: phân biệt Path với URL

Có hai họ factory nhận `URI`:

~~~java
import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;

Path fromUri = Path.of(URI.create("file:///tmp/demo.txt")); // Java 11+.
Path oldStyle = Paths.get(URI.create("file:///tmp/demo.txt")); // Java 7+.
~~~

Ví dụ là fragment minh họa URI có scheme `file` và đường dẫn theo cú pháp thường thấy trên hệ điều hành Unix; **không phải snippet portable cho file `C:` trên Windows**. Với dữ liệu thực, ưu tiên tạo URI từ Path của chính filesystem đó bằng `path.toUri()` rồi chuyển ngược nếu cần.

Đừng viết `Path.of("https://example.com/file.txt")` để kỳ vọng tải file qua HTTP. Overload nhận **String** tạo path theo **default filesystem**, trong khi overload nhận **URI** tìm provider theo **scheme** của URI. Một scheme `https` không mặc định có FileSystemProvider cài sẵn; `Path.of(URI.create("https://..."))` thường gây `FileSystemNotFoundException` hoặc lỗi provider tương ứng, **không tải dữ liệu qua mạng**. Dùng API HTTP/URL client riêng cho truy cập mạng.

### 6.1. `Path.of(URI)` có tự tạo FileSystem mới không?

Không được giả định như vậy. Hợp đồng `Path.of(URI)` là tra cứu FileSystemProvider phù hợp với scheme và chuyển đổi URI thành Path; với scheme ngoài `file`, một provider có thể yêu cầu **FileSystem đã được mount/mở** trước đó.

Ví dụ với URI trỏ vào ZIP/JAR (dạng `jar:file:...!/entry`), thường phải mở file system tương ứng bằng `FileSystems.newFileSystem(...)`, sau đó dùng chính `zipFs.getPath(...)`. Nếu gọi `Path.of(jarUri)` khi chưa có filesystem tương ứng, có thể gặp `FileSystemNotFoundException`. Không dùng `Paths.get(URI)` như một cách “tự động mount mọi loại tệp” chung.

Các exception có thể gặp tùy factory/provider: `InvalidPathException` với string path không hợp lệ; `IllegalArgumentException` khi URI vi phạm định dạng yêu cầu; `FileSystemNotFoundException` khi filesystem chưa có; `ProviderNotFoundException` khi không có provider hỗ trợ; `SecurityException` hoặc `IOException` ở API tạo/mở filesystem. Xem tài liệu overload cụ thể vì không phải exception nào cũng được khai báo ở mọi method.

## 7. Ví dụ đầy đủ: tạo Path trong ZIP FileSystem

Một file ZIP có thể được mở như một filesystem riêng nếu runtime có ZIP provider (thường là module `jdk.zipfs` trên JDK tiêu chuẩn). `FileSystem.getPath("/docs", "readme.txt")` định danh một phần tử **bên trong archive**, không phải file cùng tên trên host.

Tạo file **`ZipPathDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipPathDemo {
    public static void main(String[] args) throws IOException {
        Path tempDir = Files.createTempDirectory("zip-path-demo-");
        Path zip = tempDir.resolve("sample.zip");

        try {
            // 'zip' chưa tồn tại; provider nhận env create=true.
            try (FileSystem zipFs =
                     FileSystems.newFileSystem(zip, Map.of("create", "true"))) {

                Path member = zipFs.getPath("/docs", "readme.txt");
                Files.createDirectories(member.getParent());
                Files.writeString(member, "Hello ZIP",
                                  StandardCharsets.UTF_8);

                System.out.println("exists=" + Files.exists(member));
                System.out.println("content="
                        + Files.readString(member, StandardCharsets.UTF_8));
                System.out.println("defaultFs="
                        + (member.getFileSystem() == FileSystems.getDefault()));
            } // close zipFs: hoàn tất và giải phóng tài nguyên ZIP.

        } finally {
            Files.deleteIfExists(zip);
            Files.deleteIfExists(tempDir);
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 ZipPathDemo.java
java ZipPathDemo
~~~

**Stdout đã kiểm tra trên JDK có ZIP provider:**

~~~text
exists=true
content=Hello ZIP
defaultFs=false
~~~

**Điểm cốt lõi:**

- `Files.createTempDirectory` tạo **thư mục thật** trên default filesystem; đây là I/O. File `sample.zip` **chưa có**, cho phép env `create=true` để provider tạo archive. Không tạo sẵn một **file ZIP rỗng chỉ bằng bytes rỗng** rồi mặc định nó là archive ZIP hợp lệ.
- `FileSystems.newFileSystem(zip, Map.of("create", "true"))` từ Java 13 mở provider thích hợp cho path của archive, với cấu hình provider-specific `create`. Tham số `Map` và tên key này thuộc ZIPFS, không phải tùy chọn chung bắt buộc của mọi provider.
- `zipFs.getPath("/docs", "readme.txt")` tạo path **trong ZIPFS**; `Files.createDirectories(member.getParent())` và `Files.writeString(member,...)` thao tác thông qua provider tương ứng.
- Khi thoát try-with-resources, `zipFs.close()` đóng filesystem; sau đó `finally` xóa archive và thư mục tạm trên default filesystem.
- Nếu JDK runtime đã bị tối giản và không chứa ZIP provider, `newFileSystem` có thể gặp `ProviderNotFoundException`. Mục tiêu của ví dụ là file system semantics; không coi ZIPFS có sẵn ở mọi runtime cắt giảm.

### 7.1. Dùng cách nào nếu cần hỗ trợ Java 8?

Overload `FileSystems.newFileSystem(Path, Map)` như trên chỉ có từ Java 13. Với Java 8/11, có thể dùng overload URI đã có từ Java 7:

~~~java
// Fragment Java 8: zipFile là Path tới vị trí ZIP archive cần mở.
// URI kiểu jar:<file-uri> được zipfs provider sử dụng.
URI uri = URI.create("jar:" + zipFile.toUri());
Map<String, String> env = new HashMap<>();
env.put("create", "true");

try (FileSystem zipFs = FileSystems.newFileSystem(uri, env)) {
    Path member = zipFs.getPath("/docs", "readme.txt");
    // Thao tác trong ZIPFS ...
}
~~~

Snippet cần import `java.net.URI`, `java.nio.file.Files`, `java.nio.file.FileSystem`, `java.nio.file.FileSystems`, `java.nio.file.Path`, `java.util.Map`, `java.util.HashMap` và nằm trong method xử lý `IOException`. Trong chương trình thật, phải quản lý archive và filesystem sau khi hoàn tất. Điều kiện provider ZIPFS vẫn áp dụng; API này không tạo provider nếu runtime không có.

## 8. Tính portable: đừng tự nối chuỗi file path

Thay vì:

~~~java
// Phản ví dụ: tự ráp dấu phân tách sẽ khóa giả định về OS/provider.
String path = base + "/" + fileName;
~~~

nên dùng:

~~~java
// base đã là Path do caller cung cấp.
Path file = base.resolve(fileName);
~~~

**Ưu điểm:** `resolve` giữ path cùng provider với `base`, diễn giải separator theo provider và không cần tự xử lý trường hợp có/không slash cuối. Nhưng `resolve` **không tự bảo đảm** `fileName` an toàn, không nhất thiết ngăn đường dẫn tuyệt đối ghi đè base và không tự tạo file.

Ví dụ riêng cho Windows: chuỗi `"C:\\data\\report.txt"` có cú pháp hợp lệ trên Windows, nhưng trên Unix dấu backslash thường được coi là ký tự tên bình thường. Tương tự, `Path.of("/var/log/app.log")` là absolute Unix, không phải thiết kế cross-platform mặc định cho Windows.

### 8.1. Không dùng `Path.toString()` như định dạng trao đổi độc lập hệ điều hành

`path.toString()` được định nghĩa theo provider và thường dùng cho **hiển thị/debug/ghi log**, không nên tự coi nó là URL chuẩn hoặc format trao đổi portable giữa Windows/Linux. Khi cần nhận dạng tài nguyên bằng URI, dùng `toUri()` trong trường hợp provider hỗ trợ và lưu ý vòng đời FileSystem liên quan. Với JSON/config chuẩn quốc tế, cần quy ước riêng separator, gốc đường dẫn và cách escape chuỗi.

Trong HTML/HTTP, `/` là delimiter của URL path, không đồng nghĩa separator của filesystem. `URLDecoder` giải mã form encoding theo ngữ nghĩa khác; không tự đưa URL path đã decode vào `Path.of(...)` rồi xem như đã sandbox an toàn.

## 9. Path được tạo không chứng minh tồn tại hoặc là tệp thường

~~~java
Path p = Path.of("notes", "todo.txt");
System.out.println(p.isAbsolute()); // false trên default FS thông thường.
// Files.exists(p) có thể false nếu chưa tạo tệp.
~~~

Chỉ tạo Path không ném `NoSuchFileException` vì tệp không tồn tại. Khi muốn thao tác thực tế, dùng `Files`:

| Mục tiêu | API | Lưu ý |
| --- | --- | --- |
| Kiểm tra tồn tại | `Files.exists(path)` | `false` cũng có thể do không xác định được trạng thái trong một số điều kiện, đừng dùng riêng nó làm khóa chống race. |
| Đọc thuộc tính | `Files.readAttributes(...)` | Có thể ném IOException, phụ thuộc provider và quyền truy cập. |
| Tạo thư mục cha | `Files.createDirectories(path.getParent())` | Kiểm tra `getParent() != null` khi path chỉ có tên file. |
| Tạo file mới, không ghi đè | `Files.createFile(path)` | Thực hiện create-if-absent theo contract; có thể `FileAlreadyExistsException`. |
| Đọc text | `Files.readString(path, UTF_8)` | Java 11+, có I/O và charset. |
| Ghi text | `Files.writeString(path, content, UTF_8)` | Java 11+, tạo/ghi file tùy options; không tự tạo cha. |
| Mở byte stream | `Files.newInputStream(path)` | Caller chịu trách nhiệm close kết quả. |
| Duyệt cây | `Files.walk(path)` | Trả lazy `Stream<Path>` cần đóng, có thể giữ resource. |
| Canonical/real | `path.toRealPath()` | Có I/O, đòi đường dẫn tồn tại, xử lý symlink theo options. |

`Files.exists` rồi `Files.createFile` vẫn có **time-of-check to time-of-use (TOCTOU)**: bên khác có thể tạo/sửa file trong khoảng giữa hai thao tác. Nếu cần thao tác atomic hoặc bảo vệ quyền, sử dụng API có contract phù hợp như `createFile` hay tùy chọn `CREATE_NEW`, không dựa vào `if (!exists)` làm điều kiện an toàn duy nhất.

## 10. Kiểm soát đường dẫn từ input người dùng

Một ví dụ phổ biến là upload file vào một thư mục cố định. Nếu tên file đến từ HTTP request, không được nối vào root rồi cho phép `..` thoát vùng lưu trữ.

Ví dụ thực hành **thuần thao tác Path, không ghi file**:

Tạo file **`PathGuardDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathGuardDemo {
    public static void main(String[] args) {
        Path root = Path.of("store").toAbsolutePath().normalize();

        Path good = root.resolve("docs")
                .resolve("note.txt").normalize();

        Path bad = root.resolve("..")
                .resolve("outside.txt").normalize();

        System.out.println("inside=" + good.startsWith(root));
        System.out.println("outside=" + bad.startsWith(root));
    }
}
~~~

~~~bash
javac --release 17 PathGuardDemo.java
java PathGuardDemo
~~~

**Stdout đã kiểm tra:**

~~~text
inside=true
outside=false
~~~

Ý nghĩa: sau khi đưa về absolute và chuẩn hóa **lexical**, `startsWith(root)` so sánh thành phần Path, đáng tin cậy hơn `someString.startsWith("/root")` vốn có thể nhầm `/rootA` với `/root`. Tuy vậy, **đây không phải giải pháp sandbox hoàn chỉnh**, đặc biệt khi filesystem có symlink hoặc các tiến trình khác có thể sửa cây thư mục.

### 10.1. Giới hạn của kiểm tra lexical

Để kiểm soát security boundary thực sự, cần xem cả:

1. **Input là path tuyệt đối hay tương đối?** Nếu yêu cầu tên file đơn, từ chối separator, `.` và `..` theo chính sách nghiệp vụ; `Path.getFileName` có thể hữu ích nhưng không tự xác thực mọi input.
2. **Có symlink trong cây không?** Đường dẫn lexical nằm trong root có thể thực tế dẫn ra ngoài nếu một thành phần là symbolic link. `toRealPath()` có thể giúp biết đích hiện thời nhưng còn race.
3. **Có race với actor khác không?** Sau khi kiểm tra nhưng trước khi open, symlink hoặc directory entry có thể thay đổi. Cần thiết kế quyền hệ điều hành, thư mục không bị sửa bởi bên không tin cậy, hoặc API như `SecureDirectoryStream` khi provider hỗ trợ.
4. **Có path thuộc filesystem/provider khác không?** `root.resolve(other)` và so sánh cross provider có thể không hoạt động như mong muốn. Giữ đường dẫn con tương ứng với đúng filesystem của root.
5. **Có quy tắc riêng trên Windows không?** Drive-relative, UNC, ký tự bị cấm, case sensitivity và normalisation behavior có thể khác Unix. Không hard-code một check string rồi cho rằng an toàn trên mọi nền tảng.

**Ghi nhớ:** `normalize()` và `startsWith()` hữu ích cho kiểm tra cấu trúc, nhưng không ngăn được symlink traversal hoặc TOCTOU nếu không có các ràng buộc thực thi bổ sung.

## 11. Kiểm tra mối quan hệ giữa các FileSystem và Path

Một `Path` không phải chỉ là một string. Nó gắn với filesystem của nó:

~~~java
Path path = Path.of("a.txt");
FileSystem owner = path.getFileSystem();
boolean defaultOwner = owner == FileSystems.getDefault();
~~~

Mã fragment trên default filesystem thường có `defaultOwner == true`. Với path trong `zipFs`, `getFileSystem() == zipFs` mới đúng.

Một số thao tác có thể báo `ProviderMismatchException` hoặc `IllegalArgumentException` khi kết hợp path khác provider, tùy API/provider (ví dụ `relativize` giữa path không tương thích). `Files.copy(sourcePath, targetPath)` hỗ trợ một số thao tác cross-provider theo hợp đồng Files, nhưng không được đánh đồng nó với phương thức nối path `resolve/relativize`.

Trong **library reusable**, Oracle Javadoc của `Path.of(String,...)` lưu ý việc giả định default FileSystem hạn chế khả năng tái sử dụng. Nếu hàm được giao một `Path base`, ưu tiên xây thêm tên tương đối qua `base.resolve(...)` thay vì gọi `Path.of(...)` cho từng bước, đặc biệt khi caller có thể truyền ZIPFS hoặc virtual FS. Với API chỉ biết nội dung tên file và cần tạo path mới, có thể nhận thêm một `FileSystem` từ caller.

## 12. Xử lý ngoại lệ khi chuyển String/URI thành Path

Tạo Path từ chuỗi thường là thao tác cấu trúc và có thể fail **ngay lập tức** nếu tên không hợp lệ theo provider:

~~~java
// Fragment: raw là String lấy từ cấu hình/user input.
try {
    Path path = Path.of(raw);
    // Chỉ đến đây mới biết chuỗi chuyển thành Path được.
    // Chưa chắc file tồn tại hoặc có quyền truy cập.
} catch (java.nio.file.InvalidPathException ex) {
    // Trả lỗi validation phù hợp, không tiết lộ path nhạy cảm vào log.
}
~~~

Các tình huống tách biệt:

- **`InvalidPathException`:** chuỗi không phải path hợp lệ theo quy tắc provider, ví dụ ký tự bị cấm hoặc cấu trúc không hợp lệ.
- **`NoSuchFileException`:** thường xuất hiện lúc thực hiện Files I/O trên tài nguyên không tồn tại, **không phải** cứ `Path.of` cho tên chưa tồn tại là ném.
- **`AccessDeniedException`/`IOException`:** quyền hoặc I/O lúc thao tác tệp/dir.
- **`FileSystemNotFoundException`/`ProviderNotFoundException`:** có thể xảy ra khi xây Path từ URI hoặc mở provider không tìm thấy file system phù hợp.
- **`ClosedFileSystemException`:** đường dẫn thuộc file system đã đóng được đem đi thực hiện những thao tác phụ thuộc provider.
- **`ProviderMismatchException`:** API/provider phát hiện path thuộc provider không tương thích.
- **`SecurityException`:** một số thao tác có thể liên quan kiểm soát quyền ở môi trường tương ứng.

**Không thay mọi trường hợp bằng `catch (Exception)` rồi cho rằng chỉ cần tạo lại Path là đủ.** Hợp đồng tạo path, đường dẫn không tồn tại và lỗi đọc/ghi là những tầng khác nhau.

## 13. Các mốc phiên bản JDK cần nhớ

| Mốc | Ý nghĩa đối với bài này |
| --- | --- |
| **Java 7** | NIO.2 ra mắt với `Path`, `Paths`, `FileSystems`, `Files`; dùng `Paths.get(...)` hoặc `fs.getPath(...)`. |
| **Java 8** | Vẫn chưa có `Path.of`. Có thể dùng `Paths.get`, `Files.lines`, `Stream` và `FileSystems.newFileSystem(URI,Map)`. |
| **Java 9** | Không phải mốc giới thiệu `Path.of`; đã có các cải tiến khác trong NIO/stream, đừng nhầm. |
| **Java 11** | Thêm `Path.of(String...)` và `Path.of(URI)`; thêm các convenience text I/O như `Files.readString`/`Files.writeString`. |
| **Java 13** | Có overload `FileSystems.newFileSystem(Path,Map)` dùng trong ví dụ ZIPFS. |
| **Java 17+** | Cả ba cách tạo Path và overload ZIPFS trong bài đều khả dụng trên JDK đầy đủ; code có thể bị hạn chế bởi môi trường/provider riêng. |

**Nếu build hỗ trợ Java 8:** thay `Path.of(...)` bằng `Paths.get(...)` cho default provider hoặc dùng `FileSystem.getPath(...)`; không dùng `Files.readString/writeString` hay `FileSystems.newFileSystem(Path,Map)`; thay các API đó bằng stream/reader và overload URI tương ứng. Dùng `javac --release 8` để kiểm tra source + API khả dụng, không chỉ đổi `-source`/`-target` rồi giả định không gọi API mới.

### API selection cheat sheet

~~~text
Java 11+ + default filesystem   → Path.of("dir", "file.txt")
Java 7/8 + default filesystem   → Paths.get("dir", "file.txt")
Đã có Path base              → base.resolve("file.txt")
Đã có FileSystem fs          → fs.getPath("dir", "file.txt")
Có URI hợp lệ + provider      → Path.of(uri) (Java 11+) / Paths.get(uri)
Cần ZIP archive filesystem  → FileSystems.newFileSystem(...), rồi zipFs.getPath(...)
~~~

Không chọn `FileSystems.getDefault().getPath(...)` chỉ vì cú pháp dài hơn trông “an toàn” hơn. Nó có ý nghĩa khi muốn truyền/chọn file system tường minh; còn Path ở default provider tạo theo ba factory chính thường tương đương.

## 14. Lỗi phổ biến và cách tránh

1. **“Tạo Path tức tạo file.”** Sai: Path mô tả vị trí; `Files.createFile`/`Files.writeString` mới thực hiện I/O.
2. **“Path.of dùng được từ Java 8.”** Sai: `Path.of` được thêm từ Java 11; Java 8 dùng `Paths.get`/`FileSystem.getPath`.
3. **“Paths.get đã bị loại bỏ.”** Sai: vẫn hợp lệ, rất hữu ích cho source cũ và compatibility.
4. **“Path.of(String) và Path.of(URI) giống nhau.”** Sai: String → default FS, URI → tìm provider theo scheme.
5. **“FileSystem.getPath luôn là default FS.”** Sai: nó thuộc chính FileSystem được gọi, chẳng hạn ZIPFS.
6. **“Path trong ZIP là đường dẫn disk thông thường.”** Sai: `Path.getFileSystem()` gắn với ZIP provider.
7. **“FileSystems.newFileSystem là resource chẳng cần close.”** Sai với file system có handle như ZIPFS; đóng đúng vòng đời.
8. **“Có thể close default FileSystem để giải phóng bộ nhớ.”** Không: default FS được quản lý bởi JVM và không thể đóng theo API.
9. **“Tôi dùng dấu / nên mọi Windows path đều tương đương Unix.”** Sai: drive, UNC, separator, chữ hoa/thường và các quy tắc provider khác nhau.
10. **“Path.toString là URL.”** Sai: nó là representation theo provider, dùng `toUri` khi cần URI phù hợp.
11. **“normalize chứng minh file tồn tại.”** Sai: lexical, không truy vấn filesystem.
12. **“normalize xong startsWith(root) là sandbox tuyệt đối.”** Sai: symlink/race vẫn có thể vượt phạm vi.
13. **“toAbsolutePath kiểm tra tệp thật.”** Sai: muốn canonical real path cần `toRealPath` với ngữ nghĩa I/O.
14. **“Files.exists rồi Files.createFile là atomic.”** Sai: có TOCTOU; ưu tiên operation có contract atomic phù hợp.
15. **“resolve với tên do user gửi luôn nằm dưới base.”** Sai: input tuyệt đối/`..` có thể làm thoát root.
16. **“Mỗi FileSystem chỉ khác dấu slash.”** Sai: provider quyết định URI, roots, thuộc tính, khả năng I/O và lifecycle.
17. **“JAR URI bất kỳ đưa vào Path.of sẽ tự mount được.”** Không đảm bảo: cần provider và có thể phải tạo/mở FileSystem trước.
18. **“Path equality tức hai path trỏ cùng file vật lý.”** Không luôn đúng: so sánh path object khác với `Files.isSameFile` có thể truy vấn filesystem, symlinks/hardlinks.
19. **“Chỉ lưu string path rồi dùng trên mọi máy.”** Có thể không portable: root, name separator, encoding, provider, quyền đều phụ thuộc môi trường.
20. **“Thư viện nhận base Path nên tạo child bằng Path.of.”** Có thể sai provider; ưu tiên `base.resolve(...)`.

## 15. Câu hỏi tự kiểm tra

1. `Path.of("hello.txt")` có tạo tệp trên disk không?
2. Điểm chung và khác nhau giữa `Paths.get("a","b")` và `Path.of("a","b")` là gì? Java 8 chọn API nào?
3. Nếu caller truyền `Path base` thuộc ZIPFS, vì sao `Path.of("child.txt")` có thể là bug?
4. `FileSystems.getDefault()` có nên được đóng bằng try-with-resources không?
5. `Path.of("logs","app.log").toAbsolutePath()` có đòi file tồn tại không? Còn `toRealPath()`?
6. `Path.of(URI.create("https://example.com/x"))` có tải dữ liệu từ mạng không? API nào khác cần dùng?
7. `Files.newFileSystem(zip, Map.of("create","true"))` trong demo tạo kiểu filesystem nào và cần dọn thế nào?
8. Tại sao `normalize()` có thể thay đổi ý nghĩa đường dẫn khi symlink tham gia?
9. Nếu `base.resolve(untrustedName)` được dùng cho upload, còn cần các kiểm tra nào ngoài `startsWith`?
10. Vì sao `Files.exists` ngay trước `Files.createFile` không loại bỏ hoàn toàn tình trạng race?
11. Nếu một path thuộc file system đã đóng, phép xử lý `Files.readString(path)` có thể ra sao?
12. Khi cần code reusable cho provider khác default, nên nhận tham số `String`, `Path` hay `FileSystem`?

**Gợi ý đáp án:**

1. Không; phải gọi Files API để tạo/ghi.
2. Đều dùng default FS cho string overload trên JDK 11+; `Path.of` xuất hiện Java 11, `Paths.get` có từ Java 7 và dùng được Java 8.
3. `Path.of` lấy default FS, còn `base.resolve` giữ provider của base.
4. Không, default FS do JVM quản lý; `close()` không được hỗ trợ.
5. `toAbsolutePath` không kiểm tra tồn tại; `toRealPath` dựa vào filesystem thật và thường cần tồn tại.
6. Không; `Path.of(URI)` cần provider cho scheme, dùng HTTP client/API mạng thích hợp.
7. ZIP filesystem, đóng `FileSystem` để commit/giải phóng handle, dọn file archive nếu chỉ là dữ liệu tạm.
8. Xóa lexical `name/..` có thể khác hành trình thực qua symlink.
9. Kiểm soát tuyệt đối/tương đối, thành phần `..`, symlink, TOCTOU, quyền, provider và atomic file creation theo threat model.
10. Hai lần gọi là hai thời điểm riêng, actor khác có thể thay đổi filesystem giữa chừng.
11. Có thể ném `ClosedFileSystemException` khi provider cần filesystem đang mở.
12. Nhận `Path base` nếu cần resolve child, hoặc `FileSystem` nếu muốn chính caller quyết định provider.

## 16. Tài liệu Java SE chính thức

- [Oracle Java SE 21 — Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `of(String...)`, `of(URI)`, `resolve`, `normalize`, `toRealPath`, thao tác name components và ghi chú provider.
- [Oracle Java SE 21 — Paths](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Paths.html): `get(String...)` và `get(URI)`, tương thích default provider.
- [Oracle Java SE 21 — FileSystem](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html): `getPath`, separators, roots, lifecycle và provider.
- [Oracle Java SE 21 — FileSystems](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): `getDefault`, `newFileSystem(URI,Map)`, `newFileSystem(Path,Map)`.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): tạo/đọc/ghi tệp, operation thực tế, `exists`, `isSameFile`, directory streams.
- [Oracle Java SE 21 — InvalidPathException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/InvalidPathException.html): lỗi chuyển path string không hợp lệ.
- [OpenJDK — ZIP File System Provider](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): bối cảnh ZIP/JAR; khi triển khai ZIPFS cần kiểm tra module/provider trên runtime.

**Ghi nhớ:** `Path.of` (Java 11+) và `Paths.get` (Java 7+) là lựa chọn tiện lợi cho **default FileSystem**; `fs.getPath` tạo đường dẫn trong **đúng FileSystem cụ thể**. Tạo `Path` không tạo tệp. Khi nhận một base Path từ caller, `base.resolve(child)` thường giúp giữ đúng provider; còn khi đường dẫn đến từ người dùng, cần kiểm soát symlink, quyền và race trước thao tác Files I/O.