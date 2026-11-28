# Kiểm tra đường dẫn đầu vào và phạm vi tệp được phép tác động

Một CLI quản lý file thường có các command như `file read`, `file export`, `file delete` hoặc `backup restore`. Nếu command nhận đường dẫn trực tiếp từ người dùng rồi mở file ngay, người dùng có thể truyền `../../...` để thoát khỏi thư mục dự kiến, chọn file cấu hình nhạy cảm hoặc ghi đè dữ liệu nằm ngoài phạm vi được phép.

Lỗ hổng này thường được gọi là path traversal. Một đường dẫn trông có vẻ nằm trong thư mục an toàn vẫn có thể trỏ ra ngoài thông qua symbolic link (symlink), đường dẫn tuyệt đối hoặc thay đổi filesystem giữa bước kiểm tra và bước mở file. Ứng dụng Spring Shell cần gom việc kiểm tra đường dẫn vào một service dùng chung, áp dụng cùng chính sách cho mọi command đọc, ghi, đổi tên và xóa file.

## 1. Xác định phạm vi file mà CLI được phép truy cập

Trước khi viết code, hãy xác định thư mục gốc được phép, command nào được đọc/ghi/xóa, có cho phép thư mục con hay symlink không, loại file và kích thước tối đa, cùng quyền của process trên hệ điều hành.

Ví dụ, một CLI xuất báo cáo chỉ được phép ghi vào `./workspace/reports`. Người dùng có thể chọn tên file bên trong vùng này, nhưng không thể ghi vào `~/.ssh`, thư mục cấu hình ứng dụng hoặc một đường dẫn tùy ý.

Đặt root trong cấu hình:

```yaml
app:
  files:
    root: ./workspace
    max-read-bytes: 10485760
```

Root là cấu hình tin cậy do người vận hành quản lý. Không lấy root từ tham số command của người dùng rồi dùng chính giá trị đó làm giới hạn bảo mật.

## 2. Path traversal là gì?

Path traversal xảy ra khi đầu vào đường dẫn làm ứng dụng truy cập vị trí nằm ngoài vùng được phép.

| Đầu vào | Rủi ro |
| --- | --- |
| `../../etc/passwd` | Dùng `..` để đi lên thư mục cha |
| `../config/application.yml` | Đọc cấu hình bên ngoài vùng làm việc |
| `/home/user/.ssh/id_rsa` | Truyền đường dẫn tuyệt đối |
| `C:\Users\user\.ssh\id_rsa` | Dùng đường dẫn tuyệt đối trên Windows |
| `reports/current/../../secret.txt` | Đường dẫn con nhưng thoát root sau khi chuẩn hóa |
| `reports/link/secret.txt` | Thành phần `link` có thể là symlink trỏ ra ngoài |

Không nên chỉ lọc chuỗi `../`. Cách lọc chuỗi dễ bỏ sót dấu phân cách khác nhau giữa hệ điều hành hoặc đường dẫn đã được chuẩn hóa. Hãy phân tích bằng Java NIO `Path` và kiểm tra theo từng thành phần đường dẫn.

## 3. Phân biệt normalize và toRealPath

Java NIO cung cấp hai thao tác có mục đích khác nhau:

- `Path.normalize()` loại bỏ các thành phần dư thừa theo cú pháp, ví dụ `a/../b` thành `b`. Nó không truy cập filesystem và không phát hiện symlink.
- `Path.toRealPath()` yêu cầu đường dẫn tồn tại, trả về đường dẫn thực đã phân giải; mặc định nó theo symlink và loại bỏ các thành phần `.`/`..`.

Ví dụ:

```java
Path root = Path.of("/srv/cli-workspace").toRealPath();
Path candidate = root.resolve("reports/../private.txt").normalize();

if (!candidate.startsWith(root)) {
    throw new SecurityException("Đường dẫn nằm ngoài vùng cho phép");
}

Path real = candidate.toRealPath();
if (!real.startsWith(root)) {
    throw new SecurityException("Đường dẫn thực nằm ngoài vùng cho phép");
}
```

`normalize()` kiểm tra đường dẫn theo cú pháp. `toRealPath()` kiểm tra filesystem thực tế và giải quyết symlink. Dùng cả hai khi phù hợp; không xem một trong hai là thay thế cho thao tác còn lại.

Khi kiểm tra phạm vi, dùng `Path.startsWith(Path)` thay vì `String.startsWith(...)`. So sánh chuỗi có thể nhầm `/srv/cli-workspace-evil/file.txt` là con của `/srv/cli-workspace`, trong khi `Path.startsWith` so sánh theo thành phần path.

## 4. Khởi tạo root đã chuẩn hóa

Root phải được phân giải thành đường dẫn tuyệt đối, tồn tại và là thư mục. Thực hiện bước này một lần khi tạo service:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AllowedFileStore {

    private final Path root;
    private final long maxReadBytes;

    public AllowedFileStore(
            @Value("${app.files.root}") String rootDirectory,
            @Value("${app.files.max-read-bytes:10485760}") long maxReadBytes)
            throws IOException {
        Path configured = Path.of(rootDirectory).toAbsolutePath().normalize();
        this.root = configured.toRealPath();
        this.maxReadBytes = maxReadBytes;

        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalStateException("Thư mục file root không hợp lệ");
        }
    }
}
```

Ví dụ trên cho phép cấu hình root là symlink, nhưng lưu lại đích thực sau `toRealPath()`. Nếu chính sách triển khai yêu cầu root không được là symlink, hãy kiểm tra `Files.isSymbolicLink(configured)` trước khi phân giải.

Không tự động chuyển root sang thư mục hiện tại nếu cấu hình sai. Một fallback như vậy có thể khiến CLI đọc hoặc ghi nhầm vùng dữ liệu.

## 5. Phân tích và từ chối đầu vào nguy hiểm

Nhận đường dẫn từ người dùng dưới dạng `String` để service kiểm tra trước khi mở file. Đặt hàm sau bên trong `AllowedFileStore`:

```java
import java.nio.file.InvalidPathException;
import java.nio.file.Path;

private Path parseRelativePath(String input) {
    if (input == null || input.isBlank() || input.indexOf('\0') >= 0) {
        throw new IllegalArgumentException("Đường dẫn không hợp lệ");
    }

    final Path relative;
    try {
        relative = Path.of(input);
    }
    catch (InvalidPathException ex) {
        throw new IllegalArgumentException("Đường dẫn không hợp lệ", ex);
    }

    if (relative.isAbsolute()) {
        throw new SecurityException("Chỉ chấp nhận đường dẫn tương đối");
    }

    for (Path part : relative) {
        if (part.toString().equals("..")) {
            throw new SecurityException("Không chấp nhận thành phần '..'");
        }
    }

    if (relative.getNameCount() == 0) {
        throw new IllegalArgumentException("Cần chỉ định file");
    }
    return relative;
}
```

Từ chối `..` ngay cả khi đường dẫn cuối cùng vẫn nằm trong root giúp chính sách dễ hiểu. Đây là chính sách nghiêm ngặt phù hợp với CLI chỉ cần nhận tên file hoặc đường dẫn con.

`Path` sử dụng quy tắc của filesystem provider trên hệ điều hành đang chạy. Trên Windows, nó nhận diện drive và UNC path; trên Linux, dấu `\` có thể là ký tự tên file thông thường. Nếu CLI nhận đường dẫn từ manifest được tạo trên hệ điều hành khác, cần định nghĩa rõ định dạng manifest và cách chuyển đổi.

## 6. Kiểm tra đường dẫn đã tồn tại để đọc

Đối với file cần đọc, yêu cầu toàn bộ đường dẫn tồn tại, không chứa symlink theo chính sách nghiêm ngặt và là file thường. Đặt các hàm sau bên trong `AllowedFileStore`:

```java
private Path resolveExistingFile(String input) throws IOException {
    Path relative = parseRelativePath(input);
    Path candidate = root.resolve(relative).normalize();

    if (!candidate.startsWith(root) || candidate.equals(root)) {
        throw new SecurityException("Đường dẫn nằm ngoài vùng cho phép");
    }

    rejectSymbolicLinkComponents(relative);

    Path real = candidate.toRealPath();
    if (!real.startsWith(root)) {
        throw new SecurityException("Đường dẫn thực nằm ngoài vùng cho phép");
    }

    if (!Files.isRegularFile(real, LinkOption.NOFOLLOW_LINKS)) {
        throw new IllegalArgumentException("Đường dẫn không phải file thường");
    }
    return real;
}

private void rejectSymbolicLinkComponents(Path relative) {
    Path current = root;
    for (Path part : relative) {
        current = current.resolve(part);
        if (Files.isSymbolicLink(current)) {
            throw new SecurityException("Không chấp nhận symbolic link");
        }
    }
}
```

Kiểm tra từng thành phần giúp từ chối cả symlink ở thư mục cha, không chỉ symlink ở file cuối. Sau đó `toRealPath()` và `startsWith(root)` xác nhận đích thực vẫn ở trong root.

Ví dụ, nếu `workspace/reports` là symlink trỏ tới `/etc`, thì `workspace/reports/passwd` phải bị từ chối dù chuỗi đầu vào không chứa `..`.

## 7. Kiểm tra file mới trước khi ghi

File đích chưa tồn tại nên không thể gọi `toRealPath()` trên toàn bộ đường dẫn. Thay vào đó:

1. Phân tích đường dẫn tương đối và chuẩn hóa.
2. Xác nhận candidate vẫn nằm trong root.
3. Yêu cầu thư mục cha đã tồn tại.
4. Từ chối symlink trong các thành phần thư mục cha.
5. Phân giải thư mục cha bằng `toRealPath()`.
6. Kiểm tra thư mục cha thực vẫn nằm trong root.
7. Tạo file bằng chế độ `CREATE_NEW` và `NOFOLLOW_LINKS`.

Ví dụ hàm xác định đường dẫn tạo mới:

```java
private Path resolveNewFile(String input) throws IOException {
    Path relative = parseRelativePath(input);
    Path candidate = root.resolve(relative).normalize();

    if (!candidate.startsWith(root) || candidate.equals(root)) {
        throw new SecurityException("Đường dẫn nằm ngoài vùng cho phép");
    }

    Path parent = candidate.getParent();
    if (parent == null) {
        throw new IllegalArgumentException("Thiếu thư mục cha");
    }

    Path relativeParent = root.relativize(parent);
    rejectSymbolicLinkComponents(relativeParent);

    Path realParent = parent.toRealPath();
    if (!realParent.startsWith(root)) {
        throw new SecurityException("Thư mục cha nằm ngoài vùng cho phép");
    }

    Path target = realParent.resolve(candidate.getFileName());
    if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
        throw new IllegalArgumentException("File đích đã tồn tại");
    }
    return target;
}
```

Hàm này chỉ cho phép tạo file trong thư mục cha đã tồn tại. Nếu cần tạo thư mục con, hãy tạo từng cấp bằng service riêng và áp dụng cùng quy tắc kiểm tra cho mỗi cấp.

## 8. Ghi file mà không theo symlink ở đích

Sau khi xác định đường dẫn mới, sử dụng `CREATE_NEW` để không ghi đè file đã tồn tại. Thêm `LinkOption.NOFOLLOW_LINKS` để không mở symlink cuối:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardOpenOption;

public void writeNewTextFile(String input, String content) throws IOException {
    Path target = resolveNewFile(input);
    Files.writeString(
            target,
            content,
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE,
            LinkOption.NOFOLLOW_LINKS);
}
```

`CREATE_NEW` làm thao tác tạo file thất bại nếu tên đích đã tồn tại tại thời điểm mở. Điều này tránh việc một symlink được đặt sẵn ở tên đích bị mở để ghi theo target của nó.

Nếu sản phẩm cần ghi đè, hãy thiết kế một thao tác riêng với chính sách rõ ràng: kiểm tra file hiện tại, xác định có cho phép thay thế không, ghi file tạm trong cùng thư mục, flush dữ liệu và thay thế bằng thao tác atomic khi filesystem hỗ trợ. Không dùng `CREATE` hoặc `TRUNCATE_EXISTING` tùy tiện trên một path chưa được kiểm chứng.

## 9. Đọc file với giới hạn kích thước

Một đường dẫn nằm trong root vẫn có thể trỏ tới file rất lớn. Vì vậy, kiểm tra phạm vi path chưa đủ; cần giới hạn dung lượng đọc để tránh cạn bộ nhớ:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

public String readTextFile(String input) throws IOException {
    Path file = resolveExistingFile(input);
    long size = Files.size(file);

    if (size > maxReadBytes) {
        throw new IllegalArgumentException("File vượt quá dung lượng cho phép");
    }

    return Files.readString(file, StandardCharsets.UTF_8);
}
```

Nếu file có thể bị thay đổi đồng thời, kích thước có thể đổi giữa lúc kiểm tra và lúc đọc. Với file lớn hoặc môi trường có đối thủ có thể sửa filesystem, đọc qua channel, giới hạn số byte thực tế và xử lý trường hợp file thay đổi trong khi đọc.

## 10. Kiểm tra phạm vi khi xóa hoặc đổi tên

Command xóa và đổi tên có rủi ro cao hơn command đọc. Dùng cùng hàm phân giải file hiện có, kiểm tra loại file và xác nhận nghiệp vụ trước khi thao tác:

```java
public void deleteFile(String input) throws IOException {
    Path file = resolveExistingFile(input);
    Files.delete(file);
}
```

Với đổi tên, kiểm tra cả source và destination:

- Source phải là file thường nằm trong root.
- Destination phải nằm trong root và tuân theo chính sách ghi đè.
- Không cho phép chuyển file ra ngoài root bằng destination path.
- Nếu cần atomic move, source và destination nên nằm trên cùng filesystem; kiểm tra `AtomicMoveNotSupportedException`.

Không nhận một `Path` đã được kiểm tra từ tầng command rồi dùng lại sau thời gian dài. Service thực hiện thao tác phải kiểm tra ngay trước khi truy cập file.

## 11. Rủi ro TOCTOU và thay đổi filesystem đồng thời

TOCTOU (time of check to time of use) xảy ra khi ứng dụng kiểm tra đường dẫn ở thời điểm A, nhưng file hoặc thư mục bị thay đổi trước khi ứng dụng mở ở thời điểm B.

Ví dụ:

1. CLI kiểm tra `workspace/reports/output.txt` nằm trong root.
2. Một process khác đổi `workspace/reports` thành symlink trỏ ra ngoài.
3. CLI gọi `Files.writeString(...)`.
4. File có thể được ghi vào vị trí mà ứng dụng không dự định.

`normalize()`, `toRealPath()` và `NOFOLLOW_LINKS` giảm nhiều rủi ro nhưng không tạo ra một giao dịch filesystem bao trùm tất cả thành phần cha. Trong môi trường mà người dùng không tin cậy có thể sửa thư mục cùng lúc, cần dùng quyền hệ điều hành để ngăn họ thay đổi root, hoặc sử dụng `SecureDirectoryStream` khi filesystem provider hỗ trợ.

`SecureDirectoryStream` cho phép thao tác tương đối với một directory handle đã mở và cung cấp các thao tác an toàn hơn khi filesystem bị thay đổi đồng thời. Không phải provider nào cũng hỗ trợ; kiểm tra khả năng tại runtime và có chính sách fallback an toàn. <Link url="https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html" title="SecureDirectoryStream API — Java 17"/>.

## 12. Giải nén archive và lỗi Zip Slip

Khi command nhận ZIP để giải nén, tên entry trong archive là dữ liệu không tin cậy. Một entry như `../../outside.txt` có thể khiến file được ghi ra ngoài thư mục đích. Lỗ hổng này thường được gọi là Zip Slip.

Với mỗi entry:

1. Phân tích tên entry thành `Path`.
2. Từ chối path tuyệt đối và thành phần `..`.
3. Resolve entry dưới extraction root rồi normalize.
4. Kiểm tra `startsWith(extractionRoot)`.
5. Kiểm tra symlink và thư mục cha theo chính sách.
6. Tạo file mới bằng `CREATE_NEW` và `NOFOLLOW_LINKS`.
7. Giới hạn số entry, tổng dung lượng giải nén và độ sâu thư mục.

Ví dụ kiểm tra đường dẫn entry:

```java
Path extractionRoot = destination.toRealPath();
Path entryPath = Path.of(zipEntry.getName());

if (entryPath.isAbsolute()) {
    throw new SecurityException("Archive chứa đường dẫn tuyệt đối");
}

for (Path part : entryPath) {
    if (part.toString().equals("..")) {
        throw new SecurityException("Archive chứa path traversal");
    }
}

Path output = extractionRoot.resolve(entryPath).normalize();
if (!output.startsWith(extractionRoot)) {
    throw new SecurityException("Entry nằm ngoài thư mục giải nén");
}
```

Đây mới là bước kiểm tra đường dẫn. Trước khi tạo file, vẫn phải áp dụng kiểm tra symlink và cách ghi an toàn như các mục trước. Không tin cậy tên entry, metadata, kích thước khai báo hoặc số lượng file trong archive.

## 13. Tích hợp kiểm tra đường dẫn vào command Spring Shell

Command chỉ nên nhận chuỗi đường dẫn và giao toàn bộ chính sách filesystem cho service:

```java
import java.io.IOException;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class FileCommands {

    private final AllowedFileStore fileStore;

    public FileCommands(AllowedFileStore fileStore) {
        this.fileStore = fileStore;
    }

    @ShellMethod(key = "file read", value = "Đọc file trong workspace")
    public String read(
            @ShellOption(value = "--path") String path) throws IOException {
        try {
            return fileStore.readTextFile(path);
        }
        catch (SecurityException | IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Không thể đọc file trong workspace: " + ex.getMessage());
        }
    }
}
```

Không dùng `@ShellOption` để tự động chuyển thành `Path` rồi bỏ qua validation của service. Giữ đầu vào là `String` giúp service kiểm tra chính sách trước khi thao tác. Nếu nhiều command cần đọc/ghi/xóa, tất cả phải gọi cùng một service thay vì tự xây dựng `root.resolve(...)` riêng.

## 14. Không để thông báo lỗi làm lộ filesystem

Thông báo cho người dùng nên giải thích vì sao thao tác bị từ chối mà không tiết lộ đường dẫn tuyệt đối hoặc cấu trúc thư mục nhạy cảm:

| Không nên trả về | Nên trả về |
| --- | --- |
| `Access denied: /home/service/.ssh/id_rsa` | `Đường dẫn nằm ngoài workspace được phép` |
| Stack trace đầy đủ từ `FileSystemException` | `Không thể đọc file; hãy kiểm tra quyền và đường dẫn` |
| Đường dẫn root tuyệt đối trong mọi lỗi | Tên thao tác và tên file tương đối đã được làm sạch |

Log nội bộ có thể ghi mã lỗi, command, operation ID và đường dẫn tương đối sau khi kiểm tra. Không ghi nội dung file, token hoặc đường dẫn tuyệt đối của thư mục nhạy cảm nếu không cần thiết.

## 15. Phân quyền hệ điều hành và cấu hình thư mục

Kiểm tra trong Java không thay thế quyền truy cập của hệ điều hành. Process chạy CLI nên có quyền tối thiểu:

- Chỉ cấp read cho command cần đọc.
- Chỉ cấp write/create cho thư mục xuất dữ liệu.
- Không chạy CLI bằng tài khoản quản trị nếu không cần.
- Không đặt workspace trong thư mục chứa secrets hoặc file cấu hình hệ thống.
- Bảo vệ root và các thư mục cha để người dùng không tin cậy không thể thay symlink hoặc đổi quyền.
- Khi chạy trong container, mount đúng thư mục dữ liệu và dùng user không phải root.

Nếu workspace nằm trên network filesystem hoặc filesystem có semantics đặc biệt, kiểm tra hành vi symlink, atomic move, permission và file locking của môi trường đó.

## 16. Kiểm thử đường dẫn và phạm vi file

Dùng thư mục tạm để kiểm tra service mà không đụng tới file thật của người dùng:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AllowedFileStoreTests {

    @TempDir
    Path workspace;

    @Test
    void rejectsParentTraversal() throws Exception {
        AllowedFileStore store =
                new AllowedFileStore(workspace.toString(), 1024);

        assertThrows(SecurityException.class,
                () -> store.readTextFile("../outside.txt"));
    }

    @Test
    void readsAFileInsideWorkspace() throws Exception {
        Files.writeString(workspace.resolve("report.txt"), "hello");
        AllowedFileStore store =
                new AllowedFileStore(workspace.toString(), 1024);

        assertTrue(store.readTextFile("report.txt").contains("hello"));
    }
}
```

Đoạn test minh họa cách tổ chức; constructor và cấu hình `maxReadBytes` cần khớp với implementation hoàn chỉnh của ứng dụng. Bổ sung test cho đường dẫn tuyệt đối, file không tồn tại, symlink ở file cuối và thư mục cha, file quá lớn, destination đã tồn tại, ZIP entry chứa `..` và thay đổi symlink đồng thời.

Trên hệ điều hành không hỗ trợ tạo symlink trong test (ví dụ Windows thiếu quyền Developer Mode hoặc privilege phù hợp), đánh dấu test symlink theo điều kiện môi trường và chạy chúng trong một job CI có quyền cần thiết.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chặn `../` nhưng vẫn đọc được file ngoài root | Symlink ở thư mục cha | Kiểm tra từng thành phần và `toRealPath()` |
| `startsWith` trả kết quả sai | So sánh chuỗi path thay vì đối tượng Path | Dùng `Path.startsWith(Path)` |
| File mới không qua được `toRealPath()` | File đích chưa tồn tại | Phân giải parent hiện có và kiểm tra file name |
| Ghi file qua symlink | Dùng `CREATE`/`TRUNCATE_EXISTING` mà không chặn symlink | Dùng `CREATE_NEW` và `NOFOLLOW_LINKS` khi tạo mới |
| Đường dẫn hợp lệ lúc kiểm tra nhưng thoát root khi ghi | TOCTOU do filesystem thay đổi | Bảo vệ quyền thư mục; dùng `SecureDirectoryStream` nếu provider hỗ trợ |
| Giải nén ZIP ghi ra ngoài đích | Không kiểm tra tên entry | Kiểm tra mọi entry trước khi tạo file |
| Đọc file gây cạn bộ nhớ | Không giới hạn kích thước | Kiểm tra và giới hạn số byte thực đọc |
| Command này an toàn, command khác thì không | Mỗi command tự kiểm tra path | Tập trung policy trong một file service dùng chung |

## 18. Bài thực hành tổng hợp

Xây dựng nhóm command quản lý workspace:

1. Cấu hình `app.files.root` và `app.files.max-read-bytes`.
2. Tạo `AllowedFileStore` lưu root đã phân giải bằng `toRealPath()`.
3. Viết parser chỉ chấp nhận đường dẫn tương đối và từ chối `..`.
4. Viết hàm resolve file hiện có, kiểm tra mọi thành phần symlink và xác nhận real path nằm trong root.
5. Viết hàm resolve file mới, kiểm tra parent hiện có và tạo file bằng `CREATE_NEW`/`NOFOLLOW_LINKS`.
6. Tạo command `file read`, `file write` và `file delete` dùng chung service.
7. Giới hạn dung lượng đọc/ghi và loại file được phép.
8. Tạo command `archive extract` kiểm tra từng ZIP entry, symlink, số file và tổng dung lượng.
9. Viết test cho traversal, absolute path, symlink, file quá lớn và destination đã tồn tại.
10. Kiểm tra quyền hệ điều hành của workspace và chạy CLI bằng tài khoản có quyền tối thiểu.

## 19. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Path parsing | Từ chối path rỗng, tuyệt đối, không hợp lệ và `..` |
| Canonicalization | Phân biệt `normalize()` và `toRealPath()` |
| Root boundary | Dùng `Path.startsWith(Path)` để giới hạn trong root |
| Symlink | Kiểm tra symlink ở file cuối và mọi thư mục cha |
| New file | Xác thực parent và dùng `CREATE_NEW`/`NOFOLLOW_LINKS` |
| File operations | Đọc, ghi, xóa, rename đều dùng một policy service |
| Resource limits | Giới hạn kích thước file và archive extraction |
| TOCTOU | Hiểu race giữa check/use và biện pháp giảm thiểu |
| Spring Shell | Command nhận chuỗi path và giao việc kiểm tra cho service |
| Testing | Có test traversal, absolute path, symlink và boundary |
| OS permissions | Chạy với quyền tối thiểu và bảo vệ workspace |

## Tài liệu tham khảo

- [Java 17 — Path API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Java 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17 — SecureDirectoryStream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [Snyk — Zip Slip Vulnerability](https://security.snyk.io/research/zip-slip-vulnerability)
