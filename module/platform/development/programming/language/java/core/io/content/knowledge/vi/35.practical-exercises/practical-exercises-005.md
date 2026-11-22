# Thực hành: Xây dựng công cụ duyệt cây và lọc tệp bằng Java NIO.2

## 1. Bài toán và mục tiêu

Bạn cần một công cụ dòng lệnh để duyệt một thư mục gốc cùng các thư mục con, chỉ in những **tệp thông thường** đáp ứng điều kiện lọc. Công cụ phải hữu ích với cây thư mục lớn, dễ xác minh kết quả và chịu được một số lỗi truy cập mà không làm mất mọi kết quả đã tìm được.

Trong bài thực hành này, chúng ta sẽ viết chương trình `TreeFilter` bằng Java 17+ với các chức năng:

- Nhận **thư mục gốc** từ đối số dòng lệnh.
- Duyệt đệ quy bằng `Files.walkFileTree` và `SimpleFileVisitor`.
- Lọc theo **glob tên tệp**, kích thước nhỏ nhất/lớn nhất (byte), giới hạn **độ sâu**, và tùy chọn có/không xét mục ẩn.
- **Không đi theo symbolic link mặc định**; chỉ theo link khi người dùng bật `--follow-links`.
- Hiển thị đường dẫn tương đối cùng kích thước byte trên stdout, thống kê và cảnh báo trên stderr.
- Tiếp tục sau lỗi truy cập từng nhánh nếu có thể, ghi nhận số lỗi và trả mã thoát phù hợp.
- Tạo dữ liệu kiểm thử nhỏ để xác minh đầu ra, sau đó thảo luận giới hạn thực tế với tệp lớn và cây nhiều nhánh.

Đây là công cụ **chỉ đọc nội dung cấu trúc tệp trong lúc duyệt**; nó không xóa, sửa, di chuyển hay đổi tên tệp. Chương trình sẽ xem metadata (loại tệp, kích thước, thuộc tính ẩn) và tên tệp; nó **không mở/đọc toàn bộ nội dung** để tìm từ khóa. Nếu muốn lọc theo nội dung, cần bổ sung một bước streaming riêng.

## 2. Thiết kế giao diện CLI

Cú pháp đề xuất:

~~~text
java TreeFilter <root> [options]

Options:
  --glob <pattern>     Glob áp dụng trên TÊN TỆP (mặc định: *)
  --min-bytes <number> Kích thước tối thiểu, đơn vị byte (mặc định: 0)
  --max-bytes <number> Kích thước tối đa, đơn vị byte (mặc định: Long.MAX_VALUE)
  --max-depth <number> Giới hạn độ sâu duyệt, số nguyên >= 1
  --include-hidden     Cho phép cả tệp/thư mục được OS nhận diện là ẩn
  --follow-links       Cho phép đi theo symbolic link; mặc định không
~~~

Các lựa chọn được **AND** với nhau. Ví dụ lệnh:

~~~bash
java TreeFilter project --glob "*.java" --min-bytes 100 --max-bytes 200000 --max-depth 10
~~~

Chương trình tìm file Java có tên khớp `*.java`, từ 100 đến 200.000 byte, trong phạm vi cây bắt đầu tại `project` với độ sâu tối đa 10. Mẫu glob được áp dụng lên **`file.getFileName()`** (chỉ thành phần tên cuối). Vì vậy `*.java` có thể khớp `src/App.java`, còn `src/*.java` **không** khớp tên `App.java`; muốn lọc theo đường dẫn tương đối thì phải đổi cách áp dụng `PathMatcher`.

**Quy ước độ sâu:** gốc có độ sâu 0, tệp con trực tiếp có độ sâu 1, tệp trong thư mục con có độ sâu 2, v.v. `--max-depth 1` chỉ xét các mục trực tiếp bên dưới gốc. Thư mục ở độ sâu bằng giới hạn không được đi sâu thêm. Đây là giới hạn duyệt cây của `walkFileTree`, không phải số cấp thư mục **được in**.

**Định dạng đầu ra:** mỗi dòng kết quả chứa `đường_dẫn_tương_đối<TAB>kích_thước_byte`, tính theo `Path.toString()` của hệ điều hành. Dấu phân cách thư mục có thể là `/` trên Unix hoặc `\` trên Windows. Cách xuất TSV đơn giản thích hợp để học và thao tác nhanh; tên tệp chứa TAB hoặc xuống dòng cần escape/định dạng JSON nếu xây dựng công cụ tích hợp máy với máy.

## 3. Chọn API duyệt cây

Java NIO.2 trong `java.nio.file` hỗ trợ nhiều cách duyệt:

| API | Phạm vi | Đặc điểm cần nhớ |
| --- | --- | --- |
| `Files.list(dir)` | Một cấp | Trả `Stream<Path>`; phải đóng stream sau khi dùng |
| `Files.walk(root, depth)` | Nhiều cấp | `Stream<Path>` lazy; cần `try-with-resources` để đóng |
| `Files.find(root, depth, matcher)` | Nhiều cấp | Predicate nhận `Path` và `BasicFileAttributes`; phải đóng stream |
| `Files.walkFileTree(root, visitor)` | Nhiều cấp | Callback theo sự kiện; kiểm soát `SKIP_SUBTREE`, `TERMINATE`, lỗi truy cập và link |

`Files.walkFileTree` phù hợp khi muốn điều khiển traversal rõ ràng mà không phải giữ toàn bộ danh sách file trong RAM. `SimpleFileVisitor<Path>` cung cấp các phương thức mặc định cho bốn mốc chính:

1. `preVisitDirectory(dir, attrs)`: trước khi vào một thư mục; có thể trả `SKIP_SUBTREE` để bỏ cả nhánh.
2. `visitFile(file, attrs)`: khi gặp một mục được xử lý như file; `attrs.isRegularFile()` cho biết đó có phải tệp thông thường hay không.
3. `visitFileFailed(file, exception)`: lỗi lấy thuộc tính hoặc không thể duyệt mục, trong đó có tình huống symbolic link tạo chu trình.
4. `postVisitDirectory(dir, exception)`: sau khi xử lý thư mục; `exception` khác null nếu traversal của thư mục gặp lỗi.

Các giá trị `FileVisitResult` phổ biến là `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS` và `TERMINATE`. Trong bài này ta dùng `CONTINUE` và `SKIP_SUBTREE`; nếu không cần hủy toàn bộ quá trình thì không trả `TERMINATE` chỉ vì một file không khớp filter.

## 4. Triển khai `TreeFilter.java` đầy đủ

Lưu nguyên mã sau vào **`TreeFilter.java`**. Chương trình dùng các API chuẩn của JDK, không cần Maven, Gradle hoặc thư viện bên thứ ba.

~~~java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.PathMatcher;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.Locale;

import static java.nio.file.FileVisitResult.CONTINUE;
import static java.nio.file.FileVisitResult.SKIP_SUBTREE;

public class TreeFilter {
    private record Config(
            Path root,
            PathMatcher nameMatcher,
            long minBytes,
            long maxBytes,
            int maxDepth,
            boolean includeHidden,
            boolean followLinks) {}

    private static final class Stats {
        long directories;
        long regularFiles;
        long matches;
        long errors;
    }

    public static void main(String[] args) {
        try {
            Config config = parseArgs(args);
            Stats stats = new Stats();

            EnumSet<FileVisitOption> options = config.followLinks()
                    ? EnumSet.of(FileVisitOption.FOLLOW_LINKS)
                    : EnumSet.noneOf(FileVisitOption.class);

            Files.walkFileTree(
                    config.root(),
                    options,
                    config.maxDepth(),
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs) {
                            // Giữ quyền duyệt root; các thư mục con ẩn
                            // được loại bỏ cùng toàn bộ nhánh của chúng.
                            if (!dir.equals(config.root())
                                    && !config.includeHidden()) {
                                try {
                                    if (Files.isHidden(dir)) {
                                        return SKIP_SUBTREE;
                                    }
                                } catch (IOException e) {
                                    stats.errors++;
                                    reportError(dir, e);
                                    return SKIP_SUBTREE;
                                }
                            }
                            stats.directories++;
                            return CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            if (!attrs.isRegularFile()) {
                                return CONTINUE;
                            }
                            stats.regularFiles++;

                            if (!config.includeHidden()) {
                                try {
                                    if (Files.isHidden(file)) {
                                        return CONTINUE;
                                    }
                                } catch (IOException e) {
                                    stats.errors++;
                                    reportError(file, e);
                                    return CONTINUE;
                                }
                            }

                            if (!config.nameMatcher().matches(file.getFileName())) {
                                return CONTINUE;
                            }

                            long size = attrs.size();
                            if (size < config.minBytes()
                                    || size > config.maxBytes()) {
                                return CONTINUE;
                            }

                            Path relative = config.root().relativize(file);
                            System.out.printf(Locale.ROOT, "%s\t%d%n",
                                    relative, size);
                            stats.matches++;
                            return CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFileFailed(
                                Path file, IOException error) {
                            stats.errors++;
                            reportError(file, error);
                            return CONTINUE;
                        }

                        @Override
                        public FileVisitResult postVisitDirectory(
                                Path dir, IOException error) {
                            if (error != null) {
                                stats.errors++;
                                reportError(dir, error);
                            }
                            return CONTINUE;
                        }
                    });

            System.err.printf(Locale.ROOT,
                    "Visited directories=%d, regular files=%d, matches=%d, errors=%d%n",
                    stats.directories, stats.regularFiles,
                    stats.matches, stats.errors);

            if (stats.errors != 0) {
                System.exit(2); // Có kết quả từng phần kèm lỗi truy cập.
            }
        } catch (IllegalArgumentException e) {
            System.err.println("Invalid arguments: " + e.getMessage());
            printUsage();
            System.exit(1);
        } catch (IOException e) {
            System.err.println("Traversal failed: " + e);
            System.exit(2);
        }
    }

    private static Config parseArgs(String[] args) {
        if (args.length == 0 || args[0].startsWith("--")) {
            throw new IllegalArgumentException("Root directory is required");
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        // Bài này yêu cầu root là thư mục thực, không phải symlink.
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalArgumentException(
                    "Not a directory: " + root);
        }

        String glob = "*";
        long minBytes = 0L;
        long maxBytes = Long.MAX_VALUE;
        int maxDepth = Integer.MAX_VALUE;
        boolean includeHidden = false;
        boolean followLinks = false;

        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--glob" ->
                    glob = nextValue(args, ++i, "--glob");
                case "--min-bytes" ->
                    minBytes = Long.parseLong(
                            nextValue(args, ++i, "--min-bytes"));
                case "--max-bytes" ->
                    maxBytes = Long.parseLong(
                            nextValue(args, ++i, "--max-bytes"));
                case "--max-depth" ->
                    maxDepth = Integer.parseInt(
                            nextValue(args, ++i, "--max-depth"));
                case "--include-hidden" -> includeHidden = true;
                case "--follow-links" -> followLinks = true;
                default -> throw new IllegalArgumentException(
                        "Unknown option: " + args[i]);
            }
        }

        if (minBytes < 0 || maxBytes < 0 || maxBytes < minBytes) {
            throw new IllegalArgumentException("Invalid size range");
        }
        if (maxDepth < 1) {
            throw new IllegalArgumentException(
                    "max-depth must be >= 1");
        }

        // Glob match trên tên file, không match toàn bộ relative path.
        PathMatcher matcher = FileSystems.getDefault()
                .getPathMatcher("glob:" + glob);
        return new Config(root, matcher, minBytes, maxBytes,
                maxDepth, includeHidden, followLinks);
    }

    private static String nextValue(
            String[] args, int index, String option) {
        if (index >= args.length) {
            throw new IllegalArgumentException(
                    "Missing value for " + option);
        }
        return args[index];
    }

    private static void reportError(Path path, IOException error) {
        System.err.println("WARN " + path + ": " + error);
    }

    private static void printUsage() {
        System.err.println(
                "Usage: java TreeFilter <root> "
                + "[--glob <pattern>] "
                + "[--min-bytes <n>] [--max-bytes <n>] "
                + "[--max-depth <n>] "
                + "[--include-hidden] [--follow-links]");
    }
}
~~~

Biên dịch và chạy với Java 17 hoặc mới hơn:

~~~bash
javac TreeFilter.java
java TreeFilter . --glob "*.java" --max-depth 5
~~~

Chạy ở thư mục bất kỳ chứa mã Java để xem kết quả thực tế; số file và kích thước phụ thuộc thư mục đó. Dùng dấu ngoặc kép quanh glob để tránh shell Unix tự mở rộng `*.java` thành danh sách file trước khi Java nhận tham số.

### 4.1. Giải thích cơ chế chính

**`Path` và `PathMatcher`.** `Path.of(args[0])` tạo đối tượng đường dẫn theo filesystem provider mặc định. `toAbsolutePath().normalize()` chuyển sang đường dẫn tuyệt đối và đơn giản hóa các thành phần `.`, `..`; nó **không** kiểm chứng real path hoặc ngăn link thoát khỏi root. `PathMatcher` nhận cú pháp `glob:...`, hỗ trợ wildcard như `*`, `?` và `{java,kt}` tùy cú pháp glob của provider. Ta cố ý match `file.getFileName()` để option có ý nghĩa thống nhất: filter theo *tên* ở mọi độ sâu.

**Duyệt theo sự kiện.** Visitor không gom mọi `Path` vào `List` rồi lọc sau; khi tìm thấy một file khớp, nó in ngay. Bộ nhớ tăng chủ yếu theo độ sâu traversal và trạng thái của provider, không theo số lượng kết quả đã in. Output **không bảo đảm thứ tự từ điển** vì thứ tự duyệt do filesystem provider quyết định.

**Metadata.** `BasicFileAttributes attrs` được cung cấp khi visitor gặp file; `attrs.isRegularFile()` loại directory và các loại mục không phải regular file; `attrs.size()` lấy kích thước trong metadata. Nếu file bị sửa trong lúc duyệt, kích thước và nội dung thực tế có thể thay đổi sau thời điểm đọc attributes.

**Hidden.** Khi `includeHidden` bằng false, `preVisitDirectory` dùng `Files.isHidden(dir)` để bỏ cả nhánh thư mục ẩn và `visitFile` bỏ tệp ẩn. Quy tắc hidden khác giữa các hệ điều hành/provider: Unix thường dựa vào tên bắt đầu bằng dấu chấm, Windows có thuộc tính hidden. Do đó “hidden” là thuộc tính môi trường, không phải quy tắc Unicode/tên file do công cụ tự suy đoán. Thư mục gốc được duyệt ngay cả khi bản thân gốc được đánh dấu hidden; quy tắc bỏ hidden áp dụng các mục bên dưới gốc.

**Lọc kích thước và tên.** Ta áp dụng so khớp tên rồi kiểm tra `attrs.size()` trong khoảng bao gồm cả hai đầu mút: `minBytes <= size <= maxBytes`. Tệp có kích thước 0 hợp lệ nếu không bị điều kiện min loại. Với CLI cơ bản này, các đối số size là số nguyên hệ thập phân biểu diễn byte, chưa hỗ trợ hậu tố KB/MiB.

**Xử lý lỗi.** Nếu không được phép duyệt một nhánh, filesystem mất kết nối, hoặc symbolic link tạo vòng, visitor ghi cảnh báo vào stderr, tăng `errors` và thường tiếp tục duyệt phần khác. Mã thoát `2` báo đã có lỗi I/O, kể cả khi một số kết quả đã in; `1` báo đối số sai, còn `0` là hoàn tất không có lỗi được ghi nhận. Một số lỗi unchecked, lỗi tiến trình hoặc tác dụng phụ của filesystem provider có thể chấm dứt chương trình ngoài các nhánh `IOException` đã xử lý.

## 5. Tạo fixture nhỏ để tự kiểm tra

Để không phụ thuộc nội dung thư mục hiện có, tạo thêm một chương trình Java độc lập **`CreateDemoTree.java`**. Nó tạo cây tệp nhỏ trong thư mục `demo-tree` tương đối với working directory hiện tại.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateDemoTree {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("demo-tree");

        Files.createDirectories(root.resolve("logs/nested"));
        Files.createDirectories(root.resolve("docs"));

        Files.writeString(root.resolve("logs/a.log"), "ERROR");
        Files.writeString(root.resolve("logs/c.log"), "INFO\n");
        Files.writeString(root.resolve("logs/nested/b.log"), "WARN");
        Files.writeString(root.resolve("docs/readme.txt"), "Hello");

        System.out.println("Created demo-tree");
    }
}
~~~

Tệp `a.log` và `c.log` có đúng **5 byte** với nội dung ASCII/UTF-8 trong ví dụ, `b.log` có 4 byte và `readme.txt` có 5 byte. Chạy trong **thư mục làm việc sạch, chưa có `demo-tree` hoặc file khác trong cây** để các thống kê chính xác:

~~~bash
javac TreeFilter.java CreateDemoTree.java
java CreateDemoTree
java TreeFilter demo-tree --glob "*.log" --min-bytes 5 --max-bytes 5 --max-depth 4
~~~

Stdout của `CreateDemoTree`:

~~~text
Created demo-tree
~~~

Stdout của `TreeFilter` gồm **hai dòng sau**, nhưng thứ tự có thể đảo vì traversal không sắp xếp:

~~~text
logs/a.log	5
logs/c.log	5
~~~

Trên Windows, dấu phân cách trong hai đường dẫn là `\` thay vì `/`. Dòng thống kê stderr trên một filesystem thông thường, khi fixture đầy đủ và không có lỗi truy cập, là:

~~~text
Visited directories=4, regular files=4, matches=2, errors=0
~~~

Phân tích: bốn thư mục gồm root, `logs`, `logs/nested` và `docs`. Có bốn tệp thông thường; chỉ `a.log` và `c.log` đồng thời thỏa glob `*.log` và khoảng size `[5,5]`. `b.log` bị loại vì 4 byte, `readme.txt` vì không khớp glob. Tất cả thuộc độ sâu không vượt 4.

### 5.1. Thử từng bộ lọc riêng

**Chỉ xem log không giới hạn kích thước:**

~~~bash
java TreeFilter demo-tree --glob "*.log"
~~~

Dự kiến `matches=3`, các file `a.log`, `b.log`, `c.log` đều được in (thứ tự không cố định).

**Giới hạn độ sâu:**

~~~bash
java TreeFilter demo-tree --glob "*.log" --max-depth 2
~~~

Dự kiến `matches=2`: bỏ `logs/nested/b.log` vì nó nằm ở độ sâu 3. Theo semantics của `walkFileTree` với `maxDepth=2`, thư mục ở depth 2 không được descend để thăm file depth 3.

**Giới hạn kích thước:**

~~~bash
java TreeFilter demo-tree --glob "*.log" --min-bytes 4 --max-bytes 4
~~~

Dự kiến `matches=1`, chỉ còn `logs/nested/b.log` (4 byte).

**Đường dẫn gốc không tồn tại:**

~~~bash
java TreeFilter does-not-exist
~~~

Dự kiến in `Invalid arguments: Not a directory: ...` kèm usage trên stderr và thoát mã `1`. Phần đường dẫn tuyệt đối tùy máy. Để tự kiểm tra mã thoát, dùng `echo $?` trong Bash hoặc `$LASTEXITCODE` trong PowerShell.

### 5.2. Lưu ý về fixture

`Files.writeString` tạo mới hoặc ghi đè/truncate tệp có sẵn theo hành vi mặc định. Chỉ chạy fixture trong thư mục thực hành do bạn kiểm soát; nếu thư mục `demo-tree` đã tồn tại với tệp bổ sung, số file và số thư mục sẽ khác. Mã demo cố ý không tự xóa dữ liệu cũ để tránh một thao tác phá hủy ngoài mong đợi.

Bản thân `TreeFilter` chỉ đọc metadata. Việc chạy với root là thư mục source code hay dữ liệu thật không làm thay đổi file, nhưng người dùng vẫn cần quyền xem và duyệt những thư mục đó.

## 6. Symbolic link, chu trình và ranh giới root

### 6.1. Mặc định không đi theo symbolic link

`Files.walkFileTree` khi không đặt `FileVisitOption.FOLLOW_LINKS` không đi xuống directory link. Với symlink đến file, attributes được đọc theo chính sách không follow của traversal, vì vậy `attrs.isRegularFile()` thường không nhận nó là regular file để in ra.

Khi bật:

~~~bash
java TreeFilter demo-tree --glob "*.log" --follow-links
~~~

Java được phép đi qua symbolic link. Điều này có hai hệ quả:

1. **Có thể gặp chu trình**: `A/link -> A` hoặc liên kết gián tiếp giữa các thư mục. Visitor có thể nhận `FileSystemLoopException` thông qua `visitFileFailed`, báo lỗi và tiếp tục.
2. **Có thể đi ra ngoài cây root về mặt thực thể**: ví dụ `root/external -> /data/shared`. `Path.relativize` vẫn tạo được đường dẫn hình thức `external/...` vì walker đi theo link từ đường dẫn nằm dưới root, nhưng file vật lý thực sự có thể ở ngoài root.

Không thể coi `toAbsolutePath().normalize()` là sandbox. Nếu cần bảo đảm không rời khỏi root khi theo link, phải thiết kế policy và kiểm tra real path/canonical path cẩn thận, đồng thời xét **race condition** khi symlink bị đổi giữa lúc kiểm tra và lúc sử dụng. Một công cụ duyệt dữ liệu không tin cậy thường nên để `--follow-links` tắt và giới hạn phạm vi ở mức OS permissions.

### 6.2. Hard link và số lượng kết quả

Hard link là nhiều tên trong filesystem trỏ cùng một file identity. Công cụ hiện tại liệt kê **đường dẫn**, không deduplicate theo file identity. Vì vậy hai hard link đáp ứng filter sẽ được in hai lần; đây là hành vi phù hợp với nhiệm vụ tìm đường dẫn.

Nếu mục tiêu là đếm **file vật lý duy nhất**, cần một chính sách khác: dựa vào `BasicFileAttributes.fileKey()` khi provider hỗ trợ, nhận diện giới hạn của khóa và filesystem, rồi quản lý tập identity đã gặp. Điều này làm tăng dùng bộ nhớ. Không dùng tên đường dẫn làm bằng chứng một nội dung là duy nhất.

## 7. Vì sao không dùng `File.listFiles()` và đệ quy thủ công?

`java.io.File.listFiles()` vẫn hữu ích cho tình huống đơn giản, nhưng giá trị trả về có thể `null` khi lỗi đọc thư mục, và bạn phải tự quản lý stack/depth, symbolic link, metadata và xử lý lỗi khi viết recursive traversal. `Files.walkFileTree` cung cấp callback dành riêng cho các trường hợp đó.

Đoạn mã hay thấy:

~~~java
for (File child : directory.listFiles()) {
    visit(child);
}
~~~

Đây là **minh họa sai/thiếu**, không phải ví dụ chạy độc lập: `listFiles()` có thể trả `null` và gây `NullPointerException`; recursion sâu có thể gây `StackOverflowError`; nếu tự theo symbolic link thiếu kiểm soát có thể gặp chu trình. Dùng visitor giúp biểu diễn ý định rõ hơn, nhưng không miễn trừ việc chẩn đoán lỗi I/O.

Một lựa chọn Java NIO.2 gọn hơn cho bài toán chỉ cần stream kết quả:

~~~java
try (var paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

Đây là **đoạn mã minh họa** trong phương thức có `Path root` và xử lý `IOException`. `Files.walk` tạo stream đóng được nên cần `try-with-resources`; nếu iteration gặp I/O error, lỗi có thể được gói thành `UncheckedIOException`. Ngoài ra, việc bỏ nguyên subtree hidden hoặc thu thập lỗi rồi tiếp tục các nhánh khác không thuận tiện như visitor.

## 8. Hiệu năng và giới hạn trên cây tệp lớn

### 8.1. Bộ nhớ và độ phức tạp

Nếu có `N` mục trong phần cây được duyệt, một lượt traversal thường có chi phí thời gian cỡ `O(N)` **theo số mục được thăm**; nhưng độ trễ thực tế chịu chi phối của metadata I/O, directory enumeration, network mount, filesystem và quyền truy cập. Kiểm tra glob/size trên từng file thường rẻ hơn đọc toàn bộ nội dung.

Chương trình in ngay kết quả nên **không giữ tất cả `N` đường dẫn trong một collection**. Trạng thái của traversal phụ thuộc độ sâu cây và cách provider triển khai, còn bộ đếm chỉ dùng vài biến `long`. Nếu cần sort kết quả, thông thường phải lưu hoặc sort ngoài (external sort), khiến memory/IO trade-off khác đi.

### 8.2. Cách cải thiện khi nhu cầu tăng

- **Lọc sớm thư mục:** nếu chỉ muốn duyệt các nhánh `src` hoặc bỏ `node_modules`/`build`, bổ sung quy tắc `preVisitDirectory` trả `SKIP_SUBTREE` trước khi xuống sâu; hiệu quả hơn nhận mọi file rồi bỏ.
- **Lọc nhiều điều kiện:** mở rộng `Config` và tách các predicate rõ ràng; ví dụ loại extension khác, timestamp theo `attrs.lastModifiedTime()`, loại file lớn hơn ngưỡng.
- **Tìm nội dung:** sau khi file qua lọc metadata, đọc streaming từng chunk để tìm pattern. Quy định encoding, giới hạn bytes/size, có hỗ trợ binary hay không; đừng dùng `Files.readAllBytes` cho mọi tệp lớn.
- **Xuất máy đọc được:** thay TSV thô bằng JSON Lines với escaping chính xác hoặc viết vào database, nhất là khi tên chứa ký tự đặc biệt.
- **Sắp xếp ổn định:** để có output từ điển, dùng một cơ chế sắp xếp có giới hạn RAM, hoặc lấy collection chỉ khi tập kết quả nhỏ. Không mặc định traversal trả sorted paths.
- **Hủy sớm:** thêm tùy chọn giới hạn số kết quả và trả `TERMINATE` khi đạt ngưỡng; làm rõ đây là kết quả một phần, không còn là quét toàn bộ cây.
- **Song song:** không mặc định nhiều thread sẽ nhanh hơn, đặc biệt trên ổ đĩa/network share vì metadata I/O và contention. Khi thực sự cần song song, phải kiểm soát queue, giới hạn số worker, lỗi, thứ tự và quota tài nguyên.

### 8.3. Rủi ro khi filesystem thay đổi lúc duyệt

Directory traversal không tạo một snapshot giao dịch. Có thể xảy ra:

- Một file bị xóa/đổi tên sau khi parent directory đã liệt kê.
- Metadata kích thước thay đổi trong khi chương trình in dữ liệu.
- Quyền truy cập bị thu hồi khiến `visitFileFailed` xuất hiện giữa lượt quét.
- Symbolic link bị sửa làm kết quả khác ngay trong cùng quá trình.

Vì vậy hãy mô tả kết quả là **những đường dẫn quan sát được trong một lần quét**, không tuyên bố chứng minh toàn bộ filesystem ở đúng một thời điểm. Với tác vụ bảo mật, backup hoặc xóa file, cần thiết kế kiểm tra và cơ chế nhất quán riêng thay vì dựa hoàn toàn vào một lượt `walkFileTree`.

## 9. Kiểm thử có chủ đích

Ngoài fixture cơ bản, hãy kiểm tra các nhóm sau:

| Trường hợp | Hành vi mong đợi |
| --- | --- |
| Thư mục gốc rỗng | Không có dòng kết quả, thống kê root là một thư mục |
| `--min-bytes 0 --max-bytes 0` | Chỉ nhận regular file rỗng nếu tên khớp |
| `--glob "*.TXT"` | Phụ thuộc quy tắc case sensitivity của filesystem/provider; không giả định khớp `.txt` trên mọi hệ thống |
| `--max-depth 1` | Không vào file nằm trong thư mục con sâu hơn |
| Thư mục con hidden | Bỏ cả subtree nếu không có `--include-hidden` theo `Files.isHidden` |
| Symlink đến thư mục | Mặc định không đi theo; khi bật follow có thể duyệt mục tiêu |
| Symlink tạo vòng | Báo lỗi/cảnh báo và kết thúc hữu hạn, không đệ quy vô hạn |
| Một thư mục không có quyền đọc | Ghi nhận lỗi khi provider báo, cố tiếp tục các nhánh khác, mã thoát khác 0 |
| Root không phải thư mục | Thông báo đối số không hợp lệ, không duyệt |
| `--min-bytes` lớn hơn `--max-bytes` | Báo lỗi đối số trước khi duyệt |
| Glob sai cú pháp | `IllegalArgumentException`/lỗi pattern; hiển thị usage |
| Tên file có Unicode/space | Xử lý qua `Path`, không chia đường dẫn bằng dấu cách |
| File bị xóa khi đang quét | Ghi nhận lỗi tương ứng nếu provider phát hiện; không khẳng định snapshot |

Kiểm thử hành vi symbolic link/hidden cần tạo fixture riêng tùy nền tảng và quyền tạo symlink; máy Windows có thể yêu cầu quyền hoặc chế độ cấu hình phù hợp. Không chạy test permission hoặc link vòng trên cây thư mục công việc đang dùng chung nếu không kiểm soát được hậu quả.

Nếu cần kiểm chứng một hàm filter độc lập, bạn có thể tách predicate nhận `Path` và `BasicFileAttributes` ra thành method thuần để unit test. Kiểm thử tích hợp dùng thư mục tạm (`Files.createTempDirectory`) và `try/finally` để dọn **đúng fixture do test tạo**, tránh xóa đường dẫn do người dùng nhập. Với công cụ dòng lệnh, kiểm tra cả **stdout, stderr và exit code**, vì một lượt quét có thể có kết quả đúng nhưng đồng thời có lỗi ở nhánh khác.

## 10. Những lỗi thường gặp khi nộp bài thực hành

**Lỗi 1 — coi mọi mục là tệp.** Trong `visitFile`, khi đạt max depth, visitor có thể được gọi với directory không được descend. Vì vậy cần kiểm tra `attrs.isRegularFile()` thay vì giả định mọi mục trong callback là file thường.

**Lỗi 2 — sử dụng `Files.walk` nhưng quên đóng stream.** Stream giữ tài nguyên mở để duyệt directory; bao bằng `try-with-resources` nếu chọn API đó.

**Lỗi 3 — lọc đường dẫn sai cấp.** `PathMatcher.matches(file.getFileName())` chỉ lọc tên file. Mẫu đường dẫn `src/**/*.java` cần match trên relative path và phải kiểm chứng semantics của glob trên từng provider.

**Lỗi 4 — nhầm `Files.isHidden` với tên bắt đầu bằng dấu chấm.** Hệ điều hành có chính sách riêng, đặc biệt trên Windows; không ép giả định Unix lên môi trường khác.

**Lỗi 5 — mặc định follow symbolic link.** Điều này có thể mở rộng phạm vi quét ngoài root và tạo chu trình. Giữ lựa chọn explicit, có test vòng lặp và xử lý `FileSystemLoopException`.

**Lỗi 6 — dừng khi gặp file không khớp.** File không khớp nên `CONTINUE`; chỉ dùng `SKIP_SUBTREE` khi chủ đích loại **cả thư mục con**.

**Lỗi 7 — gom toàn bộ file vào RAM trước khi lọc.** Với hàng triệu mục, list quá lớn gây memory pressure. Ưu tiên streaming callback và chỉ tích lũy nếu cần sort hoặc aggregate.

**Lỗi 8 — cho rằng số liệu là snapshot nhất quán.** Cây tệp có thể thay đổi trong quá trình duyệt; thao tác cleanup/destructive yêu cầu kiểm tra kỹ bổ sung.

**Lỗi 9 — in warning vào cùng stdout với dữ liệu.** Pipeline parse sẽ khó xử lý; dành stdout cho kết quả và stderr cho warnings/statistics.

**Lỗi 10 — coi exit code 0 khi đã có lỗi truy cập.** Mã thoát có ý nghĩa với script; chương trình trên trả 2 khi một hoặc nhiều lỗi I/O đã được ghi nhận dù vẫn in kết quả tìm thấy.

## 11. Bài tập mở rộng có hướng dẫn

1. **Thêm lọc ngày sửa đổi:** nhận `--modified-after 2026-01-01`, parse bằng `LocalDate` theo timezone do người dùng xác định rồi so với `attrs.lastModifiedTime()`. Ghi rõ boundary là thời điểm UTC hay giờ địa phương.
2. **Loại các thư mục không cần thiết:** thêm `--exclude-dir target` để trong `preVisitDirectory` bỏ nhánh `target` dù nó nằm ở độ sâu bất kỳ; xác định so khớp tên hay relative path.
3. **Xuất CSV an toàn:** có header, escape dấu ngoặc kép, xuống dòng và dấu phân cách theo RFC 4180; chú ý Windows path separator và encoding UTF-8.
4. **Tìm tệp lớn nhất:** giữ top K bằng priority queue kích thước K thay vì thu tất cả N file; chỉ cần O(K) bộ nhớ cho tập kết quả.
5. **Lọc theo nội dung:** với các file dưới ngưỡng cho phép, dùng `BufferedReader` và `Charset` xác định để tìm dòng chứa từ khóa; phân biệt text với binary và giới hạn kích thước.
6. **Viết test tích hợp:** tạo file và thư mục tạm, chạy `TreeFilter` dưới root đó, kiểm tra số kết quả; mock/thiết lập error theo nền tảng nếu cần và không phụ thuộc thứ tự duyệt.

## 12. Câu hỏi tự đánh giá

**Câu 1.** Vì sao `Files.walkFileTree` phù hợp hơn đệ quy `File.listFiles()` cho công cụ có thể bỏ subtree?

**Đáp án:** Visitor cung cấp `preVisitDirectory` và `SKIP_SUBTREE`, cơ chế lỗi rõ ràng cùng tùy chọn depth/link, giúp kiểm soát traversal mà không phải tự viết recursion.

**Câu 2.** Gọi `java TreeFilter root --glob "*.java"` có khớp `root/src/Main.java` không?

**Đáp án:** Có, nếu mục đó là regular file hợp lệ và không bị các filter khác loại; matcher áp dụng vào tên `Main.java`, không phụ thuộc folder `src`.

**Câu 3.** Có thể gọi `root.toAbsolutePath().normalize()` là một lớp cách ly an toàn ngăn symlink vượt root không?

**Đáp án:** Không. Đó là chuẩn hóa **cú pháp đường dẫn**, không ràng buộc mục tiêu vật lý của symbolic link. Giữ `--follow-links` tắt khi không cần và dùng policy an toàn hơn cho cây không tin cậy.

**Câu 4.** Một tệp 5 byte có đạt `--min-bytes 5 --max-bytes 5`?

**Đáp án:** Có. Khoảng giới hạn của chương trình bao gồm hai đầu mút.

**Câu 5.** Chương trình quét 100 thư mục, tìm được 50 kết quả nhưng một nhánh bị lỗi đọc. Exit code nên biểu đạt điều gì?

**Đáp án:** Có thể giữ 50 kết quả đã quan sát, nhưng phải báo lỗi và trả mã khác 0 để script gọi biết quá trình quét **không hoàn chỉnh**. Trong ví dụ mã thoát là `2`.

**Câu 6.** Muốn đầu ra luôn được sắp xếp theo đường dẫn nhưng không được giữ triệu đường dẫn trong RAM, hướng xử lý nào hợp lý?

**Đáp án:** Thu kết quả ra định dạng có thể xử lý bằng external sort (hoặc database/streaming sorted pipeline phù hợp); tính toán chi phí I/O bổ sung, không giả định iterator filesystem có thứ tự cố định.

## 13. Tài liệu chính thức

- [Java 17 Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)): giao thức traversal, `maxDepth`, link và visitor.
- [Java 17 SimpleFileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): các callback và hành vi mặc định.
- [Java 17 FileVisitResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Java 17 FileSystem.getPathMatcher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)): glob/regex và phạm vi phụ thuộc provider.
- [Java 17 BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): loại tệp, kích thước và thời gian.

Một công cụ lọc tệp đáng tin cần quy định rõ **đối tượng đang được duyệt**, **quy tắc lọc áp dụng ở cấp nào**, **hành vi khi gặp symbolic link/lỗi**, và **ý nghĩa của kết quả khi cây đang thay đổi**. Dựa trên `Files.walkFileTree` cùng bộ lọc metadata rõ ràng, bạn có thể mở rộng từ bài tập đơn giản thành công cụ quét tệp có thể sử dụng trong thực tế.
