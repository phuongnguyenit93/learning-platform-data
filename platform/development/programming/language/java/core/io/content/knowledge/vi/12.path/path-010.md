# Path không bảo đảm đích đang tồn tại trong Java NIO

`java.nio.file.Path` mô tả **vị trí/đường dẫn của một mục trên hệ thống tập tin**, chứ không phải một file hoặc thư mục đã được mở và xác nhận tồn tại. Chương trình có thể tạo một `Path` tới đường dẫn chưa có file, đã bị xóa, không được phép truy cập, hoặc tới một file sẽ được tạo trong tương lai:

~~~java
Path file = Path.of("data", "today.txt");
~~~

Câu lệnh này chỉ tạo **đối tượng đường dẫn**. Nó không tạo `today.txt`, không kiểm tra quyền truy cập và không đảm bảo mục ở đích thực sự tồn tại. Đây là nguyên tắc cốt lõi cần nắm trước khi dùng `Files.exists`, `Files.readString`, `Files.createFile`, `Path.toRealPath` hoặc các phương thức tương tự.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **Path là tên/vị trí** với **file-system entry** là đối tượng thực tế được truy cập.
- Giải thích các phương thức `Path.of`, `resolve`, `getFileName`, `getParent`, `normalize`, `toAbsolutePath` hoạt động thế nào mà không bảo đảm đích tồn tại.
- Sử dụng `Files.exists` và `Files.notExists` mà không nhầm `false` với kết luận chắc chắn.
- Biết lúc nào cần `Path.toRealPath` hoặc `Files.readAttributes`, và giới hạn của một lần kiểm tra thành công.
- Thực hiện trực tiếp các thao tác `Files.readString`, `Files.newInputStream`, `Files.createFile`, `Files.createDirectories`... rồi xử lý `IOException` phù hợp.
- Nhận diện vấn đề **TOCTOU** (*time of check to time of use*), symbolic link, thay đổi đồng thời, đường dẫn không hợp lệ và khác biệt giữa file system providers.
- Viết bài kiểm thử không phụ thuộc đường dẫn có sẵn trên máy người học.

## 2. `Path` là abstraction cho đường dẫn, không phải file handle

`Path` là một **interface** thuộc `java.nio.file`, biểu diễn đường dẫn do một `FileSystem` cụ thể quản lý. Đường dẫn có thể tương đối hoặc tuyệt đối, có nhiều name component và có thể được kết hợp, chuẩn hóa hoặc so sánh.

Ví dụ:

~~~java
import java.nio.file.Path;

Path a = Path.of("reports", "2026.txt");
Path b = a.getParent();           // reports
Path c = b.resolve("draft.txt");  // reports/draft.txt
Path d = a.toAbsolutePath();
Path e = a.normalize();
~~~

Đây là **mảnh mã** (đặt trong một phương thức hoặc khối Java). Việc chạy thành công những lời gọi này **không hề chứng minh** file `reports/2026.txt`, thư mục `reports` hoặc `draft.txt` tồn tại.

Hãy xem hai tầng khác nhau:

~~~text
Tầng biểu diễn đường dẫn:
Path.of / resolve / getParent / normalize / toAbsolutePath
              |
              | tạo và biến đổi đường dẫn
              v
       Path object trong JVM
              |
              | truyền cho thao tác thực tế
              v
Tầng truy cập file system:
Files.readString / Files.newInputStream / Files.createFile /
Files.readAttributes / Path.toRealPath / Files.delete / ...
              |
              v
  Thao tác với mục tồn tại hoặc thất bại có nguyên nhân
~~~

Điểm tách này giúp chương trình có thể lập kế hoạch đường dẫn trước khi tạo file, ví dụ tạo `Path` cho file báo cáo tháng tới, hoặc tính tên đích trước khi thực hiện `Files.move`.

Một **`Path` hợp lệ về mặt cú pháp** và một **mục file system đang tồn tại** là hai khái niệm độc lập. Ngược lại, ngay cả khi file thực tế tồn tại thì đối tượng `Path` cũng không tự giữ cho file ấy tồn tại: tiến trình khác có thể xóa hoặc thay thế mục đó sau thời điểm bạn tạo `Path`.

## 3. Ví dụ Java 17+: tạo Path tới file chưa có hoàn toàn hợp lệ

Tạo file **`PathExistenceDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PathExistenceDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("path-existence-");
        Path target = root.resolve("notes.txt");

        try {
            System.out.println("pathCreated=" + (target != null));
            System.out.println("fileName=" + target.getFileName());
            System.out.println("existsBefore=" + Files.exists(target));
            System.out.println("notExistsBefore=" + Files.notExists(target));

            try {
                Files.readString(target, StandardCharsets.UTF_8);
                System.out.println("unexpected read success");
            } catch (NoSuchFileException exception) {
                System.out.println("readBefore=NoSuchFileException");
            }

            Files.writeString(
                    target,
                    "Java NIO",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );

            System.out.println("existsAfter=" + Files.exists(target));
            System.out.println(
                    "content=" + Files.readString(target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy Java 17+:

~~~bash
javac -encoding UTF-8 PathExistenceDemo.java
java PathExistenceDemo
~~~

**Stdout trong môi trường file system thông thường, khi không có tiến trình ngoài can thiệp vào thư mục tạm:**

~~~text
pathCreated=true
fileName=notes.txt
existsBefore=false
notExistsBefore=true
readBefore=NoSuchFileException
existsAfter=true
content=Java NIO
~~~

### Diễn giải từng bước

1. `Files.createTempDirectory` thực sự tạo **thư mục tạm**; tên riêng của nó do Java chọn nên không đưa vào stdout.
2. `root.resolve("notes.txt")` chỉ tạo `Path` cho file con. File đó **chưa được tạo**.
3. `target != null` chỉ xác nhận biến Java chứa một đối tượng tham chiếu; nó không nói bất cứ điều gì về file system.
4. `Files.exists(target)` lúc đầu là `false`, `Files.notExists(target)` là `true` vì đường dẫn được tạo trong thư mục tạm mới và chưa có file.
5. `Files.readString` cần mở và đọc file thực tế. Vì file chưa có nên default file system thường báo `NoSuchFileException`.
6. `Files.writeString` với `CREATE_NEW` tạo file mới; lựa chọn này tránh âm thầm ghi đè file đã tồn tại. Nếu có xung đột, thao tác sẽ báo lỗi thay vì ghi lên file cũ.
7. Lúc này `Files.exists` trả `true` và `Files.readString` đọc được văn bản vừa ghi.
8. `finally` xóa tài nguyên tạm sau ví dụ. Nếu cleanup gặp lỗi, `IOException` vẫn có thể phát sinh — đây là hành vi cần thiết khi không thể dọn tài nguyên.

**Bài học:** `target` là cùng một biến `Path` ở cả thời điểm **file chưa có** lẫn thời điểm **file đã được tạo**. Không có sự kiện “Path trở nên hợp lệ hơn” khi file xuất hiện; chỉ trạng thái file system đã thay đổi.

## 4. Các phép biến đổi `Path` không kiểm tra đích

| API | Nó chủ yếu làm gì | Có bảo đảm đích tồn tại? |
| --- | --- | --- |
| `Path.of("a", "b")` | Phân tích các phần tên đường dẫn theo provider | Không |
| `path.resolve("child")` | Kết hợp đường dẫn con hoặc xử lý path cho trước | Không |
| `path.resolveSibling("other")` | Tạo path thay thế cùng cấp với path gốc | Không |
| `path.getFileName()` | Lấy thành phần tên cuối (có thể `null` với root) | Không |
| `path.getParent()` | Lấy parent theo cấu trúc đường dẫn (có thể `null`) | Không |
| `path.normalize()` | Loại bỏ thành phần tên dư thừa theo quy tắc từ vựng | Không |
| `path.toAbsolutePath()` | Chuyển sang dạng đường dẫn tuyệt đối theo provider | Không |
| `path.toUri()` | Biểu diễn URI cho đường dẫn theo provider | Không nên coi là phép kiểm tra tồn tại |
| `path.toFile()` | Chuyển sang `java.io.File` khi provider hỗ trợ | Không |
| `Files.exists(path)` | Thử kiểm tra tồn tại tại thời điểm gọi | Không bảo đảm **tương lai** |
| `path.toRealPath()` | Truy cập file system để lấy đường dẫn thực, xử lý link theo options | Thường yêu cầu mục tồn tại **lúc gọi**, không bảo đảm sau đó |

### Ví dụ chạy được: `resolve` và `normalize` vẫn không “chạm” file

Tạo **`PathLexicalDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathLexicalDemo {
    public static void main(String[] args) {
        Path relative = Path.of("ghost")
                .resolve("draft")
                .resolve("..")
                .resolve("report.txt");

        Path normalized = relative.normalize();

        System.out.println("relative=" + !relative.isAbsolute());
        System.out.println("lastName=" + normalized.getFileName());
        System.out.println("changedByNormalize="
                + !relative.equals(normalized));
        System.out.println("absolute=" + normalized.toAbsolutePath().isAbsolute());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PathLexicalDemo.java
java PathLexicalDemo
~~~

Stdout:

~~~text
relative=true
lastName=report.txt
changedByNormalize=true
absolute=true
~~~

`ghost/draft/../report.txt` được rút gọn về `ghost/report.txt` theo quy tắc từ vựng. Thư mục `ghost` và file `report.txt` không cần tồn tại để chương trình chạy.

**Cảnh báo:** `normalize()` không phải là `toRealPath()`. Nó không giải quyết symbolic link, không xác minh file và không nhất thiết bảo toàn ý nghĩa đường dẫn khi một thành phần được loại bỏ là symbolic link. Ví dụ `link/../file` có thể có ý nghĩa khác sau khi bỏ `link/..` nếu `link` trỏ tới vị trí khác. Không dùng `normalize()` như cách xác nhận một file thực sự nằm trong một thư mục tin cậy.

## 5. `Files.exists()` và `Files.notExists()`: khác nhau với phủ định logic

Một nhầm lẫn nguy hiểm là:

~~~java
if (!Files.exists(path)) {
    // Tưởng chắc chắn file KHÔNG tồn tại.
}
~~~

Theo Java NIO, `Files.exists(path)` có thể trả `false` cả khi file thực sự không tồn tại **và** khi không thể xác định trạng thái. `Files.notExists(path)` cũng có thể trả `false` nếu không thể xác định.

| `Files.exists(path)` | `Files.notExists(path)` | Có thể hiểu trong một trạng thái ổn định |
| --- | --- | --- |
| `true` | `false` | Đã xác nhận mục tồn tại tại thời điểm kiểm tra |
| `false` | `true` | Đã xác nhận mục không tồn tại tại thời điểm kiểm tra |
| `false` | `false` | Không xác định được liệu mục có tồn tại hay không |

Không viết `Files.notExists(path) == !Files.exists(path)` như một bất biến. Thêm nữa, hai lời gọi ở hai thời điểm khác nhau có thể nhìn thấy hai trạng thái khác nhau nếu có thay đổi đồng thời. Các API kiểm tra tồn tại **không giữ khóa hay bảo lưu quyền** để bảo đảm thao tác tiếp theo.

### `isRegularFile` và `isDirectory` cũng không bảo đảm kết quả âm là nguyên nhân cụ thể

~~~java
boolean regular = Files.isRegularFile(path);
boolean directory = Files.isDirectory(path);
~~~

Giá trị `false` của `isRegularFile` có thể chỉ vì đích là thư mục, vì không tồn tại hoặc vì không xác định được thuộc tính. `isDirectory == false` cũng không chứng minh đích là file thường.

Nếu nghiệp vụ phải biết thông tin chi tiết hoặc cần nguyên nhân truy cập thất bại, có thể dùng:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class FileTypeProbe {
    private FileTypeProbe() {}

    public static BasicFileAttributes inspect(Path path) throws IOException {
        return Files.readAttributes(path, BasicFileAttributes.class);
    }
}
~~~

Đây là lớp tiện ích có thể biên dịch nhưng không có `main`. Phương thức `readAttributes` có thể ném `NoSuchFileException`, `AccessDeniedException` hoặc `IOException` khác, tùy file system provider. Tuy nhiên, kết quả thuộc tính vẫn chỉ là **ảnh chụp tại một thời điểm**, không bảo đảm file không bị thay thế sau đó.

## 6. `toRealPath()` khác `toAbsolutePath()` như thế nào?

Hai phương thức trông giống nhau nhưng có ngữ nghĩa khác:

**`path.toAbsolutePath()`**

- Chuyển `Path` tương đối thành dạng tuyệt đối theo file system/provider.
- **Không dùng kết quả như chứng nhận file hiện tồn tại**.
- Đường dẫn có thể chứa thành phần `.`, `..`; `toAbsolutePath()` tự thân không đồng nghĩa với canonicalization đầy đủ.
- Tùy môi trường, cách lấy đường dẫn tuyệt đối có thể dựa vào thư mục làm việc/đặc tính provider; đừng suy ra nó đã đọc mọi metadata của đích.

**`path.toRealPath()`**

- Trả đường dẫn thực (*real path*) theo file system.
- Thông thường nó chuẩn hóa đường dẫn tuyệt đối, giải quyết symbolic link và **kiểm tra sự tồn tại/khả năng truy cập cần thiết** tại thời điểm gọi.
- Có thể ném `IOException`/`NoSuchFileException` khi mục không tồn tại hoặc gặp trở ngại.
- Có thể truyền `LinkOption.NOFOLLOW_LINKS` để ảnh hưởng cách xử lý symbolic link. Tùy chọn này không biến một path không tồn tại thành tồn tại.

### Demo chạy được: `toRealPath()` yêu cầu mục thực tế

Tạo **`RealPathDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class RealPathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("real-path-");
        Path missing = root.resolve("not-yet.txt");

        try {
            System.out.println("absoluteCanBeBuilt="
                    + missing.toAbsolutePath().isAbsolute());

            try {
                missing.toRealPath();
                System.out.println("unexpected success");
            } catch (NoSuchFileException exception) {
                System.out.println("realBefore=NoSuchFileException");
            }

            Files.createFile(missing);
            Path real = missing.toRealPath();

            System.out.println("realAfterExists=" + Files.exists(real));
        } finally {
            Files.deleteIfExists(missing);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RealPathDemo.java
java RealPathDemo
~~~

Stdout trong môi trường file system mặc định thông thường, không có thay đổi đồng thời:

~~~text
absoluteCanBeBuilt=true
realBefore=NoSuchFileException
realAfterExists=true
~~~

`toAbsolutePath()` tạo được đường dẫn tuyệt đối trước khi file xuất hiện. `toRealPath()` không tìm thấy mục ở lần gọi đầu; sau `Files.createFile`, lời gọi thành công.

**Không lạm dụng `toRealPath()`:** Nếu bạn đang tính đường dẫn cho file *sắp được tạo*, gọi `toRealPath()` trên **file đích** thường là sai bước vì đích chưa tồn tại. Có thể cần canonicalize **thư mục cha đã tồn tại** và có chính sách tạo file riêng, nhưng vẫn phải xử lý race/symlink. Hơn nữa, thành công của `toRealPath()` hôm nay không cung cấp một file handle giữ cố định mục đó cho các thao tác sau.

## 7. Kiểm tra rồi thao tác: vấn đề TOCTOU

Xem cách viết:

~~~java
if (Files.exists(target)) {
    String text = Files.readString(target);
}
~~~

Giữa `exists` và `readString`, một tiến trình/thread khác có thể xóa file, đổi quyền, chuyển đường dẫn hoặc thay thế symbolic link. Khi đó `readString` vẫn có thể ném `IOException`.

Tương tự, đoạn sau **không an toàn để bảo đảm tạo file mới**:

~~~java
if (!Files.exists(target)) {
    Files.writeString(target, "data");
}
~~~

`Files.writeString` mặc định có thể tạo file hoặc truncate file đã có. Trong thời gian giữa kiểm tra và ghi, một bên khác có thể tạo ra file tại đích; kết quả là file của họ bị ghi đè. Ngoài ra, `Files.exists()==false` không luôn khẳng định “không tồn tại”.

### Chọn thao tác có điều kiện ngay tại điểm I/O

Nếu mục tiêu là tạo **file mới và không ghi đè**, viết:

~~~java
Files.writeString(
        target,
        "data",
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE_NEW,
        java.nio.file.StandardOpenOption.WRITE
);
~~~

`CREATE_NEW` yêu cầu kiểm tra “chưa có file” và tạo file **theo hợp đồng nguyên tử đối với các thao tác file system khác**. Nếu file tồn tại ở thời điểm thực thi, thao tác báo lỗi (thường là `FileAlreadyExistsException`). Đây là sự khác biệt then chốt so với chuỗi `exists → write`.

Nếu mục tiêu là đọc file bắt buộc tồn tại, **cứ mở và đọc**:

~~~java
String text = Files.readString(
        target, java.nio.charset.StandardCharsets.UTF_8);
~~~

Bắt/lan truyền `NoSuchFileException`, `AccessDeniedException`, `IOException` khác từ chính thao tác, thay vì dùng `Files.exists` làm “giấy phép bảo đảm”.

Nếu mục tiêu là thư mục **phải tồn tại sau thao tác**, dùng `Files.createDirectories(dir)` và xử lý `IOException` nếu không thể tạo hoặc đích không phải thư mục. Nếu mục tiêu là xóa file **nếu có**, `Files.deleteIfExists(path)` có thể trả `false` cho trường hợp thiếu nhưng vẫn có thể ném `IOException` cho các lỗi xóa khác.

**Quy tắc:** Việc kiểm tra trạng thái có ích cho giao diện người dùng hoặc chiến lược chẩn đoán, nhưng thao tác I/O thực sự luôn phải có đường xử lý lỗi.

## 8. `Path` không đồng nghĩa có quyền truy cập

Một file có thể tồn tại nhưng không đọc được vì:

- File-system permission, ACL, sandbox hoặc policy hệ điều hành.
- Mục đang được sử dụng/khóa tùy hệ thống và chế độ chia sẻ.
- Mục đã bị đổi/xóa/chuyển khi thao tác bắt đầu.
- File system không sẵn sàng, ổ mạng mất kết nối hoặc provider gặp lỗi.
- Đích là thư mục khi API yêu cầu file, hoặc ngược lại.
- Symbolic link là dangling hoặc dẫn đến mục không truy cập được.

`Files.isReadable(path)` / `Files.isWritable(path)` trả boolean mang ý nghĩa kiểm tra khả năng tại thời điểm đó; **không bảo đảm** lời gọi mở/ghi kế tiếp thành công. Một `Path` cũng có thể trỏ tới file hiện không tồn tại nhưng sẽ được tạo bởi một tác vụ khác trong tương lai.

Khi cần phân biệt lý do, ưu tiên **ngoại lệ từ thao tác**:

| API | Khi thành công | Một số trường hợp lỗi |
| --- | --- | --- |
| `Files.readString(path, UTF_8)` | Đọc văn bản từ file | `NoSuchFileException`, `AccessDeniedException`, `IOException` hoặc lỗi giải mã theo contract |
| `Files.newInputStream(path)` | Mở luồng đọc byte | `IOException` khi không mở được/đọc lỗi |
| `Files.createFile(path)` | Tạo file mới | `FileAlreadyExistsException`, `IOException` |
| `Files.createDirectories(path)` | Đảm bảo chuỗi thư mục được tạo/tồn tại | `IOException` nếu không thể tạo hoặc có mục không phải thư mục |
| `Files.delete(path)` | Xóa file/mục | `NoSuchFileException`, `DirectoryNotEmptyException` (tùy provider), `IOException` |
| `Files.readAttributes(path, BasicFileAttributes.class)` | Đọc thuộc tính tại thời điểm truy vấn | `IOException` khi không truy vấn được |
| `path.toRealPath()` | Lấy real path hiện tại | `IOException` khi không tìm/giải quyết được |

Các ngoại lệ cụ thể của một số API được ghi là *optional specific exceptions* trong Java API; provider có thể dùng một `IOException` chung. Không dựa vào thông báo lỗi tiếng Anh hoặc giả định mọi provider/OS đều báo đúng lớp con cụ thể.

## 9. Symbolic link: tồn tại của đường dẫn và tồn tại của đích liên kết là hai việc

Giả sử có một symbolic link `shortcut` trỏ tới `archive/missing.txt`, nhưng file đích đã mất. Khi đó:

- Bản thân mục **symbolic link** có thể vẫn tồn tại trên file system.
- `Files.exists(shortcut)` mặc định **theo symbolic link** (khi API/provider hỗ trợ), nên có thể trả `false` vì target không tồn tại.
- `Files.exists(shortcut, LinkOption.NOFOLLOW_LINKS)` kiểm tra chính link thay vì đi tới đích, nên có thể trả `true` khi link còn tồn tại.
- `Path.toRealPath()` mặc định giải quyết link và sẽ thất bại nếu không giải quyết được target; `NOFOLLOW_LINKS` thay đổi cách xử lý link theo hợp đồng.
- `Path.normalize()` hoàn toàn **không xác định link đó đang trỏ đi đâu**.

Không nên dạy `Files.exists()==false` như “không có bất cứ file-system entry nào ở vị trí này”. Nó có thể chỉ cho thấy đích *sau khi theo link* không tồn tại hoặc không được xác định.

Đừng phụ thuộc vào việc tạo symbolic link trong unit test ở mọi OS: Windows hoặc môi trường CI có thể yêu cầu quyền/chế độ riêng. Với logic quan trọng, nên có integration test theo từng provider.

## 10. Path traversal, thư mục gốc tin cậy và giới hạn của `normalize()`

Một API nhận tên file từ bên ngoài thường xây dựng:

~~~java
Path base = Path.of("uploads").toAbsolutePath().normalize();
Path requested = base.resolve(userName).normalize();
~~~

Đây là **mảnh mã** với biến `userName` kiểu `String` đã có. Nó tính đường dẫn để làm việc, không mở file. Ngay cả nếu thêm:

~~~java
if (!requested.startsWith(base)) {
    throw new IllegalArgumentException("Path escapes base");
}
~~~

thì kiểm tra này mới bảo vệ ở **mức từ vựng** đối với các thành phần như `..` (và cần quan tâm đường dẫn tuyệt đối của đầu vào). Nó không bảo đảm file thực nằm dưới `base` vì symlink, mount point, hard link và race condition có thể làm khác vị trí thực.

Đối với dữ liệu không tin cậy:

1. Xác định rõ nhóm tên file được phép (ví dụ chỉ một file name, không cho dấu phân cách nếu nghiệp vụ không cần đường dẫn con).
2. Không cho người dùng tự chỉ định đường dẫn tuyệt đối/`..` ngoài phạm vi hợp đồng.
3. Hiểu rằng `normalize` không truy vấn hoặc khóa file system; nó không xác thực symbolic links.
4. Áp dụng ranh giới quyền truy cập phù hợp, xử lý việc thư mục/entry bị đổi trong quá trình mở.
5. Với yêu cầu chống symlink traversal cao, tìm hiểu `SecureDirectoryStream` khi provider hỗ trợ và các chiến lược thao tác tương đối với một directory handle, thay vì chỉ so sánh chuỗi `Path`.

**Không dùng một lần `toRealPath()` rồi xem đó là giải pháp hoàn toàn loại bỏ TOCTOU**. Giữa việc kiểm tra real path và mở mục, tác nhân khác vẫn có thể thay đổi cây thư mục.

## 11. Tương đối, tuyệt đối và làm việc với nhiều file systems

### `Path` tương đối

~~~java
Path path = Path.of("notes.txt");
~~~

Nó có thể được hiểu dựa trên thư mục làm việc (hoặc quy tắc provider). Việc ứng dụng được chạy từ IDE, terminal hay scheduler có thể làm **cùng một chuỗi `notes.txt`** hướng tới các vị trí tuyệt đối khác nhau.

Nếu đường dẫn thuộc cấu hình quan trọng, hãy quyết định base directory rõ ràng:

~~~java
Path base = Path.of("/app/data"); // Minh họa path riêng môi trường Unix-like.
Path target = base.resolve("notes.txt");
~~~

Ở Windows hoặc một provider khác, cú pháp `/app/data` có ý nghĩa riêng. Đừng hard-code đường dẫn hệ điều hành vào thư viện đa nền tảng; tốt hơn truyền `Path base` từ cấu hình/constructor.

### `Path` từ provider khác

`Path` là interface do file system provider triển khai. Ngoài đĩa local có thể có ZIP file system hoặc những provider được cài thêm. Những đặc điểm cần nhớ:

- Không mọi provider đều hỗ trợ cùng loại thuộc tính, symlink, atomic move, permission hoặc chuyển sang `File`.
- `Files.exists`/`Files.readAttributes`/`toRealPath` có ngữ nghĩa chung nhưng cách báo một số lỗi/khả năng phụ thuộc provider.
- `Path.toFile()` có thể ném `UnsupportedOperationException` nếu provider không liên kết với default file system.
- So sánh `Path.equals` chủ yếu là so sánh representation/provider theo hợp đồng, **không phải kiểm tra hai tên có trỏ cùng inode/file thực không**.
- Muốn hỏi hai đường dẫn có chỉ đến cùng một file thực tại một thời điểm, dùng `Files.isSameFile(pathA, pathB)` khi phù hợp; lưu ý API này cũng có các quy tắc tối ưu và không được dùng thay thế kiểm tra sự tồn tại trong mọi tình huống.

## 12. Khác gì so với `java.io.File`?

Hai kiểu có điểm tương đồng quan trọng:

~~~java
File f = new File("missing.txt");
Path p = Path.of("missing.txt");
~~~

Cả `new File(...)` và `Path.of(...)` đều có thể tạo object trỏ đến đích **chưa tồn tại**. Chuyển đổi:

~~~java
Path fromFile = f.toPath();
File fromPath = p.toFile(); // Nếu provider hỗ trợ.
~~~

cũng **không tạo mục trên ổ đĩa** hoặc kiểm tra nó đã tồn tại.

Điểm khác biệt là NIO cho phép thao tác qua `Files` với các khả năng và lỗi chi tiết hơn:

| Nhu cầu | Phương pháp truyền thống | NIO thường phù hợp hơn |
| --- | --- | --- |
| Biểu diễn đường dẫn | `File` | `Path` |
| Kiểm tra tồn tại | `File.exists()` | `Files.exists(path)` (vẫn có giới hạn boolean) |
| Tạo file mới | `File.createNewFile()` | `Files.createFile(path)` |
| Tạo thư mục nhiều cấp | `File.mkdirs()` | `Files.createDirectories(path)` |
| Xóa file | `File.delete()` trả boolean | `Files.delete(path)` ném lỗi |
| Di chuyển | `File.renameTo(...)` trả boolean | `Files.move(...)` với options |
| Đọc thuộc tính | `File` có các thuộc tính đơn giản | `Files.readAttributes`/attribute views |

`Path` tự nó không mở/tạo/xóa file. **`Files` là tập tiện ích thao tác với Path**. Tuy vậy, ngay cả khi `Files.exists` trả true, ứng dụng vẫn phải xử lý lỗi ở thao tác tiếp theo.

## 13. Thiết kế API nhận `Path`: đừng ngầm đòi mục phải tồn tại

Hàm nhận `Path` có thể có các hợp đồng rất khác nhau:

~~~java
// Đọc nội dung: mục phải đọc được tại thời điểm thao tác.
static String load(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}

// Tạo mới: mục KHÔNG được tồn tại tại thời điểm tạo.
static Path create(Path path) throws IOException {
    return Files.createFile(path);
}

// Chỉ tính tên đích dự kiến, chưa cần tồn tại.
static Path plannedOutput(Path folder, String fileName) {
    return folder.resolve(fileName);
}
~~~

Các đoạn trên là **mảnh mã** cần đặt trong lớp Java, import `Path`, `Files`, `IOException` và `StandardCharsets`. Đừng áp một tiền điều kiện “`Path` luôn phải tồn tại” cho cả ba: `create` **cần** đích chưa có, còn `plannedOutput` chỉ tính tên.

Nên mô tả rõ trong JavaDoc/API:

- Path được phép trỏ đến đích chưa tồn tại hay không?
- Có cho phép đường dẫn tương đối không, và base directory lấy từ đâu?
- Có theo symbolic link không?
- Nếu file đã tồn tại, ghi đè, thêm vào cuối, hay báo lỗi?
- Caller hay callee sở hữu các stream/channel sau khi mở?
- Trường hợp nào được báo `IOException` và có cần phân biệt `NoSuchFileException` hay không?

### Ví dụ tạo tệp từ Path được lập kế hoạch trước

Tạo file **`PlannedFileDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PlannedFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("planned-file-");
        Path folder = root.resolve("reports");
        Path output = folder.resolve("result.txt");

        try {
            System.out.println("folderExistsBefore=" + Files.exists(folder));
            System.out.println("outputExistsBefore=" + Files.exists(output));

            Files.createDirectories(folder);
            Files.writeString(
                    output,
                    "done",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );

            System.out.println("folderExistsAfter=" + Files.isDirectory(folder));
            System.out.println("outputExistsAfter=" + Files.isRegularFile(output));
            System.out.println("text=" + Files.readString(
                    output, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(output);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Chạy:

~~~bash
javac PlannedFileDemo.java
java PlannedFileDemo
~~~

Stdout trong môi trường thông thường không có thao tác cạnh tranh trên thư mục tạm:

~~~text
folderExistsBefore=false
outputExistsBefore=false
folderExistsAfter=true
outputExistsAfter=true
text=done
~~~

Bài này minh họa tình huống thực tế: code biết đường dẫn file và thư mục cần tạo **trước khi chúng tồn tại**; sau đó dùng hai thao tác cụ thể để tạo. Đừng thêm `toRealPath()` trên `output` trước khi tạo chỉ để “xác nhận path hợp lệ”.

## 14. Những hiểu nhầm phổ biến

**Hiểu nhầm 1 — Tạo `Path` cũng là tạo file.**  
Sai. `Path.of` là phép tạo đối tượng biểu diễn đường dẫn; muốn tạo file/thư mục hãy dùng `Files.createFile`, `createDirectories` hoặc mở stream với open options phù hợp.

**Hiểu nhầm 2 — `toAbsolutePath` chứng minh file có thật.**  
Sai. Một đường dẫn tuyệt đối vẫn có thể trỏ tới mục chưa tồn tại.

**Hiểu nhầm 3 — `normalize` giải quyết symlink và xác nhận vị trí thực.**  
Sai. `normalize` xử lý thành phần tên theo từ vựng; `toRealPath` mới có truy cập file system, và kết quả chỉ phản ánh một thời điểm.

**Hiểu nhầm 4 — `Files.exists(path)==false` luôn chắc chắn chưa có mục.**  
Sai. Có trường hợp không thể xác định. `Files.notExists` không đơn giản là phủ định của `Files.exists`.

**Hiểu nhầm 5 — `Files.isReadable(path)==true` đảm bảo `readString` thành công.**  
Sai. Trạng thái, quyền hoặc đối tượng ở đích có thể thay đổi; thao tác còn có thể lỗi vì lý do khác.

**Hiểu nhầm 6 — Kiểm tra `exists` rồi gọi `writeString` là tạo file an toàn.**  
Sai. Có race condition, và `writeString` mặc định có thể ghi đè đích; dùng `CREATE_NEW` nếu nghiệp vụ yêu cầu tạo mới không ghi đè.

**Hiểu nhầm 7 — Lỗi `NoSuchFileException` nghĩa là đối tượng `Path` không hợp lệ.**  
Sai. `Path` có thể hợp lệ về cú pháp nhưng file chưa tồn tại tại thời điểm thao tác. `InvalidPathException` mới liên quan tới một chuỗi đường dẫn không thể được phân tích bởi provider; đó là vấn đề khác.

**Hiểu nhầm 8 — Đường dẫn tuyệt đối đồng nghĩa đường dẫn cố định, không bao giờ đổi mục.**  
Sai. Mục tại cùng một tên file có thể bị xóa và thay thế. Một `Path` không giữ handle/lock tới một object bất biến.

**Hiểu nhầm 9 — Nếu kiểm tra `path.normalize().startsWith(base)` thì không thể có path traversal.**  
Sai. Nó có ích để kiểm tra từ vựng nhưng không đủ chống symbolic link và TOCTOU trong cây thư mục do người khác kiểm soát.

**Hiểu nhầm 10 — `Path.toFile()` luôn hoạt động trên mọi provider.**  
Sai. Provider không thuộc default file system có thể không hỗ trợ chuyển sang `java.io.File`.

## 15. Checklist khi review chương trình dùng Path

- [ ] Đang **tạo/mô tả đường dẫn** hay thực sự **truy cập hệ thống tập tin**?
- [ ] Có giả định `Path.of`/`resolve`/`toAbsolutePath` bảo đảm đích tồn tại không?
- [ ] Nếu cần đọc file, đã thực hiện thao tác đọc và xử lý `IOException` tại chính lời gọi đó?
- [ ] Nếu cần tạo file mới, đã dùng `CREATE_NEW` hoặc `Files.createFile` tránh ghi đè?
- [ ] Nếu cần thư mục đích, đã tạo/thẩm định đúng chính sách bằng `createDirectories` hoặc API tương ứng?
- [ ] Có phân biệt `Files.exists` false với `Files.notExists` true, và trường hợp unknown?
- [ ] Có tránh kiểm tra `exists` rồi coi thao tác sau chắc chắn không lỗi?
- [ ] Nếu dùng `toRealPath()`, đích có cần phải tồn tại và symbolic link được xử lý ra sao?
- [ ] Có kiểm tra input không tin cậy: đường dẫn tuyệt đối, `..`, symlink, thư mục được phép?
- [ ] Có nêu rõ default/other file-system provider, đường dẫn tương đối và base directory?
- [ ] Unit test có dùng thư mục tạm để không phụ thuộc file có sẵn ở máy người học?
- [ ] Có cleanup tài nguyên đúng cách và không xóa đường dẫn ngoài vùng test?

## 16. Tự kiểm tra kiến thức

**Câu 1.** `Path p = Path.of("missing.txt");` chạy không có exception. Có chắc file tồn tại không?  
**Đáp án:** Không. Nó chỉ tạo một `Path` biểu diễn tên `missing.txt`.

**Câu 2.** `p.toAbsolutePath()` trả một đường dẫn tuyệt đối. Điều này chứng minh được gì về sự tồn tại?  
**Đáp án:** Không chứng minh gì; nó chỉ chuyển biểu diễn sang đường dẫn tuyệt đối.

**Câu 3.** Khi nào `Files.exists` và `Files.notExists` đều có thể trả `false`?  
**Đáp án:** Khi không thể xác định trạng thái tồn tại theo quy tắc truy vấn file system.

**Câu 4.** Phương thức nào thường kiểm tra sự tồn tại và trả real path tại thời điểm gọi?  
**Đáp án:** `toRealPath()`, có thể ném `IOException` và xử lý symbolic link theo options.

**Câu 5.** Tại sao không nên viết `if (!Files.exists(p)) Files.writeString(p, text);` nếu không muốn ghi đè?  
**Đáp án:** Vì race condition và mặc định `writeString` có thể tạo/truncate file đã tồn tại; dùng `CREATE_NEW`.

**Câu 6.** Khi hàm được truyền `Path` cho output file chưa có, nên bắt nó gọi `toRealPath()` trước không?  
**Đáp án:** Không bắt buộc và thường không phù hợp. Cần xác định/cấp quyền với parent/đích theo policy, sau đó tạo file bằng thao tác cụ thể.

**Câu 7.** `p.normalize()` đã đủ ngăn truy cập file bên ngoài thư mục cho phép chưa?  
**Đáp án:** Chưa. Symbolic link, race condition và quyền truy cập vẫn cần được xử lý.

**Câu 8.** Khi `Files.readString(path)` ném `NoSuchFileException`, có phải `Path` đã “hỏng” không?  
**Đáp án:** Không. File được yêu cầu không tồn tại tại thời điểm thao tác (hoặc provider báo điều kiện thiếu mục tương ứng), còn biểu diễn `Path` có thể vẫn hoàn toàn hợp lệ.

**Ghi nhớ:** **`Path` là đường dẫn, không phải file đang tồn tại.** Việc tạo hay biến đổi đối tượng `Path` không tạo file và không giữ cho mục bên dưới tồn tại. Muốn biết trạng thái, phải truy vấn file system, nhưng ngay cả kiểm tra thành công cũng chỉ đúng tại một thời điểm. Khi cần kết quả nghiệp vụ chắc chắn, hãy dùng thao tác `Files` trực tiếp với options phù hợp và xử lý `IOException`.

## Tham khảo Java SE 17

- [Path — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Files — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StandardOpenOption — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [LinkOption — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)