# Tạo tệp tạm có quyền phù hợp và dọn dẹp có kiểm soát trong Java NIO

## 1. Vì sao tệp tạm cũng là một vấn đề bảo mật?

Ứng dụng Java thường tạo tệp tạm để xử lý ảnh tải lên, xuất báo cáo, giải nén, sắp xếp dữ liệu lớn, lưu kết quả trung gian hoặc chuyển dữ liệu giữa các bước xử lý. Tệp chỉ tồn tại trong thời gian ngắn **không có nghĩa là an toàn**.

Các rủi ro thực tế gồm:

- **Lộ dữ liệu:** tệp chứa token, dữ liệu khách hàng, nội dung upload hoặc thông tin bí mật nhưng người dùng khác trên máy có thể đọc.
- **Dự đoán tên và chiếm chỗ:** dùng tên cố định như `/tmp/report.txt` rồi ghi đè có thể tạo race hoặc va chạm giữa các tiến trình.
- **Symbolic-link attack:** kẻ tấn công làm đường dẫn tạm trỏ đến file đích khác trước khi ứng dụng mở lại.
- **TOCTOU:** ứng dụng kiểm tra `exists()`, `isSymbolicLink()` hoặc quyền truy cập ở thời điểm A, nhưng file bị thay thế trước lúc sử dụng ở thời điểm B.
- **Rò rỉ tài nguyên:** file/channel còn mở, tệp và thư mục tạm còn lại sau exception, cancel hoặc timeout.
- **Đầy ổ đĩa:** upload không giới hạn tạo file tạm lớn, hàng nghìn request để lại file làm dịch vụ ngừng hoạt động.
- **Xóa không triệt để:** gọi `delete()` không đồng nghĩa dữ liệu cũ đã bị xóa vật lý khỏi SSD, swap, snapshot, backup hoặc journal.

Mục tiêu của bài này: **tạo tệp tạm bằng API phù hợp; áp dụng quyền ngay khi tạo; cô lập thư mục làm việc; dùng tài nguyên có quyền sở hữu rõ ràng; dọn dẹp khi thành công hoặc lỗi; hiểu rõ những giới hạn còn lại.**

## 2. Chọn API nào để tạo file hoặc thư mục tạm?

Java NIO.2 (package `java.nio.file`) có các phương thức:

~~~java
Path file = Files.createTempFile("prefix-", ".tmp");
Path dir  = Files.createTempDirectory("job-");

// Chỉ định thư mục cha đáng tin cậy:
Path fileInDir = Files.createTempFile(dir, "data-", ".bin");
Path nestedDir = Files.createTempDirectory(dir, "stage-");
~~~

Các phương thức `Files.createTempFile(...)` và `Files.createTempDirectory(...)` **tạo đối tượng trong hệ thống tệp ngay tại lời gọi**, thay vì chỉ sinh một chuỗi tên để dùng sau này.

Khi provider hỗ trợ, việc tạo entry mới kiểm tra sự tồn tại và tạo file một cách **nguyên tử đối với hoạt động filesystem liên quan**, tránh lỗi phổ biến của mẫu “chọn tên rồi kiểm tra chưa tồn tại”. Chúng không tạo hợp đồng khóa hoặc giao dịch cho các thao tác **sử dụng sau khi tạo**.

| API | Kết quả | Dùng khi nào? |
|---|---|---|
| `Files.createTempFile(prefix,suffix,attrs...)` | Tệp tạm trong vị trí do provider xác định | Thao tác độc lập không cần cây riêng |
| `Files.createTempFile(dir,prefix,suffix,attrs...)` | Tệp tạm trong thư mục đã chọn | Muốn quản lý quyền/trọn vòng đời một job |
| `Files.createTempDirectory(prefix,attrs...)` | Thư mục tạm trong vị trí do provider xác định | Cần nơi chứa riêng nhiều file trung gian |
| `Files.createTempDirectory(parent,prefix,attrs...)` | Thư mục con tạm trong parent | Dịch vụ có khu vực scratch do quản trị viên kiểm soát |
| `Files.createFile(path,attrs...)` | File có tên xác định, phải chưa tồn tại | Khi application quản lý rõ pathname và yêu cầu create-new |
| `File.createTempFile(...)` | API `java.io.File` cũ | Hệ thống legacy; code mới ưu tiên NIO `Files` |

**Không viết:**

~~~java
// Mẫu sai: tên cố định, kiểm tra rồi mới tạo.
Path p = Path.of("/tmp/my-app-export.csv");
if (!Files.exists(p)) {
    Files.writeString(p, confidentialData);
}
~~~

Có race giữa `exists()` và `writeString()`. Ngoài ra, `Files.writeString` với bộ tùy chọn mặc định có thể tạo file mới hoặc truncate file đang tồn tại, không phù hợp với yêu cầu không ghi đè dữ liệu lạ.

**Nên dùng** `Files.createTempFile(...)` hoặc một lệnh create-new có semantics được xác định rõ. Tránh tự sinh tên tạm bằng timestamp, thread ID hoặc random yếu rồi ghép vào thư mục dùng chung.

### Prefix/suffix có phải là thông tin bí mật?

Không. Prefix/suffix để giúp nhận dạng loại file và vận hành; tên do API sinh ra giúp tránh đụng độ nhưng **không thay thế quyền truy cập**. Đừng coi tên khó đoán là lớp bảo vệ duy nhất. Không cho token, password, email khách hàng hoặc dữ liệu nhạy cảm vào tên file vì tên có thể xuất hiện trong log, danh sách thư mục hay crash report.

## 3. Chọn thư mục cha: không phải mọi nơi “temp” đều đáng tin

`Files.createTempFile("x-", ".tmp")` và `createTempDirectory("x-")` không truyền tham số thư mục sẽ sử dụng vị trí mặc định của provider. Với provider mặc định, vị trí này thường liên quan thuộc tính hệ thống `java.io.tmpdir`.

Tuy nhiên:

- Vị trí temp thực tế có thể khác nhau theo OS/container, runtime configuration hoặc provider.
- Thư mục tạm chung có thể cho phép nhiều người dùng tạo entry trong đó.
- Temp trên volume mạng có đặc tính quyền, độ trễ, visibility và cleanup khác local disk.
- Một ứng dụng chạy trong container có thể dùng filesystem ephemeral, quota riêng hoặc mount read-only.
- Thư mục cha có thể không tồn tại, hết dung lượng hoặc không đủ quyền.

**Quy tắc tốt:** với dữ liệu nhạy cảm hoặc nhiều bước xử lý, tạo **một thư mục tạm riêng cho từng job**, hạn chế truy cập trên thư mục đó, rồi tạo các tệp con bên trong.

~~~text
trusted-temp-parent/
  secure-job-<generated>/
    source-<generated>.bin
    output-<generated>.json
    intermediate-<generated>.dat

Job owns entire subtree:
  create -> use -> close handles -> delete children -> delete directory
~~~

Khi chỉ một job được quyền ghi vào thư mục riêng, nhiều nguy cơ do người dùng khác thay thế pathname giảm đi đáng kể. Nhưng một tác nhân chạy **cùng tài khoản OS và có quyền tương đương**, hoặc người dùng đặc quyền, vẫn có thể can thiệp; thư mục 0700 không tạo sandbox chống chính principal sở hữu.

### Quyền của thư mục quan trọng ngang quyền file

Ngay cả file có mode `0600`, một thư mục cha có quyền viết quá rộng có thể làm pathname bị đổi/xóa, gây race lúc mở lại. Trên hệ POSIX, một thư mục scratch private thường dùng mode `0700` (owner read/write/execute, không cấp group/others).

**Đừng chỉ kiểm tra quyền file mà quên quyền parent chain.** Thư mục dùng để chứa dữ liệu mật nên do principal được tin cậy sở hữu, không bị ghi bởi đối tượng trái phép, và mọi symlink/mount trong đường dẫn phải thuộc chính sách kiểm soát.

## 4. POSIX: cấp quyền **ngay lúc tạo**, tránh “tạo rồi chmod”

Trên POSIX-compatible filesystem, các quyền cơ bản thường biểu diễn bằng chuỗi:

- `rw-------`, tức mode 0600: chỉ chủ sở hữu đọc/ghi file.
- `rwx------`, tức mode 0700: chỉ chủ sở hữu được đọc/ghi/đi qua thư mục.
- `r--r--r--`, tức mode 0444: chỉ quyền đọc, nhưng **không phù hợp** nếu cần sửa tệp trong quá trình xử lý.
- Quyền group/others có thể làm tăng người có thể đọc/thay đổi dữ liệu.

Java NIO cung cấp `PosixFilePermissions.asFileAttribute(...)` để truyền quyền khi tạo:

~~~java
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

Set<PosixFilePermission> dirMode =
        PosixFilePermissions.fromString("rwx------");
Set<PosixFilePermission> fileMode =
        PosixFilePermissions.fromString("rw-------");

FileAttribute<Set<PosixFilePermission>> privateDir =
        PosixFilePermissions.asFileAttribute(dirMode);
FileAttribute<Set<PosixFilePermission>> privateFile =
        PosixFilePermissions.asFileAttribute(fileMode);

// Tạo với thuộc tính quyền ngay trong thao tác tạo:
Path jobDir = Files.createTempDirectory("secure-job-", privateDir);
Path artifact = Files.createTempFile(jobDir, "data-", ".bin", privateFile);
~~~

Đây là **đoạn minh họa**, cần import `java.nio.file.Files` và `Path`. Chỉ chạy đúng trên provider hỗ trợ thuộc tính POSIX cho vị trí đó.

Tính chất quan trọng:

1. File attributes được chuyển vào **thao tác tạo**, nên tránh khoảng hở giữa việc tạo file với quyền quá rộng và thao tác sửa quyền sau đó.
2. Provider có thể từ chối attribute không hỗ trợ bằng `UnsupportedOperationException`; không được lờ đi và giả vờ quyền đã được bảo vệ.
3. Quyền hiệu lực có thể bị hạn chế thêm bởi umask/ACL/policy nền tảng; **kiểm tra lại quyền thực tế** nếu quyền là một security invariant.
4. `setPosixFilePermissions(path, ...)` trên một file **đã tồn tại** là thao tác thay đổi quyền riêng, không “hồi tố” việc file đã lộ dữ liệu ở thời điểm trước đó.

### Vì sao “tạo rồi sửa quyền” là nguy hiểm?

~~~java
// Không nên dùng cho dữ liệu nhạy cảm ở một thư mục chia sẻ.
Path tmp = Files.createTempFile("secret-", ".bin");
Files.setPosixFilePermissions(
        tmp, PosixFilePermissions.fromString("rw-------"));
~~~

Với provider mặc định, `createTempFile` có thể tạo quyền mặc định chặt hơn một lệnh tạo file thông thường, nhưng **không nên coi mọi provider đều bảo đảm chính sách của ứng dụng**. Nếu quyền cụ thể là bắt buộc, cung cấp thuộc tính ngay khi tạo và xác minh chúng trên nền tảng mục tiêu.

**Lưu ý về quyền owner:** mode 0600 không chống được malware chạy cùng account, root/administrator hay cơ chế backup có quyền cao; cần sandbox/OS account isolation khi threat model đòi hỏi.

## 5. Windows và filesystem không hỗ trợ POSIX

Windows thường dùng **ACL (Access Control List)**, không dựa hoàn toàn vào các bit quyền POSIX. Cú pháp `PosixFilePermissions` **không phải chính sách di động giữa mọi provider**.

Kiểm tra hỗ trợ trước khi dùng:

~~~java
boolean supportsPosix = FileSystems.getDefault()
        .supportedFileAttributeViews()
        .contains("posix");
~~~

Đây chỉ là kiểm tra capability của **default filesystem**; đường dẫn thực còn có thể ở provider/file store khác. Khi code xử lý nhiều filesystem, cần xử lý lỗi và xác minh trên chính đường dẫn mục tiêu.

Với Windows hoặc filesystem ACL-based:

- Dùng file owner và `AclFileAttributeView` / `AclEntry` khi chính sách yêu cầu thiết lập quyền cụ thể.
- Kiểm soát **inherited ACL** từ thư mục cha; không giả định tài khoản khác không có quyền vì chương trình chỉ biết tên user hiện tại.
- Nếu file share/volume có khả năng khác biệt, việc tạo file với thuộc tính ACL ngay khi tạo phụ thuộc provider; kiểm tra tài liệu platform và test security thực tế.
- Nếu không thể xác minh chính sách tối thiểu, **fail closed** đối với dữ liệu nhạy cảm thay vì âm thầm tạo file dưới quyền không rõ.
- Không dịch máy móc `chmod 0600` thành “an toàn tương đương trên mọi Windows filesystem”.

API liên quan:

~~~java
// Minh họa truy cập ACL view, không phải một policy hoàn chỉnh.
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);
if (view == null) {
    throw new UnsupportedOperationException("ACL view unavailable");
}
// ACL thực tế phải được thiết kế theo owner, service account,
// các identity được phép và quyền inherited của parent.
~~~

Các import của đoạn minh họa thuộc `java.nio.file` và `java.nio.file.attribute`. Không nên sao chép một ACL từ môi trường khác rồi đặt bừa lên thư mục/temp file vì có thể khóa chính ứng dụng hoặc mở quyền ngoài ý muốn.

## 6. Mở lại tệp tạm: tránh symbolic link và thao tác thừa

Sau khi tạo, ứng dụng thường ghi file rồi đọc lại, chuyển sang bước tiếp hoặc xóa. Nếu một bên khác có thể thay pathname trong khoảng thời gian này, thao tác mở lại có thể trỏ đến **đối tượng khác**.

Các điểm phòng vệ:

1. Tạo tệp dưới một thư mục parent chỉ tài khoản tin cậy được phép ghi.
2. Tránh giữ tên cố định trong thư mục chia sẻ công cộng.
3. Khi mở lại, cân nhắc `LinkOption.NOFOLLOW_LINKS` trong các API nhận `OpenOption` để từ chối symlink ở thành phần cuối, **nếu provider hỗ trợ**.
4. Không coi `Files.isSymbolicLink(path)` rồi `open(path)` là kiểm tra không race: pathname có thể thay đổi giữa hai lời gọi.
5. Không mặc định `NOFOLLOW_LINKS` kiểm tra đầy đủ mọi thành phần cha hoặc ngăn tất cả hardlink/mount/directory swap attacks.
6. Với trường hợp đối thủ có thể sửa directory tree, cân nhắc `SecureDirectoryStream` hoặc API cấp OS có khả năng thao tác tương đối với một directory handle an toàn khi được hỗ trợ.

Ví dụ reopen file đã tạo:

~~~java
import java.nio.channels.SeekableByteChannel;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.StandardOpenOption;
import java.util.Set;

try (SeekableByteChannel out = Files.newByteChannel(
        artifact,
        Set.<OpenOption>of(
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING,
                LinkOption.NOFOLLOW_LINKS))) {
    // Ghi dữ liệu vào channel. Không mở với CREATE nếu file đã tồn tại.
}
~~~

Đoạn trên sử dụng `artifact` được tạo trước; chưa độc lập chạy được. Vì `Files.createTempFile(...)` **đã tạo file**, thao tác mở tiếp để ghi **không cần** `CREATE` hoặc `CREATE_NEW`. Đặc biệt `CREATE_NEW` trên chính đường dẫn vừa tạo sẽ **thất bại do file đã tồn tại**.

### Tại sao `CREATE_NEW` là một công cụ khác?

`Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE), attrs...)` dùng khi muốn **tạo tệp mới tại pathname đã chọn** và tuyệt đối không ghi đè entry hiện hữu. Nó không thay cho `Files.createTempFile` trong trường hợp bạn đã có file tạm. Nếu cần tạo/tạo và mở bằng cùng một primitive atomic, có thể dùng `CREATE_NEW` với path được chọn dưới một parent tin cậy, nhưng phải tự xử lý lựa chọn tên, va chạm và quyền.

## 7. Quản lý vòng đời: tài nguyên nào phải đóng trước khi xóa?

Tệp tạm thường được mở bởi:

- `InputStream` / `OutputStream`.
- `BufferedReader` / `BufferedWriter`.
- `FileChannel` / `SeekableByteChannel`.
- Thư viện xử lý ảnh, ZIP, PDF, CSV, XML hoặc database engine.
- Một process con đang dùng đường dẫn.
- Một thread đang chạy operation bất đồng bộ.

**Nguyên tắc ownership:** thành phần tạo tài nguyên phải xác định ai chịu trách nhiệm đóng nó và ai được quyền xóa file. Nếu có thao tác I/O còn pending hoặc một process khác chưa kết thúc, xóa ngay có thể thất bại hoặc tạo hành vi phụ thuộc OS.

Mẫu thông thường:

~~~java
Path file = Files.createTempFile("work-", ".tmp");
try {
    try (OutputStream out = Files.newOutputStream(file)) {
        out.write(bytes);
    }

    // Xử lý bằng thư viện đọc file sau khi writer đã đóng.
    consumeFile(file);
} finally {
    Files.deleteIfExists(file);
}
~~~

Đây là mã minh họa, cần imports và các biến `bytes`/`consumeFile` do ứng dụng định nghĩa. `finally` được chạy cả khi xử lý thành công lẫn khi ném exception thông thường, nhưng **không có bảo đảm** nó chạy khi process bị kill cưỡng bức, JVM crash hoặc mất điện.

### Vì sao `try-with-resources` hữu ích hơn?

`try-with-resources` tự đóng `AutoCloseable` ở lối thoát, kể cả khi một bước xử lý ném exception. Nếu cả phần thân lẫn `close()` đều ném lỗi, Java giữ lỗi chính và thêm lỗi đóng làm **suppressed exception** — tốt hơn việc một lỗi cleanup trong `finally` che khuất nguyên nhân thất bại ban đầu.

Một cách tổ chức là tạo đối tượng quản lý workspace tạm triển khai `AutoCloseable`:

~~~java
try (TempWorkspace workspace = TempWorkspace.create()) {
    // Tạo và xử lý file bên trong workspace.
} // close() xóa nội dung và directory theo quy tắc.
~~~

Ví dụ chương trình hoàn chỉnh ở mục sau triển khai cấu trúc này.

## 8. Chương trình Java 17+ hoàn chỉnh: thư mục riêng 0700, file 0600 và cleanup

Chương trình dưới đây dành cho **filesystem POSIX** và cố tình **fail closed** nếu default filesystem không có POSIX attribute view. Điều này có nghĩa:

- Trên Linux/macOS hoặc filesystem POSIX phù hợp: tạo thư mục với mode owner-only, tạo file owner-only và xác minh không có quyền group/others.
- Trên Windows ACL-only: không cố tạo file nhạy cảm với quyền không thể chứng minh bằng POSIX; in thông báo và kết thúc bình thường.
- Mở file để ghi với `NOFOLLOW_LINKS`; sử dụng `try-with-resources` để đóng kênh trước khi xóa.
- Xóa file và các thư mục con bằng `Files.walkFileTree(...)`, không theo symbolic link trong traversal mặc định.
- In kết quả ổn định không tiết lộ đường dẫn file tạm ngẫu nhiên.

Lưu thành **`SecureTempLifecycleDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class SecureTempLifecycleDemo {

    // Scope sở hữu toàn bộ cây thư mục tạm.
    private static final class TempWorkspace implements AutoCloseable {
        private final Path root;

        TempWorkspace(Path root) {
            this.root = root;
        }

        @Override
        public void close() throws IOException {
            // walkFileTree mặc định KHÔNG theo symbolic links.
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.delete(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException failure)
                        throws IOException {
                    if (failure != null) {
                        throw failure;
                    }
                    Files.delete(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    private static boolean ownerOnly(
            Set<PosixFilePermission> permissions) {
        for (PosixFilePermission permission : permissions) {
            if (permission.name().startsWith("GROUP_")
                    || permission.name().startsWith("OTHERS_")) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        if (!FileSystems.getDefault()
                .supportedFileAttributeViews()
                .contains("posix")) {
            System.out.println("POSIX unavailable: refuse sensitive temp");
            return;
        }

        Set<PosixFilePermission> directoryMode =
                PosixFilePermissions.fromString("rwx------");
        Set<PosixFilePermission> fileMode =
                PosixFilePermissions.fromString("rw-------");

        Path root = Files.createTempDirectory(
                "secure-job-",
                PosixFilePermissions.asFileAttribute(directoryMode));

        boolean directoryPrivate;
        boolean filePrivate;
        String content;

        try (TempWorkspace scope = new TempWorkspace(root)) {
            directoryPrivate = ownerOnly(
                    Files.getPosixFilePermissions(
                            root, LinkOption.NOFOLLOW_LINKS));

            if (!directoryPrivate) {
                throw new SecurityException("Directory too permissive");
            }

            Path file = Files.createTempFile(
                    root,
                    "record-",
                    ".txt",
                    PosixFilePermissions.asFileAttribute(fileMode));

            filePrivate = ownerOnly(
                    Files.getPosixFilePermissions(
                            file, LinkOption.NOFOLLOW_LINKS));

            if (!filePrivate) {
                throw new SecurityException("File too permissive");
            }

            ByteBuffer payload = ByteBuffer.wrap(
                    "hello".getBytes(StandardCharsets.UTF_8));

            try (SeekableByteChannel channel = Files.newByteChannel(
                    file,
                    Set.<OpenOption>of(
                            StandardOpenOption.WRITE,
                            StandardOpenOption.TRUNCATE_EXISTING,
                            LinkOption.NOFOLLOW_LINKS))) {
                while (payload.hasRemaining()) {
                    int n = channel.write(payload);
                    if (n <= 0) {
                        throw new IOException("No write progress");
                    }
                }
            }

            // Directory thuộc owner nên các tiến trình không có
            // quyền ghi trong đó không thể thay pathname.
            content = Files.readString(file, StandardCharsets.UTF_8);
        } // Đã đóng channel; TempWorkspace.close() xóa cây tạm.

        System.out.println("private-directory=" + directoryPrivate);
        System.out.println("private-file=" + filePrivate);
        System.out.println("content=" + content);
        System.out.println("cleanup="
                + Files.notExists(root, LinkOption.NOFOLLOW_LINKS));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SecureTempLifecycleDemo.java
java SecureTempLifecycleDemo
~~~

**Stdout trên một filesystem POSIX hoạt động bình thường, có quyền tạo/xóa tệp:**

~~~text
private-directory=true
private-file=true
content=hello
cleanup=true
~~~

**Stdout khi default filesystem không hỗ trợ POSIX view:**

~~~text
POSIX unavailable: refuse sensitive temp
~~~

Giải thích:

1. Chương trình xác nhận khả năng dùng POSIX và không âm thầm bỏ qua security requirement.
2. `Files.createTempDirectory(..., asFileAttribute(0700))` tạo workspace riêng.
3. `Files.createTempFile(root,..., asFileAttribute(0600))` tạo file trong workspace với quyền được yêu cầu ngay khi tạo.
4. `getPosixFilePermissions(...)` xác minh không cấp quyền cho group/others. Cách kiểm tra này **không tự kiểm hết ACL bổ sung hoặc các cơ chế đặc quyền ngoài POSIX**.
5. `NOFOLLOW_LINKS` từ chối symlink ở file cuối khi reopen nếu provider triển khai đúng option. Parent riêng giảm rủi ro thay thế entry bởi user khác, nhưng không bảo đảm an toàn khi có kẻ tấn công cùng UID.
6. Các thao tác ghi theo `SeekableByteChannel` có vòng lặp vì không nên suy ra một lệnh `write` sẽ chuyển toàn bộ ByteBuffer trong mọi trường hợp.
7. `TempWorkspace.close()` dùng `walkFileTree`, gọi `Files.delete` trên từng file trước rồi mới delete directory. Mặc định traversal không theo symlink; nếu có symlink xuất hiện trong thư mục, nó được xử lý như entry để xóa link, không đi theo target.
8. `try-with-resources` đảm bảo cleanup được yêu cầu khi thoát khối bình thường hoặc do exception.
9. In `cleanup=true` chỉ sau khi việc xóa kết thúc và `Files.notExists(root, NOFOLLOW_LINKS)` xác nhận không còn entry ở đường dẫn đó.

**Giới hạn:** đây là ví dụ POSIX, không triển khai chính sách Windows ACL. Nếu không có POSIX support, nó từ chối tạo workspace nhạy cảm thay vì rơi về quyền mặc định không được xác minh. Với nhu cầu cross-platform, cần xây policy tương ứng trên ACL provider và kiểm thử quyền thực tế.

## 9. Dọn dẹp một file và dọn dẹp cả thư mục cây

### Một file tạm độc lập

Nếu chỉ có một file:

~~~java
Path temp = Files.createTempFile("job-", ".dat");
try {
    process(temp);
} finally {
    Files.deleteIfExists(temp);
}
~~~

`process` là hàm ứng dụng. Cần đóng mọi stream/channel do `process` mở trước khi đi tới xóa. Dùng `deleteIfExists` giúp không coi “file đã được một bước khác xóa” là lỗi, nhưng **không nuốt mọi lỗi xóa**: file còn mở, permission denied hoặc I/O failure vẫn có thể ném `IOException`.

### Nhiều file và thư mục con

Không thể xóa directory **còn chứa file** chỉ bằng một lần `Files.delete(directory)`. Cần xóa children trước và parent sau. `Files.walkFileTree` là API phù hợp khi ứng dụng **sở hữu toàn cây** và threat model không cho phép bên lạ sửa cây trong lúc cleanup.

Không dùng:

~~~java
// Không đủ nếu thư mục còn các entry:
Files.delete(tempDirectory);
~~~

Cũng không nên viết một hàm recursive delete nhận đường dẫn tùy ý từ input người dùng rồi xóa không kiểm soát. Nếu pathname bị nhập sai, bạn có thể xóa nhầm một thư mục production.

**Quy tắc an toàn cho cleanup tree:**

- Phải có bằng chứng ứng dụng đã tạo và sở hữu root workspace.
- Không nhận trực tiếp directory-to-delete từ request body hoặc query parameter.
- Không đi theo symbolic link (mặc định `walkFileTree` không bật `FOLLOW_LINKS`).
- Nếu cần bảo vệ chống cùng-account attacker sửa pathname, dùng phương án mạnh hơn như `SecureDirectoryStream` khi filesystem/provider hỗ trợ, thay vì tin rằng walk-and-delete luôn race-free.
- Log lỗi cleanup theo cách không để lộ thông tin nhạy cảm trong file name/path.
- Nếu xóa thất bại, báo cho hệ giám sát và có chính sách xử lý sau, không im lặng bỏ qua.

## 10. Vì sao `deleteOnExit()` không nên là phương án cleanup chính?

Java có:

~~~java
temp.toFile().deleteOnExit();
~~~

Nó yêu cầu JVM cố xóa file khi JVM **kết thúc bình thường** theo cơ chế shutdown hook; đây không phải bảo đảm đủ cho môi trường server hoặc dữ liệu nhạy cảm.

Nhược điểm:

- Không có bảo đảm chạy khi JVM bị kill cưỡng bức, mất điện hoặc OS crash.
- Ứng dụng server có thể sống nhiều ngày/tuần; file vẫn tồn tại suốt thời gian đó.
- Danh sách file đăng ký `deleteOnExit` tồn tại trong bộ nhớ JVM trong vòng đời process; dùng cho hàng triệu request sẽ tăng tiêu thụ bộ nhớ.
- File có thể còn được sử dụng bởi process khác hoặc không xóa được do quyền.
- Nếu có directory và nhiều child, thứ tự đăng ký xóa cần được cân nhắc; không nên dựa vào hook để thay mô hình sở hữu workspace rõ ràng.
- Trong hệ thống container/kubernetes, lifecycle có thể bị cắt ngắn hoặc mount volume persistent vẫn còn file rác.

**Khuyến nghị:** dùng `try-with-resources`/`finally` để xóa ngay khi job kết thúc. Có thể cân nhắc `deleteOnExit()` làm lớp phòng vệ phụ cho tool chạy ngắn, nhưng không xem nó là cleanup SLA hoặc cơ chế bảo mật.

## 11. `DELETE_ON_CLOSE`: hữu ích nhưng có giới hạn

`StandardOpenOption.DELETE_ON_CLOSE` yêu cầu xóa file khi channel được đóng, tùy provider hỗ trợ. Có thể dùng cho một số trường hợp file tạm chỉ cần tồn tại trong lúc channel đang mở:

~~~java
// Mã minh họa, temporaryFile đã được tạo bởi ứng dụng.
try (SeekableByteChannel channel = Files.newByteChannel(
        temporaryFile,
        Set.<OpenOption>of(
                StandardOpenOption.WRITE,
                StandardOpenOption.DELETE_ON_CLOSE,
                LinkOption.NOFOLLOW_LINKS))) {
    // Xử lý dữ liệu trong khi channel còn mở.
}
~~~

Những điều không nên giả định:

- Không phải mọi filesystem/provider đều hỗ trợ mọi option.
- Không nên phụ thuộc vào file vẫn còn nhìn thấy dưới pathname trong lúc channel đang mở. Một số hệ thống có thể xóa entry sớm hoặc có semantics khác.
- Nếu thư viện khác cần **mở lại file bằng tên**, `DELETE_ON_CLOSE` có thể làm workflow không hoạt động.
- Không đảm bảo xóa vật lý an toàn mọi bản sao của dữ liệu.
- Không thay việc cleanup các **file khác và thư mục chứa**.

Với pipeline nhiều bước, private directory + explicit cleanup thường dễ kiểm soát hơn.

## 12. Exception, cancel và lỗi cleanup: tránh làm mất nguyên nhân chính

Giả sử xử lý upload ném exception, rồi trong `finally` xóa file cũng thất bại:

~~~java
Path file = Files.createTempFile("upload-", ".tmp");
try {
    importData(file);
} finally {
    Files.deleteIfExists(file);
}
~~~

Nếu `importData` đã ném lỗi và `deleteIfExists` lại ném lỗi khác, lỗi cleanup có thể **che lấp lỗi nghiệp vụ ban đầu** trong cách viết `finally` này. Khi điều đó quan trọng, dùng đối tượng `AutoCloseable` để dọn resource bằng try-with-resources như mục 8: Java quản lý **suppressed exceptions** để giữ nguyên nhân chính.

Có thể xem:

~~~java
try {
    runJob();
} catch (Exception e) {
    System.err.println("Cause: " + e);
    for (Throwable suppressed : e.getSuppressed()) {
        System.err.println("Cleanup also failed: " + suppressed);
    }
}
~~~

Mã minh họa; `runJob` phải tự đóng tài nguyên/cleanup bằng try-with-resources theo policy. Trong production, log lỗi không nên chứa nội dung input nhạy cảm.

### I/O bất đồng bộ và process con

Nếu file tạm đang dùng bởi `AsynchronousFileChannel`, process khác hoặc background task, việc đóng wrapper ở thread chính **không chứng minh** mọi thao tác pending đã hoàn tất và kết quả đã được tiêu thụ. Cần phối hợp lifecycle:

~~~text
CREATE TEMP -> SUBMIT WORK -> WAIT / CANCEL / DRAIN
                              |
                              v
                     CLOSE ALL FILE HANDLES
                              |
                              v
                      DELETE TEMP WORKSPACE
~~~

Thời điểm xóa chỉ nên đến khi không còn bên hợp lệ cần sử dụng file. Nếu job bị hủy, hủy tác vụ trước, đợi hoặc cô lập đúng cách, rồi cleanup với timeout/giám sát phù hợp.

## 13. Lỗi cleanup trong môi trường thực tế

| Vấn đề | Nguyên nhân có thể | Phản ứng phù hợp |
|---|---|---|
| `DirectoryNotEmptyException` | Child chưa xóa, process khác vừa tạo file | Kiểm tra ownership, duyệt đúng thứ tự, hạn chế writer |
| `AccessDeniedException` | Quyền/ACL không cho xóa hoặc file đang được giữ | Đóng handle, kiểm policy, ghi nhận lỗi |
| `NoSuchFileException` | Một tác nhân khác đã xóa | `deleteIfExists` khi điều đó hợp lệ |
| `FileSystemException` | Volume lỗi, file busy, provider constraint | Báo lỗi vận hành và retry có giới hạn nếu an toàn |
| Disk full | Ghi file/metadata không đủ chỗ | Giới hạn quota, fail request, cleanup các file đã tạo |
| Process crash/KILL | `finally`/shutdown hook không chạy | Startup sweeper theo ownership và TTL, ngoài luồng nghiệp vụ |
| Symlink xuất hiện trong temp tree | Pathname có thể đã bị thay | Tránh follow link, xem xét đối thủ cùng UID, dùng directory handles khi cần |
| Thư viện giữ file handle | Windows có thể không cho xóa khi đang mở | Đóng toàn bộ readers/writers/process trước cleanup |

**Không khuyến khích retry xóa vô hạn.** Retry chỉ có ích nếu lỗi có thể hồi phục (file còn tạm thời đang được dùng) và có deadline rõ. Lỗi permission do chính sách sai cần sửa ownership/ACL, không phải tăng số lượt thử.

## 14. Xử lý dữ liệu nhạy cảm khi ghi vào file tạm

Một file tạm chứa token hoặc thông tin định danh nên có chính sách rõ:

1. **Data minimization:** có cần lưu ra đĩa không? Nếu dữ liệu nhỏ và thời gian xử lý ngắn, có thể xử lý trong memory.
2. **Quyền/identity:** chạy với service account riêng, private temp root, quyền file owner-only hoặc ACL tương đương đã kiểm chứng.
3. **Không lộ tên:** không để thông tin nhạy cảm vào prefix/suffix, log path hay exception message cho người dùng cuối.
4. **Không ghi lại quá nhiều:** không tạo bản sao trung gian không cần thiết.
5. **Giới hạn dung lượng:** đặt max bytes per request, per job, per worker và quota toàn scratch volume.
6. **Quy định thời gian lưu:** giữ file ngắn nhất có thể, dọn ngay sau completion/abort, xử lý orphaned files theo TTL.
7. **Mã hóa nếu cần:** cân nhắc mã hóa đĩa hoặc từng file khi threat model bao gồm mất/đánh cắp thiết bị, snapshot hoặc backup.
8. **Hạn chế thư viện bên thứ ba:** khi dùng công cụ chuyển đổi ảnh/PDF/ZIP, xác định thư viện có tự tạo tệp tạm ở đâu, có tôn trọng TMPDIR và cleanup không.

### Delete không phải secure erase

`Files.delete(...)` xóa một entry filesystem. Trên SSD, copy-on-write filesystem, journal, snapshot, backup hoặc storage ảo hóa, dữ liệu có thể vẫn tồn tại trong các block hoặc bản sao. Đừng hứa “gọi delete là không thể phục hồi”. Với dữ liệu mật, kết hợp encryption-at-rest, quản lý key, chính sách retention và hủy key khi cần.

## 15. Upload và giải nén: chống lạm dụng ổ đĩa

Một hệ thống nhận upload cần làm hơn việc tạo tên file khó đoán:

- Chặn kích thước HTTP request trước khi ghi xuống scratch.
- Áp dụng quota số file và tổng byte trên mỗi request/user/job.
- Với ZIP, chống zip bomb: giới hạn tổng dữ liệu sau giải nén, tỷ lệ nén, số entry, độ sâu directory và thời gian xử lý.
- Chống path traversal: entry name như `../../secret.txt` không được phép thoát ra khỏi private temp root.
- Không dựa duy nhất vào `Path.normalize().startsWith(root)` khi đối thủ có thể kiểm soát symlink và thư mục con; cần kiểm tra đường dẫn thực/handle cùng chính sách chống TOCTOU.
- Không sao chép tên file upload nguyên văn thành tên file trên đĩa. Dùng tên server-generated và lưu tên hiển thị như metadata đã sanitize.
- Sau lỗi import hoặc format parsing, dọn toàn bộ workspace mà job sở hữu, không để lại file chứa dữ liệu vừa upload.

Đoạn kiểm tra **cơ bản** chống traversal theo chuỗi đường dẫn:

~~~java
// Minh họa: root là thư mục private đã chuẩn hóa,
// entryName lấy từ archive, root không cho bên lạ sửa.
Path target = root.resolve(entryName).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("Archive path escapes workspace");
}
~~~

Đây **chưa đủ chống symlink race** nếu untrusted code có thể đặt symlink/đổi directory trong subtree. Cần lớp kiểm soát thêm, không dùng đoạn này làm bằng chứng security hoàn chỉnh cho extractor nhận nội dung thù địch.

## 16. Dọn file tạm tồn dư sau crash: startup sweeper

Không phải mọi ứng dụng đều có thể đảm bảo `finally` chạy. Có thể xây một tiến trình dọn **orphaned workspace** theo thời hạn:

~~~text
scratch-root/  (root được dịch vụ quản lý)
  job-<generated>/        createdAt=...
  job-<generated>/        createdAt=...
  job-<generated>/        createdAt=...

Sweeper (ngoài đường xử lý request):
  -> liệt kê workspace thuộc ứng dụng
  -> bỏ qua job đang có lease/heartbeat hợp lệ
  -> chọn thư mục hết TTL an toàn
  -> kiểm tra ownership/root boundaries
  -> xóa cây với quy tắc no-follow và giới hạn
  -> log failures để cảnh báo
~~~

**Không xóa mọi thư mục có prefix giống nhau** trong một folder shared; file do job khác hoặc người dùng khác có thể trùng prefix. Sweeper cần quyền sở hữu rõ ràng (thư mục parent ứng dụng kiểm soát, metadata/lease đáng tin, account riêng) và chính sách chống xóa nhầm.

Nếu ứng dụng có nhiều instance cùng chia sẻ scratch volume, mỗi instance/job nên có namespace riêng và cơ chế fencing/lease nếu bắt buộc; TTL một mình có thể xóa file của job đang chạy rất lâu.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| “Tên khó đoán đủ bảo mật tệp tạm” | Cần quyền và parent directory đáng tin. |
| “Files.createTempFile chỉ tạo tên” | Phương thức tạo file thực sự. |
| “Đã createTempFile rồi thì dùng CREATE_NEW khi mở lại” | CREATE_NEW sẽ báo file đã tồn tại. |
| “0600 bảo vệ file ngay cả khi parent cho attacker thay entry” | Parent ghi được có thể gây pathname race. |
| “Tạo file rồi chmod tương đương set quyền lúc tạo” | Có thể có cửa sổ lộ quyền; dùng FileAttribute khi tạo. |
| “POSIX permission string áp dụng mọi Windows filesystem” | Windows thường dùng ACL/provider khác. |
| “NOFOLLOW_LINKS chặn mọi đường tấn công filesystem” | Không chặn hết các thành phần cha, hardlink hoặc đổi directory. |
| “Files.isSymbolicLink rồi open là race-free” | Có TOCTOU giữa check và use. |
| “deleteOnExit chắc chắn xóa khi crash” | Không chạy khi kill/OS crash và file tồn tại suốt runtime. |
| “deleteIfExists nuốt mọi lỗi” | Vẫn có thể ném IOException/AccessDenied. |
| “Đóng channel là xóa mọi file” | Không; close và delete là các thao tác riêng. |
| “DELETE_ON_CLOSE luôn dùng được trên mọi provider” | Có thể unsupported, ảnh hưởng khả năng mở lại file. |
| “walkFileTree luôn an toàn trước concurrent attacker” | Pathname có thể bị thay; dùng directory handle nếu cần. |
| “Xóa file xong nghĩa là secure erase” | Dữ liệu có thể còn trong block/snapshot/backup. |
| “Một request được xóa toàn bộ thư mục tmp” | Chỉ xóa subtree chính request tạo và sở hữu. |
| “Mỗi request có thể dùng vô hạn scratch space” | Phải có quota, limit và cơ chế cleanup. |

## 18. Checklist triển khai

1. Xác định dữ liệu có nhạy cảm hay không và yêu cầu thời gian lưu.
2. Chọn parent scratch root do dịch vụ quản lý, giới hạn quyền ghi/traverse.
3. Tạo private temp directory riêng cho job nếu xử lý nhiều bước.
4. Dùng `Files.createTempFile/createTempDirectory` thay tên cố định hoặc check-then-create.
5. Thiết lập `FileAttribute` lúc tạo nếu filesystem hỗ trợ, xác minh quyền thực tế.
6. Với Windows, thiết kế/kiểm tra ACL; nếu không đáp ứng chính sách bảo mật, fail closed.
7. Không lưu thông tin bí mật trong tên file hay log đường dẫn.
8. Tránh symlink TOCTOU; `NOFOLLOW_LINKS` chỉ là một lớp phòng vệ.
9. Dùng try-with-resources đóng streams/channels và cleanup cả khi exception.
10. Với async/process con, chỉ xóa sau khi ownership được trả về hoặc operation được cô lập đúng cách.
11. Dọn thư mục con trước parent, không follow symlink, không nhận path-to-delete từ request.
12. Ghi nhận và xử lý lỗi cleanup; không bỏ qua lỗi hoặc retry vô hạn.
13. Đặt giới hạn số file/byte/thời gian; chống ZIP bomb và path traversal.
14. Dùng cleanup ngay sau job; không dựa vào deleteOnExit làm phương án chính.
15. Có sweeper cho orphaned workspaces sau crash và tránh xóa job còn hoạt động.
16. Kiểm thử Windows/Linux/container và filesystem sản xuất, không suy luận mọi provider có cùng khả năng.

## 19. Câu hỏi tự kiểm tra

1. `Files.createTempFile(...)` chỉ trả tên hay tạo file? **Nó tạo file thực sự.**
2. Nếu parent shared writable, tên file ngẫu nhiên có đủ chống đọc/tráo không? **Không; cần quyền/ownership và kiểm soát directory.**
3. Mode POSIX thường phù hợp cho file chứa dữ liệu riêng tư? **`rw-------` (0600)**.
4. Mode POSIX thường phù hợp cho thư mục scratch chỉ owner truy cập? **`rwx------` (0700)**.
5. Vì sao truyền `asFileAttribute(...)` ngay khi tạo? **Tránh khoảng hở trước khi set quyền sau tạo.**
6. Có thể áp dụng POSIX mode trực tiếp cho mọi Windows ACL filesystem không? **Không.**
7. Đã `createTempFile` rồi mở bằng `CREATE_NEW` có đúng không? **Không, file đã tồn tại.**
8. `NOFOLLOW_LINKS` có chặn mọi kiểu TOCTOU không? **Không, chỉ một lớp kiểm soát.**
9. `Files.deleteIfExists(...)` có luôn thành công nếu file còn mở không? **Không.**
10. `deleteOnExit()` có chạy khi JVM bị kill cưỡng bức không? **Không được bảo đảm.**
11. `walkFileTree` mặc định có tự đi theo symbolic links không? **Không.**
12. Vì sao xóa children trước khi xóa thư mục? **Directory còn entry thường không được xóa.**
13. Tại sao `try-with-resources` tốt cho cleanup hơn `finally` đơn giản? **Nó quản lý close và suppressed exceptions.**
14. `Files.delete` có chứng minh secure erase trên SSD/snapshot không? **Không.**
15. Nếu job bị hủy giữa async write, có nên xóa file ngay khi background task vẫn dùng? **Không; cần phối hợp completion/cancel/close và ownership.**
16. Cần gì để dọn file sau crash khi `finally` không chạy? **Sweeper/TTL có ràng buộc ownership và tránh xóa nhầm.**

## 20. Tham khảo chính thức

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `createTempDirectory`, `newByteChannel`, `delete`, `deleteIfExists`, `walkFileTree`.
- [Java SE 17 — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): `fromString` và `asFileAttribute`.
- [Java SE 17 — PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): quyền, owner và thuộc tính POSIX.
- [Java SE 17 — AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): chính sách ACL trên provider tương ứng.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác relative-to-directory an toàn hơn trước pathname races khi provider hỗ trợ.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `TRUNCATE_EXISTING`, `DELETE_ON_CLOSE`.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Java SE 17 — File.deleteOnExit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html#deleteOnExit()): giới hạn của cleanup khi JVM kết thúc.
