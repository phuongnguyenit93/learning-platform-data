# Liệt kê và duyệt cây thư mục bằng `Files.list`, `Files.walk` và `Files.find`

## 1. Mục tiêu và bối cảnh

Trong module **`JAVA_STREAM_API`**, một pipeline thường bắt đầu từ nguồn dữ liệu, ghép các thao tác lazy như `filter` và `map`, rồi kết thúc bằng `count`, `collect` hoặc `findFirst`. Ngoài `List`, mảng và dãy số, hệ thống tệp cũng có thể cung cấp một nguồn **`Stream<Path>`**.

Trong Java 8 trở lên, `java.nio.file.Files` có ba phương thức đáng chú ý:

- **`Files.list(dir)`:** liệt kê các mục nằm **trực tiếp** trong một thư mục.
- **`Files.walk(root, ...)`:** duyệt **cây thư mục** từ gốc tới những cấp sâu hơn.
- **`Files.find(root, maxDepth, matcher, ...)`:** duyệt cây và chỉ phát ra đường dẫn khớp một điều kiện dựa trên `Path` và `BasicFileAttributes`.

Khác stream từ collection trong bộ nhớ, các stream này có thể **giữ tài nguyên I/O** như directory handle. Vì vậy, phải đóng chúng bằng `try-with-resources`, kể cả khi terminal operation dừng sớm hoặc thất bại.

Sau bài học, bạn có thể:

1. Chọn đúng `list`, `walk` hay `find` theo phạm vi duyệt.
2. Hiểu ý nghĩa `maxDepth`, đường dẫn gốc và cách lấy tệp thay vì thư mục.
3. Dùng `BasicFileAttributes` để tìm tệp theo loại, dung lượng hoặc thời gian sửa.
4. Xử lý lazy evaluation, các ngoại lệ I/O và vòng đời của nguồn stream.
5. Nhận biết giới hạn khi gặp symbolic link, cây lớn, thứ tự duyệt không xác định và nhu cầu cắt nhánh.
6. Viết những pipeline đếm, tìm kiếm và thống kê tệp có kiểm soát tài nguyên.

Bài thuộc chương **Nguồn vào ra và quản lý tài nguyên**. Những nguyên tắc này cũng quan trọng khi học Spliterator, pipeline song song hoặc Stream Gatherers, nơi việc giữ trạng thái và quản lý tài nguyên cần được cân nhắc cẩn thận.

## 2. Khác biệt nhanh giữa ba API

Giả sử có cấu trúc:

```text
du-lieu/
├── readme.txt
├── src/
│   ├── App.java
│   └── Util.java
└── assets/
    └── logo.png
```

| Phương thức | Phạm vi duyệt | Bao gồm chính `root`? | Kết quả |
| --- | --- | --- | --- |
| `Files.list(root)` | Chỉ các mục trực tiếp của thư mục `root` | Không | `Stream<Path>` |
| `Files.walk(root)` | Cây bắt đầu từ `root`, mặc định mọi độ sâu | Có | `Stream<Path>` |
| `Files.walk(root, 2)` | `root` và các mục ở độ sâu tối đa 2 | Có | `Stream<Path>` |
| `Files.find(root, 2, matcher)` | Duyệt tới độ sâu 2, chỉ trả đường dẫn matcher chấp nhận | Có nếu matcher khớp gốc | `Stream<Path>` |

Với cây trên, `list` thấy `readme.txt`, `src`, `assets`; `walk` còn thấy chính `du-lieu` và các tệp sâu hơn; `find` có thể trả riêng `App.java` và `Util.java`.

**Thứ tự các mục con không được bảo đảm theo bảng chữ cái.** `walk` duyệt theo chiều sâu (*depth-first*), nhưng thứ tự các mục anh em phụ thuộc hệ thống tệp. Nếu báo cáo cần thứ tự ổn định, hãy sắp xếp tường minh, đồng thời xét chi phí bộ nhớ.

## 3. Ví dụ Java 8 hoàn chỉnh: thử cả ba phương thức

Chương trình sau tự tạo một cây nhỏ trong thư mục tạm và dọn dẹp khi kết thúc. Việc dọn sử dụng `Files.walk` trên **cây tạm do chương trình tạo**; không sao chép logic xóa sang thư mục thật nếu chưa xác minh phạm vi.

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Stream;

public class ThuFilesStream {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("stream-files-demo-");

        try {
            Path src = Files.createDirectories(root.resolve("src"));
            Files.createDirectories(root.resolve("assets"));
            Files.write(root.resolve("readme.txt"),
                Arrays.asList("Tai lieu"), StandardCharsets.UTF_8);
            Files.write(src.resolve("App.java"),
                Arrays.asList("class App {}"), StandardCharsets.UTF_8);
            Files.write(src.resolve("Util.java"),
                Arrays.asList("class Util {}"), StandardCharsets.UTF_8);

            System.out.println("LIST:");
            try (Stream<Path> entries = Files.list(root)) {
                entries.map(p -> p.getFileName().toString())
                    .sorted()
                    .forEach(System.out::println);
            }

            System.out.println("WALK:");
            try (Stream<Path> paths = Files.walk(root, 2)) {
                paths.map(p -> {
                    String r = root.relativize(p).toString();
                    return r.isEmpty() ? "." : r;
                })
                .sorted()
                .forEach(System.out::println);
            }

            System.out.println("FIND:");
            try (Stream<Path> matches = Files.find(root, 2,
                    (p, attrs) -> attrs.isRegularFile()
                        && p.getFileName() != null
                        && p.getFileName().toString().endsWith(".java"))) {
                matches.map(p -> root.relativize(p).toString())
                    .sorted()
                    .forEach(System.out::println);
            }
        } finally {
            // Chỉ xóa nội dung của thư mục tạm đã tạo.
            try (Stream<Path> paths = Files.walk(root)) {
                paths.sorted(Comparator.reverseOrder())
                    .forEach(p -> {
                        try {
                            Files.deleteIfExists(p);
                        } catch (IOException ex) {
                            throw new UncheckedIOException(ex);
                        }
                    });
            }
        }
    }
}
```

Kết quả mang ý nghĩa:

```text
LIST:
assets
readme.txt
src

WALK:
.
assets
readme.txt
src
src/App.java
src/Util.java

FIND:
src/App.java
src/Util.java
```

Trên Windows, dấu phân cách đường dẫn trong ví dụ `WALK` và `FIND` có thể là dấu gạch chéo ngược thay vì dấu `/`. Dấu `.` là đường dẫn tương đối của chính gốc `root`.

Chương trình cố ý dùng `sorted` để dễ đối chiếu kết quả. Với cây rất lớn, `sorted` thường cần nhận đủ các phần tử trước khi phát kết quả đã sắp xếp.

## 4. `Files.list`: duyệt một cấp

Chữ ký:

```java
public static Stream<Path> list(Path dir) throws IOException
```

`Files.list` trả các `Path` ứng với **mục trực tiếp** bên trong thư mục, gồm tệp, thư mục con và các mục khác. Nó không duyệt tiếp xuống bên dưới và không bao gồm chính `dir`.

Ví dụ một chương trình đọc thư mục đã tồn tại:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class LietKeThuMuc {
    public static void main(String[] args) throws IOException {
        Path dir = Paths.get("du-lieu");

        try (Stream<Path> entries = Files.list(dir)) {
            entries.forEach(System.out::println);
        }
    }
}
```

Điều kiện chạy: thư mục `du-lieu` phải tồn tại tương ứng với thư mục làm việc của tiến trình. Nếu đường dẫn không tồn tại, không phải thư mục hoặc thiếu quyền truy cập, API có thể báo lỗi I/O.

### 4.1. Chỉ lấy tệp thường

```java
Path dir = Paths.get("du-lieu");

try (Stream<Path> entries = Files.list(dir)) {
    entries.filter(Files::isRegularFile)
        .forEach(System.out::println);
}
```

`Files.isRegularFile(path)` kiểm tra loại tệp, mặc định **có thể theo symbolic link** tới tệp đích. Nếu nghiệp vụ chỉ muốn tệp thường, không tính symbolic link, dùng `Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)`.

### 4.2. Đếm mục trực tiếp

```java
try (Stream<Path> entries = Files.list(dir)) {
    long tongMuc = entries.count();
    System.out.println(tongMuc);
}
```

Đếm ở đây bao gồm **cả thư mục con**. Thêm `filter(Files::isRegularFile)` nếu chỉ cần đếm tệp thường ở đúng cấp hiện tại.

Đừng thay `list(root)` bằng `walk(root)` cho yêu cầu một cấp đơn giản: `walk` bao gồm gốc và có thể duyệt sâu hơn rất nhiều.

## 5. `Files.walk`: duyệt cây và giới hạn độ sâu

Hai overload từ Java 8:

```java
public static Stream<Path> walk(
    Path start,
    FileVisitOption... options
) throws IOException;

public static Stream<Path> walk(
    Path start,
    int maxDepth,
    FileVisitOption... options
) throws IOException;
```

`walk` tạo nguồn duyệt **depth-first** bắt đầu từ `start`; `start` cũng là một phần tử của kết quả. Mặc định traversal không đi theo symbolic link để vào cây thư mục đích.

### 5.1. Tìm tất cả tệp `.java` trong cây

```java
Path root = Paths.get("du-lieu");

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
        .filter(p -> p.getFileName() != null)
        .filter(p -> p.getFileName().toString().endsWith(".java"))
        .forEach(System.out::println);
}
```

`filter` chỉ ảnh hưởng tới **đường dẫn được phát ra kết quả**, không đồng nghĩa với việc ngăn `walk` duyệt bên trong một thư mục không khớp.

### 5.2. Ý nghĩa `maxDepth`

```text
root/                      depth = 0
├── a.txt                  depth = 1
└── src/                   depth = 1
    ├── App.java           depth = 2
    └── nested/            depth = 2
        └── More.java      depth = 3
```

| Lời gọi | Kết quả có thể chứa |
| --- | --- |
| `Files.walk(root, 0)` | Chỉ đường dẫn `root`. |
| `Files.walk(root, 1)` | Gốc và mọi mục trực tiếp bên dưới. |
| `Files.walk(root, 2)` | Thêm `App.java` và `nested`. |
| `Files.walk(root, 3)` | Thêm `More.java`. |
| `Files.walk(root)` | Toàn bộ độ sâu mà traversal có thể đi tới. |

`maxDepth` phải **không âm**. Độ sâu của gốc là 0. `Files.walk(root, 1)` gần với liệt kê một cấp nhưng **vẫn gồm chính root**:

```java
try (Stream<Path> paths = Files.walk(root, 1)) {
    paths.filter(p -> !p.equals(root))
        .forEach(System.out::println);
}
```

Muốn liệt kê một cấp mà không có gốc, `Files.list(root)` vẫn rõ nghĩa hơn.

### 5.3. Tên tệp và đường dẫn tương đối

```java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.filter(p -> p.getFileName() != null)
        .filter(p -> p.getFileName().toString().startsWith("Test"))
        .map(root::relativize)
        .forEach(System.out::println);
}
```

`getFileName()` lấy phần tên cuối, khác với kiểm tra toàn bộ đường dẫn. `root.relativize(p)` giúp báo cáo bớt phụ thuộc vị trí cài đặt; các path trong ví dụ cùng hệ thống tệp và đều được sinh từ `root`.

## 6. `Files.find`: tìm kiếm bằng thuộc tính tệp

Chữ ký:

```java
public static Stream<Path> find(
    Path start,
    int maxDepth,
    BiPredicate<Path, BasicFileAttributes> matcher,
    FileVisitOption... options
) throws IOException;
```

Tham số `matcher` nhận đồng thời:

- `Path path`: đường dẫn đang xét.
- `BasicFileAttributes attrs`: metadata cơ bản có được khi duyệt, gồm loại, kích thước và thời gian sửa.

Khác với `Files.walk(...).filter(...)`, matcher của `Files.find` có thể sử dụng các thuộc tính đã đọc trong quá trình duyệt, tránh tự gọi `Files.readAttributes` chỉ để kiểm tra cùng thông tin thêm một lần nữa.

### 6.1. Tìm tệp Java đến độ sâu 5

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class TimTepJava {
    public static void main(String[] args) throws IOException {
        Path root = Paths.get("du-lieu");

        try (Stream<Path> matches = Files.find(
                root,
                5,
                (p, attrs) ->
                    attrs.isRegularFile()
                    && p.getFileName() != null
                    && p.getFileName().toString().endsWith(".java")
            )) {
            matches.forEach(System.out::println);
        }
    }
}
```

### 6.2. Tìm tệp lớn hơn 10 MiB

```java
long nguong = 10L * 1024 * 1024;

try (Stream<Path> matches = Files.find(
        root,
        Integer.MAX_VALUE,
        (p, attrs) -> attrs.isRegularFile()
            && attrs.size() > nguong
    )) {
    matches.forEach(System.out::println);
}
```

`attrs.size()` thường biểu diễn độ dài tệp tính bằng byte. Đừng suy diễn kích thước thư mục từ giá trị metadata của chính directory entry; nó không phải tổng kích thước tệp con.

### 6.3. Tìm tệp sửa sau một mốc thời gian

```java
import java.nio.file.attribute.FileTime;
import java.time.Instant;

FileTime moc = FileTime.from(
    Instant.parse("2026-01-01T00:00:00Z")
);

try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, attrs) -> attrs.isRegularFile()
            && attrs.lastModifiedTime().compareTo(moc) > 0
    )) {
    matches.forEach(System.out::println);
}
```

Dùng `FileTime` giúp làm rõ mốc thời gian, nhưng không biến metadata thành một **snapshot bất biến**: tệp có thể bị sửa hoặc xóa trong khi đang duyệt.

### 6.4. `find` có tự bỏ qua thư mục không khớp không?

Không nên hiểu `matcher` là lệnh cắt nhánh. Nó quyết định **đường dẫn nào được trả về**, nhưng một thư mục không khớp vẫn có thể cần được mở để kiểm tra các tệp con.

Nếu mục tiêu là **không đi vào thư mục build**, một bộ lọc kết quả đơn thuần như `!p.toString().contains("build")` vừa có thể loại nhầm tệp hợp lệ, vừa không bảo đảm cắt toàn bộ subtree. Dùng `Files.walkFileTree` với `SKIP_SUBTREE` khi cần quyền điều khiển traversal theo nhánh.

## 7. Đóng stream: `try-with-resources` là bắt buộc

Các stream nguồn I/O này có thể giữ directory handle mở trong suốt quá trình duyệt. Hãy đóng cả khi chỉ `count` hoặc `findFirst`:

```java
try (Stream<Path> paths = Files.walk(root)) {
    long soTep = paths
        .filter(Files::isRegularFile)
        .count();

    System.out.println(soTep);
} // close() tự động khi kết thúc khối try
```

`collect` và `count` **không tự bảo đảm đóng** stream nguồn. `try-with-resources` giải phóng tài nguyên khi xong hoặc gặp ngoại lệ.

### 7.1. Sai: trả stream từ trong khối `try`

```java
// KHÔNG NÊN: stream trả ra đã bị đóng.
static Stream<Path> timSai(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile);
    }
}
```

Khi phương thức trả về, khối `try` đã kết thúc và stream bị đóng. Code bên ngoài không nên tiêu thụ pipeline này.

Nếu dữ liệu đủ nhỏ, thu kết quả ngay bên trong khối:

```java
import java.util.List;
import java.util.stream.Collectors;

static List<Path> timTep(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile)
            .collect(Collectors.toList());
    }
}
```

`List<Path>` ở đây chỉ lưu đường dẫn, không mở nội dung từng tệp. Với cây khổng lồ, đừng thu hết đường dẫn vào RAM; cân nhắc xử lý từng mục trong phạm vi stream hoặc một API theo batch.

### 7.2. Một stream chỉ tiêu thụ được một lần

```java
try (Stream<Path> entries = Files.list(root)) {
    long soMuc = entries.count();

    // KHÔNG ĐƯỢC: stream đã tiêu thụ.
    // entries.forEach(System.out::println);
}
```

Nếu cần đếm rồi liệt kê, tạo một stream mới từ cùng nguồn, hoặc thu dữ liệu rồi dùng collection nếu dữ liệu nhỏ và yêu cầu phù hợp. `try-with-resources` không làm stream tái sử dụng được.


## 8. Lazy evaluation và các phép kết thúc ngắn mạch

Các stream do `Files.list`, `Files.walk` và `Files.find` trả về được **làm đầy lazily**: hệ thống tệp có thể được duyệt theo nhu cầu của terminal operation thay vì lấy toàn bộ tên tệp trước. Tuy nhiên, **lời gọi tạo stream vẫn có thể làm I/O ban đầu** và ném `IOException` ngay lúc khởi tạo.

### 8.1. Kiểm tra có tệp `.java` hay không

```java
try (Stream<Path> paths = Files.walk(root)) {
    boolean coJava = paths
        .anyMatch(p -> p.getFileName() != null
            && p.getFileName().toString().endsWith(".java"));

    System.out.println(coJava);
}
```

`anyMatch` là terminal operation có khả năng **short-circuit**: có thể dừng khi gặp phần tử thỏa điều kiện. Nhưng do thứ tự các phần tử cùng cấp không được bảo đảm, không được dựa vào việc *tệp cụ thể nào* được kiểm tra đầu tiên.

### 8.2. `limit` giới hạn kết quả, không bảo đảm chỉ đọc đúng bấy nhiêu mục

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.limit(10)
        .forEach(System.out::println);
}
```

Với pipeline này, chỉ có tối đa 10 đường dẫn được chuyển đến `forEach`. Nếu đặt `filter` trước `limit`, hệ thống có thể phải xét nhiều hơn 10 mục để có 10 đường dẫn phù hợp:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p -> p.getFileName() != null)
        .filter(p -> p.getFileName().toString().endsWith(".rare"))
        .limit(10)
        .forEach(System.out::println);
}
```

Nếu không có tệp `.rare`, toàn bộ cây trong phạm vi duyệt có thể được kiểm tra trước khi kết thúc. `limit` không phải cơ chế cắt những thư mục con khỏi quá trình traversal.

### 8.3. `sorted` thường phải quan sát toàn bộ nguồn

```java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.map(p -> root.relativize(p).toString())
        .sorted()
        .limit(10)
        .forEach(System.out::println);
}
```

`sorted` là phép toán trung gian **có trạng thái**: với đầu vào hữu hạn, nó thường cần tập hợp các giá trị trước khi phát kết quả theo thứ tự mới. Vì vậy `sorted().limit(10)` không đồng nghĩa chỉ truy cập 10 đường dẫn. Đảo thành `limit(10).sorted()` có thể giảm dữ liệu phải sắp xếp nhưng cũng **thay đổi yêu cầu**: khi đó chỉ sắp xếp 10 mục đầu được gặp, không phải 10 mục nhỏ nhất trên toàn bộ cây.

Khi chọn các tệp lớn nhất hoặc mới nhất từ cây khổng lồ, có thể cần một thuật toán top-k dùng bộ nhớ hữu hạn thay vì `sorted` trên toàn bộ phần tử.

## 9. Symbolic link và `FOLLOW_LINKS`

Theo mặc định, `Files.walk` và `Files.find` không đi vào một cây thư mục được tham chiếu qua **symbolic link**. Đường dẫn link vẫn có thể được phát ra, nhưng traversal không theo link để duyệt sâu hơn.

Nếu nghiệp vụ thật sự yêu cầu, có thể bật `FileVisitOption.FOLLOW_LINKS`:

```java
import java.nio.file.FileVisitOption;

try (Stream<Path> paths = Files.walk(
        root,
        3,
        FileVisitOption.FOLLOW_LINKS
    )) {
    paths.forEach(System.out::println);
}
```

Phải cân nhắc các nguy cơ:

- Link có thể trỏ **ra ngoài phạm vi thư mục gốc** mà ứng dụng được phép đọc.
- Hai link có thể tạo **chu trình**, dẫn đến lỗi trong quá trình duyệt, ví dụ `FileSystemLoopException`.
- Quyền truy cập hoặc đích của link có thể thay đổi khi đang quét.
- `maxDepth` chỉ giới hạn **độ sâu**, không phải chính sách bảo mật về đường dẫn đích.

**Không bật `FOLLOW_LINKS` mặc định** trong công cụ quét thư mục mà chưa có chính sách về phạm vi và quyền truy cập.

### `Files.isRegularFile` và link có thể cho kết quả dễ nhầm

`Files.isRegularFile(path)` theo symbolic link theo mặc định. Bởi vậy:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
        .forEach(System.out::println);
}
```

`walk` không đi vào thư mục được link trỏ tới, nhưng bộ lọc `isRegularFile` có thể coi một link đến **tệp thường** là tệp thường. Nếu muốn kiểm tra bản thân mục mà không theo link:

```java
import java.nio.file.LinkOption;

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p ->
        Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)
    ).forEach(System.out::println);
}
```

Khi dùng `Files.find`, `BasicFileAttributes` trong matcher phản ánh chính sách theo link của quá trình duyệt; `attrs.isRegularFile()` phù hợp hơn việc gọi một phép kiểm tra thuộc tính mới với chính sách khác.

## 10. Lỗi I/O: `IOException`, `UncheckedIOException` và sự thay đổi của cây

Đọc cây thư mục có thể thất bại vì tệp không tồn tại, không có quyền, thư mục bị di chuyển, symbolic link lỗi hoặc sự cố hệ thống tệp. Hai thời điểm lỗi thường gặp:

| Thời điểm | Loại lỗi tiêu biểu | Vì sao |
| --- | --- | --- |
| Gọi `Files.list` / `Files.walk` / `Files.find` | `IOException` (checked) | Không thể khởi tạo truy cập, mở đường dẫn hoặc lấy thông tin cần thiết. |
| Duyệt trong terminal operation | `UncheckedIOException` | Stream lazy bọc một lỗi I/O phát sinh khi đang đọc thêm phần tử. |
| Chạy lambda thao tác I/O tùy chỉnh | Checked `IOException` cần xử lý trong lambda | Functional interface phổ biến không khai báo checked exception. |

Một phương thức đếm tệp cơ bản:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long demTep(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile).count();
    }
}
```

`IOException` khi khởi tạo được khai báo bằng `throws IOException`; `UncheckedIOException` trong lúc duyệt vẫn có thể lan ra vì là runtime exception.

Nếu lambda gọi trực tiếp một thao tác I/O có checked exception, hãy xử lý tường minh:

```java
import java.io.UncheckedIOException;

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
        .forEach(p -> {
            try {
                System.out.println(Files.size(p));
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
}
```

Trong ứng dụng thực, tầng gọi có thể bắt cả `IOException` và `UncheckedIOException` để báo rõ thư mục và nguyên nhân. Đừng âm thầm bắt mọi lỗi rồi trả về số `0`: "**không có tệp**" khác hoàn toàn "**không đọc được tệp**".

### Tình huống tệp thay đổi giữa lúc kiểm tra và sử dụng

`Path` trong stream chỉ là một đường dẫn, **không phải bản sao nội dung tệp**. Sau khi matcher kết luận `attrs.isRegularFile()`, một tiến trình khác vẫn có thể xóa, đổi quyền hoặc ghi đè tệp trước khi ứng dụng mở nó.

Đó là tình huống *time-of-check to time-of-use* (TOCTOU). Đối với thao tác nhạy cảm hoặc đòi hỏi tính nhất quán, cần xác thực khi thực sự sử dụng tài nguyên và tuân thủ chính sách mở tệp an toàn; không coi kết quả quét metadata là trạng thái bất biến.

## 11. Cắt cả một nhánh thư mục: khi nào chuyển sang `Files.walkFileTree`?

`filter` sau `walk` và `matcher` của `find` chỉ có nhiệm vụ **chọn đường dẫn đưa vào kết quả**. Chúng không phải lệnh tổng quát để **cấm traversal đi vào một thư mục con**.

Khi cần bỏ qua nội dung các thư mục `build`, dùng `Files.walkFileTree` với `FileVisitResult.SKIP_SUBTREE`:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

static void duyetBoQuaBuild(Path root) throws IOException {
    Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult preVisitDirectory(
                Path dir,
                BasicFileAttributes attrs) throws IOException {

            Path ten = dir.getFileName();
            if (!dir.equals(root)
                    && ten != null
                    && ten.toString().equals("build")) {
                return FileVisitResult.SKIP_SUBTREE;
            }
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file,
                BasicFileAttributes attrs) throws IOException {

            if (attrs.isRegularFile()) {
                System.out.println(file);
            }
            return FileVisitResult.CONTINUE;
        }
    });
}
```

`preVisitDirectory` chạy trước khi duyệt nội dung thư mục; `SKIP_SUBTREE` bỏ qua phần bên dưới. `visitFile` nhận những tệp được duyệt.

`walkFileTree` dùng mô hình **visitor callback**, không trả `Stream<Path>`. Nó thích hợp khi cần can thiệp traversal, xử lý lỗi theo từng tệp, sao chép hoặc xóa cây có kiểm soát. Đối với nhu cầu đơn giản "lấy mọi tệp Java trong cây", `Files.find` hay `Files.walk` vẫn dễ đọc hơn.

## 12. Một số công thức thực tế

Các đoạn ngắn dưới đây giả định `Path root` đã tồn tại; khi đặt riêng trong lớp Java, cần các import như `java.nio.file.*`, `java.util.*`, `java.util.stream.*` và `java.io.*`.

### 12.1. Đếm tệp thường ở đúng một cấp

```java
try (Stream<Path> entries = Files.list(root)) {
    long soTep = entries
        .filter(Files::isRegularFile)
        .count();

    System.out.println(soTep);
}
```

### 12.2. Tìm mọi tệp Java nhưng chỉ đến độ sâu ba

```java
try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, attrs) -> attrs.isRegularFile()
            && p.getFileName() != null
            && p.getFileName().toString().endsWith(".java")
    )) {
    matches.forEach(System.out::println);
}
```

### 12.3. Thu đường dẫn về list sau khi đóng nguồn

```java
import java.util.List;
import java.util.stream.Collectors;

List<Path> ketQua;

try (Stream<Path> paths = Files.walk(root, 2)) {
    ketQua = paths.filter(Files::isRegularFile)
        .collect(Collectors.toList());
}

// Có thể dùng List<Path> khi nguồn I/O đã đóng.
System.out.println(ketQua.size());
```

Dữ liệu trong `ketQua` là các `Path`, không phải nội dung tệp. Việc mở tệp qua những path này trong tương lai vẫn có thể thất bại nếu cây đã thay đổi. Thu tất cả đường dẫn về list cũng tiêu tốn bộ nhớ, không phù hợp cho cây không có giới hạn.

### 12.4. Tổng số byte của các tệp ở độ sâu tối đa hai

```java
try (Stream<Path> matches = Files.find(
        root,
        2,
        (p, attrs) -> attrs.isRegularFile()
    )) {
    long tongByte = matches.mapToLong(p -> {
        try {
            return Files.size(p);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }).sum();

    System.out.println(tongByte);
}
```

Ví dụ này đọc `Files.size(p)` thêm một lần sau matcher và có thể gặp tình trạng tệp thay đổi hoặc bị xóa. Nếu cần tổng hợp trực tiếp từ `BasicFileAttributes` trong một lượt duyệt, `Files.walkFileTree` với `visitFile` và `attrs.size()` là lựa chọn phù hợp. Ngoài ra, `long` cũng có thể tràn nếu tổng vượt miền biểu diễn.

### 12.5. In đường dẫn tương đối theo thứ tự ổn định

```java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(p -> !p.equals(root))
        .map(p -> root.relativize(p).toString())
        .sorted()
        .forEach(System.out::println);
}
```

`sorted` làm kết quả dễ kiểm thử nhưng có chi phí sắp xếp toàn bộ đường dẫn trong phạm vi đã duyệt.

## 13. Bảng chọn API và những lỗi thường gặp

| Nhu cầu | Lựa chọn | Điểm cần nhớ |
| --- | --- | --- |
| Liệt kê đúng một cấp | `Files.list(dir)` | Không có chính `dir`. |
| Duyệt cây tới độ sâu N | `Files.walk(root, N)` | Có cả `root`; độ sâu của root là 0. |
| Lọc theo loại, kích thước hoặc thời gian sửa | `Files.find(root, N, matcher)` | `matcher` nhận sẵn `BasicFileAttributes`. |
| Muốn bỏ qua cả một nhánh | `Files.walkFileTree` | Dùng `SKIP_SUBTREE`. |
| Chỉ cần biết có một tệp phù hợp | `anyMatch` / `findFirst` | Có thể short-circuit; vẫn phải đóng. |
| Có symbolic link nhưng không muốn theo đích | Không dùng `FOLLOW_LINKS` | Kiểm tra thêm `NOFOLLOW_LINKS` khi cần. |
| Muốn in theo thứ tự nhất định | `sorted` / comparator | Cần xử lý và giữ dữ liệu trước khi sắp xếp. |
| Dữ liệu quá lớn | Giới hạn phạm vi, độ sâu hoặc xử lý theo batch | Không thu/sắp xếp toàn bộ cây vô điều kiện. |

Các lỗi phổ biến:

- **Quên `try-with-resources`:** bỏ sót đóng directory handle dù đã gọi `count` hoặc `collect`.
- **Nhầm `walk(root, 1)` với `list(root)`:** quên rằng `walk` còn phát `root`.
- **Dùng `walk(root)` khi chỉ cần một cấp:** duyệt sâu không cần thiết.
- **Dùng `filter` để "ngăn vào thư mục con":** bộ lọc chỉ loại phần tử kết quả.
- **Dùng `contains("build")` trên chuỗi path để cắt nhánh:** dễ loại nhầm, không kiểm soát traversal.
- **Dựa vào thứ tự duyệt mặc định:** thứ tự mục trong thư mục không phải thứ tự chữ cái được bảo đảm.
- **Tự động bật `FOLLOW_LINKS`:** có nguy cơ vòng lặp và truy cập vượt phạm vi.
- **Trả stream ra ngoài `try`:** stream đã đóng khi bên gọi nhận được.
- **Dùng lại stream sau terminal operation:** stream chỉ được tiêu thụ một lần.
- **Nuốt `IOException` rồi trả kết quả rỗng:** che giấu lỗi hệ thống.
- **Sắp xếp cả cây rất lớn để lấy vài phần tử:** làm giảm lợi ích xử lý lazy.
- **Giả định tệp không đổi sau khi matcher kiểm tra:** có nguy cơ TOCTOU.

## 14. Bài tập thực hành

Giả sử có cây:

```text
kho/
├── notes.txt
├── src/
│   ├── Main.java
│   ├── Model.java
│   └── nested/
│       └── Test.java
├── docs/
│   └── guide.md
└── build/
    └── classes.bin
```

### Bài 1 — So sánh `list` và `walk`

Với `root = Paths.get("kho")`, `Files.list(root)` trả những đường dẫn nào? `Files.walk(root, 1)` có thêm phần tử gì? `Files.walk(root, 2)` có chứa `src/nested/Test.java` không?

### Bài 2 — Tìm tệp Java

Viết `Files.find(root, 3, matcher)` để lấy các tệp thường có đuôi `.java`. Đóng nguồn bằng `try-with-resources`. Dự đoán các tệp kết quả.

### Bài 3 — Đếm tệp ở đúng một cấp

Dùng `Files.list` để đếm các tệp thường trực tiếp dưới `kho`, không tính thư mục. Kết quả là bao nhiêu?

### Bài 4 — Chỉ cần hai tệp có đuôi hiếm

Nếu gọi `Files.walk(root).filter(p -> p.toString().endsWith(".jar")).limit(2)`, nhưng cây không có `.jar`, có phải Java chỉ kiểm tra hai đường dẫn rồi dừng? Vì sao? Có phải đóng stream không?

### Bài 5 — Yêu cầu không truy cập thư mục `build`

Vì sao `Files.find` với matcher loại đường dẫn chứa chuỗi `build` chưa đáp ứng yêu cầu? Nên dùng API gì và giá trị trả nào để bỏ toàn bộ subtree?

### Đáp án tham khảo

**Bài 1:** `Files.list(root)` trả `notes.txt`, `src`, `docs`, `build`; thứ tự không xác định. `Files.walk(root, 1)` còn chứa chính `root`. `src/nested/Test.java` nằm ở độ sâu **3**, nên không nằm trong `walk(root, 2)`.

**Bài 2:**

```java
try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, attrs) -> attrs.isRegularFile()
            && p.getFileName() != null
            && p.getFileName().toString().endsWith(".java")
    )) {
    matches.map(p -> root.relativize(p).toString())
        .sorted()
        .forEach(System.out::println);
}
```

Kết quả là `src/Main.java`, `src/Model.java` và `src/nested/Test.java` (dấu phân cách tùy hệ điều hành).

**Bài 3:**

```java
try (Stream<Path> entries = Files.list(root)) {
    long count = entries.filter(Files::isRegularFile).count();
    System.out.println(count); // 1 (notes.txt)
}
```

**Bài 4:** Không. `limit(2)` áp dụng cho **số phần tử vượt qua `filter`**; nếu không có `.jar`, traversal có thể phải kiểm tra hết cây. Vẫn phải đóng stream dù không có kết quả.

**Bài 5:** Matcher của `find` chọn đường dẫn trả ra nhưng không cung cấp lệnh cắt subtree. `Files.walkFileTree` cho phép override `preVisitDirectory` và trả `FileVisitResult.SKIP_SUBTREE` khi gặp thư mục tên `build`; các thư mục khác trả `CONTINUE`.

## 15. Tổng kết

```java
// Chỉ các mục trực tiếp:
try (Stream<Path> s = Files.list(root)) {
    s.forEach(System.out::println);
}

// Cây tới độ sâu 3, gồm cả root:
try (Stream<Path> s = Files.walk(root, 3)) {
    s.forEach(System.out::println);
}

// Chỉ phát đường dẫn matcher chấp nhận:
try (Stream<Path> s = Files.find(
        root, 3,
        (p, attrs) -> attrs.isRegularFile()
    )) {
    s.forEach(System.out::println);
}
```

- **`Files.list`** chỉ liệt kê một cấp; **`Files.walk`** duyệt cây; **`Files.find`** duyệt cây với điều kiện nhận `BasicFileAttributes`.
- Luôn dùng **`try-with-resources`** để đóng nguồn stream I/O, kể cả khi không nhận được phần tử nào.
- `maxDepth` giới hạn độ sâu tính từ gốc; mặc định không theo symbolic link.
- `filter` và `matcher` chọn đầu ra, **không cắt nhánh traversal**. Muốn bỏ subtree cần `Files.walkFileTree` và `SKIP_SUBTREE`.
- Xử lý `IOException` khi khởi tạo và `UncheckedIOException` có thể phát sinh trong lúc duyệt; không đánh đồng lỗi I/O với tập dữ liệu rỗng.
- Thứ tự thư mục không được bảo đảm; sắp xếp khi có yêu cầu xác định nhưng cân nhắc chi phí trên cây lớn.

Kết hợp ba nguồn tệp này với `filter`, `map`, `count` và `collect` đúng cách giúp tạo công cụ khám phá hệ thống tệp rõ ràng, tiết kiệm tài nguyên và an toàn hơn trước những thay đổi của môi trường I/O.
