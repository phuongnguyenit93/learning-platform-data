# Lọc bằng glob hoặc `DirectoryStream.Filter` khi duyệt thư mục trong Java

## 1. Mục tiêu bài học

Khi ứng dụng cần liệt kê những mục phù hợp trong một thư mục — chẳng hạn các file `.java`, báo cáo `.txt` đủ lớn, hoặc file đáp ứng nhiều điều kiện — Java cung cấp hai overload rất hữu ích của `Files.newDirectoryStream`:

~~~java
Files.newDirectoryStream(directory, "*.java");
Files.newDirectoryStream(directory, customFilter);
~~~

Đây là **hai biểu thức minh họa**, trong đó `directory` là `Path` và `customFilter` là `DirectoryStream.Filter<Path>`. Phương thức thứ nhất lọc bằng **glob pattern** trên **tên từng entry**; phương thức thứ hai gọi một hàm lọc có thể kiểm tra **tên, loại mục, kích thước hoặc metadata**.

Hai overload này xuất hiện từ **Java 7**, vẫn được hỗ trợ trong Java hiện hành. Chúng được dùng cho **một thư mục trực tiếp**, không tự đi vào thư mục con. Chủ đề thuộc phần *Duyệt cây tệp*, nhưng cần phân biệt rõ: **lọc một cấp** bằng `DirectoryStream` là nền tảng để chọn entry, còn **duyệt toàn cây** phải sử dụng vòng lặp đệ quy có kiểm soát hoặc các API như `Files.walkFileTree`/`Files.walk`/`Files.find` khi thích hợp.

Sau bài, bạn có thể:

1. Chọn glob hoặc `DirectoryStream.Filter<Path>` đúng với loại điều kiện.
2. Viết pattern `*.java`, `*.{java,md}`, `file?.log` và `file[12].log` đúng ngữ nghĩa.
3. Phân biệt **file name** với **đường dẫn đầy đủ** khi khớp glob.
4. Hiểu rằng glob lọc **tên entry**, không tự giới hạn chỉ file thường, không tự đi sâu vào thư mục con.
5. Kết hợp `Files.isRegularFile`, `Files.size`, phần mở rộng và `LinkOption.NOFOLLOW_LINKS` trong Filter.
6. Sử dụng try-with-resources và hiểu vòng lặp trên `DirectoryStream<Path>`, thứ tự không được đảm bảo và giới hạn **một iterator**.
7. Xử lý `PatternSyntaxException`, `DirectoryIteratorException` và các lỗi `IOException`.
8. Giữ kết quả test có thứ tự ổn định bằng cách sắp xếp sau khi duyệt.
9. Chọn API tương đương phù hợp trong Java 17+: `Files.list`, `Files.walk` và `Files.find`.
10. Nhận biết các rủi ro portability, symlink, thay đổi file đồng thời và lọc nhầm file không được phép xử lý.

**Phiên bản:** Tất cả các ví dụ hoàn chỉnh được viết và kiểm thử với Java 17+, sử dụng API vẫn được hỗ trợ hiện nay. `Files.newDirectoryStream` và `FileSystem.getPathMatcher` có từ Java 7. `Files.list`, `Files.walk` và `Files.find` có từ Java 8. Không dùng thư viện ngoài hoặc kiến thức legacy để thay thế những API hiện hành.

## 2. Hiểu đúng cấu trúc `DirectoryStream`

Khởi tạo một `Path` đến thư mục:

~~~java
Path directory = Path.of("src");
~~~

Đây là một dòng minh họa trong phương thức đã import `java.nio.file.Path`. `Path.of` có từ Java 11; nếu dự án thực sự biên dịch với source level Java 7, có thể dùng `Paths.get("src")`.

Khi gọi:

~~~java
try (DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory, "*.java")) {
    for (Path entry : stream) {
        System.out.println(entry.getFileName());
    }
}
~~~

đoạn này sẽ:

- Mở một **directory stream** cho thư mục `directory`.
- Duyệt các entry **trực tiếp** trong thư mục đó. Ví dụ `src/Main.java` và `src/Utils.java` là các entry; `src/nested/Deep.java` không phải entry trực tiếp.
- Chỉ đưa ra những entry có **tên** khớp glob `*.java`.
- Trả mỗi entry bằng một `Path` đại diện cho vị trí đó, không trả một String tên file.
- Đóng directory stream khi rời try-with-resources, giải phóng handle và tài nguyên filesystem có liên quan.

`DirectoryStream<Path>` implement `Iterable<Path>` và `AutoCloseable`. Nó **không phải** `java.util.stream.Stream<Path>`; vì vậy không tự gọi các phép `filter/map/collect` của Java Stream trực tiếp trên đối tượng DirectoryStream. Muốn dùng phong cách Java Stream, có thể xem `Files.list` (Java 8+) và vẫn phải đóng nó.

### 2.1. Chữ “lọc” không có nghĩa dữ liệu đã được đọc vào bộ nhớ

`DirectoryStream` được thiết kế để duyệt entry của một thư mục **theo iterator**, không yêu cầu nạp toàn bộ danh sách từ đầu. Tuy nhiên, kết quả từ directory stream **không có thứ tự cố định theo API**; muốn hiển thị theo tên hoặc kiểm tra stdout chính xác, hãy lưu các tên đã lọc vào list rồi `Collections.sort`.

Chỉ lưu list khi phù hợp với kích thước đầu ra. Với một thư mục rất lớn và quy trình xử lý theo từng file, có thể xử lý entry ngay khi lặp để giảm bộ nhớ.

### 2.2. Một cấp duyệt khác duyệt đệ quy

Giả sử cây tệp:

~~~text
project/
├── Main.java
├── Utils.java
├── README.md
└── nested/
    └── Deep.java
~~~

Lời gọi:

~~~java
Files.newDirectoryStream(projectPath, "*.java")
~~~

chỉ xem các **entry của `project/`**, tức `Main.java` và `Utils.java`. Nó **không** tự tìm `nested/Deep.java`.

**Đừng suy ra rằng** đổi glob thành `**/*.java` sẽ khiến DirectoryStream tự đi xuống thư mục con: glob vẫn chỉ được áp dụng cho **tên của các entry trực tiếp**, còn việc duyệt cây là hành vi của API gọi, không phải quyền năng của dấu sao kép.

## 3. Ví dụ hoàn chỉnh 1 — Glob `*.java` chỉ lọc một cấp

Tạo file `GlobJavaDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

public class GlobJavaDemo {
    static String names(DirectoryStream<Path> stream) {
        List<String> names = new ArrayList<>();
        for (Path entry : stream) {
            names.add(entry.getFileName().toString());
        }
        Collections.sort(names);
        return String.join(",", names);
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("glob-java-");
        Path nested = root.resolve("nested");

        try {
            Files.createFile(root.resolve("Main.java"));
            Files.createFile(root.resolve("Utils.java"));
            Files.createFile(root.resolve("notes.md"));
            Files.createDirectory(nested);
            Files.createFile(nested.resolve("Deep.java"));

            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(root, "*.java")) {
                System.out.println("java=" + names(stream));
            }

            System.out.println("nestedStillExists=" +
                    Files.exists(nested.resolve("Deep.java")));
        } finally {
            Files.deleteIfExists(nested.resolve("Deep.java"));
            Files.deleteIfExists(nested);
            Files.deleteIfExists(root.resolve("Main.java"));
            Files.deleteIfExists(root.resolve("Utils.java"));
            Files.deleteIfExists(root.resolve("notes.md"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa source:

~~~bash
javac -encoding UTF-8 --release 17 GlobJavaDemo.java
java GlobJavaDemo
~~~

Stdout chính xác:

~~~text
java=Main.java,Utils.java
nestedStillExists=true
~~~

Giải thích:

1. File tạm được tạo trong thư mục tạm của hệ điều hành, giúp test không sửa dữ liệu dự án.
2. `Main.java` và `Utils.java` là entry trực tiếp của `root`, tên khớp `*.java`.
3. `notes.md` không khớp phần mở rộng.
4. `Deep.java` tuy tồn tại nhưng thuộc `nested/`, nên không được glob `*.java` trên `root` trả ra.
5. Hàm `names` chuyển `Path.getFileName()` thành String rồi **sort**, tránh lệ thuộc thứ tự trả về của filesystem.
6. Sau khi đóng directory stream, cleanup xóa file con trước, thư mục cha sau.

**Chỉ dùng cách `names` lưu cả kết quả vào List cho tập dữ liệu vừa phải**. Trong hệ thống duyệt hàng triệu mục, cần đánh giá yêu cầu thứ tự và mức sử dụng bộ nhớ trước khi gom tất cả kết quả.

## 4. Cú pháp glob được Java hỗ trợ

Với `Files.newDirectoryStream(dir, glob)`, tham số `glob` là một **chuỗi pattern đơn thuần**. Không cần thêm tiền tố `"glob:"` cho overload này; phương thức sẽ giải thích theo quy tắc glob của FileSystem provider.

Các mẫu cần nhớ:

| Glob | Nghĩa |
| --- | --- |
| `*` | Không hoặc nhiều ký tự trong một **thành phần tên** |
| `?` | Đúng **một ký tự** trong thành phần tên |
| `*.java` | Tên kết thúc `.java` |
| `*.{java,md}` | Tên kết thúc bằng `.java` **hoặc** `.md` |
| `file?.log` | `file` + đúng một ký tự + `.log` |
| `file[12].log` | Chỉ `file1.log` hoặc `file2.log` |
| `report[0-9].txt` | Một chữ số trong khoảng 0–9 |
| `[!a-z]*` | Ký tự đầu **không** thuộc khoảng a–z |
| `*.{txt,csv,json}` | Một trong ba phần mở rộng |
| `**` | Về mặt ngôn ngữ glob, khớp qua ranh giới thư mục; **không khiến DirectoryStream duyệt đệ quy** |

Các dấu `{...}` tạo tập lựa chọn, phân cách bởi dấu phẩy; theo chuẩn glob của `FileSystem.getPathMatcher`, nhóm lựa chọn không được lồng nhau. Ký tự `\` dùng để escape metacharacters trong pattern; trong Java source, backslash phải escape theo cú pháp String Java, nên việc viết pattern cho dấu đặc biệt cần chú ý **hai lớp escaping**.

**Một số điểm dễ hiểu sai:**

- `*` khớp **zero hoặc nhiều** ký tự trong một thành phần tên; `?` là **đúng một** ký tự.
- `file?.log` khớp `file1.log` nhưng không khớp `file10.log` vì hai chữ số không phải một.
- Glob không phải regex. Viết `.*\.java` theo thói quen regex không phải mẫu glob nên dùng; với glob, chọn `*.java`.
- `*.java` áp dụng cho **filename**, không buộc entry đó là file thường: một thư mục tên `archive.java` cũng có thể khớp.
- Một filename bắt đầu bằng dấu chấm **không bị glob `*` tự loại**. Nếu muốn loại file ẩn, cần chính sách riêng; khái niệm hidden có thể khác theo provider.
- Quy tắc **case sensitivity** của glob do filesystem implementation quyết định. Không mặc định `*.java` sẽ xử lý `Main.JAVA` giống nhau trên mọi OS.
- Dấu phân tách đường dẫn, root và một số chi tiết match phụ thuộc FileSystem provider; đừng ép syntax toàn bộ path thành kết luận chung cho mọi OS.

Nguồn: [FileSystem.getPathMatcher — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)).

## 5. Ví dụ hoàn chỉnh 2 — `{...}`, `?` và `[...]`

Tạo file `GlobSyntaxDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;

public class GlobSyntaxDemo {
    static String matching(Path root, String glob) throws Exception {
        List<String> names = new ArrayList<>();

        try (DirectoryStream<Path> stream =
                     Files.newDirectoryStream(root, glob)) {
            for (Path entry : stream) {
                names.add(entry.getFileName().toString());
            }
        }

        Collections.sort(names);
        return String.join(",", names);
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("glob-syntax-");
        String[] files = {
                "Alpha.java", "README.md", "file1.log",
                "file2.log", "file10.log", "plain"
        };

        try {
            for (String name : files) {
                Files.createFile(root.resolve(name));
            }

            System.out.println("alternatives=" +
                    matching(root, "*.{java,md}"));
            System.out.println("question=" +
                    matching(root, "file?.log"));
            System.out.println("characterClass=" +
                    matching(root, "file[12].log"));
            System.out.println("all=" +
                    matching(root, "*"));
        } finally {
            for (String name : files) {
                Files.deleteIfExists(root.resolve(name));
            }
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 GlobSyntaxDemo.java
java GlobSyntaxDemo
~~~

Stdout:

~~~text
alternatives=Alpha.java,README.md
question=file1.log,file2.log
characterClass=file1.log,file2.log
all=Alpha.java,README.md,file1.log,file10.log,file2.log,plain
~~~

Các kết quả cho thấy:

1. `*.{java,md}` chọn `Alpha.java` và `README.md`; không cần hai lượt duyệt.
2. `file?.log` chọn `file1.log` và `file2.log`; loại `file10.log` vì phần `?` chỉ nhận một ký tự.
3. `file[12].log` cũng chọn hai tên đó nhưng **chỉ** chấp nhận 1 hoặc 2 ở vị trí được yêu cầu.
4. `*` bao phủ mọi entry trực tiếp ở root trong bộ fixture.
5. Hàm sắp xếp tên trước khi in, vì Java **không quy định thứ tự directory iteration**.

Trong code sản phẩm, pattern có thể được cung cấp qua cấu hình; cần kiểm tra/giới hạn cú pháp được phép và xử lý `PatternSyntaxException`. Không coi glob là ranh giới an ninh để cấp quyền đọc tệp.

## 6. `FileSystem.getPathMatcher` và khác biệt name/path

Khi cần **kiểm tra một Path riêng lẻ** hoặc tái sử dụng matcher trong nhiều nơi, Java cung cấp:

~~~java
PathMatcher matcher =
        directory.getFileSystem().getPathMatcher("glob:*.java");

boolean accepted = matcher.matches(path.getFileName());
~~~

Đây là **đoạn minh họa** trong phương thức có `directory`/`path` kiểu `Path`. Khác với `Files.newDirectoryStream(dir, "*.java")`, API `getPathMatcher` nhận **chuỗi gồm prefix cú pháp**: `"glob:" + pattern`. Ngoài `glob:`, nó cũng hỗ trợ `regex:`, nhưng chính sách và escaping của regex **khác** glob.

Quan trọng: Một pattern `*.java` chỉ khớp **tên file**. Nếu đưa cả đường dẫn chứa nhiều thành phần như `/tmp/run-123/Example.java` vào matcher, pattern không nhất thiết khớp vì path có separator. Cách thường gặp khi chỉ quan tâm extension là:

~~~java
matcher.matches(path.getFileName())
~~~

Chính `Files.newDirectoryStream(dir, glob)` theo Javadoc cũng so khớp **String representation của file name** của mỗi entry, không phải cả absolute path.

### 6.1. Ví dụ hoàn chỉnh 3 — Matcher áp dụng đúng đối tượng

Tạo file `PathMatcherDemo.java`:

~~~java
import java.nio.file.*;

public class PathMatcherDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("matcher-");
        Path java = root.resolve("Example.java");
        Path txt = root.resolve("notes.txt");

        try {
            Files.createFile(java);
            Files.createFile(txt);

            PathMatcher matcher = root.getFileSystem()
                    .getPathMatcher("glob:*.java");

            System.out.println("filenameMatches=" +
                    matcher.matches(java.getFileName()));
            System.out.println("fullPathMatches=" +
                    matcher.matches(java));
            System.out.println("txtMatches=" +
                    matcher.matches(txt.getFileName()));
        } finally {
            Files.deleteIfExists(java);
            Files.deleteIfExists(txt);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 PathMatcherDemo.java
java PathMatcherDemo
~~~

Stdout trong môi trường đã kiểm thử:

~~~text
filenameMatches=true
fullPathMatches=false
txtMatches=false
~~~

**Giải thích:** Tên `Example.java` khớp, nhưng đường dẫn đầy đủ từ root tạm chứa thêm thành phần và dấu phân tách nên không khớp `glob:*.java`; `notes.txt` không có phần mở rộng cần thiết. Quy tắc matching path có thể phụ thuộc provider, nên lời khuyên chuẩn là **chủ động đưa `getFileName()` khi muốn match tên**.

**Tình huống khác:** Nếu bạn thực sự muốn khớp một đường dẫn tương đối có nhiều cấp, cần thiết kế pattern theo **cấu trúc path** và API duyệt cây phù hợp; không nhầm việc chọn `PathMatcher` có `**` với việc tự duyệt cây.

## 7. `DirectoryStream.Filter<Path>`: điều kiện tùy chỉnh

Glob rất hợp khi chỉ cần khớp tên. Nhưng điều kiện nghiệp vụ thường phức tạp hơn:

- Chỉ lấy **file thường**, không lấy thư mục.
- Chỉ nhận file có phần mở rộng `.txt` không phân biệt chữ hoa/thường.
- Chỉ nhận file có kích thước **ít nhất 3 byte**.
- Chỉ lấy file do ứng dụng được phép xử lý, hoặc metadata phù hợp.

Dùng `DirectoryStream.Filter<Path>`:

~~~java
DirectoryStream.Filter<Path> filter = entry ->
        Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS)
        && entry.getFileName().toString()
                .toLowerCase(Locale.ROOT).endsWith(".txt")
        && Files.size(entry) >= 3L;

try (DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory, filter)) {
    for (Path entry : stream) {
        // entry đáp ứng tất cả điều kiện trong filter.
    }
}
~~~

Đây là **đoạn trong phương thức** đã khai báo `directory` kiểu `Path`; cần import `java.nio.file.*` và `java.util.Locale`. `Filter<Path>` là **functional interface** có phương thức `boolean accept(Path entry) throws IOException`, nên có thể dùng lambda Java 8+ hoặc anonymous class nếu cần cú pháp kiểu Java 7.

### 7.1. Từng điều kiện có tác dụng gì?

1. `Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS)` kiểm tra đó là file thường **mà không theo symbolic link**. Vì đứng đầu phép `&&`, nếu không phải regular file, hai điều kiện sau không được chạy.
2. `entry.getFileName()` nhận tên entry, không chứa đường dẫn thư mục cha.
3. `toLowerCase(Locale.ROOT)` giúp so sánh phần mở rộng ASCII `.txt` một cách ổn định không phụ thuộc locale mặc định. Đây là **chính sách do ứng dụng tự định nghĩa**; không phải tính case-insensitive tự động của glob.
4. `Files.size(entry) >= 3L` kiểm tra kích thước file theo byte. `Files.size` có thể ném `IOException`; không có cách nào biến kiểm tra metadata thành “miễn phí”.
5. Dấu `&&` làm các điều kiện kết hợp theo **AND**; nếu muốn OR, phải viết `||` và dùng ngoặc rõ ràng.
6. `NOFOLLOW_LINKS` được chọn có chủ đích để không nhận symlink trỏ tới file khác. Nếu ứng dụng cần theo symlink, có thể đổi chính sách nhưng phải đánh giá rủi ro/path ownership.

**Một điểm tinh tế:** `Files.isRegularFile` trả `false` nếu không thể xác định file là regular file, bao gồm một số tình huống lỗi I/O. Nếu ứng dụng cần phân biệt “không phải file thường” với “không đọc được attributes”, nên dùng `Files.readAttributes` và xử lý IOException rõ ràng, thay vì coi `false` là kết luận chắc chắn về loại file.

### 7.2. Ví dụ hoàn chỉnh 4 — Lọc đồng thời loại file, phần mở rộng và size

Tạo `CustomFilterDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

public class CustomFilterDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("filter-demo-");
        Path dir = root.resolve("archive.txt");

        try {
            Files.writeString(root.resolve("a.txt"), "abc");
            Files.writeString(root.resolve("b.TXT"), "x");
            Files.writeString(root.resolve("c.txt"), "data");
            Files.writeString(root.resolve("notes.md"), "long");
            Files.createDirectory(dir);

            DirectoryStream.Filter<Path> filter = entry ->
                    Files.isRegularFile(
                            entry, LinkOption.NOFOLLOW_LINKS)
                    && entry.getFileName().toString()
                            .toLowerCase(Locale.ROOT)
                            .endsWith(".txt")
                    && Files.size(entry) >= 3;

            List<String> matches = new ArrayList<>();
            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(root, filter)) {
                for (Path entry : stream) {
                    matches.add(entry.getFileName().toString());
                }
            }

            Collections.sort(matches);
            System.out.println("filtered=" +
                    String.join(",", matches));
            System.out.println("directoryExcluded=" +
                    !matches.contains("archive.txt"));
            System.out.println("shortExcluded=" +
                    !matches.contains("b.TXT"));
        } finally {
            for (String name :
                    new String[]{"a.txt", "b.TXT", "c.txt", "notes.md"}) {
                Files.deleteIfExists(root.resolve(name));
            }
            Files.deleteIfExists(dir);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CustomFilterDemo.java
java CustomFilterDemo
~~~

Stdout:

~~~text
filtered=a.txt,c.txt
directoryExcluded=true
shortExcluded=true
~~~

Phân tích:

- `a.txt` (3 byte) và `c.txt` (4 byte) thỏa mọi điều kiện.
- `b.TXT` có phần mở rộng chấp nhận vì đã dùng `Locale.ROOT`, nhưng kích thước chỉ 1 byte nên bị loại.
- `notes.md` không có phần mở rộng cần thiết.
- `archive.txt` có tên đúng phần mở rộng nhưng là **directory**, nên bị loại bởi `Files.isRegularFile(..., NOFOLLOW_LINKS)`.
- Không có phụ thuộc vào thứ tự liệt kê vì code sort trước khi in.

Một filter làm I/O như `Files.size` có thể chậm nếu thư mục chứa rất nhiều entry hoặc filesystem nằm trên mạng. Hãy tối ưu thứ tự điều kiện rẻ trước, điều kiện I/O sau; nếu cần lọc theo rất nhiều thuộc tính, cân nhắc API `Files.find` khi duyệt cây để tận dụng `BasicFileAttributes` có sẵn.

## 8. Glob khớp tên — không khẳng định đó là file thường

Nếu thư mục chứa cả:

~~~text
archive.log/    (đây là directory)
event.log       (đây là file)
~~~

thì glob `*.log` có thể trả **cả hai** vì hai tên đều khớp. Muốn file thường, kiểm tra thêm loại entry.

### 8.1. Ví dụ hoàn chỉnh 5 — Tách glob và kiểm tra loại

Tạo file `GlobDirectoryTypeDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;

public class GlobDirectoryTypeDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("glob-type-");
        Path folder = root.resolve("archive.log");
        Path file = root.resolve("event.log");

        try {
            Files.createDirectory(folder);
            Files.createFile(file);

            List<String> all = new ArrayList<>();
            List<String> files = new ArrayList<>();

            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(root, "*.log")) {
                for (Path entry : stream) {
                    all.add(entry.getFileName().toString());
                    if (Files.isRegularFile(
                            entry, LinkOption.NOFOLLOW_LINKS)) {
                        files.add(entry.getFileName().toString());
                    }
                }
            }

            Collections.sort(all);
            Collections.sort(files);
            System.out.println("globEntries=" + String.join(",", all));
            System.out.println("regularOnly=" + String.join(",", files));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 GlobDirectoryTypeDemo.java
java GlobDirectoryTypeDemo
~~~

Stdout:

~~~text
globEntries=archive.log,event.log
regularOnly=event.log
~~~

Đây không phải lỗi glob. Glob chỉ kiểm tra **tên entry**; điều kiện loại mục là một bước nghiệp vụ khác. Bạn có thể lọc loại bằng `DirectoryStream.Filter` ngay từ đầu, hoặc lọc kết quả sau khi lấy từ glob nếu việc duyệt một lần là đủ. `Files.newDirectoryStream` không có overload trực tiếp nhận **vừa String glob vừa Filter** trong cùng một lời gọi; khi cần hai loại điều kiện, đưa chúng vào một Filter (ví dụ tự tạo `PathMatcher`) hoặc lọc sau khi duyệt.

## 9. Kết hợp glob matcher và điều kiện tùy chỉnh trong một Filter

Khi muốn “tên `*.java` **và** là file thường”, có thể dùng `PathMatcher`:

~~~java
PathMatcher matcher = directory.getFileSystem()
        .getPathMatcher("glob:*.java");

DirectoryStream.Filter<Path> filter = entry ->
        matcher.matches(entry.getFileName())
        && Files.isRegularFile(
                entry, LinkOption.NOFOLLOW_LINKS);

try (DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory, filter)) {
    for (Path entry : stream) {
        // Chỉ file thường tên *.java.
    }
}
~~~

Đây là **đoạn minh họa trong một phương thức**, cần import `java.nio.file.*`. Thứ tự điều kiện giúp tránh kiểm tra thuộc tính khi tên không khớp. Một filter có thể bao gồm nhiều điều kiện AND/OR, nhưng hãy giữ predicate dễ đọc, dễ test.

**Nếu pattern đến từ người dùng:** `getPathMatcher("glob:" + pattern)` có thể ném `PatternSyntaxException` nếu pattern không hợp lệ. Đừng nuốt ngoại lệ rồi âm thầm trả danh sách trống: “không có file nào khớp” và “pattern sai cú pháp” là hai trạng thái khác nhau.

## 10. Lỗi glob và IOException bên trong Filter

Hai nguồn lỗi khác nhau cần xử lý riêng:

- **Pattern không hợp lệ:** `Files.newDirectoryStream(directory, "[")` có thể ném `PatternSyntaxException` (unchecked), vì dấu `[` mở character class nhưng không đóng.
- **I/O khi mở thư mục:** không tồn tại, không có quyền, không phải thư mục, hoặc lỗi provider dẫn tới `IOException`; subclass `NotDirectoryException` có thể được dùng nhưng không được bảo đảm ở mọi provider.
- **I/O trong lúc duyệt:** một `IOException` từ filesystem **hoặc từ `Filter.accept`** được bọc trong `DirectoryIteratorException`, ném bởi `hasNext()` hoặc `next()`. Lỗi gốc nằm trong `getCause()`.
- **RuntimeException/Error trong Filter:** được lan truyền đến thao tác iterator tương ứng; chúng không biến thành “không khớp”.
- **Lỗi close:** `DirectoryStream.close()` có thể ném IOException; dùng try-with-resources để quản lý đóng và suppressed exceptions phù hợp.

### 10.1. Ví dụ hoàn chỉnh 6 — Hai loại lỗi

Tạo file `GlobErrorsDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;
import java.util.regex.PatternSyntaxException;

public class GlobErrorsDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("glob-errors-");

        try {
            Files.createFile(root.resolve("first.txt"));

            boolean invalidGlob = false;
            try (DirectoryStream<Path> ignored =
                         Files.newDirectoryStream(root, "[")) {
                // Pattern sai nên không vào khối này.
            } catch (PatternSyntaxException e) {
                invalidGlob = true;
            }
            System.out.println("invalidGlob=" + invalidGlob);

            DirectoryStream.Filter<Path> broken = entry -> {
                throw new IOException("filter-failure");
            };

            boolean wrapped = false;
            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(root, broken)) {
                for (Path unused : stream) {
                    // Không có entry hợp lệ vì filter ném IOException.
                }
            } catch (DirectoryIteratorException e) {
                wrapped = e.getCause() instanceof IOException
                        && "filter-failure".equals(
                                e.getCause().getMessage());
            }
            System.out.println("ioWrapped=" + wrapped);
        } finally {
            Files.deleteIfExists(root.resolve("first.txt"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 GlobErrorsDemo.java
java GlobErrorsDemo
~~~

Stdout:

~~~text
invalidGlob=true
ioWrapped=true
~~~

**Vì sao cần biết `DirectoryIteratorException`?**

Filter được chạy **trong quá trình lặp**, nên câu lệnh mở stream có thể thành công trước khi lỗi I/O xuất hiện. Nếu chỉ bao `Files.newDirectoryStream(...)` trong `try/catch(IOException)` mà bỏ qua lỗi khi iterator duyệt, bạn có thể chưa xử lý được tình huống này. Khi cần thông tin chi tiết, kiểm tra cause của `DirectoryIteratorException` rồi xác định chính sách thử lại, báo lỗi, log hoặc dừng tiến trình.

Đừng coi danh sách chưa liệt kê hết là một kết quả hợp lệ nếu bắt được lỗi giữa chừng mà không thông báo. Một hệ thống backup/indexing có thể gặp hậu quả nghiêm trọng nếu âm thầm bỏ qua các file chưa duyệt.

Nguồn: [Files.newDirectoryStream(Path, Filter) — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newDirectoryStream(java.nio.file.Path,java.nio.file.DirectoryStream.Filter)) và [DirectoryIteratorException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/DirectoryIteratorException.html).

## 11. Một `DirectoryStream` chỉ cấp một iterator

`DirectoryStream` **khác một collection có thể duyệt lại tùy ý**. Theo hợp đồng của nó, mỗi DirectoryStream chỉ cấp **một iterator**. Gọi `stream.iterator()` lần thứ hai dẫn đến `IllegalStateException`, kể cả khi iterator đầu tiên chưa dùng hết.

Cách dùng bình thường:

~~~java
try (DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory)) {
    for (Path entry : stream) {
        // Duyệt một lần rồi đóng.
    }
}
~~~

Không viết hai vòng `for (Path entry : stream)` trên **cùng một** DirectoryStream với kỳ vọng chạy lại từ đầu. Nếu cần hai lượt duyệt, mở một DirectoryStream mới hoặc lưu kết quả vào một Collection theo yêu cầu bộ nhớ và tính nhất quán.

### 11.1. Ví dụ hoàn chỉnh 7 — Contract của iterator

Tạo file `IteratorContractDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;

public class IteratorContractDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("single-iterator-");

        try {
            Files.createFile(root.resolve("sample.txt"));

            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(root)) {
                Iterator<Path> one = stream.iterator();

                boolean secondBlocked = false;
                try {
                    stream.iterator();
                } catch (IllegalStateException expected) {
                    secondBlocked = true;
                }

                System.out.println("secondIteratorBlocked=" +
                        secondBlocked);
                System.out.println("firstHasEntry=" + one.hasNext());
            }
        } finally {
            Files.deleteIfExists(root.resolve("sample.txt"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 IteratorContractDemo.java
java IteratorContractDemo
~~~

Stdout:

~~~text
secondIteratorBlocked=true
firstHasEntry=true
~~~

**Lưu ý thực tế:** Một iterator của `DirectoryStream` được định nghĩa là **weakly consistent**. Nếu thư mục thay đổi trong khi đang duyệt, nó có thể phản ánh hoặc không phản ánh một số thay đổi; đừng coi danh sách thu được là snapshot transactional của hệ thống tệp.

Cũng không có thứ tự cụ thể. Với thao tác cần dữ liệu có thứ tự xác định, hãy thu thập, sắp xếp rồi mới xử lý theo thứ tự; nhưng nếu có process khác đang ghi/xóa file, **sort không biến một lần duyệt thành snapshot nhất quán**.

Nguồn: [DirectoryStream Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/DirectoryStream.html).

## 12. `Files.list` so với `DirectoryStream` trong Java mới

Từ Java 8, `Files.list(dir)` trả `Stream<Path>`, nên có thể viết điều kiện theo Java Stream API:

~~~java
try (Stream<Path> entries = Files.list(directory)) {
    entries.filter(Files::isRegularFile)
           .filter(path -> path.getFileName().toString()
                   .endsWith(".java"))
           .forEach(path -> process(path));
}
~~~

Đây là **đoạn minh họa trong phương thức** có `directory`, `process(Path)` đã khai báo và import `java.nio.file.Files`/`java.util.stream.Stream`. Cũng như `DirectoryStream`, `Files.list` không tự duyệt đệ quy và **phải đóng** stream; đừng gọi `Files.list(dir).collect(...)` mà bỏ qua quản lý resource.

Khi nào dùng?

- **`Files.newDirectoryStream(dir, "*.java")`:** ngắn gọn, tập trung vào lọc filename glob, có từ Java 7.
- **`Files.newDirectoryStream(dir, filter)`:** rõ ràng khi predicate phức tạp/kiểm tra metadata và cần kiểm soát iterator.
- **`Files.list(dir)`:** thuận tiện khi cần pipeline `filter/map/sorted/collect` của Stream API; vẫn có lỗi I/O và resource lifecycle.
- **`Files.walk(dir, depth)` hoặc `Files.find(dir, depth, ...)`:** khi cần duyệt cây nhiều tầng (Java 8+), với giới hạn độ sâu và quy tắc symlink.
- **`Files.walkFileTree`:** khi cần kiểm soát sâu hơn về trước/sau khi vào thư mục, cách báo lỗi và quyết định bỏ qua subtree; API đã có từ Java 7.

### 12.1. Ví dụ hoàn chỉnh 8 — Cùng một yêu cầu, hai API

Tạo file `FilesListAlternativeDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class FilesListAlternativeDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-alt-");
        Path folder = root.resolve("ignore.java");

        try {
            Files.createFile(root.resolve("Main.java"));
            Files.createFile(root.resolve("Utils.java"));
            Files.createFile(root.resolve("README.md"));
            Files.createDirectory(folder);

            List<String> viaGlob = new ArrayList<>();
            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(root, "*.java")) {
                for (Path entry : stream) {
                    if (Files.isRegularFile(entry)) {
                        viaGlob.add(entry.getFileName().toString());
                    }
                }
            }
            Collections.sort(viaGlob);

            List<String> viaList;
            try (Stream<Path> stream = Files.list(root)) {
                viaList = stream
                        .filter(Files::isRegularFile)
                        .map(path -> path.getFileName().toString())
                        .filter(name -> name.endsWith(".java"))
                        .sorted()
                        .collect(Collectors.toList());
            }

            System.out.println("glob=" +
                    String.join(",", viaGlob));
            System.out.println("list=" +
                    String.join(",", viaList));
            System.out.println("equal=" + viaGlob.equals(viaList));
        } finally {
            Files.deleteIfExists(root.resolve("Main.java"));
            Files.deleteIfExists(root.resolve("Utils.java"));
            Files.deleteIfExists(root.resolve("README.md"));
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 FilesListAlternativeDemo.java
java FilesListAlternativeDemo
~~~

Stdout:

~~~text
glob=Main.java,Utils.java
list=Main.java,Utils.java
equal=true
~~~

**Điểm so sánh:** Ở ví dụ này, cả hai cách đều chọn file thường `*.java` trực tiếp trong `root`, bỏ thư mục `ignore.java` dù tên của nó khớp glob. Kết quả được sắp xếp để có stdout ổn định.

Tuy nhiên, hai API **không tuyệt đối đồng nghĩa** trong mọi trường hợp: glob có quy tắc FileSystem provider riêng, còn predicate `endsWith(".java")` là logic String Java, có thể có chính sách case khác nhau. Với directory mutation và I/O errors, cơ chế lỗi/lifecycle của Iterator và Java Stream cũng có khác biệt. Chọn API phù hợp và viết test theo yêu cầu thật.

## 13. Lọc đệ quy: khi một cấp không đủ

Nếu bài toán yêu cầu “tìm mọi file `.java` trong cả cây `src/`”, `newDirectoryStream(src, "*.java")` **không đáp ứng**. Một mẫu Java 17+ dùng `Files.walk`:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(path ->
                    Files.isRegularFile(
                            path, LinkOption.NOFOLLOW_LINKS))
         .filter(path ->
                    path.getFileName().toString().endsWith(".java"))
         .forEach(path -> handle(path));
}
~~~

Đây là **đoạn minh họa**, chưa phải class chạy độc lập; `root` là `Path`, `handle(Path)` do ứng dụng định nghĩa, cần import `Files`, `LinkOption`, `Path`, `Stream`. Nó cho thấy khác biệt của **traversal** với **filtering**: `Files.walk` duyệt cây, rồi hai predicate lọc kết quả.

Cân nhắc thực tế:

- Với cây sâu hoặc rất lớn, đặt **maxDepth** khi có giới hạn nghiệp vụ: `Files.walk(root, maxDepth)`.
- `Files.walk` mặc định không đi theo symbolic links (trừ khi có option) và trả Stream cần đóng.
- `Files.find` (Java 8+) cho phép predicate nhận cả `BasicFileAttributes`, hữu ích khi cần kiểm tra loại file/kích thước trong quá trình duyệt cây.
- `Files.walkFileTree` (Java 7+) phù hợp khi cần xử lý lỗi riêng cho từng thư mục, quyết định không đi vào subtree hay có lifecycle rõ ràng.
- Với symlink, vòng lặp/cycle và đường dẫn trỏ ngoài gốc, phải có chính sách bảo mật rõ. Không tự chọn `FOLLOW_LINKS` chỉ vì muốn “duyệt được nhiều hơn”.
- Không chỉ dựa vào phần mở rộng để suy ra nội dung file, tính an toàn hay quyền truy cập.

**Tách đúng hai bước:** quyết định **đi vào những thư mục nào** là bài toán traversal; quyết định **nhận entry nào** là bài toán filtering. Một predicate `*.java` không thể tự thiết kế chiến lược duyệt cây.

## 14. Tính di động giữa Windows, Linux và filesystem khác nhau

### 14.1. Phân biệt hoa/thường

Glob trên Java tuân theo FileSystem provider; tài liệu không cam kết case-sensitive ở mọi nền tảng. Vì vậy không nên viết một bài test cứng rằng `"*.java"` nhất định bỏ qua `Main.JAVA` trên mọi máy.

Nếu nghiệp vụ quy định file `.JAVA` và `.java` đều hợp lệ, hãy viết chính sách trong `Filter<Path>`:

~~~java
DirectoryStream.Filter<Path> filter = entry ->
        Files.isRegularFile(
                entry, LinkOption.NOFOLLOW_LINKS)
        && entry.getFileName().toString()
                .toLowerCase(Locale.ROOT)
                .endsWith(".java");
~~~

Đây là **đoạn trong phương thức**, cần import `Locale` và NIO. Dùng `Locale.ROOT` cho phép so sánh extension ASCII có kiểm soát; việc xử lý Unicode case folding cho tên ở một hệ thống phức tạp có thể cần quy tắc chuyên biệt.

### 14.2. File ẩn và tên bắt đầu bằng dấu chấm

Theo ngôn ngữ glob của Java, ký tự `.` đầu tên **không bị xử lý đặc biệt**; một glob `*` có thể nhận `.config`. Nhưng `Files.isHidden(entry)` là một API khác và kết quả có thể phụ thuộc filesystem/OS. Muốn ẩn/hiện mục nào, cần chính sách riêng; đừng mặc định dotfile và hidden attribute là một khái niệm thống nhất trên mọi máy.

### 14.3. Symbolic links và việc kiểm tra loại file

`Files.isRegularFile(entry)` mặc định có thể **theo symbolic link** tới target. Nếu yêu cầu chỉ xử lý file thường **không phải symlink**, dùng:

~~~java
Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS)
~~~

Đây là một biểu thức minh họa. Đừng coi một lần kiểm tra loại file là giải pháp an ninh hoàn chỉnh khi kẻ khác có thể đổi đường dẫn giữa lúc kiểm tra và mở file (**TOCTOU**, time-of-check-to-time-of-use). Với thư mục không tin cậy, kiểm soát quyền, sandbox và các primitive filesystem mạnh hơn khi cần.

### 14.4. Thứ tự duyệt và thay đổi đồng thời

DirectoryStream không bảo đảm thứ tự file; Windows, Linux, macOS và từng filesystem có thể trả các entry theo thứ tự khác nhau. Nếu stdout hoặc báo cáo phải ổn định, hãy sort **sau khi lọc**.

Iterator được mô tả là **weakly consistent**. Khi có process khác tạo/xóa/đổi tên file trong lúc liệt kê, danh sách có thể phản ánh hoặc không phản ánh thay đổi. Một lần liệt kê và sort không bảo đảm snapshot giống nhau giữa các máy hay giữa các thời điểm. Với quy trình cần độ nhất quán mạnh, cần phối hợp quyền ghi hoặc snapshot cấp filesystem/ứng dụng.

## 15. Hiệu năng và quản lý tài nguyên

Một vài quy tắc khi lọc trên directory thực:

1. **Đóng stream:** Dùng try-with-resources cho cả `DirectoryStream` và `Files.list/walk/find` Stream. Directory handle là tài nguyên hệ điều hành.
2. **Lọc rẻ trước:** So khớp tên bằng String/PathMatcher trước, chỉ gọi `Files.size/readAttributes` khi thực sự cần.
3. **Không quét lại nhiều lần vô cớ:** Một Filter có thể gộp nhiều điều kiện. Nhưng nếu danh sách cần được kiểm tra tại nhiều thời điểm, mỗi lần quét có thể thấy trạng thái mới.
4. **Không dựa vào thứ tự:** Nếu cần sort, cân nhắc bộ nhớ cho list các kết quả; tránh gom tất cả nếu không cần.
5. **Không dùng glob làm validation bảo mật:** Pattern chỉ giúp chọn tên; việc được phép đọc/ghi file còn phụ thuộc policy và kiểm tra đường dẫn an toàn.
6. **Phân biệt kết quả rỗng và lỗi:** Pattern không khớp cho iterator rỗng; glob sai syntax hoặc thư mục không đọc được phải được xử lý thành lỗi tương ứng.
7. **Không gọi lại iterator:** Một DirectoryStream chỉ được cấp iterator một lần. Nếu cần duyệt lại, mở mới hoặc lưu list.
8. **Chú ý metadata race:** Kiểm tra `Files.size` hoặc `Files.isRegularFile` rồi xử lý entry có thể không còn đúng nếu file bị thay sau đó.
9. **Thao tác trên từng entry có thể lỗi:** Kể cả khi liệt kê thành công, mở file cho xử lý sau đó vẫn có thể thất bại.
10. **Giới hạn cây lớn:** Với duyệt đệ quy, đặt maxDepth và chính sách symlink, tránh quét vô hạn/tốn quá nhiều tài nguyên.

## 16. Khi nào nên chọn glob, Filter hay duyệt cây?

| Nhu cầu | Lựa chọn đề xuất | Lý do |
| --- | --- | --- |
| Liệt kê `*.java` ngay trong một thư mục | `newDirectoryStream(dir, "*.java")` | Ngắn, rõ và đủ |
| Chọn nhiều phần mở rộng theo tên | `newDirectoryStream(dir, "*.{java,md}")` | Glob có group |
| Chọn file thường có kích thước tối thiểu | `DirectoryStream.Filter<Path>` | Cần metadata ngoài tên |
| Không theo symlink | Filter + `NOFOLLOW_LINKS` | Kiểm soát loại entry |
| Case-insensitive extension theo quy định ứng dụng | Filter dùng `Locale.ROOT` | Tránh phụ thuộc case matching của provider |
| Kết hợp glob và metadata | Filter chứa `PathMatcher.matches(entry.getFileName())` | Một lượt lọc với AND/OR |
| Cần pipeline Stream `map/filter/sorted` | `Files.list(dir)` (Java 8+) | API Stream, vẫn chỉ một cấp và phải close |
| Tìm file trong toàn cây | `Files.walk/find` (Java 8+) hoặc `walkFileTree` (Java 7+) | Cần traversal đệ quy |
| Duyệt cây với xử lý lỗi riêng từng thư mục | `Files.walkFileTree` | Có visitor và quyết định subtree |
| Cần xử lý dữ liệu rất lớn từng mục | DirectoryStream/streaming traversal | Tránh nạp toàn bộ danh sách khi không cần |

**Một tiêu chí giúp chọn nhanh:** Nếu câu hỏi là **“Tên file này có hợp pattern?”**, glob đủ. Nếu là **“Entry này có thuộc tính và quy tắc nghiệp vụ nào?”**, Filter phù hợp. Nếu là **“Có ở bất cứ đâu trong cả cây?”**, phải thêm cơ chế traversal.

## 17. Các lỗi và ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`newDirectoryStream(dir,"*.java")` tìm mọi thư mục con.” | Chỉ entry trực tiếp; không đệ quy. |
| “Thêm `**` vào glob tự khiến stream đi sâu.” | Không. Traversal và matching là hai cơ chế khác nhau. |
| “Glob được so với absolute path của entry.” | Overload `newDirectoryStream(dir, glob)` so với **tên entry**. |
| “`*.java` chỉ chọn file thường.” | Thư mục `archive.java` cũng có thể khớp tên. |
| “Glob là regex Java.” | Không. Có ngôn ngữ syntax riêng. |
| “`file?.log` sẽ chọn `file10.log`.” | `?` chỉ một ký tự. |
| “`*.{java,md}` chỉ dùng được trong shell.” | Java FileSystem hỗ trợ group glob. |
| “File bắt đầu bằng dấu chấm tự bị `*` loại.” | Dấu chấm là ký tự bình thường trong glob Java. |
| “Glob luôn phân biệt hoa/thường như Linux.” | Case sensitivity tùy FileSystem implementation. |
| “`DirectoryStream.Filter` chỉ lọc theo tên.” | Có thể kiểm tra type/size/metadata và điều kiện nghiệp vụ. |
| “Mỗi lần `stream.iterator()` sẽ duyệt từ đầu.” | DirectoryStream chỉ cấp **một** iterator. |
| “Kết quả directory stream luôn alphabetically sorted.” | Không có thứ tự cụ thể; sort nếu cần. |
| “Iterator nhìn thấy mọi file được tạo trong lúc duyệt.” | Iterator weakly consistent, không phải snapshot. |
| “Mọi lỗi Filter sẽ chỉ xuất hiện khi mở stream.” | Lỗi có thể xuất hiện trong `hasNext/next`. |
| “`IOException` từ `Filter.accept` sẽ được ném y nguyên.” | Nó được bọc thành `DirectoryIteratorException` trong lúc duyệt. |
| “Pattern sai trả danh sách rỗng.” | Có thể ném `PatternSyntaxException`. |
| “Đóng DirectoryStream là không cần vì chỉ đọc.” | Handle filesystem cần được đóng. |
| “`Files.list` không cần try-with-resources vì là Stream Java.” | `Files.list` trả Stream gắn với tài nguyên cần close. |
| “`Files.isRegularFile` false luôn chứng minh entry chắc là thư mục.” | False còn có thể do loại khác hoặc không đọc được attributes. |
| “`NOFOLLOW_LINKS` giải quyết mọi race bảo mật.” | Nó chỉ điều chỉnh follow-links tại kiểm tra; không thay policy và phòng TOCTOU. |

## 18. Checklist trước khi đưa bộ lọc vào production

1. Thư mục cần lọc có tồn tại/được phép mở không? Nếu không, lỗi sẽ được trình bày thế nào?
2. Cần lọc **một cấp** hay **toàn cây**? Chọn đúng API traversal.
3. Mẫu glob có thực sự áp dụng cho tên file không, hay bạn đang lẫn với absolute path?
4. Pattern có thể nhập từ ngoài không? Có kiểm tra `PatternSyntaxException` và giới hạn thao tác không?
5. Cần file thường hay mọi entry phù hợp tên? Nếu chỉ file, kiểm tra `isRegularFile`.
6. Có cần loại symlink không? Có dùng `NOFOLLOW_LINKS` hoặc quy tắc khác theo threat model không?
7. Điều kiện phần mở rộng có case-sensitive hay case-insensitive theo nghiệp vụ?
8. Có phụ thuộc vào dấu chấm đầu tên hoặc trạng thái hidden của OS không?
9. Có kiểm tra size/metadata không? I/O errors từ Filter được xử lý qua `DirectoryIteratorException` chứ?
10. DirectoryStream/Files.list/walk/find đã được đóng trong try-with-resources chưa?
11. Có vô tình gọi `iterator()` lần thứ hai trên cùng stream không?
12. Thứ tự output cần ổn định không? Nếu cần, đã sort chưa?
13. Bộ lọc có thể thay đổi kết quả khi directory được ghi/xóa đồng thời không? Chính sách nhất quán là gì?
14. Nếu phải xử lý hàng triệu entry, có cần streaming và giới hạn bộ nhớ không?
15. Có phân biệt “không có kết quả” với “lỗi giữa chừng” để tránh bỏ sót dữ liệu?
16. Có test ít nhất các mẫu `*.java`, `*.{java,md}`, `file?.log` và `file[12].log` không?
17. Có test folder trùng phần mở rộng, tên case khác, file bị symlink, file ẩn khi nghiệp vụ yêu cầu?
18. Có test glob lỗi cú pháp và filter ném IOException không?
19. Có test Windows/Linux/macOS nếu sản phẩm hỗ trợ, thay vì giả định filename/glob semantics giống nhau?
20. Có phân biệt code minh họa một phần với class main runnable để người khác có thể chạy lại không?

## 19. Câu hỏi tự kiểm tra

**1.** `Files.newDirectoryStream(dir, "*.java")` có đi vào thư mục con không?  
**Đáp án:** Không. Nó chỉ liệt kê các entry trực tiếp của `dir`.

**2.** Dùng `**/*.java` có tự bật đệ quy cho DirectoryStream không?  
**Đáp án:** Không. Dấu sao kép là cú pháp matching, không thay đổi cách API duyệt thư mục.

**3.** `file?.log` khớp `file10.log` không?  
**Đáp án:** Không; `?` chỉ khớp đúng một ký tự.

**4.** Glob `*.{java,md}` có ý nghĩa gì?  
**Đáp án:** Chọn tên kết thúc `.java` hoặc `.md`.

**5.** Glob `*.java` có thể trả đường dẫn của thư mục `archive.java` không?  
**Đáp án:** Có, nếu tên entry khớp. Muốn chỉ file, thêm `Files.isRegularFile`.

**6.** Dùng `FileSystem.getPathMatcher` có cần tiền tố `glob:` không?  
**Đáp án:** Có, ví dụ `getPathMatcher("glob:*.java")`. Với `Files.newDirectoryStream(dir, "*.java")` không cần tiền tố.

**7.** Vì sao nên dùng `matcher.matches(entry.getFileName())` thay vì đưa entire path khi lọc extension?  
**Đáp án:** Pattern `*.java` mô tả **tên**, còn đường dẫn chứa nhiều thành phần.

**8.** Với file `b.TXT` và filter `toLowerCase(Locale.ROOT).endsWith(".txt")`, extension có được chấp nhận không?  
**Đáp án:** Có, theo logic do ứng dụng định nghĩa.

**9.** `Files.isRegularFile(entry, NOFOLLOW_LINKS)` dùng khi nào?  
**Đáp án:** Khi muốn nhận file thường nhưng không coi symlink tới file là file thường.

**10.** Filter có thể dùng `Files.size(entry)` không?  
**Đáp án:** Có. Nó có thể ném `IOException` và nên được gọi sau điều kiện rẻ khác.

**11.** Khi `Filter.accept` ném `IOException`, lỗi nào xuất hiện trong vòng lặp?  
**Đáp án:** `DirectoryIteratorException` có `IOException` làm cause.

**12.** Glob sai cú pháp như dấu `[` không đóng có thể gây gì?  
**Đáp án:** `PatternSyntaxException`.

**13.** `DirectoryStream` có bảo đảm thứ tự theo tên không?  
**Đáp án:** Không. Thu thập rồi sort nếu cần output ổn định.

**14.** Có thể gọi `iterator()` hai lần trên cùng một DirectoryStream không?  
**Đáp án:** Không; lần thứ hai bị `IllegalStateException`.

**15.** Tạo file mới trong khi đang duyệt có chắc xuất hiện trong kết quả không?  
**Đáp án:** Không. Iterator weakly consistent, không đảm bảo snapshot hay cập nhật tức thời.

**16.** `Files.list(dir)` có tự đi vào thư mục con không?  
**Đáp án:** Không. Nó trả Stream entry trực tiếp và cần được close.

**17.** Muốn tìm toàn cây, dùng gì?  
**Đáp án:** `Files.walk/find` (Java 8+) hoặc `Files.walkFileTree` (Java 7+) tùy yêu cầu lỗi/duyệt.

**18.** Glob Java có mặc định bỏ file ẩn theo dấu chấm đầu tên không?  
**Đáp án:** Không. Dấu chấm đầu tên là ký tự bình thường; trạng thái hidden cần logic riêng.

**19.** Vì sao không nên coi `Files.isRegularFile(entry)==false` luôn là “directory”?  
**Đáp án:** Entry có thể là symlink, loại khác hoặc không đọc được attributes.

**20.** Có thể bảo đảm một lần lọc trả danh sách tuyệt đối nhất quán khi ứng dụng khác đang thay đổi directory không?  
**Đáp án:** Không chỉ bằng DirectoryStream. Cần phối hợp nghiệp vụ hoặc snapshot mạnh hơn nếu yêu cầu.

## 20. Nguồn tài liệu chính thức

- [Oracle Java SE 26 — Files.newDirectoryStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): overload không filter, overload `String glob` và overload `DirectoryStream.Filter`.
- [Oracle Java SE 26 — FileSystem.getPathMatcher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)): cú pháp glob/regex, `*`, `**`, `?`, `{...}` và `[...]`, case-sensitivity tùy implementation.
- [Oracle Java SE 26 — DirectoryStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/DirectoryStream.html): một iterator, weakly consistent, không bảo đảm thứ tự, quản lý đóng stream.
- [Oracle Java SE 26 — DirectoryIteratorException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/DirectoryIteratorException.html): I/O error trong lúc iterator.
- [Oracle Java SE 26 — LinkOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html): kiểm tra thuộc tính không theo symbolic links.
- [Oracle Java SE 26 — Files.isRegularFile, Files.size](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): kiểm tra loại entry và metadata có thể lỗi.
- [Oracle Java SE 26 — Files.list/walk/find](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): các lựa chọn Stream và duyệt cây.
- [Oracle Java SE 26 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): duyệt cây tệp bằng visitor và kiểm soát lỗi.
- [Oracle Java SE 7 — Files](https://docs.oracle.com/javase/7/docs/api/java/nio/file/Files.html): xác nhận `newDirectoryStream`/filter/glob đã tồn tại từ Java 7; dùng làm mốc lịch sử, không thay đặc tả hiện hành.
- [Java Developer — Listing the Content of a Directory](https://dev.java/learn/api/io/java-io/file-system/listing/): hướng dẫn chính thức về DirectoryStream, filtering và glob.
- [Oracle Java SE 26 — PathMatcher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/PathMatcher.html): khớp một Path với pattern theo FileSystem.

**Ghi nhớ:** **Glob** giúp lọc *tên* entry, **`DirectoryStream.Filter<Path>`** giúp lọc theo *nhiều điều kiện*, còn **Files.walk/find/walkFileTree** đảm nhiệm *traversal nhiều cấp*. Với mọi trường hợp, đóng tài nguyên bằng try-with-resources, không dựa vào thứ tự directory stream, xử lý đúng lỗi pattern/I/O và kiểm tra loại file/symlink theo yêu cầu thực tế.