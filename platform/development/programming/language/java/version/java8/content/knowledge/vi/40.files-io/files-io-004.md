# Files.walk và giới hạn độ sâu trong Java

**`Files.walk`** là API duyệt cây tệp của `java.nio.file.Files`, xuất hiện từ **Java 8** và vẫn được hỗ trợ trong Java hiện nay. Phương thức tạo ra `Stream<Path>` được điền dần khi tiêu thụ, cho phép duyệt từ một `Path` bắt đầu đến **độ sâu tối đa** do bạn lựa chọn.

Điểm trọng tâm của bài: `maxDepth` **đếm số mức kể từ chính đường dẫn bắt đầu, với gốc ở mức 0**; stream có thể trả cả directory lẫn regular file, và phải **đóng** bằng try-with-resources. `filter` chỉ lọc output, **không ngăn traversal vào nhánh con**. Khi đi theo symbolic links hoặc xử lý cây lớn, cần hiểu cycles, I/O errors và phạm vi bảo mật.

Bài Knowledge thuộc phần **Tệp và I/O**, đi sâu vào cú pháp `Files.walk`, `maxDepth`, stream lazy, điều kiện lọc, xử lý lỗi, so sánh `Files.list` / `Files.find` / `Files.walkFileTree`, và sáu chương trình Java 17+ chạy độc lập đã kiểm thử. API cốt lõi vẫn dùng được từ Java 8; tiện ích `Files.writeString` và `Stream.toList` trong các chương trình cần JDK mới hơn, được chỉ rõ ở cuối bài.

## 1. Các overload của Files.walk

Hai overload chính:

```java
Files.walk(Path start, FileVisitOption... options);
Files.walk(Path start, int maxDepth,
           FileVisitOption... options);
```

Đây là dạng lời gọi minh họa, đặt trong một phương thức xử lý `IOException` và đóng stream kết quả.

| Tham số / kết quả | Ý nghĩa |
| --- | --- |
| `start` | Đường dẫn bắt đầu, có thể là directory hoặc regular file |
| `maxDepth` | Giới hạn các mức truy cập tính từ `start`, không được âm |
| `FileVisitOption...` | Tùy chọn duyệt, đáng chú ý nhất là `FOLLOW_LINKS` |
| `Stream<Path>` | Các `Path` phát ra dần khi stream được tiêu thụ |
| `IOException` | Lỗi truy cập `start` khi tạo stream |
| `UncheckedIOException` | Có thể là lỗi I/O phát sinh trong khi stream đang duyệt |

`Files.walk(start)` hoạt động như `Files.walk(start, Integer.MAX_VALUE)` theo hợp đồng API. Nó **không** mặc định chỉ duyệt một cấp. Thao tác diễn ra theo chiều sâu trước (**depth-first**), directory trước các phần tử của chính directory đó; **thứ tự các mục cùng cấp không được đảm bảo**.

### Pattern sử dụng cơ bản

```java
Path root = Path.of("data");

try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
```

Đoạn này đặt trong method có `import java.nio.file.*;`, `import java.util.stream.Stream;` và khai báo `throws IOException` hoặc xử lý exception. `Path.of` là API Java 11+; với Java 8 dùng `Paths.get("data")`. Trên môi trường thực, directory `data` phải tồn tại và có quyền truy cập.

**Nên ghi giới hạn rõ ràng** thay vì dùng overload không giới hạn đối với root do người dùng truyền vào. Tuy vậy, `maxDepth` không tự kiểm soát số file, số bytes, thời gian hay quyền truy cập.

## 2. Định nghĩa mức 0, 1, 2, 3

Xét cây:

```text
root/                    depth 0
├── root.txt             depth 1
├── one/                 depth 1
│   ├── a.txt            depth 2
│   └── deep/            depth 2
│       └── c.log        depth 3
└── two/                 depth 1
    └── b.md             depth 2
```

- `Files.walk(root, 0)` chỉ có **root**.
- `Files.walk(root, 1)` có root, `root.txt`, `one`, `two`.
- `Files.walk(root, 2)` có cả `one/a.txt`, `one/deep`, `two/b.md`.
- `Files.walk(root, 3)` thêm `one/deep/c.log`.
- Một directory đúng tại maxDepth **vẫn có thể được phát** nhưng children sâu hơn không được duyệt.

**Depth không phải số thư mục trong đường dẫn tuyệt đối.** Nó được tính tương đối so với `start`. Nếu root là `C:\work\project`, bản thân nó vẫn ở mức **0**.

`Files.walk(root, 1)` **không** đồng nghĩa “các file trực tiếp” vì còn có cả chính root và các directory con. Nếu cần chỉ tệp thường, lọc thêm `Files.isRegularFile`.

## 3. Chương trình Java: kiểm tra bốn mức độ sâu

Tệp `DepthMatrixDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class DepthMatrixDemo {
    static String rel(Path root, Path p) {
        Path r = root.relativize(p);
        return r.toString().isEmpty()
                ? "."
                : r.toString().replace('\\', '/');
    }

    static List<String> names(
            Path root, int depth) throws IOException {
        try (Stream<Path> paths = Files.walk(root, depth)) {
            return paths.map(p -> rel(root, p))
                    .sorted()
                    .toList();
        }
    }

    static void cleanup(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path p : paths.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("walk-depth-");
        try {
            Files.createDirectories(root.resolve("one/deep"));
            Files.createDirectories(root.resolve("two"));
            Files.writeString(root.resolve("root.txt"), "r");
            Files.writeString(root.resolve("one/a.txt"), "a");
            Files.writeString(root.resolve("one/deep/c.log"), "c");
            Files.writeString(root.resolve("two/b.md"), "b");

            System.out.println(
                    "depth 0 = " + names(root, 0));
            System.out.println(
                    "depth 1 = " + names(root, 1));
            System.out.println(
                    "depth 2 = " + names(root, 2));
            System.out.println(
                    "depth 3 = " + names(root, 3));
        } finally {
            cleanup(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 DepthMatrixDemo.java
java DepthMatrixDemo
```

```text
depth 0 = [.]
depth 1 = [., one, root.txt, two]
depth 2 = [., one, one/a.txt, one/deep, root.txt, two, two/b.md]
depth 3 = [., one, one/a.txt, one/deep, one/deep/c.log, root.txt, two, two/b.md]
```

**Dấu chấm trong output biểu diễn chính root**, không phải tên directory phụ. `root.relativize(root).toString()` cho chuỗi rỗng, hàm `rel` đổi thành dấu `.` cho dễ đọc. `replace('\\','/')` chuẩn hóa cách in tương đối để kết quả giống nhau trên Windows và Linux.

Các `Path` được sắp xếp bằng `sorted()` để stdout không phụ thuộc thứ tự filesystem. **Không suy ra Files.walk tự sắp xếp theo tên**. Hàm cleanup xóa chỉ cây tạm do chương trình tạo, từ file con lên directory cha.

## 4. Giới hạn độ sâu khác lọc kết quả

Hai thao tác diễn ra ở hai tầng:

```java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(Files::isRegularFile)
         .filter(p -> p.getFileName()
                 .toString().endsWith(".txt"))
         .forEach(System.out::println);
}
```

- `Files.walk(root, 2)` quyết định **những path nào được phép đi qua trong traversal**.
- `filter(Files::isRegularFile)` loại các directory khỏi **output**, nhưng các directory ở depth nhỏ hơn 2 vẫn được mở để duyệt xuống sâu hơn.
- `endsWith(".txt")` lọc theo hậu tố tên file.
- `forEach` là terminal operation làm stream bắt đầu được tiêu thụ.
- Cả hai `filter` **không có chức năng cắt nhánh**.

Nếu một directory `one` bị loại bởi `isRegularFile` thì `one/a.txt` vẫn có thể xuất hiện. Nó thuộc cùng cây traversal và nằm trong giới hạn depth. Chỉ những đường dẫn vượt quá maxDepth mới không được source đi tới.

## 5. Chương trình Java: tìm .txt theo từng depth

Tệp `SearchAtDepthDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class SearchAtDepthDemo {
    static String rel(Path root, Path p) {
        return root.relativize(p)
                .toString()
                .replace('\\', '/');
    }

    static List<String> txt(
            Path root, int depth) throws IOException {
        try (Stream<Path> paths = Files.walk(root, depth)) {
            return paths.filter(Files::isRegularFile)
                    .filter(p -> p.getFileName()
                            .toString().endsWith(".txt"))
                    .map(p -> rel(root, p))
                    .sorted().toList();
        }
    }

    static void cleanup(Path root) throws IOException {
        try (Stream<Path> ps = Files.walk(root)) {
            for (Path p : ps.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("walk-filter-");
        try {
            Files.createDirectories(root.resolve("a/b"));
            Files.writeString(root.resolve("top.txt"), "x");
            Files.writeString(root.resolve("a/near.txt"), "a");
            Files.writeString(root.resolve("a/b/deep.txt"), "b");
            Files.writeString(root.resolve("a/ignore.md"), "n");

            System.out.println(
                    "txt depth 1 = " + txt(root, 1));
            System.out.println(
                    "txt depth 2 = " + txt(root, 2));
            System.out.println(
                    "txt depth 3 = " + txt(root, 3));
        } finally {
            cleanup(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 SearchAtDepthDemo.java
java SearchAtDepthDemo
```

```text
txt depth 1 = [top.txt]
txt depth 2 = [a/near.txt, top.txt]
txt depth 3 = [a/b/deep.txt, a/near.txt, top.txt]
```

Suffix `.txt` đang phân biệt hoa/thường. `file.TXT` sẽ không qua `endsWith(".txt")`. Nếu nghiệp vụ muốn không phân biệt hoa/thường, cần chuẩn hóa tên (thường dùng `toLowerCase(Locale.ROOT)`) hoặc quy định `PathMatcher` tương ứng file system.

Điểm then chốt: `depth=1` tìm đúng file ngay dưới root; `depth=2` có thể tìm thêm file trong một thư mục con; `depth=3` cho phép file trong hai thư mục con lồng nhau.

## 6. `start` có thể là tệp thường

`Files.walk` không bắt `start` phải là directory:

```java
try (Stream<Path> s = Files.walk(filePath, 0)) {
    System.out.println(s.count());
}
```

Nếu `filePath` là một file tồn tại, kết quả là 1: chính file đó. Dùng `Files.walk(filePath,99)` cũng vẫn là một entry vì file không có directory children.

Ngược lại, `Files.walk(directory,0)` phát đúng directory đó; nó **không phát** tất cả con trực tiếp.

Nếu start không tồn tại, quyền truy cập bị từ chối hoặc file system lỗi, `Files.walk` có thể ném `IOException` ngay ở lúc tạo stream. Đối với local disk tiêu chuẩn, path không tồn tại thường dẫn đến `NoSuchFileException`, nhưng **không nên coi subtype cụ thể là một bảo đảm tuyệt đối cho mọi provider**.

## 7. `maxDepth` không được âm

`Files.walk(start, -1)` ném `IllegalArgumentException`. Trong dịch vụ nhận số độ sâu từ client, nên kiểm tra trước:

```java
if (depth < 0 || depth > configuredMaxDepth) {
    throw new IllegalArgumentException("Invalid depth");
}
try (Stream<Path> paths = Files.walk(root, depth)) {
    // Tiêu thụ stream có phạm vi đã được giới hạn.
}
```

Đây là snippet có `root`, `depth` và `configuredMaxDepth` do ứng dụng định nghĩa. Giới hạn trên là **policy riêng**, không phải một giá trị cứng do JDK bắt buộc.

Với overload không có depth, `Files.walk(start)` hoạt động như duyệt đến `Integer.MAX_VALUE`. Đây là giới hạn về cách biểu đạt số mức, **không phải đảm bảo đủ tài nguyên để duyệt cây có hàng triệu tệp**.

## 8. Chương trình Java: edge cases và giá trị âm

Tệp `WalkEdgeCasesDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class WalkEdgeCasesDemo {
    static void cleanup(Path root) throws IOException {
        try (Stream<Path> ps = Files.walk(root)) {
            for (Path p : ps.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("walk-edge-");
        try {
            Path f = Files.writeString(
                    root.resolve("only.txt"), "Hello");

            try (Stream<Path> ps = Files.walk(f, 0)) {
                System.out.println(
                        "file start depth 0 count = " +
                                ps.count());
            }
            try (Stream<Path> ps = Files.walk(f, 99)) {
                System.out.println(
                        "file start depth 99 count = " +
                                ps.count());
            }

            try {
                Files.walk(root, -1);
                System.out.println("negative unexpected success");
            } catch (IllegalArgumentException ex) {
                System.out.println(
                        "negative depth = IllegalArgumentException");
            }

            try {
                Files.walk(root.resolve("missing"), 0);
                System.out.println("missing unexpected success");
            } catch (NoSuchFileException ex) {
                System.out.println(
                        "missing start = NoSuchFileException");
            }
        } finally {
            cleanup(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 WalkEdgeCasesDemo.java
java WalkEdgeCasesDemo
```

```text
file start depth 0 count = 1
file start depth 99 count = 1
negative depth = IllegalArgumentException
missing start = NoSuchFileException
```

Đây là fixture tự tạo trên file system mặc định, đã kiểm thử. Trong ứng dụng thật cần xử lý `IOException` rộng hơn, không chỉ `NoSuchFileException`. Với đầu vào âm, exception xuất hiện trước khi có stream để close.

## 9. Stream là lazy, không phải danh sách sẵn

`Files.walk` trả về một stream mà file tree được duyệt dần khi các phần tử được tiêu thụ:

```java
try (Stream<Path> paths = Files.walk(root, 3)) {
    long count = paths
            .filter(Files::isRegularFile)
            .count();
    System.out.println(count);
}
```

- `filter`, `map` là intermediate operations.
- `count`, `forEach`, `findFirst`, `toList` là terminal operations.
- Chỉ khởi tạo `Files.walk` không có nghĩa mọi thư mục đã được đọc.
- Khi duyệt sau lúc gọi, stream có thể mở những directory mới và thực hiện I/O.
- `limit(n)` hoặc `findFirst` có thể dừng tiêu thụ sớm, nhưng không phải phương pháp quản lý an toàn mọi tài nguyên hay deadline.
- Nếu cây được chỉnh sửa trong lúc đi qua, kết quả có thể thay đổi.
- Stream đã được tiêu thụ hoặc đóng thì không được dùng lại như một stream mới.

**Lazy không đồng nghĩa không chiếm tài nguyên.** Nó có thể mở directory handles và đọc attributes trên mỗi entry. Chính vì thế `try-with-resources` là yêu cầu thực tế rất quan trọng.

## 10. Phải đóng stream bằng try-with-resources

JavaDoc quy định stream do `Files.walk` trả về giữ tham chiếu đến **một hoặc nhiều thư mục đang mở**. Dùng:

```java
try (Stream<Path> paths = Files.walk(root, maxDepth)) {
    paths.forEach(this::handle);
}
```

Đây là đoạn minh họa trong class có `handle(Path)` và `maxDepth` đã định nghĩa. Cần import `java.nio.file.*`, `java.util.stream.Stream` và xử lý checked `IOException`. Khi block kết thúc, Java tự gọi `close()` kể cả khi xử lý ném exception.

Không chỉ đặt:

```java
Stream<Path> paths = Files.walk(root);
// ... xử lý nhưng không close: DỄ RÒ directory handles.
```

Trả một stream mở ra khỏi method không hoàn toàn sai nếu chuyển **quyền sở hữu close** rõ ràng cho caller; nhưng nếu API không nói rõ trách nhiệm đóng, dễ làm file descriptors bị giữ lâu và trên Windows có thể cản trở thao tác sửa/xóa directory.

Ngay cả khi stream chỉ đếm vài entry hay dùng `findFirst()`, hãy close vì việc traversal dừng sớm có thể còn thư mục đang mở.

## 11. `Files.list` khác `Files.walk(root,1)` như thế nào?

Cả hai có thể cho thông tin về children trực tiếp, nhưng:
- `Files.list(root)` **không có root** trong stream; chỉ có các entry con trực tiếp, không recursive.
- `Files.walk(root,1)` **có root ở mức 0** rồi các entry con ở mức 1.
- `Files.walk(root,2)` còn có những file một mức sâu hơn bên trong directory con.
- `Files.list` cũng là một **resource-backed Stream** và phải đóng.

Chọn `Files.list` nếu chỉ muốn “liệt kê directory này”; chọn `Files.walk` nếu cần **root hoặc nhiều cấp traversal**. Với cây rất nông, `Files.list` thường làm ý định dễ hiểu hơn.

## 12. Chương trình Java: list, walk và stream đã đóng

Tệp `CloseAndListDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class CloseAndListDemo {
    static String rel(Path root, Path p) {
        return root.relativize(p)
                .toString()
                .replace('\\', '/');
    }

    static void cleanup(Path root) throws IOException {
        try (Stream<Path> ps = Files.walk(root)) {
            for (Path p : ps.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("walk-close-");

        try {
            Files.createDirectories(root.resolve("sub"));
            Files.writeString(root.resolve("top.txt"), "t");
            Files.writeString(
                    root.resolve("sub/deep.txt"), "d");

            try (Stream<Path> list = Files.list(root)) {
                System.out.println(
                        "list immediate = " +
                                list.map(p -> rel(root, p))
                                        .sorted().toList());
            }

            try (Stream<Path> walk = Files.walk(root, 2)) {
                System.out.println(
                        "walk full = " +
                                walk.map(p -> rel(root, p))
                                        .map(s -> s.isEmpty() ? "." : s)
                                        .sorted().toList());
            }

            Stream<Path> paths = Files.walk(root, 2);
            paths.close();

            try {
                paths.count();
            } catch (IllegalStateException ex) {
                System.out.println(
                        "closed stream = IllegalStateException");
            }
        } finally {
            cleanup(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 CloseAndListDemo.java
java CloseAndListDemo
```

```text
list immediate = [sub, top.txt]
walk full = [., sub, sub/deep.txt, top.txt]
closed stream = IllegalStateException
```

Đoạn dùng stream sau `close` là **phản ví dụ có chủ đích**, không phải pattern xử lý production. Với `Files.walk`, một Stream đã đóng/đã thực hiện terminal operation không thể dùng lại để duyệt cây lần hai. Muốn đọc lần khác, mở một stream mới và tiếp tục đảm bảo close.

## 13. `IOException` khi tạo và `UncheckedIOException` khi tiêu thụ

Theo JavaDoc, nếu không truy cập được **đường dẫn bắt đầu**, `Files.walk` có thể ném `IOException` ngay khi gọi. Nếu **sau khi trả về stream** mới phát sinh lỗi I/O trong quá trình truy cập một directory sâu hơn, Java bọc lỗi thành **`UncheckedIOException`**, ném từ thao tác stream đang tiến hành.

Mẫu phân biệt:

```java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.forEach(this::process);
} catch (UncheckedIOException ex) {
    IOException cause = ex.getCause();
    reportWalkFailure(cause);
} catch (IOException ex) {
    reportOpenFailure(ex);
}
```

Đây là snippet trong class có `process(Path)`, `reportWalkFailure` và `reportOpenFailure` được ứng dụng triển khai, không phải chương trình tự chạy. `IOException` được khai báo hoặc catch; `UncheckedIOException` là unchecked wrapper nên có thể xuất hiện khi `count`, `forEach`, `sorted`, `toList` tiếp tục duyệt.

Không catch `Exception` rồi tuyên bố “quét xong” nếu stream bị lỗi nửa chừng. Hệ thống cần ghi nhận **scan incomplete** và chọn chính sách bỏ qua, retry hoặc fail tùy nghiệp vụ.

## 14. `FOLLOW_LINKS` và symbolic links

Mặc định `Files.walk` **không tự theo symbolic directory links** khi traversal. Nếu cần, truyền:

```java
try (Stream<Path> paths =
        Files.walk(root, 3, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
```

Đoạn minh họa trong method có `root`, import `java.nio.file.*` và `java.util.stream.Stream`. Tùy chọn `FOLLOW_LINKS` có thể làm API đi qua symlink đến target directory, kể cả target **nằm ngoài root theo đường dẫn thực**.

Khi FOLLOW_LINKS bật:
- Có thể có symlink **vòng về directory tổ tiên**.
- API phát hiện chu trình và xem đó là lỗi I/O, thường là `FileSystemLoopException`; lỗi phát sinh trong lúc stream duyệt có thể được bọc `UncheckedIOException`.
- Nếu thuộc tính target không đọc được, API có thể thử đọc attributes của chính link.
- Quyền tạo/đọc symlink phụ thuộc OS, filesystem và permission.
- Độ sâu chỉ giới hạn **các mức traverse**, **không phải sandbox**.

Không dùng FOLLOW_LINKS tùy tiện cho đường dẫn do người dùng chưa tin cậy cung cấp. Một path trông nằm trong root có thể đi qua link tới khu vực khác trên hệ thống. Cần áp chính sách file access/OS permissions và kiểm tra target phù hợp.

## 15. `Files.isRegularFile` và LinkOption riêng biệt

Dù traversal mặc định không theo symbolic directory links, việc lọc:

```java
paths.filter(Files::isRegularFile);
```

sử dụng quy tắc của **`Files.isRegularFile`**, mặc định có thể theo symbolic link để xét loại **target**. Đây là thao tác đọc thuộc tính độc lập với `FileVisitOption` đã truyền vào `Files.walk`.

Muốn kiểm tra chính link **không theo target**:

```java
paths.filter(p ->
        Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS));
```

Các snippet giả định `paths` là Stream còn mở, import `java.nio.file.*`. `NOFOLLOW_LINKS` ảnh hưởng attribute query này; nó không phải công tắc bảo mật hoàn chỉnh cho mọi đường dẫn hay mọi lệnh mở file.

Một ứng dụng có yêu cầu bảo mật nên kiểm soát cả **symlink traversal, path resolution, TOCTOU, mount points và quyền OS**, không chỉ một boolean.

## 16. `Files.find` nhận BasicFileAttributes để lọc

`Files.find` (Java 8+) có dạng:

```java
try (Stream<Path> found =
        Files.find(root, 2,
                (path, attrs) ->
                        attrs.isRegularFile()
                        && attrs.size() >= 1024)) {

    found.forEach(System.out::println);
}
```

`attrs` là `BasicFileAttributes` đã được đọc khi duyệt. Nếu pipeline của bạn cần kiểm tra loại file, size hoặc metadata, `Files.find` có thể tránh đọc lại attributes so với một chuỗi `Files.walk(...).filter(p -> Files.size(p)...)`.

Nhưng `Files.find` **không** tự prune subtree theo matcher. Nó có `maxDepth` giống Files.walk, và cũng có resource-backed stream cần close. Cân nhắc sự khác nhau khi cần file metadata, không xem một phương thức luôn nhanh hơn tất cả phương thức kia.

## 17. Chương trình Java: Files.find và giới hạn sâu

Tệp `FindAttributesDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class FindAttributesDemo {
    static String rel(Path root, Path p) {
        return root.relativize(p)
                .toString()
                .replace('\\', '/');
    }

    static void cleanup(Path root) throws IOException {
        try (Stream<Path> ps = Files.walk(root)) {
            for (Path p : ps.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("walk-find-");

        try {
            Files.createDirectories(root.resolve("nested"));
            Files.writeString(
                    root.resolve("small.txt"),
                    "xy", StandardCharsets.UTF_8);
            Files.writeString(
                    root.resolve("nested/big.txt"),
                    "abcdef", StandardCharsets.UTF_8);
            Files.writeString(
                    root.resolve("nested/no.md"),
                    "123456789", StandardCharsets.UTF_8);

            try (Stream<Path> ps =
                    Files.find(root, 2,
                            (p, a) -> a.isRegularFile()
                                    && a.size() >= 5
                                    && p.toString()
                                            .endsWith(".txt"))) {
                System.out.println(
                        "find large txt = " +
                                ps.map(p -> rel(root, p))
                                        .sorted().toList());
            }

            try (Stream<Path> ps = Files.walk(root, 1)) {
                System.out.println(
                        "walk depth 1 = " +
                                ps.map(p -> rel(root, p))
                                        .filter(s -> !s.isEmpty())
                                        .sorted().toList());
            }
        } finally {
            cleanup(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 FindAttributesDemo.java
java FindAttributesDemo
```

```text
find large txt = [nested/big.txt]
walk depth 1 = [nested, small.txt]
```

`nested/big.txt` sâu 2 và có 6 bytes, khớp suffix. `nested/no.md` có 9 bytes nhưng sai hậu tố, còn `small.txt` có 2 bytes. `walk depth 1` chỉ phát directory `nested` và file `small.txt` trực tiếp. Đây là minh họa rõ ranh giới depth và điều kiện matcher.

## 18. `Files.walkFileTree` để thật sự bỏ qua subtree

`Files.walk` đi qua các directory theo depth và trả một Stream. Một `filter` trên stream **không** quyết định bỏ hẳn việc mở/duyệt directory con.

Ví dụ phản chứng:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p ->
            !p.getFileName().toString().equals("skip"))
         .forEach(System.out::println);
}
```

`skip/hidden.txt` vẫn có thể xuất hiện vì tên cuối của path đó là `hidden.txt`, không phải `skip`. Ngay cả khi filter kiểm tra toàn bộ path để bỏ con của `skip` khỏi output, traversal vẫn đã có thể **đi vào nhánh ấy**, khiến chi phí I/O và rủi ro lỗi không giảm như mong muốn.

Muốn prune **từ khi gặp directory**: dùng `Files.walkFileTree` và `FileVisitResult.SKIP_SUBTREE` trả về từ `preVisitDirectory`.

```java
Files.walkFileTree(root,
        new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) {
        if (dir.equals(root.resolve("skip"))) {
            return FileVisitResult.SKIP_SUBTREE;
        }
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là snippet trong method có các import `java.nio.file.*` và `java.nio.file.attribute.BasicFileAttributes`, xử lý `IOException`. `SKIP_SUBTREE` chỉ có ý nghĩa cắt nhánh ở callback `preVisitDirectory`.

## 19. Chương trình Java: Files.walk so với visitor cắt nhánh

Tệp `WalkVsVisitorDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.stream.Stream;

public class WalkVsVisitorDemo {
    static String rel(Path root, Path p) {
        Path r = root.relativize(p);
        return r.toString().isEmpty()
                ? "."
                : r.toString().replace('\\', '/');
    }

    static void cleanup(Path root) throws IOException {
        try (Stream<Path> ps = Files.walk(root)) {
            for (Path p : ps.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("walk-visitor-");

        try {
            Files.createDirectories(root.resolve("keep"));
            Files.createDirectories(root.resolve("skip"));

            Files.writeString(root.resolve("top.txt"), "t");
            Files.writeString(root.resolve("keep/a.txt"), "a");
            Files.writeString(
                    root.resolve("skip/hidden.txt"), "h");

            try (Stream<Path> ps = Files.walk(root, 3)) {
                System.out.println(
                        "walk all = " +
                                ps.map(p -> rel(root, p))
                                        .sorted().toList());
            }

            List<String> found = new ArrayList<>();
            Files.walkFileTree(root,
                    new SimpleFileVisitor<Path>() {

                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {

                    if (dir.equals(root.resolve("skip"))) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    found.add(rel(root, dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {

                    found.add(rel(root, file));
                    return FileVisitResult.CONTINUE;
                }
            });

            Collections.sort(found);
            System.out.println(
                    "pruned visitor = " + found);
        } finally {
            cleanup(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 WalkVsVisitorDemo.java
java WalkVsVisitorDemo
```

```text
walk all = [., keep, keep/a.txt, skip, skip/hidden.txt, top.txt]
pruned visitor = [., keep, keep/a.txt, top.txt]
```

`walkFileTree` không đi vào `skip` vì visitor trả `SKIP_SUBTREE` đúng lúc gặp directory ấy. `Files.walk(root,3)` vẫn phát cả `skip` và file con.

Khi nghiệp vụ muốn **bỏ node_modules, .git hoặc một thư mục cache rất lớn**, `walkFileTree` phù hợp hơn một filter chỉ loại kết quả đầu ra.

## 20. Các callback và chính sách lỗi của walkFileTree

Một `FileVisitor` có các callback:
- `preVisitDirectory(dir, attrs)`: trước khi đi vào directory.
- `visitFile(file, attrs)`: khi gặp file.
- `visitFileFailed(file, error)`: khi không truy cập được một entry.
- `postVisitDirectory(dir, error)`: sau khi duyệt directory hoặc báo lỗi khi duyệt.

`FileVisitResult` có các lựa chọn `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`. Chọn giá trị đúng theo ngữ cảnh và yêu cầu cụ thể. `Files.walkFileTree` có overload nhận `Set<FileVisitOption>` và `maxDepth` để giới hạn mức; rất hữu ích khi cần cắt nhánh và xử lý lỗi từng entry.

Sự khác biệt với `Files.walk` không phải chỉ “API callback vs stream”: visitor cho phép ra quyết định **trước khi đi xuống một subtree**, điều mà `filter` trên Stream<Path> không làm.

## 21. Weak consistency và thay đổi file giữa khi quét

Theo tài liệu, `Files.walk` **weakly consistent**: nó không đóng băng cây thư mục tại một thời điểm. Trong quá trình traversal:
- File có thể bị tạo thêm, xóa hoặc rename.
- Stream có thể thấy hoặc không thấy thay đổi.
- Một `Path` được phát có thể không còn tồn tại khi code mở nó.
- `Files.exists(path)` có thể đúng rồi một thao tác tiếp theo vẫn lỗi (TOCTOU).
- `Files.walk` không tạo snapshot transaction của thư mục.
- Thứ tự entry cùng cấp không được đảm bảo giống nhau trong mọi lần chạy.

Nếu cần backup/mirror có tính nhất quán cao, cần thêm chiến lược snapshot filesystem, quyền truy cập, retry/reconciliation, hoặc policy phù hợp. **Độ sâu giới hạn không đồng nghĩa dữ liệu đã nhất quán**.

## 22. Giới hạn depth không giới hạn số file

Một directory ngay bên dưới root có thể chứa hàng triệu files. Vì vậy `Files.walk(root,1)` tuy nông nhưng vẫn có thể chậm và tốn I/O.

Các giới hạn thực tế cần xét đồng thời:
- `maxDepth` và root được phép.
- Số file/entry tối đa.
- Tổng bytes cần đọc.
- Timeout/deadline và cancellation.
- Quyền truy cập và ranh giới file system.
- Quy tắc symbolic links.
- Bộ nhớ dành cho `sorted` hoặc `toList`.
- Mức đồng thời nếu xử lý nội dung từng file.
- Chính sách khi scan thất bại giữa chừng.

`limit(100)` trong stream chỉ giới hạn số kết quả được tiêu thụ, không tự tạo sandbox hay byte budget. Khi lọc trước `limit`, source có thể phải đi qua nhiều entries mới tìm được 100 kết quả đạt điều kiện.

## 23. Cân nhắc `parallel()`

Dùng `Files.walk(root).parallel()` không nhất thiết nhanh hơn:
- Directory iteration và file metadata là I/O.
- Source traversal có thể không chia workload tốt như một collection trong bộ nhớ.
- Parallel file reads có thể quá tải storage hoặc network mounts.
- Nếu callback có side effects, thứ tự và resource lifecycle phức tạp hơn.
- Exceptions trong pipeline song song cần được xử lý và ghi nhận cẩn thận.

Ưu tiên sequential traversal với depth/budget rõ. Nếu từng file cần công việc CPU hoặc I/O dài, cân nhắc **bounded ExecutorService** xử lý các path riêng, có queue/backpressure và logging lỗi. Cần benchmark trên workload thật trước khi khẳng định tốc độ.

## 24. Truy vấn đường dẫn không tin cậy và bảo mật

`Files.walk` không phải security sandbox. Với đường dẫn do user nhập:
1. Chỉ cho phép root thuộc phạm vi được ủy quyền.
2. Có chính sách xử lý symlink/junction và traversal ngoài phạm vi.
3. Không cho phép FOLLOW_LINKS mặc định nếu không cần.
4. Xem xét filesystem changes giữa lúc kiểm tra và lúc mở file.
5. Giới hạn độ sâu, tổng entry, thời gian, bytes.
6. Không coi `Path.normalize()` một mình là giải pháp đầy đủ cho symlink/TOCTOU.
7. Không tự động xóa/copy dữ liệu thật từ kết quả scan thiếu kiểm duyệt.
8. Dựa vào OS permissions, boundary controls và API file access phù hợp.

Bản thân maxDepth chỉ giảm số mức có thể đi qua, **không thể ngăn một symlink hợp lệ trỏ đến một nơi không được phép** nếu FOLLOW_LINKS được bật. Root directory cũng phải được xác thực trước khi scan.

## 25. Mã truy vấn điển hình trong một service

Bài toán: lấy một danh sách .txt nằm trong tối đa hai mức tính từ root.

```java
List<Path> result;

try (Stream<Path> paths = Files.walk(root, 2)) {
    result = paths
            .filter(Files::isRegularFile)
            .filter(p -> p.getFileName()
                    .toString().endsWith(".txt"))
            .sorted()
            .toList();
}
```

Đây là snippet Java 17+ trong method có `Path root`, import `java.nio.file.*`, `java.util.*`, `java.util.stream.*` và xử lý `IOException`. Nó chính xác với quy tắc depth nhưng **chưa phải complete service security policy**: cần validate root, giới hạn output, phân loại lỗi và xác định trường hợp file tree bị thay đổi.

Với cây lớn, tránh thu thập mọi file vào `List` nếu không cần. Có thể xử lý tuần tự theo từng path/batch trong terminal operation và đóng stream sớm nhất có thể.

## 26. Khác biệt phiên bản: Java 8 và Java 17+

| API | Phiên bản được giới thiệu | Vai trò |
| --- | --- | --- |
| `Files.walk` | Java 8 | Trọng tâm bài, vẫn hiện hành |
| `Files.find` | Java 8 | Tìm path dùng attributes và maxDepth |
| `Files.list` | Java 8 | Liệt kê một cấp |
| `Files.walkFileTree` | Java 7 | Duyệt cây bằng visitor, vẫn hiện hành |
| `Files.writeString` | Java 11 | Tạo dữ liệu fixture đơn giản trong ví dụ |
| `Path.of` | Java 11 | Cú pháp Path tiện lợi |
| `Stream.toList()` | Java 16 | Thu thập kết quả stream ở JDK hiện đại |

Nếu code cần biên dịch trên **Java 8**, dùng `Files.write(path, content.getBytes(StandardCharsets.UTF_8))` và `stream.collect(Collectors.toList())`. Nếu code chạy JDK 17+ như sáu chương trình mẫu, các API mới hơn trên vẫn hợp lệ.

Không dùng hướng dẫn cũ dựa trên `java.io.File.listFiles()` và tự viết vòng đệ quy như cách mặc định khi `java.nio.file.Files.walk` hoặc `walkFileTree` giải quyết trực tiếp; những API java.io cũ vẫn tồn tại, nhưng lựa chọn NIO.2 thường diễn đạt tốt hơn nhu cầu traversal, thuộc tính và xử lý lỗi.

## 27. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng depth 0 là rỗng | Root nằm ở mức 0 | `Files.walk(root,0)` cho root |
| Cho rằng depth 1 chỉ chứa file | Root và directory con cũng có | Lọc `isRegularFile` |
| Nhầm `Files.list` với `Files.walk(root,1)` | list không trả root | Chọn đúng API |
| Nhầm depth tương đối với độ sâu tuyệt đối path | Root được tính là 0 | Đếm cạnh từ start |
| Muốn file depth 3 nhưng truyền 2 | Vượt giới hạn | Chọn depth 3 |
| Chỉ `filter` directory cần skip | Không prune source traversal | `walkFileTree` + `SKIP_SUBTREE` |
| Không đóng stream | Directory handles có thể bị giữ | Try-with-resources |
| Chỉ catch checked `IOException` | Lỗi sau khi tạo stream có thể unchecked | Xử lý `UncheckedIOException` |
| Giả định sibling order ổn định | Provider không đảm bảo | `sorted` nếu output cần determinism |
| Dùng `FOLLOW_LINKS` với root không tin cậy | Cycles và traversal ngoài root | Chính sách symlink và OS permissions |
| Cho rằng isRegularFile cũng NOFOLLOW | Attribute query có logic riêng | Truyền `LinkOption.NOFOLLOW_LINKS` |
| Coi maxDepth là giới hạn số entry | Directory nông có thể rộng | Entry/time/byte budget |
| Dùng `sorted` cho toàn bộ cây lớn | Bộ nhớ tăng | Streaming/giới hạn |
| Dùng `parallel` mà không đo | I/O và contention có thể tệ hơn | Benchmark, bounded workers |
| Dùng stream sau terminal operation hoặc close | Stream không tái sử dụng | Mở stream mới |
| Coi kết quả là snapshot cố định | File tree weakly consistent | Retry/reconciliation |
| Dùng `Path.normalize()` làm sandbox | Symlink và TOCTOU vẫn tồn tại | Boundary đúng, OS controls |
| Chọn API theo tên mà không xét cần prune | Filter không cắt subtree | Visitor cho pruning |
| Dùng `Files.writeString` ở runtime Java 8 | API Java 11+ | `Files.write` |
| Dùng `Stream.toList` ở Java 8 | API Java 16+ | `Collectors.toList` |

## 28. Bài tập tự kiểm tra

**Câu 1.** `Files.walk(root,0)` trả gì?  
**Đáp án:** Chính root (nếu truy cập thành công).

**Câu 2.** `Files.walk(root,1)` có gồm root không?  
**Đáp án:** Có, cùng các entry trực tiếp.

**Câu 3.** `root/a/b.txt` nằm ở depth mấy tính từ root?  
**Đáp án:** Depth 2.

**Câu 4.** Một directory ở đúng maxDepth có xuất hiện không?  
**Đáp án:** Có thể xuất hiện, nhưng con sâu hơn không được duyệt.

**Câu 5.** Overload `Files.walk(root)` mặc định duyệt bao nhiêu mức?  
**Đáp án:** Tương đương `Integer.MAX_VALUE`, không giới hạn nhỏ như 1 hoặc 2.

**Câu 6.** `maxDepth=-1` gây gì?  
**Đáp án:** `IllegalArgumentException`.

**Câu 7.** Nếu start là regular file, tăng maxDepth lên 99 có sinh thêm entries không?  
**Đáp án:** Không, vẫn chính file ấy.

**Câu 8.** `filter(Files::isRegularFile)` có ngăn việc mở directory con không?  
**Đáp án:** Không, nó chỉ lọc output.

**Câu 9.** Muốn bỏ toàn bộ subtree thì làm sao?  
**Đáp án:** `Files.walkFileTree` và `SKIP_SUBTREE` từ `preVisitDirectory`.

**Câu 10.** Cách nào chỉ liệt kê entries con trực tiếp mà không chứa root?  
**Đáp án:** `Files.list(root)`.

**Câu 11.** Vì sao Files.walk cần try-with-resources?  
**Đáp án:** Stream có thể giữ open directory handles.

**Câu 12.** IOException có thể xuất hiện sau khi Files.walk trả stream không?  
**Đáp án:** Có, dưới dạng `UncheckedIOException` khi stream duyệt.

**Câu 13.** Stream trả về theo thứ tự tên file đã sắp xếp không?  
**Đáp án:** Không, cần `sorted` nếu cần.

**Câu 14.** Tree bị thay đổi trong lúc duyệt, kết quả là snapshot không?  
**Đáp án:** Không, stream weakly consistent.

**Câu 15.** Mặc định có đi theo symbolic links không?  
**Đáp án:** Không tự đi theo khi traversal, trừ khi bật `FOLLOW_LINKS`.

**Câu 16.** FOLLOW_LINKS có thể gặp cycle không?  
**Đáp án:** Có; có thể ném `FileSystemLoopException`.

**Câu 17.** maxDepth có thay thế sandbox security được không?  
**Đáp án:** Không. Symlink, permission và path resolution cần policy riêng.

**Câu 18.** `Files.find` được lợi gì?  
**Đáp án:** Có `BasicFileAttributes` trong matcher, tránh một số lần đọc lại attributes.

**Câu 19.** `Files.walk(root,1)` có thể duyệt rất nhiều tệp không?  
**Đáp án:** Có, nếu root có rất nhiều entries con trực tiếp.

**Câu 20.** `Files.writeString` và `Stream.toList()` có phải Java 8 không?  
**Đáp án:** Không; chúng được bổ sung ở Java 11 và Java 16.

## 29. Tổng kết

- `Files.walk` là API Java 8 vẫn còn áp dụng để duyệt cây qua `Stream<Path>`.
- **Depth được tính từ `start`, gốc ở 0**, không phải từ filesystem root tuyệt đối.
- `maxDepth=0` trả start, `maxDepth=1` trả start và entries trực tiếp, các levels sâu hơn cần độ sâu tương ứng.
- `Files.walk(start)` không truyền depth tương đương tìm đến mức `Integer.MAX_VALUE`.
- **Filter chỉ thay output, không prune subtree**; muốn cắt nhánh dùng `walkFileTree` và `SKIP_SUBTREE`.
- Stream **lazy, weakly consistent và resource-backed**; phải đóng bằng try-with-resources.
- Phân biệt lỗi `IOException` lúc mở và `UncheckedIOException` khi đang duyệt.
- Mặc định không follow directory symlinks; `FOLLOW_LINKS` cần xử lý chu trình và boundary.
- `Files.list` cho một cấp, `Files.find` lọc bằng attributes, `walkFileTree` có callback và quyền cắt nhánh.
- Không coi maxDepth là giới hạn số entries, bytes, thời gian hoặc sandbox. Hãy áp budgets và policies bảo mật/đồng bộ phù hợp.

### Tài liệu API chính thức

- [Oracle Java SE 25 — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `walk`, `list`, `find`, `walkFileTree`, độ sâu, lazy stream, ngoại lệ, đóng tài nguyên.
- [Oracle Java SE 25 — `FileVisitOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileVisitOption.html): tùy chọn `FOLLOW_LINKS`.
- [Oracle Java SE 25 — `FileVisitResult`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Oracle Java SE 25 — `Path`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html): `resolve`, `relativize` và xử lý đường dẫn.
- [Oracle Java SE 25 — `LinkOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` với attribute checks.
- [Oracle Java SE 25 — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/UncheckedIOException.html): I/O exceptions xảy ra khi duyệt stream.
