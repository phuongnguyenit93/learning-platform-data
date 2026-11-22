# Quyền và tính hỗ trợ theo hệ điều hành khi liên kết tệp (Java NIO.2)

Liên kết tệp (file link) cho phép nhiều đường dẫn tham chiếu tới cùng dữ liệu hoặc cho phép một đường dẫn chuyển hướng sang đường dẫn khác. Trong Java, API `java.nio.file.Files` hỗ trợ **symbolic link** (liên kết mềm) và **hard link** (liên kết cứng), nhưng thao tác thành công hay không phụ thuộc vào **hệ điều hành, hệ thống tệp, quyền của tiến trình và chính sách bảo mật tại thời điểm chạy**. Việc biên dịch thành công trên Java 17+ không bảo đảm có thể tạo mọi loại liên kết trên mọi máy.

## 1. Hiểu đúng đối tượng được cấp quyền

| Tiêu chí | Symbolic link (symlink) | Hard link |
| --- | --- | --- |
| Cơ chế | Một mục hệ thống tệp lưu **đường dẫn đích**; hệ điều hành phân giải đích khi truy cập. | Một tên/mục thư mục khác cùng trỏ đến **đối tượng tệp hiện có** (thường cùng định danh tệp). |
| Đích khi tạo | Có thể chưa tồn tại: tạo ra *dangling symlink*. | Đối tượng hiện có phải tồn tại; thông thường tệp thường, không phải thư mục. |
| Tác động khi đổi/xóa tên đường dẫn gốc | Link có thể bị gãy nếu đường dẫn lưu trong link không còn hợp lệ. | Hard link khác vẫn truy cập được dữ liệu dù xóa tên gốc, miễn còn một liên kết/tệp đang được hệ thống giữ. |
| Hệ thống tệp khác | Có thể chứa đường dẫn tới nơi khác; truy cập chỉ thành công khi đích tới được. | Thường bắt buộc cùng một hệ thống tệp/volume. |
| Quyền truy cập | Quyền khi mở nội dung áp dụng theo đích thực tế và các thư mục trên đường đi. | Các tên chia sẻ cùng đối tượng nên quyền trên đối tượng tệp thường chung; quyền đổi tên/xóa mục thư mục vẫn phụ thuộc thư mục cha. |
| API Java | `Files.createSymbolicLink(link, target)` | `Files.createLink(link, existing)` |

Ví dụ: `/data/report.txt` là tệp thật; `/work/report-link.txt` có thể là symlink lưu `/data/report.txt`; còn `/data/report-copy-name.txt` là hard link tới đúng đối tượng tệp của `/data/report.txt`. **Hard link không tự sao chép bytes**. Tên gọi “shortcut” của Windows (`.lnk`) là định dạng tệp của Shell và **khác** symbolic link của hệ thống tệp: `Files.createSymbolicLink` không tạo `.lnk`.

Một **đường dẫn** (`Path`) là tên để định vị; một **đối tượng tệp** là tài nguyên được hệ thống tệp quản lý. Phân biệt hai thứ này giúp lý giải việc xóa link, quyền truy cập và thay đổi nội dung.

## 2. Những API Java cần dùng và quy tắc theo link

| API | Ý nghĩa, điểm cần nhớ |
| --- | --- |
| `Files.createSymbolicLink(link, target)` | Tạo symlink; `target` có thể là đường dẫn tương đối hoặc tuyệt đối. Đây là thao tác *tùy chọn* theo provider và quyền. |
| `Files.createLink(link, existing)` | Tạo hard link tới tệp hiện có; có thể bị từ chối do khác file store hoặc chính sách hệ thống. |
| `Files.isSymbolicLink(path)` | Kiểm tra bản thân mục `path` có phải symlink; không cần mở nội dung đích. |
| `Files.readSymbolicLink(path)` | Lấy **đường dẫn được lưu** trong symlink; không tự chuyển thành absolute hay kiểm tra đích tồn tại. |
| `Files.exists(path)` | Mặc định đi theo symlink; nếu đích không tồn tại có thể trả `false`. Cũng trả `false` khi không thể xác định sự tồn tại. |
| `Files.exists(path, LinkOption.NOFOLLOW_LINKS)` | Kiểm tra mục link, kể cả khi đích của nó bị gãy. |
| `Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)` | Xem metadata của link thay vì của đối tượng đích. |
| `path.toRealPath()` | Trả đường dẫn thật sau phân giải liên kết (theo mặc định), yêu cầu đường dẫn tồn tại. `toRealPath(NOFOLLOW_LINKS)` áp dụng chính sách không theo symlink. |
| `Files.isSameFile(a, b)` | So sánh hai đường dẫn có định danh cùng tệp hay không, có thể phát sinh `IOException`; hữu ích để kiểm chứng hard link. |
| `Files.delete(path)` | Nếu `path` là symlink, xóa **mục symlink**, không xóa tệp đích. Nếu xóa một hard link, xóa một tên của tệp. |
| `Files.walkFileTree(root, visitor)` | Mặc định **không** theo symlink tới thư mục. Bật `FileVisitOption.FOLLOW_LINKS` chỉ khi thật sự cần và xử lý vòng lặp. |

Với symlink tương đối, `target` được diễn giải **tương đối từ thư mục chứa link**, không phải working directory của Java. Ví dụ tạo `/app/links/log` trỏ tới `../logs/current.log` sẽ phân giải đến `/app/logs/current.log`. Nếu di chuyển chính link sang thư mục khác, ý nghĩa của target tương đối có thể thay đổi. `Path.normalize()` chỉ chuẩn hóa cú pháp dấu `.`/`..`; nó **không** mở link để xác nhận đích thực.

Một số khác biệt dễ bỏ sót:

- `Files.readString(link)` và nhiều thao tác đọc nội dung thường đi theo symlink; nhưng các API có tham số `LinkOption` cho phép chọn hành vi khác.
- `Files.copy(sourceLink, target)` mặc định sao chép **nội dung đích** của symlink nguồn; `Files.copy(sourceLink, target, LinkOption.NOFOLLOW_LINKS)` yêu cầu sao chép chính link khi được hỗ trợ. Không mặc định rằng thao tác sao chép/move nào cũng dereference giống nhau.
- `Files.move(sourceLink, dest)` di chuyển mục symlink nguồn, không đổi đường dẫn lưu trong link thành một đích “mới” cho bạn; hãy kiểm tra lại link tương đối sau khi di chuyển.
- `Files.walk` hoặc `walkFileTree` khi được bật `FOLLOW_LINKS` có thể gặp chu trình; `FileSystemLoopException` hoặc lỗi I/O liên quan phải được xử lý. Với cây dữ liệu người dùng cung cấp, mặc định không theo link thường an toàn hơn.

## 3. Điều kiện quyền: tạo link khác với truy cập tệp đích

Khi dùng `Files.createSymbolicLink(link, target)` hoặc `Files.createLink(link, existing)`, cần tách ba câu hỏi:

1. **Có quyền tạo mục mới tại thư mục chứa `link` không?** Trên Unix/POSIX, thường cần quyền ghi (`w`) và đi xuyên/truy cập (`x`) thư mục cha; còn ACL, sticky bit, mount hoặc chính sách bảo mật cũng có thể ảnh hưởng. Trên Windows, quyền này liên quan ACL/permission của thư mục và token tiến trình.
2. **Có quyền tạo loại link đó không?** Symlink/hard link có ràng buộc riêng của hệ điều hành, driver và file store. Ví dụ Windows có cơ chế đặc quyền tạo symlink; một số filesystem không hỗ trợ kiểu link đang yêu cầu.
3. **Có quyền thao tác với đích khi sử dụng link không?** Một symlink tạo được vẫn có thể trỏ đến tệp mà người gọi không có quyền đọc. Đổi tên hay xóa mục link có thể thành công trong khi đọc nội dung đích thất bại, và ngược lại.

Đối với Unix/POSIX, **9 bit `rwx`** gắn với owner/group/others. Với *tệp*, `r` cho phép đọc nội dung, `w` cho phép sửa nội dung, `x` cho phép thực thi theo cơ chế OS. Với *thư mục*, `r` hỗ trợ liệt kê tên, `w` hỗ trợ sửa mục con, `x` cho phép tìm kiếm/đi xuyên đường dẫn; cần kết hợp quyền hợp lệ trên các thư mục cha. Quyền của chính symlink trên nhiều hệ Unix không đóng vai trò kiểm soát đọc dữ liệu đích; quyền đích và đường đi mới quyết định. Không giả định rằng `chmod` trên symlink sẽ điều khiển quyền tệp đích theo cách mong muốn.

Với hard link, quyền trên nội dung tệp thường áp dụng cho **cùng đối tượng** qua tất cả tên. Việc xóa một tên thường xét quyền của thư mục chứa tên đó, không đơn thuần quyền `w` của tệp. Các hệ thống có thể hạn chế tạo hard link tới tệp không thuộc sở hữu người gọi, cấm hard link tới thư mục hoặc ngăn các kiểu truy cập có rủi ro.

`Files.isReadable(path)`, `Files.isWritable(path)` và `Files.isExecutable(path)` chỉ cho một **kiểm tra tại thời điểm gọi**. Kết quả có thể không phản ánh đầy đủ ACL, trạng thái tệp mở, sandbox, mount và thay đổi đồng thời; chúng **không cấp quyền**, cũng không thay thế xử lý `AccessDeniedException`/`IOException` trong thao tác thực tế. Không tạo chuỗi bảo mật `if (Files.isWritable(p)) Files.writeString(p, ...)` rồi xem điều kiện đầu là bảo đảm.

## 4. Tính hỗ trợ theo hệ điều hành và hệ thống tệp

| Môi trường | Symbolic link | Hard link | Cấp quyền và thuộc tính |
| --- | --- | --- | --- |
| **Linux / Unix** với hệ thống tệp hỗ trợ (ví dụ ext4) | Thường hỗ trợ link tới tệp/thư mục, kể cả đích tương đối và đích chưa tồn tại. | Thường hỗ trợ các tên cùng file store; hard link tới thư mục thường bị hạn chế/cấm. | Mode POSIX `rwx`, owner/group, ACL nếu filesystem cấu hình hỗ trợ; mount/chính sách bảo mật có thể giới hạn thêm. |
| **macOS** với APFS và cấu hình thông thường | Hỗ trợ symlink; link tương đối và dangling link có ý nghĩa tương tự Unix. | Hỗ trợ hard link cho tệp trong giới hạn filesystem; không suy rộng sang thư mục. | POSIX permissions, owner/group và cơ chế ACL/phân quyền bổ sung. |
| **Windows** với NTFS | Hỗ trợ symbolic link kiểu filesystem; quyền tạo có thể phụ thuộc đặc quyền, Developer Mode, chính sách máy và cách JDK/provider gọi API. | NTFS có hard link cho tệp; yêu cầu cùng volume và các điều kiện của OS. | ACL Windows là cơ chế chính; `DosFileAttributeView` thể hiện thuộc tính như read-only/hidden, **không tương đương** POSIX `rwx`. |
| **FAT/exFAT, ổ mạng, container, filesystem ảo/provider bên thứ ba** | Khả năng hỗ trợ tùy filesystem, server, mount và provider; có thể hoàn toàn không tạo được. | Tương tự; qua các filesystem/volume thường không được. | Attribute views và chính sách quyền có thể khác hệ điều hành host. |

Các ví dụ trong bảng mô tả **cấu hình thường gặp**, không phải hợp đồng bảo đảm của Java. `System.getProperty("os.name")` chỉ cho biết tên hệ điều hành; không cho biết ổ chứa `Path` có hỗ trợ symlink, hard link, POSIX, ACL hay không. Ứng dụng cần kiểm tra tại **file store thực** và thử thao tác được phép, xử lý lỗi cụ thể.

Trên Windows, tài liệu Microsoft mô tả việc tạo symbolic link bằng Win32 có thể yêu cầu quyền tương ứng; cờ `SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE` hoạt động trong điều kiện Developer Mode đã bật. **Không suy ra rằng chỉ bật Developer Mode thì mọi bản JDK/provider và mọi volume đều chắc chắn tạo được symlink**; Java chỉ cam kết báo lỗi khi không thực hiện được. Máy cơ quan có thể áp chính sách riêng. Việc bật Developer Mode là thay đổi cấu hình máy và không phải cách xử lý duy nhất hay tự động của chương trình Java.

Trong Docker/Kubernetes, CI, máy chủ dùng filesystem ảo hoặc shared folder, một đoạn code thành công ở máy lập trình vẫn có thể thất bại do user ID, read-only mount, symlink policy, quyền volume hoặc driver lưu trữ. Lựa chọn fallback phải dựa trên yêu cầu nghiệp vụ: **sao chép bytes không bảo toàn đặc tính đồng bộ của hard link**, còn ghi một đường dẫn trong cấu hình không tạo ra symlink thật.

## 5. Kiểm tra attribute views đúng cách

Java NIO.2 cung cấp nhiều view thuộc tính:

- `BasicFileAttributeView`: kích thước, thời điểm, loại tệp, định danh nếu provider có; khả dụng qua NIO.2 cho các tệp thông thường.
- `PosixFileAttributeView`: owner, group và chín bit quyền (`PosixFilePermission`). Dùng `Files.getPosixFilePermissions` và `Files.setPosixFilePermissions` **chỉ khi hỗ trợ**.
- `AclFileAttributeView`: ACL gồm các mục `AclEntry` và principal khi provider hỗ trợ. ACL phức tạp hơn ba nhóm owner/group/others, không thể quy đổi tổng quát thành `chmod 755`.
- `DosFileAttributeView`: các thuộc tính DOS như read-only, hidden, system, archive. Thuộc tính read-only **không phải mô hình đầy đủ của quyền truy cập**.
- `FileStore.supportsFileAttributeView("posix")` (hoặc `"acl"`, `"dos"`): nhận diện khả năng view của **file store**, **không** phải API kiểm tra khả năng tạo symlink/hard link hay quyền hiện tại của user. Một provider có thể hỗ trợ nhiều view đồng thời, kể cả view `dos` trên môi trường không phải Windows.

Khi cần xem chính link, truyền `LinkOption.NOFOLLOW_LINKS` vào phương thức phù hợp; khi cần quyền của dữ liệu đích, để mặc định theo link nhưng phải dự liệu đường dẫn đích bị gãy hoặc bị từ chối. Một số thao tác sửa thuộc tính của symlink bản thân nó không được provider hỗ trợ; tránh dùng `Files.setPosixFilePermissions(link, ...)` rồi cho rằng đã thiết lập quyền của “link” độc lập.

## 6. Ví dụ chạy được: thử hai loại liên kết, xử lý tính không hỗ trợ

Tạo tệp `LinkSupportDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class LinkSupportDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-links-");
        Path original = dir.resolve("source.txt");
        Path symlink = dir.resolve("shortcut.txt");
        Path hardlink = dir.resolve("second-name.txt");
        try {
            Files.writeString(original, "hello", StandardCharsets.UTF_8);
            try {
                // Relative target được tính từ thư mục chứa shortcut.txt.
                Files.createSymbolicLink(symlink, Path.of("source.txt"));
                System.out.println("symbolic=" + Files.isSymbolicLink(symlink));
                System.out.println("raw-target=" + Files.readSymbolicLink(symlink));
                System.out.println("through-link=" + Files.readString(symlink));
            } catch (IOException | UnsupportedOperationException | SecurityException ex) {
                System.out.println("symbolic-unavailable=" + ex.getClass().getSimpleName());
            }
            try {
                Files.createLink(hardlink, original);
                System.out.println("same-file=" + Files.isSameFile(original, hardlink));
                Files.writeString(hardlink, "updated", StandardCharsets.UTF_8);
                System.out.println("through-original=" + Files.readString(original));
            } catch (IOException | UnsupportedOperationException | SecurityException ex) {
                System.out.println("hard-unavailable=" + ex.getClass().getSimpleName());
            }
            System.out.println("posix-view=" +
                Files.getFileStore(original).supportsFileAttributeView("posix"));
        } finally {
            // Xóa các tên trước, sau đó xóa file và thư mục tạm.
            Files.deleteIfExists(symlink);
            Files.deleteIfExists(hardlink);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac --release 17 LinkSupportDemo.java
java LinkSupportDemo
```

Một lần chạy trên Linux với filesystem hỗ trợ cả hai loại link cho output:

```text
symbolic=true
raw-target=source.txt
through-link=hello
same-file=true
through-original=updated
posix-view=true
```

Giải thích: symlink lưu đường dẫn tương đối `source.txt`; đọc qua symlink trả nội dung `hello`. Hard link cung cấp tên thứ hai cho **cùng đối tượng tệp**, nên ghi `updated` qua `second-name.txt` khiến đọc từ `source.txt` thấy nội dung mới. Trên máy không hỗ trợ, có thể xuất hiện `symbolic-unavailable=...` hoặc `hard-unavailable=...` với tên exception cụ thể; `posix-view` cũng phụ thuộc file store. Đây là **kết quả có điều kiện**, không phải sáu dòng chắc chắn trên mọi OS.

Ví dụ dùng thư mục riêng được tạo qua `Files.createTempDirectory` và dọn trong `finally`; để đơn giản, nếu có tiến trình khác cố ý sửa thư mục tạm trong lúc chạy, thao tác dọn vẫn có thể ném `IOException`. Trong ứng dụng thực, log exception cùng path/file store và thực hiện cleanup phù hợp quyền sở hữu tài nguyên.

## 7. Ví dụ chạy được: quan sát và đặt quyền POSIX khi có hỗ trợ

Tạo `PermissionProbe.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.util.Set;

public class PermissionProbe {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("nio-permission-", ".txt");
        try {
            FileStore store = Files.getFileStore(file);
            System.out.println("posix=" + store.supportsFileAttributeView("posix"));
            System.out.println("acl=" + store.supportsFileAttributeView("acl"));
            System.out.println("dos=" + store.supportsFileAttributeView("dos"));

            if (store.supportsFileAttributeView("posix")) {
                Set<PosixFilePermission> previous = Files.getPosixFilePermissions(file);
                try {
                    Files.setPosixFilePermissions(file,
                        PosixFilePermissions.fromString("rw-------"));
                    System.out.println("permissions=" + PosixFilePermissions.toString(
                        Files.getPosixFilePermissions(file)));
                } finally {
                    Files.setPosixFilePermissions(file, previous);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 PermissionProbe.java
java PermissionProbe
```

Ví dụ trên một hệ Linux/JDK cụ thể:

```text
posix=true
acl=false
dos=true
permissions=rw-------
```

Ba dòng đầu **phụ thuộc Java provider và file store**, không phản ánh trực tiếp OS là gì; ví dụ `dos=true` có thể xuất hiện cả trên Linux. Dòng `permissions=rw-------` chỉ có khi POSIX view hỗ trợ và thao tác thay quyền thành công: owner có đọc/ghi, group và others không có bit `rwx` nào. Ví dụ khôi phục mode cũ trong `finally` trước khi xóa file tạm; ACL, effective access và chính sách OS vẫn có thể làm quyền thực tế phức tạp hơn chín bit này. Nếu bị từ chối thay quyền, `IOException` sẽ báo lỗi: không nên nuốt lỗi rồi giả định đã thiết lập bảo mật.

Đối với Windows ACL, dùng `AclFileAttributeView` sau khi kiểm tra khả năng hỗ trợ và hiểu đúng `UserPrincipal` / `AclEntry`. Đừng cố dùng `setPosixFilePermissions` thay thế ACL. Nếu mục tiêu chỉ là mở file để đọc/ghi, thường nên thực hiện thao tác NIO thật và xử lý lỗi thay vì cố thay quyền hệ thống.

## 8. Các tình huống lỗi và cách xử lý có chủ đích

| Hiện tượng / exception | Nguyên nhân cần kiểm tra | Phản ứng phù hợp |
| --- | --- | --- |
| `UnsupportedOperationException` từ tạo link | Provider không hỗ trợ thao tác hoặc thuộc tính yêu cầu. | Thông báo feature không hỗ trợ; chỉ chuyển sang giải pháp khác nếu hợp đồng ứng dụng cho phép. |
| `AccessDeniedException` / `FileSystemException` | Quyền thư mục, đặc quyền tạo symlink, chính sách Windows/Unix, mount, filesystem hoặc tệp đang dùng. | Ghi nhận thao tác, path, loại filesystem và thông điệp lỗi; kiểm tra quyền/config theo môi trường, không tự động nâng quyền. |
| `FileAlreadyExistsException` | Tên `link` đã có mục, có thể là symlink gãy. | Dùng tên mới hoặc chính sách xử lý xung đột rõ ràng; **không** xóa dữ liệu hiện có một cách mù quáng. |
| `NoSuchFileException` khi đọc qua link | Link bị gãy hoặc một thành phần của đường dẫn không tồn tại. | Phân biệt sự tồn tại của link và của đích bằng `NOFOLLOW_LINKS`. |
| Lỗi tạo hard link trên volume khác | Hard link không thể nối hai đối tượng ở hai file store khác nhau trong nhiều filesystem. | Đặt link cùng file store hoặc thay thiết kế lưu trữ, hiểu rằng copy không đồng nghĩa hard link. |
| `FileSystemLoopException` khi duyệt theo link | Một symlink quay về thư mục tổ tiên gây chu trình. | Tắt `FOLLOW_LINKS` nếu không cần; nếu cần thì bắt lỗi, giới hạn độ sâu và định nghĩa chính sách xử lý vòng lặp. |
| `SecurityException` | Truy cập bị chặn bởi chính sách bảo mật/runtime phù hợp cấu hình đang dùng. | Xem đúng cơ chế chặn; không đồng nhất với “filesystem không hỗ trợ”. |

**Không kiểm tra `Files.exists(link)` để quyết định chắc chắn có thể tạo link mới.** Symlink gãy có thể làm `exists(link) == false` dù mục link vẫn chiếm tên. Ngay cả `exists(link, NOFOLLOW_LINKS)` cũng chỉ là ảnh chụp tức thời, dễ bị race; thao tác tạo `createSymbolicLink`/`createLink` vẫn phải tự xử lý `FileAlreadyExistsException`.

Ví dụ nhanh để hiểu dangling symlink (chỉ chạy ở nơi được phép tạo symlink):

```java
Path dangling = dir.resolve("broken-link"); // dir đã tồn tại
Files.createSymbolicLink(dangling, Path.of("missing.txt"));
System.out.println(Files.exists(dangling)); // thường false: đích chưa có
System.out.println(Files.exists(dangling, LinkOption.NOFOLLOW_LINKS)); // true: link có
Files.delete(dangling); // chỉ xóa link
```

Đoạn trên là **minh họa phụ thuộc biến `dir` đã tạo trước**, không phải chương trình Java độc lập. Kết quả giả định việc tạo symlink thành công và không có tác nhân khác sửa đường dẫn.

## 9. An toàn và tính đúng đắn khi đường dẫn đến từ người dùng

- **Tránh symlink traversal:** nếu ứng dụng cho người dùng chọn tên file trong thư mục được kiểm soát, hãy đề phòng người khác tạo symlink dẫn tới file bên ngoài. `base.resolve(userInput).normalize().startsWith(base)` chỉ kiểm tra đường dẫn về mặt chữ, **không xác nhận** thực thể mà symlink dẫn tới.
- **Không tin vào check-then-use:** giữa `toRealPath`/`exists` và `Files.newInputStream` hay `Files.delete`, một tiến trình khác có thể đổi link. Dùng `LinkOption.NOFOLLOW_LINKS` nơi API cho phép khi muốn thao tác trên mục cuối; khi phải truy cập cây thư mục không tin cậy, xem xét `SecureDirectoryStream` (nếu provider hỗ trợ) hoặc cơ chế mở file an toàn do nền tảng cung cấp.
- **Rõ chính sách follow:** khi quét folder, backup, xóa cây, unpack archive hoặc đồng bộ dữ liệu, quyết định có theo symlink hay không. Theo link bừa bãi có thể lặp vô hạn, vượt ranh giới thư mục hoặc đụng tài nguyên không thuộc phạm vi.
- **Không “sửa lỗi quyền” bằng `chmod 777` / chạy Administrator mặc định:** chỉ cấp đúng quyền cần thiết cho tài khoản dịch vụ, thư mục và đối tượng. Kiểm tra ACL, user/group, quyền mount và policy trên môi trường triển khai.
- **Dự tính tính di động:** Java có API thống nhất nhưng không chuẩn hóa mọi semantics cấp OS. Một tính năng bắt buộc tạo symlink/hard link phải được kiểm tra trên filesystem mục tiêu trong môi trường thực; fallback và thông báo lỗi phải được xác định trước.

## 10. Checklist vận dụng

1. Xác định nghiệp vụ cần **đường dẫn chuyển hướng** (symlink), **nhiều tên chung một đối tượng** (hard link), hay **bản sao dữ liệu độc lập** (`Files.copy`): ba mục tiêu không thay thế nhau.
2. Xác định `Path` nguồn, vị trí tạo link, tồn tại đích và quan hệ volume/file store. Với symlink tương đối, tính target từ **thư mục chứa link**.
3. Kiểm tra view theo `FileStore` khi cần metadata/quyền; phân biệt POSIX, ACL và DOS; không dùng tên OS thay cho phép đo khả năng thực tế.
4. Thực hiện API tạo/đọc/xóa thật trong `try`/`catch`, xử lý lỗi quyền, unsupported, target gãy và xung đột tên, không dựa vào `exists` như khóa đồng bộ.
5. Quyết định rõ khi nào theo symlink, khi nào dùng `NOFOLLOW_LINKS`; kiểm tra đường dẫn từ nguồn không tin cậy và vấn đề race.
6. Thử trên Linux/macOS/Windows hoặc môi trường triển khai dự kiến **với đúng filesystem, user và mount**; không chỉ thử trên máy developer.

**Tự kiểm tra kiến thức**

- Vì sao xóa `shortcut.txt` (symlink) không xóa `source.txt`, còn sửa nội dung qua hard link thường làm thay đổi dữ liệu nhìn thấy ở mọi tên?
- Vì sao `Files.exists(brokenLink)` có thể trả `false` trong khi `Files.exists(brokenLink, NOFOLLOW_LINKS)` trả `true`?
- Nếu `FileStore.supportsFileAttributeView("posix")` trả `true`, đã có thể kết luận tạo symbolic link thành công chưa? **Chưa:** attribute view và khả năng/quyền tạo link là hai vấn đề khác nhau.
- Khi chạy cùng code trên Windows NTFS và ổ FAT/exFAT hoặc ổ mạng, yếu tố nào có thể khác? **Loại link được hỗ trợ, yêu cầu đặc quyền, ACL, thuộc tính, mount/driver và các lỗi I/O.**
- Tại sao một đường dẫn chuẩn hóa bằng `normalize()` vẫn có thể vượt ra ngoài thư mục gốc thông qua symlink? Vì `normalize()` không phân giải link trên filesystem.

## Tài liệu chính thức

- Java SE 21: [`Files` — `createSymbolicLink`, `createLink`, `readSymbolicLink`, `walkFileTree`, `NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).
- Java SE 21: [`PosixFileAttributeView` — quyền, owner, group và mode bit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html).
- Microsoft Learn: [`CreateSymbolicLinkW` — đặc quyền và cờ unprivileged create](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createsymboliclinkw); [Developer Mode trên Windows](https://learn.microsoft.com/en-us/windows/advanced-settings/developer-mode).

Các mô tả ở đây áp dụng cho API chuẩn Java NIO.2 (Java 17+); khả năng thực tế luôn phụ thuộc provider/file store và cấu hình hệ điều hành.