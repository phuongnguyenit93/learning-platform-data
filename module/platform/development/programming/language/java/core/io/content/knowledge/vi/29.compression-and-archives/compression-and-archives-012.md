# Giải nén đúng thư mục đích và xử lý đường dẫn entry trong Java

## 1. Mục tiêu: giải nén đúng chỗ, không ghi ra ngoài vùng được phép

Trong Java I/O, một ZIP archive có thể chứa nhiều `ZipEntry`. Mỗi entry có **tên** (ví dụ `docs/manual.txt`), dữ liệu nén và metadata. Khi giải nén xuống ổ đĩa, chương trình phải chuyển **tên entry không đáng tin cậy** thành một `Path` trên máy đích, tạo thư mục cha, rồi ghi dữ liệu vào file được phép.

Lỗi phổ biến là nối tên entry vào thư mục đích mà không kiểm tra:

~~~java
Path target = outputDir.resolve(entry.getName());
Files.copy(zip, target); // nguy hiểm nếu entry.getName() chưa kiểm tra
~~~

Đây là **mã phản ví dụ**, không chạy độc lập. Nếu entry có tên `../../outside.txt`, thao tác ghi có thể vượt khỏi thư mục `outputDir`. Lỗ hổng này được gọi là **Zip Slip** (path traversal khi giải nén).

Một chương trình giải nén phù hợp phải đảm bảo:

1. Mọi file và thư mục nằm **bên trong một thư mục gốc đích** do ứng dụng chỉ định.
2. Entry không chứa đường dẫn tuyệt đối, `..`, ký tự phân tách nguy hiểm hoặc tên không tương thích chính sách.
3. Không đi xuyên **symbolic link** hoặc thành phần đường dẫn do người khác kiểm soát.
4. Không ghi đè file đã tồn tại nếu người dùng/chính sách không cho phép.
5. Có giới hạn **số lượng entry, độ dài tên, số byte giải nén và tổng tài nguyên**.
6. Giải phóng stream/channel đúng cách, phát hiện lỗi archive và không coi một lần copy lỗi là thành công.
7. Có kế hoạch xử lý file mới tạo dở khi thất bại; giải nén nhiều entry **không tự là transaction nguyên tử**.

Bài này tập trung giải nén ZIP bằng `java.util.zip` và `java.nio.file` trên **Java 17+**. Với `.tar.gz`, GZIP chỉ giải nén stream bên ngoài, còn TAR cần parser phù hợp; các nguyên tắc xử lý tên entry bên dưới vẫn có ích nhưng API TAR không thuộc `java.util.zip`.

## 2. Hiểu đúng tên ZipEntry và thư mục đích

Ví dụ trong một ZIP:

~~~text
Archive backup.zip
  docs/
  docs/readme.txt
  docs/config/app.properties
  images/logo.png
~~~

Giả sử ứng dụng muốn giải nén vào:

~~~text
/opt/myapp/imports/job-001/
~~~

Sau khi xử lý an toàn, kết quả mong đợi là:

~~~text
/opt/myapp/imports/job-001/
  docs/
    readme.txt
    config/
      app.properties
  images/
    logo.png
~~~

Trên Windows, thư mục gốc có thể là `C:\data\imports\job-001` thay vì đường dẫn Linux. **Tên trong ZIP thường dùng dấu slash `/` làm ký tự phân tách**; không nên tự ý xem `\` là đường dẫn con hợp lệ khi nhập archive không tin cậy.

### 2.1. ZipEntry không phải java.nio.file.Path

`ZipEntry.getName()` trả một **String lấy từ archive**, không phải một đường dẫn đã được hệ điều hành chuẩn hóa hoặc xác nhận quyền truy cập. Ví dụ:

~~~java
ZipEntry entry = zip.getNextEntry();
String name = entry.getName(); // dữ liệu lấy từ archive
~~~

`name` có thể đại diện file thường, thư mục (quy ước tên kết thúc bằng `/`), hoặc tên không an toàn. Java không tự động gắn tên đó vào đúng đích cho bạn.

**Không dùng `entry.getName()` trực tiếp làm đầu ra** trong `new File(...)`, `Files.copy(...)`, `Files.newOutputStream(...)` hoặc `Files.createDirectories(...)` nếu chưa xác thực.

### 2.2. Đường dẫn tương đối phải thuộc thư mục gốc

Với thư mục đích `root`, ta thường xây dựng:

~~~java
Path target = root.resolve(entry.getName()).normalize();
if (!target.startsWith(root)) {
    throw new IOException("Entry outside output directory");
}
~~~

Đây là **biện pháp bắt buộc cơ bản nhưng chưa đầy đủ**. Nó phải đi cùng:

- `root` là đường dẫn **tuyệt đối đã được xác định an toàn**, không so sánh một relative root với absolute target.
- Tên entry được kiểm tra **trước khi dùng**, nhất là absolute path, `..`, backslash, Windows drive/UNC và null byte.
- Kiểm tra symbolic link ở các thành phần thư mục cha và ngăn đổi đường dẫn qua race khi có đối tượng khác được quyền sửa filesystem.
- Chính sách overwrite và giới hạn tài nguyên.

Nếu `root` là absolute normalized, `target.startsWith(root)` là phép so sánh thành phần `Path`, **không phải** so chuỗi bằng `String.startsWith(...)`. Ví dụ đường dẫn `/safe/outside.txt` có thể bắt đầu bằng chuỗi `"/safe/out"` nhưng **không nằm dưới** path `/safe/out` theo thành phần Path.

## 3. Những kiểu tên entry không được tin tưởng

Bảng sau minh họa các trường hợp cần chặn hoặc áp dụng chính sách đặc biệt:

| Tên entry | Rủi ro | Cách xử lý an toàn điển hình |
|---|---|---|
| `docs/readme.txt` | Đường dẫn tương đối bình thường | Có thể chấp nhận nếu các kiểm tra khác đạt |
| `docs/config/app.yml` | Cần tạo thư mục cha | Xác thực rồi tạo directory an toàn |
| `../outside.txt` | Vượt một cấp lên trên | **Từ chối** |
| `../../secret.txt` | Vượt nhiều cấp | **Từ chối** |
| `/etc/passwd` | Absolute path Unix | **Từ chối** |
| `C:/Windows/temp.txt` | Windows drive-absolute | **Từ chối** |
| `C:relative.txt` | Windows drive-relative / tên có colon | **Từ chối** theo policy portable |
| `\\server\share\file.txt` | Windows UNC hoặc separator khác | **Từ chối** backslash/UNC |
| `docs\..\outside.txt` | Backslash traversal trên Windows | **Từ chối** |
| `docs/./a.txt` | Thành phần `.` không cần thiết | Nên từ chối theo policy chặt |
| `docs//a.txt` | Thành phần rỗng/đường dẫn bất thường | Nên từ chối |
| `docs/../a.txt` | Có `..` dù normalize vẫn bên trong | Nên từ chối ngay tên |
| `docs/a.txt:stream` | Alternate Data Stream (Windows) | Từ chối dấu colon |
| `docs/a.txt` lặp lại | Overwrite/collision | Từ chối duplicate hoặc có chính sách tường minh |
| Tên rất dài/nhiều cấp | Exhaustion, lỗi filesystem | Giới hạn độ dài và độ sâu |

Các ví dụ `C:`, `\`, ADS có tính đặc thù Windows. Để viết chương trình giải nén đa nền tảng và tránh khác biệt về cách parse của các filesystem provider, **không nên chấp nhận các dạng này chỉ vì chúng trông vô hại trên Linux**.

### Kiểm tra ngay cả khi normalize vẫn cho đường dẫn bên trong

Tên `docs/../file.txt` sau `normalize()` có thể thành `file.txt`, vẫn nằm dưới root. Nhưng chấp nhận dấu `..` làm tăng độ phức tạp, khiến kiểm tra tên không nhất quán và dễ bị khác biệt OS. Với một extractor chính sách chặt, **từ chối mọi path component `..` và `.`**, rồi mới resolve/normalize như lớp kiểm tra dự phòng.

### Directory entry

`ZipEntry.isDirectory()` thường nhận biết tên có dấu `/` cuối. Entry `docs/` là thư mục; code phải tạo directory thay vì mở output stream để ghi nội dung như file thường. Nhưng ZIP hợp lệ có thể **không chứa entry `docs/` riêng** mà chỉ chứa `docs/readme.txt`, vì vậy extractor cần tự tạo thư mục cha khi cần, sau khi đã xác thực đường dẫn.

Không dựa hoàn toàn vào đuôi `/` để xác định **mọi loại filesystem object trong ZIP do bên thứ ba tạo**; một số archive giữ Unix file modes/symlink metadata ngoài phạm vi đơn giản mà `ZipInputStream` biểu lộ.

## 4. Zip Slip: normalize, startsWith và ranh giới bảo vệ

Một extractor sai có thể làm:

~~~java
Path target = root.resolve(entry.getName()); // Chưa normalize/chưa validate.
Files.createDirectories(target.getParent());
Files.copy(zip, target);
~~~

Khi entry là `../attack.txt`, `resolve` tạo ra một path đi ra ngoài root theo nghĩa đường dẫn. `Files.createDirectories` và `Files.copy` có thể ghi ra nơi không mong muốn hoặc tác động một tài nguyên bên ngoài phạm vi extraction.

Một hướng kiểm tra tốt hơn:

~~~java
Path root = outputDir.toRealPath();
String name = entry.getName();

// Chặn dạng không đáng tin trước khi dùng Path API.
if (name.isEmpty() || name.startsWith("/")
        || name.indexOf('\\') >= 0
        || name.indexOf('\0') >= 0) {
    throw new IOException("Unsafe entry name");
}

Path target = root.resolve(name).normalize();
if (target.equals(root) || !target.startsWith(root)) {
    throw new IOException("ZIP entry escaped target directory");
}
~~~

Đây là **mã minh họa**, chưa bao gồm tách component để chặn `..`, `.`, colon, empty segments, symlink và quota. Mẫu chạy đầy đủ ở mục 8 triển khai những điểm đó.

### Vì sao không so chuỗi thô?

Đoạn code như:

~~~java
if (!target.toString().startsWith(root.toString())) {
    throw new IOException("Unsafe target");
}
~~~

là **mã phản ví dụ**. Nếu root là `/srv/out` thì `/srv/outside/a.txt` cũng bắt đầu bằng cùng chuỗi. `Path.startsWith(Path)` kiểm tra theo thành phần tên đường dẫn, giúp tránh nhầm lẫn này.

### Vì sao toAbsolutePath + normalize chưa chống được symlink?

`normalize()` xử lý các thành phần cú pháp `.` và `..`; nó **không duyệt filesystem để phát hiện symbolic link**. Giả sử dưới root đã có `docs` là symlink trỏ tới `/tmp/other`. Path `root/docs/file.txt` vẫn có thể vượt ngoài root **theo vị trí vật lý thực tế** dù phép kiểm tra tên/normalize/startsWith đều đạt.

Vì vậy phải chú ý đến **trạng thái filesystem**, chứ không chỉ String và Path.

## 5. Symlink, hardlink và TOCTOU

### 5.1. Directory symlink trong thư mục đích

Nếu thư mục đích cho phép những thành phần không đáng tin cậy, mã kiểu:

~~~java
Files.createDirectories(target.getParent());
Files.newOutputStream(target);
~~~

có thể đi qua một symlink đã có trên ổ đĩa và ghi vào vị trí khác. Cách phòng vệ cơ bản:

- Giải nén vào **thư mục mới, rỗng, private**, dưới một parent do ứng dụng kiểm soát.
- Khi duyệt các thành phần thư mục, dùng `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` để **không coi symlink là directory**.
- Khi tạo file, dùng `StandardOpenOption.CREATE_NEW` để không ghi đè file hoặc symlink đã tồn tại ở path cuối.
- Không tự động tạo symlink/hardlink từ metadata entry nếu chưa có policy nghiêm ngặt.

### 5.2. Giới hạn của check-then-use

Kiểm tra `NOFOLLOW_LINKS` rồi sau đó gọi `Files.newOutputStream(...)` **không tạo một transaction bảo mật nguyên tử** giữa các bước. Kẻ tấn công có quyền sửa thư mục đích có thể đổi một directory thành symlink **giữa lúc kiểm tra và lúc mở file**. Đây là lỗi **TOCTOU — time of check to time of use**.

Nếu threat model có tiến trình khác **đồng thời sửa trực tiếp thư mục đích**, cần cơ chế mạnh hơn: isolation/quyền thư mục riêng, OS sandbox, hoặc API tương đương descriptor-relative operation với `SecureDirectoryStream` khi provider hỗ trợ. Không được tuyên bố `normalize()`, `NOFOLLOW_LINKS` hay `CREATE_NEW` đơn lẻ làm code miễn nhiễm với mọi race.

### 5.3. Mã minh họa sử dụng thư mục mới

Ví dụ ở mục 8 chủ động yêu cầu `Files.createDirectory(destination)` **phải tạo directory mới**. Nếu directory đã tồn tại, chương trình từ chối thay vì trộn entry vào dữ liệu cũ. Điều này vừa tránh overwrite, vừa giảm nguy cơ có symlink do người khác để lại trong cây thư mục. Tuy nhiên, **parent của destination vẫn phải đáng tin cậy**, và không được cho actor không tin cậy sửa trong lúc giải nén.

### 5.4. Tên trùng và collision theo filesystem

Các entry `a.txt` lặp lại có thể khiến file sau ghi đè file trước. Ngoài ra, filesystem có thể coi `A.txt` và `a.txt` là cùng một file, hoặc chuẩn hóa Unicode/tên đặc biệt theo quy tắc OS. Vì vậy ngoài việc giữ `Set<Path>` để phát hiện tên trùng sau normalize, vẫn cần **CREATE_NEW** để file tồn tại không bị ghi đè. Một extractor dành cho môi trường có tên file đặc biệt cần chính sách kiểm tra bổ sung về tên reserved, trailing dots/spaces và Unicode normalization.

## 6. Giải nén từng entry bằng ZipInputStream

`java.util.zip.ZipInputStream` hoạt động trên một input stream chứa ZIP, tiến qua từng entry bằng `getNextEntry()`:

~~~java
try (ZipInputStream zip = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {
    ZipEntry entry;
    while ((entry = zip.getNextEntry()) != null) {
        // 1. Kiểm tra tên và root-bound path.
        // 2. Nếu là directory: tạo directory an toàn.
        // 3. Nếu là file: tạo file mới, copy theo chunk và đếm byte.
        // 4. closeEntry() sau khi xử lý xong entry.
        zip.closeEntry();
    }
}
~~~

Đây là **khung minh họa, không phải extractor độc lập**; trong code thật phải giải nén dữ liệu entry, không được chỉ gọi `closeEntry()` rồi coi file đã được trích xuất.

Các điểm API:

- `getNextEntry()` chuyển đến entry kế tiếp và trả `null` khi hết.
- `zip.read(buffer)` khi đang trong một entry trả **số byte đã giải nén**; `-1` là hết dữ liệu của entry ấy, **không phải** hết archive.
- `closeEntry()` kết thúc đọc entry hiện tại và chuẩn bị di chuyển đến entry tiếp.
- `ZipInputStream` không cho random lookup bằng tên như `ZipFile.getEntry(name)`.
- Mỗi entry nên có file đích riêng, nhưng không nhất thiết có directory entry cha trong ZIP.
- Với file upload/ZIP không đáng tin, không dùng `zip.readAllBytes()` rồi ghi: lượng giải nén có thể rất lớn.

### ZIP bomb và quota

Một archive có thể nén rất gọn nhưng bung thành gigabytes. **Không tin vào `ZipEntry.getSize()`** vì metadata có thể không có hoặc không đáng tin. Phải đếm **số byte thật sự trả về từ `zip.read(...)`** trong quá trình giải nén.

Các quota nên đặt rõ:

| Quota | Vì sao? |
|---|---|
| Số entry tối đa | Tránh hàng triệu file rỗng |
| Số byte giải nén mỗi entry | Tránh một file phình cực lớn |
| Tổng byte giải nén | Giới hạn dung lượng toàn archive |
| Độ dài tên entry | Chặn tên quá dài/path abuse |
| Độ sâu thư mục | Giảm rủi ro cây path cực sâu |
| Thời gian/deadline và CPU | Chống xử lý vô hạn/quá tốn CPU |
| Số lượng thư mục/file thực tế | Tránh inode exhaustion |
| Dung lượng trên disk quota | Tránh đầy phân vùng |

Các giới hạn trong demo là **giá trị minh họa**, không phải ngưỡng bảo mật chung cho mọi ứng dụng.

## 7. Chiến lược extractor an toàn: dữ liệu, kiểm tra, ghi, hoàn tất

Một quy trình có thể triển khai gồm:

1. Xác định đường dẫn ZIP đầu vào (nguồn) và chọn **parent đáng tin** cho output.
2. Tạo **thư mục output mới**; nếu đã có, từ chối hoặc thực hiện chính sách staging/merge riêng.
3. Đọc `ZipEntry.getName()`, kiểm tra chiều dài và từng segment, từ chối ký tự phân tách/`..`/đường dẫn tuyệt đối/drive.
4. Resolve path vào root đã canonicalize, normalize, xác minh `target.startsWith(root)` và không bằng root.
5. Dùng set để phát hiện entry path trùng sau normalize.
6. Với directory: tạo từng directory component, không đi qua symlink.
7. Với regular file: tạo file mới bằng `CREATE_NEW` rồi stream-decompress theo chunk.
8. Mỗi chunk đọc được phải cộng vào per-entry và total budget; dừng **trước khi ghi vượt quota**.
9. Gọi `closeEntry()` và xử lý ngoại lệ CRC/corrupt ZIP theo chính sách; nếu lỗi file, dọn file dở.
10. Sau toàn bộ archive: hoàn tất stream; quyết định publish output vào vị trí cuối chỉ khi archive và cấu trúc đã được xác nhận đầy đủ.

**Chú ý:** nếu fail ở entry thứ mười thì chín entry trước có thể đã được tạo. Vì thế phương án production thường dùng **staging directory**, chỉ công bố/di chuyển sang đích chính khi toàn bộ giải nén thành công; phải xác định atomicity/overwrite của thao tác di chuyển trên filesystem thực tế. Các thay đổi đa file không tự trở thành transaction.

## 8. Chương trình Java 17+ hoàn chỉnh: giải nén an toàn ở mức cơ bản

Ví dụ sau tạo một ZIP tốt có hai file, một ZIP độc hại có tên `../escape.txt`, và thử giải nén cả hai. Chương trình yêu cầu **thư mục đích mới và trống**, chặn path traversal và tên bất thường, không theo symlink directory đã tồn tại, không overwrite file, giới hạn kích thước giải nén và dọn tệp tạm.

Đây là ví dụ thiết kế **đơn giản, có thể chạy**, không phải sandbox chống lại đối thủ có quyền race sửa chính filesystem; xem mục 5 về TOCTOU.

**Tệp: `SafeZipExtractDemo.java`**

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class SafeZipExtractDemo {
    private static final int MAX_ENTRIES = 100;
    private static final int MAX_NAME_LENGTH = 240;
    private static final int MAX_DEPTH = 16;
    private static final long MAX_ENTRY_BYTES = 1_000_000L;
    private static final long MAX_TOTAL_BYTES = 3_000_000L;

    // Kiểm tra tên ZIP theo policy portable, rồi tạo path dưới root.
    private static Path safeTarget(Path root, String name)
            throws IOException {
        if (name.isEmpty() || name.length() > MAX_NAME_LENGTH
                || name.startsWith("/") || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0) {
            throw new IOException("Unsafe ZIP entry path");
        }

        String body = name.endsWith("/")
                ? name.substring(0, name.length() - 1)
                : name;
        String[] parts = body.split("/", -1);
        if (parts.length > MAX_DEPTH) {
            throw new IOException("Unsafe ZIP entry path");
        }

        for (String part : parts) {
            if (part.isEmpty() || part.equals(".")
                    || part.equals("..") || part.indexOf(':') >= 0) {
                throw new IOException("Unsafe ZIP entry path");
            }
        }

        Path target = root.resolve(name).normalize();
        if (target.equals(root) || !target.startsWith(root)) {
            throw new IOException("Unsafe ZIP entry path");
        }
        return target;
    }

    // Duyệt từng directory component và không chấp nhận symlink.
    private static void ensureDirs(Path root, Path dir)
            throws IOException {
        Path current = root;
        for (Path component : root.relativize(dir)) {
            current = current.resolve(component);
            if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                if (!Files.isDirectory(
                        current, LinkOption.NOFOLLOW_LINKS)) {
                    throw new IOException("Unsafe directory component");
                }
            } else {
                Files.createDirectory(current);
            }
        }
    }

    static long extract(Path archive, Path newDestination)
            throws IOException {
        // Yêu cầu directory chưa tồn tại. Parent phải đáng tin.
        Path root = Files.createDirectory(newDestination).toRealPath();
        Set<Path> seen = new HashSet<>();
        int entries = 0;
        long total = 0;

        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(archive), StandardCharsets.UTF_8)) {
            ZipEntry entry;

            while ((entry = zip.getNextEntry()) != null) {
                if (++entries > MAX_ENTRIES) {
                    throw new IOException("Too many entries");
                }

                Path target = safeTarget(root, entry.getName());
                if (!seen.add(target)) {
                    throw new IOException("Duplicate ZIP path");
                }

                if (entry.isDirectory()) {
                    ensureDirs(root, target);
                    zip.closeEntry();
                    continue;
                }

                ensureDirs(root, target.getParent());
                boolean created = false;
                try {
                    try (OutputStream out = Files.newOutputStream(
                            target, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                        created = true;
                        byte[] buffer = new byte[8192];
                        long count = 0;

                        for (int n; (n = zip.read(buffer)) != -1; ) {
                            if (n == 0) {
                                throw new IOException(
                                        "No decompression progress");
                            }
                            if (n > MAX_ENTRY_BYTES - count
                                    || n > MAX_TOTAL_BYTES - total) {
                                throw new IOException(
                                        "Decompressed data limit");
                            }

                            out.write(buffer, 0, n);
                            count += n;
                            total += n;
                        }
                    }
                    zip.closeEntry();
                } catch (IOException | RuntimeException ex) {
                    if (created) {
                        try {
                            Files.deleteIfExists(target);
                        } catch (IOException cleanup) {
                            ex.addSuppressed(cleanup);
                        }
                    }
                    throw ex;
                }
            }
        }
        return total;
    }

    // Chỉ phục vụ demo: tạo hai archive nhỏ để kiểm thử.
    private static void createZip(
            Path archive, String[] names, String[] bodies)
            throws IOException {
        try (ZipOutputStream zip = new ZipOutputStream(
                Files.newOutputStream(archive),
                StandardCharsets.UTF_8)) {
            for (int i = 0; i < names.length; i++) {
                zip.putNextEntry(new ZipEntry(names[i]));
                zip.write(bodies[i].getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("zip-safe-example-");
        try {
            Path good = work.resolve("good.zip");
            Path evil = work.resolve("evil.zip");

            createZip(
                    good,
                    new String[]{"docs/a.txt", "docs/b.txt"},
                    new String[]{"Hello ZIP", "Java 17"});
            createZip(
                    evil,
                    new String[]{"../escape.txt"},
                    new String[]{"not allowed"});

            Path goodOut = work.resolve("good-out");
            long copied = extract(good, goodOut);
            System.out.println("bytes=" + copied);
            System.out.println(
                    "a=" + Files.readString(
                            goodOut.resolve("docs/a.txt")));
            System.out.println(
                    "b=" + Files.readString(
                            goodOut.resolve("docs/b.txt")));

            try {
                extract(evil, work.resolve("bad-out"));
                System.out.println("blocked=false");
            } catch (IOException rejected) {
                System.out.println(
                        "blocked=" + rejected.getMessage());
            }

            System.out.println(
                    "escaped=" + Files.exists(
                            work.resolve("escape.txt")));
        } finally {
            // Work là thư mục tạm mới do demo sở hữu.
            try (Stream<Path> paths = Files.walk(work)) {
                for (Path p : paths
                        .sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
~~~

**Biên dịch/chạy với JDK 17+:**

~~~bash
javac SafeZipExtractDemo.java
java SafeZipExtractDemo
~~~

**Stdout đã chạy kiểm tra trên JDK:**

~~~text
bytes=16
a=Hello ZIP
b=Java 17
blocked=Unsafe ZIP entry path
escaped=false
~~~

### Giải thích từng kết quả

- File `docs/a.txt` chứa chuỗi UTF-8 `Hello ZIP` (9 byte); `docs/b.txt` chứa `Java 17` (7 byte), nên tổng giải nén `16` byte.
- Dù archive không có entry `docs/` riêng, `ensureDirs` tạo directory cần thiết trước khi ghi file.
- `Files.newOutputStream(..., CREATE_NEW, WRITE)` yêu cầu path file đích chưa tồn tại; nếu đã là file hoặc symlink, thao tác tạo mới không ghi đè.
- `../escape.txt` bị từ chối **trước khi tạo file** nhờ kiểm tra từng path component; thông báo `blocked=Unsafe ZIP entry path`.
- `escaped=false` xác nhận chương trình không tạo `escape.txt` ngoài thư mục `bad-out` trong demo này.
- `Files.createTempDirectory` cấp cho demo một parent tạm riêng, và `finally` xóa các file mà chính demo tạo.

### Giới hạn an toàn của demo

1. **Không bảo đảm chống race của tiến trình khác** được quyền sửa parent/output cùng lúc; đây là vấn đề `TOCTOU`. Trên server, chỉ giải nén vào thư mục riêng do service sở hữu với quyền hạn thích hợp, hoặc dùng primitive chống race.
2. **Không atomic cho cả archive:** nếu entry sau bị lỗi, entry trước có thể vẫn tồn tại trong `newDestination`. Trong production, giải nén vào staging, kiểm tra toàn bộ, rồi publish theo chính sách. Phải cleanup staging khi thất bại.
3. **Không tái hiện symlink/hardlink/permission/ownership metadata** từ ZIP. Đây là quyết định giảm bề mặt tấn công của ví dụ: entry được xử lý là directory hoặc regular file, không tạo link từ metadata. Nếu yêu cầu bảo tồn symlink, cần kiểm tra loại entry, link target, permission và ranh giới root theo threat model riêng.
4. **Quota là ngưỡng minh họa**: tối đa 100 entries, 240 ký tự tên, 16 levels, 1.000.000 byte/entry và tổng 3.000.000 byte. Với server thật còn cần deadline, CPU quota, số directory tạo thực tế, disk quota và hạn mức request.
5. **Dọn file tạm trong finally** có thể thất bại trên môi trường filesystem đặc biệt hoặc nếu file bị giữ bởi actor khác. Production cần logging và retry/retention chính sách thích hợp, không xóa thư mục không thuộc quyền sở hữu của mình.
6. **Dữ liệu source do demo tự tạo** và output đúng charset UTF-8. Với ZIP của bên thứ ba, charset entry names và payload có thể khác nhau; cần áp dụng chính sách hỗ trợ thực tế.

## 9. Một số cải tiến cho hệ thống production

### 9.1. Staging trước khi publish

Thay vì ghi trực tiếp vào thư mục hiển thị cho người dùng, nên:

1. Tạo staging directory mới trong khu vực service kiểm soát.
2. Giải nén vào staging sau khi validate entry.
3. Kiểm tra số file, kích thước, định dạng, checksum hay chữ ký nếu cần.
4. Chỉ khi toàn bộ archive thành công mới chuyển/đổi tên staging sang vị trí đích cuối.
5. Có cách rollback/delete staging khi fail và cleanup khi service bị crash.

**Không tự cho rằng `Files.move(..., ATOMIC_MOVE)` luôn được hỗ trợ** hoặc có nghĩa transaction trên mọi file store. Nó có thể ném `AtomicMoveNotSupportedException`; nếu target đã tồn tại, yêu cầu overwrite khác nhau theo policy. Trên nhiều filesystem, rename thư mục chỉ atomic trong những điều kiện cụ thể và vẫn không thay thế các bước xác nhận integrity.

### 9.2. Sử dụng thư mục đích đã tồn tại

Nếu product bắt buộc giải nén vào thư mục có sẵn, policy phải rõ:

- Có được ghi đè file cùng tên không?
- Entry trùng tên trong chính archive được chấp nhận không?
- Nếu target có symlink, junction/reparse point (Windows) hay hardlink thì làm gì?
- Các file ngoài archive đang có trong thư mục cần giữ nguyên chứ?
- Có cần đối chiếu file permission, ownership hoặc timestamps không?
- Có tiến trình khác được quyền tạo/xóa/đổi đường dẫn trong lúc giải nén không?

Mẫu demo **không hỗ trợ merge vào existing directory theo thiết kế**; phải có logic bổ sung thay vì thay `createDirectory` bằng `createDirectories` rồi coi mọi thứ vẫn an toàn.

### 9.3. Kiểm tra Unicode, case folding và tên hệ điều hành

Trên các filesystem khác nhau, nhiều tên entry có thể chỉ về cùng file hoặc tên bị từ chối:

- `a.txt` và `A.txt` có thể đụng nhau khi hệ thống không phân biệt hoa/thường.
- Unicode có thể có nhiều biểu diễn normalization.
- Trên Windows, các tên device reserved như `CON`, `PRN`, `AUX` hoặc `NUL` có giới hạn riêng, kể cả khi thêm extension.
- Tên có dấu chấm/khoảng trắng cuối có thể bị xử lý đặc biệt tùy provider.
- `:` có thể biểu diễn Alternate Data Stream trên NTFS, nên policy portable của ví dụ cấm nó.

`CREATE_NEW` từ chối file thực tế đã tồn tại, nhưng hệ thống production nên xác thực trước tên không hợp lệ và báo lỗi rõ ràng.

### 9.4. Chống Zip bomb và disk exhaustion

Ngay cả khi có quota byte, archive có thể khai báo hoặc tạo vô số entry rỗng. Phải kết hợp **count quota + byte quota + depth/path quota + CPU/deadline + disk quota**. Đếm byte được giải nén thực tế quan trọng vì kích thước metadata của ZIP có thể không biết trước (`ZipEntry.getSize() == -1`) hoặc không nên tin.

Không dùng `ZipInputStream.readAllBytes()` cho entry không đáng tin. Trong demo, mảng đệm cố định 8.192 byte, mỗi chunk được kiểm tra giới hạn **trước khi ghi**. Phép so sánh `n > MAX_TOTAL_BYTES - total` cũng tránh cộng tràn số khi dùng quota dương.

### 9.5. Integrity và chữ ký

ZIP thường có **CRC-32** để phát hiện lỗi truyền/lưu trữ. CRC-32 **không phải cơ chế chống sửa đổi có chủ đích**. Nếu archive được dùng làm gói triển khai/phần mềm/cấu hình quan trọng, cần hệ thống xác thực chữ ký số/MAC hay hash được đối chiếu từ nguồn tin cậy. File hợp lệ theo CRC vẫn có thể chứa payload nguy hiểm hoặc file path gây rủi ro nếu không kiểm tra.

`ZipInputStream` đọc local entry headers; `ZipFile` dùng central directory để truy cập entry theo tên. Với archive không tin cậy có metadata không nhất quán giữa local và central directory, việc chọn parser/API có thể ảnh hưởng chính sách xử lý. Không tự suy luận chỉ cần scan một danh sách tên là đã đảm bảo đúng mọi byte/entry mà extractor sẽ xử lý. **Validate ngay khi xử lý từng entry thực tế**.

## 10. Những lỗi thường gặp

1. **Lấy `entry.getName()` ghép vào output và ghi ngay.** Dễ có Zip Slip.
2. **Chỉ so `target.toString().startsWith(root.toString())`.** Có thể nhầm `/root/outside` với `/root/out`.
3. **Chỉ dùng `normalize()` rồi tin rằng đã xử lý symlink.** Normalize không duyệt filesystem.
4. **Không từ chối `..` vì sau normalize vẫn nằm trong root.** Làm policy không nhất quán, tăng nguy cơ bypass.
5. **Chỉ lọc dấu `/` mà quên backslash trên Windows.** Có thể bỏ lọt traversal.
6. **Tin rằng `Path.isAbsolute()` trên Linux chặn được `C:\...` trên Windows.** Cần kiểm tra định dạng tên portable trước.
7. **Dùng `Files.createDirectories` cho bất kỳ parent nào trong cây đích cũ.** Có thể đi qua symlink.
8. **Dùng `Files.newOutputStream(target)` mặc định.** Có thể truncate file đã tồn tại; dùng `CREATE_NEW` khi không cho overwrite.
9. **Cho phép nhiều entry cùng tên tự ghi đè.** Có thể thay thế payload hợp lệ bằng payload nguy hiểm.
10. **Dùng `readAllBytes()` hoặc `Files.copy` không có hạn mức với ZIP không đáng tin.** Có thể hết RAM/disk vì Zip bomb.
11. **Tin `ZipEntry.getSize()` luôn có giá trị đúng.** Có thể `-1` hoặc metadata không đáng tin.
12. **Gọi `zip.read()==-1` rồi cho rằng hết cả archive.** Đó là EOF entry; phải tiếp tục `getNextEntry()`.
13. **Không đóng `ZipInputStream`/output stream.** Gây leak hoặc file ghi thiếu.
14. **Nhầm entry `docs/` là file regular.** Phải tạo directory, không ghi payload thành file.
15. **Coi extraction thất bại là đã rollback hết file.** Các entry ghi trước đó có thể còn tồn tại.
16. **Dùng `NOFOLLOW_LINKS` + kiểm tra rồi tuyên bố loại bỏ hoàn toàn TOCTOU.** Nếu actor khác có quyền thay filesystem, vẫn cần cách ly và primitive mạnh hơn.
17. **Tin CRC-32 là chữ ký số của nhà phát hành.** CRC không chống giả mạo.
18. **Giải nén từ archive ZIP được upload vào một thư mục chung có quyền ghi công khai.** Tăng nguy cơ đường dẫn bị thay đổi trong lúc chạy.

## 11. Tự kiểm tra

**Câu 1.** Vì sao `root.resolve(entry.getName()).normalize().startsWith(root)` cần thiết nhưng chưa đủ?

**Đáp án:** Nó kiểm tra containment theo thành phần `Path`, nhưng chưa chặn đủ tên platform-specific, symlink trong filesystem, TOCTOU, overwrite, duplicate và resource exhaustion.

**Câu 2.** Entry tên `../../escape.txt` được đặt dưới `/data/uploads/job1`. Có được tạo file không?

**Đáp án:** Không. Tên chứa `..` phải bị từ chối. Nếu dùng trực tiếp, nó có thể thoát khỏi `job1` rồi ghi vào thư mục khác.

**Câu 3.** ZIP chỉ có `docs/a.txt` mà không có entry `docs/`. Có thể giải nén đúng không?

**Đáp án:** Có. Sau khi validate tên, extractor tạo an toàn directory cha `docs` rồi tạo file `a.txt`.

**Câu 4.** Vì sao `CREATE_NEW` hữu ích hơn mở output stream mặc định?

**Đáp án:** Vì nó yêu cầu tạo file mới và thất bại nếu file/path cuối đã tồn tại (kể cả symlink), tránh ghi đè/truncate theo cơ chế mở mặc định.

**Câu 5.** Vì sao vẫn cần chống Zip bomb dù kiểm tra path đã an toàn?

**Đáp án:** Path validation chỉ giới hạn nơi ghi; archive nhỏ có thể tạo quá nhiều file hoặc dữ liệu giải nén khổng lồ, làm cạn CPU/RAM/disk.

**Câu 6.** Thư mục output root do ứng dụng sở hữu nhưng tiến trình khác được phép đổi tên thành phần con đồng thời. Kiểm tra `NOFOLLOW_LINKS` có đủ an toàn không?

**Đáp án:** Không. Check-then-open có thể bị race; cần isolation, quyền directory riêng hoặc API chống TOCTOU phù hợp.

**Câu 7.** Extraction thất bại sau khi ghi được 5/10 entry. Các file trước đó có tự mất đi không?

**Đáp án:** Không. Muốn hành vi gần transaction cần staging, chính sách cleanup và publish sau khi kiểm tra thành công.

### Tài liệu Java 17 chính thức

- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [Path: resolve, normalize, startsWith](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Files: createDirectory, newOutputStream, exists, isDirectory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StandardOpenOption.CREATE_NEW](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html#CREATE_NEW)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
