# Giới hạn đường dẫn và tài nguyên khi giải nén ZIP trong Java

## 1. Vấn đề cần giải quyết

Giải nén ZIP có vẻ chỉ gồm đọc một `ZipEntry` rồi ghi dữ liệu ra thư mục. Nhưng archive do bên ngoài cung cấp có thể chứa **tên đường dẫn cố tình vượt thư mục đích** (*Zip Slip*), tệp nén nhỏ nhưng giải nén thành lượng dữ liệu khổng lồ (*ZIP bomb*), hàng chục nghìn entry, đường dẫn lồng quá sâu hoặc dữ liệu hỏng giữa chừng. Nếu chỉ dùng `Files.copy(...)` mà không kiểm tra, ứng dụng có thể ghi đè tệp ngoài phạm vi, làm đầy ổ đĩa, cạn RAM hoặc để lại kết quả chưa hoàn chỉnh.

Mục tiêu là xây dựng một quy trình **giải nén trong ranh giới cho phép**: mỗi entry chỉ được ghi bên trong nơi đã chọn; lượng dữ liệu, số tệp và thời gian xử lý phải có hạn mức; khi có lỗi, kết quả dở dang được dọn và không được công bố như thành công.

Bài tập trung vào API **hiện vẫn được hỗ trợ** trong Java 17+ (`java.util.zip.ZipInputStream`, `ZipEntry`, `java.nio.file.Path`, `Files` và try-with-resources). Các kỹ thuật và giới hạn dưới đây vẫn áp dụng khi dùng `ZipFile`, hoặc thư viện bên thứ ba. Đây là bài về **kiểm soát đường dẫn và tài nguyên khi giải nén**, không phải hướng dẫn tạo ZIP hay giới thiệu mọi API ZIP.

## 2. Mô hình đe dọa: đầu vào nào không đáng tin?

Một entry ZIP có ít nhất tên và dữ liệu. Ví dụ tên hợp lệ là `docs/guide.txt`; tên nguy hiểm có thể là:

- `../secret.txt` hoặc `folder/../../secret.txt`: thành phần `..` khiến đường dẫn thoát khỏi thư mục đích.
- `/etc/config` hoặc đường dẫn tuyệt đối tương ứng trên hệ điều hành: bỏ qua vị trí đích khi ghép đường dẫn không cẩn thận.
- `C:\temp\file.txt`, `..\outside.txt`: biến thể có dấu `\`, ký tự ổ đĩa hoặc cú pháp riêng của Windows.
- `a/b/c/...` với rất nhiều cấp: tạo cây thư mục quá sâu, gây lỗi hệ tệp hoặc tốn tài nguyên.
- Nhiều entry trùng tên hoặc xung đột giữa tên tệp và tên thư mục: có thể ghi đè hoặc làm quá trình dừng giữa chừng.
- Một entry có kích thước sau giải nén cực lớn, nhiều entry rất nhỏ, hoặc ZIP lồng ZIP: có thể làm cạn CPU, dung lượng đĩa, bộ nhớ, số inode hoặc thời gian xử lý.

**Không bao giờ tin `entry.getName()` là đường dẫn an toàn.** Tên entry đến từ archive, không phải do hệ điều hành tạo ra cho thư mục đích. Các thuộc tính `getSize()`, `getCompressedSize()` cũng không phải hệ thống thực thi hạn mức: chúng có thể là `-1`, thiếu tại thời điểm đọc hoặc không đáng tin để ra quyết định bảo mật.

Cùng một tệp có phần mở rộng `.zip` không chứng minh nội dung đúng định dạng, đáng tin hay đã được quét. Cần xử lý `IOException`/`ZipException`, kiểm tra nội dung nghiệp vụ sau khi giải nén và chỉ đưa dữ liệu đã được xử lý thành công vào hệ thống.

## 3. Giới hạn đường dẫn: chống Zip Slip

### 3.1. Lỗi cốt lõi

Ví dụ cách ghép đường dẫn nguy hiểm (chỉ để nhận diện lỗi; **không dùng để xử lý ZIP không tin cậy**):

```java
Path output = destination.resolve(entry.getName());
Files.copy(zipInputStream, output);
```

Với entry `../../outside.txt`, đường dẫn kết quả có thể nằm ngoài `destination`. Nếu ứng dụng có quyền ghi mạnh, lỗi có thể ảnh hưởng tới tệp cấu hình hoặc dữ liệu khác. Kẻ tấn công không cần điều khiển tên ZIP trên đĩa; họ chỉ cần điều khiển **tên entry bên trong**.

### 3.2. Kiểm tra đúng bằng `Path`

Với một thư mục đích `root` đã tin cậy, các bước tối thiểu là:

1. Đọc và kiểm tra tên entry; với định dạng đầu vào đa nền tảng, nên từ chối đường dẫn tuyệt đối, ký tự NUL, dấu `\`, dấu `:` và thành phần `.`/`..`. Đây là **chính sách bảo thủ có chủ ý**; không phải mọi tên ZIP bị từ chối đều là tấn công.
2. Chuyển tên hợp lệ thành một `Path` **tương đối**, đặt giới hạn độ dài tên và độ sâu thư mục.
3. Tính `target = root.resolve(relative).normalize()`.
4. Chỉ cho phép tiếp tục nếu `target.startsWith(root)`. Phương thức `Path.startsWith` so sánh **thành phần đường dẫn**, khác với `String.startsWith` dễ nhầm `/data/safe` và `/data/safe-backup`.
5. **Kiểm tra trước khi tạo** thư mục hoặc file. Dùng `CREATE_NEW` cho tệp để tránh âm thầm ghi đè entry trùng tên.
6. Tạo tệp trong **thư mục staging mới và riêng biệt**, không cho tiến trình/người dùng không tin cậy chèn symbolic link hoặc thay cấu trúc giữa lúc kiểm tra và lúc mở tệp.

Không chỉ kiểm tra chuỗi tên rồi coi là đủ: `normalize()` chỉ xử lý đường dẫn **theo cú pháp**; nó không tự bảo vệ khỏi symbolic link đã có trong các thư mục cha hay cuộc đua thay đổi hệ tệp (*TOCTOU*). Nếu giải nén trực tiếp vào thư mục dùng chung, một symlink có thể hướng một đường dẫn bên trong root sang vị trí ngoài root dù `startsWith` trả về true.

Cách dễ kiểm soát hơn là một **staging directory mới trong parent đáng tin, với quyền truy cập hạn chế**, và không tạo symlink/hardlink từ nội dung ZIP. Khi môi trường có đối thủ có thể thay đổi cùng cây thư mục trong lúc giải nén, cần cách mở tệp an toàn theo thư mục như `SecureDirectoryStream` khi nhà cung cấp filesystem hỗ trợ, hoặc cơ chế cách ly hệ thống tương đương; riêng kiểm tra chuỗi `Path` không đủ chống race.

### 3.3. Những tên cần chính sách riêng

- **Dấu phân cách:** tên ZIP thông dụng dùng `/`. Để tránh hai cách hiểu giữa Linux/Windows, ví dụ ở phần 6 từ chối dấu `\` và `:`, kể cả khi trên một nền tảng chúng được xem là ký tự thường.
- **Absolute path và traversal:** kiểm tra cả khi chỉ xử lý trên một hệ điều hành; không chờ lỗi tạo file tự chặn.
- **Tên trùng, phân biệt hoa/thường, Unicode và ký tự bị giới hạn bởi filesystem:** tùy hệ điều hành, hai tên khác nhau có thể trỏ đến cùng một tệp. Chính sách `CREATE_NEW` hoặc phát hiện trùng trước khi công bố giúp tránh overwrite ngoài ý muốn.
- **Tệp thực thi, extension và tên đặc biệt:** nếu nghiệp vụ chỉ chấp nhận CSV/JSON, có thể đặt allowlist sau khi qua các kiểm tra đường dẫn; đừng mặc định cho chạy file được trích xuất.
- **Symlink và metadata ngoài:** `ZipInputStream` đọc phần header cục bộ; nó không cung cấp mọi metadata trong central directory, trong đó có external file attributes. Ví dụ an toàn dưới đây chỉ tạo thư mục và **regular file**, không phục dựng symlink, permission hoặc executable bit từ ZIP. Với thư viện tự khôi phục symlink/hardlink phải có chính sách kiểm tra riêng.

## 4. Giới hạn tài nguyên: chống ZIP bomb và lỗi từ chối dịch vụ

Một file ZIP đầu vào có dung lượng nhỏ không có nghĩa tổng dữ liệu sau giải nén nhỏ. Thuật toán nén có thể nén rất tốt dữ liệu lặp, và archive có thể chứa nhiều entry. Đếm lượng byte **thực sự đã giải nén** ngay trong vòng lặp `read(...)` và **kiểm tra hạn mức trước khi `write(...)`**.

Các giới hạn độc lập đáng cân nhắc:

| Ranh giới | Cần hạn chế điều gì? | Điểm đo phù hợp |
| --- | --- | --- |
| Dung lượng đầu vào | Tệp ZIP tải lên quá lớn | Ngay khi upload/ghi file tạm; `Files.size` hữu ích khi đã có tệp snapshot ổn định |
| Số lượng entry | Rất nhiều entry rỗng/nhỏ làm tốn inode, CPU | Tăng bộ đếm sau mỗi `getNextEntry()` |
| Kích thước một entry | Một tệp giải nén quá lớn | Cộng `n` mỗi lần đọc byte trong entry |
| Tổng kích thước giải nén | Nhiều entry hợp lệ riêng lẻ nhưng tổng quá lớn | Cộng `n` trên **mọi** entry |
| Độ dài tên và độ sâu | Đường dẫn gây lỗi hoặc cây thư mục quá sâu | Kiểm tra trước khi tạo file/dir |
| Thời gian/CPU | Giải nén kéo dài bất thường | Deadline, cancellation, I/O timeout, CPU quota ở tầng thực thi |
| Số ZIP xử lý đồng thời | Nhiều archive nhỏ làm cạn tài nguyên tổng | Worker pool, queue và quota theo người dùng/tenant |
| ZIP lồng nhau | Vượt giới hạn qua việc giải nén lặp | Cấm tự động đệ quy hoặc dùng một bộ quota chung cho toàn bộ cây |

**Quan trọng:** không dựa duy nhất vào `ZipEntry.getSize()` hay tỉ lệ nén. `ZipInputStream` đọc local header và kích thước có thể chưa biết khi `getNextEntry()` trả về; metadata còn có thể không phản ánh lượng byte sẽ đi qua ứng dụng. Tỉ lệ nén lớn có thể hợp lệ với dữ liệu lặp; giới hạn **byte giải nén thực tế**, số entry và thời gian mới là chốt bảo vệ cốt lõi.

Dùng buffer cố định (ví dụ `byte[8192]`), không gọi `readAllBytes()` cho đầu vào không giới hạn; `transferTo(...)` và `Files.copy(...)` cũng không tự cung cấp quota byte giải nén. Nếu tính tổng bằng số nguyên, dùng `long` và kiểm tra trước phép cộng để tránh overflow. Giới hạn theo luồng không thay thế disk quota/CPU quota/cancellation bên ngoài khi có nhiều phiên đồng thời.

**Thời gian:** kiểm tra `System.nanoTime()` ở mỗi vòng đọc là cơ chế *best effort*: nó không dừng được một I/O call đang chặn vô thời hạn. Khi nhận dữ liệu trực tiếp từ mạng, cần request size limit, socket/read timeout và hủy tác vụ ở tầng server. Khi giải nén file đã lưu ổn định, deadline vẫn hữu ích nhưng không phải bảo đảm giới hạn CPU tuyệt đối.

## 5. Quy trình giải nén có thể công bố an toàn

Một quy trình thực tế phù hợp với file người dùng upload:

1. **Nhận đầu vào có hạn mức**: xác thực quyền, giới hạn HTTP request size, lưu vào tệp tạm do ứng dụng kiểm soát. Không để bên ngoài sửa tệp trong lúc kiểm tra và giải nén.
2. **Tạo staging riêng** bên trong parent được kiểm soát quyền. Chưa ghi thẳng vào thư mục dữ liệu chính hoặc ghi đè file đang dùng.
3. **Duyệt ZIP có kiểm soát**: kiểm tra đường dẫn của **từng entry**; giới hạn số entry, kích thước từng entry, tổng byte giải nén, độ sâu và deadline. Dùng `CREATE_NEW` cho file mới.
4. **Xử lý lỗi theo nguyên tắc fail closed**: dừng ngay khi vượt quota, phát hiện tên bất hợp lệ hoặc ZIP hỏng; đóng luồng, xóa staging và ghi log ngắn gọn, không công bố đầu ra dở dang.
5. **Kiểm tra nội dung nghiệp vụ**: loại file cho phép, schema, checksum/chữ ký từ nguồn đáng tin nếu sản phẩm yêu cầu, quét mã độc khi phù hợp. Một archive giải nén thành công chưa mặc nhiên được tin cậy.
6. **Công bố sau kiểm định**: chuyển dữ liệu đã xác minh sang đích cuối qua cơ chế phù hợp, tránh overwrite không chủ ý; xử lý rollback và hạn mức dung lượng. Nếu cần tính nguyên tử khi đổi tên, phải đáp ứng điều kiện filesystem/destination cho phép atomic move; không giả định mọi lần `move` đều atomic.

ZIP parser **không** là sandbox hệ điều hành. Sử dụng user/process ít đặc quyền, quota đĩa, giới hạn worker, vùng tạm riêng và giám sát mới tạo thành bảo vệ nhiều lớp. Không giải nén đệ quy ZIP bên trong ZIP nếu chưa có yêu cầu và bộ quota toàn cục.

## 6. Java 17+: chương trình chạy được với các giới hạn cụ thể

Ví dụ sau tạo ba archive tự kiểm tra: một ZIP hợp lệ, một entry cố thoát khỏi thư mục đích và một entry vượt ngưỡng byte sau giải nén. Giải nén được thực hiện trong staging mới, chỉ tạo regular file/thư mục, giới hạn từng entry và tổng byte, dọn kết quả khi lỗi.

**Các hạn mức ví dụ**: ZIP trên đĩa ≤5 MiB; tối đa 256 entry; ≤1 MiB/entry; ≤4 MiB byte đã giải nén/ZIP; tối đa 16 cấp thư mục; tên entry ≤240 ký tự UTF-16; deadline kiểm tra 20 giây. Đây là con số phục vụ học tập, phải điều chỉnh theo nhu cầu và rủi ro của hệ thống thực.

Lưu chính xác thành **`SafeZipDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public final class SafeZipDemo {
    private static final long MAX_ARCHIVE = 5L * 1024 * 1024;
    private static final long MAX_ENTRY = 1L * 1024 * 1024;
    private static final long MAX_TOTAL = 4L * 1024 * 1024;
    private static final int MAX_ENTRIES = 256;
    private static final int MAX_DEPTH = 16;
    private static final long MAX_TIME_NANOS = 20_000_000_000L;

    public static Path extract(Path archive, Path trustedParent) throws IOException {
        if (Files.size(archive) > MAX_ARCHIVE) {
            throw new IOException("ZIP input exceeds limit");
        }
        if (!Files.isDirectory(trustedParent, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Trusted parent must be a real directory");
        }

        Path stage = Files.createTempDirectory(trustedParent, "unzipped-");
        try {
            int entries = 0;
            long total = 0;
            long started = System.nanoTime();
            try (ZipInputStream zip = new ZipInputStream(
                    Files.newInputStream(archive), StandardCharsets.UTF_8)) {
                ZipEntry entry;
                byte[] buffer = new byte[8192];
                while ((entry = zip.getNextEntry()) != null) {
                    if (++entries > MAX_ENTRIES) {
                        throw new IOException("Too many ZIP entries");
                    }
                    checkDeadline(started);
                    Path target = checkedTarget(stage, entry.getName());
                    if (entry.isDirectory()) {
                        // Reject a directory entry that unexpectedly contains payload.
                        if (zip.read(buffer) != -1) {
                            throw new IOException("Directory entry contains data");
                        }
                        Files.createDirectories(target);
                    } else {
                        Files.createDirectories(target.getParent());
                        long entryBytes = 0;
                        try (OutputStream out = Files.newOutputStream(target,
                                StandardOpenOption.CREATE_NEW,
                                StandardOpenOption.WRITE)) {
                            int n;
                            while ((n = zip.read(buffer)) != -1) {
                                checkDeadline(started);
                                if (entryBytes > MAX_ENTRY - n || total > MAX_TOTAL - n) {
                                    throw new IOException("Uncompressed data exceeds limit");
                                }
                                out.write(buffer, 0, n);
                                entryBytes += n;
                                total += n;
                            }
                        }
                    }
                    zip.closeEntry();
                }
            }
            return stage;
        } catch (IOException | RuntimeException failure) {
            try {
                deleteTree(stage);
            } catch (IOException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }

    private static void checkDeadline(long started) throws IOException {
        if (System.nanoTime() - started > MAX_TIME_NANOS) {
            throw new IOException("ZIP processing deadline exceeded");
        }
    }

    private static Path checkedTarget(Path root, String name) throws IOException {
        if (name.isBlank() || name.length() > 240 || name.startsWith("/")
                || name.indexOf('\\') >= 0 || name.indexOf(':') >= 0
                || name.indexOf('\0') >= 0) {
            throw new IOException("Unsafe ZIP entry name: " + name);
        }
        String[] segments = name.split("/", -1);
        int depth = 0;
        for (int i = 0; i < segments.length; i++) {
            String part = segments[i];
            if (part.isEmpty() && i == segments.length - 1) {
                continue;
            }
            if (part.isEmpty() || part.equals(".") || part.equals("..")) {
                throw new IOException("Unsafe ZIP path segment: " + name);
            }
            depth++;
        }
        if (depth == 0 || depth > MAX_DEPTH) {
            throw new IOException("ZIP path depth exceeds limit");
        }
        try {
            Path relative = Path.of(name).normalize();
            Path target = root.resolve(relative).normalize();
            if (relative.isAbsolute() || !target.startsWith(root)) {
                throw new IOException("ZIP path escapes destination");
            }
            return target;
        } catch (InvalidPathException failure) {
            throw new IOException("Invalid ZIP entry path", failure);
        }
    }

    private static void deleteTree(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            List<Path> deletionOrder = paths.sorted(Comparator.reverseOrder()).toList();
            for (Path path : deletionOrder) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("zip-limits-demo-");
        try {
            Path good = work.resolve("good.zip");
            try (ZipOutputStream zip = new ZipOutputStream(
                    Files.newOutputStream(good), StandardCharsets.UTF_8)) {
                zip.putNextEntry(new ZipEntry("docs/"));
                zip.closeEntry();
                zip.putNextEntry(new ZipEntry("docs/hello.txt"));
                zip.write("Hello ZIP".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
            Path result = extract(good, work);
            System.out.println("Valid: " + Files.readString(result.resolve("docs/hello.txt")));

            Path traversal = work.resolve("traversal.zip");
            try (ZipOutputStream zip = new ZipOutputStream(
                    Files.newOutputStream(traversal), StandardCharsets.UTF_8)) {
                zip.putNextEntry(new ZipEntry("../escape.txt"));
                zip.write("blocked".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
            try {
                extract(traversal, work);
                System.out.println("Traversal: NOT BLOCKED");
            } catch (IOException expected) {
                System.out.println("Traversal: blocked");
            }

            Path expansion = work.resolve("expansion.zip");
            try (ZipOutputStream zip = new ZipOutputStream(
                    Files.newOutputStream(expansion), StandardCharsets.UTF_8)) {
                zip.putNextEntry(new ZipEntry("large.bin"));
                byte[] zeros = new byte[8192];
                for (int i = 0; i < 129; i++) {
                    zip.write(zeros);
                }
                zip.closeEntry();
            }
            try {
                extract(expansion, work);
                System.out.println("Expansion: NOT BLOCKED");
            } catch (IOException expected) {
                System.out.println("Expansion: blocked");
            }
        } finally {
            deleteTree(work);
        }
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 SafeZipDemo.java
java SafeZipDemo
```

Stdout dự kiến, không phụ thuộc đường dẫn thư mục tạm:

```text
Valid: Hello ZIP
Traversal: blocked
Expansion: blocked
```

Chương trình đã được biên dịch và chạy với **JDK 21**, tương thích cú pháp Java 17+. Kịch bản thứ ba ghi 129 khối, mỗi khối 8.192 byte (1.056.768 byte sau giải nén), vượt ngưỡng 1 MiB/entry dù dữ liệu nén bằng số 0 rất nhỏ. Kịch bản traversal bị chặn **trước khi tạo file đầu ra**. Khi có ngoại lệ, chương trình cố xóa staging; nếu dọn không thành công, lỗi dọn được gắn dưới dạng `suppressed exception` để caller vẫn biết lỗi gốc.

### 6.1. Giải thích các quyết định trong mã

- `Files.size(archive)` kiểm tra kích thước tệp **đầu vào đã lưu trên đĩa**. Điều kiện tiên quyết là archive được lưu trong vùng chỉ ứng dụng kiểm soát và **không thể bị sửa đồng thời**; với HTTP upload, phải giới hạn byte ngay khi nhận dữ liệu thay vì chỉ tin kết quả `Files.size` sau đó.
- `Files.createTempDirectory(trustedParent, ...)` tạo một thư mục staging mới. `trustedParent` phải là thư mục thật, đủ riêng tư và có quyền truy cập phù hợp. Đoạn mã không phải giải pháp độc lập cho filesystem nơi kẻ tấn công có quyền thay đổi các thư mục cha.
- `checkedTarget` áp đặt chính sách tên, chặn `.`/`..`, kiểm tra độ sâu, `normalize()` và `startsWith(root)`. Đây là hai lớp bổ trợ: tên bị nghi ngờ bị từ chối sớm, đường dẫn kết quả được kiểm tra lại trước khi tạo.
- Với entry tệp, `CREATE_NEW` từ chối ghi đè file đã tồn tại, kể cả trường hợp hai entry có cùng tên. Với thư mục, `createDirectories` cho phép thư mục đã tạo trước đó.
- Một entry được đánh dấu thư mục nhưng bất ngờ chứa byte được **từ chối**; không gọi `closeEntry()` để bỏ qua dữ liệu của thư mục chưa kiểm tra, vì thao tác đó có thể giải nén dữ liệu mà không qua các bộ đếm.
- Với entry tệp, byte nhận từ `zip.read(buffer)` được đếm và so với cả hạn mức mỗi entry và tổng. Câu điều kiện `entryBytes > MAX_ENTRY - n` tránh overflow khi cộng; số byte bị vượt mức sẽ không được ghi ra.
- Nếu đọc đến hết entry, `closeEntry()` chuyển sang entry kế tiếp. `try-with-resources` bảo đảm đóng luồng ngay cả khi lỗi. Một archive bị lỗi checksum hoặc cấu trúc có thể ném `ZipException`/`IOException` và bị từ chối.
- `deleteTree(...)` dùng `Files.walk` mặc định **không đi theo symbolic link**, sắp xếp xóa file trước thư mục. Ví dụ main xóa toàn bộ vùng thử nghiệm, còn `extract` xóa staging khi thất bại.

**Giới hạn của ví dụ:** các giá trị là cấu hình cố định để học tập; đây không phải dịch vụ upload hoàn chỉnh. Hệ thống thực cần giới hạn request body, quota lưu trữ, cấp quyền thư mục, giới hạn concurrency, xử lý cancellation, logging và cơ chế công bố dữ liệu đã kiểm định. Deadline kiểm tra trong mã là *best effort*. Ví dụ cũng không xác minh chữ ký số, mã độc hay tính phù hợp nghiệp vụ của từng tệp.

## 7. Khi dùng `ZipFile` thay `ZipInputStream`

Nếu đầu vào đã là một ZIP ổn định trên đĩa và cần tra cứu entry theo tên, `ZipFile` có thể thuận tiện hơn. Nó đọc thông tin danh mục ZIP và cung cấp `getEntry(name)`, `entries()`, `getInputStream(entry)`. Tuy nhiên **`ZipFile` không tự chống Zip Slip hoặc ZIP bomb**: mọi entry sắp ghi ra đĩa vẫn cần `checkedTarget`, quota byte thực đọc, quota số entry, staging riêng và xử lý lỗi.

Với `ZipInputStream`, ta thường chỉ biết metadata từ local header tại thời điểm đang đọc entry. Trường `getSize()` có thể bằng `-1`; không được giả định đủ thông tin ở đầu vòng lặp. Với `ZipFile`, metadata danh mục có thể giúp từ chối sớm, nhưng không thay thế việc đếm byte đã giải nén thực tế. Không dùng việc mở ZIP thành công như một phép xác minh chữ ký, nguồn gốc hoặc an toàn nội dung.

## 8. Tình huống lỗi và checklist kiểm thử

| Tình huống kiểm thử | Hành vi cần có |
| --- | --- |
| `../outside.txt`, `a/../../b.txt`, đường dẫn tuyệt đối | Từ chối trước khi ghi file |
| `..\outside.txt`, `C:\temp\x.txt` | Không được ghi theo cách diễn giải đường dẫn của Windows hoặc host |
| Entry trùng tên tệp, trùng theo quy tắc filesystem | Từ chối overwrite hoặc xử lý trùng theo chính sách rõ ràng |
| Thư mục con là symlink trỏ ra ngoài | Không theo link; trong ví dụ chỉ thao tác ở staging riêng đáng tin |
| Một entry nở quá hạn mức | Dừng, xóa tệp/chunk dở và staging |
| Nhiều entry vượt tổng byte hoặc số lượng | Dừng, không công bố dữ liệu |
| Entry thư mục có dữ liệu bất thường | Từ chối, không bỏ qua luồng dữ liệu chưa giới hạn |
| ZIP hỏng, sai CRC, exception khi đang đọc | Dừng, đóng tài nguyên, xóa staging |
| Ảnh hưởng từ ZIP lồng nhau | Không tự động giải nén đệ quy; nếu cần, chia quota chung |
| Hết dung lượng, lỗi quyền, deadline, client ngắt | Không coi giải nén là thành công, cleanup và log |
| Hai request chạy đồng thời | Có staging riêng và quota toàn cục/concurrency |
| Tệp nén có nội dung JavaScript, executable hoặc file cấu hình | Kiểm tra allowlist, loại nội dung và quyền sử dụng sau giải nén |

Đặc biệt nên kiểm thử trên **Linux và Windows** nếu sản phẩm chạy đa nền tảng: tên tệp, phân biệt hoa/thường, ký tự bị cấm, symbolic link và đường dẫn tuyệt đối có thể khác. Nếu người dùng được phép tự do đặt tên file, hãy thiết kế chính sách đổi tên/từ chối rõ ràng; không âm thầm biến hai tên khác nhau thành cùng một đường dẫn.

## 9. Những lỗi triển khai phổ biến

1. **Chỉ gọi `normalize()` rồi ghi:** còn phải chặn traversal, xác nhận nằm trong root, xử lý symlink và race.
2. **Dùng `String.startsWith` với đường dẫn:** phải dùng `Path.startsWith` để so sánh theo thành phần thư mục.
3. **Tin metadata kích thước:** hạn mức phải dựa trên byte giải nén thực đọc; `getSize()` có thể `-1` và không đáng tin.
4. **Chỉ giới hạn từng entry:** nhiều tệp nhỏ có thể vượt tổng byte hoặc hết inode; cần quota toàn cục và số entry.
5. **Gọi `readAllBytes()`/`transferTo()` cho ZIP lạ:** có thể cấp phát hoặc ghi dữ liệu không giới hạn.
6. **Dùng `closeEntry()` để bỏ qua payload chưa đo:** có thể tiêu tốn tài nguyên giải nén ngoài bộ đếm; kiểm soát cả đường bỏ qua.
7. **Giải nén trực tiếp vào thư mục đích cuối:** khi thất bại dễ còn file dở dang, hỏng dữ liệu hoặc ghi đè.
8. **Cho thư mục staging bị người khác chỉnh sửa:** đường dẫn an toàn về mặt cú pháp vẫn có thể bị chuyển hướng qua symlink/TOCTOU.
9. **Coi timeout vòng lặp là timeout cứng:** thao tác I/O bị chặn vẫn cần cơ chế tầng ứng dụng, hủy tác vụ và hạn mức hạ tầng.
10. **Giải nén đệ quy không có ngân sách tổng:** ZIP lồng nhau có thể vượt quota của từng archive đơn lẻ.

## 10. Tài liệu chính thức và đọc thêm

- [Java SE — `ZipInputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/ZipInputStream.html): `getNextEntry`, `read`, `closeEntry` và metadata local header.
- [Java SE — `ZipFile`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/ZipFile.html): tra cứu entry theo tên và đọc từ ZIP trên đĩa.
- [Java SE — `Path`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`.
- [Java SE — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): tạo thư mục tạm, mở stream, tạo file mới, thao tác với filesystem.
- [OWASP Web Security Testing Guide — Upload of Malicious Files](https://owasp.org/www-project-web-security-testing-guide/): tìm hiểu rủi ro upload archive, symlink, ZIP bomb và kiểm thử.

**Ghi nhớ:** kiểm tra **tên entry trước khi tạo**, giải nén trong **staging riêng đáng tin**, áp đặt **quota thực đọc** cho từng entry và toàn archive, rồi **chỉ công bố kết quả hoàn tất và hợp lệ**. Ba lớp này phải đi cùng nhau.
