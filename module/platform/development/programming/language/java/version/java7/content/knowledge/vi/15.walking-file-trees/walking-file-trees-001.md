# Java 7 — Duyệt cây tệp: Đọc thư mục theo DirectoryStream

## 1. Mục tiêu bài học

`java.nio.file.DirectoryStream<Path>` là một giao diện trong NIO.2 dùng để **duyệt các mục trực tiếp của một thư mục**. Nó được cung cấp từ Java 7 và vẫn là API hiện hành, được dùng tốt với Java 17+. Thay vì yêu cầu chương trình lập tức tạo một danh sách tất cả file, `DirectoryStream` cho phép truy cập lần lượt các entry qua vòng lặp `for-each`.

Mẫu cơ bản:

```java
Path directory = Path.of("data", "incoming");

try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(directory)) {
    for (Path entry : stream) {
        System.out.println(entry.getFileName());
    }
}
```

Đây là **snippet đặt bên trong một phương thức** với import `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.file.DirectoryStream` và xử lý `IOException`. `Path.of` có từ Java 11; khi chạy JDK 17+ hoàn toàn hợp lệ. `DirectoryStream` và `Files.newDirectoryStream` đã tồn tại từ Java 7.

**Các vấn đề bài này giải quyết:** mở thư mục; duyệt Path trực tiếp; lọc theo glob; lọc với `DirectoryStream.Filter`; đóng tài nguyên; xử lý lỗi ở hai giai đoạn mở và duyệt; hiểu iterator chỉ dùng một lần; không dựa vào thứ tự; chọn giữa `DirectoryStream` và `Files.list/walk/walkFileTree`; và tránh sai sót liên quan symbolic link hoặc thay đổi thư mục đồng thời.

**Cần nhớ ngay:** `DirectoryStream` **không đệ quy**. Nếu cấu trúc gồm `root/a.txt` và `root/sub/b.txt` thì mở stream của `root` chỉ trả entry `a.txt` và `sub`; nó không tự đi vào `sub` để trả `b.txt`.

## 2. Cơ chế DirectoryStream hoạt động như thế nào?

`DirectoryStream<T>` mở rộng `Iterable<T>` và `Closeable`. Với overload thông dụng của `Files`, kiểu phần tử là `Path`. Những Path này được tạo như thể **tên entry được resolve vào Path của thư mục đang mở**.

Giả sử cây thư mục:

```text
demo/
├── a.txt
├── b.log
├── c.txt
└── sub/
    └── deep.txt
```

Đọc một cấp:

```java
try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(Path.of("demo"))) {
    for (Path entry : stream) {
        System.out.println(entry);
    }
}
```

Kết quả bao gồm các đường dẫn tương ứng `demo/a.txt`, `demo/b.log`, `demo/c.txt` và `demo/sub`, **không bảo đảm thứ tự**. Nếu `demo` là relative Path, các entry cũng có thể là relative Path theo provider. Không có bước I/O tự động đi vào `demo/sub`.

### 2.1. DirectoryStream không phải List

Một `DirectoryStream` không phải snapshot danh sách tại thời điểm mở. Nó có những tính chất quan trọng:

- **Chỉ cấp một Iterator:** gọi `stream.iterator()` lần thứ hai trên cùng stream ném `IllegalStateException`.
- **Không có thứ tự bảo đảm:** không mặc định theo alphabet, ngày tạo hay kích thước.
- **Weakly consistent:** thay đổi của thư mục trong khi duyệt có thể được nhìn thấy hoặc không.
- **Cần đóng:** `close()` giải phóng tài nguyên liên quan tới việc mở thư mục.
- **Iterator không hỗ trợ `remove()`:** không dùng iterator để xóa entry.
- **Không duyệt con:** entry là thư mục con vẫn chỉ là một Path được trả về.

Do đó, không viết API nhận DirectoryStream rồi duyệt hai lần như với List; không để một stream mở vô thời hạn để chờ dữ liệu mới.

### 2.2. Path returned khác với tên file

`entry` là một `Path` đầy đủ về cấu trúc (theo provider và Path thư mục), không phải một tên đơn:

```java
Path fileName = entry.getFileName();
Path parent = entry.getParent();
boolean isDirectory = Files.isDirectory(entry);
```

Đây là **snippet minh họa** trong phương thức có biến `Path entry`. `getFileName()` lấy thành phần tên cuối, `getParent()` lấy parent theo cú pháp và `Files.isDirectory(entry)` kiểm tra kiểu entry trên filesystem. Phương thức kiểm tra thuộc tính có thể phải truy cập file system và kết quả có thể thay đổi ngay sau khi được đọc.

## 3. Những overload của Files.newDirectoryStream

Trên Java 17 có ba cách gọi chính:

| API | Kết quả |
| --- | --- |
| `Files.newDirectoryStream(dir)` | Duyệt các entry trực tiếp, không lọc bằng điều kiện ứng dụng |
| `Files.newDirectoryStream(dir, "*.txt")` | Chỉ những entry trực tiếp **có tên khớp glob** |
| `Files.newDirectoryStream(dir, filter)` | Chỉ những entry thỏa `DirectoryStream.Filter<? super Path>` |

Mọi overload trả một **DirectoryStream<Path> đang mở**, có thể ném `IOException` tại thời điểm mở và cần được đóng bằng try-with-resources. Nếu `dir` là một file thường chứ không phải thư mục, thao tác mở không tạo ra stream liệt kê hợp lệ.

### 3.1. Dùng đúng nơi

- Cần duyệt mọi entry của một folder: overload **không filter**.
- Cần tìm một số đuôi tên: overload **glob**.
- Cần kết hợp tên, loại file, size hoặc metadata: overload nhận **Filter<Path>**.
- Cần duyệt toàn bộ cây: chuyển sang `Files.walk` hoặc `Files.walkFileTree` hay điều phối recursion có kiểm soát; không nhầm rằng `newDirectoryStream` tự đi sâu.

## 4. Chương trình Java 17+ hoàn chỉnh và đã kiểm thử

Chương trình tạo thư mục tạm riêng, ba file trực tiếp và một thư mục con chứa file sâu hơn. Nó thử duyệt không lọc, lọc glob, lọc có điều kiện, xin iterator lần thứ hai và tạo lỗi IOException trong Filter. Kết quả được **sort theo tên để stdout ổn định**; bản thân DirectoryStream không hứa thứ tự.

Tạo file **`DirectoryStreamDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

public class DirectoryStreamDemo {
    static List<String> names(DirectoryStream<Path> stream) {
        List<String> result = new ArrayList<>();
        for (Path entry : stream) {
            result.add(entry.getFileName().toString());
        }
        Collections.sort(result);
        return result;
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-stream-demo-");
        try {
            Files.writeString(root.resolve("a.txt"), "alpha",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("b.log"), "log",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("c.txt"), "cat",
                    StandardCharsets.UTF_8);
            Files.createDirectory(root.resolve("sub"));
            Files.writeString(root.resolve("sub").resolve("deep.txt"),
                    "deep", StandardCharsets.UTF_8);

            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root)) {
                List<String> direct = names(stream);
                System.out.println("direct = " + direct);
                System.out.println("includes nested file = " +
                        direct.contains("deep.txt"));
            }

            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root, "*.txt")) {
                System.out.println("glob = " + names(stream));
            }

            DirectoryStream.Filter<Path> largeFiles =
                    entry -> Files.isRegularFile(entry) &&
                            Files.size(entry) >= 4;
            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root, largeFiles)) {
                System.out.println("filter = " + names(stream));
            }

            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root)) {
                Iterator<Path> first = stream.iterator();
                try {
                    stream.iterator();
                } catch (IllegalStateException expected) {
                    System.out.println("second iterator = " +
                            expected.getClass().getSimpleName());
                }
            }

            DirectoryStream.Filter<Path> failing = entry -> {
                throw new IOException("filter failed");
            };
            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root, failing)) {
                try {
                    stream.iterator().hasNext();
                } catch (DirectoryIteratorException ex) {
                    System.out.println("filter error cause = " +
                            ex.getCause().getClass().getSimpleName());
                }
            }
        } finally {
            Files.deleteIfExists(root.resolve("sub").resolve("deep.txt"));
            Files.deleteIfExists(root.resolve("sub"));
            Files.deleteIfExists(root.resolve("a.txt"));
            Files.deleteIfExists(root.resolve("b.log"));
            Files.deleteIfExists(root.resolve("c.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 DirectoryStreamDemo.java
java DirectoryStreamDemo
```

**Stdout đã kiểm thử trên JDK 24:**

```text
direct = [a.txt, b.log, c.txt, sub]
includes nested file = false
glob = [a.txt, c.txt]
filter = [a.txt]
second iterator = IllegalStateException
filter error cause = IOException
```

**Phân tích từng dòng:**

1. `direct` có bốn entry trực tiếp và được sắp xếp theo tên. File `deep.txt` nằm trong `sub/` nên không có trong List.
2. `includes nested file = false` xác nhận việc liệt kê **không recursive**.
3. `glob = [a.txt, c.txt]` vì chỉ hai tên trực tiếp kết thúc bằng `.txt`.
4. `filter = [a.txt]` vì filter yêu cầu regular file có size ≥ 4 byte; `a.txt` chứa `alpha` = 5 byte, hai file còn lại dài 3 byte và `sub` là thư mục.
5. `second iterator` là `IllegalStateException`: mỗi DirectoryStream cấp **một Iterator**.
6. Filter cuối ném `IOException` cố ý; lỗi trong quá trình duyệt được **bọc trong DirectoryIteratorException**. `getCause()` là `IOException`.

Ví dụ chỉ ghi trong thư mục tạm do chính chương trình tạo. Khối `finally` cố dọn file và thư mục. Nếu hệ điều hành từ chối tạo/xóa file tạm, chương trình có thể ném `IOException`; output trên được kiểm thử ở môi trường có quyền I/O bình thường. Đoạn mã dùng `Files.writeString` và `Path.of` có trên JDK 17, dù cơ chế `DirectoryStream` vốn đã có từ Java 7.

## 5. Đọc thư mục với try-with-resources

Một DirectoryStream là resource đang mở, có thể giữ handle hoặc descriptor. Nếu quên đóng, service chạy lâu có thể tích lũy tài nguyên và gặp lỗi I/O sau nhiều lượt xử lý.

Mẫu chuẩn:

```java
static void printEntries(Path dir) throws IOException {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
        for (Path entry : stream) {
            System.out.println(entry.getFileName());
        }
    }
}
```

Đây là phương thức minh họa trong một class có import `Path`, `Files`, `DirectoryStream` và `IOException`. TWR đóng stream dù vòng lặp kết thúc bình thường hay có exception. Đọc nhiều thư mục trong vòng lặp thì nên **mở/đóng theo phạm vi ngắn**, không giữ hàng trăm stream cùng lúc.

### 5.1. Lấy dữ liệu để dùng sau khi đóng

Nếu caller cần nhiều lượt duyệt, hãy tạo một collection trong scope resource:

```java
static List<Path> listDirectChildren(Path dir) throws IOException {
    List<Path> result = new ArrayList<>();

    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
        for (Path entry : stream) {
            result.add(entry);
        }
    } catch (DirectoryIteratorException ex) {
        throw ex.getCause();
    }
    return result;
}
```

Đây là phương thức minh họa; cần import các kiểu NIO, `ArrayList` và `List`. Stream đã đóng trước khi return; caller nhận List và có thể duyệt nhiều lần. Tuy nhiên List chỉ chứa **các Path đã nhìn thấy trong lượt liệt kê**. Nó không khóa file hoặc tạo snapshot nguyên tử của trạng thái thực.

### 5.2. Vì sao không trả DirectoryStream trần cho mọi API?

Nếu một method trả DirectoryStream, caller phải biết **đóng tài nguyên** và **không yêu cầu iterator lần hai**. Với API công khai, đây là hợp đồng dễ bị dùng sai. Có thể ưu tiên một callback xử lý entry trong try-with-resources, hoặc trả List sau khi đóng nếu kích thước vừa phải. Với thư mục cực lớn, xử lý từng entry sẽ tiết kiệm bộ nhớ hơn việc gom toàn bộ.

## 6. Glob: lọc trực tiếp theo tên file

Cú pháp:

```java
try (DirectoryStream<Path> csv =
        Files.newDirectoryStream(dir, "*.csv")) {
    for (Path path : csv) {
        System.out.println(path.getFileName());
    }
}
```

Đây là snippet trong phương thức có `Path dir` và xử lý ngoại lệ. Overload nhận `String glob` sử dụng cú pháp glob của filesystem provider, tương tự cách `FileSystem.getPathMatcher("glob:...")` xử lý mẫu.

Một số mẫu thường gặp:

| Glob | Ý nghĩa minh họa |
| --- | --- |
| `*.txt` | Tên có đuôi `.txt` |
| `*.{java,kt}` | Tên kết thúc bằng `.java` hoặc `.kt` |
| `report-??.csv` | Hai ký tự ở giữa `report-` và `.csv` |
| `[ab]*.log` | Tên bắt đầu với a hoặc b, có đuôi `.log` |
| `*` | Tất cả tên khớp theo provider |

**Chú ý:** Glob ở đây so **tên entry trong một thư mục**, không bắt đầu traversal đệ quy. Dấu `**` trong pattern không tự làm `newDirectoryStream` đi vào subdirectory. Ngoài ra glob **không kiểm tra entry có thực sự là file thường**; một thư mục tên `old.txt` cũng có thể khớp `*.txt`.

Cách xử lý chữ hoa/thường, escape và một số chi tiết pattern có thể khác theo provider/file system. Khi pattern đến từ người dùng, phải xác thực cú pháp (có thể phát sinh `PatternSyntaxException`) và giới hạn phạm vi nếu dữ liệu được dùng cho các thao tác nhạy cảm.

## 7. Filter<Path>: lọc theo thuộc tính và logic ứng dụng

`DirectoryStream.Filter<T>` là giao diện có phương thức `boolean accept(T entry) throws IOException`. Với DirectoryStream thông dụng, `T` là Path. Lambda có thể thực hiện điều kiện bất kỳ phù hợp nghiệp vụ.

### 7.1. Lấy regular file

```java
DirectoryStream.Filter<Path> filesOnly =
        entry -> Files.isRegularFile(entry);

try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(dir, filesOnly)) {
    for (Path entry : stream) {
        System.out.println(entry.getFileName());
    }
}
```

Đây là snippet trong phương thức với `Path dir`. `Files.isRegularFile(entry)` thường trả false khi entry không phải regular file **hoặc không thể xác định được thuộc tính**. Nếu cần phân biệt lỗi đọc metadata, dùng `Files.readAttributes`/API tương ứng và xử lý checked IOException.

### 7.2. Lấy file đủ lớn

```java
DirectoryStream.Filter<Path> bigFiles =
        entry -> Files.isRegularFile(entry)
                && Files.size(entry) >= 8 * 1024L;
```

Đây là snippet minh họa. `Files.size` trả **số byte**, không phải số ký tự. Nếu entry bị xóa/đổi giữa hai lệnh, filter có thể quan sát kết quả khác hoặc gặp lỗi I/O. Dù filter có checked `IOException` trong chữ ký `accept`, khi iterator chạy, lỗi I/O đó có thể bị bọc thành `DirectoryIteratorException`.

### 7.3. Chỉ thư mục con không theo symbolic link

```java
DirectoryStream.Filter<Path> folders =
        entry -> Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet trong phương thức, cần import `java.nio.file.LinkOption`. `NOFOLLOW_LINKS` giúp phân biệt một symbolic link trỏ tới thư mục với chính directory entry, nhưng không tạo bảo đảm tránh race khi entry thay đổi sau khi kiểm tra.

### 7.4. Lọc theo tên mà không dùng glob

```java
DirectoryStream.Filter<Path> csvFiles =
        entry -> entry.getFileName().toString().endsWith(".csv")
                && Files.isRegularFile(entry);
```

Đây là snippet minh họa. `String.endsWith` phân biệt chữ hoa/thường theo String, **không theo chính sách case sensitivity của file system**. Nếu nghiệp vụ chấp nhận cả `.csv` và `.CSV`, cần thiết kế chính sách so sánh tên rõ ràng.

### 7.5. Không dùng filter làm nơi thực hiện nghiệp vụ lâu dài

Filter nên chỉ quyết định **có chấp nhận một entry hay không**; tránh xóa file, đổi tên, gọi API mạng hoặc cập nhật database bên trong filter. Những side effect như vậy làm khó dự đoán kết quả khi iteration có read-ahead hoặc thư mục thay đổi. Tốt hơn là để filter chọn ứng viên rồi xử lý trong vòng for-each với error handling và ownership riêng.

## 8. Ngoại lệ tại lúc mở và lúc duyệt: không giống nhau

### 8.1. Khi mở DirectoryStream

`Files.newDirectoryStream(dir)` có thể ném `IOException` ngay khi mở:

- `dir` không tồn tại.
- `dir` là file, không phải thư mục.
- Không có quyền hoặc provider không thể mở directory handle.
- File system gặp lỗi tạm thời.

Một số hệ thống ném `NoSuchFileException` hoặc `NotDirectoryException`. Javadoc mô tả một số subclass là **optional specific exceptions**, nên đừng giả định mọi provider báo lỗi bằng cùng subclass. Khi cần, bắt `IOException` và giữ ngữ cảnh đường dẫn; không che lỗi thành “thư mục rỗng”.

### 8.2. Khi iterator đọc entry

Nếu stream đã mở thành công nhưng iterator gặp lỗi I/O trong `hasNext` hoặc `next`, nó ném **`DirectoryIteratorException`**, là unchecked exception chứa `IOException` làm cause.

```java
static List<Path> collect(Path dir) throws IOException {
    List<Path> result = new ArrayList<>();
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
        for (Path entry : stream) {
            result.add(entry);
        }
    } catch (DirectoryIteratorException ex) {
        throw ex.getCause();
    }
    return result;
}
```

Đây là phương thức minh họa đặt trong class với imports cần thiết. Nó chuyển exception khi duyệt về checked IOException của API caller. Catch nằm ngoài TWR để stream được đóng trước khi lỗi được truyền lên.

### 8.3. Khi Filter.accept ném IOException

`Files.newDirectoryStream(dir, filter)` có thể gọi filter trong quá trình iterator. Nếu `filter.accept` ném IOException, API bọc IOException đó vào DirectoryIteratorException. Demo ở phần 4 minh họa:

```text
filter error cause = IOException
```

Không giả định `Files.newDirectoryStream(dir, filter)` sẽ thực thi toàn bộ filter ngay lúc mở. Những lỗi **RuntimeException** khác trong filter thường được truyền ra, không tự biến thành IOException.

### 8.4. Khi close gặp lỗi

`DirectoryStream.close()` có thể ném IOException. Try-with-resources đảm bảo gọi close; nếu thân try đã có exception và close cũng lỗi, lỗi close có thể xuất hiện trong `getSuppressed()` theo cơ chế Java. Không cố tránh TWR để “đỡ exception”; hãy xử lý nguyên nhân thật và bảo toàn thông tin lỗi.

## 9. Quy tắc Iterator: một lần, read-ahead và trạng thái đóng

**Chỉ một Iterator:** `iterator()` chỉ được gọi một lần trên mỗi DirectoryStream. For-each ngầm gọi iterator, vì vậy lặp hai lần trên một stream không hợp lệ.

**Không hỗ trợ remove:** `Iterator.remove()` không được hỗ trợ; nó không xóa entry trên filesystem.

**Read-ahead:** `hasNext()` đảm bảo đọc trước ít nhất một phần tử. Theo Javadoc, nếu `hasNext()` trả true rồi ngay sau đó gọi `next()`, `next()` không thất bại **vì lỗi I/O hoặc vì stream đã được đóng** giữa hai lời gọi. Đây là một cam kết hẹp của iterator, không phải bảo đảm toàn bộ traversal không có lỗi.

**Sau close:** iterator có thể trả một vài phần tử đã nằm trong buffer đọc trước, rồi hành xử như hết dữ liệu. Không dùng hành vi này để “duyệt thêm” sau khi đóng. Khi buffer đã hết, `hasNext()` trả false và `next()` ném `NoSuchElementException`.

**Weakly consistent:** iterator có thể phản ánh hoặc không phản ánh thay đổi của thư mục sau thời điểm tạo stream. Nó không hứa một snapshot tĩnh, và tính thread-safe theo Javadoc **không** đồng nghĩa được phép tạo nhiều iterator hoặc biết trước thứ tự giữa các thread.

## 10. Không được phụ thuộc thứ tự thư mục

Duyệt directory không có thứ tự cụ thể. Nếu muốn xử lý file theo tên, thời điểm hoặc priority, phải **sort chủ động**.

```java
static List<String> sortedFileNames(Path dir) throws IOException {
    List<String> names = new ArrayList<>();
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
        for (Path p : stream) {
            names.add(p.getFileName().toString());
        }
    } catch (DirectoryIteratorException ex) {
        throw ex.getCause();
    }
    Collections.sort(names);
    return names;
}
```

Đây là phương thức minh họa, cần imports `List`, `ArrayList`, `Collections` và NIO. Nó thu thập các tên thấy được trong lượt duyệt và sắp xếp theo so sánh String. Nếu muốn sort theo “thứ tự thân thiện người dùng” cần xác định locale/collator. Nếu thư mục thay đổi đồng thời, kết quả đã sort **không** trở thành một snapshot nguyên tử của toàn bộ filesystem.

**Đánh đổi:** Sort cần gom dữ liệu vào RAM; nếu chỉ cần xử lý từng file và không quan tâm thứ tự, dùng for-each trực tiếp để không tăng bộ nhớ theo số entry.

## 11. DirectoryStream, Files.list, Files.walk và walkFileTree khác nhau

| API | Phạm vi | Kiểu kết quả | Resource | Khi nên dùng |
| --- | --- | --- | --- | --- |
| `Files.newDirectoryStream(dir)` | Một cấp | `DirectoryStream<Path>` | Đóng TWR | Liệt kê for-each, glob, filter NIO |
| `Files.list(dir)` | Một cấp | `Stream<Path>` | Đóng Stream | Pipeline `filter/map/sorted` của Java 8+ |
| `Files.walk(root)` | Nhiều cấp | `Stream<Path>` | Đóng Stream | Duyệt sâu dạng pipeline, giới hạn depth |
| `Files.walkFileTree(root, visitor)` | Nhiều cấp | Callback FileVisitor | API quản lý lượt duyệt | Cần skip subtree, xử lý lỗi từng nhánh, xóa/copy cây |

### 11.1. Files.list (Java 8+)

```java
try (var paths = Files.list(dir)) {
    List<Path> files = paths
            .filter(Files::isRegularFile)
            .sorted()
            .toList();
    System.out.println(files.size());
}
```

Đây là snippet Java 17+ trong phương thức có `Path dir` và xử lý IOException/UncheckedIOException. `Files.list` **không recursive**, cũng cần đóng do giữ directory resource. Lỗi I/O xảy ra khi terminal operation đọc có thể được đưa ra dưới dạng `UncheckedIOException`, khác DirectoryIteratorException của DirectoryStream. `Stream.toList()` có từ Java 16.

### 11.2. Files.walk (Java 8+)

```java
try (var paths = Files.walk(root, 3)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
```

Đây là snippet Java 17+ với `Path root`. `Files.walk` bắt đầu từ root và có thể duyệt nhiều cấp đến độ sâu chỉ định. Theo mặc định nó không theo symbolic link trừ khi chọn `FOLLOW_LINKS`. Phải đóng Stream sau sử dụng. Với cây rất lớn, giới hạn độ sâu và xử lý lỗi/cycle theo hợp đồng.

### 11.3. Files.walkFileTree (Java 7+)

Nếu cần điều khiển trước/sau khi vào thư mục, bỏ qua một nhánh, hoặc xử lý lỗi `visitFileFailed`, `Files.walkFileTree` với `FileVisitor` thường phù hợp hơn tự viết recursion bằng DirectoryStream.

**Không tự viết recursion** nếu chưa xử lý trường hợp symlink cycle, quyền đọc ở từng cấp, đường dẫn rất sâu, quá nhiều handle mở, và thay đổi đồng thời. DirectoryStream vẫn tốt cho **một lượt liệt kê của một thư mục riêng lẻ**.

## 12. Lỗi đồng thời, symlink và TOCTOU

Giả sử một ứng dụng:

1. Nhìn thấy `incoming/job.csv` từ DirectoryStream.
2. Kiểm tra `Files.isRegularFile(entry)` và `Files.size(entry)`.
3. Mở file bằng `Files.newBufferedReader(entry, UTF_8)`.
4. Di chuyển file sau khi xử lý.

Giữa mỗi bước, tiến trình khác có thể xóa, đổi tên hoặc thay entry bằng symbolic link. Lọc một lần **không khóa file**. Ứng dụng phải xử lý IOException ở lúc mở/đọc/di chuyển thật và xây chính sách ownership/idempotency nếu cần “xử lý một file đúng một lần”.

### 12.1. Theo hoặc không theo symbolic links

`Files.isRegularFile(entry)` mặc định có thể theo link. Nếu muốn phân loại **entry tự thân** mà không theo symbolic link:

```java
boolean regularWithoutFollowing =
        Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet với import `java.nio.file.LinkOption` và biến `Path entry`. Nó có ích để ra quyết định filter, nhưng không tự chống lại việc entry bị thay đổi giữa kiểm tra và mở.

### 12.2. SecureDirectoryStream (tùy provider)

`SecureDirectoryStream<Path>` là subtype của DirectoryStream cung cấp một số thao tác tương đối với directory handle đang mở nhằm giảm nguy cơ race nếu provider hỗ trợ. Không giả định mọi hệ thống sẽ trả loại secure.

```java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
    if (stream instanceof SecureDirectoryStream<?>) {
        System.out.println("Secure directory operations available");
    }
}
```

Đây là snippet trong phương thức có import `SecureDirectoryStream`. Output phụ thuộc provider. **Không** coi `normalize().startsWith(root)`, glob `*.csv` hoặc việc chỉ đọc DirectoryStream là sandbox bảo mật. Đối với thư mục không tin cậy, còn cần kiểm tra root, symlink policy, quyền filesystem và race.

## 13. Hiệu năng và bộ nhớ

DirectoryStream phù hợp với các trường hợp muốn **đọc và xử lý lần lượt**. Với thư mục có nhiều entry, ứng dụng không cần tạo một List lớn chỉ để for-each. Nhưng cần nhớ:

- Provider/OS có thể buffer và cache; không hứa toàn bộ đường đi dùng đúng O(1) RAM trong mọi triển khai.
- `Filter<Path>` dùng `Files.size`, `Files.readAttributes` hoặc I/O khác có thể phát sinh nhiều lần truy cập metadata.
- Nếu bạn gom mọi tên để sort, bộ nhớ do ứng dụng dùng tăng theo số entry.
- Nếu xử lý từng file mất nhiều thời gian, việc giữ DirectoryStream mở quá lâu có thể tốn tài nguyên; cân nhắc batch và vòng đời resource.
- Không dùng DirectoryStream như hệ thống polling sự kiện liên tục; nếu cần phát hiện thay đổi, có thể cân nhắc `WatchService` với cơ chế quét lại và xử lý khả năng mất sự kiện.

### 13.1. Đếm entry đã nhìn thấy

```java
long count = 0;
try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
    for (Path path : stream) {
        if (Files.isRegularFile(path)) {
            count++;
        }
    }
}
```

Đây là snippet trong phương thức có `Path dir`. `count` chỉ đếm những entry được iterator nhìn thấy và thỏa filter tại thời điểm kiểm tra. Nó không chứng minh một con số cố định nếu thư mục thay đổi đồng thời.

## 14. Thiết kế workflow xử lý file thực tế

Một chương trình nhập file CSV từ folder có thể thực hiện theo hướng:

1. **Chọn nguồn tin cậy:** Path của thư mục intake phải được cấu hình và kiểm soát quyền.
2. **Liệt kê một cấp:** `newDirectoryStream(dir, "*.csv")`.
3. **Phân loại:** kiểm tra entry là file thường (và symlink policy).
4. **Mở/validate dữ liệu thật:** xử lý I/O và các lỗi định dạng ngay tại lúc đọc.
5. **Ghi nhận kết quả/di chuyển:** dùng file rename/move hoặc cơ chế nghiệp vụ đảm bảo idempotency và xử lý cạnh tranh.
6. **Đóng resource:** stream đóng trước khi trả kết quả/thoát phương thức.
7. **Không phụ thuộc thứ tự:** nếu có thứ tự ưu tiên, sort theo tiêu chí có chủ đích.
8. **Không mặc định liệt kê là snapshot:** nếu mục có thể đổi/xóa, chuẩn bị retry/error handling riêng.

Ví dụ minh họa **lấy tên các CSV**, không xử lý nội dung:

```java
static List<Path> csvCandidates(Path dir) throws IOException {
    List<Path> found = new ArrayList<>();
    try (DirectoryStream<Path> stream =
            Files.newDirectoryStream(dir, "*.csv")) {
        for (Path entry : stream) {
            if (Files.isRegularFile(entry)) {
                found.add(entry);
            }
        }
    } catch (DirectoryIteratorException ex) {
        throw ex.getCause();
    }
    found.sort(Path::compareTo);
    return found;
}
```

Đây là phương thức minh họa. Nó trả các Path, không copy nội dung hoặc “giành quyền” xử lý file; phải kiểm tra lại quyền và sự tồn tại ở bước mở thực. `Path::compareTo` hợp lý khi các entry thuộc cùng provider; không dùng comparator này một cách mù quáng với Path đến từ nhiều FileSystemProvider khác nhau.

## 15. Những sai lầm thường gặp

**1. Duyệt cùng stream hai lần.** DirectoryStream chỉ hỗ trợ một Iterator; lần hai ném IllegalStateException.

**2. Quên close.** Một stream có tài nguyên; dùng try-with-resources.

**3. Nghĩ newDirectoryStream tự duyệt toàn bộ cây.** Nó chỉ một cấp; muốn recursive dùng walk/walkFileTree.

**4. Nghĩ glob chỉ trả regular files.** Glob so tên; một thư mục có đuôi `.txt` vẫn có thể khớp.

**5. Tin tưởng thứ tự iterator.** Không có bảo đảm thứ tự; muốn deterministic phải sort.

**6. Chỉ bắt IOException ở lúc mở.** I/O trong lúc duyệt có thể là DirectoryIteratorException.

**7. Không hiểu lỗi trong Filter.** Checked IOException từ filter có thể được bọc khi iterator xử lý.

**8. Dùng iterator.remove() để xóa file.** Iterator không hỗ trợ remove; xóa là thao tác Files riêng có policy và IOException.

**9. Đóng stream rồi mong tiếp tục duyệt.** Có thể còn phần tử read-ahead nhưng không thể dùng như stream đang mở.

**10. Dùng `entry.toString()` như tên file đơn.** Đây là Path biểu diễn entry; `getFileName()` là tên cuối.

**11. Nghĩ filter size xác nhận file sẽ giữ nguyên.** Entry có thể đổi sau kiểm tra; phải xử lý race tại lúc mở.

**12. Cho rằng DirectoryStream là snapshot.** Weakly consistent, có thể hoặc không thấy thay đổi.

**13. Dùng `Files.list` rồi quên đóng Stream.** Files.list cũng giữ tài nguyên thư mục.

**14. Chỉ dùng `endsWith(".csv")` mà tin nội dung là CSV hợp lệ.** Tên file không chứng minh định dạng.

**15. Ghi log mọi Path nguyên bản mà không chú ý dữ liệu nhạy cảm.** Tên file có thể chứa thông tin riêng tư; log có kiểm soát.

**16. Mở quá nhiều thư mục cùng lúc.** Nên đóng mỗi DirectoryStream sau khi xong; file descriptors không vô hạn.

**17. Xóa/move file dựa vào danh sách vừa đọc mà không xử lý FileNotFound/I/O.** Thư mục biến động có thể khiến entry không còn.

**18. Xem `SecureDirectoryStream` là mặc định trên mọi filesystem.** Đó là khả năng tùy provider, không phải guarantee phổ quát.

## 16. Checklist code review

- [ ] Bài toán chỉ cần duyệt **một cấp**, hay thật ra cần duyệt **cây**?
- [ ] Có dùng `try-with-resources` ở mọi lần mở DirectoryStream?
- [ ] Có vô tình xin **iterator thứ hai** hoặc for-each lại cùng stream?
- [ ] Có phụ thuộc vào **thứ tự** mà API không bảo đảm?
- [ ] Filter glob có đang so **tên**, không phải xác thực loại/nội dung file?
- [ ] Filter tùy chỉnh có xử lý đúng IOException và DirectoryIteratorException?
- [ ] Có phân biệt lỗi mở directory với lỗi giữa quá trình đọc?
- [ ] Có quyết định rõ khi `Files.isRegularFile` không xác định được thuộc tính?
- [ ] Có chính sách symlink và `NOFOLLOW_LINKS` khi cần?
- [ ] Có xử lý việc entry bị thay đổi/xóa giữa liệt kê và mở thật?
- [ ] Có cần giữ nguyên bộ nhớ với thư mục cực lớn hay phải sort?
- [ ] Có dùng đúng provider/Path semantics trên Windows/Linux/macOS?
- [ ] Có test thư mục rỗng, file thường, thư mục con, glob, Filter lỗi và ngoại lệ khi đóng?
- [ ] Nếu xử lý nhạy cảm, có kiểm soát quyền và không mặc định DirectoryStream tạo sandbox?
- [ ] Nếu dùng `Files.list/walk`, có đóng Stream?
- [ ] Nếu cần recursive, có chính sách depth, link cycle và lỗi từng nhánh?
- [ ] Khi ghi/đổi/xóa file, có policy đồng thời, retry và idempotency?
- [ ] Caller có biết ownership và lifetime nếu một API trả về resource trực tiếp?

## 17. Câu hỏi tự đánh giá

**1.** `Files.newDirectoryStream(dir)` trả gì? — Một `DirectoryStream<Path>` đang mở cho **các entry trực tiếp**.

**2.** API này tự duyệt thư mục con không? — **Không**; nó duyệt một cấp.

**3.** Vì sao phải dùng try-with-resources? — Để đóng directory resource ngay cả khi lỗi.

**4.** Có thể dùng hai for-each trên cùng DirectoryStream không? — **Không**; chỉ một iterator.

**5.** Glob `*.txt` có luôn trả các file thường không? — **Không**; nó chỉ lọc tên entry.

**6.** Thứ tự entry theo alphabet có được bảo đảm không? — **Không**, phải sort nếu cần.

**7.** Lỗi I/O xảy ra khi iterator chạy được báo bằng gì? — **DirectoryIteratorException** có nguyên nhân IOException.

**8.** Nếu Filter.accept ném IOException thì sao? — Khi iterator thực thi filter, lỗi có thể bị bọc trong DirectoryIteratorException.

**9.** `Files.size(entry)` đo gì? — **Số byte**, không phải số ký tự.

**10.** `Iterator.remove()` có xóa file được không? — **Không**, iterator của DirectoryStream không hỗ trợ remove.

**11.** Sau close, `next()` có chắc ném ngay? — **Không**, có thể còn phần tử đã read-ahead; không vì thế mà được sử dụng stream đã đóng.

**12.** DirectoryStream có snapshot ổn định không? — **Không**, iterator weakly consistent.

**13.** `Files.list` khác gì? — Trả Stream<Path> cho một cấp, phù hợp pipeline, vẫn phải đóng.

**14.** Muốn tìm file sâu nhiều cấp? — Dùng `Files.walk` hoặc `Files.walkFileTree`.

**15.** Vì sao `getFileName()` hữu ích? — Nó lấy **tên entry**, không phải toàn Path của entry.

**16.** Có thể hoàn toàn tin `Files.isRegularFile` sau khi lọc? — **Không**; có race nếu entry thay đổi giữa các thao tác.

**17.** `SecureDirectoryStream` dùng khi nào? — Khi provider hỗ trợ và cần thao tác relative theo handle để giảm một số nguy cơ race.

**18.** Muốn thống kê “tất cả file đã có đúng lúc bắt đầu” chỉ bằng DirectoryStream được không? — Không được bảo đảm; nó không snapshot thư mục.

## Tài liệu chính thức

- [Java SE 17 — DirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html): Iterator chỉ một lần, read-ahead, close, weak consistency, thứ tự không xác định.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): newDirectoryStream overload, glob, filter, Files.list/walk/walkFileTree.
- [Java SE 17 — DirectoryIteratorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryIteratorException.html): bọc IOException khi duyệt.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác theo directory handle khi provider hỗ trợ.
- [Java SE 17 — FileSystem.getPathMatcher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)): cú pháp glob theo provider.
- [Java SE 17 — FileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html): callback khi cần duyệt cả cây tệp.

**Ghi nhớ:** `DirectoryStream` là một resource để **duyệt trực tiếp từng entry của một thư mục**. Dùng `try-with-resources`, chỉ tạo **một iterator**, không phụ thuộc thứ tự, hiểu rằng glob lọc tên và Filter có thể làm I/O, cũng như xử lý `DirectoryIteratorException` xảy ra trong quá trình duyệt. Nếu thật sự cần duyệt cả cây, chọn `Files.walk`/`Files.walkFileTree` và giải quyết riêng bài toán link, độ sâu và quyền truy cập.