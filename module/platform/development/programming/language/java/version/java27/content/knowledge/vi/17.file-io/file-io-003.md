# Duyệt cây thư mục và đóng stream tài nguyên đúng cách trong Java 27

Khi ứng dụng Java cần tìm tệp theo phần mở rộng, thống kê dung lượng một thư mục, quét cấu trúc dự án hoặc xử lý nhiều tệp nhật ký, ta phải giải quyết **hai vấn đề độc lập**:

1. Duyệt đúng phạm vi tệp/thư mục và xử lý các điều kiện của hệ thống tệp: cấp con, độ sâu, quyền truy cập, liên kết tượng trưng (*symbolic link*) và lỗi I/O.
2. Quản lý vòng đời của những tài nguyên mở trong lúc duyệt. Một `Stream<Path>` lấy từ `Files.walk(...)` không chỉ là chuỗi phần tử trong bộ nhớ: nó có thể đang giữ các **directory handle** cần đóng.

Trong **Java 27**, API `java.nio.file`, `Files.list`, `Files.walk`, `Files.find`, `Files.walkFileTree` và `DirectoryStream` là những lựa chọn Java SE chính thức. Bài này tập trung vào API còn áp dụng hiện nay, không dựa vào những cơ chế duyệt tệp cũ hoặc tính năng preview.

## 1. Bản đồ các API: chọn đúng công cụ

| Nhu cầu | API | Duyệt bao nhiêu cấp? | Có tài nguyên cần đóng? |
| --- | --- | --- | --- |
| Xem các mục ngay bên trong một thư mục | `Files.list(dir)` | Một cấp; **không** bao gồm chính `dir` | **Có**: `Stream<Path>`, dùng try-with-resources |
| Duyệt thư mục có bộ lọc glob đơn giản | `Files.newDirectoryStream(dir, "*.csv")` | Một cấp | **Có**: `DirectoryStream<Path>` |
| Duyệt thư mục con và kết hợp Stream operations | `Files.walk(root)` | Đệ quy, bao gồm `root` | **Có**: `Stream<Path>` |
| Giới hạn mức duyệt | `Files.walk(root, maxDepth)` | Từ `0` đến `maxDepth` | **Có**: `Stream<Path>` |
| Tìm tệp khi muốn dùng cả thuộc tính đã đọc trong lúc duyệt | `Files.find(root, maxDepth, matcher)` | Đệ quy, lọc theo `Path` và `BasicFileAttributes` | **Có**: `Stream<Path>` |
| Duyệt điều khiển từng thư mục, xử lý lỗi, có callback trước/sau thư mục | `Files.walkFileTree(root, visitor)` | Đệ quy; có overload giới hạn độ sâu | **Không có Stream trả về**: API tự quản lý việc đóng thư mục trong traversal |
| Đọc từng dòng của một tệp dưới dạng Stream | `Files.lines(path, charset)` | Đọc nội dung **một tệp**, không phải duyệt cây | **Có**: `Stream<String>` giữ tài nguyên tệp |

`Path` (trong `java.nio.file`) biểu diễn đường dẫn, không mặc nhiên đảm bảo mục tiêu còn tồn tại hoặc có thể đọc tại thời điểm sử dụng. `Files` là lớp cung cấp thao tác tệp/thư mục tương ứng. Thứ tự các mục trả về trong một thư mục **không được API cam kết là thứ tự tên**; hãy sắp xếp tường minh khi bài toán cần kết quả ổn định.

## 2. Vì sao Stream từ hệ thống tệp phải được đóng?

`java.util.stream.Stream` kế thừa `AutoCloseable` thông qua `BaseStream`. Tuy nhiên, không phải **mọi** Stream đều gắn với tài nguyên ngoài JVM.

- `List.of(1, 2).stream()` hoặc `Stream.of(...)` thường không sở hữu file descriptor/directory handle; việc gọi `close()` sau một terminal operation không phải yêu cầu quản lý file handle.
- `Files.list(...)`, `Files.walk(...)` và `Files.find(...)` có thể giữ **directory handle** trong quá trình duyệt.
- `Files.lines(...)` giữ tài nguyên để đọc tệp theo kiểu lazy.

**Lệnh terminal như `count()`, `toList()`, `findFirst()`, `forEach()` không tự đảm bảo gọi `close()`.** Ngay cả khi đã dùng hết phần tử, không nên chờ garbage collector giải phóng tài nguyên này.

### 2.1. Mẫu chuẩn: try-with-resources

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class DirectoryCountDemo {
    public static void main(String[] args) throws IOException {
        Path dir = args.length == 0 ? Path.of(".") : Path.of(args[0]);

        try (Stream<Path> entries = Files.list(dir)) {
            long count = entries.count();
            System.out.println("Số mục trực tiếp: " + count);
        } // entries.close() được gọi tự động
    }
}
```

**Cách chạy** (từ thư mục có file nguồn): biên dịch bằng JDK 27, rồi chạy `java DirectoryCountDemo` hoặc truyền một đường dẫn thư mục làm đối số. `Files.list` đếm **các mục trực tiếp** trong thư mục; không tính các mục nằm sâu ở các thư mục con.

Vì `Stream` là `AutoCloseable`, cú pháp `try (...)` bảo đảm gọi `close()` sau khi khối kết thúc bình thường, sau `return` hoặc khi có exception. Với Stream từ `Files.walk` và `Files.find`, đây cũng là mẫu bắt buộc nên ưu tiên.

### 2.2. Ví dụ rò rỉ tài nguyên cần tránh

```java
// KHÔNG NÊN: không quản lý việc đóng Stream do Files.walk mở.
static long countFilesUnsafe(Path root) throws IOException {
    return Files.walk(root)
            .filter(Files::isRegularFile)
            .count();
}
```

Dù `count()` tiêu thụ hết Stream, cách viết trên không xác nhận việc đóng các directory handle. Phiên bản an toàn:

```java
static long countFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile).count();
    }
}
```

Tên method `countFilesUnsafe` ở đây chỉ dùng để minh họa **mẫu sai cần tránh**, không phải mẫu khuyến khích sử dụng.

### 2.3. Kết thúc sớm vẫn phải đóng

```java
static java.util.Optional<Path> firstLog(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root, 4)) {
        return paths
                .filter(path -> Files.isRegularFile(path))
                .filter(path -> path.getFileName()
                        .toString().endsWith(".log"))
                .findFirst();
    }
}
```

`findFirst()` có thể dừng duyệt ngay khi gặp một tệp khớp, trong khi vẫn còn thư mục chưa duyệt. Khối `try` đóng tài nguyên kể cả khi pipeline dừng sớm. Kết quả trả về là một `Optional<Path>` độc lập với Stream đã đóng; nó không phải là nội dung tệp và **không bảo đảm tệp còn tồn tại** khi caller sử dụng `Path` sau đó.

## 3. Files.list: duyệt một cấp, không đệ quy

`Files.list(dir)` trả một `Stream<Path>` chứa các mục **nằm ngay bên trong** `dir`, bao gồm tệp và thư mục con; nó không tự đi sâu và không trả `dir` như một phần tử.

Ví dụ chỉ hiển thị các tệp thông thường nằm trực tiếp trong một thư mục:

```java
// File: ListFilesDemo.java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class ListFilesDemo {
    public static void main(String[] args) throws IOException {
        Path dir = args.length == 0
                ? Path.of(".").toAbsolutePath().normalize()
                : Path.of(args[0]).toAbsolutePath().normalize();

        try (Stream<Path> entries = Files.list(dir)) {
            entries
                .filter(p -> Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
                .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                .forEach(p -> System.out.println(p.getFileName()));
        }
    }
}
```

Trong ví dụ:

- `Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)` chỉ nhận **tệp thông thường**, không xử lý link dẫn tới tệp như chính tệp đích.
- `sorted(...)` sắp theo tên nhằm cho đầu ra dễ đọc; quá trình sắp xếp phải giữ các mục để sắp xếp nên có chi phí bộ nhớ.
- `toAbsolutePath().normalize()` giúp cách hiển thị/ghép đường dẫn nhất quán hơn, nhưng **không** tạo ra một biên giới bảo mật và không ngăn được các vấn đề symbolic link hoặc race condition.

Nếu chỉ cần liệt kê vài mục gần nhất với thư mục nguồn, `Files.list` gọn hơn việc duyệt toàn bộ cây bằng `Files.walk`.

### 3.1. Files.newDirectoryStream cho việc duyệt từng mục

`DirectoryStream` là một `Iterable<Path>` có tài nguyên bên ngoài, thích hợp cho vòng lặp `for-each` và lọc glob ở một cấp:

```java
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

static void printCsvFiles(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir, "*.csv")) {
        for (Path entry : entries) {
            System.out.println(entry.getFileName());
        }
    }
}
```

`"*.csv"` là glob kiểm tra tên mục, không có nghĩa là duyệt xuống mọi thư mục con. `DirectoryStream` **không phải** `java.util.stream.Stream`, dù có chữ “Stream” trong tên; nó hỗ trợ duyệt qua iterator và phải đóng bằng `try-with-resources`.

Mỗi `DirectoryStream` thông thường chỉ cấp **một iterator**; không tái sử dụng như collection trong bộ nhớ. Lỗi I/O xảy ra **giữa lúc duyệt** có thể được đóng gói thành `DirectoryIteratorException`, có nguyên nhân là `IOException`. Khi cần chuyển tiếp lỗi trong method khai báo `throws IOException`:

```java
static void printCsvSafely(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir, "*.csv")) {
        for (Path p : entries) {
            System.out.println(p);
        }
    } catch (java.nio.file.DirectoryIteratorException ex) {
        throw ex.getCause();
    }
}
```

Khi cần truy xuất sâu, xác định giới hạn `maxDepth` hoặc callback để xử lý lỗi từng nhánh, hãy chuyển sang API ở các phần tiếp theo.

## 4. Files.walk: duyệt đệ quy bằng Stream<Path>

`Files.walk(root)` trả một `Stream<Path>` được tạo **lazily** khi duyệt cây theo chiều sâu (*depth-first traversal*). Theo Javadoc Java SE 27:

- **Có** phần tử `root` trong Stream, kể cả khi `root` là tệp.
- Thư mục được phát ra **trước** các mục con (*preorder*).
- Không cam kết thứ tự các mục cùng cấp.
- Mặc định **không đi theo symbolic link** khi duyệt.
- `Files.walk(root, maxDepth)` giới hạn số cấp tương đối so với gốc: `root` là cấp `0`, con trực tiếp là cấp `1`, v.v.
- `maxDepth < 0` gây `IllegalArgumentException`. Không giới hạn bằng một giá trị hữu hạn có thể quét cây rất lớn, nên chỉ định giới hạn phù hợp với phạm vi nghiệp vụ.

Sơ đồ:

```text
data/                         depth 0
├── report.csv                 depth 1
├── logs/                      depth 1
│   ├── app.log                depth 2
│   └── 2026/                  depth 2
│       └── november.log       depth 3
└── archive/                   depth 1
    └── old.log                depth 2
```

- `Files.list(data)` chỉ đưa ra `report.csv`, `logs` và `archive`.
- `Files.walk(data, 1)` bao gồm `data` và ba mục con cấp `1`.
- `Files.walk(data, 2)` còn thấy `app.log`, `2026` và `old.log`.
- `Files.walk(data)` không giới hạn độ sâu, đi qua toàn bộ cây trong ví dụ.

### 4.1. Tìm tệp theo phần mở rộng trong tối đa ba cấp

Chương trình độc lập:

```java
// File: SearchTextFiles.java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class SearchTextFiles {
    static List<Path> findTextFiles(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            return paths
                .filter(p -> Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
                .filter(p -> p.getFileName().toString().endsWith(".txt"))
                .map(root::relativize)
                .sorted(Comparator.comparing(Path::toString))
                .toList();
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = args.length == 0
                ? Path.of(".").toAbsolutePath().normalize()
                : Path.of(args[0]).toAbsolutePath().normalize();

        for (Path relativePath : findTextFiles(root, 3)) {
            System.out.println(relativePath);
        }
    }
}
```

`root.relativize(p)` tạo đường dẫn tương đối để hiển thị, không làm thao tác I/O. `sorted(...)` tạo thứ tự hiển thị rõ ràng theo biểu diễn chuỗi của `Path`; do đó kết quả có chi phí sắp xếp và tích lũy toàn bộ danh sách. Nếu xử lý hàng triệu file, nên xét thuật toán duyệt streaming thay vì `toList()` mọi đường dẫn.

Đầu ra thực tế phụ thuộc hoàn toàn vào thư mục được truyền và hệ điều hành; không nên giả định một danh sách cố định.

### 4.2. Chỉ đếm, không cần giữ các Path

```java
static long countJavaFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
            .filter(p -> Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
            .filter(p -> p.getFileName().toString().endsWith(".java"))
            .count();
    }
}
```

`count()` trả một số và không cần tích lũy tất cả `Path` vào `List`. Tuy nhiên, vẫn phải đóng Stream khi thao tác hoàn thành.

### 4.3. Khi không nên dùng Files.walk

`Files.walk` tiện cho pipeline lọc, map và count; nhưng nó không có callback riêng để chọn **bỏ qua một nhánh thư mục** hay xử lý một lỗi cụ thể tại từng bước như `walkFileTree`. Dùng `Files.walk(root).filter(...)` **không** bảo đảm ngừng truy cập các nhánh không mong muốn: bộ lọc áp dụng trên các phần tử đã được traversal phát ra.

Nếu cần bỏ qua hoàn toàn cây `node_modules`, kiểm soát một thư mục không có quyền truy cập, thu thập kết quả theo pre/post-order hoặc kết thúc traversal theo chính sách, `Files.walkFileTree` thường phù hợp hơn.

## 5. Files.find: dùng cả Path và BasicFileAttributes

`Files.find(root, maxDepth, matcher)` duyệt cây gần giống `Files.walk`, nhưng nhận một `BiPredicate<Path, BasicFileAttributes>`. Thuộc tính cơ bản đã được đọc trong traversal có thể dùng ngay để lọc mà không cần gọi `Files.readAttributes(...)` lại trong predicate.

```java
// File: FindLogsDemo.java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FindLogsDemo {
    public static void main(String[] args) throws IOException {
        Path root = args.length == 0 ? Path.of(".") : Path.of(args[0]);

        try (Stream<Path> logs = Files.find(
                root,
                5,
                (path, attrs) -> attrs.isRegularFile()
                    && path.getFileName().toString().endsWith(".log"))) {

            System.out.println("Số log: " + logs.count());
        }
    }
}
```

Ưu điểm: `attrs.isRegularFile()` và `attrs.size()` sử dụng dữ liệu metadata do traversal cung cấp, có thể tránh đọc thuộc tính thừa so với việc kết hợp `Files.walk(...).filter(p -> Files.isRegularFile(p))` trong nhiều trường hợp. Dù vậy, thứ tự duyệt vẫn không cam kết và kết quả không phải snapshot: file có thể bị đổi hoặc xóa ngay sau khi metadata được đọc.

**Bắt buộc đóng Stream** trả về từ `Files.find` như với `Files.walk`. Nếu mở được gốc nhưng xảy ra I/O error giữa lúc duyệt, lỗi thường phát sinh dưới dạng `UncheckedIOException` ở terminal operation.

## 6. Files.walkFileTree: duyệt cây với FileVisitor

`Files.walkFileTree` cung cấp một cách duyệt theo callback cho các tình huống cần **kiểm soát luồng traversal**. Phương thức này trả lại `Path` gốc sau khi hoàn thành (hoặc ném lỗi), **không trả về Stream để caller phải đóng**. Cơ chế traversal chịu trách nhiệm đóng directory handle khi hoàn tất từng thư mục.

`SimpleFileVisitor<Path>` cung cấp hành vi mặc định; ta override các callback cần thiết:

| Callback | Được gọi khi | Công việc thường làm |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi vào một thư mục | Kiểm tra điều kiện và chọn đi sâu/bỏ qua |
| `visitFile(file, attrs)` | Khi gặp mục không phải thư mục được đi sâu | Xử lý tệp, đọc kích thước, ghi nhận kết quả |
| `visitFileFailed(file, exc)` | Không thể truy cập một mục, hoặc gặp vòng liên kết khi theo link | Ghi nhận/tiếp tục hoặc ném lỗi |
| `postVisitDirectory(dir, exc)` | Sau khi duyệt xong một thư mục; `exc` có thể đại diện lỗi trong quá trình duyệt | Tổng hợp sau thứ tự con, xử lý lỗi |

### 6.1. Ý nghĩa FileVisitResult

| Kết quả trả về | Ý nghĩa |
| --- | --- |
| `CONTINUE` | Tiếp tục traversal |
| `SKIP_SUBTREE` | Bỏ qua con của **thư mục hiện tại** khi trả từ `preVisitDirectory` |
| `SKIP_SIBLINGS` | Bỏ qua các mục cùng cấp còn lại; trong `preVisitDirectory` nó cũng không đi vào thư mục hiện tại |
| `TERMINATE` | Dừng traversal sớm |

`SKIP_SUBTREE` chỉ có hiệu lực đặc biệt khi callback `preVisitDirectory` trả nó; đừng dùng `filter` của `Files.walk` rồi cho rằng traversal tự bỏ qua toàn bộ nhánh. Việc trả `TERMINATE` là cách hợp lệ để dừng traversal do visitor, không phải một Exception.

### 6.2. Ví dụ có thể chạy: thống kê tệp và kích thước

```java
// File: TreeStatsDemo.java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeStatsDemo {
    record Stats(long regularFiles, long bytes) {}

    private static final class Counter {
        long files;
        long bytes;
    }

    static Stats scan(Path root) throws IOException {
        Counter total = new Counter();

        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) {
                if (attrs.isRegularFile()) {
                    total.files++;
                    total.bytes = Math.addExact(total.bytes, attrs.size());
                }
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc) throws IOException {
                throw new IOException("Không thể đọc: " + file, exc);
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

        return new Stats(total.files, total.bytes);
    }

    public static void main(String[] args) throws IOException {
        Path root = args.length == 0 ? Path.of(".") : Path.of(args[0]);
        Stats stats = scan(root);
        System.out.println("Tệp thường: " + stats.regularFiles());
        System.out.println("Tổng byte: " + stats.bytes());
    }
}
```

Cơ chế:

1. `Files.walkFileTree` mở và duyệt mỗi thư mục dưới `root` theo chiều sâu.
2. `visitFile` nhận `BasicFileAttributes` đã đọc; với mục là tệp thông thường, tích lũy số lượng và `attrs.size()`.
3. Khi không đọc được một mục, ví dụ này **ném lỗi và dừng**, thay vì âm thầm đưa ra tổng thiếu dữ liệu.
4. `postVisitDirectory` tiếp tục hoặc chuyển tiếp lỗi I/O phát sinh khi duyệt thư mục.
5. Không có `Stream<Path>` bị để mở sau khi method trả về.

`Math.addExact(...)` ném `ArithmeticException` nếu tổng `long` vượt phạm vi. Đây là một lựa chọn bảo vệ dữ liệu báo cáo. Tổng dung lượng chỉ có ý nghĩa tại thời điểm traversal; file có thể bị ghi/xóa đồng thời, nên phép cộng không phải một ảnh chụp nguyên tử của hệ thống tệp.

### 6.3. Bỏ qua thư mục có tên nhất định

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) {
        Path name = dir.getFileName();

        if (name != null && name.toString().equals("node_modules")) {
            return FileVisitResult.SKIP_SUBTREE;
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        System.out.println(file);
        return FileVisitResult.CONTINUE;
    }
});
```

`preVisitDirectory` quyết định **trước khi đi sâu**, vì vậy nhánh `node_modules` được bỏ qua. Khi áp dụng thực tế, cần xem liệu có muốn bỏ qua chính `root` nếu nó mang tên này; có thể thêm điều kiện `!dir.equals(root)`.

### 6.4. Chính sách lỗi: fail-fast hay bỏ qua có ghi nhận?

`SimpleFileVisitor` mặc định **ném lại** nhiều lỗi I/O. Nếu ứng dụng cần quét “best effort” (cố gắng lấy phần đọc được) và đánh dấu kết quả **không đầy đủ**, có thể override:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc) {
    System.err.println("Bỏ qua " + file + ": " + exc.getMessage());
    return FileVisitResult.CONTINUE;
}
```

Đây là **một phần của visitor**, không phải method đứng riêng trong một class bất kỳ. Không nên âm thầm trả `CONTINUE` mà không thông báo: kết quả thống kê sẽ thiếu một số file. Tương tự, khi `postVisitDirectory(dir, exc)` nhận `exc != null`, ứng dụng phải có chính sách ghi nhận và tiếp tục hoặc ném lỗi nhất quán.

**Lưu ý:** nếu traversal kết thúc bằng IOException hoặc RuntimeException không được xử lý, `walkFileTree` dừng và không đảm bảo một báo cáo hoàn chỉnh được trả về.

## 7. Symbolic link, độ sâu và vòng lặp

### 7.1. Mặc định không duyệt theo liên kết tượng trưng

`Files.walk`, `Files.find` và `Files.walkFileTree` theo mặc định **không theo symbolic link khi quyết định mở thư mục con**. Điều này giúp tránh bất ngờ duyệt sang vị trí khác chỉ vì một entry là link. Tuy nhiên, một symbolic link vẫn có thể xuất hiện trong những mục được liệt kê/viếng thăm.

Phân biệt:

- `Files.isRegularFile(path)` **mặc định có thể theo link** để kiểm tra tệp đích.
- `Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)` kiểm tra entry không đi theo link.
- Trong `Files.find(..., matcher)` hoặc `FileVisitor.visitFile(..., attrs)`, `attrs` được cung cấp theo chính cách traversal đọc thuộc tính, tránh các phép kiểm tra dư thừa.

Khi cần tuyệt đối không duyệt qua liên kết do người dùng có thể sửa, cần thiết kế thêm ranh giới quyền truy cập. Chỉ dùng `normalize()` hoặc `startsWith(root)` **không đủ** để chống toàn bộ trường hợp symbolic-link traversal hay race condition.

### 7.2. FOLLOW_LINKS là lựa chọn có chủ đích

Có thể yêu cầu traversal theo symbolic links:

```java
import java.nio.file.FileVisitOption;
import java.util.stream.Stream;

try (Stream<Path> paths = Files.walk(
        root, 5, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
```

Khi theo link, traversal có thể đi ra ngoài cây thư mục ban đầu theo nghĩa vật lý, gặp mục trùng qua nhiều đường dẫn hoặc tạo vòng lặp. JDK theo dõi các thư mục tổ tiên để phát hiện vòng; khi phát hiện sẽ nêu `FileSystemLoopException`:

- Với `walkFileTree`, lỗi có thể được báo đến `visitFileFailed` để visitor quyết định.
- Với `Files.walk`/`Files.find`, lỗi trong quá trình tiêu thụ có thể được chuyển thành `UncheckedIOException`.

Chỉ bật `FOLLOW_LINKS` khi nghiệp vụ thực sự cần và đã xác định chính sách về quyền truy cập, giới hạn độ sâu, vòng lặp và dữ liệu bị đếm trùng. Một giới hạn độ sâu hữu hạn giúp giới hạn số tầng duyệt, **không bảo đảm** không đi sang đường dẫn nhạy cảm hoặc giải quyết mọi vấn đề bảo mật.

## 8. Xử lý IOException và UncheckedIOException

Với các phương thức trả Stream từ `Files`, có hai thời điểm phát sinh lỗi:

1. **Mở ban đầu:** `Files.list(dir)`, `Files.walk(root)`, `Files.find(...)` và `Files.lines(path)` có thể ném `IOException` trước khi trả về Stream.
2. **Trong lúc tiêu thụ Stream:** truy cập thư mục/tệp có thể thất bại sau khi method đã trả về. Javadoc quy định lỗi I/O này được đóng gói vào `UncheckedIOException`, một runtime exception; ngay cả khi pipeline có `filter` hay `count` vẫn có thể gặp.

Ví dụ chuyển tiếp nguyên nhân I/O về dạng checked trong một API của ứng dụng:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countEntries(Path dir) throws IOException {
    try (Stream<Path> paths = Files.list(dir)) {
        return paths.count();
    } catch (UncheckedIOException exc) {
        throw exc.getCause();
    }
}
```

Khối `try-with-resources` vẫn chạy logic đóng tài nguyên trước khi exception được đưa ra ngoài. `UncheckedIOException.getCause()` cung cấp `IOException` gốc để tầng gọi có thể xử lý nhất quán. Đừng bắt mọi `RuntimeException` rồi trả về danh sách rỗng: điều đó có thể che giấu lỗi quyền, lỗi đĩa hoặc lỗi giải mã ký tự.

### 8.1. try-with-resources và suppressed exception

Khi khối `try` ném một exception, đồng thời lời gọi `close()` cũng ném exception, Java giữ exception từ **thân khối** làm lỗi chính; exception từ đóng tài nguyên được gắn vào `getSuppressed()` của lỗi chính.

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.forEach(System.out::println);
}
```

Nếu phát sinh lỗi, hãy xem nguyên nhân và `getSuppressed()` khi cần điều tra lỗi đóng tài nguyên. Đóng Stream khi xong **không** có nghĩa là đã xử lý mọi lỗi I/O; try-with-resources chịu trách nhiệm *giải phóng tài nguyên*, còn nghiệp vụ chịu trách nhiệm *xử lý lỗi*.

### 8.2. Không trả Stream còn gắn với directory handle ra ngoài vô tư

Thiết kế có rủi ro:

```java
// Caller phải biết và nhớ đóng tài nguyên.
static Stream<Path> openPaths(Path root) throws IOException {
    return Files.walk(root);
}
```

Method trên **có thể hợp lệ** nếu hợp đồng API ghi rõ caller sở hữu và phải đóng Stream. Nhưng một API báo cáo thường an toàn hơn khi **tự tiêu thụ và đóng** Stream trong cùng method:

```java
static long countRegularFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile).count();
    }
}
```

Khi buộc phải trả một Stream lười để giảm bộ nhớ, hãy ghi rõ điều kiện ownership và luôn sử dụng `try-with-resources` tại nơi nhận Stream.

## 9. Kết hợp Files.walk với Files.lines: hai cấp tài nguyên

`Files.lines(path, charset)` cũng trả `Stream<String>` cần đóng. Nếu duyệt nhiều tệp và đọc từng tệp, cần quản lý vòng đời của **cả traversal Stream lẫn file-content Stream**.

Một cách dễ hiểu (đổi lại, có tạo danh sách tên file trung gian):

```java
// File: CountErrorsDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class CountErrorsDemo {
    static long countErrors(Path dir) throws IOException {
        List<Path> logFiles;

        // 1. Lấy tên tệp trực tiếp và đóng Directory Stream trước.
        try (Stream<Path> entries = Files.list(dir)) {
            logFiles = entries
                .filter(p -> Files.isRegularFile(
                        p, LinkOption.NOFOLLOW_LINKS))
                .filter(p -> p.getFileName()
                        .toString().endsWith(".log"))
                .toList();
        }

        long total = 0;
        // 2. Đọc tuần tự từng file, mỗi file được đóng ngay sau khi đếm.
        for (Path file : logFiles) {
            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                total = Math.addExact(total,
                    lines.filter(line -> line.contains("ERROR")).count());
            }
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        Path dir = args.length == 0 ? Path.of(".") : Path.of(args[0]);
        System.out.println(countErrors(dir));
    }
}
```

Ở ví dụ:

- `Files.list` liệt kê tệp **một cấp**, không tự lấy file dưới thư mục con.
- `Files.lines` đọc lần lượt các dòng được giải mã UTF-8, có `Stream` đọc tệp phải đóng.
- `Math.addExact` phát hiện tràn số `long`.
- `List<Path>` trung gian giúp đóng directory handle **trước** khi mở từng file. Nếu số tên file quá lớn, hãy chọn giải pháp visitor/streaming thay vì tích lũy toàn bộ vào `List`.

Với dữ liệu văn bản không dùng UTF-8, truyền đúng `Charset` theo định dạng file. Đọc byte lỗi encoding hoặc lỗi I/O phát sinh trong quá trình tiêu thụ `lines` có thể trở thành `UncheckedIOException`; cần xử lý theo chính sách của ứng dụng.

**Không nên** mở hàng nghìn `Files.lines` rồi giữ tất cả Stream trong một Collection chờ xử lý về sau; việc này có thể làm cạn file descriptor và tài nguyên hệ thống.

## 10. Hiệu năng, tài nguyên và an toàn vận hành

### 10.1. Lazy không đồng nghĩa “không tốn tài nguyên”

`Files.walk` và `Files.find` tạo Stream lazily: traversal thực hiện dần khi có terminal operation. Nhưng traversal vẫn có thể giữ các directory handle đang mở, đọc metadata và tạo nhiều `Path`. Với cây sâu/lớn, cần chú ý:

- Giới hạn độ sâu hợp lý khi nghiệp vụ cho phép.
- Dùng `count`/tổng hợp streaming thay vì giữ toàn bộ `Path` trong `List` nếu chỉ cần thống kê.
- Tránh `sorted()` trên tập rất lớn nếu không thực sự cần sắp xếp; thao tác này phải xử lý dữ liệu của toàn bộ Stream.
- Với nhu cầu bỏ qua nhánh, dùng `walkFileTree` thay vì lọc hậu kỳ.
- Chỉ bật `FOLLOW_LINKS` nếu đã đánh giá vòng lặp và phạm vi đường dẫn.

### 10.2. Duyệt cây không tạo snapshot nguyên tử

Các API duyệt thư mục là **weakly consistent**: cấu trúc cây có thể thay đổi bởi tiến trình khác trong lúc traversal đang chạy. Có thể xảy ra:

- Tệp tồn tại khi liệt kê nhưng biến mất trước khi mở đọc.
- Kích thước tệp thay đổi sau khi `BasicFileAttributes` được đọc.
- Mục vừa tạo có thể xuất hiện hoặc không xuất hiện trong cùng một lượt quét.
- Việc quét không đảm bảo một bản chụp hệ thống tệp tại một thời điểm cố định.

Với nghiệp vụ yêu cầu nhất quán mạnh (ví dụ sao lưu dữ liệu sống), phải có chiến lược snapshot/lock/giao thức nhất quán bên ngoài API duyệt, không chỉ dựa vào một Stream.

### 10.3. Đường dẫn do người dùng cung cấp cần thêm ranh giới bảo vệ

Không tự ghép một đường dẫn do người dùng nhập rồi giả định `normalize()` làm nó an toàn. Các yếu tố cần xem xét tùy ứng dụng:

- Giới hạn root được phép quét theo quyền truy cập và chính sách của hệ thống.
- Kiểm soát symbolic links và các file system mount point khi thích hợp.
- Xem xét race condition giữa kiểm tra đường dẫn và mở tệp (*time-of-check/time-of-use*).
- Không tự xóa hoặc chỉnh sửa tệp chỉ vì một traversal tìm thấy nó.

Trên các file system provider hỗ trợ, `SecureDirectoryStream` có thể hỗ trợ một số thao tác tương đối với directory handle nhằm giảm rủi ro race condition; cần kiểm tra hỗ trợ và xây giải pháp theo yêu cầu bảo mật thực tế. Đây là chủ đề mở rộng, không phải thuộc tính bảo mật mặc định của `Files.walk`.

### 10.4. Khi nào chọn Visitor thay cho Stream?

Chọn `Files.walkFileTree` khi cần:

- Dừng sớm, bỏ qua nhánh có chủ đích hoặc giới hạn quyền truy cập theo callback.
- Phân biệt lỗi từng file/thư mục và quyết định fail-fast hay tiếp tục có ghi nhận.
- Thu thập thống kê mà không giữ danh sách `Path` lớn.
- Xử lý thư mục theo **postorder** (ví dụ khi cần lập kế hoạch thao tác phụ thuộc con trước cha).

Chọn `Files.walk`/`find` khi cần các pipeline `filter`/`map`/`count` tự nhiên và việc đóng Stream tại cùng scope là rõ ràng.

## 11. Các lỗi hay gặp và cách sửa

| Lỗi hoặc triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| File descriptor tăng, chương trình không giải phóng directory handle | Không đóng `Files.list/walk/find` hoặc `Files.lines` | Luôn dùng `try (Stream<?> s = Files....) { ... }` hoặc cấu trúc đóng tương đương |
| Nghĩ `count()` hoặc `findFirst()` đã đóng Stream | Terminal operation chỉ tiêu thụ pipeline, không tự quản lý close | Đóng trong `finally`/try-with-resources ngay cả khi kết thúc sớm |
| `Files.list(dir)` không thấy tệp trong thư mục con | `list` chỉ duyệt một cấp | Dùng `walk`, `find` hoặc `walkFileTree` |
| `Files.walk(root, 0)` có một phần tử | `root` nằm ở cấp `0` và được đưa vào Stream | Hiểu độ sâu: 0=gốc, 1=con trực tiếp |
| Lọc `node_modules` bằng `Files.walk(...).filter(...)` vẫn tốn thời gian duyệt | Stream filter chỉ chạy khi traversal đã phát ra Path | Dùng `preVisitDirectory` và `SKIP_SUBTREE` |
| Kết quả quét thay đổi thứ tự giữa các lần chạy | Không có cam kết về thứ tự các mục cùng cấp | Sắp xếp nếu cần thứ tự xác định |
| Lỗi `UncheckedIOException` khi gọi `toList()`/`count()` | I/O error xảy ra **sau khi** method trả Stream | Xử lý nguyên nhân `getCause()` và đảm bảo đóng Stream |
| `DirectoryIteratorException` khi duyệt for-each | Lỗi I/O phát sinh lúc lặp `DirectoryStream` | Xử lý `getCause()`, đóng bằng try-with-resources |
| Đếm sai khi có symbolic link | `Files.isRegularFile` mặc định có thể theo link dù traversal không theo thư mục link | Quyết định chính sách rõ ràng; dùng `NOFOLLOW_LINKS` nếu phù hợp |
| `FileSystemLoopException` khi bật FOLLOW_LINKS | Symbolic links tạo vòng tổ tiên | Mặc định không follow; nếu cần, xử lý vòng và chính sách bỏ qua |
| `visitFileFailed` bị bỏ qua khiến báo cáo thiếu file | Callback trả `CONTINUE` mà không ghi nhận | Ghi log/đánh dấu incomplete hoặc ném lỗi để fail-fast |
| `Files.lines` báo lỗi ký tự hoặc dữ liệu không đọc được | Charset không đúng hoặc I/O error trong quá trình đọc | Dùng `Charset` đúng, xử lý `UncheckedIOException` |
| OOM khi gọi `Files.walk(...).toList()` với cây quá lớn | Gom mọi đường dẫn vào bộ nhớ | Dùng tổng hợp streaming/visitor; hạn chế độ sâu |
| Quét từ một thư mục nhưng tệp bị thay đổi giữa chừng | Traversal không tạo snapshot nguyên tử | Thiết kế nhất quán ở tầng filesystem/ứng dụng |

## 12. Checklist thực hành với Java 27

Trước khi đưa một chức năng duyệt tệp vào production, hãy xác nhận:

1. **Phạm vi duyệt:** một cấp hay đệ quy; cần root trong kết quả hay chỉ các phần tử con; giới hạn `maxDepth` là bao nhiêu.
2. **Đóng tài nguyên:** mọi `Files.list`/`walk`/`find`/`lines` đều nằm trong try-with-resources, kể cả `findFirst` và `limit`.
3. **Tách loại dữ liệu:** phân biệt tệp thường, thư mục, symbolic link; quyết định có `NOFOLLOW_LINKS` hay `FOLLOW_LINKS` hay không.
4. **Chính sách lỗi:** lỗi tại lúc mở và khi đang duyệt/đọc có thể khác loại (`IOException` so với `UncheckedIOException`).
5. **Thứ tự:** không giả định thứ tự trong một thư mục là alphabetical; chỉ `sorted()` khi nghiệp vụ cần.
6. **Bộ nhớ:** không gọi `toList()` toàn cây nếu chỉ cần đếm; cân nhắc `walkFileTree` cho cây lớn hoặc skip branch.
7. **Tính nhất quán:** chấp nhận rằng tệp có thể bị đổi/xóa trong quá trình quét, hoặc thiết kế snapshot nếu cần.
8. **Đường dẫn đầu vào:** giới hạn quyền và root theo chính sách bảo mật, không xem `normalize` là cơ chế chặn symlink.
9. **Số cấp tài nguyên:** nếu traversal đồng thời mở nhiều file nội dung, phải đóng từng file kịp thời, tránh tích lũy hàng loạt handle.
10. **Đầu ra trung thực:** nếu bỏ qua lỗi để tiếp tục, ghi nhận danh sách file lỗi hoặc đánh dấu kết quả không đầy đủ.
11. **Kiểm tra thực tế:** thử thư mục rỗng, thư mục sâu, tệp quyền hạn chế, symbolic link, traversal dừng sớm và file thay đổi trong lúc quét.

## Tài liệu tham khảo chính thức

- [`Files` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html) — `list`, `walk`, `find`, `walkFileTree`, `lines`, `newDirectoryStream` và quy tắc đóng tài nguyên.
- [`DirectoryStream<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/DirectoryStream.html) — iterator, việc đóng directory stream và `DirectoryIteratorException`.
- [`SimpleFileVisitor<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/SimpleFileVisitor.html) — hành vi visitor mặc định và callback khi lỗi.
- [`FileVisitResult` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/FileVisitResult.html) — `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [`FileVisitOption` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/FileVisitOption.html) — cấu hình `FOLLOW_LINKS`.
- [`BasicFileAttributes` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html) — thông tin loại tệp, kích thước và thuộc tính khi duyệt.
- [`BaseStream` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/BaseStream.html) — `AutoCloseable`, `close` và `onClose`.
- [`UncheckedIOException` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/UncheckedIOException.html) — biểu diễn lỗi I/O phát sinh trong xử lý lazy Stream.
