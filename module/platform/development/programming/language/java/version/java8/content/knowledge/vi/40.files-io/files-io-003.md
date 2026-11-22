# Files.list và danh sách con trực tiếp trong Java

**Chủ đề:** Java 8 → Tệp và I/O → Files.list và danh sách con trực tiếp.

Trong Java, khi muốn xem **những tệp và thư mục nằm ngay bên trong một thư mục**, API phù hợp là **`java.nio.file.Files.list(Path dir)`**. Phương thức này trả một **`Stream<Path>`** để xử lý bằng Stream API (`filter`, `map`, `sorted`, `count`, `forEach`, `collect`...). Đây là API được giới thiệu từ **Java 8**, và vẫn được hỗ trợ trong Java hiện hành.

Ví dụ cấu trúc:

~~~text
workspace/
├── a.txt
├── b.log
├── config/
│   └── app.properties
└── images/
    └── logo.png
~~~

Khi gọi `Files.list(workspace)`, stream gồm **ba? Không: bốn** phần tử con trực tiếp: `a.txt`, `b.log`, `config` và `images`. Các file `config/app.properties`, `images/logo.png` **không xuất hiện** trong stream ấy. Bản thân `workspace` cũng **không** là một phần tử trả về.

**Điểm quan trọng nhất cần nhớ:**

> `Files.list(dir)` chỉ liệt kê **một cấp trực tiếp**, không duyệt đệ quy. Nó trả một stream có tài nguyên hệ thống gắn với thư mục, nên **phải đóng stream bằng try-with-resources** ngay cả khi đã gọi toán tử terminal.

**Chỉ đọc danh sách không đồng nghĩa đã đọc nội dung file.** Stream trả **đường dẫn (`Path`)**, không phải chuỗi nội dung file.

Các chương trình độc lập trong bài dùng **Java 17+**, có thể biên dịch và chạy bằng `javac`/`java`. Bản thân `Files.list`, `Path`, `Stream` và `try-with-resources` đều có thể dùng trong Java 8. Một số tiện ích như `Files.writeString`, `Path.of` và `Stream.toList` ra đời **sau Java 8**, sẽ được nêu rõ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích chữ ký `Files.list(Path)` và kết quả `Stream<Path>`.
2. Phân biệt **con trực tiếp** với **hậu duệ ở nhiều cấp**.
3. Viết đúng `try (Stream<Path> entries = Files.list(dir)) { ... }`.
4. Biết vì sao `count()`, `forEach()`, `collect()` **không tự thay cho `close()`**.
5. Dùng `Path.getFileName`, `filter`, `map`, `sorted`, `findFirst`, `count`, `toList`.
6. Hiểu **thứ tự liệt kê không được bảo đảm**, và tạo output ổn định bằng sort khi cần.
7. Lọc file thường, thư mục con, phần mở rộng, xử lý symlink theo `LinkOption.NOFOLLOW_LINKS`.
8. Phân biệt `IOException` khi mở danh sách với `UncheckedIOException` khi duyệt.
9. Nắm đặc tính **lazy** và **weakly consistent** khi thư mục thay đổi đồng thời.
10. So sánh đúng `Files.list`, `Files.walk`, `Files.find`, `Files.newDirectoryStream`.
11. Tránh giữ file descriptor quá lâu, không trả ra stream đã đóng hoặc bị rò rỉ.
12. Thiết kế test dùng thư mục tạm, kết quả xác định và dọn tài nguyên đúng thứ tự.

## 2. Chữ ký và hợp đồng của Files.list

Chữ ký:

~~~java
public static Stream<Path> list(Path dir) throws IOException
~~~

Đây là chữ ký API rút gọn để giải thích, không phải một chương trình độc lập.

**Tham số `dir`** là `Path` trỏ đến thư mục cần liệt kê. **Giá trị trả về** là `Stream<Path>` được tạo với nội dung được điền **lười (lazily populated)**.

Mỗi phần tử có kiểu `Path` biểu diễn một mục con trực tiếp được lấy tương đương với thao tác `dir.resolve(entryName)`. Ví dụ:

~~~java
Path dir = Path.of("workspace");
Path child = dir.resolve("a.txt");

// child là Path tương ứng workspace/a.txt
// (dấu phân cách thực tế phụ thuộc hệ điều hành).
~~~

Đây là đoạn minh họa Java 17+, cần import `java.nio.file.Path`.

### 2.1. Những mục nào xuất hiện?

Với một thư mục thông thường, kết quả có thể gồm:

- File thường (`report.csv`, `notes.txt`).
- Thư mục con (`archive`, `images`).
- Symbolic link nếu hệ thống file hỗ trợ.
- Các loại entry khác mà file system provider biểu diễn bằng `Path`.
- File/thư mục được coi là ẩn, **nếu không có bộ lọc riêng**.

**Không mặc định loại các file bắt đầu bằng dấu chấm.** Việc coi một mục là hidden phụ thuộc file system; một mục `.env` trên Unix và cơ chế hidden attributes trên Windows không hoàn toàn cùng quy tắc. `Files.list` **không lọc hidden entries theo mặc định**.

**Không có các entry đại diện dấu `.` và `..`** cho chính thư mục hiện tại và thư mục cha; tài liệu API nêu những liên kết đặc biệt kiểu này không được đưa vào kết quả.

### 2.2. Những gì không xuất hiện?

- **Không** có `dir` làm phần tử đầu tiên.
- **Không** tự truy cập các file ở bên trong thư mục con sâu hơn một cấp.
- **Không** cung cấp nội dung byte/string của file.
- **Không** sắp xếp theo tên, thời gian, kích cỡ hay loại entry theo một quy tắc được bảo đảm.
- **Không** tạo một snapshot nguyên tử nếu thư mục bị thay đổi trong lúc liệt kê.

### 2.3. Files.list không dùng Path.getFileName() thay cho toàn Path

Một phần tử `Path p` dùng được cho:

~~~java
Path nameOnly = p.getFileName();
Path absolute = p.toAbsolutePath();
boolean isDir = Files.isDirectory(p);
~~~

Đây là đoạn minh họa, cần import `java.nio.file.Files` và `java.nio.file.Path`.

`getFileName()` lấy tên entry cuối của đường dẫn. Nếu chỉ muốn in tên, dùng `p.getFileName().toString()`. Nếu muốn mở/xử lý entry, giữ `Path p` đầy đủ; không tự nối chuỗi `"dir/" + name` vì dấu phân cách phụ thuộc hệ thống.

## 3. Sơ đồ một cấp: so sánh trực quan

Cấu trúc:

~~~text
root/
├── a.txt
├── b.log
├── sub/
│   └── deep.txt
└── assets/
    └── icon.svg
~~~

`Files.list(root)` trả:

~~~text
a.txt
b.log
sub
assets
~~~

(Khi trình bày ở đây các dòng được liệt kê cho dễ đọc; **thứ tự thực tế không được bảo đảm**.)

`Files.list(root)` **không** trả:

~~~text
root
sub/deep.txt
assets/icon.svg
.
..
~~~

**Vì sao?** Phương thức đang liệt kê **directory entries của chính `root`**, không thực hiện tree traversal.

Nếu yêu cầu là **toàn bộ cây thư mục**, cân nhắc `Files.walk(root)` hoặc `Files.find(...)`, chứ không cố coi `Files.list` như một recursive API.

## 4. Ví dụ đầy đủ đầu tiên: liệt kê trực tiếp và tự dọn thư mục tạm

Ví dụ tạo một thư mục tạm độc lập với đường dẫn trên máy người học, tạo hai file và một thư mục con có file sâu hơn, rồi gọi `Files.list`. Sau đó xóa những thứ vừa tạo theo thứ tự **file sâu → thư mục con → các file ngoài → thư mục gốc**.

Lưu thành **`DirectChildrenDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class DirectChildrenDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("direct-list-");
        Path sub = root.resolve("sub");
        Path a = root.resolve("a.txt");
        Path b = root.resolve("b.log");
        Path deep = sub.resolve("deep.txt");

        try {
            Files.createDirectory(sub);
            Files.writeString(a, "A");
            Files.writeString(b, "B");
            Files.writeString(deep, "DEEP");

            try (Stream<Path> entries = Files.list(root)) {
                entries
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .forEach(System.out::println);
            }

            System.out.println(
                    "nestedListed=" +
                    Files.exists(root.resolve("deep.txt")));
        } finally {
            Files.deleteIfExists(deep);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DirectChildrenDemo.java
java DirectChildrenDemo
~~~

**Stdout:**

~~~text
a.txt
b.log
sub
nestedListed=false
~~~

**Giải thích:**

1. `Files.createTempDirectory` tạo nơi thử nghiệm riêng, không phụ thuộc đường dẫn tuyệt đối cứng.
2. `Files.createDirectory(sub)` tạo thư mục con.
3. `Files.writeString(...)` tạo file và ghi nội dung. **`Files.writeString` có từ Java 11+**, phù hợp khi chạy Java 17+.
4. `Files.list(root)` mở stream liệt kê **chỉ ba entry con trực tiếp**.
5. `map(p -> p.getFileName().toString())` biến `Path` thành tên dễ đọc.
6. `sorted()` bảo đảm các dòng trong stdout có thứ tự tên được chọn, thay vì phụ thuộc thứ tự của hệ thống file.
7. `deep.txt` ở `sub/deep.txt`, không phải `root/deep.txt`, nên dòng `nestedListed=false` nhấn mạnh không đi sâu.
8. Stream được đóng **trước khi xóa** nhờ try-with-resources; phần cleanup ở `finally` chạy ngay cả khi một phần ví dụ bị lỗi.

**Lưu ý:** `Files.exists(root.resolve("deep.txt"))` chỉ kiểm tra đường dẫn sai cấp, không phải lệnh khẳng định file `sub/deep.txt` không tồn tại. File sâu vẫn tồn tại trước khi cleanup. Chính phần liệt kê `a.txt,b.log,sub` chứng minh phạm vi một cấp.

### 4.1. Không nên dự đoán thứ tự tự nhiên

Nếu bỏ `sorted()`, có thể thấy:

~~~text
sub
b.log
a.txt
~~~

hoặc một thứ tự khác. Không được tự coi kết quả là theo thứ tự tạo file, alphabet hoặc inode.

**Nếu muốn output xác định:** sắp xếp tường minh trước khi in hoặc trước khi đưa vào báo cáo. Với tên file nhạy cảm hoa-thường, phải xác định rõ cách so sánh thay vì mặc định `sorted()` đáp ứng quy tắc kinh doanh.

## 5. Try-with-resources là phần bắt buộc của cách dùng đúng

Ví dụ chuẩn:

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries.forEach(System.out::println);
}
~~~

Đây là đoạn minh họa với `Path dir` đã có giá trị.

**Tại sao phải đóng?** Stream được `Files.list` trả ra giữ một tham chiếu tới **thư mục đang mở**. Theo hợp đồng Java, thư mục được đóng khi **đóng stream**.

Các terminal operations như:

- `forEach`
- `collect`
- `count`
- `findFirst`
- `anyMatch`
- `reduce`
- `toList`

**không mặc nhiên gọi `close()`** trên stream. Chúng chỉ kết thúc việc tiêu thụ pipeline tương ứng.

### 5.1. Mẫu sai: quên close

~~~java
// Anti-pattern:
Files.list(dir)
        .filter(Files::isRegularFile)
        .forEach(System.out::println);
~~~

Kết quả có thể vẫn đúng ở lần chạy nhỏ, nhưng stream gắn với tài nguyên thư mục không được đóng một cách chắc chắn. Nếu làm thế trong request loop hoặc trên nhiều thư mục, có nguy cơ rò file handles và gây lỗi tài nguyên.

### 5.2. Mẫu đúng: đóng cả khi xử lý thất bại

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries
            .filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

Nếu `forEach` hoặc phép lọc ném exception, try-with-resources vẫn chạy cơ chế đóng stream. Trong ứng dụng thật, kết hợp với xử lý `IOException` và `UncheckedIOException` theo hợp đồng.

### 5.3. Dù chỉ lấy một phần tử vẫn phải close

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    return entries.findFirst();
}
~~~

Đây là **đoạn minh họa của một phương thức trả `Optional<Path>`**, không phải toàn bộ chương trình.

`findFirst()` là một **short-circuit terminal operation**. Nó có thể kết thúc trước khi đọc hết thư mục. Vì stream có directory handle, vẫn phải đóng nó khi kết thúc sớm.

**Đừng dựa vào garbage collector hoặc finalization để đóng handle kịp thời.** Dùng `try-with-resources`.

## 6. Stream lười (lazy) nhưng không phải một danh sách bất biến

`Files.list` trả `Stream<Path>` được điền khi tiêu thụ. Từ "lười" có nghĩa API không yêu cầu gom mọi entry thành một `List<Path>` ngay trong lúc tạo stream.

Ví dụ:

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    long count = entries.count();
    System.out.println(count);
}
~~~

Đây là đoạn minh họa. Count phải duyệt những entries cần thiết, không tự được bảo đảm là O(1).

### 6.1. Một stream chỉ tiêu thụ một lần

~~~java
// Anti-pattern:
try (Stream<Path> entries = Files.list(dir)) {
    long count = entries.count();
    entries.forEach(System.out::println); // Không hợp lệ.
}
~~~

Sau khi terminal operation tiêu thụ stream, không được tái sử dụng pipeline. Lần hai có thể ném `IllegalStateException`.

**Giải pháp A:** mở stream mới cho thao tác mới (và đóng từng stream).

**Giải pháp B:** nếu thư mục nhỏ/vừa và thực sự cần dùng nhiều lần, materialize danh sách trước khi đóng:

~~~java
List<Path> children;

try (Stream<Path> entries = Files.list(dir)) {
    children = entries.toList(); // Java 16+
}

System.out.println(children.size());
children.forEach(System.out::println);
~~~

Đây là đoạn minh họa Java 17+. `Stream.toList()` có từ **Java 16** và trả `List` không sửa được. Nếu cần compile Java 8, dùng `entries.collect(Collectors.toList())`.

### 6.2. List<Path> chỉ là snapshot các tên Path đã quan sát

Materialize một danh sách giúp **đóng directory handle và dùng lại các Path**. Nó không khiến hệ thống file đứng yên. Sau đó file có thể bị xóa, đổi tên hoặc thay nội dung.

**Không nhầm:**
- *Snapshot Java List của các Path đã thu thập*.
- *Snapshot nguyên tử của trạng thái toàn bộ thư mục/hệ thống file*.

`Files.list` có semantics **weakly consistent** khi thư mục đổi trong lúc duyệt, nên nó không được bảo đảm là một snapshot nguyên tử của mọi entry tại một thời điểm.

## 7. Lọc chỉ file thường, chỉ thư mục con và theo phần mở rộng

`Files.list` tự trả cả file lẫn thư mục; dùng `filter` để chọn loại.

### 7.1. Chỉ file thường

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    List<Path> regularFiles = entries
            .filter(Files::isRegularFile)
            .toList();
}
~~~

Đây là đoạn minh họa Java 17+. `Files.isRegularFile(p)` **mặc định có thể theo symbolic link** để kiểm tra đối tượng đích. Nếu chỉ muốn nhận những entry bản thân chúng là file thường, không theo symlink, dùng:

~~~java
.filter(p -> Files.isRegularFile(
        p, LinkOption.NOFOLLOW_LINKS))
~~~

Đây là đoạn rút gọn cần import `java.nio.file.LinkOption`.

**Cảnh báo:** `Files.isRegularFile` trả false khi không xác định được trạng thái vì lỗi I/O; nếu muốn phân biệt “không phải file thường” và “không đọc được thuộc tính”, dùng `Files.readAttributes` với `BasicFileAttributes` và xử lý `IOException`.

### 7.2. Chỉ thư mục con

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries
            .filter(Files::isDirectory)
            .forEach(System.out::println);
}
~~~

**Không có đệ quy:** lệnh này chỉ đưa vào những entry **thư mục trực tiếp của dir**, không mở chúng để tìm cấp sâu hơn.

Dùng `Files.isDirectory(p, LinkOption.NOFOLLOW_LINKS)` nếu cần phân loại entry là thư mục thực mà không coi symlink tới thư mục là directory.

### 7.3. Lọc phần mở rộng

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries
            .filter(Files::isRegularFile)
            .filter(p -> p.getFileName()
                    .toString()
                    .endsWith(".txt"))
            .forEach(System.out::println);
}
~~~

Đây là phép so sánh hậu tố **phân biệt hoa-thường**. File `REPORT.TXT` không khớp với `.txt` nếu dùng trực tiếp.

Muốn bỏ qua hoa-thường cho một quy tắc ứng dụng có chủ đích, có thể chuyển tên với `toLowerCase(Locale.ROOT)` rồi kiểm tra hậu tố. **Không suy ra hệ thống file của máy cũng phân biệt hoa-thường giống như cách so sánh Java String.**

## 8. Ví dụ đầy đủ: lọc .txt, phân loại và đếm con trực tiếp

Lưu thành **DirectFilterDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DirectFilterDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("filter-list-");

        Path x = dir.resolve("x.txt");
        Path z = dir.resolve("z.txt");
        Path log = dir.resolve("b.log");
        Path folder = dir.resolve("docs.txt");

        try {
            Files.createFile(x);
            Files.createFile(z);
            Files.createFile(log);
            Files.createDirectory(folder);

            try (Stream<Path> entries = Files.list(dir)) {
                String names = entries
                        .filter(p -> Files.isRegularFile(
                                p, LinkOption.NOFOLLOW_LINKS))
                        .map(p -> p.getFileName().toString())
                        .filter(name -> name.endsWith(".txt"))
                        .sorted()
                        .collect(Collectors.joining(","));

                System.out.println("txtFiles=" + names);
            }

            try (Stream<Path> entries = Files.list(dir)) {
                System.out.println(
                        "directCount=" + entries.count());
            }

            try (Stream<Path> entries = Files.list(dir)) {
                String categories = entries
                        .map(p -> {
                            String type =
                                    Files.isDirectory(
                                            p,
                                            LinkOption.NOFOLLOW_LINKS)
                                            ? "DIR:"
                                            : Files.isRegularFile(
                                            p,
                                            LinkOption.NOFOLLOW_LINKS)
                                            ? "FILE:"
                                            : "OTHER:";

                            return type + p.getFileName();
                        })
                        .sorted()
                        .collect(Collectors.joining("|"));

                System.out.println("categories=" + categories);
            }
        } finally {
            Files.deleteIfExists(x);
            Files.deleteIfExists(z);
            Files.deleteIfExists(log);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectFilterDemo.java
java DirectFilterDemo
~~~

**Stdout:**

~~~text
txtFiles=x.txt,z.txt
directCount=4
categories=DIR:docs.txt|FILE:b.log|FILE:x.txt|FILE:z.txt
~~~

**Giải thích:**

1. Thư mục gốc chứa ba file và một thư mục có đuôi `.txt`.
2. Bộ lọc `isRegularFile(..., NOFOLLOW_LINKS)` loại thư mục `docs.txt` dù tên giống file text.
3. `endsWith(".txt")` nhận `x.txt`, `z.txt`.
4. `count()` đếm **các entry trực tiếp** nên bằng 4, không phải 3.
5. Nhờ `.sorted()` trên chuỗi đã ánh xạ, stdout có thứ tự ổn định.
6. Mỗi toán tử terminal dùng **một stream mới và mỗi stream đều được đóng**.

**Không gom cả ba terminal operations vào cùng một stream.** Stream đã tiêu thụ thì không thể `count()` lần hai hoặc `forEach()` thêm.

## 9. Files.list so với Files.walk, Files.find và DirectoryStream

Bốn API đều hữu ích, nhưng giải quyết các yêu cầu khác nhau.

| API | Phạm vi | Kiểu kết quả | Có resource cần đóng? |
|---|---|---|---|
| **Files.list(dir)** | Con trực tiếp của dir | `Stream<Path>` | **Có** |
| **Files.walk(start)** | Cả cây, đệ quy theo độ sâu | `Stream<Path>` | **Có** |
| **Files.walk(start, maxDepth)** | Root và con tới mức sâu cho phép | `Stream<Path>` | **Có** |
| **Files.find(start, depth, matcher)** | Đi trong cây và chọn theo `Path` + attributes | `Stream<Path>` | **Có** |
| **Files.newDirectoryStream(dir)** | Con trực tiếp, dùng `DirectoryStream<Path>` | `DirectoryStream<Path>` | **Có** |

### 9.1. Điểm dễ nhầm: walk(root, 1) gồm cả root

Với:

~~~text
root/
├── a.txt
└── sub/
    └── deep.txt
~~~

**Files.list(root)** có các phần tử:

~~~text
a.txt
sub
~~~

**Files.walk(root, 1)** có:

~~~text
root
a.txt
sub
~~~

**Files.walk(root)** hoặc `Files.walk(root, Integer.MAX_VALUE)` có thể đi xuống `sub/deep.txt` theo cơ chế duyệt cây.

**Không coi `Files.walk(root, 1)` hoàn toàn bằng `Files.list(root)`**: walk có phần tử chính root và có chính sách đọc metadata/traversal khác.

### 9.2. Files.find

`Files.find(start, maxDepth, (path, attrs) -> ...)` duyệt cây với bộ lọc theo `BasicFileAttributes`. Dùng khi cần tìm file theo type, kích thước hoặc điều kiện dựa trên attributes, thay vì liệt kê một cấp.

**Không cần Files.find nếu bài toán chỉ là hiện tên các mục con trực tiếp**. Files.list là lựa chọn đơn giản hơn.

### 9.3. Files.newDirectoryStream

`Files.newDirectoryStream(dir)` trả `DirectoryStream<Path>`. Nó phù hợp với cách duyệt từng entry, kể cả khi làm việc với thư mục rất lớn. Có overload nhận glob như `newDirectoryStream(dir, "*.java")`.

Như Files.list, DirectoryStream phải đóng bằng try-with-resources. Nếu cần thao tác race-resistant trên directory entries trong môi trường an ninh cao, xem thêm `SecureDirectoryStream` khi file system provider hỗ trợ.

### 9.4. java.io.File.listFiles() vẫn tồn tại nhưng là một mô hình khác

`java.io.File.listFiles()` trả mảng `File[]`, không phải `Stream<Path>` lười, và có semantics lỗi khác (ví dụ có thể trả null). Nó **không phải API bị xóa**, nhưng khi viết mới với NIO Path/Stream, Files.list hoặc DirectoryStream thường phù hợp hơn.

**Không đưa kiến thức từ File.listFiles() sang suy luận sai về Files.list**: Files.list ném IOException khi không thể mở thư mục, không trả `File[]` hoặc `null` cho trường hợp tương ứng.

## 10. Ví dụ đầy đủ: quan sát khác biệt giữa list và walk

Lưu thành **ListVersusWalkDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ListVersusWalkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("list-walk-");
        Path a = root.resolve("a.txt");
        Path sub = root.resolve("sub");
        Path deep = sub.resolve("deep.txt");

        try {
            Files.createFile(a);
            Files.createDirectory(sub);
            Files.createFile(deep);

            try (Stream<Path> paths = Files.list(root)) {
                String value = paths
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .collect(Collectors.joining(","));

                System.out.println("list=" + value);
            }

            try (Stream<Path> paths = Files.walk(root, 1)) {
                String value = paths
                        .map(p -> p.equals(root)
                                ? "ROOT"
                                : p.getFileName().toString())
                        .sorted()
                        .collect(Collectors.joining(","));

                System.out.println("walkDepth1=" + value);
            }

            try (Stream<Path> paths = Files.walk(root)) {
                long count = paths.count();
                System.out.println("walkAllCount=" + count);
            }
        } finally {
            Files.deleteIfExists(deep);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(a);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListVersusWalkDemo.java
java ListVersusWalkDemo
~~~

**Stdout:**

~~~text
list=a.txt,sub
walkDepth1=ROOT,a.txt,sub
walkAllCount=4
~~~

**Giải thích:** Với bốn Path `root`, `root/a.txt`, `root/sub`, `root/sub/deep.txt`:

- `list` nhận 2 con trực tiếp.
- `walk(root, 1)` nhận `root` và 2 con.
- `walk(root)` nhận tất cả 4 Path.

**Lưu ý:** `Files.walk` mặc định không đi theo symbolic links ở các mức sâu hơn trừ khi dùng `FileVisitOption.FOLLOW_LINKS`. Với Files.list, bản thân phép liệt kê chỉ có một cấp nên không có bước recursion vào bất kỳ mục nào.

## 11. Xử lý thứ tự liệt kê

**Không có thứ tự liệt kê thống nhất do Files.list bảo đảm.** Những yếu tố như file system provider, kiểu hệ thống file, thay đổi thư mục và hệ điều hành có thể ảnh hưởng thứ tự.

### 11.1. Sắp xếp tên khi cần output xác định

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries
            .map(p -> p.getFileName().toString())
            .sorted()
            .forEach(System.out::println);
}
~~~

Đây là sắp xếp `String` theo natural order, không tự là thứ tự ngôn ngữ địa phương.

Nếu có tên `A.txt`, `a.txt`, ký tự có dấu hoặc cần thứ tự người dùng mong đợi, cân nhắc comparator cụ thể:

~~~java
Comparator<Path> byName =
        Comparator.comparing(
                p -> p.getFileName().toString());

try (Stream<Path> entries = Files.list(dir)) {
    entries.sorted(byName).forEach(System.out::println);
}
~~~

Đoạn minh họa cần import `java.util.Comparator`.

### 11.2. Limit trước/sau sort có ý nghĩa khác nhau

~~~java
entries.limit(10);
~~~

Lấy tối đa 10 entry theo encounter order của stream; **không hứa đó là mười tên đầu alphabet**.

~~~java
entries.sorted(byName).limit(10);
~~~

Cần xem xét toàn bộ danh sách trước để xác định mười phần tử đầu theo comparator, nên có thể tốn bộ nhớ/thời gian hơn trên thư mục lớn.

**Không vừa yêu cầu “top 10 theo alphabet” vừa bỏ sort**, và không khẳng định `limit(10)` tự động nhanh khi đã đặt một toán tử stateful `sorted()` phía trước.

## 12. File ẩn và symbolic link

`Files.list` không có mặc định “chỉ hiện file thường không ẩn”. Nó liệt kê các **directory entries**, còn chương trình tự quyết định lọc.

### 12.1. File ẩn

`Files.isHidden(path)` trả `boolean` nhưng **có thể ném IOException** theo file system provider. Khái niệm hidden khác nhau giữa các nền tảng:

- Trên nhiều hệ Unix, dấu chấm đầu tên thường được coi là hidden.
- Trên Windows, thuộc tính hidden là quy tắc hệ thống riêng.
- Provider khác có thể có semantics khác.

Nếu chỉ muốn loại **tên bắt đầu bằng dấu chấm** theo quy tắc ứng dụng, dùng:

~~~java
.filter(p -> !p.getFileName()
        .toString()
        .startsWith("."))
~~~

Đây là **lọc tên**, không phải cách định nghĩa hidden trên mọi hệ thống. Nếu yêu cầu đúng theo file system, dùng `Files.isHidden` và xử lý `IOException` phù hợp.

### 12.2. Symbolic link

Một symbolic link có thể nằm trong danh sách con trực tiếp, nhưng `Files.list(root)` **không tự mở thư mục đích của link để đệ quy**.

Khi phân loại:

~~~java
Files.isSymbolicLink(path);
Files.isDirectory(path);
Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS);
~~~

- `isSymbolicLink` kiểm tra entry là link.
- `isDirectory(path)` mặc định có thể theo link để kiểm tra đích.
- `isDirectory(path, NOFOLLOW_LINKS)` kiểm tra bản thân entry, giúp phân biệt một link trỏ tới thư mục với một thư mục thật.

Tương tự áp dụng cho `isRegularFile`.

**Đừng xây test bắt buộc tạo symlink mà giả định nó luôn được phép trên Windows hoặc mọi file system.** Một số môi trường hạn chế quyền tạo symbolic link. Những ví dụ runnable chính trong bài chủ động không phụ thuộc quyền symlink.

### 12.3. Link và vấn đề an toàn đường dẫn

`Path.normalize()` chỉ loại các đoạn tên dư thừa về mặt cú pháp, **không tự kiểm tra filesystem hoặc bảo vệ khỏi link traversal**. Nếu đường dẫn thư mục là đầu vào của người dùng, cần quy tắc sandbox/authorization rõ ràng, có thể dùng real path resolution, policy về link và các thao tác an toàn theo provider.

Đừng cho phép người dùng truy cập mọi đường dẫn trên server chỉ vì code gọi Files.list và có thêm một phép kiểm tra tên sơ sài.

## 13. Xử lý IOException và UncheckedIOException

`Files.list(Path)` khai báo `throws IOException` khi **mở thư mục**. Có thể gặp:

- Đường dẫn không tồn tại (`NoSuchFileException` trên những provider phù hợp).
- Đường dẫn trỏ file thường thay vì thư mục (`NotDirectoryException` là một exception chuyên biệt tùy provider).
- Lỗi quyền truy cập hoặc I/O khác.
- Vấn đề tạm thời ở filesystem/network filesystem.

**Đừng giả định mọi provider đều ném cùng một lớp IOException chuyên biệt**; tài liệu ghi `NotDirectoryException` là tùy chọn cụ thể.

### 13.1. Lỗi sau khi stream đã mở

Vì stream lazy, I/O có thể thất bại **khi tiêu thụ** sau khi `Files.list` đã trả về. Trong trường hợp này, tài liệu Java mô tả checked `IOException` được bọc trong **`UncheckedIOException`**, rồi ném từ thao tác stream gây truy cập.

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries.forEach(System.out::println);
} catch (IOException ex) {
    System.err.println("Could not open directory: "
            + ex.getMessage());
} catch (UncheckedIOException ex) {
    System.err.println("Failed while listing: "
            + ex.getCause());
}
~~~

Đây là đoạn minh họa trong method có `Path dir` hợp lệ và các import phù hợp.

**Không chỉ catch IOException rồi cho rằng mọi lỗi traversal đã được xử lý.** `UncheckedIOException` là `RuntimeException`, cần chính sách riêng khi pipeline lazy gặp I/O.

Nếu trong lambda tự đọc `Files.size(p)` hoặc `Files.readAttributes(p, ...)` (các API có checked IOException), phải xử lý/lan truyền lỗi ấy theo semantics riêng. `Stream.filter` không cho phép ném checked IOException trực tiếp nếu không có wrapper thích hợp.

### 13.2. Không che mọi lỗi bằng giá trị mặc định

Một anti-pattern:

~~~java
// Anti-pattern:
try (Stream<Path> entries = Files.list(dir)) {
    return entries.count();
} catch (IOException ex) {
    return 0L;
}
~~~

Trả 0 khiến caller không phân biệt **thư mục trống thật** với **không được quyền liệt kê** hoặc lỗi I/O.

Nếu nghiệp vụ muốn bỏ qua lỗi, phải có lý do và phản hồi rõ. Trong API quan trọng, có thể trả lỗi domain, log có ngữ cảnh, hoặc đưa kết quả lỗi ra caller.

### 13.3. Một ví dụ lỗi file không phải directory

Lưu thành **ListErrorDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class ListErrorDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile(
                "not-a-directory-", ".txt");

        try {
            try (Stream<Path> ignored = Files.list(file)) {
                System.out.println("unreachable");
            } catch (IOException ex) {
                System.out.println("rejected=true");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListErrorDemo.java
java ListErrorDemo
~~~

**Stdout với file system provider thông thường của JDK:**

~~~text
rejected=true
~~~

**Giải thích:** Files.list đòi đường dẫn thư mục. Một regular file không đáp ứng, nên việc mở directory stream thất bại với IOException hoặc subtype phù hợp. Chương trình chỉ in một boolean không phụ thuộc tên exception chuyên biệt. Trên provider bất thường, ứng dụng vẫn cần dựa vào hợp đồng chính thức và kiểm tra lỗi phù hợp.

## 14. Empty directory: stream rỗng, không phải null

Một thư mục tồn tại nhưng rỗng có zero entries:

~~~java
try (Stream<Path> entries = Files.list(emptyDir)) {
    long count = entries.count(); // 0
}
~~~

**Files.list không trả `null`** như một tín hiệu của thư mục rỗng. Giá trị trả về là một stream, và terminal operation có thể cho kết quả 0 hoặc `Optional.empty()` nếu không có phần tử.

Ví dụ:

~~~java
try (Stream<Path> entries = Files.list(emptyDir)) {
    Optional<Path> first = entries.findFirst();
    // first.isEmpty() là true trên Java 11+.
}
~~~

Đây là đoạn minh họa Java 17+. `Optional.isEmpty()` có từ Java 11; nếu compile Java 8, dùng `!first.isPresent()`.

**Không dùng sự tồn tại của thư mục dựa trên count lớn hơn 0.** Một thư mục rỗng vẫn tồn tại và có thể hoàn toàn hợp lệ.

## 15. Biến Stream<Path> thành dữ liệu trả về an toàn từ service

Một method có thể muốn cung cấp **danh sách tên** cho caller:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class DirectoryNames {
    public static List<String> directNames(Path directory)
            throws IOException {

        try (Stream<Path> entries = Files.list(directory)) {
            return entries
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .toList();
        }
    }
}
~~~

Đây là class Java 17+ (không có main). `Stream.toList()` ra đời từ Java 16; với Java 8 thay bằng `.collect(Collectors.toList())`.

**Vì sao trả `List<String>` tốt hơn trả Stream đã đóng?** Caller nhận dữ liệu đã materialize, stream đã close và directory handle đã được giải phóng.

### 15.1. Anti-pattern: trả stream nằm trong try

~~~java
// Anti-pattern:
Stream<Path> directChildren(Path dir) throws IOException {
    try (Stream<Path> entries = Files.list(dir)) {
        return entries;  // Đã đóng trước khi caller dùng!
    }
}
~~~

Khi return ra khỏi scope, try-with-resources đóng stream. Caller không thể coi nó là một nguồn còn mở để duyệt.

### 15.2. Trả raw Stream mà không nói ownership cũng rủi ro

~~~java
Stream<Path> directChildren(Path dir) throws IOException {
    return Files.list(dir);
}
~~~

Đoạn này có thể có chủ đích nếu hợp đồng API nói **caller bắt buộc close stream**. Nhưng nếu caller quên, handle có thể bị rò.

Với API public đơn giản, cân nhắc trả một danh sách đã materialize nếu kích thước vừa phải, hoặc cung cấp callback/iterator API với lifecycle được quản lý rõ.

**Một `Path` object được collect ra List không giữ directory stream mở**; nhưng nội dung thực tế mà Path trỏ tới có thể thay đổi sau đó.

## 16. Files.list và thư mục rất lớn

Với hàng trăm nghìn hoặc hàng triệu entries, cần phân biệt:

1. **Duyệt tuần tự và xử lý từng Path:** có thể giữ lượng bộ nhớ bổ sung thấp.
2. **`.toList()` / `collect(toList())`:** materialize mọi phần tử, có chi phí bộ nhớ tỷ lệ số entries.
3. **`.sorted()`** trước terminal operation: thường cần nắm nhiều phần tử để sắp xếp, tốn bộ nhớ và thời gian.
4. **`.count()`**: vẫn có thể phải duyệt nhiều entries, không nên coi là một metadata lookup O(1).
5. **`.limit(10)`** khi chưa sort: có thể giúp dừng sớm, nhưng không bảo đảm “10 entry theo thứ tự alphabet”.
6. **`newDirectoryStream`**: hữu ích khi muốn quản lý iteration trực tiếp và có thể dùng glob filter theo filename.

### 16.1. Duyệt mà không giữ toàn bộ danh sách

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries
            .filter(Files::isRegularFile)
            .forEach(this::processFile);
}
~~~

Đây là đoạn minh họa trong một instance method có `processFile(Path)`.

**Cảnh báo:** `forEach` chạy xử lý theo pipeline, có thể ném exception. Nếu `processFile` giữ Path để dùng bất đồng bộ sau này, file có thể thay đổi hoặc bị xóa. Nếu xử lý lâu, directory stream có thể giữ handle mở lâu; cần cân nhắc materialize một batch và đóng sớm.

### 16.2. Đừng mặc định parallel() sẽ tốt hơn

~~~java
// Không mặc định đây là cách tối ưu:
Files.list(dir).parallel().forEach(...);
~~~

Ngoài việc **chưa close stream**, duyệt file system thường bị giới hạn bởi I/O/provider và không được đảm bảo cải thiện throughput bằng parallel stream. Nếu cần xử lý đồng thời, thiết kế executor/concurrency limit, tài nguyên và chính sách lỗi theo workload thay vì tự đặt `.parallel()`.

### 16.3. DirectoryStream cho nhu cầu kiểm soát vòng đời

~~~java
try (DirectoryStream<Path> entries =
             Files.newDirectoryStream(dir)) {

    for (Path p : entries) {
        // Xử lý từng entry.
    }
}
~~~

Cần import `java.nio.file.DirectoryStream`. `Files.newDirectoryStream(dir, "*.txt")` có thể lọc theo glob của filename, nhưng vẫn không tự duyệt thư mục con.

## 17. Weak consistency khi thư mục đang thay đổi

Oracle mô tả stream từ Files.list là **weakly consistent**. Có nghĩa:

- Stream không đóng băng thư mục.
- Một entry được tạo sau lúc mở stream **có thể xuất hiện hoặc không xuất hiện**.
- Một entry bị xóa/đổi tên trong lúc duyệt **có thể tạo quan sát khác nhau**.
- Không có cam kết rằng toàn bộ các phần tử đại diện cho một filesystem snapshot nguyên tử.
- Việc traversal “thread-safe” theo mô tả API **không** có nghĩa ứng dụng có transaction filesystem.

### 17.1. TOCTOU — kiểm tra rồi dùng có khoảng cách

Ví dụ:

~~~java
try (Stream<Path> entries = Files.list(dir)) {
    entries
            .filter(Files::isRegularFile)
            .forEach(path -> {
                // Tệp có thể đã bị xóa giữa filter và xử lý!
                process(path);
            });
}
~~~

Đây là đoạn minh họa với process(Path). Nếu một tiến trình khác sửa thư mục, trạng thái entry có thể đổi sau khi `isRegularFile` trả true.

Nếu mở file, đọc nội dung hay thao tác an ninh, **bước thực hiện thật phải tự xử lý IOException, race và kiểm tra quyền truy cập theo hợp đồng**. `Files.list` không khóa các entries hay bảo đảm chúng vẫn tồn tại.

### 17.2. Cần snapshot thật sự thì sao?

Một danh sách Path thu thập từ Files.list vẫn chưa phải snapshot transaction. Nếu yêu cầu nhất quán mạnh, có thể cần:

- Kiểm soát writer bằng khóa/giao thức trong chính ứng dụng.
- Duyệt từ một filesystem snapshot có khả năng hỗ trợ.
- Sử dụng database hoặc transaction store cho danh sách authoritative.
- Dùng `SecureDirectoryStream` khi provider hỗ trợ cho một số thao tác race-resistant (không phải giải pháp transaction toàn cây).

**Không suy ra `Files.list` tạo snapshot chỉ vì bạn gọi `collect(toList())`.**

## 18. Một số tình huống ứng dụng

### 18.1. Hiển thị danh sách file tải lên của một thư mục

~~~java
List<String> names;

try (Stream<Path> entries = Files.list(uploadDir)) {
    names = entries
            .filter(Files::isRegularFile)
            .map(p -> p.getFileName().toString())
            .sorted()
            .toList();
}
~~~

**Điểm cần bổ sung trong production:** xác thực quyền xem, không cho caller tự chọn đường dẫn bất kỳ, giới hạn số lượng kết quả và phân trang nếu thư mục lớn.

### 18.2. Tìm những thư mục con trực tiếp

~~~java
try (Stream<Path> entries = Files.list(projectDir)) {
    List<String> subfolders = entries
            .filter(p -> Files.isDirectory(
                    p, LinkOption.NOFOLLOW_LINKS))
            .map(p -> p.getFileName().toString())
            .sorted()
            .toList();
}
~~~

`NOFOLLOW_LINKS` giúp không coi một symlink trỏ đến directory là một thư mục thực, nếu đó là policy bạn muốn.

### 18.3. Đếm số file cấu hình ở cấp gốc

~~~java
try (Stream<Path> entries = Files.list(configDir)) {
    long count = entries
            .filter(p -> Files.isRegularFile(
                    p, LinkOption.NOFOLLOW_LINKS))
            .filter(p -> p.getFileName()
                    .toString().endsWith(".properties"))
            .count();
}
~~~

Đoạn này **chỉ đếm các file config ở cấp gốc**, không đếm file `.properties` bên trong thư mục con.

### 18.4. Tìm tên file đầu tiên theo thứ tự

~~~java
Optional<String> name;

try (Stream<Path> entries = Files.list(dir)) {
    name = entries
            .map(p -> p.getFileName().toString())
            .sorted()
            .findFirst();
}
~~~

Ở đây `sorted().findFirst()` lấy tên nhỏ nhất theo natural String order, **khác** với chỉ `.findFirst()` trên stream chưa có thứ tự liệt kê được bảo đảm.

### 18.5. Giao diện lọc glob

Nếu người dùng muốn chỉ các entry `*.json`, có thể dùng `Files.newDirectoryStream(dir, "*.json")` hoặc `Files.list(dir).filter(...)` với matcher riêng. Khi dùng glob, cần biết nó so trên tên/Path theo API cụ thể và file system provider; đừng tự coi mọi pattern glob là regex của Java.

## 19. Hệ thống file, quyền truy cập và bảo mật

Khi đường dẫn đến từ HTTP parameter hoặc input của người dùng, Files.list có thể tiết lộ tên file hệ thống. Cần:

- **Xác thực và phân quyền** trước khi duyệt.
- Giới hạn root directory được phép truy cập.
- Validate/ràng buộc các đường dẫn do người dùng chỉ định.
- Định nghĩa policy đối với symbolic links.
- Không chỉ dùng `String.startsWith` để kiểm tra một đường dẫn nằm trong root; dùng Path-aware checks và hiểu symlink/TOCTOU.
- Giới hạn số entries trả về, đặc biệt với thư mục rất lớn.
- Không log hoặc trả về đường dẫn tuyệt đối, tên file nhạy cảm khi không cần thiết.
- Xử lý file biến mất hoặc permission thay đổi giữa lúc list và đọc.

**`Path.normalize()` là phép biến đổi cú pháp, không đảm bảo an ninh**: một symlink có thể trỏ ra ngoài root dù tên Path đã normalize. Với thao tác đòi hỏi tính an toàn cao, thiết kế authorization và filesystem operations dựa trên giải pháp provider/OS phù hợp.

### 19.1. Files.isReadable không phải bằng chứng thao tác tiếp theo luôn thành công

Tương tự `Files.exists`, các phép check trạng thái có thể lỗi thời ngay lập tức. Đừng kiểm tra rồi giả định file vẫn không thay đổi; xử lý lỗi ở thao tác I/O thật.

## 20. Những lỗi phổ biến cần tránh

1. **Nhầm Files.list là duyệt đệ quy.** Nó chỉ liệt kê một cấp.
2. **Tưởng stream gồm chính thư mục gốc.** Files.list chỉ gồm entries bên trong; Files.walk mới gồm start.
3. **Quên try-with-resources.** Directory handle có thể bị rò.
4. **Tin terminal operation tự đóng.** `forEach`, `count`, `collect`, `findFirst` không tự bảo đảm close.
5. **Trả một stream đã đóng từ bên trong try-with-resources.** Caller không thể dùng pipeline còn mở.
6. **Trả raw stream mà không quy định caller phải close.** Dễ rò tài nguyên.
7. **Tiêu thụ một Stream hai lần.** Phải mở stream mới hoặc materialize rồi dùng lại.
8. **Giả định thứ tự alphabet.** Dùng `.sorted()` theo policy rõ ràng.
9. **Dùng `.limit(10)` rồi quảng bá “10 file đầu theo alphabet”.** Nếu chưa sort, không có đảm bảo.
10. **Dùng `sorted().limit(10)` nhưng tưởng chỉ đọc 10 entries.** Sort có thể phải đọc rất nhiều.
11. **Dùng `.toList()` cho thư mục khổng lồ mà không xét bộ nhớ.** Có thể tốn nhiều RAM.
12. **Gọi Files.list rồi nghĩ đã đọc nội dung file.** Stream chỉ chứa Path.
13. **Dùng `getFileName()` rồi mất thông tin thư mục khi cần mở file.** Giữ Path gốc nếu cần thao tác.
14. **Đếm số file bằng `.count()` mà không lọc directory.** Count đang đếm mọi entry trực tiếp.
15. **Chỉ lọc hậu tố `.txt` mà quên kiểm tra loại file.** Một directory cũng có thể tên `docs.txt`.
16. **Giả định file ẩn luôn bị loại.** Files.list không có bộ lọc hidden mặc định.
17. **Giả định symbolic links luôn được loại.** Chúng có thể là entry trả về; phân loại cần policy rõ.
18. **Dùng `Files.isRegularFile` nhưng tưởng lỗi I/O luôn ném IOException.** Phương thức có thể trả false khi không xác định được.
19. **Catch IOException khi mở nhưng quên UncheckedIOException trong lúc duyệt lazy.**
20. **Bỏ qua lỗi I/O bằng cách trả danh sách rỗng.** Caller không phân biệt lỗi và thư mục trống.
21. **Giả định danh sách là snapshot nguyên tử khi có writer.** Stream là weakly consistent.
22. **Kiểm tra `exists`/`isRegularFile` rồi không xử lý lỗi ở thao tác dùng tiếp theo.** Có TOCTOU.
23. **Dùng `Files.walk(root, 1)` thay list mà không xử lý root.** Walk gồm cả root.
24. **Sao chép cú pháp API mới vào project bắt buộc Java 8.** `Files.writeString` Java 11+, `Stream.toList` Java 16+, `Path.of` Java 11+.
25. **Đổi sang parallel stream mà không quản lý lifecycle và I/O.** Không được đảm bảo cải thiện hiệu năng.
26. **Xóa thư mục tạm trước khi đóng stream.** Có thể gây vấn đề handle tùy hệ điều hành, đặc biệt trên Windows.
27. **Tạo fixture kiểm thử trong thư mục thật của người dùng.** Dùng `Files.createTempDirectory`, cleanup đúng các entry tự tạo.
28. **Dùng path String để kiểm soát quyền truy cập.** Cần Path-aware/real-path policy và chống symlink traversal.
29. **Tưởng `newDirectoryStream(dir)` đệ quy.** Nó cũng chỉ liệt kê directory entries một cấp.
30. **Dùng `Files.list` trong một vòng request nóng rồi quên giới hạn số kết quả.** Có thể chiếm file handles, I/O và memory.

## 21. Checklist khi viết code production

- [ ] Đầu vào là **directory Path** hợp lệ và đã được cho phép truy cập.
- [ ] Chỉ muốn **mục con trực tiếp**, không cần recursive traversal.
- [ ] Dùng `try (Stream<Path> stream = Files.list(dir))`.
- [ ] Có xử lý `IOException` mở directory và `UncheckedIOException` khi tiêu thụ nếu cần.
- [ ] Không dùng stream sau khi terminal operation hoặc sau close.
- [ ] Nếu trả kết quả cho caller, xác định ownership và materialization hợp lý.
- [ ] Nếu cần tên ổn định để hiển thị/test, sắp xếp tường minh.
- [ ] Lọc đúng file thường/thư mục/link, cân nhắc NOFOLLOW_LINKS.
- [ ] Đã phân biệt directory có hậu tố `.txt` với regular file `.txt`.
- [ ] Đã xác định có/không bao gồm hidden entries.
- [ ] Cân nhắc thư mục lớn trước khi `.sorted()` hoặc `.toList()`.
- [ ] Không coi danh sách Path là snapshot nguyên tử khi filesystem thay đổi.
- [ ] Khi xử lý entry sau liệt kê, xử lý file bị xóa/đổi tên/permission thay đổi.
- [ ] Với đường dẫn user-provided, có authorization và chính sách symlink phù hợp.
- [ ] Tests dùng temp directory và đóng stream trước cleanup.
- [ ] Các snippets đúng JDK của dự án: Java 8 core, Java 11+ writeString, Java 16+ toList.
- [ ] Không có assumption về thứ tự native directory listing.

## 22. Bài tập thực hành

### Bài 1 — Con trực tiếp

Tạo cấu trúc:

~~~text
sandbox/
├── readme.md
├── settings.json
└── nested/
    └── hidden-inside.txt
~~~

Hãy viết một lần `Files.list(sandbox)` rồi in tên theo alphabet. Dự đoán số phần tử, giải thích vì sao `nested/hidden-inside.txt` không có trong kết quả.

### Bài 2 — Chỉ file thường

Tạo file `report.txt` và directory `backup.txt` cùng nằm trực tiếp trong một root. Hãy dùng `Files.isRegularFile(..., LinkOption.NOFOLLOW_LINKS)` để chỉ nhận `report.txt`.

### Bài 3 — Đóng stream

Viết một method `List<String> directFileNames(Path dir)`; dùng try-with-resources và `.toList()` khi compile Java 17+. Hãy giải thích vì sao không nên return một Stream đã đóng.

### Bài 4 — Đếm mục con

Một thư mục có 3 files và 2 subdirectories. `Files.list(dir).count()` cho số gì? Muốn đếm chỉ file thường thì cần thay pipeline như thế nào?

### Bài 5 — Files.list và Files.walk

So sánh các phần tử của `Files.list(root)`, `Files.walk(root, 1)` và `Files.walk(root)` với một cây sâu 3 cấp. API nào bao gồm bản thân root?

### Bài 6 — Thứ tự

Một thư mục có `z.txt`, `a.txt`, `m.txt`. Có được assert Files.list trả đúng thứ tự alphabet không? Cách sửa test?

### Bài 7 — Lazy error

Một filesystem provider gặp I/O error giữa lúc stream đã trả về và đang duyệt. Cần xử lý exception nào ở lúc tạo stream và exception nào khi tiêu thụ?

### Bài 8 — Weak consistency

Một producer tạo file mới khi reader đang duyệt `Files.list`. Có được bảo đảm file mới sẽ xuất hiện không? Vì sao không?

### Bài 9 — Symlink

Nếu `link-to-directory` là một symbolic link trong thư mục, hãy giải thích sự khác nhau giữa `Files.isDirectory(path)` và `Files.isDirectory(path, NOFOLLOW_LINKS)`.

### Bài 10 — Danh sách lớn

So sánh bộ nhớ của `.forEach(...)` và `.sorted().toList()` trên một thư mục nhiều triệu entries. Điều gì xảy ra nếu `.limit(10)` được đặt sau `.sorted()`?

### Bài 11 — Đường dẫn an toàn

Giải thích vì sao `Path.normalize()` và `Files.exists()` không tự ngăn symlink traversal hoặc TOCTOU khi user chỉ định thư mục để liệt kê.

### Bài 12 — Xử lý file thay đổi

Một API lấy danh sách file xong mới lần lượt đọc nội dung. File thứ hai bị xóa giữa hai bước. Hãy viết chiến lược bắt IOException, báo tình trạng không còn và không làm rò stream.

## 23. Câu hỏi tự kiểm tra

**1. `Files.list(dir)` trả kiểu gì?** — `Stream<Path>`.

**2. Nó đệ quy không?** — Không, chỉ một cấp.

**3. Có trả chính `dir` không?** — Không.

**4. Có trả thư mục con trực tiếp không?** — Có, như một entry Path; không đi sâu vào nội dung của nó.

**5. Có mặc định loại hidden files không?** — Không.

**6. Có mặc định sắp xếp theo tên không?** — Không có bảo đảm.

**7. Vì sao dùng try-with-resources?** — Để đóng stream và directory handle.

**8. `count()` có tự đóng stream không?** — Không có bảo đảm tự close resource.

**9. `findFirst()` có thể trả gì với thư mục rỗng?** — `Optional.empty()`.

**10. Có dùng lại stream sau `count()` không?** — Không.

**11. Dùng `.toList()` cho Java 8 được không?** — Không; Stream.toList từ Java 16. Dùng Collectors.toList trong Java 8.

**12. `Files.writeString` có từ Java 8 không?** — Không, từ Java 11.

**13. `Path.of` có từ Java 8 không?** — Không, từ Java 11; Java 8 có `Paths.get(...)`.

**14. Files.list và Files.walk(root,1) khác ở đâu?** — `walk` gồm cả `root`, list chỉ gồm con trực tiếp.

**15. Files.walk mặc định đi sâu không?** — Có, nếu không giới hạn độ sâu và truy cập được.

**16. Files.list có trả nội dung file không?** — Không, trả Path.

**17. `p.getFileName()` trả gì?** — Thành phần tên cuối của Path.

**18. `Files.isRegularFile` mặc định có thể theo symlink không?** — Có; NOFOLLOW_LINKS đổi hành vi.

**19. `Files.isHidden` có nghĩa giống hệt trên Windows và Unix không?** — Không; tùy file system/provider.

**20. Một directory tên `docs.txt` có qua bộ lọc `endsWith(".txt")` không?** — Có nếu chỉ lọc tên; cần lọc isRegularFile để loại.

**21. `Files.list` ném gì nếu không thể mở directory?** — IOException hoặc subtype thích hợp.

**22. Nếu I/O lỗi lúc tiêu thụ stream thì sao?** — Có thể ném UncheckedIOException.

**23. Weakly consistent nghĩa gì?** — Stream không đóng băng directory; các thay đổi concurrent có thể được phản ánh hoặc không.

**24. `Files.list` có tạo filesystem snapshot nguyên tử không?** — Không.

**25. `Files.newDirectoryStream` có đệ quy không?** — Không, cũng là con trực tiếp.

**26. `sorted().limit(10)` có thể tốn bộ nhớ hơn `limit(10)` không?** — Có, do sorting cần xem nhiều phần tử.

**27. Nếu Files.list trả danh sách tên rồi file bị xóa, Path còn hợp lệ để đọc không?** — Không được bảo đảm; thao tác đọc sau có thể lỗi.

**28. Dùng File.listFiles và Files.list giống nhau hoàn toàn không?** — Không; khác API, kết quả và error/lifecycle semantics.

**29. Khi thư mục lớn, nên cân nhắc gì?** — Không materialize/sort vô hạn, xử lý tuần tự/batch, đóng handle sớm.

**30. Có thể duyệt folder người dùng nhập mà không kiểm tra quyền không?** — Không; cần authorization và path validation.

## 24. Tổng kết

**`Files.list(Path)` là API hiện hành để liệt kê các directory entries nằm ngay một cấp bên dưới thư mục.** Nó đơn giản, kết hợp tốt với Stream API, nhưng có ba đặc tính cần nhớ song song:

- **Không đệ quy:** chỉ lấy con trực tiếp; không bao gồm root hoặc con ở cấp sâu.
- **Có tài nguyên cần đóng:** luôn dùng try-with-resources cho `Stream<Path>`, kể cả khi đã gọi `count`, `collect`, `findFirst`.
- **Không snapshot nguyên tử:** kết quả lazy và weakly consistent, không có thứ tự native được bảo đảm khi directory đổi.

Các thói quen tốt:

1. Dùng `Path.getFileName()` khi cần tên, giữ Path đầy đủ khi cần thao tác file.
2. Sắp xếp tường minh để output/test ổn định.
3. Lọc loại entry bằng `Files.isRegularFile/isDirectory`; quy định symlink với `NOFOLLOW_LINKS`.
4. Xử lý `IOException` lúc mở và `UncheckedIOException` khi duyệt.
5. Không dùng stream nhiều lần; materialize nếu cần dùng kết quả sau khi đóng.
6. Chọn `Files.walk` khi cần recursive traversal, `newDirectoryStream` khi cần iteration trực tiếp/glob.
7. Với đường dẫn do người dùng cung cấp, phải thiết kế authorization, bảo vệ symlink traversal và TOCTOU.
8. Với thư mục lớn, kiểm soát memory/handles và không dùng `.sorted().toList()` một cách vô hạn.

### Tài liệu chính thức Oracle

- [Files — Java SE 26: list(Path), walk, find, isDirectory, isRegularFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [Path — Java SE 26: resolve, getFileName, relativize, toRealPath](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html)
- [Stream — Java SE 26: terminal operations và close](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [DirectoryStream — Java SE 26: iterate entries, glob và resource lifecycle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/DirectoryStream.html)
- [LinkOption — Java SE 26: NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html)
- [UncheckedIOException — Java SE 26: wrapping I/O errors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/UncheckedIOException.html)
- [BasicFileAttributes — Java SE 26: loại entry và metadata](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
