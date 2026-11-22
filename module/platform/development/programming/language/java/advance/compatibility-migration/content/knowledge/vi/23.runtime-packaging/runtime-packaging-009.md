# Đường dẫn, quyền tệp, font và các giả định về hệ điều hành

Một ứng dụng Java có thể chạy hoàn hảo trong IDE trên Windows nhưng thất bại khi được đóng gói thành JAR và triển khai lên Linux: không tìm thấy file cấu hình, không ghi được thư mục tạm, không đọc được chứng chỉ, hoặc tài liệu PDF xuất ra bị mất dấu tiếng Việt. Những vấn đề này có thể xuất hiện cùng lúc với việc nâng JDK, đổi image container, sử dụng `jlink` hoặc chuyển máy chủ. Tuy nhiên, **không phải lỗi nào xuất hiện sau khi nâng Java đều do API Java thay đổi**; nhiều lỗi bắt nguồn từ giả định ẩn về hệ điều hành và cách đóng gói.

Trong **Java Advance Compatibility Migration**, nhóm cần kiểm tra cả **mã Java, tập tin đi kèm ứng dụng, filesystem, quyền của tiến trình, font, locale và runtime image**. Việc chương trình biên dịch thành công không chứng minh những điều kiện đó tồn tại khi chạy production.

Bài học này hướng dẫn cách dùng `java.nio.file` để thao tác đường dẫn an toàn, phân biệt resource nằm trong JAR với file bên ngoài, kiểm tra quyền theo từng nền tảng, quản lý font khi chạy headless/container, và xây ma trận thử nghiệm để loại bỏ những phụ thuộc vào OS không được khai báo.

## 1. Nhận diện đúng các tầng khi ứng dụng thao tác với tệp

Một thao tác như “đọc file mẫu để tạo báo cáo” có thể đi qua nhiều tầng:

~~~text
Application code
    |
    +-- java.nio.file.Path / Files
    +-- ClassLoader.getResourceAsStream()
    |
Packaging:
    +-- JAR/WAR/resource trong archive
    +-- File cấu hình đặt ngoài archive
    +-- Runtime image tạo bởi jlink
    |
Operating system:
    +-- Filesystem và mount point
    +-- Đường dẫn, case sensitivity, symbolic link
    +-- Ownership, ACL/POSIX permissions
    +-- Charset, locale, timezone, font availability
    |
Deployment:
    +-- Working directory
    +-- User/UID của process
    +-- Container volume, read-only filesystem
    +-- Java runtime/JDK distribution
~~~

Nhìn biểu đồ trên, một `NoSuchFileException` không nhất thiết nói “Java không nhận ra file”. Nó có thể nghĩa là file được tìm **tại một đường dẫn khác**, resource đã nằm trong JAR thay vì filesystem thông thường, hoặc volume chưa được mount. Một `AccessDeniedException` thường đòi kiểm quyền của tài khoản chạy tiến trình hơn là thay phiên bản Java.

### 1.1. Ma trận triệu chứng ban đầu

| Triệu chứng | Nhóm nguyên nhân nên kiểm trước | Không nên vội kết luận |
|---|---|---|
| `NoSuchFileException` | Working directory, đường dẫn thực, mount, tên file | JDK mới đã xóa file |
| `AccessDeniedException` | UID/GID, ACL, owner, directory traversal permission | Cần chạy ứng dụng bằng root |
| `InvalidPathException` | Cú pháp đường dẫn không hợp lệ với filesystem provider | Có thể thay mọi dấu phân cách một cách cơ học |
| Resource đọc được trong IDE nhưng mất khi chạy JAR | Đang dùng đường dẫn tới `src/main/resources` thay vì classpath | Plugin build luôn sai |
| Font hiển thị thành ô vuông | Font không chứa glyph, fontconfig, fallback, embedded font | Charset UTF-8 chắc chắn sai |
| Giao diện cần display khi chạy server | AWT headless và API có yêu cầu display | `java.desktop` chắc chắn đã bị xóa |
| Linux chạy, Windows không xóa được file | File handle còn mở, semantics delete/lock khác nhau | `Files.delete` bị lỗi ở JDK mới |
| Container bị lỗi dù local chạy | File permissions, mount, minimal image, OS architecture | Chỉ cần tăng heap |
| File test pass trên macOS, fail trên Linux | Case sensitivity, Unicode normalization, path layout | Source code hẳn không biên dịch |

Luôn bắt đầu từ **đường dẫn thực và runtime thực** đã ghi trong log/stack trace, không từ phỏng đoán về hệ điều hành.

## 2. Java Path là một abstraction của filesystem, không phải chuỗi thuần

Java NIO.2 cung cấp `Path`, `Files` và các attribute view để thao tác file. So với việc ghép chuỗi, API này giúp biểu diễn đường dẫn theo quy tắc của filesystem provider đang chạy.

Ví dụ nên dùng:

~~~java
import java.nio.file.Path;

Path root = Path.of("/srv/app/data");
Path report = root.resolve("reports").resolve("daily.csv");

System.out.println(report);
~~~

Cú pháp `Path.of` có từ Java 11. Nếu dự án vẫn phải hỗ trợ Java 8, dùng `Paths.get(...)` tương ứng.

Không nên tự ghép:

~~~java
String report = root + "/" + folder + "\\" + fileName;
~~~

Đoạn trên trộn separator và giả định `root`, `folder` không có dấu phân cách ở đầu/cuối. Trên Windows và Unix, tên path được hiểu khác nhau.

### 2.1. Các phương thức cần phân biệt

| API | Vai trò | Điểm dễ nhầm |
|---|---|---|
| `Path.of(...)` | Tạo Path theo filesystem mặc định | Chuỗi có thể hợp lệ ở OS này nhưng không hợp lệ ở OS khác |
| `resolve(other)` | Ghép đường dẫn theo quy tắc Path provider | Nếu `other` là absolute path thì cách resolve có thể bỏ qua base |
| `normalize()` | Loại các thành phần `.`, `..` dư thừa về mặt cú pháp | Không truy cập filesystem và không loại bỏ mọi rủi ro symlink |
| `toAbsolutePath()` | Chuyển thành absolute path theo ngữ cảnh runtime | Có thể dựa vào working directory |
| `toRealPath()` | Xác định đường dẫn thật trong filesystem, có kiểm tra tồn tại | Có thể follow symlink và gặp lỗi quyền/I/O |
| `relativize(other)` | Tìm đường dẫn tương đối giữa hai Path | Thường cần cùng provider/compatible roots |
| `getFileName()` | Lấy thành phần tên cuối | Không phải phép xác minh tên an toàn cho upload |

`Path.normalize()` là phép chuẩn hóa cú pháp, không phải một kiểm tra bảo mật đầy đủ. Đặc biệt, `toRealPath()` và thao tác file thực tế có thể quan sát filesystem ở hai thời điểm khác nhau.

## 3. Dấu phân cách, ổ đĩa và đường dẫn tuyệt đối

Trên Linux và nhiều Unix-like OS, path separator là `/`; Windows có drive letter, UNC paths và quy tắc riêng. Một chuỗi như:

~~~text
C:\services\app\data\report.csv
~~~

có ý nghĩa như đường dẫn Windows. Đưa nguyên chuỗi đó vào một Linux container không tạo ra “file trên ổ C”. Với Windows còn có các dạng root-relative, drive-relative và UNC mà code không nên tự xử lý bằng vài phép `split`.

### 3.1. Cấu hình path theo môi trường

Thay vì hardcode:

~~~java
Path base = Path.of("C:\\Work\\report-system\\data");
~~~

nên lấy path được cung cấp bởi deployment:

~~~java
String configured = System.getenv("APP_DATA_DIR");

if (configured == null || configured.isBlank()) {
    throw new IllegalStateException(
            "APP_DATA_DIR must be configured");
}

Path dataDir = Path.of(configured).toAbsolutePath().normalize();
~~~

Với Java 8, thay `isBlank()` bằng kiểm tra phù hợp. Biến môi trường chỉ là một cách đưa cấu hình vào ứng dụng; có thể dùng command-line option hoặc framework configuration chuẩn. Quan trọng là **không giấu đường dẫn riêng của máy phát triển trong source**.

### 3.2. Không mặc định cùng một root ở mọi môi trường

| Môi trường | Ví dụ path hợp lý | Nguồn phải được quản lý |
|---|---|---|
| Windows developer | `C:\work\app\data` | User-local config |
| Linux VM | `/srv/app/data` | Service deployment |
| Container | `/var/lib/app/data` | Image, volume và mount |
| macOS developer | Thư mục con của user home | User-local config |
| CI | Thư mục tạm/checkout do runner cung cấp | Pipeline/workspace config |

Các path trên chỉ là ví dụ. Không cần ép Windows/Linux dùng cùng một chuỗi path; mục tiêu là **cùng ý nghĩa cấu hình**.

## 4. Working directory không phải thư mục chứa JAR

Đoạn code sau phụ thuộc working directory:

~~~java
Path config = Path.of("config", "application.properties");
String text = java.nio.file.Files.readString(config);
~~~

Nếu chạy từ project root, chương trình có thể tìm đúng `config/application.properties`. Nếu service manager chạy từ `/` hoặc container đặt `WORKDIR /app`, kết quả khác.

Hãy quan sát:

~~~java
System.out.println(
        "user.dir = " + System.getProperty("user.dir"));

System.out.println(
        "working path = " +
        Path.of(".").toAbsolutePath().normalize());
~~~

Đừng dựa vào việc `java -jar /path/to/app.jar` tự chuyển working directory sang thư mục chứa JAR. Java launcher không cam kết hành vi như vậy.

### 4.1. Cách thiết kế bền vững

- **Resource cố định của ứng dụng**: đóng gói vào classpath/JAR và đọc qua resource stream.
- **Cấu hình triển khai**: đường dẫn/file/secret do môi trường cấp, có hợp đồng rõ.
- **Dữ liệu nghiệp vụ cần ghi**: persistent volume hoặc storage được quản lý.
- **File tạm**: sử dụng directory được cấp và API `Files.createTempFile`.
- **Bản xuất cho người dùng**: thư mục output do ứng dụng/quy trình chọn, không tự phụ thuộc CWD.

Không chọn một phương án duy nhất cho cả năm nhóm.

## 5. Resource trong JAR không giống một file ngoài filesystem

Một sai lầm phổ biến khi chuyển từ IDE sang JAR:

~~~java
Path template =
        Path.of("src/main/resources/templates/invoice.txt");
~~~

Cách này có thể hoạt động khi chạy trong project checkout. Sau `gradle jar` hoặc `mvn package`, resource thường nằm **bên trong JAR**, không còn ở đường dẫn source đó.

### 5.1. Dùng Class.getResourceAsStream

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class TemplateLoader {
    public static String load() throws IOException {
        try (InputStream stream =
                     TemplateLoader.class.getResourceAsStream(
                             "/templates/invoice.txt")) {
            if (stream == null) {
                throw new IOException(
                        "Missing classpath resource: templates/invoice.txt");
            }
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

Ví dụ dùng `InputStream.readAllBytes()` (Java 9+). Khi hỗ trợ Java 8, dùng cách đọc stream tương ứng.

Lưu ý sự khác biệt:

- `SomeClass.class.getResourceAsStream("/path")`: dấu `/` đầu nghĩa là đường dẫn tuyệt đối trong classpath/resource namespace.
- `SomeClass.class.getResourceAsStream("path")`: tương đối với package của class.
- `SomeClass.class.getClassLoader().getResourceAsStream("path")`: thường dùng tên resource không có dấu `/` đầu.

### 5.2. Không chuyển mọi resource URL thành Path

Một cách dễ lỗi:

~~~java
var url = TemplateLoader.class.getResource("/templates/invoice.txt");
Path path = Path.of(url.toURI());
~~~

Khi chạy trong thư mục classes, URL có thể là `file:` và Path hoạt động. Khi resource nằm trong JAR, URL thường mang scheme `jar:`; `Path.of(URI)` không tự bảo đảm đọc được bên trong archive bằng default filesystem provider.

Với resource chỉ cần đọc, **ưu tiên InputStream**. Nếu thư viện bên ngoài bắt buộc nhận `Path`, có thể copy resource ra file tạm được quản lý và xóa khi không cần. Hoặc dùng ZIP filesystem provider khi đúng yêu cầu, nhưng cần xử lý vòng đời filesystem.

## 6. File cấu hình và dữ liệu bên ngoài JAR

Nếu một file phải được người vận hành thay đổi mà không rebuild artifact, không nên nhúng nó như một resource bất biến bên trong JAR.

Ví dụ:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path configPath = Path.of(
        System.getenv("APP_CONFIG_FILE"));

String config = Files.readString(
        configPath, StandardCharsets.UTF_8);
~~~

Trong code production cần xử lý biến môi trường không tồn tại và quyền đọc file như ví dụ ở phần cấu hình. Với secret, không nên in toàn bộ nội dung lên log. File đặt ngoài JAR có thể được quản lý bằng ConfigMap, Secret mount, service manager hoặc cơ chế hạ tầng phù hợp.

### 6.1. Đọc được file không có nghĩa file là đúng phiên bản

Một container có thể mount nhầm config của môi trường khác. Nên kiểm:

- Có tồn tại file ở path được công bố không?
- Owner/perms có phù hợp với service account không?
- Nội dung thuộc schema/version config nào?
- Encoding là gì?
- Có thiếu các giá trị bắt buộc không?
- Credential có được cấp qua secret store thay vì commit trong image không?

Không được coi `Files.exists(path)` là toàn bộ validation.

## 7. Case sensitivity: sai tên file thường chỉ xuất hiện trên Linux

Các filesystem có thể khác về phân biệt chữ hoa/thường. Một project chứa:

~~~text
src/main/resources/Templates/Invoice.html
~~~

nhưng code gọi:

~~~java
getResourceAsStream("/templates/invoice.html")
~~~

có thể hoạt động trong một số cấu hình filesystem case-insensitive nhưng thất bại trên Linux case-sensitive. Tương tự, Git có thể không ghi nhận đổi chữ hoa/thường theo cùng cách ở mọi máy tùy filesystem và config.

### 7.1. Cách phòng tránh

- Dùng tên path đúng chính tả và case từ đầu.
- Định nghĩa convention nhất quán cho tên file/resource.
- Chạy clean checkout và đóng gói trên Linux nếu production là Linux.
- Kiểm file đóng gói trong JAR, không chỉ source tree.
- Khi sửa tên chỉ khác case, xác minh Git đã ghi nhận rename đúng trên filesystem đang dùng.

Không nên “sửa” bằng cách duyệt toàn bộ thư mục để chọn tên gần giống không phân biệt case: cách đó có thể che nhầm file và tạo kết quả không xác định.

## 8. Unicode trong tên file khác Unicode trong nội dung file

Việc nội dung file dùng UTF-8 không tự bảo đảm mọi filesystem xử lý tên file theo cùng một cách. Một tên tiếng Việt có dấu có thể được biểu diễn bằng những chuỗi Unicode khác nhau nhưng nhìn gần giống nhau, ví dụ ký tự được ghép sẵn hoặc base character đi kèm combining mark.

Trên các OS/filesystem khác nhau, quy tắc normalization, case folding và encoding của path có thể khác. Không nên mặc định hai chuỗi `String` trông giống nhau luôn tham chiếu cùng file.

### 8.1. Thiết kế tên file ổn định

Với dữ liệu nghiệp vụ hoặc upload:

- Dùng ID ổn định hoặc tên file được chuẩn hóa theo quy tắc ứng dụng.
- Không dùng tên hiển thị do người dùng cung cấp làm khóa lưu trữ duy nhất.
- Giữ metadata `originalFilename` riêng nếu cần cho UI.
- Kiểm những tên bất hợp lệ/trùng sau normalization và case folding.
- Test tên có dấu tiếng Việt, emoji, dấu cách và ký tự tổ hợp.
- Tránh giả định một giới hạn độ dài tên file cho tất cả filesystems.

**Không** dùng `Normalizer.normalize()` như biện pháp duy nhất để bảo vệ path; normalization ký tự và bảo vệ traversal là các vấn đề khác nhau.

## 9. Tên file hợp lệ không giống nhau trên mọi hệ điều hành

Một số tên hoặc ký tự được filesystem này cho phép nhưng hệ khác từ chối. Chẳng hạn, Windows có những tên device dành riêng (như `CON`, `NUL`), một số dấu phân cách và quy tắc với dấu chấm/dấu cách ở cuối. Linux chủ yếu phân biệt dấu `/` và byte NUL ở mức tên file nhưng còn phụ thuộc filesystem và tầng giao tiếp.

Một dịch vụ cho người dùng tải file lên không nên lấy tên gốc và ghép trực tiếp vào đường dẫn:

~~~java
Path target = uploadRoot.resolve(userProvidedName);
~~~

Ngoài các ký tự không hợp lệ, chuỗi có thể chứa `../` hoặc dạng đường dẫn tuyệt đối. Cần có quy tắc đặt tên được kiểm soát, kiểm file extension theo nội dung/chính sách, giới hạn độ dài và giữ dữ liệu upload ra khỏi thư mục executable/config.

### 9.1. Cách tiếp cận phổ biến: tên lưu trữ do hệ thống cấp

~~~java
String storageName = java.util.UUID.randomUUID().toString();
Path destination = uploadRoot.resolve(storageName + ".bin");
~~~

Đây là cách minh họa việc tránh dùng trực tiếp tên do người dùng cung cấp. Production còn phải kiểm soát file type, access authorization, quota, malware scanning khi cần và metadata đi kèm.

## 10. Path traversal và symbolic link: chuẩn hóa cú pháp chưa đủ

Khi một API nhận relative path từ client, đoạn code sau giúp chặn một số trường hợp lexical traversal:

~~~java
Path root = Path.of("/srv/app/uploads")
        .toAbsolutePath()
        .normalize();

Path requested = root.resolve(relativePath)
        .normalize();

if (!requested.startsWith(root)) {
    throw new SecurityException(
            "Path escapes the allowed directory");
}
~~~

Tuy nhiên, **đây chỉ là kiểm tra đường dẫn theo cú pháp**. Nếu trong `root` có symbolic link trỏ ra ngoài, đường dẫn vẫn có thể `startsWith(root)` nhưng hệ điều hành truy cập file ngoài phạm vi. Một attacker có thể thay symlink hoặc parent directory giữa lúc kiểm và lúc mở file — tình huống time-of-check/time-of-use (TOCTOU).

### 10.1. Các kiểm soát cần kết hợp

- Chỉ dùng root directory do hệ thống quản lý và có quyền truy cập tối thiểu.
- Không cho untrusted user tự thay entries/symlink trong cây thư mục nhạy cảm.
- Chặn absolute path, traversal và filename không hợp lệ theo business contract.
- Khi cần bảo đảm dưới race, cân nhắc `SecureDirectoryStream` hoặc API/thiết kế file access có kiểm soát phù hợp với filesystem provider, thay vì tách check/open.
- Khi sử dụng `NOFOLLOW_LINKS`, hiểu chính xác thao tác nào áp dụng nó và những parent path nào vẫn có thể follow link.
- Dùng quyền OS/container để giới hạn hậu quả nếu kiểm tra ứng dụng bị vượt qua.

`Files.isSymbolicLink(path)` hoặc `toRealPath()` có thể hỗ trợ điều tra, nhưng một lần check đơn lẻ không loại bỏ race. Với thao tác bảo mật nhạy cảm, thiết kế storage và permissions quan trọng hơn việc ghép thêm một phép kiểm.

## 11. Files.exists, isReadable và isWritable không bảo đảm thao tác tiếp theo thành công

Java có các phương thức:

~~~java
Files.exists(path);
Files.isReadable(path);
Files.isWritable(path);
Files.isDirectory(path);
~~~

Chúng hữu ích để kiểm tra ban đầu hoặc cung cấp thông báo rõ hơn. Tuy nhiên, trạng thái filesystem có thể thay đổi ngay sau khi kiểm; quyền POSIX/ACL, mount, network filesystem hoặc security context cũng có thể khiến kết quả khác với thao tác thực.

Cách xử lý đáng tin cậy là **thực hiện thao tác thực tế và xử lý IOException**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public static String readConfig(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

Nếu cần phân biệt lỗi, bắt những exception cụ thể như `NoSuchFileException`, `AccessDeniedException` và những `FileSystemException` khác; khi log, không lộ secrets hoặc đường dẫn nhạy cảm ngoài phạm vi cho phép.

## 12. Quyền tệp: POSIX permissions, Windows ACL và thực tế filesystem

Quyền truy cập file **không được biểu diễn giống nhau trên mọi hệ điều hành**.

| Hệ thống/quy tắc | Cơ chế phổ biến | Điều cần lưu ý |
|---|---|---|
| Linux/Unix POSIX | Owner, group, other; read/write/execute | Directory cần quyền traverse để truy cập file bên trong |
| Windows NTFS | Access Control Lists (ACL) và identity | Không thể giả lập đầy đủ bằng `chmod` |
| Container Linux | UID/GID của process, image files, mounted volume | User chạy container có thể khác owner của file |
| Network filesystem | Permission, ACL, server-side policy, mount options | Kiểm tra local có thể khác server |
| Read-only mount | Filesystem hoặc volume chỉ đọc | Dù mode bits cho phép ghi, thao tác vẫn có thể thất bại |
| Custom runtime image | File permissions của image và launcher | Có thể không chứa shell/utility để điều tra |

Không nên suy từ `Files.isWritable(path) == true` rằng ghi chắc chắn thành công. Mặt khác, lỗi ghi có thể do quota, hết đĩa, file locks hoặc mount read-only chứ không chỉ ACL.

### 12.1. Directory execute/traverse permission

Trong POSIX, quyền `x` trên **directory** cho phép đi qua đường dẫn khi kết hợp các quyền phù hợp; nó không có ý nghĩa giống bit execute của một file chương trình.

Ví dụ file có `rw-------` nhưng tiến trình không có quyền đi qua thư mục cha, việc mở file vẫn có thể bị từ chối. Vì vậy kiểm owner/mode của **mọi thư mục trên đường đi**, không chỉ file cuối.

## 13. Java NIO file attribute views

Java cung cấp những attribute views có điều kiện theo filesystem:

- `BasicFileAttributeView`: metadata cơ bản.
- `PosixFileAttributeView`: owner/group/POSIX permission bits trên filesystem phù hợp.
- `AclFileAttributeView`: access control list khi provider hỗ trợ.
- `DosFileAttributeView`: các cờ như read-only/hidden trên filesystem thích hợp.
- `FileOwnerAttributeView`: owner metadata theo khả năng provider.

Cách đúng là kiểm tra khả năng hỗ trợ và xử lý `UnsupportedOperationException` khi thao tác không được cung cấp.

### 13.1. Đọc POSIX permissions khi được hỗ trợ

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;

public static void showPermissions(Path file) throws Exception {
    Set<PosixFilePermission> permissions =
            Files.getPosixFilePermissions(file);

    System.out.println(permissions);
}
~~~

Code này có thể chạy trên một filesystem POSIX, nhưng không được dùng như phương pháp portable duy nhất: Windows hoặc provider khác có thể không hỗ trợ POSIX view.

### 13.2. Feature detection

~~~java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;

FileStore store = Files.getFileStore(path);
boolean posix =
        store.supportsFileAttributeView(
                PosixFileAttributeView.class);

System.out.println("POSIX view supported: " + posix);
~~~

Khả năng hỗ trợ phụ thuộc **filesystem/provider tại path** chứ không chỉ tên OS. Một ứng dụng chạy Linux vẫn có thể thao tác với network mount hoặc provider đặc biệt có semantics khác filesystem gốc.

## 14. Tạo file với quyền tối thiểu ngay từ đầu

Đối với secret hoặc dữ liệu nhạy cảm, không nên tạo file với quyền rộng rồi mới sửa lại quyền, vì có thể tồn tại khoảng thời gian file bị truy cập ngoài ý muốn.

Khi filesystem hỗ trợ POSIX, có thể khai báo file attributes ở lúc tạo:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.EnumSet;
import java.util.Set;

Path secretFile = Path.of("/secure/app/token.data");

Set<PosixFilePermission> permissions = EnumSet.of(
        PosixFilePermission.OWNER_READ,
        PosixFilePermission.OWNER_WRITE);

Files.createFile(
        secretFile,
        PosixFilePermissions.asFileAttribute(permissions));
~~~

Đoạn này giả định thư mục cha đã tồn tại, tiến trình có quyền tạo file và filesystem hỗ trợ POSIX attributes. Trong môi trường khác, phải dùng cơ chế permission/ACL phù hợp; không tự động fallback sang quyền toàn bộ thế giới có thể đọc.

Để tạo file an toàn trong production còn cần kiểm tranh chấp tên, file đã tồn tại, symbolic link và cấu hình directory. Đừng dùng ví dụ này như API upload hoàn chỉnh.

### 14.1. Vì sao chmod 777 là hướng sửa nguy hiểm?

Một command như `chmod -R 777 /srv/app` có thể làm chương trình ghi được nhưng mở rộng quyền đọc/ghi/thực thi cho nhiều tài khoản, bao gồm file bí mật hoặc artifact. Nó cũng có thể che cấu hình UID/GID sai.

Hướng xử lý là xác định **process identity**, owner/group của dữ liệu, mount policy và quyền tối thiểu cần thiết. Nếu thiếu quyền ghi một thư mục output, hãy cấp quyền chính xác cho service account hoặc group được phê duyệt, không thay đổi toàn bộ filesystem.

## 15. UID/GID trong container và mounted volume

Container thường chạy dưới user/UID được khai báo trong image hoặc qua Kubernetes `securityContext`. Một volume có thể được tạo với owner khác user chạy ứng dụng.

Ví dụ:

~~~text
Image filesystem:
  /app/app.jar           readable by app process
  /app/templates/        read-only

Persistent volume:
  /var/lib/app/data      owned by UID 1000
Running process:
  UID 2000
~~~

Nếu process UID 2000 không có quyền cần thiết, tạo file ở volume có thể ném `AccessDeniedException`. Trên một máy phát triển chạy bằng user khác hoặc root, lỗi không xuất hiện.

### 15.1. Đừng giải quyết bằng cách chạy root mặc định

Kiểm tra:

1. Image đang khai báo `USER` nào?
2. Pod/service có override user/group không?
3. Persistent volume và thư mục con do ai sở hữu?
4. Có group permission hoặc ACL phù hợp không?
5. Volume có được mount read-only không?
6. Security policy của cluster có hạn chế `chown` hoặc thay đổi owner không?
7. Ứng dụng thực sự cần ghi thư mục nào?

Một giải pháp bền vững là provision volume với owner/group/quyền phù hợp hoặc dùng cơ chế group như `fsGroup` khi phù hợp với cluster/driver, thay vì tăng đặc quyền của toàn process.

## 16. Đọc và ghi file theo UTF-8 có chủ đích

Khác biệt charset là nguồn lỗi thường gặp khi chuyển từ Windows sang Linux hoặc đổi JDK. Java 18 đưa UTF-8 thành default charset theo **JEP 400** cho nhiều API tiêu chuẩn, trong khi môi trường/JDK cũ có thể sử dụng default charset phụ thuộc nền tảng. Không nên mặc định **mọi dữ liệu lịch sử** đều dùng UTF-8 chỉ vì JDK mới làm vậy.

### 16.1. Chỉ rõ charset khi đọc/ghi nội dung

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("reports", "status.txt");

Files.writeString(
        file,
        "Báo cáo hoàn thành",
        StandardCharsets.UTF_8);

String content = Files.readString(
        file,
        StandardCharsets.UTF_8);
~~~

`Files.writeString`, `Files.readString` có từ Java 11. Nếu cần tương thích Java 8, dùng `Files.newBufferedReader`, `newBufferedWriter` hoặc stream với charset chỉ định.

### 16.2. Không nhầm charset nội dung với glyph của font

Nếu một chuỗi Java đã chứa tiếng Việt Unicode đúng nhưng PDF xuất ra thành hình vuông, nguyên nhân có thể là **font không hỗ trợ ký tự** hoặc thiếu font trong runtime image, không phải UTF-8.

Ngược lại, nếu ngay khi đọc file dữ liệu đã thành ký tự thay thế (�), hãy kiểm encoding input trước; cài thêm font không tự sửa chuỗi bị decode sai.

## 17. Newline và file format giữa Windows/Linux

Windows thường dùng CRLF (`\r\n`), Unix-like OS thường dùng LF (`\n`). Java có:

~~~java
String localNewline = System.lineSeparator();
~~~

Nhưng lựa chọn newline phải theo **hợp đồng file**, không phải luôn theo OS:

- File cấu hình hoặc định dạng giao thức yêu cầu LF: ghi `\n` cố định.
- Văn bản hiển thị theo OS local: có thể chọn `System.lineSeparator()`.
- CSV/JSON/XML xuất theo quy tắc riêng: dùng serializer/format specification thay vì ghép thủ công.
- Golden file trong test: normalize newline có chủ đích nếu hợp đồng cho phép, không xóa khác biệt có ý nghĩa.

Trên Windows, Git có thể chuyển đổi line endings theo setting; một script shell commit với CRLF có thể không chạy trên Linux. Đây là vấn đề packaging/source control, không phải lỗi API JVM.

## 18. File locks, open handles và hành vi xóa/đổi tên

Một ứng dụng có thể đọc xong dữ liệu nhưng vẫn giữ `InputStream`, `FileChannel` hoặc memory mapping. Sự khác nhau giữa hệ điều hành hiện rõ khi xóa/đổi tên file:

- Một số Unix-like filesystem cho phép unlink file vẫn đang được mở; handle hiện tại có thể tiếp tục truy cập nội dung.
- Trên Windows, file đang được mở với sharing mode không phù hợp có thể không xóa/đổi tên được.
- File locking và atomic move có giới hạn khác nhau trên local/network filesystems.

### 18.1. Đóng tài nguyên rõ ràng

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (InputStream input = Files.newInputStream(path)) {
    // Process file content within the resource lifetime.
}
~~~

Không dựa vào garbage collector để “tự đóng file sớm”. Với Java NIO, try-with-resources là cấu trúc nên dùng cho stream/channel.

### 18.2. Atomic write chỉ bảo đảm trong điều kiện hỗ trợ

Một kỹ thuật ghi file cấu hình là viết vào file tạm trong cùng directory rồi đổi tên:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path target = Path.of("/srv/app/config/result.txt");
Path parent = target.getParent();

Path tmp = Files.createTempFile(
        parent, "result-", ".tmp");

try {
    Files.writeString(tmp, "new content",
            StandardCharsets.UTF_8);

    Files.move(
            tmp,
            target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Decide explicitly whether a non-atomic fallback is acceptable.
    throw unsupported;
} finally {
    Files.deleteIfExists(tmp);
}
~~~

Ví dụ dành cho filesystem hỗ trợ atomic move và thư mục cha đã tồn tại. Khả năng kết hợp `ATOMIC_MOVE` với lựa chọn thay thế, behavior khi target tồn tại và atomicity thực tế phụ thuộc provider. Với file quan trọng, cần thiết kế fsync/durability và rollback phù hợp; atomic rename không tự bảo đảm dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ khi mất điện.

### 18.3. Không đồng nhất mọi filesystem

Network filesystem, object-store filesystem provider, volume mounts, overlay filesystem và ổ local có thể khác semantics lock/move/caching. Cần test thao tác thật trên storage class được dùng trong production.

## 19. Thư mục tạm: /tmp không phải chuẩn cho mọi OS

Một lỗi phổ biến:

~~~java
Path temp = Path.of("/tmp/output.pdf");
~~~

Đường dẫn `/tmp` không áp dụng giống nhau trên Windows, và một container có thể mount thư mục tạm read-only, quota thấp hoặc có chính sách dọn dẹp.

Java cung cấp:

~~~java
Path tempFile = Files.createTempFile(
        "report-", ".tmp");

try {
    // Write and process the temporary file.
} finally {
    Files.deleteIfExists(tempFile);
}
~~~

Với Java NIO, file tạm được tạo theo đường dẫn/temp directory JVM và với tên giảm nguy cơ trùng. Cần lưu ý:

- `java.io.tmpdir` có thể khác giữa JDK/OS/container.
- Temp file có thể chứa secret hoặc dữ liệu khách hàng; cần bảo vệ quyền.
- Môi trường test có thể dùng temp directory riêng.
- Không giả định file tạm sống qua restart.
- Nên giới hạn kích thước và dọn dẹp theo chính sách.
- Khi dùng thư viện ngoài cần nhận file path, phải quản lý vòng đời file.

Với dữ liệu lớn, volume tạm có thể đầy khiến ghi lỗi dù heap đủ.

## 20. Font không chỉ là tên family trong Java

Ứng dụng tạo hình ảnh, barcode, PDF, báo cáo hoặc HTML server-side có thể sử dụng `java.awt.Font`, `Graphics2D`, thư viện PDF hoặc renderer khác. Việc tạo `new Font("Some Font", ...)` **không bảo đảm font thật cùng tên tồn tại ở runtime**.

Java có **logical fonts** như `Serif`, `SansSerif`, `Monospaced`, `Dialog`, `DialogInput`. Chúng được ánh xạ sang physical fonts theo JVM, OS và cấu hình font. Một tên physical font như `Arial` hoặc `Times New Roman` có thể tồn tại trên Windows nhưng không có trong Linux container tối giản.

### 20.1. Triệu chứng font migration

| Triệu chứng | Nguyên nhân cần kiểm |
|---|---|
| Chữ tiếng Việt mất dấu/ô vuông | Font thiếu glyph, fallback không phù hợp |
| PDF/PNG có độ dài dòng khác | Font substitution và metric khác |
| Hàng trong báo cáo bị cắt | Line height/kerning/glyph metrics thay đổi |
| Font được chọn nhưng hiển thị khác | Physical font không có, logical font fallback |
| `Fontconfig`/font manager lỗi trên Linux | Thiếu fontconfig hoặc font data phù hợp |
| Ứng dụng yêu cầu X11/display | Dùng API GUI trong môi trường headless |
| Local render đúng, container render sai | Font packages, runtime image, locale, native libraries khác |

Vấn đề font và encoding liên quan trải nghiệm người dùng nhưng phải được chẩn đoán riêng. UTF-8 không tự tạo glyph mà physical font không có.

## 21. Kiểm tra font nào thực sự khả dụng

Nếu `java.desktop` có trong runtime image, có thể dùng `GraphicsEnvironment`:

~~~java
import java.awt.GraphicsEnvironment;
import java.util.Arrays;

public final class FontInventory {
    public static void main(String[] args) {
        GraphicsEnvironment environment =
                GraphicsEnvironment.getLocalGraphicsEnvironment();

        System.out.println(
                "Headless: " +
                GraphicsEnvironment.isHeadless());

        String[] fontFamilies =
                environment.getAvailableFontFamilyNames();

        Arrays.stream(fontFamilies)
                .limit(30)
                .forEach(System.out::println);
    }
}
~~~

Ví dụ chỉ in 30 font families đầu; không phải danh mục đầy đủ. `getAvailableFontFamilyNames()` không xác nhận mọi font chứa đủ glyph cho tiếng Việt. Cần test text cụ thể với font và rendering engine thực tế.

### 21.1. Kiểm glyph mà font có thể hiển thị

~~~java
import java.awt.Font;

Font font = new Font("SansSerif", Font.PLAIN, 14);

String sample = "Tiếng Việt: Đường dẫn và quyền tệp";

int firstMissing = font.canDisplayUpTo(sample);

if (firstMissing >= 0) {
    System.out.println(
            "Font cannot display character index " +
            firstMissing);
}
~~~

Đây là phép kiểm hữu ích ở cấp font, nhưng không thay thế snapshot/render test. Kết quả cuối có thể bị ảnh hưởng bởi fallback, shaping, thư viện PDF và khả năng embed font.

Nếu `Font.canDisplayUpTo` trả -1, font báo có khả năng display chuỗi theo phép kiểm này; không phải lời hứa rằng mọi đầu ra từ thư viện khác sẽ có bố cục giống nhau.

## 22. AWT headless và module java.desktop

Server thường không có GUI display. Java cung cấp headless mode cho môi trường không có keyboard, mouse hoặc display tương ứng.

Có thể xác định:

~~~java
import java.awt.GraphicsEnvironment;

boolean headless =
        GraphicsEnvironment.isHeadless();

System.out.println("Headless: " + headless);
~~~

Có thể cấu hình JVM khi phù hợp:

~~~bash
java -Djava.awt.headless=true -jar application.jar
~~~

Tuy nhiên:

- **Headless** không đồng nghĩa **không có module `java.desktop`**.
- Một số API dựng ảnh/font có thể hoạt động trong headless mode.
- Những API thực sự cần cửa sổ/display có thể ném `HeadlessException`.
- Đặt headless không tự cài font, fontconfig hoặc native libraries.
- Một số công cụ dựng ảnh/report có yêu cầu riêng về runtime và font rendering.

### 22.1. jlink có thể loại bỏ java.desktop

Khi tạo custom runtime image bằng `jlink`, nhóm có thể vô tình bỏ module cần cho `java.awt.Font` hoặc `javax.imageio`.

Ví dụ minh họa:

~~~bash
jlink \
  --add-modules java.base,java.desktop \
  --output runtime-with-desktop
~~~

Đối với ứng dụng thật, cần phân tích toàn bộ module dependencies bằng `jdeps`/build tools và khai báo modules phù hợp. Ví dụ trên không phải image hoàn chỉnh cho mọi ứng dụng Java.

Nếu `java.desktop` không được đóng gói trong runtime image, việc thêm font vào container **không tự khôi phục các Java classes bị thiếu**. Ngược lại, có `java.desktop` nhưng không có physical fonts thì hiển thị Unicode vẫn có thể sai.

## 23. Cung cấp font cùng ứng dụng khi cần kết quả ổn định

Một phương án cho sản phẩm tạo báo cáo là đóng gói font **có license phù hợp** trong resource của ứng dụng, load từ stream rồi dùng đúng font đó. Cách này giảm phụ thuộc vào bộ font cài đặt trên OS.

Ví dụ:

~~~java
import java.awt.Font;
import java.awt.FontFormatException;
import java.io.IOException;
import java.io.InputStream;

public final class ReportFonts {
    public static Font loadBodyFont()
            throws IOException, FontFormatException {

        try (InputStream stream =
                     ReportFonts.class.getResourceAsStream(
                             "/fonts/report-body.ttf")) {

            if (stream == null) {
                throw new IOException(
                        "Missing report font resource");
            }

            return Font.createFont(
                    Font.TRUETYPE_FONT,
                    stream).deriveFont(12f);
        }
    }
}
~~~

Ví dụ giả định `report-body.ttf` là font hợp lệ được phép phân phối cùng ứng dụng. Không được tải hoặc đóng gói font thương mại nếu license không cho phép.

### 23.1. Đóng gói font chưa đồng nghĩa PDF embed đúng

Một số thư viện PDF hoặc report có engine font riêng. `Font.createFont` tạo đối tượng phục vụ Java2D; thư viện PDF có thể cần thêm thao tác **register/embed font** theo API của nó.

Với PDF có chữ tiếng Việt, cần kiểm:

- Font có đủ Unicode glyph không?
- Có được embed vào file PDF đúng cách không (nếu sản phẩm yêu cầu)?
- Có bị thay thế font ở môi trường xem PDF khác không?
- Có vấn đề shaping/combining marks không?
- File có thể copy/search chữ Unicode đúng không?
- License có cho phép embedding/distribution không?

Không chỉ kiểm “render đúng trong IDE” rồi tin PDF sẽ giống trên Linux server.

### 23.2. Fontconfig trên Linux

Một số Java runtimes dựa vào cấu hình font của OS (ví dụ fontconfig và bộ font được cài). Image tối giản có thể thiếu chúng. Nếu report renderer cần font từ OS, phải đảm bảo image chứa các package/font cần thiết và pin version/digest cho tính tái lập.

Trên hệ thống Linux có công cụ phù hợp, có thể điều tra:

~~~bash
fc-list
fc-match sans-serif
~~~

Các lệnh này **không phải Java API** và có thể không có trong minimal container. Không coi việc chúng vắng mặt là bằng chứng JVM không hỗ trợ font; cần xem môi trường thực tế và thư viện rendering.

## 24. Packaging: JAR/WAR, resource directory và custom runtime image

Một artifact deployable có thể có nhiều thành phần:

~~~text
app/
  app.jar                    # application bytecode
  lib/                       # external dependencies, nếu cách đóng gói yêu cầu
  config/                    # file cấu hình triển khai (có thể mount)
  fonts/                     # physical font assets, nếu cần và được cấp phép
  native/                    # shared libraries theo OS/architecture
  data/                      # persistent volume, không nhất thiết nằm trong image
  logs/                      # writable output, nếu thiết kế dùng file logs
~~~

Không phải mọi ứng dụng cần cấu trúc này. Với executable fat JAR, resource có thể nằm trong JAR; với WAR, servlet container quản lý classloader/resource; với `jlink`, Java runtime modules có thể bị rút gọn.

### 24.1. Ma trận file: nhúng hay mount?

| Thành phần | Nhúng vào artifact | Mount/cấp từ môi trường | Lưu ý |
|---|---|---|---|
| Template bất biến | Thường phù hợp | Có thể nếu cần tùy biến | Đọc bằng classpath stream khi nhúng |
| Config theo môi trường | Thường không | Phù hợp | Validate schema và phân quyền |
| Secret/private key | Tránh nhúng | Secret mechanism | Không log hoặc commit giá trị |
| Font được phép phân phối | Có thể | Có thể qua OS/image | Kiểm Unicode, license, version |
| User uploads | Không | Persistent storage | Quota, ACL, traversal protection |
| Log/runtime temp | Không | Writable volume/stdout/temp | Rotation và giới hạn |
| Native library | Có thể theo OS-specific artifact | Có thể trong image | OS/architecture/ABI tương thích |

Dù file được nhúng hay mount, đường dẫn và vòng đời phải rõ. Một thay đổi từ exploded WAR sang executable JAR có thể phá code dựa vào physical path của resource.

## 25. Native libraries và giả định về OS/architecture

Ngoài path và font, ứng dụng có thể dùng thư viện native hoặc Java agent cần file binary theo nền tảng:

- Linux: thường có `.so`.
- macOS: thường có `.dylib`.
- Windows: thường có `.dll`.

Nếu một JAR nạp `libcodec.so` được build cho x64 trên ARM64, hoặc dựa vào một phiên bản libc khác, lỗi có thể là `UnsatisfiedLinkError` hay crash native.

Không sửa bằng cách thay dấu `/` thành `\` hoặc chỉ thêm `java.library.path` nếu binary thực sự không tương thích. Cần xem:

1. OS và CPU architecture.
2. ABI, libc/native dependencies.
3. Quyền đọc/execute trên file và thư mục.
4. Cách library được đóng gói hoặc unpack.
5. Native access restrictions của JDK mục tiêu khi liên quan.
6. Error logs, vendor support matrix và artifact checksum.

Sự khác nhau giữa path portability và native binary portability là hai lớp kiểm tra độc lập.

## 26. Giới hạn hệ điều hành của ProcessBuilder và external tools

Một số ứng dụng gọi `wkhtmltopdf`, `ffmpeg`, `git` hoặc shell script. Đường dẫn executable, environment variables, quoting và shell syntax có thể khác giữa Windows và Linux.

Nên dùng `ProcessBuilder` để truyền từng argument thay vì tự xây một command string ghép với input chưa tin cậy:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

Path executable = Path.of(
        System.getenv("REPORT_RENDERER"));

ProcessBuilder builder = new ProcessBuilder(
        List.of(
                executable.toString(),
                "--output",
                "/srv/app/out/report.pdf"));

Process process = builder.start();
int exitCode;

try {
    exitCode = process.waitFor();
} catch (InterruptedException interrupted) {
    process.destroyForcibly();
    Thread.currentThread().interrupt();
    throw interrupted;
}

if (exitCode != 0) {
    throw new IOException(
            "Report renderer failed: " + exitCode);
}
~~~

Ví dụ chỉ minh họa cấu trúc ProcessBuilder, chưa xử lý stdout/stderr, timeout, validation executable, giá trị environment chưa có hoặc việc quản lý file output. Production cần tránh deadlock do không đọc stdout/stderr, giới hạn thời gian và không truyền nội dung user input vào shell một cách không an toàn.

Điểm quan trọng là **không giả định Linux command tồn tại trên Windows** hoặc ngược lại. Nếu một tool là dependency runtime, phải khai báo/cài/kiểm nó theo môi trường mục tiêu.

## 27. Kiểm tra môi trường bằng Java mà không phụ thuộc shell riêng

Một diagnostic nhỏ có thể hỗ trợ điều tra khi application đã được triển khai:

~~~java
import java.awt.GraphicsEnvironment;
import java.nio.charset.Charset;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.util.Locale;

public final class EnvironmentProbe {
    public static void main(String[] args) {
        System.out.println("Java version: " +
                System.getProperty("java.version"));
        System.out.println("Java vendor: " +
                System.getProperty("java.vendor"));
        System.out.println("OS: " +
                System.getProperty("os.name"));
        System.out.println("OS arch: " +
                System.getProperty("os.arch"));
        System.out.println("File separator: " +
                FileSystems.getDefault().getSeparator());
        System.out.println("Working directory: " +
                Path.of(".").toAbsolutePath().normalize());
        System.out.println("Temp directory: " +
                System.getProperty("java.io.tmpdir"));
        System.out.println("Default charset: " +
                Charset.defaultCharset());
        System.out.println("Default locale: " +
                Locale.getDefault());
        System.out.println("Headless: " +
                GraphicsEnvironment.isHeadless());
    }
}
~~~

Ví dụ dùng `java.desktop` cho phần headless. Nếu runtime image không có module này, phải bỏ phần GraphicsEnvironment hoặc cung cấp module theo yêu cầu ứng dụng.

Trong production, không xuất tất cả thông tin hệ thống hoặc đường dẫn nội bộ lên một endpoint công khai. Chỉ dùng diagnostic phù hợp quyền truy cập và log redaction.

### 27.1. Vì sao phải ghi cả JDK và OS?

Cùng Java 21 trên hai platform có thể khác:

- File path syntax và case sensitivity.
- Font availability và font substitution.
- Native library availability.
- Permission model và file sharing.
- Local charset/timezone/locale configuration.
- Container mount/cgroup và user identity.
- Filesystem provider/support của attribute views.

Đó là lý do một bug phát sinh “sau nâng Java” có thể thực chất do deployment chuyển từ máy Windows sang Linux container trong cùng đợt.

## 28. Đưa vấn đề vào unit test và integration test thế nào?

Không nên chỉ viết một test xác minh `Path.of("a", "b")`. Test cần mô phỏng đúng contract ở những tầng có khả năng khác nhau.

### 28.1. Unit tests cho xử lý Path

- Path tương đối và tuyệt đối.
- Filename không hợp lệ hoặc có ký tự đặc biệt.
- Unicode, khoảng trắng và dấu tiếng Việt.
- `.`, `..` và traversal.
- Tên không phân biệt case nếu logic ứng dụng yêu cầu.
- File missing và invalid input.
- URL/resource name đúng/chưa có trong JAR.

Ví dụ JUnit 5 với thư mục tạm:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FileStoreTest {
    @TempDir
    Path tempDir;

    @Test
    void readsUtf8Text() throws Exception {
        Path file = tempDir.resolve("bao-cao.txt");
        Files.writeString(
                file,
                "Đường dẫn hợp lệ",
                StandardCharsets.UTF_8);

        assertEquals(
                "Đường dẫn hợp lệ",
                Files.readString(
                        file, StandardCharsets.UTF_8));
    }
}
~~~

Ví dụ giả định có JUnit Jupiter dependency và dùng Java 11+. Dùng `@TempDir` tốt hơn hardcode `/tmp/my-test`, nhưng vẫn cần xác định test filesystem và quyền trong CI.

### 28.2. Integration tests cho quyền tệp

Cần có các case:

- Process có quyền đọc nhưng không ghi.
- Process không có quyền truy cập thư mục cha.
- Output directory read-only.
- Volume không tồn tại.
- File đã tồn tại hoặc bị lock.
- Dung lượng/quota bị giới hạn trong môi trường test khi cần.
- Native binary/font resource được mount/đóng gói đúng.

Không nên chạy test phá hoại quyền hoặc fill disk trên production. Dùng môi trường cô lập và quota test có kiểm soát.

### 28.3. Snapshot/golden tests cho font

Để phát hiện khác biệt font sau đổi image/JDK, thử:

- Chuỗi tiếng Việt có dấu: `Đường dẫn, quyền tệp, ảnh hưởng môi trường`.
- Ký tự tổ hợp và ký tự ngoài ASCII.
- Chữ in đậm/nghiêng, số và dấu câu.
- Các kích thước trang hoặc hình ảnh khác nhau.
- Kết quả khi font vật lý không có.
- File PDF có thể copy/search text đúng nếu contract yêu cầu.

Snapshot ảnh có thể thay đổi do anti-aliasing, renderer hoặc JDK, nên cần xác định mức so sánh hợp lý và cố định font/runtime nếu yêu cầu output pixel-identical.

## 29. Ma trận thử nghiệm theo môi trường

Một ma trận gợi ý cho ứng dụng vừa chạy trên máy developer vừa deploy Linux container:

| Môi trường | Path/resources | Permissions | Fonts/headless | Packaging/runtime |
|---|---|---|---|---|
| Windows developer | Drive path, case, resource in IDE | ACL, file locks | Physical fonts local | IDE/CLI JDK |
| Linux CI | Case-sensitive paths, clean JAR | Non-root user, temp dir | Font availability/Unicode | Clean build + test |
| Linux container staging | Volume mount, absolute config paths | UID/GID, read-only rootfs | fontconfig, headless, render | Same image lineage as production |
| macOS developer (nếu hỗ trợ) | Unicode normalization, path case | POSIX ACL/provider | macOS fonts | Local toolchain |
| Production | Actual persistent storage | Real service account | Approved font set | Exact JDK/image digest |

Không cần giả định mọi dự án bắt buộc hỗ trợ đầy đủ cả ba OS. Nếu sản phẩm chỉ chạy trên Linux production, ma trận vẫn nên bao phủ Linux CI/container và xác định các khác biệt giữa máy phát triển với runtime được hỗ trợ.

### 29.1. Những case bắt buộc ở JAR đóng gói

Chạy **artifact đóng gói thật**, không chỉ chạy từ IDE:

- Resource stream tìm được file bên trong JAR không?
- File ngoài JAR được đọc theo config path chính xác không?
- Thư mục ghi output có tồn tại và có quyền không?
- Font của report có được load và render trên headless image không?
- Runtime image có module `java.desktop` nếu cần không?
- Đường dẫn native library có hợp lệ không?
- Log/dump/temp được ghi ở path cho phép không?
- File handle có được đóng trước thao tác delete/move không?

Một số lỗi chỉ xuất hiện khi mọi resource được đóng gói lại hoặc khi chạy dưới user không đặc quyền.

## 30. Kế hoạch migration từ Windows/VM sang Linux container

Đây là một tình huống thường xảy ra khi nâng Java 8 lên 17/21 đồng thời hiện đại hóa deployment.

### Bước 1: Kiểm kê phụ thuộc vào OS

Tìm những chuỗi path hardcode, lệnh shell, tên font, file encoding, thư mục tạm, native binaries, registry/environment và giả định về file locks/case sensitivity.

### Bước 2: Phân loại loại file

Tách resource nằm trong artifact, config ngoài, secret, persistent data, temp, logs và native/fonts assets. Mỗi loại có ownership và deployment policy riêng.

### Bước 3: Chuẩn hóa Java Path/Files

Thay ghép path thủ công bằng `Path.resolve`; dùng `Files` và streams phù hợp. Xử lý IOException và không giả định working directory.

### Bước 4: Sửa resource loading

Đọc template/classpath resource qua `getResourceAsStream`. Nếu API cần physical path, copy resource theo vòng đời được quản lý; không dùng `src/main/resources` ở runtime.

### Bước 5: Thiết kế permissions trước khi triển khai

Xác định user/UID/GID, mount, owner, ACL/mode, writable dirs và temporary storage. Không giải quyết bằng root hoặc `chmod 777` theo mặc định.

### Bước 6: Đóng gói fonts/native assets có chủ đích

Chọn font có license phù hợp, đủ glyph; dùng resource hoặc OS font packages được pin. Kiểm OS-native libraries và module `java.desktop` nếu cần.

### Bước 7: Đặt rõ charset, newline, locale và timezone

Dùng UTF-8 cho dữ liệu có hợp đồng UTF-8; chọn định dạng newline theo format; không suy ngày giờ từ timezone mặc định nếu nghiệp vụ yêu cầu zone cụ thể.

### Bước 8: Thử artifact thật trong image thật

Chạy dưới service account không đặc quyền, với volumes, read-only mount và tài nguyên của staging tương tự production.

### Bước 9: Chạy negative tests

Kiểm missing config, directory read-only, filename không hợp lệ, font missing, symlink/traversal và resource path sai.

### Bước 10: Ghi bằng chứng và rollout

Lưu OS/JDK/build/image digest, file permission model, các volume, font packages, kết quả render và logs. Chỉ triển khai khi các rủi ro còn lại được ghi rõ và có phương án khôi phục.

## 31. Case study A: file nằm trong JAR nhưng code cố đọc từ ổ đĩa

**Hiện tượng:** IDE đọc được `src/main/resources/templates/invoice.html`. Sau khi tạo executable JAR và chạy container, log báo `NoSuchFileException`.

**Nguyên nhân:** code đang dùng path của source checkout, không phải classpath resource.

**Hướng xử lý:** chuyển template bất biến sang `getResourceAsStream("/templates/invoice.html")`; xác minh template thật sự có trong packaged JAR; nếu thư viện renderer chỉ nhận physical file, copy resource ra file tạm được quản lý và đóng/mở file đúng vòng đời.

**Bằng chứng:** test đọc resource từ artifact đã đóng gói, không chỉ test IDE.

## 32. Case study B: ghi file thất bại khi container chạy non-root

**Hiện tượng:** `Files.writeString` chạy trong local nhưng container trả `AccessDeniedException` tại `/var/lib/app/data/report.txt`.

**Nguyên nhân khả dĩ:** volume owner không khớp UID process, thư mục cha thiếu traverse permission, mount chỉ đọc hoặc filesystem policy hạn chế.

**Hướng xử lý:** ghi nhận UID/GID runtime, kiểm owner/mode/ACL và mount flags, provision writable directory đúng quyền. Giữ process chạy theo nguyên tắc least privilege.

**Không nên:** chuyển container sang root hoặc áp `chmod -R 777` nếu chưa đánh giá; chúng làm giảm bảo vệ hệ thống và không giải quyết nguyên nhân thiết kế.

**Bằng chứng:** integration test tạo/đọc/xóa file trên volume dưới đúng identity production.

## 33. Case study C: báo cáo PDF bị mất dấu tiếng Việt

**Hiện tượng:** cùng dữ liệu `"Đường dẫn và quyền tệp"`, file PDF render đúng trên Windows nhưng thiếu dấu khi chạy image Linux tối giản.

**Nguyên nhân khả dĩ:** font dùng trong code không tồn tại trong container, font substitution khác, thiếu glyph hoặc fontconfig/Java desktop setup không đủ; cũng có thể là lỗi decoding dữ liệu trước khi render.

**Hướng xử lý:**

1. Xác nhận chuỗi Java trước khi render có Unicode đúng.
2. Kiểm `java.desktop` và headless mode.
3. Kiểm physical font được resolve và khả năng hiển thị glyph.
4. Cung cấp font được phép phân phối hoặc cài font package cần thiết.
5. Nếu dùng thư viện PDF, cấu hình embedding và font fallback theo API của thư viện.
6. Render test trên image thực, kiểm cả hiển thị lẫn copy/search text theo contract.

**Bằng chứng:** screenshot/golden PDF hoặc image test có tiếng Việt với JDK/image đã ghi version.

## 34. Case study D: file không xóa được trên Windows

**Hiện tượng:** test tạo file rồi xóa thành công trên Linux CI nhưng bị access/locking error trên Windows.

**Nguyên nhân khả dĩ:** `InputStream`, `FileChannel` hoặc một thư viện giữ file handle; OS chia sẻ/quy tắc delete khác.

**Hướng xử lý:** dùng try-with-resources, kiểm stream/lazy parser/renderer thực sự đóng resource; tách trường hợp file bị mở bởi tiến trình khác. Nếu xóa/move chỉ được hỗ trợ dưới semantics nhất định, cập nhật hợp đồng và test theo OS.

**Không nên:** vòng lặp retry vô hạn để che file handle leak. Retry có giới hạn chỉ phù hợp khi xác định lỗi tạm thời và có backoff, timeout, observability.

## 35. Những hiểu lầm thường gặp

**“Java chạy ở mọi nơi nên path nào cũng portable.”** Java cung cấp API đa nền tảng, nhưng filesystem semantics, permission và packaging vẫn khác nhau.

**“`/` và `\` có thể thay tự do trong mọi path.”** Không. Dùng `Path` và filesystem provider, tránh tự phân tích chuỗi.

**“`java -jar` tự lấy working directory là nơi chứa JAR.”** Không có bảo đảm đó.

**“File trong `src/main/resources` luôn tồn tại như file vật lý khi chạy production.”** Không. Thường resource nằm bên trong JAR/WAR.

**“`Path.normalize()` chặn được toàn bộ traversal.”** Không. Symbolic links, filesystem races và authorization cần xử lý thêm.

**“`Files.exists()` và `isWritable()` đảm bảo thao tác sau sẽ thành công.”** Không. Filesystem có thể đổi trạng thái và có nhiều điều kiện khác.

**“Linux permissions giống Windows ACL.”** Không. Kiểm attribute view theo provider; tránh áp POSIX API vô điều kiện.

**“Dùng root hoặc chmod 777 là cách sửa permission nhanh và an toàn.”** Không. Nó mở rộng quyền và che lỗi owner/mount.

**“Dữ liệu UTF-8 đúng thì font chắc chắn render tiếng Việt.”** Không. Font cần hỗ trợ glyph và renderer phải chọn/embed đúng.

**“Bật headless sẽ loại bỏ mọi vấn đề font.”** Không. Headless không tự cài font hoặc thay thế module `java.desktop`.

**“Có `java.desktop` thì chắc chắn có Arial/Times New Roman.”** Không. Bộ physical fonts phụ thuộc image/OS/config.

**“File handle sẽ được GC đóng kịp lúc.”** Không nên dựa vào GC để đóng tài nguyên; dùng try-with-resources.

**“`ATOMIC_MOVE` hoạt động giống nhau trên mọi filesystem.”** Không. Phụ thuộc provider, mount và thao tác thực tế.

**“Test chạy trong IDE chứng minh đóng gói đúng.”** Không. Cần test artifact đã package trên runtime mục tiêu.

**“Nâng JDK gây lỗi font hoặc quyền file nên cần downgrade JDK.”** Trước hết phải phân biệt sự thay đổi trong Java runtime với image, OS, config và quyền của tiến trình.

## 36. Checklist trước khi triển khai

- [ ] Đã ghi JDK feature/update/vendor, OS/architecture và container image nguồn/đích.
- [ ] Đã kiểm kê file resources, external config, secrets, persistent data, temp, logs và native assets.
- [ ] Đã bỏ hardcoded absolute paths đặc thù máy phát triển.
- [ ] Đã dùng `Path.resolve` và API NIO phù hợp, không ghép separator thủ công.
- [ ] Đã xác định working directory và mọi relative path còn được hỗ trợ.
- [ ] Đã đọc classpath resources bằng stream khi chúng nằm trong JAR/WAR.
- [ ] Đã kiểm clean package và run từ artifact đóng gói.
- [ ] Đã kiểm case sensitivity, Unicode normalization và filename restrictions trên OS đích.
- [ ] Đã chặn path traversal và xem xét symbolic link/TOCTOU khi input không tin cậy.
- [ ] Đã phân biệt POSIX permissions, ACL, owner/group và filesystem provider.
- [ ] Đã xác nhận UID/GID của service/container và quyền đối với volume.
- [ ] Đã hạn chế quyền thay vì chạy root hoặc chmod 777.
- [ ] Đã kiểm các thao tác read/write/delete/move và đóng file handles.
- [ ] Đã xử lý atomic write theo khả năng filesystem và yêu cầu durability.
- [ ] Đã sử dụng thư mục tạm được cấp, có quota và cơ chế dọn dẹp.
- [ ] Đã chỉ rõ charset và định dạng newline theo hợp đồng dữ liệu.
- [ ] Đã kiểm bộ font thật, Unicode glyph, font fallback và licensing.
- [ ] Đã kiểm `java.desktop`, headless mode và custom runtime image.
- [ ] Đã kiểm native libraries và external tools theo OS/architecture nếu có.
- [ ] Đã chạy unit/integration/negative tests dưới đúng service identity.
- [ ] Đã test image/container/volume gần với production.
- [ ] Đã ghi artifact digest, config paths, kết quả render, log và giới hạn kiểm thử.
- [ ] Đã có owner, rollout và phương án rollback/roll-forward khi gặp lỗi.

## 37. Nguồn tài liệu để đối chiếu

Khi triển khai trong một dự án cụ thể, nên dùng API docs và tài liệu JDK đúng release:

- **Java NIO `Path` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html
- **Java NIO `Files` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- **`PosixFilePermissions`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- **`GraphicsEnvironment`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/GraphicsEnvironment.html
- **`Font` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/Font.html
- **JEP 400 — UTF-8 by Default (JDK 18):** https://openjdk.org/jeps/400
- **Java Platform Module System:** https://openjdk.org/projects/jigsaw/spec/

Những nguồn trên giúp xác định API/semantics; còn quyền file, font availability và hành vi filesystem cần được kiểm trên **OS, container và runtime đã triển khai thật**. Khi target JDK khác Java 21, tra tài liệu của JDK đó để kiểm option/API availability.

## Kết luận

**Đường dẫn, quyền tệp, font và các giả định về hệ điều hành là một phần của hợp đồng vận hành khi nâng Java.** Một ứng dụng có thể hoàn toàn source-compatible và binary-compatible với JDK mới nhưng vẫn fail khi chạy trong JAR, WAR, `jlink` image hoặc container vì working directory khác, resource không còn là file vật lý, process thiếu quyền, filesystem có semantics khác hoặc image thiếu font.

Cách migration bền vững là xác định loại dữ liệu/tệp, dùng `Path` và `Files` theo contract rõ ràng, đọc resource trong JAR qua stream, quản lý quyền theo user và filesystem thực tế, cung cấp font/desktop module khi cần, xử lý Unicode/charset/newline có chủ đích, rồi **kiểm thử artifact đóng gói dưới đúng runtime và identity production**. Khi mọi giả định OS được khai báo và có bằng chứng, việc nâng JDK sẽ không còn phụ thuộc vào những điều kiện “tình cờ đúng” trên một máy phát triển.
