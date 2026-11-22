# `PathMatcher` với glob và regex

## Mục tiêu bài học

Trong Java NIO.2, `java.nio.file.Path` mô tả một đường dẫn, còn `java.nio.file.PathMatcher` trả lời câu hỏi **“đường dẫn này có khớp mẫu đã định nghĩa hay không?”**. `PathMatcher` hỗ trợ hai họ cú pháp quan trọng qua `FileSystem.getPathMatcher(...)`: **`glob:`** (dễ đọc khi chọn tên file) và **`regex:`** (mạnh hơn khi cần biểu thức chính quy).

Sau bài này, bạn có thể:

- Tạo `PathMatcher` bằng `FileSystems.getDefault().getPathMatcher("glob:...")` và `"regex:..."`.
- Hiểu `matches(Path)` so khớp **đối tượng `Path` được đưa vào**, không tự tìm kiếm file trên đĩa.
- Phân biệt `path`, `path.getFileName()`, `root.relativize(path)` và `path.toAbsolutePath()` khi lọc tên hay cả đường dẫn.
- Sử dụng các ký hiệu glob `*`, `**`, `?`, `[]`, `{}` và cách escape phù hợp; phân biệt glob với Java regular expression.
- Biết lý do một mẫu có thể cho kết quả khác trên các filesystem/OS do dấu phân cách, phân biệt hoa thường và quy tắc provider.
- Áp dụng matcher để lọc `Files.list` hoặc `Files.walk`, quản lý stream bằng try-with-resources, xử lý lỗi và bảo mật.
- Viết và chạy các ví dụ Java 17+ có đầu ra xác định.

## 1. `PathMatcher` là gì, và nó không làm gì?

`PathMatcher` là một **functional interface** trong `java.nio.file`:

```java
public interface PathMatcher {
    boolean matches(Path path);
}
```

Đây là **chữ ký minh họa**, không phải file Java độc lập để bạn khai báo lại trong dự án.

`matches(path)` quyết định mẫu có khớp `Path` được truyền hay không. Nó **không**:

- Mở hoặc tạo file, directory.
- Tự gọi `Files.list()` hoặc duyệt cây thư mục.
- Xác minh file thực sự tồn tại hoặc có quyền đọc.
- Kiểm tra MIME type hay định dạng nội dung.
- Bảo đảm tên/đường dẫn đã an toàn để mở, xóa hoặc thực thi.
- Tự chuyển sang khớp `getFileName()` nếu bạn truyền cả đường dẫn.

Sơ đồ logic:

```text
Chuỗi quy tắc                     Đường dẫn ứng viên
"glob:*.java"                     Path.of("src", "App.java")
       │                                   │
       ▼                                   ▼
FileSystem.getPathMatcher(...)     Path được caller chọn
       │                                   │
       └───────── matcher.matches(path) ───┘
                          │
                     true / false
```

Điều có tính quyết định là **`Path` nào được đưa vào matcher**. Với ví dụ trên, mẫu `glob:*.java` được thiết kế để khớp một thành phần tên, còn `Path.of("src", "App.java")` có nhiều thành phần; kết quả thông thường là `false`. Nếu muốn lọc theo tên cuối cùng, đưa `path.getFileName()` vào thay vì toàn bộ `path`.

## 2. Tạo matcher qua `FileSystem`

API cốt lõi:

```java
FileSystem fs = FileSystems.getDefault();

PathMatcher javaNames = fs.getPathMatcher("glob:*.java");
PathMatcher numberedReports =
    fs.getPathMatcher("regex:report-\\d{4}\\.csv");
```

Đây là **đoạn minh họa**, cần import `java.nio.file.FileSystem`, `FileSystems`, `PathMatcher`. Lưu ý: trong **Java source**, `\\d` và `\\.` dùng hai dấu backslash trong literal để tạo ra regex thực tế `\d` và `\.`. `PathMatcher` không trực tiếp là `java.util.regex.Pattern`; matcher được filesystem provider tạo ra theo cú pháp đã chỉ định.

Cú pháp chuỗi:

```text
syntax:pattern
```

- `syntax`: với default provider, có **`glob`** hoặc **`regex`**.
- `pattern`: quy tắc khớp được giải thích theo syntax đã chọn.
- `getPathMatcher(...)` thuộc **một `FileSystem`**, vì đường dẫn và ngữ nghĩa có thể phụ thuộc provider.
- Mẫu không hợp lệ có thể dẫn đến `PatternSyntaxException` (unchecked); syntax không được provider hỗ trợ cũng là lỗi cần xử lý theo hợp đồng.

`FileSystems.getDefault()` là filesystem mặc định của JVM. Với filesystem đặc biệt như ZipFS hoặc provider bên thứ ba, nên tạo matcher từ chính `path.getFileSystem()` hoặc filesystem đang xử lý thay vì mặc nhiên dùng default filesystem.

### Một matcher có thể tái sử dụng

```java
PathMatcher matcher =
    FileSystems.getDefault().getPathMatcher("glob:*.txt");

boolean ok1 = matcher.matches(Path.of("note.txt"));
boolean ok2 = matcher.matches(Path.of("photo.png"));
```

Đây là **đoạn minh họa** với import `java.nio.file.*`. `ok1` là `true`; `ok2` là `false` với tên ASCII trên default filesystem thông thường. Nên tạo matcher **một lần** cho một quy tắc và dùng lại trong vòng lặp thay vì biên dịch mẫu cho từng entry.

## 3. `glob:`: cú pháp thân thiện với tên file

Glob khác regex. Những quy tắc phổ biến của glob trong Java default filesystem:

| Glob | Ý nghĩa | Ví dụ |
|---|---|---|
| `*.java` | Phần tên bất kỳ, kết thúc bằng `.java`; `*` không vượt dấu phân cách thư mục | `Main.java` |
| `file?.txt` | Một ký tự không phải separator tại vị trí `?` | `file1.txt`, không phải `file12.txt` |
| `img[0-9].png` | Một ký tự trong dải ký tự nêu trong `[]` | `img7.png` |
| `report[abc].csv` | Một trong `a`, `b`, `c` | `reporta.csv` |
| `report[!0-9].csv` | Một ký tự không nằm trong dải `0..9` | `reportx.csv` |
| `*.{java,kt}` | Chọn một trong hai nhánh tên phần mở rộng | `Main.java`, `Main.kt` |
| `**` | Khớp zero hoặc nhiều ký tự, **có thể** đi qua separator | Có thể dùng trong mẫu nhiều cấp |
| `\\*` | Escape dấu `*` để coi nó là ký tự tên literal (quy tắc glob) | Tên chứa dấu `*` trên filesystem cho phép |

Cú pháp trên là mô tả glob; khi viết **Java string literal** cần escape thêm dấu `\\`, và khi dùng filesystem khác nhau thì ký tự phân cách, tên hợp lệ và case sensitivity có thể thay đổi. Không tự suy rằng tên có dấu `*` hợp lệ trên mọi hệ điều hành.

### `*` khác `**` như thế nào?

- `*` khớp **không hoặc nhiều** ký tự **trong một thành phần** đường dẫn, không nuốt directory separator.
- `**` khớp **không hoặc nhiều** ký tự **bao gồm cả dấu phân cách**, nên thích hợp để diễn đạt mẫu đường dẫn nhiều cấp.
- `?` khớp **đúng một** ký tự, không phải separator; nó không tương đương với `*`.
- `[]` là **character class** và `{}` là **nhóm lựa chọn** theo glob. Đây không phải `[]`/`{}` trong mọi trường hợp của regex.

Ví dụ ý tưởng:

```text
glob:*.java
  ├─ Main.java        ✓
  ├─ Test.java        ✓
  └─ src/Main.java    ✗  (vì có separator)

glob:**/*.java
  ├─ src/Main.java         ✓
  └─ src/test/Test.java    ✓
```

Lưu ý **rất dễ nhầm**: `glob:**/*.java` không nên được mặc định là khớp cả `Main.java` nằm ngay tại root trên mọi provider, vì mẫu vẫn có đoạn separator trước phần tên cuối. Nếu muốn thống nhất cả file ở root và ở dưới thư mục, một cách rõ ràng là duyệt cây bằng `Files.walk` rồi match `path.getFileName()` với `glob:*.java`. Như thế quy tắc phần mở rộng không phụ thuộc độ sâu của file.

### `{}` trong glob không phải regex quantifier

`glob:*.{java,kt}` chọn `.java` hoặc `.kt`.

Trong regex Java, `{4}` có thể nghĩa là **lặp đúng bốn lần**, nhưng ở glob, dấu ngoặc nhọn là nhóm lựa chọn như `{java,kt}`. Muốn đúng bốn ký tự ở glob, dùng `????` hoặc mẫu cụ thể hơn; muốn bốn chữ số, regex `\\d{4}` sẽ rõ ràng.

Glob có thể dùng `\\` để escape những ký tự có ý nghĩa đặc biệt như `*`, `?`, `[`, `{`. Trong Java source, bạn lại phải escape dấu `\\` của Java string. Khi logic xử lý dấu `\\` trên Windows, cần đặc biệt cẩn thận vì đây còn là đường phân cách hệ thống trong nhiều dạng path; hãy kiểm thử trực tiếp trên hệ điều hành được hỗ trợ.

## 4. `regex:`: sức mạnh của biểu thức chính quy

Với `regex:`, phần mẫu dùng **cú pháp của Java `Pattern`**. Ví dụ:

```java
PathMatcher report =
    FileSystems.getDefault().getPathMatcher(
        "regex:report-\\d{4}\\.csv"
    );
```

Đây là **đoạn minh họa**, với import `java.nio.file.*`. Mẫu chấp nhận `report-2026.csv`, không chấp nhận `report-ABCD.csv`.

Một số thành phần regex thường dùng:

| Regex | Nghĩa |
|---|---|
| `.` | Một ký tự bất kỳ, ngoại trừ một số line terminator theo chế độ mặc định |
| `.*` | Không hoặc nhiều ký tự bất kỳ theo quy tắc dấu `.` |
| `\\.` | Dấu chấm literal trong **biểu thức regex** |
| `\\d` | Một chữ số theo quy tắc Java regex |
| `[0-9]` | Một ký tự ASCII trong dải 0–9 |
| `[A-Za-z]` | Một ký tự thuộc dải chữ cái ASCII nêu ra |
| `(?:csv|tsv)` | Chọn một trong `csv`, `tsv` mà không tạo capturing group |
| `{4}` | Lặp đúng bốn lần phần tử trước |
| `+` | Một hoặc nhiều lần |
| `?` | Không hoặc một lần |
| `^`, `$` | Neo đầu/cuối chuỗi theo semantics Java regex |

**Khác biệt quan trọng:** `PathMatcher.matches(Path)` là **kiểm tra khớp toàn bộ biểu diễn Path**, không phải API tìm substring bất kỳ. Vì vậy không cần tự thêm `.*` vào đầu/cuối chỉ để biến matcher thành một phép tìm tên file bên trong path. Nếu muốn so khớp một phần cụ thể, đưa `path.getFileName()` hay một `Path` tương đối thích hợp vào matcher.

Khi viết biểu thức regex dưới dạng Java `String`, có **hai lớp cú pháp**:

1. Java string literal giải mã các escape của Java: `"\\d"` mới tạo chuỗi hai ký tự `` và `d`.
2. Regex engine nhận chuỗi đó và hiểu `\d` là nhóm chữ số.

Do đó:

| Ý định | Java source literal |
|---|---|
| Regex cho 4 chữ số | `"regex:\\d{4}"` |
| Regex dấu chấm thật | `"regex:\\."` |
| Regex đuôi `.java` | `"regex:.*\\.java"` |
| Regex file `report-2026.csv` | `"regex:report-\\d{4}\\.csv"` |

Đừng nhầm `glob:*.java` với `regex:*.java`: trong regex, dấu `*` không thể đứng đầu một biểu thức như glob wildcard, vì nó là quantifier của phần tử **đứng trước**. Muốn “bất kỳ ký tự rồi `.java`” theo regex, dùng `regex:.*\\.java` trong Java source.

### Glob hay regex?

- Dùng **glob** khi mô tả phần mở rộng, tiền tố, tên đơn giản hoặc một số pattern file dễ đọc.
- Dùng **regex** khi cần nhóm, số lượng lặp, vị trí, quy tắc tên phức tạp, ký tự hợp lệ hoặc định dạng token.
- Đừng chọn regex chỉ vì nó có vẻ mạnh hơn: khi lọc `*.txt` hoặc `*.java`, glob thường dễ đọc, dễ bảo trì.

## 5. Ví dụ 1: phân biệt khớp tên và khớp cả đường dẫn

Lưu **`PathMatcherBasicsDemo.java`**:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.PathMatcher;

public class PathMatcherBasicsDemo {
    public static void main(String[] args) {
        PathMatcher glob = FileSystems.getDefault()
            .getPathMatcher("glob:*.java");
        PathMatcher regex = FileSystems.getDefault()
            .getPathMatcher("regex:.*\\.java");

        Path plain = Path.of("Demo.java");
        Path nested = Path.of("src", "Demo.java");
        Path text = Path.of("Demo.txt");

        System.out.println("glob plain: " + glob.matches(plain));
        System.out.println("glob nested full: " +
            glob.matches(nested));
        System.out.println("glob nested filename: " +
            glob.matches(nested.getFileName()));
        System.out.println("regex filename: " +
            regex.matches(plain.getFileName()));
        System.out.println("glob text: " + glob.matches(text));
    }
}
```

Biên dịch/chạy với Java 17+:

```bash
javac PathMatcherBasicsDemo.java
java PathMatcherBasicsDemo
```

Stdout với default filesystem thông thường:

```text
glob plain: true
glob nested full: false
glob nested filename: true
regex filename: true
glob text: false
```

Giải thích:

1. `glob:*.java` phù hợp với `Path.of("Demo.java")`.
2. `nested` gồm hai thành phần `src` và `Demo.java`, có separator. `*` không bao gồm separator, nên `glob.matches(nested)` là `false`.
3. `nested.getFileName()` chỉ gồm `Demo.java`; matcher lúc này nhận đúng phần tên cần lọc.
4. `regex:.*\\.java` tương đương `.*\.java` ở tầng regex, khớp tên `Demo.java`.
5. Đuôi `.txt` không được chấp nhận.

Ví dụ dùng tên ASCII đơn giản và không phụ thuộc file vật lý tồn tại. Nó thể hiện rằng **PathMatcher không phải filesystem scanner**: cả ba `Path` chỉ là object chứa đường dẫn.

## 6. Ví dụ 2: so sánh glob `?` với regex `\\d{4}`

Dù cả hai có thể kiểm tra “bốn ký tự”, chúng không hoàn toàn giống nhau.

Lưu **`GlobRegexComparisonDemo.java`**:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.PathMatcher;

public class GlobRegexComparisonDemo {
    public static void main(String[] args) {
        PathMatcher glob = FileSystems.getDefault()
            .getPathMatcher("glob:report-????.csv");
        PathMatcher regex = FileSystems.getDefault()
            .getPathMatcher("regex:report-\\d{4}\\.csv");

        String[] names = {
            "report-2026.csv",
            "report-ABCD.csv",
            "report-26.csv",
            "other-2026.csv"
        };

        for (String name : names) {
            Path path = Path.of(name);
            System.out.println(name
                + " | glob=" + glob.matches(path)
                + " | regex=" + regex.matches(path));
        }
    }
}
```

Chạy:

```bash
javac GlobRegexComparisonDemo.java
java GlobRegexComparisonDemo
```

Stdout:

```text
report-2026.csv | glob=true | regex=true
report-ABCD.csv | glob=true | regex=false
report-26.csv | glob=false | regex=false
other-2026.csv | glob=false | regex=false
```

Tại sao `report-ABCD.csv` được glob chấp nhận? Vì `????` chỉ yêu cầu **đúng bốn ký tự không phải separator**, không nhất thiết là số. Regex `\\d{4}` (chuỗi regex sau khi Java decode là `\d{4}`) yêu cầu **bốn chữ số**, nên từ chối bốn chữ cái.

Khi yêu cầu khớp chính xác một grammar đặt tên, nên chọn regex hoặc bổ sung kiểm tra logic thay vì giả định glob wildcard đã kiểm tra định dạng nội dung.

## 7. Khớp phần nào của `Path`?

Cần quyết định rõ ràng **phạm vi pattern** trước khi tạo matcher. Có bốn trường hợp thường gặp:

| Giá trị đưa vào `matches` | Diễn giải | Ví dụ sử dụng |
|---|---|---|
| `path` | Toàn bộ `Path` hiện có, có thể tương đối hoặc tuyệt đối | Khi pattern mô tả cấu trúc đầy đủ của `path` |
| `path.getFileName()` | Thành phần cuối (tên file/dir) | Lọc tất cả `*.java` bất kể độ sâu |
| `root.relativize(path)` | Đường dẫn tương đối **so với root xác định** | Lọc đường dẫn theo vị trí trong cây |
| `path.toAbsolutePath()` | Đường dẫn tuyệt đối theo working directory hiện tại | Match rule thật sự được định nghĩa ở mức đường dẫn tuyệt đối |

Ví dụ:

```java
Path root = Path.of("project");
Path file = root.resolve(Path.of("src", "App.java"));

Path name = file.getFileName();   // App.java
Path relative = root.relativize(file); // src/App.java theo hệ
```

Đây là **đoạn minh họa**; chuỗi hiển thị của `relative` có thể là `src\\App.java` trên Windows. `Path.getFileName()` có thể trả `null` cho một số loại path như root-only; kiểm tra null trước khi gọi matcher trong mã xử lý đường dẫn tùy ý.

**Quan trọng với `relativize`:** Hai `Path` nên cùng filesystem/provider và phải tương thích về tính tương đối/tuyệt đối theo hợp đồng provider; nếu không, có thể ném `IllegalArgumentException`. Hãy chuẩn hóa cách biểu diễn `root` và `path` trước khi `relativize` nếu nguồn đến từ nhiều chỗ.

Không dùng `root.relativize(path)` như cơ chế chống path traversal: tạo đường dẫn tương đối chỉ biến đổi cách biểu diễn; nó không chứng minh `path` an toàn hay vẫn nằm trong root sau khi resolve symbolic link.

### “Khớp tên” và “khớp cấu trúc thư mục” là hai nhiệm vụ khác nhau

- Yêu cầu: “Mọi file `.java` trong cây” → `matcher.matches(path.getFileName())` trong quá trình duyệt cây.
- Yêu cầu: “Chỉ `.java` nằm trong thư mục `src`” → quy tắc trên **relative path** và cấu trúc thư mục; hoặc kết hợp kiểm tra cha với matcher tên.
- Yêu cầu: “Lọc đường dẫn tuyệt đối dưới một root” → xử lý theo `Path`, kiểm tra phạm vi và symlink an toàn riêng; match pattern chỉ là một bước chọn tên.

Khi thiết kế filter, ghi rõ **độ sâu**, **tập root**, **có theo symlink không** và **có phân biệt hoa thường không** để tránh hành vi bất ngờ khi chuyển từ local development sang CI hoặc production.

## 8. Ví dụ 3: `Files.list` và `Files.walk` + `PathMatcher`

`PathMatcher` không tự duyệt thư mục. Muốn lọc file thực tế, cần API liệt kê như:

- `Files.list(dir)`: stream các entry **trực tiếp** trong directory.
- `Files.walk(root)`: stream các đường dẫn theo quá trình duyệt cây **đệ quy**, có thể giới hạn độ sâu.
- `Files.walkFileTree(root, ...)`: visitor để quản lý từng trạng thái và lỗi traversal chi tiết hơn.

Cả `Files.list` và `Files.walk` trả về `Stream<Path>` **cần đóng** bằng try-with-resources để giải phóng tài nguyên hệ thống. Trong quá trình tiêu thụ stream, lỗi I/O có thể phát sinh dưới dạng `UncheckedIOException`. Bộ lọc `matcher.matches(path)` không biến stream thành snapshot bất biến.

Lưu **`PathMatcherDirectoryDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.PathMatcher;
import java.util.List;
import java.util.stream.Stream;

public class PathMatcherDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("pathmatch-");
        Path sub = root.resolve("sub");

        try {
            Files.createDirectory(sub);
            Files.createFile(root.resolve("a.java"));
            Files.createFile(root.resolve("b.java"));
            Files.createFile(root.resolve("readme.md"));
            Files.createFile(sub.resolve("nested.java"));

            PathMatcher matcher = FileSystems.getDefault()
                .getPathMatcher("glob:*.java");

            List<String> direct;
            try (Stream<Path> entries = Files.list(root)) {
                direct = entries
                    .filter(Files::isRegularFile)
                    .filter(p -> matcher.matches(p.getFileName()))
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .toList();
            }

            List<String> recursive;
            try (Stream<Path> entries = Files.walk(root)) {
                recursive = entries
                    .filter(Files::isRegularFile)
                    .filter(p -> matcher.matches(p.getFileName()))
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .toList();
            }

            System.out.println("direct: " + direct);
            System.out.println("recursive: " + recursive);
        } finally {
            Files.deleteIfExists(sub.resolve("nested.java"));
            Files.deleteIfExists(root.resolve("a.java"));
            Files.deleteIfExists(root.resolve("b.java"));
            Files.deleteIfExists(root.resolve("readme.md"));
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy Java 17+:

```bash
javac PathMatcherDirectoryDemo.java
java PathMatcherDirectoryDemo
```

Stdout khi fixture được tạo và liệt kê thành công:

```text
direct: [a.java, b.java]
recursive: [a.java, b.java, nested.java]
```

Phân tích:

1. Chương trình tự tạo một thư mục tạm có hai file `.java` trực tiếp và một file `.java` trong `sub`.
2. `Files.list(root)` chỉ thấy các entry cấp đầu; sau khi lọc theo file thông thường và tên `.java`, nhận `a.java` và `b.java`.
3. `Files.walk(root)` duyệt sâu nên còn có `nested.java`. Việc match **`getFileName()`** giúp cùng một glob `*.java` chấp nhận tên ở mọi độ sâu.
4. `sorted()` làm output có thứ tự xác định; bản thân các API traversal **không cam kết** thứ tự ổn định trên mọi hệ thống.
5. Cả hai Stream đều đóng trong TWR; `finally` dọn fixture.
6. `Files.isRegularFile` dùng chính sách theo symlink của API; nếu yêu cầu không theo symlink, cần lựa chọn `LinkOption.NOFOLLOW_LINKS` và traversal options rõ ràng, không mặc định mọi link được phép.

**Giới hạn:** `Files.walk` duyệt filesystem thật; trong ví dụ chỉ có bốn entry do chương trình tạo. Với cây rất lớn, hạn chế depth, chi phí I/O và chiến lược xử lý lỗi. Mã dọn file tạm trong `finally` cũng có thể ném lỗi; trong sản phẩm nên dùng cơ chế cleanup có chính sách tránh che khuất lỗi chính.

## 9. Phân biệt `PathMatcher` và `java.util.regex.Pattern`

Một regex hoàn toàn có thể được dùng theo hai cách:

**Cách A — `PathMatcher` từ filesystem:**

```java
PathMatcher matcher = FileSystems.getDefault()
    .getPathMatcher("regex:report-\\d{4}\\.csv");

boolean ok = matcher.matches(Path.of("report-2026.csv"));
```

**Cách B — `Pattern` trên chuỗi:**

```java
Pattern pattern = Pattern.compile("report-\\d{4}\\.csv");

boolean ok = pattern.matcher("report-2026.csv").matches();
```

Hai đoạn đều **minh họa**, cần import `java.nio.file.*` hoặc `java.util.regex.Pattern` tương ứng. Trong hai ví dụ tên ASCII đơn giản, `ok == true`.

Khác biệt:

| Vấn đề | `PathMatcher` | `Pattern` |
|---|---|---|
| Đầu vào | `Path` | `CharSequence` (thường là `String`) |
| Lấy qua | `FileSystem.getPathMatcher` | `Pattern.compile` |
| Cú pháp | `glob:`, `regex:` | Java regex |
| Quan hệ filesystem | Matcher gắn với provider | Không gắn với provider |
| Match toàn bộ | `matcher.matches(path)` | `pattern.matcher(s).matches()` |
| Tìm một đoạn nhỏ | Chọn phần Path phù hợp | `Matcher.find()` |
| Ứng dụng | Chính sách khớp path/tên file | Kiểm tra/khai thác pattern text nói chung |

Đừng nhầm `PathMatcher.matches` với `Matcher.find()`. `Matcher.find()` có thể tìm một chuỗi con; `matches()` đòi khớp toàn bộ đầu vào. Trong nhiều chương trình, người dùng nhập một “keyword tìm kiếm” nhưng developer gọi `PathMatcher.matches` với mẫu không có wildcard; kết quả sẽ false dù tên có chứa keyword.

Ví dụ nếu muốn khớp tên bất kỳ chứa `invoice`, mẫu glob là `glob:*invoice*` (trên một tên), không phải `glob:invoice`.

## 10. Hệ điều hành, dấu phân cách và case sensitivity

Một `PathMatcher` do filesystem provider tạo ra có thể **không mang cùng kết quả** trên mọi hệ điều hành nếu pattern phụ thuộc vào:

- **Dấu phân cách thư mục:** hệ Unix thường dùng `/`; Windows thường biểu diễn path bằng `\\`. Java `Path` trừu tượng hóa nhiều thao tác, nhưng viết cứng separator vào glob/regex có thể gây lỗi porting.
- **Phân biệt hoa/thường:** `App.JAVA` có thể được filesystem/provider đối xử khác với `App.java`. Không mặc định cùng policy trên Linux, Windows, macOS và ZipFS.
- **Quy tắc tên hợp lệ:** tên chứa `:`, `*`, `?` hoặc ký tự điều khiển có thể bị cấm hoặc có ý nghĩa khác ở filesystem này so với filesystem khác.
- **Unicode/canonical equivalence:** hai chuỗi nhìn giống nhau có thể gồm các code point khác nhau; không mặc định filesystem/provider chuẩn hóa chuỗi tên theo cùng một cách.
- **Absolute vs relative:** đường dẫn tuyệt đối chứa root, ổ đĩa hoặc các thành phần khác; glob thiết kế cho tên đơn giản không tự khớp toàn bộ dạng đó.

### Một cách làm portable cho việc lọc đuôi

Nếu yêu cầu chỉ là **tên file**, hãy lấy `path.getFileName()` và dùng pattern không chứa separator:

```java
PathMatcher javaName = path.getFileSystem()
    .getPathMatcher("glob:*.java");

Path filename = path.getFileName();
boolean accepted =
    filename != null && javaName.matches(filename);
```

Đây là **đoạn minh họa**, cần `path` khác `null` và import `Path`/`PathMatcher`. Nó tránh hardcode separator trong mẫu, nhưng **không tự tạo cùng chính sách phân biệt hoa thường** trên mọi hệ thống; nếu ứng dụng yêu cầu case-insensitive thực sự giống nhau, phải thiết kế/test policy riêng.

### Regex với đường dẫn nhiều cấp

Nếu muốn regex kiểm tra tên trong directory tree:

1. Quy định root và biến ứng viên thành `root.relativize(path)`.
2. Quy định dạng separator dùng trong regex và cách nó được nhận diện bởi provider.
3. Tránh giả định `regex:src/.+\\.java` luôn portable đối với mọi `Path` trên mọi OS.
4. Nếu chỉ cần kiểm tra một thành phần, tách `relative.getName(index)` hoặc dùng `getFileName()`.
5. Viết integration test trên các nền tảng mục tiêu nếu pattern có cấu trúc nhiều cấp.

Đừng tự động đổi `path.toString().replace('\\', '/')` rồi truyền lại cho `PathMatcher` của một provider mà không xác định kiểu `Path` mới và ngữ nghĩa mong muốn. Nếu yêu cầu một **cú pháp đường dẫn độc lập hệ điều hành** (ví dụ URL/ZIP entry key dùng `/`), cân nhắc tạo một mô hình biểu diễn chuẩn của ứng dụng và dùng `Pattern` trên chuỗi đó, hoặc dùng provider phù hợp.

## 11. Validation, lỗi pattern và dữ liệu không tin cậy

### Mẫu sai có thể làm chương trình lỗi ngay lúc tạo matcher

Ví dụ một regex sai:

```java
String syntaxAndPattern = "regex:[";
PathMatcher bad = FileSystems.getDefault()
    .getPathMatcher(syntaxAndPattern);
```

Đây là **phản ví dụ**, trên provider regex chuẩn, pattern có character class chưa đóng và việc tạo matcher sẽ ném `PatternSyntaxException`. Trong sản phẩm, nếu pattern đến từ cấu hình/người dùng, hãy catch `PatternSyntaxException`, báo lỗi rõ ràng và không lưu pattern lỗi vào bộ lọc đang hoạt động.

Một số syntax không được hỗ trợ hoặc provider không hiểu là lỗi cấu hình. Không tự chuyển bất kỳ string thiếu prefix nào sang regex; luôn xác định rõ `glob:` hay `regex:`.

### Matcher không phải công cụ kiểm tra bảo mật đường dẫn

`matcher.matches(path)` chỉ trả true/false theo mẫu. Nếu đường dẫn được nhập từ người dùng:

- **Path traversal:** đường dẫn `../secret.txt` có thể lọt vào một pipeline nếu chỉ xét `getFileName()` (`secret.txt`) và bỏ qua nơi nó trỏ tới.
- **Symlink:** một đường dẫn nhìn như nằm trong root có thể liên kết sang filesystem khác. `normalize()` chỉ xử lý thành phần cú pháp như `.`/`..`, không tự giải quyết symlink theo tất cả trường hợp.
- **TOCTOU:** đường dẫn/metadata có thể thay đổi giữa lúc match, `Files.isRegularFile` và lúc mở thật.
- **Regex quá phức tạp do người dùng cung cấp:** có thể tiêu tốn CPU bất thường trên đường dẫn dài (regex backtracking); giới hạn độ dài và độ phức tạp pattern.
- **Resource exhaustion:** `Files.walk` trên cây rất lớn, symlink/permission và số entry không giới hạn có thể tiêu tốn tài nguyên.

Phòng tránh phải dựa trên **quy tắc root, quyền truy cập, phương thức mở, file descriptor, validation và chính sách symlink** phù hợp, không chỉ pattern. Nếu xử lý thư mục không tin cậy, có thể cần `SecureDirectoryStream` (nếu provider hỗ trợ) hoặc cơ chế giới hạn truy cập của OS.

### `matches` không cần file tồn tại

```java
PathMatcher p = FileSystems.getDefault()
    .getPathMatcher("glob:*.txt");
boolean matched = p.matches(Path.of("not-created.txt"));
```

Đây là **đoạn minh họa**: `matched` có thể là `true` dù file `not-created.txt` chưa tồn tại. Nếu yêu cầu “file phải tồn tại và là file thông thường”, bạn phải kiểm tra bằng `Files.isRegularFile` hoặc thao tác mở phù hợp trong workflow, đồng thời cân nhắc rủi ro race condition.

## 12. Hiệu năng và cách thiết kế bộ lọc

Matcher thường chỉ xử lý **cách biểu diễn đường dẫn**, không tự truy cập filesystem để đọc nội dung. Tuy nhiên việc liệt kê tree, kiểm tra metadata và đọc file thật có thể tốn nhiều I/O.

Thực hành nên làm:

1. **Tạo matcher một lần** bên ngoài vòng lặp, dùng lại cho nhiều `Path`.
2. **Chọn phạm vi trước**: chỉ tên, đường dẫn tương đối hay toàn bộ path.
3. **Giảm số lần truy vấn metadata**: nếu chỉ lọc theo tên thì không cần gọi `Files.isRegularFile` cho mọi entry trừ khi yêu cầu thực sự là file thông thường.
4. **Giới hạn traversal**: chọn `Files.list` cho một cấp hoặc `Files.walk(root, maxDepth)` khi có độ sâu giới hạn.
5. **Đóng stream**: `Files.list`/`Files.walk` là tài nguyên I/O; dùng try-with-resources.
6. **Xác định thứ tự**: `sorted()` nếu cần output deterministic, nhưng nhớ sort nhiều path cũng tốn bộ nhớ.
7. **Không đưa thao tác ghi/xóa vào predicate match**: filter nên là thao tác kiểm tra; nếu muốn hành động trên file, tách giai đoạn xử lý và bảo đảm quyền/khả năng khôi phục.
8. **Log lỗi có ngữ cảnh**: thiếu permission, directory bị xóa, broken symbolic link và pattern sai có cách xử lý khác nhau.
9. **Kiểm thử trên OS/provider đích**: đặc biệt khi pattern chứa separator hoặc chữ hoa/thường.
10. **Ưu tiên đường dẫn tương đối đã định nghĩa rõ root** khi rule gắn với cấu trúc dự án; tránh viết rule ngầm phụ thuộc working directory của tiến trình.

Nếu chỉ cần pattern đơn giản cố định như `*.java`, một `glob` trên `getFileName()` thường là điểm bắt đầu tốt. Nếu cần kiểm tra “tên dạng `report-YYYY.csv`”, regex rõ ràng hơn. Nếu cần liệt kê và xử lý hàng chục nghìn file, chọn đúng API traversal mới là yếu tố hiệu năng lớn hơn việc chọn glob hay regex.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `PathMatcher` được lấy như thế nào?

**Đáp án:** Từ `FileSystem.getPathMatcher("glob:...")` hoặc `getPathMatcher("regex:...")`, thường bắt đầu bằng `FileSystems.getDefault()`.

**Câu 2.** `glob:*.java` khớp `Path.of("src", "Main.java")` không? Nếu không, làm sao lọc tên?

**Đáp án:** Trên default provider thông thường là không, vì `*` không nuốt separator. Dùng `matcher.matches(path.getFileName())` để khớp `Main.java`.

**Câu 3.** `glob:report-????.csv` có bắt buộc bốn ký tự là số không?

**Đáp án:** Không, `?` là một ký tự không phải separator. Dùng regex `report-\\d{4}\\.csv` nếu muốn bốn chữ số.

**Câu 4.** Trong Java string literal, vì sao `"regex:.*\\.java"` có hai dấu backslash?

**Đáp án:** Một dấu `\\` là escape ở tầng Java string; regex thực tế cần `\.` để khớp dấu chấm literal thay vì wildcard `.`.

**Câu 5.** Gọi `matcher.matches(path)` có tự quét thư mục hoặc kiểm tra `Files.exists(path)` không?

**Đáp án:** Không. Nó chỉ so khớp `Path` được đưa vào. Muốn lọc file đang tồn tại phải dùng API duyệt/lấy thông tin filesystem riêng.

**Câu 6.** Khi dùng `Files.walk(root)` để tìm mọi file `.java` ở mọi độ sâu, có cách nào tránh glob nhiều cấp phụ thuộc separator?

**Đáp án:** Lọc `p -> matcher.matches(p.getFileName())` với `glob:*.java`, sau đó áp dụng yêu cầu về loại file, quyền truy cập và symlink riêng.

**Câu 7.** `Files.list(root)` và `Files.walk(root)` khác nhau thế nào?

**Đáp án:** `Files.list` liệt kê một cấp; `Files.walk` duyệt cây theo cấu hình độ sâu. Cả hai trả `Stream<Path>` phải được đóng.

**Câu 8.** `PathMatcher` có bảo đảm trên Windows và Linux giống nhau hoàn toàn với mẫu chứa dấu separator và chữ hoa không?

**Đáp án:** Không. Matcher gắn với filesystem/provider; cần xét separator, case-sensitivity và cách biểu diễn Path.

**Câu 9.** `glob:*.txt` khớp một `Path` thì có chứng minh file đó an toàn để đọc hoặc thuộc root được phép không?

**Đáp án:** Không. Đó là kiểm tra mẫu tên/đường dẫn, không phải validation chống traversal/symlink, kiểm tra quyền hoặc mở file an toàn.

**Câu 10.** Muốn tìm một substring trong chuỗi chứ không phải match toàn bộ path, nên dùng gì?

**Đáp án:** Có thể dùng `java.util.regex.Pattern` và `Matcher.find()` trên một chuỗi đã xác định, hoặc thiết kế glob có wildcard bao quanh tên theo đúng yêu cầu.

## Tổng kết

- `PathMatcher` được tạo từ `FileSystem.getPathMatcher("glob:...")` hoặc `"regex:..."`.
- `glob` ngắn gọn cho tên file (`*`, `?`, `[]`, `{}`, `**`), còn `regex` phù hợp các quy tắc có cấu trúc/định lượng.
- `matches(Path)` so khớp **đúng đối tượng Path caller truyền**; khi chỉ lọc tên, dùng `getFileName()`.
- Cả glob và regex có thể nhạy với filesystem/provider, separator và case-sensitivity; không giả định hành vi giống nhau trên mọi nền tảng.
- `PathMatcher` không tự duyệt directory, xác minh tồn tại hay giải quyết bảo mật. Kết hợp nó với `Files.list`/`Files.walk`, try-with-resources và các bước validation thích hợp.
- Với Java 17, giữ rõ **phạm vi khớp**, **thứ tự filter**, **phạm vi root** và **hợp đồng filesystem** để tránh các lỗi khó phát hiện.
