# Thực hành Java 17: nén, giải nén ZIP có giới hạn và kiểm tra đường dẫn entry

## 1. Mục tiêu và kết quả thực hành

Bài thực hành này xây dựng một **ZIP packer/extractor** bằng Java Core I/O, không phụ thuộc thư viện ngoài. Chương trình nén một cây thư mục thành `.zip`, giải nén sang thư mục đích mới và chủ động từ chối dữ liệu vượt chính sách.

Sau khi làm xong, bạn có thể:

1. Dùng `Files.walkFileTree` duyệt cây file **không đi theo symbolic link** theo mặc định.
2. Dùng `ZipOutputStream` tạo archive gồm file và cả **thư mục rỗng**.
3. Dùng `ZipInputStream` xử lý lần lượt từng `ZipEntry`, không load tất cả file vào RAM.
4. Đặt giới hạn về **số entry, độ sâu, độ dài tên, số byte mỗi file và tổng số byte giải nén**.
5. Phát hiện **Zip Slip** qua entry tên `../escape.txt`, tên tuyệt đối hoặc các separator không an toàn.
6. Dùng `Path.resolve`, `normalize`, `Path.startsWith(Path)`, `NOFOLLOW_LINKS` và `CREATE_NEW` đúng phạm vi.
7. Tạo thư mục cha cho file con dù ZIP không có directory entry riêng.
8. Phân biệt thành công của việc ghi dữ liệu, kiểm tra đường dẫn, **toàn vẹn của archive** và khả năng chống các race trên filesystem.
9. Chạy test **round trip** rồi thử hai archive có vấn đề: traversal và quá giới hạn giải nén.

Kết quả mong đợi:

~~~text
packedBytes=9
unpackedBytes=9
sameA=true
emptyDirectory=true
zipSlip=Unsafe entry name
limit=Uncompressed byte limit
outsideCreated=false
~~~

**Lưu ý:** Đây là bài thực hành thiết kế nền tảng và phòng vệ nhiều lớp. Nó **không tự xưng là sandbox hoàn chỉnh trước đối thủ có quyền sửa filesystem đồng thời**. Phần cuối giải thích cách nâng lên thành giải pháp production với staging, kiểm soát quyền và xử lý TOCTOU.

## 2. Bài toán cụ thể

Giả sử input là:

~~~text
source/
  docs/
    a.txt       (Alpha)
    b.txt       (Beta)
  empty/
~~~

Chương trình tạo:

~~~text
bundle.zip
  docs/
  docs/a.txt
  docs/b.txt
  empty/
~~~

Sau đó giải nén vào **thư mục output mới**, ta mong:

~~~text
output/
  docs/
    a.txt       (Alpha)
    b.txt       (Beta)
  empty/
~~~

Cùng lúc, extractor phải từ chối:

~~~text
../escape.txt              -> ghi ra ngoài output
/srv/app/config.txt        -> đường dẫn tuyệt đối
C:/Windows/Temp/a.txt      -> tên có dấu ':' kiểu Windows drive
docs\..\escape.txt         -> backslash traversal
docs/./a.txt               -> tên không chuẩn theo chính sách
docs/../a.txt              -> thành phần '..'
docs/a.txt (lặp)           -> duplicate/overwrite
large.txt (bung quá quota) -> zip bomb / disk exhaustion
~~~

ZIP là **archive có nhiều entry mang tên** chứ không phải một byte stream nén GZIP. `ZipOutputStream` và `ZipInputStream` làm việc lần lượt với `ZipEntry`. Định dạng ZIP có thể lưu từng entry bằng `DEFLATED` hoặc `STORED`; ZIP **không đồng nghĩa mọi entry đều bị nén**.

## 3. Thiết kế chính sách trước khi viết code

Không nên viết hàm `extract(zip, target)` rồi mới tìm cách vá các tên nguy hiểm. Hãy xác định rõ chính sách:

| Ràng buộc | Giá trị trong ví dụ | Ý nghĩa |
|---|---:|---|
| `maxEntries` | 20 | Giới hạn tổng số file và directory entry |
| `maxDepth` | 8 | Giới hạn số thành phần tên entry |
| `maxName` | 100 | Giới hạn độ dài chuỗi tên entry |
| `maxFileBytes` | 128 | Giới hạn số byte **chưa nén** của mỗi file |
| `maxTotalBytes` | 256 | Giới hạn tổng số byte **chưa nén** |
| Output dir | Chưa tồn tại | Không merge/overwrite dữ liệu cũ |
| Symlink đầu vào | Từ chối | Không pack nội dung ngoài cây được phép |
| Symlink trên output | Không theo khi duyệt cha | Giảm nguy cơ ghi lệch đích |
| File trùng đường dẫn | Từ chối | Tránh thay thế dữ liệu |
| Entry name bất thường | Từ chối | Tránh traversal/platform-specific path |
| Bộ nhớ đọc/ghi | Buffer 8192 byte | Không `readAllBytes()` với file không tin cậy |

Các ngưỡng `128`/`256` byte cực nhỏ để dễ thử **bài thực hành**; chúng **không phải gợi ý quota production**. Trong hệ thống thật, chọn quota theo yêu cầu nghiệp vụ, memory/disk budget, số người dùng đồng thời, thời gian và giới hạn hệ thống.

Chúng ta dùng một Java `record` để chứa chính sách:

~~~java
record Limits(
        int maxEntries,
        int maxDepth,
        int maxName,
        long maxFileBytes,
        long maxTotalBytes) {
}
~~~

Đây là **mã trích từ class chính ở mục 6**, không phải file chạy độc lập. Trong code production, nên validate những giá trị record nhận vào đều dương/hợp lệ ở constructor/factory; ví dụ này khởi tạo bằng hằng số đã kiểm soát.

## 4. Bước 1 — duyệt nguồn để nén mà không đi ra ngoài cây

`Files.walkFileTree(root, visitor)` mặc định **không theo symbolic link** khi không truyền `FOLLOW_LINKS`. Với `SimpleFileVisitor`:

- `preVisitDirectory`: gặp directory, có thể ghi một directory entry kết thúc bằng dấu `/`.
- `visitFile`: gặp file thường, ghi một file entry và stream từng chunk.
- Nếu gặp symlink hoặc file type không được hỗ trợ, ví dụ **từ chối** thay vì silently follow/copy.
- Nếu tệp nguồn thay đổi trong lúc pack, cần xử lý kiểm thử/threat model riêng; `walkFileTree` không tạo snapshot bất biến của cả cây thư mục.

### Lấy tên entry độc lập máy chạy

`Path` trên Windows có thể biểu diễn separator khác Linux. Tên trong ZIP nên được chuẩn hóa thành **relative name dùng `/`**:

~~~java
static String relativeName(Path root, Path path) {
    return root.relativize(path).toString().replace('\\', '/');
}
~~~

Đây là method minh họa. Không ghi tên tuyệt đối của file nguồn vào ZIP: người giải nén chỉ cần tên tương đối dưới một thư mục đích do họ chọn.

**Không tạo ZIP ngay trong cây nguồn đang duyệt.** Nếu output archive nằm trong source directory, traversal có thể gặp chính file ZIP đang tăng kích thước và làm cho input không ổn định. Ví dụ sẽ từ chối `archivePath.startsWith(sourceRoot)` sau khi canonicalize root.

### Giữ directory rỗng

Nếu chỉ tạo entry cho file, một directory `empty/` không có file con có thể bị mất. Vì vậy với directory (ngoại trừ root), tạo `ZipEntry("relative/path/")`. Phần directory entry **không mang nội dung file thường** trong demo.

## 5. Bước 2 — định nghĩa tên entry được phép và đường dẫn đích

### 5.1. Vì sao `entry.getName()` là dữ liệu không đáng tin?

Tên ZIP do người tạo archive quyết định. Java `ZipInputStream.getNextEntry()` trả `ZipEntry` nhưng **không tự kiểm tra rằng tên file đó an toàn để ghi vào một output directory**.

Phản ví dụ:

~~~java
Path target = outputRoot.resolve(entry.getName());
Files.copy(zipInputStream, target); // KHÔNG được làm với tên chưa kiểm tra.
~~~

Đây là **mã phản ví dụ**, không chạy độc lập. Với tên `../escape.txt`, thao tác resolve có thể đưa file ra ngoài `outputRoot`. Đây là **Zip Slip/path traversal**.

### 5.2. Kiểm tra từng thành phần tên

Policy của demo:

- Từ chối tên rỗng hoặc quá `maxName` ký tự.
- Từ chối tên bắt đầu bằng `/`.
- Từ chối dấu `\` (tránh Windows traversal/UNC và sự nhập nhằng separator).
- Từ chối ký tự NUL.
- Loại dấu `/` cuối **chỉ khi kiểm tra directory entry**.
- Chia theo `/` và từ chối thành phần rỗng, `.`, `..` hoặc chứa dấu `:`.
- Giới hạn số thành phần theo `maxDepth`.
- Sau đó mới `root.resolve(name).normalize()` và xác nhận `target.startsWith(root)` theo **thành phần Path**.

~~~java
static Path targetFor(Path root, String name, Limits limits)
        throws IOException {
    validateName(name, limits);
    Path target = root.resolve(name).normalize();
    if (target.equals(root) || !target.startsWith(root)) {
        throw new IOException("Unsafe entry name");
    }
    return target;
}
~~~

`validateName` và `Limits` được triển khai trong code đầy đủ bên dưới. **Không dùng `target.toString().startsWith(root.toString())`** vì chuỗi `/safe/output-other` có thể trông như con của `/safe/output` dù `Path` nói khác.

### 5.3. Phân biệt normalize với real path

- `normalize()` là xử lý **cú pháp đường dẫn**, loại thành phần `.`/`..`; không kiểm tra symbolic link thực tế trên disk.
- `toRealPath()` xác định path thực và cần tài nguyên tồn tại; nó có thể resolve symlink theo hành vi được yêu cầu.
- `Path.startsWith(Path)` so sánh theo các thành phần đường dẫn trên provider tương ứng, không đơn thuần là tiền tố chuỗi.
- `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` giúp từ chối một symlink khi đang xét một component có phải directory thật hay không.

Một symlink trong thư mục cha vẫn có thể đưa I/O ra ngoài root nếu chỉ kiểm tra `normalize()+startsWith`. Demo tạo **output directory mới** dưới parent do ứng dụng kiểm soát và kiểm tra các thành phần khi tạo directory. Nhưng nếu attacker có thể sửa parent/concurrent subdirectory, còn rủi ro **TOCTOU**, giải thích ở mục 10.

## 6. Chương trình Java 17+ hoàn chỉnh: pack, unpack và hai trường hợp bị chặn

**Tên file: `ArchivePracticeDemo.java`**

Chương trình dưới đây tự tạo thư mục tạm và dữ liệu test nên không cần bạn chuẩn bị file bên ngoài. Code sử dụng **Java 17 standard library**; không cần Maven, Gradle hay JUnit để chạy bài lab.

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.zip.*;

public class ArchivePracticeDemo {
    record Limits(int maxEntries, int maxDepth, int maxName,
                  long maxFileBytes, long maxTotalBytes) {
    }

    static final Limits NORMAL = new Limits(20, 8, 100, 128, 256);

    // Cấm relative path nguy hiểm và đường dẫn không portable.
    static void validateName(String name, Limits limits)
            throws IOException {
        if (name.isEmpty() || name.length() > limits.maxName()
                || name.charAt(0) == '/' || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0) {
            throw new IOException("Unsafe entry name");
        }

        String value = name.endsWith("/")
                ? name.substring(0, name.length() - 1)
                : name;

        String[] pieces = value.split("/", -1);
        if (pieces.length > limits.maxDepth()) {
            throw new IOException("Unsafe entry name");
        }

        for (String part : pieces) {
            if (part.isEmpty() || part.equals(".")
                    || part.equals("..") || part.indexOf(':') >= 0) {
                throw new IOException("Unsafe entry name");
            }
        }
    }

    static String relativeName(Path root, Path path) {
        return root.relativize(path).toString().replace('\\', '/');
    }

    // Duyệt file nguồn, tạo ZIP theo entry và giới hạn byte được đọc.
    static long pack(Path sourceDir, Path archive, Limits limits)
            throws IOException {
        if (Files.isSymbolicLink(sourceDir)) {
            throw new IOException("Symlink source");
        }

        Path root = sourceDir.toRealPath();
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)
                || archive.toAbsolutePath().normalize().startsWith(root)) {
            throw new IOException("Archive path invalid");
        }

        final long[] total = {0};
        final int[] entries = {0};

        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(
                        archive,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE),
                StandardCharsets.UTF_8)) {

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                void begin(String name) throws IOException {
                    validateName(name, limits);
                    if (++entries[0] > limits.maxEntries()) {
                        throw new IOException("Entry limit");
                    }
                    out.putNextEntry(new ZipEntry(name));
                }

                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs)
                        throws IOException {

                    if (!dir.equals(root)) {
                        begin(relativeName(root, dir) + "/");
                        out.closeEntry();
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {

                    if (!attrs.isRegularFile()) {
                        throw new IOException(
                                "Unsupported source type");
                    }

                    begin(relativeName(root, file));
                    long size = 0;

                    try (InputStream in = Files.newInputStream(
                            file, LinkOption.NOFOLLOW_LINKS)) {
                        byte[] buffer = new byte[8192];

                        for (int n; (n = in.read(buffer)) != -1; ) {
                            if (n == 0) {
                                throw new IOException(
                                        "No input progress");
                            }

                            if (n > limits.maxFileBytes() - size
                                    || n > limits.maxTotalBytes()
                                           - total[0]) {
                                throw new IOException(
                                        "Uncompressed byte limit");
                            }

                            out.write(buffer, 0, n);
                            size += n;
                            total[0] += n;
                        }
                    }

                    out.closeEntry();
                    return FileVisitResult.CONTINUE;
                }
            });

        } catch (IOException | RuntimeException ex) {
            // Không để lại ZIP pack dở.
            try {
                Files.deleteIfExists(archive);
            } catch (IOException cleanup) {
                ex.addSuppressed(cleanup);
            }
            throw ex;
        }

        return total[0];
    }

    static Path targetFor(Path root, String name, Limits limits)
            throws IOException {
        validateName(name, limits);

        Path target = root.resolve(name).normalize();
        if (target.equals(root) || !target.startsWith(root)) {
            throw new IOException("Unsafe entry name");
        }
        return target;
    }

    // Tạo từng thư mục cha, không chấp nhận symbolic link làm directory.
    static void directories(Path root, Path destDir) throws IOException {
        Path at = root;

        for (Path part : root.relativize(destDir)) {
            at = at.resolve(part);

            if (Files.exists(at, LinkOption.NOFOLLOW_LINKS)) {
                if (!Files.isDirectory(
                        at, LinkOption.NOFOLLOW_LINKS)) {
                    throw new IOException(
                            "Non-directory or symlink parent");
                }
            } else {
                Files.createDirectory(at);
            }
        }
    }

    // Giải nén ZIP vào thư mục MỚI, chặn path traversal và byte bomb.
    static long unpack(Path archive, Path newOutput, Limits limits)
            throws IOException {
        Path root = Files.createDirectory(newOutput).toRealPath();
        Set<Path> names = new HashSet<>();
        int entries = 0;
        long total = 0;

        try (ZipInputStream in = new ZipInputStream(
                Files.newInputStream(archive),
                StandardCharsets.UTF_8)) {

            ZipEntry entry;
            while ((entry = in.getNextEntry()) != null) {
                if (++entries > limits.maxEntries()) {
                    throw new IOException("Entry limit");
                }

                Path target = targetFor(
                        root, entry.getName(), limits);

                if (!names.add(target)) {
                    throw new IOException("Duplicate entry");
                }

                if (entry.isDirectory()) {
                    directories(root, target);
                    in.closeEntry();
                    continue;
                }

                directories(root, target.getParent());
                boolean created = false;

                try {
                    long size = 0;

                    try (OutputStream out = Files.newOutputStream(
                            target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                        created = true;
                        byte[] buffer = new byte[8192];

                        for (int n; (n = in.read(buffer)) != -1; ) {
                            if (n == 0) {
                                throw new IOException(
                                        "No output progress");
                            }

                            if (n > limits.maxFileBytes() - size
                                    || n > limits.maxTotalBytes()
                                           - total) {
                                throw new IOException(
                                        "Uncompressed byte limit");
                            }

                            out.write(buffer, 0, n);
                            size += n;
                            total += n;
                        }
                    }

                    in.closeEntry();

                } catch (IOException | RuntimeException ex) {
                    // Nếu đang giải nén dở file hiện tại, xóa file đó.
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

        // Các file entry trước đó vẫn còn nếu unpack lỗi ở entry sau.
        return total;
    }

    // Chỉ phục vụ bài kiểm thử: tạo một ZIP chứa một entry tùy chọn.
    static void makeSingleZip(
            Path archive, String name, byte[] content)
            throws IOException {
        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(
                        archive,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE),
                StandardCharsets.UTF_8)) {

            out.putNextEntry(new ZipEntry(name));
            out.write(content);
            out.closeEntry();
        }
    }

    // Chỉ xóa directory tạm do demo tạo và sở hữu.
    static void clean(Path work) throws IOException {
        if (!Files.exists(work)) {
            return;
        }

        try (var paths = Files.walk(work)) {
            for (Path p : paths
                    .sorted(Comparator.reverseOrder())
                    .toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory(
                "archive-practice-");

        try {
            Path source = Files.createDirectory(
                    work.resolve("source"));
            Path docs = Files.createDirectory(
                    source.resolve("docs"));

            Files.writeString(
                    docs.resolve("a.txt"), "Alpha",
                    StandardCharsets.UTF_8);
            Files.writeString(
                    docs.resolve("b.txt"), "Beta",
                    StandardCharsets.UTF_8);
            Files.createDirectory(source.resolve("empty"));

            // Happy path: source -> ZIP -> output mới.
            Path zip = work.resolve("bundle.zip");
            System.out.println(
                    "packedBytes=" + pack(source, zip, NORMAL));

            Path output = work.resolve("output");
            System.out.println(
                    "unpackedBytes=" + unpack(zip, output, NORMAL));

            System.out.println("sameA=" + Arrays.equals(
                    Files.readAllBytes(docs.resolve("a.txt")),
                    Files.readAllBytes(
                            output.resolve("docs/a.txt"))));
            System.out.println("emptyDirectory=" +
                    Files.isDirectory(
                            output.resolve("empty")));

            // Negative test 1: ZIP có tên thoát ra ngoài root.
            Path escape = work.resolve("escape.zip");
            makeSingleZip(
                    escape, "../escape.txt", new byte[]{1});

            try {
                unpack(escape, work.resolve("reject-escape"), NORMAL);
            } catch (IOException ex) {
                System.out.println(
                        "zipSlip=" + ex.getMessage());
            }

            // Negative test 2: entry nhỏ khi nén nhưng bung quá limit.
            Path huge = work.resolve("huge.zip");
            makeSingleZip(
                    huge, "large.txt", new byte[200]);

            try {
                unpack(
                        huge,
                        work.resolve("reject-large"),
                        new Limits(20, 8, 100, 32, 64));
            } catch (IOException ex) {
                System.out.println(
                        "limit=" + ex.getMessage());
            }

            System.out.println("outsideCreated=" +
                    Files.exists(
                            work.resolve("escape.txt")));

        } finally {
            clean(work);
        }
    }
}
~~~

Chạy tại thư mục chứa `ArchivePracticeDemo.java`:

~~~bash
javac ArchivePracticeDemo.java
java ArchivePracticeDemo
~~~

**Stdout đã kiểm tra bằng Java:**

~~~text
packedBytes=9
unpackedBytes=9
sameA=true
emptyDirectory=true
zipSlip=Unsafe entry name
limit=Uncompressed byte limit
outsideCreated=false
~~~

### Giải thích kết quả

- `packedBytes=9`: hai file chứa `Alpha` (5 byte UTF-8) và `Beta` (4 byte UTF-8). Đó là **số byte dữ liệu gốc đã đưa vào ZIP**, không phải `Files.size(bundle.zip)`. ZIP có header và central directory nên kích thước archive khác.
- `unpackedBytes=9`: tổng số byte thật sự giải nén thành file, độc lập metadata size chưa chắc đáng tin.
- `sameA=true`: so sánh bằng `Arrays.equals(byte[], byte[])` xác nhận file nguồn và file khôi phục có bytes bằng nhau.
- `emptyDirectory=true`: directory entry `empty/` đã được pack và tạo lại đúng tên.
- `zipSlip=Unsafe entry name`: `../escape.txt` bị từ chối trước khi được dùng làm đường dẫn ghi.
- `limit=Uncompressed byte limit`: entry gồm 200 byte `0` bị từ chối khi giới hạn mỗi file chỉ 32 byte và tổng 64 byte.
- `outsideCreated=false`: không có file `escape.txt` bị tạo ở parent của directory đích.

Chương trình sử dụng `Files.createTempDirectory` và chỉ xóa **cây tạm do chính nó tạo**, kể cả khi test throw. Nếu chạy trong môi trường không cho tạo file hoặc thiếu quyền truy cập filesystem, thao tác có thể ném `IOException`; đó là giới hạn môi trường chứ không phải output của happy path.

## 7. Bước 3 — kiểm tra ZIP thực tế có gì?

Khi pack, `ZipOutputStream.putNextEntry` ghi tên entry và bắt đầu luồng dữ liệu của entry. `closeEntry` hoàn tất entry hiện tại, còn `ZipOutputStream.close` hoàn tất cả ZIP archive và đóng output. **Không mở ZIP output để đọc trước khi stream được đóng/finish**: central directory có thể chưa được ghi đủ.

Hai cách đọc ZIP có mục tiêu khác nhau:

| API | Dùng khi nào? |
|---|---|
| `ZipInputStream` | Duyệt lần lượt những entry khi input có dạng stream, ví dụ upload, và kiểm tra tên **ngay trước khi ghi** |
| `ZipFile` | Mở một file ZIP trên đĩa, liệt kê/tìm entry theo tên và lấy stream đọc entry |
| `ZipOutputStream` | Tạo archive bằng cách thêm nhiều `ZipEntry` |
| `ZipEntry` | Metadata/tên của từng mục trong archive |

Lưu ý `ZipInputStream` làm việc chủ yếu theo các **local entry records**; `ZipFile` có thể tận dụng **central directory**. Một archive chế tạo không nhất quán giữa local headers và central directory có thể có những khác biệt khi được nhiều công cụ phân tích. Đối với input không tin cậy, **xác thực entry thực tế mà extractor sẽ ghi**, không chỉ scan một danh sách tên bằng một parser rồi mặc nhiên tin rằng parser khác sẽ giải nén giống hệt.

### Tại sao đọc data theo chunk?

Code:

~~~java
byte[] buffer = new byte[8192];
for (int n; (n = zip.read(buffer)) != -1; ) {
    // Kiểm tra quota theo n, sau đó ghi n byte.
}
~~~

Đây là đoạn mô tả cấu trúc, không phải loop độc lập. `ZipInputStream.read` trả dữ liệu **đã giải nén của entry hiện tại**. Giá trị `-1` ở đây là hết entry, không có nghĩa đã hết archive. Sau khi xử lý xong, gọi `closeEntry()` rồi `getNextEntry()` để nhận entry tiếp.

**Không dùng `zip.readAllBytes()` cho archive không tin cậy**, vì entry nhỏ trên disk có thể bung thành dữ liệu lớn và gây hết heap.

## 8. Bước 4 — chống Zip Slip: kiểm tra tên trước khi tạo file

Trong code `unpack`, mỗi entry trải qua:

~~~text
getNextEntry()
     |
     v
++entryCount, kiểm tra maxEntries
     |
     v
validateName: length / absolute / slash / backslash / . / .. / colon
     |
     v
root.resolve(name).normalize()
     |
     v
target.startsWith(root) và target != root
     |
     v
Set<Path>.add(target): từ chối duplicate
     |
     v
tạo directory cha an toàn
     |
     +-- directory entry --> tạo thư mục, closeEntry
     |
     +-- file entry -------> CREATE_NEW, copy có byte quota, closeEntry
~~~

### Tại sao không chỉ `Path.isAbsolute`?

Trên Linux, tên `C:\Windows\file.txt` có thể được parse như một tên tương đối có backslash, trong khi trên Windows nó mang nghĩa path khác. Bài dùng **chính sách tên portable**: cấm backslash và colon trước khi resolve, thay vì chỉ dựa vào cách parse path của hệ điều hành hiện tại.

Tương tự, `\\server\share\...` có thể là đường dẫn UNC trên Windows. Chặn backslash giúp giảm một nhóm ambiguity.

### Tại sao cấm dấu `..` ngay cả khi normalize không thoát root?

Ví dụ `docs/../a.txt` sau normalize có thể trở thành `a.txt` và vẫn nằm trong root. Tuy nhiên, chấp nhận traversal components làm chính sách khó kiểm toán, nhất là khi có symlink/logic giải nén khác. Bài chọn **từ chối mọi `..` và `.`** để có một quy tắc nhất quán.

### Vì sao so sánh Path chứ không so chuỗi?

Nếu root là `/var/data/out`, path `/var/data/outside.txt` cũng bắt đầu với chuỗi `"/var/data/out"`. Nhưng `Path.startsWith(root)` xem các path components và không coi `outside.txt` là con của `out`. Dù vậy, Path comparison là một **lớp kiểm tra cú pháp**, không phải giải pháp duy nhất chống symlink.

## 9. Bước 5 — đặt giới hạn theo byte đã giải nén, không chỉ metadata

### Đừng tin `ZipEntry.getSize()`

Một số entry chưa biết kích thước hoặc có metadata không đáng tin, nên `ZipEntry.getSize()` có thể là `-1` hoặc không phản ánh chính xác dữ liệu cần giải nén. Nếu dùng metadata này để cấp phát mảng rồi đọc hết một lần, chương trình có thể bị **zip bomb**.

Ví dụ kiểm tra trong loop:

~~~java
if (n > limits.maxFileBytes() - size
        || n > limits.maxTotalBytes() - total) {
    throw new IOException("Uncompressed byte limit");
}

out.write(buffer, 0, n);
size += n;
total += n;
~~~

Đây là đoạn trích từ chương trình hoàn chỉnh. Hai biến `size`/`total` chỉ tăng sau khi kiểm tra và ghi chunk. Cách so `n > limit - used` tránh overflow do cộng số lớn trước rồi mới kiểm tra, với điều kiện limits dương và used chưa vượt limit.

**Quotas không chỉ là byte:**

- `maxEntries` chặn archive có hàng triệu directory/file entry rỗng.
- `maxName` giảm khả năng tên quá dài.
- `maxDepth` giới hạn tầng thư mục.
- `maxFileBytes` chặn một entry bung quá lớn.
- `maxTotalBytes` chặn nhiều entry nhỏ nhưng tổng lớn.
- Production còn cần **deadline, CPU quota, số inode/file được tạo, disk quota, số thư mục và tổng input compressed bytes**.

Không xem giới hạn tỉ lệ nén (uncompressed/compressed) là hàng rào duy nhất: metadata compressed size có thể không đáng tin hoặc tính toán không phù hợp khi streaming. Luôn kiểm đếm dữ liệu thật.

### Nếu vượt quota sau khi file đã được tạo?

Trong demo, file mới tạo qua `Files.newOutputStream(..., CREATE_NEW, WRITE)` có thể đã được ghi một phần trước khi một chunk vượt quota. `catch` sẽ cố **xóa file hiện tại**.

Nhưng nếu trước đó đã giải nén các entry khác thành công, chúng **có thể vẫn nằm trong thư mục output**. Toàn bộ `unpack` **không phải transaction nguyên tử**. Ở production, dùng staging directory do ứng dụng sở hữu, chỉ publish khi mọi entry đã xử lý và validate xong.

## 10. Thư mục đích và symbolic link: phạm vi an toàn thực tế

### 10.1. Vì sao bắt buộc tạo thư mục đích mới?

`Files.createDirectory(newOutput)` yêu cầu path chưa tồn tại, khác `Files.createDirectories` vốn có thể chấp nhận một cây có sẵn.

Trong bài:

~~~java
Path root = Files.createDirectory(newOutput).toRealPath();
~~~

Lợi ích:

- Không vô tình trộn file từ archive vào dữ liệu cũ.
- Không overwrite tên file có sẵn.
- Không có các subdirectory/symlink được đặt trước bên trong **output mới**, với giả định parent đáng tin cậy và không ai khác được ghi vào cây output.
- Dễ định nghĩa ownership và cleanup nếu extraction thất bại.

Điều kiện tiên quyết: **parent của `newOutput` phải đáng tin**, và actor không tin cậy không có quyền sửa cây output trong lúc giải nén. Demo tự tạo parent bằng `Files.createTempDirectory` để có môi trường luyện tập.

### 10.2. Kiểm tra symlink ở parent components

Khi tạo đường dẫn `root/docs/a.txt`, code `directories` kiểm tra từng component:

~~~java
if (Files.exists(at, LinkOption.NOFOLLOW_LINKS)) {
    if (!Files.isDirectory(at, LinkOption.NOFOLLOW_LINKS)) {
        throw new IOException("Non-directory or symlink parent");
    }
} else {
    Files.createDirectory(at);
}
~~~

Một symlink hiện hữu thường không thỏa `isDirectory(..., NOFOLLOW_LINKS)`, nên bị từ chối thay vì âm thầm theo link để ghi ra ngoài root. `CREATE_NEW` ở file cuối giúp tránh ghi đè file/symlink đã tồn tại.

### 10.3. TOCTOU chưa được giải quyết hoàn toàn

**TOCTOU (Time Of Check To Time Of Use)** là khoảng giữa lúc kiểm tra path và lúc mở/tạo file. Nếu attacker có quyền đổi directory sang symlink trong khoảng đó, kiểm tra Java trước đó có thể không còn đúng.

Do đó **`normalize()`, `NOFOLLOW_LINKS` và `CREATE_NEW` không tự tạo atomic filesystem sandbox**.

Khi threat model cho phép tiến trình khác sửa tree output, có thể cần:

- Tạo/staging dưới parent private với OS permission/ACL hạn chế.
- Dùng descriptor-relative operations, ví dụ `SecureDirectoryStream` nếu filesystem provider hỗ trợ, để giảm những race cụ thể.
- Dùng OS-level isolation/sandbox, container, quyền process tối thiểu.
- Cẩn thận với junction/reparse points trên Windows và cấu trúc path đặc thù provider.
- Không phục hồi symlink/hardlink từ metadata archive nếu chưa xác thực target theo chính sách rất rõ.

**Không mô tả demo là chống mọi Zip Slip/TOCTOU tuyệt đối**. Nó là nền tảng kiểm soát tên/path và quyền ghi trên môi trường đích mới đáng tin.

## 11. Tính di động: Windows, Unicode và tên có thể va chạm

`validateName` cố ý có một policy portable **cơ bản**, nhưng không xử lý mọi tên filesystem đặc biệt.

Các trường hợp cần cân nhắc khi nâng cấp:

1. **Case-insensitive collision:** `docs/A.txt` và `docs/a.txt` có thể cùng đích trên một số filesystem.
2. **Unicode normalization:** Hai tên trông như nhau có thể được chuẩn hóa về cùng đường dẫn.
3. **Windows reserved names:** `CON`, `PRN`, `AUX`, `NUL`, `COM1`... có quy tắc đặc biệt, kể cả một số tên có phần mở rộng.
4. **Trailing dot/space:** Tên `a.txt.` hay `a.txt ` có thể bị normalize/collision theo OS.
5. **Colon/NTFS ADS:** `a.txt:stream` bị policy ví dụ từ chối dấu `:`.
6. **Slash/backslash:** ZIP tên thường dùng `/`; policy không cho phép `\` để tránh hành vi khác nhau giữa OS.
7. **Symlink/junction:** Cần phát hiện cả khi tên hợp lệ về cú pháp.
8. **Tên quá dài tính theo byte:** Giới hạn `String.length()` trong demo là UTF-16 code units; OS còn có thể giới hạn tên/path theo **byte** hoặc representation riêng.

`CREATE_NEW` là một lớp phòng vệ thực tế trước collision của final path, nhưng hệ thống có nhu cầu cross-platform nghiêm ngặt nên có **validator tên filesystem riêng**, test trên các OS mục tiêu.

## 12. Thực hành mở rộng: thêm các negative tests

Bài lab đã có hai negative tests: traversal và byte bomb. Để luyện tập đầy đủ, hãy mở rộng `makeSingleZip` hoặc tạo helper tạo ZIP nhiều entry và thử thêm các trường hợp:

| Test case | Kết quả mong đợi |
|---|---|
| `/tmp/outside.txt` | Từ chối absolute entry |
| `C:/temp/out.txt` | Từ chối dấu colon/drive |
| `docs\..\outside.txt` | Từ chối backslash |
| `docs/../outside.txt` | Từ chối `..` |
| `docs//a.txt` | Từ chối component rỗng |
| Hai entry `same.txt` | Từ chối duplicate |
| `docs/a.txt` rồi `docs/a.txt/b.txt` | Từ chối vì parent là file, không phải directory |
| Hàng trăm entry rỗng | Chặn `maxEntries` |
| Entry quá nhiều tầng | Chặn `maxDepth` |
| Một entry nở lớn | Chặn `maxFileBytes` |
| Nhiều entry tổng nở lớn | Chặn `maxTotalBytes` |
| Trùng tên chỉ khác chữ hoa/thường | Tùy filesystem; không được overwrite |
| Symlink trong cây nguồn | Packer từ chối loại nguồn không hỗ trợ |
| File ZIP/đích thiếu quyền | Ném IOException; đóng stream và cleanup phù hợp |
| Archive bị truncate/CRC lỗi | Phải báo lỗi, không publish output dở |

Các assertions quan trọng không chỉ là “ném exception”:

- **Không file nào được tạo ngoài root**.
- Không file có sẵn bị overwrite.
- File vừa tạo dở bị xóa khi lỗi entry đang xử lý.
- Những file khác trước đó có thể còn lại: test phải **biết rõ giới hạn rollback**.
- Sau lỗi, tài nguyên đã mở qua TWR vẫn được đóng.
- Quota đếm được dựa trên byte **sau giải nén**.
- Với test ngắt việc pack giữa chừng, file ZIP mới tạo phải được cleanup.

### Dùng unit test assertion thay vì dựa vào log

Một JUnit 5 test có thể viết theo ý tưởng:

~~~java
@Test
void rejectsZipSlip() throws Exception {
    Path archive = createArchiveWithEntry(
            "../escape.txt", new byte[]{1});
    Path root = newTemporaryDestination();

    assertThrows(
            IOException.class,
            () -> ArchivePracticeDemo.unpack(
                    archive, root, TEST_LIMITS));

    assertFalse(Files.exists(
            root.getParent().resolve("escape.txt")));
}
~~~

Đây là **pseudocode JUnit 5**, không compile độc lập: `createArchiveWithEntry`, `newTemporaryDestination`, `TEST_LIMITS` là fixtures do test project định nghĩa. `root` phải **chưa tồn tại** khi truyền cho `unpack`. Chương trình đầy đủ mục 6 không yêu cầu JUnit và đã tạo testcase tương đương.

## 13. Khi nào cần ZipFile thay ZipInputStream?

Đối với file ZIP đã nằm trên disk, `ZipFile` có thể tra cứu entry theo tên:

~~~java
try (ZipFile zip = new ZipFile(
        archivePath.toFile(), StandardCharsets.UTF_8)) {

    ZipEntry entry = zip.getEntry("docs/a.txt");
    if (entry != null) {
        try (InputStream in = zip.getInputStream(entry)) {
            // Đọc nội dung entry này và giới hạn bytes như phần unpack.
        }
    }
}
~~~

Đây là mã minh họa, cần `Path archivePath` và các import. `ZipFile` có thể dùng central directory; còn `ZipInputStream` tiện cho upload/stream. **Không đổi sang ZipFile rồi bỏ kiểm tra đường dẫn, quota và ownership**.

Nếu archive mang **ZIP encryption/password**, Java `java.util.zip` không cung cấp một API tổng quát giải mã mọi biến thể ZIP có mật khẩu. Với ZIP features ngoài phạm vi JDK, cần thư viện được đánh giá phù hợp. Đừng coi exception “unsupported method” là tín hiệu để vô hiệu hóa path validation.

## 14. Cấu trúc production: staging rồi mới publish

Dùng hai giai đoạn:

~~~text
archive.zip
    |
    v
Private staging directory (new)
    |
    +-- từng entry: validate path, quota, no-follow, CREATE_NEW
    |
    +-- kiểm tra toàn archive / format / checksum / malware policy nếu cần
    |
    v
Publish sang destination cuối theo policy
    |
    v
Cleanup staging khi lỗi
~~~

Trong production, lý tưởng cần:

1. Đặt staging cùng filesystem với destination nếu muốn có khả năng rename atomic theo điều kiện filesystem cho phép.
2. Không cho người dùng khác ghi vào staging hoặc thay directory/symlink.
3. Giới hạn compressed input bytes, uncompressed bytes, entry count, depth, CPU time và số inode.
4. Không mở các entry dạng executable/script nhạy cảm nếu product không cần.
5. Kiểm tra tên filesystem reserved/collision trên OS thực tế.
6. Làm rõ merge/overwrite policy; demo chỉ hỗ trợ **new destination**.
7. Khi publish, kiểm tra hỗ trợ `StandardCopyOption.ATOMIC_MOVE` nếu muốn atomic move; có thể có `AtomicMoveNotSupportedException` và thao tác đổi tên không là transaction trên nhiều filesystem.
8. Cleanup cả staging khi fail giữa chừng và cleanup orphan staging sau crash.
9. Đối với nội dung nhạy cảm, CRC32 ZIP chỉ phát hiện hỏng ngẫu nhiên, **không phải chữ ký số chống giả mạo**.
10. Ghi log lỗi đủ phân biệt “invalid path”, “quota exceeded”, “archive corrupted”, “permission denied”, “I/O interrupted” mà không làm lộ path hệ thống ngoài mong muốn.

**Đừng trả về thành công chỉ vì `unpack` đã tạo vài file.** Thành công phải nghĩa là mọi entry được đọc, validate, trích xuất, các stream được đóng thành công và output được publish theo hợp đồng.

## 15. Các sai lầm dễ mắc

1. **Ghi thẳng `entry.getName()` vào thư mục output mà không kiểm tra.** Dẫn tới Zip Slip.
2. **Chỉ dùng `String.startsWith` để kiểm tra containment.** Có thể nhầm đường dẫn có cùng tiền tố chuỗi.
3. **Tin `Path.normalize()` giải quyết symlink.** Sai: normalize chỉ xử lý cú pháp.
4. **Tin `NOFOLLOW_LINKS` loại được mọi race.** Sai nếu attacker có thể sửa cây file đồng thời.
5. **Dùng `CREATE`/`TRUNCATE_EXISTING` với entry không tin cậy.** Có thể ghi đè file cũ; dùng `CREATE_NEW` khi không cho overwrite.
6. **Giải nén vào directory đã có nội dung mà không có merge policy.** Dễ gây collision/overwrite.
7. **Bỏ qua directory entries.** Mất thư mục rỗng.
8. **Tin mọi ZIP đều có directory entry `docs/` trước `docs/a.txt`.** Không được bảo đảm; tự tạo parent sau khi validate.
9. **Không giới hạn số entry.** Archive hàng triệu file rỗng vẫn phá hệ thống dù tổng bytes thấp.
10. **Tin `entry.getSize()` để cấp phát mảng.** Có thể -1 hoặc không đáng tin.
11. **Dùng `zip.readAllBytes()` cho upload không tin cậy.** Dễ hết heap khi zip bomb.
12. **Chỉ giới hạn dung lượng ZIP nén.** Một file vài KiB có thể bung rất lớn.
13. **Quên `ZipOutputStream.close()`.** Central directory có thể chưa hoàn tất.
14. **Hiểu `ZipInputStream.read() == -1` là hết archive.** Đó là hết entry hiện tại.
15. **Để output ZIP nằm trong source tree đang walk.** Dễ có input biến động/tự chứa ZIP.
16. **Follow symlink nguồn không kiểm soát.** Có thể pack tài liệu ngoài thư mục đã định.
17. **Dùng dấu backslash trong entry theo cách tự tiện.** Hành vi khác nhau giữa hệ điều hành.
18. **Không kiểm tra duplicate/case-collision.** Có thể mất hoặc ghi đè file.
19. **Cho rằng IOException tự rollback mọi file đã tạo trước đó.** Sai: cần staging/cleanup.
20. **Cho rằng CRC32 chứng minh archive đáng tin.** Sai: checksum không có xác thực mật mã.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao packer phải viết directory entries như `empty/`?

**Đáp án:** Để giữ thư mục rỗng. Nếu ZIP chỉ có file entries, một thư mục không có file con có thể biến mất khi giải nén.

**Câu 2.** Vì sao chỉ kiểm tra `zipEntry.getSize() <= maxBytes` không đủ chống zip bomb?

**Đáp án:** Metadata có thể thiếu/không đáng tin, và tổng nhiều entry vẫn lớn. Cần kiểm đếm byte đã giải nén thật trong mỗi vòng `read` trước khi ghi.

**Câu 3.** Nếu ZIP chứa `docs/a.txt` nhưng không có `docs/`, extractor có tạo được không?

**Đáp án:** Có. Sau khi tên được validate và nằm trong root, tạo các thư mục cha an toàn rồi tạo file mới.

**Câu 4.** Vì sao `Path.startsWith(root)` tốt hơn `String.startsWith(root.toString())`?

**Đáp án:** Nó so sánh theo thành phần Path, tránh nhầm `/safe/output2` là con của `/safe/output`.

**Câu 5.** `Files.newOutputStream(..., CREATE_NEW)` giải quyết được vấn đề gì?

**Đáp án:** Ngăn ghi đè/truncate một file hoặc symlink có sẵn ở path cuối; không tự ngăn attacker đổi directory cha khi có race.

**Câu 6.** Vì sao thử `../escape.txt` phải kiểm tra cả exception và file thực tế?

**Đáp án:** Có exception không chứng minh file ngoài root chưa từng được tạo. Assertion cần xác nhận không có file vi phạm sau thao tác thất bại.

**Câu 7.** Nếu entry thứ mười vượt quota nhưng chín entry trước hợp lệ đã được giải nén, các file trước có tự biến mất không?

**Đáp án:** Không. Demo chỉ cố dọn file entry đang xử lý; cần staging + cleanup/publish riêng để đạt quy trình trọn gói.

**Câu 8.** Vì sao Java `ZipInputStream` không nên được dùng với một luồng GZIP đơn `.gz`?

**Đáp án:** ZIP archive có `ZipEntry` và cấu trúc ZIP, còn GZIP là định dạng nén stream khác; dù cả hai có thể dùng DEFLATE, header/container không giống nhau.

**Câu 9.** Chương trình được chạy trên Linux nhưng archive có tên `C:/tmp/a.txt`. Vì sao chính sách của bài vẫn từ chối?

**Đáp án:** Để giữ tính portable và tránh tên chuyển nghĩa thành đường dẫn drive khi archive được giải nén trên Windows hoặc qua tool khác.

### Tài liệu Java 17 chính thức

- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [Files.walkFileTree và Files.newOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Path.resolve, normalize, startsWith](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [LinkOption.NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
- [StandardOpenOption.CREATE_NEW](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
