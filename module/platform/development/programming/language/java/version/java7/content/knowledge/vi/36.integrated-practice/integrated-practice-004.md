# Thực hành tổng hợp: viết công cụ tìm kiếm, sao chép và thống kê cây tệp bằng Java

## 1. Mục tiêu và sản phẩm cuối bài

Bạn sẽ xây dựng **một chương trình dòng lệnh Java 17+** thao tác trên một cây thư mục bằng API **NIO.2** trong `java.nio.file`. Chương trình nhận ba lệnh:

```text
java TreeTool find  <thu-muc-goc> <glob-ten-tep>
java TreeTool stats <thu-muc-goc>
java TreeTool copy  <thu-muc-nguon> <thu-muc-dich-moi>
```

- **`find`:** tìm **tệp thông thường** trong cây thư mục theo mẫu tên (glob), in đường dẫn tương đối và số tệp tìm được.
- **`stats`:** đếm thư mục, tệp thường, symbolic link, các loại entry khác và tính **tổng số byte logic** của những tệp thường.
- **`copy`:** sao chép cấu trúc thư mục và nội dung tệp vào **một thư mục đích chưa tồn tại**, không tự ghi đè. Chương trình không đi theo symbolic link và **dừng nếu gặp link/entry đặc biệt** để người dùng biết bản sao chưa đầy đủ.

Bài này rèn luyện cách kết hợp `Path`, `Files`, `SimpleFileVisitor`, `BasicFileAttributes`, `FileVisitResult`, `PathMatcher` và xử lý `IOException`. Các API này được giới thiệu từ Java 7 nhưng **vẫn đang được hỗ trợ và dùng phổ biến trong Java 17+**. Ví dụ chạy bằng Java 17+ để có cú pháp `switch` hiện đại; không dùng `java.io.File` để tự viết đệ quy thủ công.

Sau bài học bạn sẽ hiểu **vì sao phải quyết định chính sách theo dõi symbolic link, đường dẫn đích, lỗi từng entry và tác động của việc cây tệp thay đổi trong lúc duyệt**.

## 2. Tư duy thiết kế trước khi viết code

Một *cây tệp* có thư mục gốc, các thư mục con, tệp và có thể có symbolic link hoặc entry đặc biệt.

```text
demo-tree/
├── docs/
│   └── readme.txt       (6 byte)
└── notes.txt            (5 byte)

Kết quả thống kê:
- thư mục: 2  (demo-tree và docs)
- tệp thường: 2
- symbolic link: 0
- entry khác: 0
- dung lượng tệp logic: 11 byte
```

Chương trình cần đặt ra chính sách nhất quán:

| Quyết định | Phương án dùng trong bài | Lý do |
| --- | --- | --- |
| Duyệt con | `Files.walkFileTree(root, visitor)` theo chiều sâu | Có callback trước/sau thư mục, tự đóng luồng duyệt thư mục và báo lỗi I/O |
| Duyệt symbolic link | **Không bật** `FOLLOW_LINKS` | Không tự đi ra ngoài cây nguồn; tránh vòng lặp link |
| Tìm kiếm | Chỉ tệp thường, glob khớp với **tên tệp cuối cùng** | Dễ dùng: `"*.txt"` hoặc `"App?.java"` |
| Sao chép | Chỉ file thường và thư mục, báo lỗi khi gặp link/entry đặc biệt | Không vô tình biến link thành bản sao ngoài phạm vi hoặc âm thầm bỏ sót dữ liệu |
| Ghi đè | Cấm đích tồn tại, không dùng `REPLACE_EXISTING` | Giảm nguy cơ phá hủy dữ liệu đang có |
| Đích bên trong nguồn | Cấm | Tránh tự sao chép lặp vào chính cây đang duyệt |
| Quyền truy cập/lỗi | Dừng và báo lỗi cụ thể | Không báo “thành công” nếu một nhánh chưa được đọc |
| Metadata | Chỉ sao chép **nội dung tệp**, không cam kết giữ ACL, owner, timestamp | Chính sách rõ ràng, nhất quán giữa các hệ thống |
| Thống kê kích thước | Cộng `BasicFileAttributes.size()` của file thường, dùng `long` | Đo kích thước logic, không suy ra dung lượng vật lý đĩa |

**Lưu ý về tính nguyên tử:** công cụ thực hành không tạo snapshot nhất quán và không có rollback. Nếu file bị sửa lúc đang chạy hoặc sao chép gặp lỗi giữa chừng, kết quả có thể không đại diện cho một thời điểm duy nhất và thư mục đích có thể chứa bản sao dở dang. Phần mở rộng cho production sẽ giải quyết riêng.

## 3. Các API NIO.2 cần nắm

### `Path` và `Files`

- `Path.of("data", "docs")` tạo một đường dẫn theo quy tắc của hệ điều hành đang chạy.
- `toAbsolutePath().normalize()` biến đường dẫn thành tuyệt đối và loại các đoạn từ vựng như `.`, `..`; thao tác này **không tự kiểm chứng symbolic link**.
- `toRealPath()` yêu cầu đường dẫn tồn tại, kiểm tra thực tế trên filesystem và mặc định giải quyết symbolic link; hữu ích để xác định thư mục nguồn và phần cha đích.
- `root.relativize(file)` tạo đường dẫn tương đối từ root đến file; `destination.resolve(relative)` ánh xạ sang cây đích.
- `Files.createDirectory(path)` tạo **một** thư mục mới và lỗi nếu đã tồn tại. `Files.createDirectories(path)` tạo nhiều thư mục cha nếu cần; bài chọn `createDirectory` khi sao chép để phát hiện tình huống trùng tên.
- `Files.copy(source, target, options...)` sao chép **một entry**; nếu truyền đường dẫn thư mục, lệnh **không tự sao chép đệ quy toàn bộ các con**.
- `Files.isDirectory(path)` hoặc `Files.exists(path)` có thể kiểm tra nhanh, nhưng kết quả kiểm tra có thể hết đúng ngay khi filesystem bị tiến trình khác sửa (*time-of-check to time-of-use*, TOCTOU).

### `FileVisitor` và `SimpleFileVisitor`

`Files.walkFileTree(root, visitor)` duyệt cây theo chiều sâu, mặc định **không theo symbolic link**, và gọi các callback:

| Callback | Khi nào được gọi | Ứng dụng trong bài |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi thăm con của thư mục | Đếm thư mục; tạo thư mục tương ứng ở đích |
| `visitFile(file, attrs)` | Khi gặp entry không được duyệt như thư mục | So glob, thống kê size/link, hoặc copy file |
| `visitFileFailed(file, exc)` | Không đọc được thuộc tính hoặc không mở được entry | Báo lỗi kèm đường dẫn |
| `postVisitDirectory(dir, exc)` | Sau khi duyệt xong các con hoặc khi phát sinh lỗi duyệt | Kiểm tra lỗi của lượt duyệt thư mục |

**Kết quả callback:** `CONTINUE` tiếp tục; `SKIP_SUBTREE` bỏ các con của một thư mục trong `preVisitDirectory`; `SKIP_SIBLINGS` bỏ các entry anh em còn lại; `TERMINATE` dừng hẳn. Callback **không được trả `null`**. Trong bài, tất cả lượt thành công đều trả `CONTINUE`.

**Tại sao dùng `SimpleFileVisitor<Path>`?** Đây là lớp cơ sở đã cài các callback mặc định phù hợp, giúp chỉ override những điểm cần thiết. Thay vì tự giữ một `Stream<Path>`, nó cho phép tạo thư mục đích đúng lúc trước khi thăm các tệp bên trong.

### `BasicFileAttributes`

Trong callback, `attrs` cho biết:

- `attrs.isDirectory()`, `attrs.isRegularFile()`, `attrs.isSymbolicLink()`, `attrs.isOther()`;
- `attrs.size()`: độ dài logic báo bởi filesystem cho file;
- `attrs.lastModifiedTime()`, `attrs.creationTime()`, `attrs.fileKey()` nếu cần mở rộng.

Dùng dữ liệu thuộc tính **đã được cung cấp cho lần thăm đó**, tránh gọi `Files.size()` riêng cho từng tệp không cần thiết. Nhưng đó vẫn chỉ là thông tin tại một thời điểm; file có thể thay đổi giữa lúc đọc thuộc tính và copy.

### `PathMatcher` và glob

`FileSystems.getDefault().getPathMatcher("glob:" + pattern)` tạo bộ so khớp đường dẫn theo cú pháp glob trên filesystem provider hiện tại. Ví dụ `*.txt`, `Main?.java` và `report-*.csv`. Trong code ta áp bộ so khớp lên `file.getFileName()`: nó kiểm tra **tên file**, không kiểm tra toàn bộ đường dẫn con, vì vậy `**/*.txt` **không phải** lựa chọn thích hợp cho phiên bản công cụ này.

Độ nhạy chữ hoa/thường, dấu phân cách đường dẫn và một số chi tiết glob phụ thuộc filesystem/provider; không mặc định Windows/Linux có cùng hành vi. Khi gõ trong shell, nên **đặt glob trong dấu nháy** để shell không tự mở rộng danh sách file trước khi Java xử lý.

## 4. Thiết kế giao diện lệnh và kết quả

Ba lệnh có ý nghĩa rõ ràng:

```bash
java TreeTool find demo-tree "*.txt"
java TreeTool stats demo-tree
java TreeTool copy demo-tree copied-tree
```

**`find`** in từng đường dẫn tương đối của tệp tìm thấy, rồi tổng số kết quả. Thứ tự file phụ thuộc thứ tự trả về từ filesystem, **không được bảo đảm sắp xếp**; các chương trình dùng output làm dữ liệu nên parse theo quy ước riêng, thay vì giả định thứ tự.

**`stats`** in các trường theo thứ tự cố định: `Directories`, `Files`, `Symlinks`, `Other`, `Bytes`. Số directory **tính cả root**. Số `Bytes` chỉ gồm file thường, không bao gồm overhead thư mục, allocated blocks, link hoặc metadata.

**`copy`** đòi thư mục cha của đích đã tồn tại, còn **chính thư mục đích chưa tồn tại**. Ví dụ `copied-tree` chưa tồn tại nhưng thư mục làm việc hiện tại tồn tại. Sao chép vào `demo-tree/backup` bị từ chối vì đích nằm bên trong nguồn.

Mỗi lần lỗi, chương trình in `Error: ...` sang stderr và trả exit code 1. Với tham số thiếu, chương trình cũng báo cách dùng. Một file tree có lỗi permission hoặc chứa symbolic link sẽ khiến `copy` báo thất bại thay vì âm thầm quảng cáo là sao chép đủ.

## 5. Chương trình Java 17+ hoàn chỉnh: `TreeTool.java`

Lưu **toàn bộ** mã sau trong file có tên chính xác **`TreeTool.java`**. Đây là chương trình độc lập, biên dịch được trên Java 17+ và sử dụng các API NIO.2 còn hiện hành.

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.PathMatcher;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public final class TreeTool {
    private TreeTool() { }

    public static void main(String[] args) {
        if (args.length == 0) {
            usage();
            return;
        }

        try {
            switch (args[0]) {
                case "find" -> {
                    requireCount(args, 3);
                    find(existingRoot(args[1]), args[2]);
                }
                case "stats" -> {
                    requireCount(args, 2);
                    stats(existingRoot(args[1]));
                }
                case "copy" -> {
                    requireCount(args, 3);
                    copy(existingRoot(args[1]), args[2]);
                }
                default -> throw new IllegalArgumentException(
                        "Unknown command: " + args[0]);
            }
        } catch (IOException | IllegalArgumentException ex) {
            System.err.println("Error: " + ex.getMessage());
            usage();
            System.exit(1);
        }
    }

    private static void usage() {
        System.err.println(
                "Usage: java TreeTool find <root> <glob>");
        System.err.println(
                "       java TreeTool stats <root>");
        System.err.println(
                "       java TreeTool copy <source> <new-destination>");
    }

    private static void requireCount(String[] args, int expected) {
        if (args.length != expected) {
            throw new IllegalArgumentException(
                    "Expected " + (expected - 1)
                    + " argument(s) after " + args[0]);
        }
    }

    private static Path existingRoot(String raw) throws IOException {
        Path root = Path.of(raw).toRealPath();
        if (!Files.isDirectory(root)) {
            throw new IOException("Not a directory: " + root);
        }
        return root;
    }

    private static void find(Path root, String glob)
            throws IOException {
        PathMatcher matcher = FileSystems.getDefault()
                .getPathMatcher("glob:" + glob);
        long[] count = {0};

        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) {
                if (attrs.isRegularFile()
                        && matcher.matches(file.getFileName())) {
                    System.out.println(root.relativize(file));
                    count[0]++;
                }
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc) throws IOException {
                throw new IOException(
                        "Cannot visit: " + file, exc);
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException exc) throws IOException {
                if (exc != null) {
                    throw exc;
                }
                return FileVisitResult.CONTINUE;
            }
        });

        System.out.println("Matched files: " + count[0]);
    }

    private static final class StatsVisitor
            extends SimpleFileVisitor<Path> {
        private long directories;
        private long files;
        private long symlinks;
        private long other;
        private long bytes;

        @Override
        public FileVisitResult preVisitDirectory(
                Path dir, BasicFileAttributes attrs) {
            directories++;
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            if (attrs.isSymbolicLink()) {
                symlinks++;
            } else if (attrs.isRegularFile()) {
                files++;
                bytes = Math.addExact(bytes, attrs.size());
            } else {
                other++;
            }
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFileFailed(
                Path file, IOException exc) throws IOException {
            throw new IOException("Cannot visit: " + file, exc);
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }

        private void print() {
            System.out.println("Directories: " + directories);
            System.out.println("Files: " + files);
            System.out.println("Symlinks: " + symlinks);
            System.out.println("Other: " + other);
            System.out.println("Bytes: " + bytes);
        }
    }

    private static void stats(Path root) throws IOException {
        StatsVisitor visitor = new StatsVisitor();
        Files.walkFileTree(root, visitor);
        visitor.print();
    }

    private static void copy(Path source, String destinationName)
            throws IOException {
        Path destination = Path.of(destinationName)
                .toAbsolutePath().normalize();
        Path parent = destination.getParent();

        if (parent == null || !Files.isDirectory(parent)) {
            throw new IOException(
                    "Destination parent must already exist: " + parent);
        }

        // Giai quyet link o thu muc cha de phat hien dich
        // thuc te nam trong chinh cay nguon.
        Path realDestination = parent.toRealPath()
                .resolve(destination.getFileName());

        if (realDestination.startsWith(source)) {
            throw new IOException(
                    "Destination must be outside source tree");
        }
        if (Files.exists(destination, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException(
                    "Destination already exists: " + destination);
        }

        // CREATE_NEW theo nghia thu muc: neu da co thi bao loi.
        Files.createDirectory(destination);
        long[] copied = {0};

        try {
            Files.walkFileTree(source, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs)
                        throws IOException {
                    Path relative = source.relativize(dir);
                    if (!relative.toString().isEmpty()) {
                        Files.createDirectory(
                                destination.resolve(relative));
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    if (attrs.isSymbolicLink()) {
                        throw new IOException(
                                "Symbolic link not copied: " + file);
                    }
                    if (!attrs.isRegularFile()) {
                        throw new IOException(
                                "Unsupported entry type: " + file);
                    }

                    Path relative = source.relativize(file);
                    Path target = destination.resolve(relative);

                    // Khong REPLACE_EXISTING va khong dereference
                    // symbolic link cua source trong lenh copy.
                    Files.copy(file, target, LinkOption.NOFOLLOW_LINKS);
                    copied[0]++;
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(
                        Path file, IOException exc) throws IOException {
                    throw new IOException(
                            "Cannot visit: " + file, exc);
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException exc) {
            throw new IOException(
                    "Copy failed; partial destination remains at "
                    + destination + ": " + exc.getMessage(), exc);
        }

        System.out.println("Copied files: " + copied[0]);
    }
}
```

Biên dịch:

```bash
javac -encoding UTF-8 TreeTool.java
```

Cách chạy tổng quát:

```bash
java TreeTool find "path/to/source" "*.java"
java TreeTool stats "path/to/source"
java TreeTool copy "path/to/source" "path/to/new-copy"
```

Thay các đường dẫn bằng đường dẫn thực tế của bạn. Trong PowerShell, Command Prompt hay shell Unix, cách viết path và ký tự phân cách có thể khác nhau; dùng dấu nháy khi path có khoảng trắng. Đây là ví dụ CLI: không cần dependency bên ngoài Java SE và không sử dụng thư viện đã cũ.

### Giải thích từng phần của chương trình

**(1) `existingRoot(...)` chuẩn hóa một điểm bắt đầu có thật.** `toRealPath()` xử lý phần path tồn tại, giải quyết symbolic link trên đường nguồn và báo lỗi nếu root không tồn tại. Sau đó `Files.isDirectory(...)` xác nhận đúng loại entry. Một symlink được chỉ định **ngay tại root** sẽ được giải quyết bởi `toRealPath()`; trong cây con, traversal mặc định không theo symlink.

**(2) `find(...)` duyệt một lần rồi in kết quả.** `PathMatcher` được tạo trước traversal, chỉ thử những entry có `attrs.isRegularFile()`. `root.relativize(file)` giữ tên và cấu trúc tương đối của file; không in path tuyệt đối khi không cần. Chương trình không lưu tất cả kết quả vào `List` nên thường không tốn heap tỷ lệ với tổng số tệp.

**(3) `StatsVisitor` gom số liệu bằng `long`.** Dùng `Math.addExact` để phát hiện tràn số khi cộng byte; thông thường dữ liệu thực tế không đến mức tràn `long` nhưng đây là cách tránh có tổng âm im lặng. `Symlinks` được đếm riêng, không lấy kích thước dữ liệu mà link trỏ tới. Thư mục được đếm trong `preVisitDirectory`, bao gồm root.

**(4) `copy(...)` dựa trên đường dẫn tương đối.** Trước khi copy, chương trình kiểm tra thư mục cha đích, chuẩn hóa vị trí đích thực tế và chặn đích nằm trong nguồn. Nó không cho ghi đè và chỉ tạo một root đích mới. Mỗi khi gặp directory con, `preVisitDirectory` tạo directory tương ứng. Khi gặp file thường, `visitFile` thực hiện `Files.copy` vào đúng vị trí tương đối.

**(5) Link và entry đặc biệt.** `walkFileTree` mặc định không theo symbolic link; vì vậy `visitFile` nhận link như một entry để quyết định xử lý. `find` bỏ qua link vì chỉ tìm file thường; `stats` đếm link; `copy` **báo lỗi** nếu xuất hiện link hoặc entry đặc biệt. Không có nội dung link nào được tự sao chép hoặc duyệt ra ngoài nguồn theo logic bình thường.

**(6) Lỗi được đẩy lên thay vì che giấu.** `visitFileFailed` và `postVisitDirectory` ném `IOException` khi không thể đọc một nhánh. Nếu copy lỗi sau khi đã tạo một vài file, thông điệp nêu rõ **partial destination**. Chương trình **không xóa tự động** dữ liệu đích khi lỗi; hãy kiểm tra nó trước khi xóa thủ công.

**(7) Hạn chế của bản thực hành.** Không giữ POSIX permissions, Windows ACL, owner, timestamp hay hard-link identity; không bảo đảm atomic snapshot; không tránh hoàn toàn symlink-race trong một filesystem bị bên thứ ba sửa ác ý; không hỗ trợ incremental sync, resume, exclude rules, checksum hay retry.

## 6. Tạo fixture để chạy thử và kiểm tra stdout

Để có đầu vào giống nhau trên Windows/Linux/macOS, tạo chương trình Java nhỏ **`MakeDemoTree.java`**. Chạy trong thư mục làm việc **chưa có** `demo-tree`; mỗi lệnh chỉ chạy một lần trừ khi bạn chủ động dùng thư mục làm việc mới.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MakeDemoTree {
    public static void main(String[] args) throws Exception {
        Path root = Path.of("demo-tree");
        Files.createDirectory(root);
        Files.createDirectory(root.resolve("docs"));

        Files.writeString(
                root.resolve("docs").resolve("readme.txt"),
                "hello\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);
        Files.writeString(
                root.resolve("notes.txt"),
                "java\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);

        System.out.println("Demo tree ready");
    }
}
```

Biên dịch và khởi tạo:

```bash
javac -encoding UTF-8 TreeTool.java MakeDemoTree.java
java MakeDemoTree
```

Stdout chính xác nếu tạo fixture thành công:

```text
Demo tree ready
```

Đầu vào có **hai file UTF-8 chỉ chứa ASCII**: `hello\n` là 6 byte và `java\n` là 5 byte. Đây là lý do tổng kích thước logic chính xác là 11 byte. Nếu thư mục `demo-tree` đã tồn tại, `Files.createDirectory` sẽ lỗi; điều này có chủ đích để không ghi đè dữ liệu cũ.

### 6.1. Kiểm thử tìm kiếm

```bash
java TreeTool find demo-tree "*.txt"
```

Output chứa **hai dòng đường dẫn tương đối** và một dòng tổng:

```text
docs/readme.txt
notes.txt
Matched files: 2
```

Thứ tự hai đường dẫn **không được bảo đảm**, và Windows có thể in `docs\readme.txt` thay vì `docs/readme.txt`. Dòng tổng `Matched files: 2` luôn chính xác cho fixture đã tạo và không bị sửa.

Thử không khớp:

```bash
java TreeTool find demo-tree "*.csv"
```

Stdout chính xác:

```text
Matched files: 0
```

### 6.2. Kiểm thử thống kê

```bash
java TreeTool stats demo-tree
```

Stdout chính xác:

```text
Directories: 2
Files: 2
Symlinks: 0
Other: 0
Bytes: 11
```

**Giải thích:** root được tính là một thư mục, `docs` là thư mục thứ hai; hai file thường có 6 và 5 byte. Kết quả đo **kích thước logic**, không bao gồm dung lượng dành cho directory entries và metadata.

### 6.3. Kiểm thử sao chép và đối chiếu kết quả

```bash
java TreeTool copy demo-tree copied-tree
java TreeTool stats copied-tree
```

Khi `copied-tree` chưa tồn tại và không có lỗi I/O, stdout:

```text
Copied files: 2
Directories: 2
Files: 2
Symlinks: 0
Other: 0
Bytes: 11
```

Nếu chạy lại lệnh `copy` với cùng đích, chương trình báo `Destination already exists` và trả mã lỗi; nó **không** thay nội dung đích đã tạo. Bạn có thể mở `copied-tree/docs/readme.txt` và `copied-tree/notes.txt` để so sánh nội dung với nguồn.

**Một kiểm chứng mạnh hơn:** dùng `Files.mismatch(source, target)` trong một công cụ kiểm tra riêng để so sánh nội dung byte của từng cặp file. Giá trị `-1` nghĩa là nội dung hai file khớp. `Files.mismatch` có từ Java 12 nên dùng được trên Java 17+. Việc số file và tổng byte bằng nhau **không tự chứng minh từng byte giống nhau**.

## 7. Phân tích độ phức tạp và sử dụng bộ nhớ

Gọi `N` là tổng số entries được duyệt, `D` là độ sâu lớn nhất của cây, `M` là số file khớp tìm kiếm và `B` là tổng số byte nội dung file cần sao chép.

| Lệnh | Thời gian xấp xỉ | Bộ nhớ phụ trợ | Điều ảnh hưởng nhiều |
| --- | --- | --- | --- |
| `find` | `O(N)` cộng chi phí so khớp từng tên | Khoảng `O(D)` để duyệt, không lưu `M` kết quả | Độ trễ filesystem, mạng, glob matching |
| `stats` | `O(N)` | Khoảng `O(D)` | Đọc metadata, quyền truy cập, số entries |
| `copy` | `O(N + B)` theo góc nhìn duyệt và truyền byte | Không lưu toàn bộ dữ liệu file trong heap ở API copy thông thường | I/O, tốc độ đĩa/mạng, dung lượng đích |

Đây là **ước lượng mô hình**, không phải cam kết chính xác về bộ nhớ nội bộ của từng filesystem provider hoặc bộ đệm native. Độ phức tạp quan trọng nhất: chương trình **không gọi `Files.readAllBytes` rồi giữ cả cây trong RAM**; `walkFileTree` duyệt lần lượt và `Files.copy` sao chép file theo cơ chế của provider.

Với hàng triệu entries, thời gian đọc metadata, số lần mở directory, permission checks và đường truyền mạng có thể trội hơn thời gian xử lý Java. Với file lớn, `Files.copy` có thể tận dụng cơ chế tối ưu của hệ điều hành/provider, nhưng không nên giả định zero-copy trong mọi môi trường.

## 8. Các tình huống lỗi quan trọng cần thử

| Tình huống | Kết quả mong muốn của phiên bản này | Vì sao |
| --- | --- | --- |
| Root không tồn tại | Lỗi từ `toRealPath()` | Không giả định cây rỗng |
| Root là file thường | Báo `Not a directory` | Ba lệnh này yêu cầu root dạng thư mục |
| Glob sai cú pháp | Báo `IllegalArgumentException`/glob error | Pattern được kiểm tra khi tạo `PathMatcher` |
| Không đọc được một directory | `visitFileFailed`/`postVisitDirectory` báo lỗi | Tránh số liệu thiếu nhưng vẫn báo hoàn tất |
| Đích đã tồn tại | Từ chối ngay trước khi tạo | Không ghi đè dữ liệu |
| Đích nằm dưới nguồn | Từ chối khi kiểm tra path đã giải quyết cha đích | Tránh copy vào chính cây nguồn |
| Đích có cha chưa tồn tại | Từ chối | Phiên bản này yêu cầu parent tồn tại |
| Nguồn có symbolic link trong cây | `find` bỏ qua, `stats` đếm, `copy` báo lỗi | Chính sách riêng cho từng lệnh, không đi theo link |
| Copy bị hết dung lượng/quyền | Báo lỗi, đích có thể một phần | Không được coi bản sao là hoàn chỉnh |
| File bị xóa giữa khi thăm và copy | Báo lỗi I/O | Cây filesystem không được snapshot |
| Tên trùng sau chuyển sang filesystem khác | Có thể báo `FileAlreadyExistsException` | Khác biệt case sensitivity/normalization giữa filesystem |
| Chạy trên thư mục chứa nhiều mount points | Có thể đi vào cây trên filesystem khác | `walkFileTree` mặc định không giới hạn ở một `FileStore` |

### Không theo symbolic link là một quyết định chủ động

Mặc định `Files.walkFileTree(root, visitor)` **không đi vào các thư mục tượng trưng trỏ tới nơi khác**. Điều này tránh rất nhiều vấn đề như đi lặp vòng hoặc kéo thêm dữ liệu ngoài phạm vi người dùng định sao chép.

Nếu cần theo link, có overload nhận `EnumSet.of(FileVisitOption.FOLLOW_LINKS)`. Khi đó cần thiết kế lại chính sách về vòng lặp và đường dẫn đích. Java có thể nhận diện một số chu trình và báo `FileSystemLoopException`, nhưng việc **cho phép theo link không tự biến thao tác sao chép thành an toàn**. Không tự bật cờ này trong công cụ tổng quát.

### Vì sao copy nên từ chối link thay vì im lặng bỏ qua?

Một backup âm thầm bỏ qua các symbolic link có thể trông như đã sao chép đủ nhưng thực tế thiếu entry. Ngược lại, sao chép **nội dung đích của link** có thể vô tình lôi cả thư mục nằm ngoài cây nguồn. Trong bản thực hành, quyết định an toàn và dễ kiểm chứng là **báo lỗi** để người dùng xác định chính sách thích hợp. Hệ thống backup thật có thể hỗ trợ sao chép link như chính link đó, hoặc ghi link metadata vào manifest.

### Vì sao không dùng `REPLACE_EXISTING`?

Nếu một nguồn chứa nhiều file và người dùng vô tình nhập nhầm đích là thư mục dữ liệu quan trọng, `REPLACE_EXISTING` có thể phá hủy dữ liệu. Bài học dùng `createDirectory` cho root đích và `Files.copy` không có `REPLACE_EXISTING`, nhờ đó việc trùng đích là lỗi có thể phát hiện. Đây là **bảo vệ ở mức thao tác thông thường**, không đủ để chống race hoặc filesystem bị sửa ác ý.

## 9. Những giới hạn bảo mật và tính đúng đắn cần biết

### 9.1. TOCTOU và symbolic-link races

Tổ hợp `toRealPath`, `normalize`, `exists` và `startsWith` kiểm tra trạng thái **tại thời điểm gọi**. Tiến trình khác vẫn có thể thay symbolic link, đổi directory hoặc chuyển file giữa lúc kiểm tra và sử dụng. Khi chạy trên cây chứa dữ liệu không tin cậy hoặc do attacker có quyền sửa đồng thời, bản ví dụ **chưa đủ mạnh để bảo đảm confinement tuyệt đối**.

Để thiết kế công cụ production trong môi trường hostile:

- cân nhắc `SecureDirectoryStream` khi filesystem provider có hỗ trợ để thao tác tương đối với directory handle, hạn chế một số race;
- dùng vùng nguồn/đích do ứng dụng kiểm soát quyền ghi và cô lập khỏi actor không đáng tin;
- kiểm tra identity/metadata khi thích hợp; tránh chỉ tin string path;
- xác minh khả năng support và hành vi symlink của filesystem cụ thể;
- triển khai theo nguyên tắc quyền tối thiểu.

Không tuyên bố “đã ngăn mọi kiểu path traversal” chỉ vì thấy `normalize()` và `startsWith()`.

### 9.2. Đầu ra có thể không nhất quán nếu cây đang thay đổi

Giả sử ứng dụng khác ghi vào `orders.log` trong lúc `copy` đang chạy. `stats` có thể đọc size trước khi file lớn lên; `Files.copy` có thể sao chép một trạng thái khác. Ngay cả khi copy không lỗi, tổng byte từ một lần stats trước đó có thể khác bản copy sau đó.

Đối với backup nghiêm túc, dùng snapshot filesystem/storage khi có, hoặc dừng nguồn ghi trong cửa sổ nhất quán. Cân nhắc manifest chứa path, length, hash, thời gian, trạng thái thao tác để đối chiếu sau. Giữa các hệ thống, timestamp không phải bằng chứng nội dung khớp.

### 9.3. Sao chép dở và atomic publish

Ví dụ tạo thư mục đích ngay trước khi copy. Nếu ổ đầy sau 80%, chương trình để lại **partial destination** và báo lỗi. Công cụ sao chép thực tế thường:

1. Tạo thư mục staging với tên mới ngoài vùng nguồn.
2. Sao chép vào staging và thu thập các lỗi.
3. Xác minh số file, bytes, hash hoặc manifest theo yêu cầu.
4. Công bố staging thành đích chính thức bằng cách đổi tên/move phù hợp, nếu filesystem cho phép.
5. Quản lý cleanup/retry một cách tường minh, tránh xóa nhầm dữ liệu người dùng.

**`StandardCopyOption.ATOMIC_MOVE` chỉ áp dụng cho thao tác move khi filesystem hỗ trợ**, không biến cả chuỗi copy dài thành một transaction. Nếu không hỗ trợ, có thể nhận `AtomicMoveNotSupportedException`; chương trình production phải thiết kế fallback có điều kiện rõ ràng.

### 9.4. Tệp đặc biệt và hard link

Trên Unix có FIFO, socket hoặc device entry; Java filesystem provider có thể phân loại chúng trong `isOther()`. Đọc/copy chúng như file thường có thể treo hoặc gây hậu quả ngoài mong muốn. Công cụ này dừng copy khi gặp loại không được hỗ trợ, `stats` đếm `Other`.

**Hard link** khác symbolic link: nhiều tên đường dẫn có thể tham chiếu cùng một nội dung vật lý. `BasicFileAttributes.fileKey()` có thể giúp phát hiện một số file identity, nhưng không bảo đảm luôn có hoặc có cùng ý nghĩa trên mọi provider. `stats` hiện đếm **mỗi đường dẫn file thường** và cộng logical bytes của nó, vì thế có thể tính cùng dữ liệu vật lý nhiều lần đối với hard links. `copy` tạo các file đích độc lập, không tái tạo quan hệ hard link.

## 10. Mở rộng chức năng tìm kiếm

Một phiên bản thực tế có thể nhận thêm:

- `--max-depth=N`: giới hạn mức sâu bằng `Files.walkFileTree(root, options, maxDepth, visitor)`.
- `--type=file|dir|link`: chọn loại entry muốn tìm.
- `--min-size`/`--max-size`: lọc theo `BasicFileAttributes.size()` đối với file thường.
- `--modified-after=<timestamp>`: so sánh `FileTime`.
- `--relative-glob="**/*.java"`: áp `PathMatcher` lên `root.relativize(file)` thay vì `file.getFileName()`.
- `--max-results=N`: khi đủ kết quả, trả `TERMINATE` để giảm thời gian duyệt.
- `--json`: máy có thể parse ổn định, escape path và dùng metadata rõ ràng.
- Sắp xếp: gom các kết quả rồi sort theo comparator xác định; đổi lại phải dùng RAM tỷ lệ số kết quả, hoặc có cách sort bên ngoài cho tập rất lớn.

**Phân biệt tên file và nội dung file:** công cụ `find` này tìm **theo tên**, không đọc văn bản bên trong file. Nếu muốn grep nội dung, phải thêm bước đọc file với charset rõ ràng, xử lý binary file, giới hạn size và lỗi decode. Không nên gọi `Files.readAllBytes` với file quá lớn.

## 11. Mở rộng chức năng sao chép và thống kê

### Copy metadata

Nếu yêu cầu giữ một phần thuộc tính, `Files.copy` có tùy chọn `StandardCopyOption.COPY_ATTRIBUTES`. Tuy nhiên hỗ trợ owner, permission, DOS flags và ACL khác nhau tùy nền tảng; copy giữa filesystem khác nhau có thể không thể giữ mọi thuộc tính. Với directory timestamp, thường cần xử lý **sau khi đã sao chép xong con** (trong `postVisitDirectory`), vì thao tác tạo file có thể thay đổi modification time của directory đích.

Không nên mặc định nói `Files.copy` giữ đầy đủ ACL/timestamp; ví dụ đã cố ý chỉ cam kết **nội dung file thường và cấu trúc directory**.

### Resume/incremental copy

Một công cụ backup thực tế nên so sánh trạng thái nguồn/đích để chỉ sao chép file mới hoặc thay đổi, có policy riêng cho file bị xóa. Quyết định dựa duy nhất trên size/mtime có thể bỏ sót thay đổi; hash giúp kiểm tra nội dung nhưng tăng I/O. Nếu thao tác copy kéo dài, cần lưu manifest tiến độ và cơ chế retry idempotent thay vì ghi đè tùy tiện.

### Báo cáo lỗi và thống kê sâu hơn

Có thể thống kê theo extension, tổng byte theo thư mục, file lớn nhất, độ sâu lớn nhất, số lỗi quyền truy cập và thời gian thực hiện. Nếu chọn cơ chế “bỏ qua lỗi”, cần **đếm và báo rõ lỗi**, không in status “complete” khi thiếu dữ liệu.

Khi thống kê theo extension, chú ý file không có dấu chấm, file bắt đầu bằng dấu chấm, tên chứa nhiều dấu chấm và case sensitivity. Đừng coi extension là cách kiểm tra MIME hay bảo mật nội dung.

### Hủy thao tác và giới hạn tài nguyên

Nếu công cụ chạy trong service/API, cần hủy được khi user cancel, giới hạn số file/byte/thời gian, tránh scan các directory ngoài phạm vi, và không in đường dẫn bí mật vào log công khai. Với thư mục lớn qua network share, tính đến lỗi mạng tạm thời và connection throttling.

## 12. Vì sao không nên giải quyết toàn bộ bằng một `Files.walk(...)`?

`Files.walk(root)` trả về `Stream<Path>`, rất tiện cho nhiều truy vấn ngắn; phải dùng `try (Stream<Path> s = Files.walk(root))` để đóng tài nguyên thư mục. Nó cũng không tự sao chép một cây.

Trong bài này, `walkFileTree` được chọn vì:

1. `preVisitDirectory` cho phép **tạo thư mục đích đúng thứ tự**;
2. `postVisitDirectory` hữu ích khi bảo tồn metadata sau copy hoặc xử lý lỗi duyệt;
3. `visitFileFailed` cung cấp đường xử lý lỗi I/O tường minh;
4. có `FileVisitResult` để quyết định tiếp tục, bỏ nhánh hoặc dừng;
5. không cần tích lũy toàn bộ các đường dẫn vào RAM.

Cả hai API đều hiện hành. Chọn theo loại thao tác thay vì dựa vào việc API nào “mới hơn”.

## 13. Các lỗi phổ biến trong bài thực hành

1. **Sao chép một directory bằng `Files.copy(sourceDir, targetDir)` rồi nghĩ nó copy toàn bộ cây.** Phải duyệt con nếu muốn copy đệ quy.
2. **Đặt đích bên trong nguồn.** Có thể khiến kết quả lặp hoặc sinh thêm entries trong lúc duyệt; phải chặn trước thao tác.
3. **Bật `FOLLOW_LINKS` mà không hiểu phạm vi.** Link có thể trỏ ra ngoài cây; vẫn có thể gặp vòng lặp và I/O error.
4. **Không override `visitFileFailed`.** Một nhánh lỗi có thể bị xử lý không đúng với policy mong muốn.
5. **Bỏ qua `postVisitDirectory(..., exc)`.** Lỗi phát sinh lúc lặp directory có thể bị bỏ sót.
6. **Dùng `int` để cộng byte.** Dễ tràn khi dữ liệu lớn; dùng `long` và kiểm tra overflow nếu cần.
7. **Cho rằng `size()` là số byte vật lý đã chiếm trên đĩa.** Nó là logical size của file theo filesystem provider.
8. **Sắp xếp output theo cảm tính.** `walkFileTree` không cam kết thứ tự siblings.
9. **Tin rằng normalize đã giải quyết mọi symbolic link.** `normalize` là thao tác từ vựng, không phải kiểm chứng filesystem và race.
10. **Thêm `REPLACE_EXISTING` để tránh mọi exception.** Có thể phá hủy dữ liệu đích.
11. **Không giải thích partial copy.** Nếu thất bại giữa chừng, không được báo thành công.
12. **Giữ toàn bộ kết quả tìm kiếm trong `ArrayList` khi không cần sắp xếp.** Tốn memory khi có hàng triệu matches.
13. **Giả định glob trên mọi OS giống nhau 100%.** Kiểm thử các mẫu và ký tự đặc biệt trên filesystem đích.
14. **Chỉ kiểm tra tổng file và tổng bytes sau copy.** Có thể bằng nhau dù một số file có nội dung khác; cần checksum/byte comparison khi yêu cầu bảo đảm.
15. **Chạy backup trên cây thay đổi liên tục rồi coi kết quả là snapshot.** Không có đảm bảo đồng bộ nếu không phối hợp filesystem/storage hoặc nguồn ghi.

## 14. Bài tập nâng cao có tiêu chí kiểm chứng

### Bài A — thống kê theo phần mở rộng

Mở rộng `StatsVisitor` để in số file `.txt`, `.java`, `.csv` và các loại khác. Nên quyết định rõ có phân biệt `.TXT` và `.txt` không. **Đạt** khi kết quả tổng các nhóm khớp `Files`, và file không có extension được xếp đúng.

### Bài B — tìm theo glob của đường dẫn tương đối

Thêm `find-path` nhận pattern như `**/*.java` và sử dụng `matcher.matches(root.relativize(file))`. **Đạt** khi hai file có tên giống nhau ở hai thư mục khác nhau được xử lý theo đường dẫn tương đối, không chỉ phần basename.

### Bài C — thống kê file lớn nhất

Dùng `BasicFileAttributes.size()`, lưu cặp `Path` và `long` lớn nhất. **Đạt** khi cây rỗng không gây lỗi và file lớn nhất có size chính xác. Chú ý file có size bằng nhau cần quy định cách phá hòa nếu muốn output ổn định.

### Bài D — chạy lại copy an toàn

Thiết kế `copy --resume` có manifest ghi file đã hoàn thành, checksum, trạng thái copy. **Đạt** khi dừng giữa chừng rồi tiếp tục không ghi đè file sai và không báo hoàn tất khi còn file lỗi. Chỉ triển khai sau khi có chính sách xử lý những file nguồn bị thay đổi.

### Bài E — copy dữ liệu có link

Thiết kế một chế độ rõ ràng: từ chối link, bỏ qua nhưng báo cáo, hoặc sao chép chính link nếu filesystem hỗ trợ. **Đạt** khi link trỏ ra ngoài cây không vô tình khiến chương trình copy toàn bộ dữ liệu phía ngoài; kiểm tra trên nền tảng cho phép tạo symlink.

## 15. Checklist trước khi dùng lại trong dự án

- [ ] Xác định rõ root và phương án giải quyết symbolic link; không dùng glob không kiểm soát trên path nhạy cảm.
- [ ] Tìm kiếm: biết đang lọc **basename** hay **relative path** và có cần kết quả sắp xếp không.
- [ ] Thống kê: phân biệt logical bytes với allocated disk bytes, và hard link với symbolic link.
- [ ] Sao chép: không ghi đè ngoài ý muốn, không copy vào trong nguồn, không giả định snapshot.
- [ ] Có callback báo lỗi thay vì bỏ qua âm thầm; không coi partial destination là bản sao hợp lệ.
- [ ] Không giữ tất cả file bytes trong heap; kiểm tra quyền, đĩa và tốc độ I/O khi dữ liệu lớn.
- [ ] Có fixture kiểm tra: cây rỗng, tên Unicode, thư mục lồng nhiều cấp, link, denied directory, đích tồn tại, root không tồn tại.
- [ ] Nếu dùng production: thêm staging/manifest/verification/atomic publish phù hợp và xử lý TOCTOU.
- [ ] Chạy thử trên Windows/Linux/macOS hoặc những filesystem thực tế mà dự án hỗ trợ.
- [ ] Dùng API Java SE hiện hành của `java.nio.file` thay vì phụ thuộc phương pháp đã lỗi thời.

## 16. Câu hỏi tự kiểm tra

1. Tại sao `Files.copy(directory, target)` không đủ để clone một cây thư mục?
2. Callback `preVisitDirectory` và `visitFile` đóng vai trò gì khi xây dựng cây đích?
3. Vì sao công cụ `stats` đếm symlink nhưng không cộng dung lượng nội dung mà nó trỏ tới?
4. Khi nào nên áp `PathMatcher` lên `getFileName()`, khi nào nên áp lên `root.relativize(file)`?
5. Vì sao `normalize` và `startsWith` không phải bảo đảm an toàn tuyệt đối khi filesystem bị thay đổi đồng thời?
6. Sao chép bị lỗi sau một nửa số file: vì sao không thể báo thành công hoặc âm thầm xóa mọi thứ trong đích?
7. Vì sao hai file có cùng size và timestamp chưa chắc có cùng nội dung?
8. Những thay đổi nào cần có nếu ứng dụng phải backup một cây tệp lớn đang được ghi liên tục?

## Tài liệu tham khảo hiện hành

- [Oracle Java SE 26 — `Files`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `walkFileTree`, `copy`, `exists`, `createDirectory` và hành vi với symbolic link.
- [Oracle Java SE 26 — `SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): hành vi mặc định và callback xử lý file tree.
- [Oracle Java SE 26 — `FileVisitor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileVisitor.html): hợp đồng các callback và `FileVisitResult`.
- [Oracle Java SE 26 — `Path`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): `resolve`, `relativize`, `normalize`, `toRealPath`.
- [Oracle Java SE 26 — `PathMatcher`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/PathMatcher.html): glob và tương tác filesystem provider.
- [Oracle Java SE 26 — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): thuộc tính file, kiểu và logical size.
- [Oracle Java SE 26 — `LinkOption`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Oracle Java SE 26 — `SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác tương đối với directory handle khi cần xử lý race an toàn hơn.
