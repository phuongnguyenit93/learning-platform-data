# Giữ đường dẫn mục giải nén trong vùng đích cho phép (Java NIO.2 và ZIP)

> **Mục tiêu:** Ngăn *Zip Slip* — lỗi cho phép tên mục trong ZIP làm extractor ghi file **ra ngoài thư mục đích được phép**. Khi nhận ZIP từ nguồn không tin cậy, phải kiểm tra tên từng `ZipEntry`, tính `Path` bên dưới root được kiểm soát, tránh symbolic-link escapes, không tự ghi đè, giới hạn dữ liệu và chỉ công bố kết quả sau khi toàn bộ archive đã được xác minh. Bài dùng API NIO.2 từ **Java 7** hiện vẫn áp dụng và những tiện ích trong **Java 11**, minh họa bằng **JDK 17**. Mục tiêu là hiểu đầy đủ mô hình an toàn chứ không chỉ học một biểu thức `normalize().startsWith(root)`.

## 1. Vấn đề của entry name chưa được tin cậy

Một ZIP archive có thể chứa những mục:

```text
documents/readme.txt
images/icon.png
../escape.txt
../../secrets/config.txt
/absolute/path.txt
C:/Windows/system.ini
folder\..\escape.txt
```

Một extractor ngây thơ tạo output bằng cách nối tên entry với root:

```java
Path output = root.resolve(entry.getName());
Files.copy(zipInputStream, output);
```

Đây là **đoạn minh họa sai**, không sử dụng cho ZIP từ người dùng. Tên `../escape.txt` có thể dẫn ra thư mục cha; tên absolute trên một hệ thống có thể bỏ qua root; dấu `\` có thể là separator trên Windows; còn thư mục cha bên trong root có thể là symlink tới nơi khác. Dữ liệu độc hại có thể viết đè configuration, file người khác hoặc một vị trí trái quyền.

### 1.1. Cần phân biệt ba loại đường dẫn

| Đường dẫn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Archive host Path | `/tmp/upload.zip` | File ZIP trên filesystem host |
| Entry name | `docs/readme.txt` | Chuỗi tên nằm trong archive, **chưa tin cậy** |
| Output host Path | `/srv/app/staging/docs/readme.txt` | Nơi được phép ghi sau khi validate |

Khi dùng ZIP FileSystem (`jdk.zipfs`), `zipFs.getPath("/docs/readme.txt")` là Path **bên trong ZIP**, không phải Path của host. Khi copy ZIP entry ra host phải tạo một host Path mới từ output root được phép.

### 1.2. Điều kiện đúng cần đồng thời thỏa mãn

1. Chỉ chấp nhận tên entry theo một grammar đã định, **không tin raw string**.
2. Entry phải tương đối, không được absolute/drive/UNC.
3. Không cho bất kỳ thành phần `..` hoặc `.` không mong muốn; có quy tắc cho backslash, dấu hai chấm, tên thiết bị.
4. Sau khi ghép, Path chuẩn hóa nằm dưới root theo **Path components**, không phải String prefix.
5. Root/parent directories là directories thực, không phải symlinks bị lợi dụng.
6. Attacker không thể đổi root/parent entries trong lúc extraction, hoặc cần dùng cơ chế directory handle.
7. Output file mới được tạo bằng `CREATE_NEW`; không mặc định overwrite.
8. Có giới hạn số entry, độ sâu tên, bytes giải nén từng entry, tổng bytes và thời gian.
9. Archive lỗi phải bị từ chối; output chưa hoàn tất chỉ nằm trong **staging riêng**, không publish.
10. Cleanup chỉ đụng tới resources **do job thực sự sở hữu**.

## 2. Hai sai lầm dễ gặp: String prefix và absolute Path

### 2.1. `String.startsWith` không kiểm tra directory boundary

Giả sử root là `/var/app/extract`, còn output là `/var/app/extract-backup/private.txt`. Chuỗi output vẫn bắt đầu bằng chữ `/var/app/extract` nhưng nằm ở **thư mục bên cạnh**.

```java
Path base = destination.toAbsolutePath().normalize();
Path candidate = base.resolve(relativeEntry).normalize();
if (!candidate.startsWith(base)) {
    throw new SecurityException("output escapes destination");
}
```

Đây là snippet với `Path destination`, `relativeEntry` đã được khai báo, và phù hợp khi `base` và candidate thuộc cùng provider. `Path.startsWith(Path)` kiểm tra prefix theo các **name elements**, tránh nhầm tên sibling cùng prefix như kiểm tra String.

### 2.2. `Path.resolve` có quy tắc với argument absolute

Đừng chỉ gọi `root.resolve(rawEntry)` rồi mặc định kết quả luôn dưới root. Nếu `rawEntry` là absolute, `resolve` có thể trả nguyên Path đó. Trên Windows còn có drive roots, UNC shares và quy tắc tên đặc biệt.

Phải **chặn tuyệt đối/drive** ngay từ trước khi resolve, đồng thời kiểm tra kết quả sau normalize. Hai bước bổ sung nhau.

### 2.3. `normalize` vẫn chỉ là lexical

`normalize` loại `.` và xử lý `..` theo các thành phần tên. Nó **không làm I/O**, không giải symbolic links, không kiểm tra quyền, không xác minh file tồn tại. Đường dẫn `root/shared/data.txt` nhìn có vẻ nằm trong root, nhưng `shared` có thể là symlink sang một thư mục ngoài root.

Đừng gọi `normalize().startsWith(base)` là một sandbox hoàn chỉnh. Nó là **bước kiểm tra tên**, chưa phải kiểm soát cả filesystem.

## 3. Chọn grammar ZIP entry nghiêm ngặt, portable

Tên ZIP thông thường dùng `/` làm separator. Để có cùng cách diễn giải giữa Windows và Unix, bài chọn **một strict profile**:

- Không null/empty; không bắt đầu bằng `/` hoặc `\`.
- Cấm mọi `\`, vì có thể là path separator trên Windows nhưng là ký tự thường ở Unix.
- Cấm `:`, giảm ambiguity với Windows drive và alternate data streams.
- Cấm NUL/control characters.
- Cấm `//`, thành phần rỗng, `.` và `..`.
- Cho phép một dấu `/` ở cuối khi entry là directory.
- Cấm component kết thúc bằng dấu chấm hoặc khoảng trắng để giảm khác biệt cách đặt tên trên Windows.
- Cấm `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9` kể cả phần mở rộng.
- Tính relative Path bằng **filesystem của root**, giải target từ root rồi normalize.
- Từ chối target bằng chính root hoặc không nằm dưới root.
- Cuối cùng phải thực hiện các bước I/O có bảo vệ: kiểm tra parent directories, mở file CREATE_NEW và ngân sách dữ liệu.

**Đây là chính sách bảo thủ của ứng dụng**, không phải toàn bộ chuẩn ZIP. Một ZIP hợp lệ theo quy ước khác vẫn có thể bị từ chối. Khi nghiệp vụ buộc hỗ trợ tên Unicode phức tạp, đường dẫn từ nhiều hệ điều hành hay archive legacy, phải định nghĩa một chính sách mapping rõ ràng và kiểm thử collision thực tế, không bỏ validation để “cho dễ chạy”.

### 3.1. Vì sao từ chối cả `docs/../inside.txt`?

Dù normalize có thể đặt nó trong root, `..` khiến semantics khó hơn khi tồn tại symlink ancestors, provider differences hoặc xử lý khác nhau trước/sau canonicalization. Strict policy **không cho `..` ở mọi vị trí**, đơn giản và dễ kiểm toán hơn.

### 3.2. Vì sao `.hidden.txt` được phép còn `.` không?

Tên `.hidden.txt` là một component thông thường, khác với component `.` có ý nghĩa “thư mục hiện tại”. Chính sách phân biệt hai trường hợp này.

## 4. Chương trình 1: kiểm tra tên ZIP entry thuần Path

Không cần quyền tạo symlink hoặc có file ZIP thật. Lưu thành `ZipEntryPathPolicyDemo.java`:

```java
import java.nio.file.Path;
import java.util.Locale;

public class ZipEntryPathPolicyDemo {
    static Path resolveEntry(Path root, String name, boolean directory) {
        if (name == null || name.isEmpty() || name.startsWith("/")
                || name.indexOf('\\') >= 0 || name.indexOf(':') >= 0
                || name.indexOf('\0') >= 0 || name.contains("//")) {
            throw new IllegalArgumentException("unsafe name");
        }
        if (directory != name.endsWith("/")) {
            throw new IllegalArgumentException("entry type mismatch");
        }
        String trimmed = directory ? name.substring(0, name.length() - 1) : name;
        if (trimmed.isEmpty()) throw new IllegalArgumentException("empty path");
        for (String part : trimmed.split("/", -1)) {
            String upper = part.toUpperCase(Locale.ROOT);
            if (part.isEmpty() || part.equals(".") || part.equals("..")
                    || part.endsWith(".") || part.endsWith(" ")
                    || upper.matches("(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\\..*)?")
                    || part.chars().anyMatch(c -> c < 32 || c == 127)) {
                throw new IllegalArgumentException("unsafe segment");
            }
        }
        Path base = root.toAbsolutePath().normalize();
        Path relative = base.getFileSystem().getPath(trimmed);
        if (relative.isAbsolute() || relative.getRoot() != null) {
            throw new IllegalArgumentException("absolute entry");
        }
        Path output = base.resolve(relative).normalize();
        if (!output.startsWith(base) || output.equals(base)) {
            throw new IllegalArgumentException("outside root");
        }
        return output;
    }

    public static void main(String[] args) {
        Path root = Path.of("safe-extract").toAbsolutePath().normalize();
        String[] entries = {
            "docs/readme.txt", "img/icons/", "../escape.txt",
            "docs/../../outside.txt", "/absolute.txt", "C:/Windows/win.ini",
            "docs\\backslash.txt", "docs//duplicate.txt",
            "./hidden.txt", "docs/../inside.txt", "CON.txt",
            ".hidden.txt", "docs/trailing. ", "docs/note.txt"
        };
        for (String name : entries) {
            try {
                boolean directory = name.endsWith("/");
                Path dest = resolveEntry(root, name, directory);
                System.out.println("ALLOW " + name + " -> " +
                        root.relativize(dest).toString().replace('\\', '/'));
            } catch (IllegalArgumentException denied) {
                System.out.println("REJECT " + name.replace('\\', '/'));
            }
        }
    }
}
```

Chạy bằng JDK 17:

```bash
javac -encoding UTF-8 --release 17 ZipEntryPathPolicyDemo.java
java ZipEntryPathPolicyDemo
```

Stdout **đã kiểm thử**:

```text
ALLOW docs/readme.txt -> docs/readme.txt
ALLOW img/icons/ -> img/icons
REJECT ../escape.txt
REJECT docs/../../outside.txt
REJECT /absolute.txt
REJECT C:/Windows/win.ini
REJECT docs/backslash.txt
REJECT docs//duplicate.txt
REJECT ./hidden.txt
REJECT docs/../inside.txt
REJECT CON.txt
ALLOW .hidden.txt -> .hidden.txt
REJECT docs/trailing. 
ALLOW docs/note.txt -> docs/note.txt
```

### 4.1. Vì sao test in `docs/backslash.txt` ở dòng REJECT?

Vì câu lệnh in dùng `replace('\\','/')` để **định dạng output ổn định**. Input ban đầu chứa `\` đã bị từ chối. Đừng hiểu đó là bộ chuẩn hóa biến input độc hại thành hợp lệ.

### 4.2. Quy tắc dấu slash cuối

Directory entry có thể kết thúc `/`. Policy tách dấu đó để kiểm tra các thành phần tên rồi tạo host directory. File entry không thể kết thúc `/` theo quy ước được chọn. Không bao giờ cho tên rỗng hoặc `/` ghi vào chính root.

### 4.3. Đây chưa phải extractor hoàn chỉnh

`resolveEntry` chỉ tính một Path hợp lệ về **mặt tên**. Nó không chứng minh directory thật tồn tại, không kiểm tra symlink, không ngăn ghi đè, không kiểm soát quota và không bảo đảm người khác không sửa cây đích giữa kiểm tra và ghi.

## 5. Chọn root staging do ứng dụng sở hữu

Một biện pháp mạnh là không giải nén trực tiếp vào thư mục chứa dữ liệu hoạt động của người dùng. Thay vào đó, mỗi upload/job dùng **staging directory mới, riêng**, chỉ process tin cậy có quyền ghi:

```java
Path work = Files.createTempDirectory("extract-");
Path stage = Files.createDirectory(work.resolve("stage"));
```

Đây là snippet với `Files`/`Path` và method xử lý IOException.

Đừng hiểu `Files.createTempDirectory` một mình bảo đảm permission isolation trên mọi nền tảng. Production phải xác minh ACL/quyền của thư mục cha, sandbox/container/tenant isolation và quyền tài khoản chạy. Mục đích là **không cho attacker sửa entry/staging đồng thời**.

### 5.1. Luồng lifecycle nên dùng

```text
Nhận archive
   |
   v
Tạo staging riêng + kiểm tra quyền
   |
   v
Đọc entry -> validate name -> validate output Path
   |
   v
Kiểm tra parent directories -> create new file -> stream giới hạn
   |
   v
Nếu có lỗi: abort + đóng streams + dọn staging, KHÔNG publish
   |
   v
Nếu toàn bộ thành công: kiểm tra nghiệp vụ/integrity
   |
   v
Publish kết quả theo chính sách riêng
```

Giải nén nhiều file không tự là transaction. `ATOMIC_MOVE` có thể không được hỗ trợ giữa filesystems hoặc thư mục riêng; không hứa một loạt file được publish nguyên tử nếu chưa thiết kế được điều đó.

### 5.2. Vì sao tạo staging mới trước khi kiểm tra archive?

Nếu entry thứ 100 độc hại, 99 file trước có thể đã được ghi. Trên staging riêng, chúng không trở thành dữ liệu được công bố. Nếu giải nén trực tiếp vào output chính, chương trình có thể để lại file dở hoặc overwrite dữ liệu của người khác trước khi phát hiện archive lỗi.

## 6. Symlink parent: vấn đề mà normalize không giải quyết

Giả sử:

```text
/app/extract/
   reports -> /outside/private/
```

Tên entry `reports/data.txt` qua `normalize` vẫn bắt đầu bằng `/app/extract`. Nhưng nếu thao tác ghi file theo symlink `reports`, nó có thể kết thúc tại `/outside/private/data.txt`.

### 6.1. Kiểm tra thư mục cha với `NOFOLLOW_LINKS`

`Files.readAttributes(dir, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)` xem **directory entry** chứ không tự đi theo symlink. Đối với mỗi component trong đường dẫn từ root tới parent của file:
- Nếu component chưa có, tạo directory mới trong root.
- Nếu đã có, xác nhận là directory thực, **không phải symbolic link**.
- Nếu là file thường hoặc symlink, từ chối.
- Đảm bảo root/ancestor không được untrusted actor thay thế trong suốt extraction, hoặc dùng cách làm dựa trên handles.

`Files.createDirectories(parent)` riêng lẻ không phải giải pháp chống symlink: khi một directory path đã tồn tại dưới dạng link đến directory khác, method có thể follow link hoặc xem target là directory tùy API/provider. Vì vậy code có kiểm tra từng component.

### 6.2. `NOFOLLOW_LINKS` ở file cuối không bảo vệ mọi ancestor

`Files.newOutputStream(target, CREATE_NEW, WRITE, NOFOLLOW_LINKS)` kiểm soát thao tác tạo **file đích**. Nó không tự cấm `target.getParent()` là symlink. Cần kết hợp cả ownership/quyền thư mục, kiểm tra parents và, nếu threat model có concurrent attacker, directory-handle APIs.

### 6.3. TOCTOU là gì?

Một chương trình có thể đọc metadata và xác nhận parent là directory thật ở T1. Nếu user có quyền thay nó bằng symlink trước khi thao tác mở file ở T2, kết quả có thể khác. Đây là *time-of-check to time-of-use*. `toRealPath` cũng chỉ chứng minh real path **ở thời điểm gọi**, không tự giữ directory entry bất biến.

Không quảng cáo việc kiểm tra từng directory component là bảo vệ tuyệt đối trên một cây mà attacker có quyền sửa đồng thời.

## 7. Chương trình 2: extractor an toàn theo threat model staging riêng

Chương trình dưới đây:
- tạo một ZIP hợp lệ và một ZIP chứa `../escape.txt`;
- tạo hai staging roots riêng trong temp directory do chính nó sở hữu;
- kiểm tra tên từng entry **trước khi ghi**;
- xác nhận root và các parent directories bằng metadata `NOFOLLOW_LINKS`;
- dùng `CREATE_NEW` và `NOFOLLOW_LINKS` cho file mới;
- giới hạn bytes từng file/tổng và số entries;
- từ chối archive ngay khi gặp tên entry nguy hiểm;
- không publish staging khi lỗi;
- dọn riêng mọi file tạm do demo tạo.

Lưu thành `ZipSlipSafeExtractionDemo.java`:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Comparator;
import java.util.Locale;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipSlipSafeExtractionDemo {
    static Path destination(Path root, ZipEntry entry) {
        String name = entry.getName();
        if (name == null || name.isEmpty() || name.startsWith("/")
                || name.indexOf('\\') >= 0 || name.indexOf(':') >= 0
                || name.indexOf('\0') >= 0 || name.contains("//")) {
            throw new IllegalArgumentException("unsafe entry");
        }
        String[] parts = name.split("/", -1);
        int count = entry.isDirectory() ? parts.length - 1 : parts.length;
        if (count == 0 || (entry.isDirectory() && !parts[parts.length - 1].isEmpty())) {
            throw new IllegalArgumentException("empty entry");
        }
        for (int i = 0; i < count; i++) {
            String part = parts[i];
            String upper = part.toUpperCase(Locale.ROOT);
            if (part.isEmpty() || part.equals(".") || part.equals("..")
                    || part.endsWith(".") || part.endsWith(" ")
                    || upper.matches("(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\\..*)?")
                    || part.chars().anyMatch(c -> c < 32 || c == 127)) {
                throw new IllegalArgumentException("unsafe segment");
            }
        }
        Path relative = root.getFileSystem().getPath(String.join("/",
                java.util.Arrays.copyOf(parts, count)));
        Path resolved = root.resolve(relative).normalize();
        if (relative.isAbsolute() || resolved.equals(root) || !resolved.startsWith(root)) {
            throw new IllegalArgumentException("escapes root");
        }
        return resolved;
    }

    static void makeDirectoriesNoLinks(Path root, Path dir) throws IOException {
        Path current = root;
        for (Path part : root.relativize(dir)) {
            current = current.resolve(part);
            try {
                Files.createDirectory(current);
            } catch (FileAlreadyExistsException alreadyThere) {
                // Verify the existing entry below, without following a symbolic link.
            }
            BasicFileAttributes attrs = Files.readAttributes(
                    current, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attrs.isDirectory() || attrs.isSymbolicLink()) {
                throw new IOException("unsafe directory entry");
            }
        }
    }

    static void writeEntry(ZipOutputStream out, String name, String text)
            throws IOException {
        out.putNextEntry(new ZipEntry(name));
        out.write(text.getBytes(StandardCharsets.UTF_8));
        out.closeEntry();
    }

    static void makeArchive(Path zip, boolean malicious) throws IOException {
        try (ZipOutputStream out = new ZipOutputStream(Files.newOutputStream(zip))) {
            writeEntry(out, "good/data.txt", "DATA");
            writeEntry(out, "good/sub/nested.txt", "NESTED");
            if (malicious) writeEntry(out, "../escape.txt", "BAD");
        }
    }

    static int extract(Path archive, Path root) throws IOException {
        BasicFileAttributes base = Files.readAttributes(root,
                BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!base.isDirectory() || base.isSymbolicLink()) {
            throw new IOException("root is not a real directory");
        }
        int files = 0;
        int entryCount = 0;
        int totalBytes = 0;
        try (ZipInputStream in = new ZipInputStream(Files.newInputStream(archive))) {
            ZipEntry entry;
            while ((entry = in.getNextEntry()) != null) {
                if (++entryCount > 20) throw new IOException("entry limit reached");
                Path dest = destination(root, entry); // Reject before writing or skipping data.
                if (entry.isDirectory()) {
                    makeDirectoriesNoLinks(root, dest);
                } else {
                    makeDirectoriesNoLinks(root, dest.getParent());
                    OutputStream created = Files.newOutputStream(dest,
                            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE,
                            LinkOption.NOFOLLOW_LINKS);
                    boolean complete = false;
                    try {
                        try (OutputStream out = created) {
                            int fileBytes = 0;
                            byte[] buffer = new byte[512];
                            int count;
                            while ((count = in.read(buffer)) != -1) {
                                fileBytes += count;
                                totalBytes += count;
                                if (fileBytes > 64 || totalBytes > 128) {
                                    throw new IOException("uncompressed-size limit");
                                }
                                out.write(buffer, 0, count);
                            }
                        }
                        complete = true;
                    } finally {
                        if (!complete) Files.deleteIfExists(dest);
                    }
                    files++;
                }
                in.closeEntry();
            }
        }
        return files;
    }

    static void deleteOwnedTree(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path p : (Iterable<Path>)
                    paths.sorted(Comparator.reverseOrder())::iterator) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("safe-extract-");
        try {
            Path safeZip = work.resolve("safe.zip");
            Path badZip = work.resolve("bad.zip");
            Path safeRoot = Files.createDirectory(work.resolve("safe-stage"));
            Path badRoot = Files.createDirectory(work.resolve("bad-stage"));
            makeArchive(safeZip, false);
            makeArchive(badZip, true);

            System.out.println("safeFiles=" + extract(safeZip, safeRoot));
            System.out.println("safeData=" +
                    Files.readString(safeRoot.resolve("good/data.txt")));
            System.out.println("safeNested=" +
                    Files.readString(safeRoot.resolve("good/sub/nested.txt")));

            boolean blocked = false;
            try {
                extract(badZip, badRoot);
            } catch (IllegalArgumentException expected) {
                blocked = true;
            }
            System.out.println("unsafeArchiveBlocked=" + blocked);
            System.out.println("escapedFileExists=" +
                    Files.exists(work.resolve("escape.txt")));
        } finally {
            deleteOwnedTree(work); // Only the temporary directory made by this demo.
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ZipSlipSafeExtractionDemo.java
java ZipSlipSafeExtractionDemo
```

Stdout đã chạy trên JDK 17:

```text
safeFiles=2
safeData=DATA
safeNested=NESTED
unsafeArchiveBlocked=true
escapedFileExists=false
```

### 7.1. Tại sao số file hợp lệ là 2?

`safe.zip` chứa hai mục file: `good/data.txt` và `good/sub/nested.txt`. Chương trình tạo các thư mục cha cần thiết, chỉ đếm file đã ghi. Nội dung được đối chiếu bằng `Files.readString`.

### 7.2. Tại sao archive xấu bị từ chối?

`bad.zip` có hai file hợp lệ rồi đến `../escape.txt`. Khi tới mục nguy hiểm, `destination` phát hiện segment `..` và ném `IllegalArgumentException` trước khi mở output cho entry đó. Vì vậy `unsafeArchiveBlocked=true` và không có file thoát root.

Hai file trước đó **có thể đã nằm trong bad-stage**. Đây là lý do archive không được publish khi thất bại; chương trình dọn toàn bộ workspace trong `finally`. Một dịch vụ cần dọn staging hỏng hoặc giữ cách ly với chính sách expiry/audit, tuyệt đối không expose partial outputs.

### 7.3. Vì sao không “skip” malicious entry rồi tiếp tục?

`ZipInputStream.closeEntry()` có thể phải đọc/tiêu thụ phần nội dung còn lại để sang entry kế tiếp. Với ZIP bombs, thao tác bỏ qua vẫn có thể gây tốn CPU/I/O. Khi gặp tên entry không hợp lệ từ archive không tin cậy, **fail-fast và đóng stream** thường dễ kiểm soát hơn.

### 7.4. Đoạn tạo directory làm gì?

`makeDirectoriesNoLinks` tiến từng component từ root đến parent, cố tạo directory mới, hoặc nếu entry đã tồn tại thì đọc attrs `NOFOLLOW_LINKS` để từ chối file/symlink. Nó giảm khả năng đi theo một parent symlink có sẵn.

**Giới hạn:** nếu attacker được phép thay đường dẫn cha ngay sau metadata check, vẫn có race. Ví dụ dựa trên giả định stage do ứng dụng sở hữu và untrusted actors **không được sửa stage**.

### 7.5. Giới hạn bytes demo

`64 bytes/entry`, `128 bytes/job` và `20 entries` là limits nhỏ để minh họa. Ứng dụng thật tự định nghĩa số lượng/bytes/depth/time theo yêu cầu nghiệp vụ. Không lấy giới hạn của bài học làm mặc định production.

### 7.6. Cleanup có thể ném lỗi

Nếu I/O hoặc đóng stream thất bại, cleanup cũng có thể thất bại; production cần ghi lại nguyên nhân đầy đủ, không báo thành công. Chỉ xóa staging mà job sở hữu; đừng gọi cleanup lên một root tùy ý từ request.

## 8. Ghi file mới không ghi đè: `CREATE_NEW`

Đoạn dễ mắc lỗi:

```java
if (!Files.exists(target)) {
    Files.newOutputStream(target);
}
```

Đây là ví dụ **không đủ an toàn**: một tiến trình khác có thể tạo file sau check; mở stream với option mặc định có thể truncate một file đã có. `Files.exists` cũng không phải phép xác minh tuyệt đối, và không khóa directory entry.

Cách phù hợp hơn:

```java
try (OutputStream out = Files.newOutputStream(
        target,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE,
        LinkOption.NOFOLLOW_LINKS)) {
    // Ghi payload trong giới hạn đã kiểm tra.
}
```

Đây là snippet với `OutputStream`, `Path target`, method xử lý IOException và parent directories đã được bảo vệ. `CREATE_NEW` kiểm tra tồn tại và tạo file một cách nguyên tử tương ứng với filesystem operations, giảm race ở **tên cuối**. `NOFOLLOW_LINKS` không tự cấm symlinks ở **thư mục cha**.

### 8.1. Nếu open CREATE_NEW thất bại

Không được tự xóa `target` trong catch, vì target có thể là file của người khác đã tồn tại trước. Trong extractor mẫu, chỉ sau khi `newOutputStream` **thành công** mới có `created` stream. Nếu quá trình **ghi file mới do chính mình tạo** thất bại, finally mới xóa file đó. Đây là một khác biệt quan trọng giữa cleanup hợp lệ và xóa nhầm dữ liệu.

## 9. Chương trình 3: chống ghi đè với `CREATE_NEW` và `NOFOLLOW_LINKS`

Lưu thành `CreateNewNoFollowDemo.java`:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class CreateNewNoFollowDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-new-");
        Path target = root.resolve("report.txt");
        try {
            try (OutputStream out = Files.newOutputStream(target,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS)) {
                out.write("SAFE".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("created=" + Files.readString(target));
            try (OutputStream ignored = Files.newOutputStream(target,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS)) {
                System.out.println("overwriteBlocked=false");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("overwriteBlocked=true");
            }
            System.out.println("rootIsDirectory=" +
                    Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CreateNewNoFollowDemo.java
java CreateNewNoFollowDemo
```

Stdout đã kiểm chứng:

```text
created=SAFE
overwriteBlocked=true
rootIsDirectory=true
```

Lần đầu mở `CREATE_NEW` tạo file `SAFE`. Lần thứ hai cùng tên bị từ chối với `FileAlreadyExistsException` thay vì cắt ngắn dữ liệu. Mã này không thay thế các bước kiểm tra root và parent directories.

## 10. Symbolic link ở thư mục cha có thể vượt qua lexical containment

Giả sử `root/shared` là symlink trỏ tới `/other/private`. `root.resolve("shared/data.txt").normalize().startsWith(root)` có thể true, nhưng thực tế open có thể đi tới `/other/private/data.txt`.

Nên tách:
- **Lexical containment**: Path theo tên nằm dưới root.
- **Entry inspection**: parent entries thực là directories không phải symlinks.
- **Filesystem authorization**: caller được phép ghi vào đâu.
- **Race resistance**: có ai có quyền đổi entry giữa check và use hay không.

`Path.toRealPath()` giúp kiểm tra một đường dẫn đã tồn tại sau khi giải links, nhưng cũng chỉ phản ánh **thời điểm kiểm tra**, không đóng băng filesystem.

## 11. Chương trình 4: minh họa parent symlink và giới hạn kiểm thử

Lưu thành `SymlinkParentGuardDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class SymlinkParentGuardDemo {
    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("symlink-guard-");
        Path out = work.resolve("out");
        Path other = work.resolve("elsewhere");
        Path link = out.resolve("shared");
        try {
            Files.createDirectory(out);
            Files.createDirectory(other);
            try {
                Files.createSymbolicLink(link, other);
            } catch (IOException | UnsupportedOperationException | SecurityException unavailable) {
                System.out.println("symlink=SKIPPED");
                return;
            }
            Path target = out.resolve("shared/data.txt").normalize();
            boolean lexicalInside = target.startsWith(out);
            BasicFileAttributes attr = Files.readAttributes(
                    link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            boolean parentSymlink = attr.isSymbolicLink();
            boolean realParentInside =
                    link.toRealPath().startsWith(out.toRealPath());
            System.out.println("symlink=CREATED");
            System.out.println("lexicalInside=" + lexicalInside);
            System.out.println("parentIsSymlink=" + parentSymlink);
            System.out.println("realParentInside=" + realParentInside);
            System.out.println("rejectParent=" + parentSymlink);
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(other);
            Files.deleteIfExists(out);
            Files.deleteIfExists(work);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SymlinkParentGuardDemo.java
java SymlinkParentGuardDemo
```

Nếu provider cho tạo symbolic link, dự kiến:

```text
symlink=CREATED
lexicalInside=true
parentIsSymlink=true
realParentInside=false
rejectParent=true
```

**Kết quả thật trên Windows kiểm thử bị giới hạn quyền:**

```text
symlink=SKIPPED
```

Bài kiểm thử đã biên dịch và chạy, nhưng nhánh symlink thật **chưa được kiểm chứng thực nghiệm** trên máy này. Không được báo nhánh `CREATED` là PASS; cần chạy tại CI/test environment có quyền tạo symbolic links.

## 12. `SecureDirectoryStream` và TOCTOU

`java.nio.file.SecureDirectoryStream` có từ Java 7 và còn áp dụng cho ứng dụng nhạy cảm về race. Nó cho phép những thao tác I/O tương đối với một **directory handle đã mở**, giúp tránh một số race khi directory name bị thay trong thời gian thao tác.

Ví dụ nhận diện capability:

```java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    if (stream instanceof SecureDirectoryStream<?>) {
        // Có thể thiết kế traversal bằng open directory handles.
    } else {
        // Từ chối chế độ cần race-resistance hoặc dùng root đã khóa quyền.
    }
}
```

Đây là **snippet** có `DirectoryStream`, `SecureDirectoryStream`, `Files`, `Path` được import và method xử lý IOException; nó chưa phải extractor hoàn chỉnh.

`SecureDirectoryStream` cung cấp:
- `newDirectoryStream(relativeChild, NOFOLLOW_LINKS)`;
- `newByteChannel(relativeName, options, attrs)`;
- `deleteFile(relativeName)`, `deleteDirectory(relativeName)`;
- `move(relativeName, targetStream, targetName)`;
- `getFileAttributeView(...)`.

Nếu provider hỗ trợ, các operation này định vị entry tương đối với directory handle, giảm phụ thuộc vào tên đường dẫn ngoài có thể bị rename. Nhưng **không có nghĩa một đoạn `instanceof` tự động bảo vệ toàn bộ extractor**. Phải thiết kế traversal từng component, mở handles có `NOFOLLOW_LINKS`, kiểm tra quyền, quản lý handles và fail nếu thiếu khả năng an ninh cần thiết.

Nếu attacker có quyền sửa staging đồng thời và `SecureDirectoryStream` không hỗ trợ, không nên âm thầm hạ cấp sang check-then-write theo path string rồi tuyên bố race-free. Cần thay đổi mô hình permission/root isolation hoặc từ chối operation.

## 13. Giới hạn kích thước khi streaming ZIP

Tên entry hợp lệ vẫn có thể thuộc ZIP bomb. Kích thước ZIP nén nhỏ không chứng minh dữ liệu giải nén nhỏ.

### 13.1. `ZipEntry.getSize()` có thể là `-1`

Theo Javadoc, `getSize()` trả uncompressed size, **hoặc -1 nếu chưa biết**. Metadata có thể chỉ được biết sau khi xử lý entry; vì vậy không thể chỉ đọc size rồi `Files.copy` toàn bộ không giới hạn.

Quy tắc:
- dùng buffer cố định;
- đếm bytes **thực đọc từ ZIP input**;
- giới hạn bytes mỗi entry và bytes tổng;
- giới hạn số file, tên và độ sâu;
- xem xét thời gian/CPU, compression ratio, hạ tầng và memory quotas.

### 13.2. Vượt hạn mức thì stop, không chỉ “skip”

`ZipInputStream.closeEntry()` có thể tiêu thụ phần dữ liệu còn lại để đến entry tiếp theo. Với archive không tin cậy, limit exceeded nên kết thúc extraction, đóng stream và dọn staging; không cố đọc tiếp.

## 14. Chương trình 5: xác minh ngân sách bytes

Lưu thành `ZipStreamBudgetDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Arrays;
import java.util.zip.*;
import java.io.ByteArrayOutputStream;

public class ZipStreamBudgetDemo {
    static byte[] limitedRead(ZipInputStream in, int maxBytes) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[256];
        int n;
        while ((n = in.read(buf)) != -1) {
            if (out.size() + n > maxBytes) throw new IOException("too large");
            out.write(buf, 0, n);
        }
        return out.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        Path zip = Files.createTempFile("zip-budget-", ".zip");
        try {
            try (ZipOutputStream out = new ZipOutputStream(Files.newOutputStream(zip))) {
                out.putNextEntry(new ZipEntry("huge.txt"));
                byte[] huge = new byte[4096];
                Arrays.fill(huge, (byte)'A');
                out.write(huge);
                out.closeEntry();

                out.putNextEntry(new ZipEntry("small.txt"));
                out.write("OK".getBytes(StandardCharsets.UTF_8));
                out.closeEntry();
            }
            try (ZipInputStream in = new ZipInputStream(Files.newInputStream(zip))) {
                ZipEntry big = in.getNextEntry();
                boolean denied = false;
                try {
                    limitedRead(in, 128);
                } catch (IOException expected) {
                    denied = true;
                }
                System.out.println("largeRejected=" + denied);
                in.closeEntry();
                ZipEntry small = in.getNextEntry();
                System.out.println("smallName=" + small.getName());
                System.out.println("smallContent=" +
                        new String(limitedRead(in, 128), StandardCharsets.UTF_8));
                in.closeEntry();
            }
        } finally {
            Files.deleteIfExists(zip);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ZipStreamBudgetDemo.java
java ZipStreamBudgetDemo
```

Stdout đã kiểm chứng:

```text
largeRejected=true
smallName=small.txt
smallContent=OK
```

**Lưu ý quan trọng:** đây là bài test với fixture `4096 bytes` do chính chương trình tạo. Nó cố ý gọi `closeEntry` sau khi gặp limit để quan sát entry sau trong ZIP nhỏ đã biết. **Không dùng cách tiếp tục này cho ZIP độc hại trong production**: khi vượt hạn mức hãy abort stream ngay. Với file lớn thật, nên stream trực tiếp vào output giới hạn, thay vì tích lũy `ByteArrayOutputStream` trong RAM như demo nhỏ.

## 15. Dùng ZIP FileSystem khi cần nhưng không bỏ qua containment

Trong JDK hiện đại, module `jdk.zipfs` cho phép mount archive thành ZIP FileSystem:

```java
URI uri = URI.create("jar:" + archive.toUri());
try (FileSystem zipFs =
        FileSystems.newFileSystem(uri, Map.of("create", "true"))) {
    Path entry = zipFs.getPath("/docs/report.txt");
}
```

Đây là **snippet** trong method xử lý IOException, dùng ZIP provider có scheme `jar` và `Map.of` Java 9+. `archive` là Path của file ZIP trên host, còn `entry` là Path **bên trong ZIPFS**.

Khi copy entry sang host:
1. Xác định relative entry name theo policy.
2. Tạo host Path từ **host output root**.
3. Kiểm tra lexical containment và parents.
4. Dùng no-overwrite và quotas.
5. Copy/stream dữ liệu, kiểm tra I/O và cleanup.

Không tin ZIPFS tự sanitize mọi dữ liệu độc hại. Không dùng `zipEntry.toFile()` để biến ZIP entry thành host file; ZIP Path không phải file riêng trên host.

## 16. Chương trình 6: ZIPFS Path và host Path khác filesystem

Lưu thành `ZipFsCopyContainmentDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public class ZipFsCopyContainmentDemo {
    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("zipfs-contain-");
        Path archive = work.resolve("sample.zip");
        Path out = Files.createDirectory(work.resolve("output"));
        Path extracted = out.resolve("docs/report.txt");
        try {
            try (FileSystem zip = FileSystems.newFileSystem(
                    URI.create("jar:" + archive.toUri()), Map.of("create", "true"))) {
                Path entry = zip.getPath("/docs/report.txt");
                Files.createDirectories(entry.getParent());
                Files.writeString(entry, "FROM ZIP");

                Path relative = zip.getPath("/").relativize(entry);
                String relativeName = relative.toString().replace('\\', '/');
                Path target = out.resolve(relativeName).normalize();
                if (!target.startsWith(out) || target.equals(out)) {
                    throw new SecurityException("outside root");
                }
                Files.createDirectories(target.getParent());
                Files.copy(entry, target);
                System.out.println("entryUsesZip=" + (entry.getFileSystem() == zip));
                System.out.println("targetUsesDefault=" +
                        (target.getFileSystem() == FileSystems.getDefault()));
                System.out.println("insideOutput=" + target.startsWith(out));
                System.out.println("copied=" + Files.readString(target));
            }
        } finally {
            Files.deleteIfExists(extracted);
            Files.deleteIfExists(out.resolve("docs"));
            Files.deleteIfExists(out);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(work);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ZipFsCopyContainmentDemo.java
java ZipFsCopyContainmentDemo
```

Stdout đã kiểm chứng trên JDK 17 có `jdk.zipfs`:

```text
entryUsesZip=true
targetUsesDefault=true
insideOutput=true
copied=FROM ZIP
```

**Giới hạn của ví dụ:** archive, entry và root đều do chính demo tạo, không có input độc hại. `Files.createDirectories` và `Files.copy` ở đây **chỉ minh họa chuyển giữa hai FileSystem namespaces**, không phải extractor bảo mật cho ZIP tùy ý. Khi xử lý ZIP từ user, phải áp lại strict validator, parent `NOFOLLOW_LINKS`, CREATE_NEW, quotas và staging. Không được dùng mỗi đoạn này như một giải pháp Zip Slip hoàn chỉnh.

## 17. Các trường hợp path collision và metadata khác

Một ZIP có thể có:
- nhiều entry names trùng nhau;
- tên `Readme.txt` và `readme.txt` mà host case-insensitive coi là một file;
- hai chuỗi Unicode khác nhau nhưng host xử lý tương đương;
- một file `docs` và entry `docs/report.txt` tạo xung đột;
- tên thiết bị Windows hoặc phần mở rộng đặc biệt;
- directory entry lặp lại;
- metadata Unix symbolic-link dù ZIP reader đơn giản chỉ trình bày tên và bytes.

Không suy từ `String.equals` rằng hai entries chắc chắn tạo ra hai host files riêng. Kết quả thực tế phụ thuộc host provider và filesystem.

### 17.1. Chiến lược collision conservative

- Mở file đầu ra bằng `CREATE_NEW`.
- Nếu tên đã có: **fail** hoặc áp explicit business policy, không tự ghi đè.
- Với directory đã tồn tại: đọc attributes NOFOLLOW, từ chối nếu không phải real directory.
- Có thể giữ tập những tên đã thấy để reject duplicates sớm, nhưng vẫn phải dùng filesystem-level checks.
- Không thêm suffix tự động nếu điều đó phá cấu trúc archive/manifest mà nghiệp vụ cần.

### 17.2. Chú ý symlink entry bên trong ZIP

Một số định dạng ZIP lưu metadata biểu thị symbolic link. Không phải mọi Java ZIP API mặc định diễn giải nó như nhau. Nếu ứng dụng không cần symlinks, policy nên chỉ xuất regular file/directory đã xác minh và **không tự tạo symbolic links** từ nội dung archive. Đối với app cần links, phải có thiết kế riêng về target validation, vòng tham chiếu và root containment.

### 17.3. Encoding tên entry

`ZipInputStream` mặc định dùng UTF-8 cho tên ZIP khi phù hợp; có constructor với Charset. Một archive cũ có encoding khác có thể tạo ra tên không như dự đoán. Không tự hợp thức hóa tên giải mã sai; phải xác định format/charset đầu vào và áp validation **sau khi giải mã đúng**, rồi kiểm tra target trong filesystem đích.

## 18. Những lỗi thường gặp khi extract

| Tình huống | Kết quả hoặc exception | Hướng xử lý |
| --- | --- | --- |
| `../escape.txt` | Validator từ chối | Abort archive |
| Tên absolute hoặc drive | Validator từ chối | Không resolve trực tiếp |
| Backslash/colon bị cấm | Validator từ chối theo portable policy | Không “sửa” im lặng |
| File trùng tên | `FileAlreadyExistsException` | Không overwrite |
| Parent symlink | Metadata NOFOLLOW báo isSymbolicLink | Abort, kiểm tra quyền root |
| Parent không phải directory | `NotDirectoryException`/IOException | Abort |
| ZIP hỏng | `ZipException`/IOException | Không publish partial |
| Vượt entry/byte limit | Exception do app phát sinh | Stop stream, cleanup |
| Thiếu quyền | `AccessDeniedException`/IOException | Báo lỗi quyền, không suy là missing |
| Provider không hỗ trợ option | `UnsupportedOperationException` | Không silently hạ cấp bảo vệ |
| ZIPFS không có trong runtime | `ProviderNotFoundException` | Kiểm tra module |
| ZIPFS đã đóng | `ClosedFileSystemException` | Giữ resource mở trong scope |
| Invalid host Path | `InvalidPathException` | Từ chối tên |
| Root bị thay trong lúc ghi | Race/TOCTOU | Cần protected root hoặc directory handles |

### 18.1. Không dựa duy nhất vào `Files.exists`

`Files.exists` có thể trả false vì không có file **hoặc không xác định được trạng thái**, và kết quả lập tức có thể cũ. Kiểm tra `exists` trước `newOutputStream` không thay thế `CREATE_NEW`. Với input không tin cậy, nên coi errors và uncertainty là lý do không publish staging.

### 18.2. Cleanup phải bảo toàn lỗi gốc

Nếu ghi entry thất bại rồi việc xóa file tạm cũng thất bại, dịch vụ cần ghi lại nguyên nhân và cleanup error. Không biến lỗi partial thành success. Nếu một file đã tồn tại trước khi CREATE_NEW được gọi, **đừng xóa nó chỉ vì open failed**.

## 19. Checklist code review

1. Entry name có được xem là dữ liệu chưa tin cậy?
2. Root có được tạo riêng cho một job và bảo vệ quyền?
3. Tất cả entry names được validate trước khi mở output?
4. Có cấm absolute/drive/UNC, `..` và separator ambiguity?
5. Có quy tắc với `.`, empty segments, trailing slash và directory entries?
6. Có cấm Windows reserved names và tên có colon?
7. Có dùng `Path.startsWith(Path)` thay cho String prefix?
8. Có kiểm tra target không bằng chính root?
9. Có tạo output Path trong **host filesystem**?
10. Có đọc root và parent attrs bằng NOFOLLOW?
11. Có từ chối symlink parents?
12. Attacker có quyền sửa staging/root đồng thời không?
13. Nếu cần tránh race, provider có SecureDirectoryStream không?
14. Có dùng CREATE_NEW để chặn overwrite?
15. Khi CREATE_NEW thất bại, có tránh xóa file chưa sở hữu?
16. Khi ghi một file mới dở, có xóa partial đúng tên?
17. Có giới hạn số entry, bytes/file, bytes/job và depth?
18. Có abort stream khi vượt quota với ZIP không tin cậy?
19. Có kiểm soát memory/CPU/time không?
20. Có kiểm tra duplicate/case-insensitive/unicode collisions?
21. Có từ chối hoặc xử lý special entries theo policy?
22. Có xử lý ZipException và I/O ở tất cả các bước?
23. Có dọn staging nếu một entry ở cuối ZIP bị reject?
24. Có chỉ publish sau khi mọi entry và business checks thành công?
25. Có kiểm thử trên Windows/Linux và providers thực tế?
26. Có ghi rõ các nhánh symlink bị SKIPPED khi thiếu quyền?
27. Có dùng API hiện hành, không dựa trên những thủ thuật File/Path legacy?
28. Có tránh hiển thị full path nhạy cảm trong error message gửi client?

## 20. Câu hỏi ôn tập và đáp án

**Câu 1.** Zip Slip xảy ra khi nào? — Khi extractor cho phép tên entry khiến output nằm ngoài vùng đích cho phép.

**Câu 2.** Vì sao `String.startsWith(root)` không đủ? — Nó so prefix ký tự, không bảo đảm directory boundary; `extract-other` có cùng prefix với `extract`.

**Câu 3.** `Path.normalize()` có xác minh symlink không? — Không; chỉ xử lý tên lexical.

**Câu 4.** Tại sao phải chặn absolute path trước `resolve`? — `resolve` có thể trả absolute argument, bỏ qua base.

**Câu 5.** Vì sao cấm `..` dù target sau normalize còn dưới root? — Để giảm ambiguity/rủi ro và có strict policy dễ kiểm toán.

**Câu 6.** Vì sao cấm `\` trong entry name? — Nó có semantics separator trên Windows và ký tự tên trên Unix.

**Câu 7.** `.hidden.txt` khác `.` ở đâu? — Dotfile là tên thông thường; `.` biểu diễn thư mục hiện tại.

**Câu 8.** `CREATE_NEW` giải quyết rủi ro nào? — Tránh tạo/ghi đè một file tại tên đã tồn tại bằng operation tạo mới.

**Câu 9.** `NOFOLLOW_LINKS` ở file cuối có ngăn mọi parent symlink? — Không.

**Câu 10.** `Files.createDirectories(parent)` có chứng minh parent không phải symlink? — Không, cần metadata không follow và quyền phù hợp.

**Câu 11.** `toRealPath()` có loại bỏ TOCTOU? — Không, vì path có thể đổi sau check.

**Câu 12.** `SecureDirectoryStream` có trên mọi provider? — Không.

**Câu 13.** Vì sao cần staging? — Để cách ly partial extraction và chỉ publish sau thành công.

**Câu 14.** Vượt bytes limit nên làm gì? — Abort ZIP input và dọn staging, không tiếp tục bỏ qua entry lớn.

**Câu 15.** `ZipEntry.getSize()` có thể trả gì khi chưa biết kích thước? — `-1`.

**Câu 16.** ZIPFS Path là host Path không? — Không, nó nằm trong ZIP FileSystem namespace.

**Câu 17.** Một ZIP có hai entry giống nhau có nên tự overwrite? — Không, phải có explicit collision policy.

**Câu 18.** Compile PASS nhưng symbolic link test in SKIPPED có chứng minh nhánh symlink thật? — Không.

**Câu 19.** Nếu archive có một entry độc hại sau 50 entries hợp lệ thì sao? — Từ chối archive, không publish staging chưa hoàn chỉnh.

**Câu 20.** Vì sao phải giới hạn tổng bytes ngoài per-entry bytes? — Nhiều entries nhỏ vẫn có thể tiêu thụ tổng tài nguyên lớn.

## 21. Bài tập thực hành

### Bài A — Bảng tên path độc hại

Thêm các tên `../../outside`, `C:/temp/x`, `//server/share`, `a/../b` và `AUX.txt` vào `ZipEntryPathPolicyDemo`; dự đoán và xác minh kết quả.

### Bài B — Kiểm tra prefix sibling

Giả sử root là `/tmp/extract`, candidate là `/tmp/extract-backup/item`. So sánh `String.startsWith` với `Path.startsWith(Path)`.

### Bài C — Hai entries trùng đích

Tạo ZIP có hai entries cùng tên bằng công cụ thích hợp, thử extractor với `CREATE_NEW`. Xác minh không overwrite tên đã có.

### Bài D — Parent symlink

Chạy `SymlinkParentGuardDemo` trên môi trường có quyền tạo symlink; đối chiếu lexicalInside và realParentInside. Nếu SKIPPED, ghi rõ chưa test nhánh thật.

### Bài E — Vượt ngân sách dữ liệu

Tăng fixture trong `ZipStreamBudgetDemo`, kiểm tra bytes limit và giải thích vì sao production phải abort thay vì tiếp tục `closeEntry`.

### Bài F — Archive có entry độc hại ở cuối

Chạy `ZipSlipSafeExtractionDemo`. Thay `../escape.txt` bằng `good/../../outside.txt`, bảo đảm archive bị reject và không publish bad-stage.

### Bài G — ZIPFS sang host

Chạy `ZipFsCopyContainmentDemo` và in schemes của hai Path. Lý giải vì sao output path phải được tạo từ host root sau validation.

### Bài H — Mô hình concurrency

Giả sử attacker có quyền thay directory cha sau khi extractor kiểm tra. Viết threat model và đề xuất ACL/ownership hoặc SecureDirectoryStream thay vì chỉ normalize.

### Bài I — Case-insensitive collisions

Trên filesystem phù hợp, thử entries `readme.txt` và `README.txt`. Dùng CREATE_NEW và log kết quả mà không ghi đè.

### Bài J — Thiết kế kết quả có trạng thái

Tạo một `enum ExtractionStatus` với COMPLETE, INVALID_PATH, IO_FAILED, LIMIT_EXCEEDED, COLLISION. Chỉ phát download link hoặc publish khi COMPLETE.

## 22. Tài liệu Java chính thức

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`, `toRealPath`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `newOutputStream`, `readAttributes`, `createDirectory`, `createTempDirectory`, `copy`, `walk`.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW` và `WRITE`.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): operations tương đối với open directory, hỗ trợ giảm race khi provider cho phép.
- [Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `isDirectory` và `isSymbolicLink`.
- [Java SE 17 — ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html): tên entry, directory metadata, kích thước có thể unknown.
- [Java SE 17 — ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html): `getNextEntry`, `read`, `closeEntry`.
- [Java SE 17 — ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html): đọc ZIP entries qua archive file.
- [JDK 17 — jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP FileSystem provider.

**Kết luận:** Đừng bao giờ tin trực tiếp `ZipEntry.getName()`. Hãy áp một policy tên relative rõ ràng, từ chối absolute/`..`/tên không portable, tạo Path trong vùng đích và kiểm tra theo `Path.startsWith`, bảo vệ parent directories/symlinks và root ownership, dùng `CREATE_NEW` để tránh ghi đè, đặt hạn mức streaming và cô lập bằng staging. Với adversary có thể sửa thư mục đồng thời, lexical checks không đủ; phải dùng quyền filesystem/handle-based operations hoặc từ chối khi không có capability. Chỉ công bố kết quả sau khi archive được giải nén đầy đủ và kiểm chứng thành công.
