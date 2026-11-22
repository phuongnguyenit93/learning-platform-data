# `PathMatcher` trong Java: Khác biệt giữa `glob` và biểu thức chính quy khi duyệt cây tệp

## 1. Mục tiêu: lọc đường dẫn đúng thay vì tự kiểm tra chuỗi

Giả sử một công cụ build cần tìm mọi tệp `.java` trong cây dự án; một công cụ khác chỉ nhận những tên `Main1.java`, `Main12.java` nhưng không nhận `MainA.java`. Ta cần hai khả năng khác nhau:

1. **Duyệt cây tệp** để lấy ra các đối tượng `Path` thực tế.
2. **So khớp đường dẫn** với một mẫu (*pattern*) theo quy tắc đã định.

Từ Java 7, NIO.2 cung cấp `java.nio.file.PathMatcher`, một interface có phương thức:

```java
boolean matches(Path path);
```

`PathMatcher` được tạo từ `FileSystem.getPathMatcher(String syntaxAndPattern)`. Hai cú pháp chuẩn được các `FileSystem` hỗ trợ là:

- **`glob`**: mẫu đơn giản cho tên tệp và cấu trúc đường dẫn, ví dụ `glob:*.java`.
- **`regex`**: biểu thức chính quy theo cú pháp `java.util.regex.Pattern`, ví dụ chuỗi Java `"regex:Main\\d+\\.java"`.

Ví dụ:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.PathMatcher;

PathMatcher javaFile = FileSystems.getDefault()
        .getPathMatcher("glob:*.java");

System.out.println(javaFile.matches(Path.of("Main.java"))); // true
System.out.println(javaFile.matches(Path.of("README.md"))); // false
```

**Đây là đoạn minh họa bên trong phương thức**, chưa phải chương trình độc lập. Ví dụ đầy đủ có lệnh `javac`/`java` và stdout kiểm thử ở mục 10.

**Thông điệp chính:** `PathMatcher` **chỉ kiểm tra một `Path` đã được đưa vào**, không tự mở thư mục, không đi tìm file và không tự đệ quy. Muốn tìm file trong một cây thư mục cần kết hợp với `Files.walk`, `Files.find`, `Files.walkFileTree` hoặc `DirectoryStream` theo yêu cầu.

Bài học tập trung vào cách hiểu **`glob` khác `regex`**, ý nghĩa của **tên tệp so với đường dẫn nhiều thành phần**, và cách áp dụng khi duyệt cây. Đây là các API còn được hỗ trợ trong Java 17+ và hiện nay; `PathMatcher` và `FileSystem.getPathMatcher` đã có từ Java 7.

## 2. Tạo `PathMatcher` bằng `FileSystem.getPathMatcher`

### 2.1. Cú pháp `syntax:pattern`

```java
FileSystem fs = FileSystems.getDefault();

PathMatcher byGlob = fs.getPathMatcher("glob:*.java");
PathMatcher byRegex = fs.getPathMatcher("regex:.*\\.java");
```

Ở ví dụ trên:

- `FileSystem` xác định **filesystem provider** được dùng để diễn giải đường dẫn.
- `getPathMatcher` nhận chuỗi dạng `syntax:pattern`: dấu hai chấm đầu tiên phân tách tên cú pháp và pattern.
- `glob` và `regex` là tên cú pháp chuẩn; tên phần cú pháp được so sánh không phân biệt chữ hoa/chữ thường theo Java API.
- `PathMatcher.matches(path)` trả `true` hoặc `false` cho `Path` được đưa vào.

**Lưu ý:** Java source cần viết `"regex:.*\\.java"` vì ký tự `\` trong regular expression phải được escape trong **string literal Java**. Regex thực tế sau khi Java đọc chuỗi là `.*\.java`.

### 2.2. Lấy matcher từ filesystem của `Path` hiện có

Nếu đang làm việc với các provider khác nhau, cách rõ ràng hơn là:

```java
Path root = /* một đường dẫn có thật do ứng dụng cung cấp */;
PathMatcher matcher = root.getFileSystem()
        .getPathMatcher("glob:*.java");
```

Đây là **mã minh họa**, trong đó `root` phải được ứng dụng cung cấp; comment không phải code tạo sẵn một root. Tạo matcher trên **cùng filesystem** với các `Path` dự kiến kiểm tra giúp tránh ngộ nhận về dấu phân cách, cách so sánh tên và root.

Một `Path` bên trong ZIP filesystem không nhất thiết dùng cùng cách diễn giải với `Path.of(...)` ở filesystem mặc định. Đừng lấy matcher cho filesystem A rồi mặc định nó có ngữ nghĩa hoàn toàn tương đương trên mọi đối tượng path đến từ filesystem B.

### 2.3. Những lỗi khi tạo matcher

Theo tài liệu API:

- Thiếu dạng `syntax:pattern` có thể ném `IllegalArgumentException`.
- Pattern `glob` hoặc `regex` không hợp lệ có thể ném `PatternSyntaxException`.
- Tên syntax không được provider hỗ trợ có thể ném `UnsupportedOperationException`.
- Regex hay glob được parse **khi tạo matcher**, nên nên tạo một lần rồi tái sử dụng thay vì tạo lại cho từng file.

```java
PathMatcher good = fs.getPathMatcher("glob:*.java");

// Không đúng cú pháp regex: dấu * đứng đầu mà không có biểu thức trước nó.
// fs.getPathMatcher("regex:*.java"); // PatternSyntaxException
```

Đoạn này là minh họa, với `fs` đã khai báo. Không nên coi `*.java` là mẫu có thể “đổi tiền tố `glob:` thành `regex:`” mà giữ nguyên ý nghĩa.

## 3. `glob` và `regex` khác nhau về ngữ pháp

### 3.1. Bảng so sánh nhanh

| Ý định | Mẫu `glob` | Mẫu `regex` |
| --- | --- | --- |
| Tên tệp kết thúc bằng `.java` | `*.java` | `.*\.java` |
| Tên bắt đầu bằng `Main` và chỉ có **một** ký tự trước `.java` | `Main?.java` | `Main.\.java` |
| Tên bắt đầu bằng `Main`, sau đó một hoặc nhiều chữ số | Không có `\d+` tương đương trực tiếp trong glob | `Main\d+\.java` |
| Chọn `.java` **hoặc** `.class` | `*.{java,class}` | `.*\.(java\|class)` |
| Chọn `Main1.java` hoặc `Main2.java` | `Main[12].java` | `Main[12]\.java` |
| Chọn một ký tự không thuộc `a` tới `c` | `[!a-c]` | `[^a-c]` |
| Khớp trên cả đường dẫn nhiều cấp | Dùng `**` cho phép vượt ranh giới thư mục | Dùng regex phù hợp biểu diễn đường dẫn, ví dụ `.*\.java` |

**Trong cột regex**, biểu thức được viết ở dạng **regex thuần** để người học thấy rõ ký hiệu. Khi đưa vào Java string literal, phải escape backslash lần nữa (ví dụ `"regex:Main\\d+\\.java"`).

### 3.2. Ba nhầm lẫn cơ bản

**Thứ nhất: `*` có hai ý nghĩa khác nhau.**

- Với `glob`, `*` khớp **0 hoặc nhiều ký tự trong một thành phần tên**, không vượt qua dấu phân cách thư mục.
- Với `regex`, `*` là **quantifier** áp dụng cho biểu thức ngay trước nó: lặp 0 hoặc nhiều lần. Do đó `regex:*.java` là pattern sai cú pháp.

**Thứ hai: `?` có hai ý nghĩa khác nhau.**

- Với `glob`, `?` khớp **đúng một ký tự** trong thành phần tên.
- Với `regex`, `?` thường nghĩa là **0 hoặc 1 lần** xuất hiện của biểu thức trước nó. Muốn đúng một ký tự bất kỳ trong regex, dùng `.`.

**Thứ ba: dấu chấm `.` có hai ý nghĩa khác nhau.**

- Với `glob`, `.` thông thường là một dấu chấm **theo nghĩa ký tự**.
- Với `regex`, `.` khớp một ký tự tùy ý theo quy tắc regex; muốn dấu chấm thật, dùng `\.` trong regex (và `\\.` trong Java string).

Nhầm một trong ba điều này khiến bộ lọc có thể **chọn sai file, bỏ sót file hoặc từ chối khởi tạo matcher**.

## 4. Quy tắc `glob` trong Java: `*`, `**`, `?`, `[]`, `{}`

`FileSystem.getPathMatcher` định nghĩa ngôn ngữ glob tương đối nhỏ và phù hợp đường dẫn. Nó **không phải** cú pháp glob của mọi shell hoặc mọi thư viện. Một số cách mở rộng của Bash, PowerShell, Node.js và các công cụ khác không phải là quy tắc Java glob chuẩn.

### 4.1. `*` — mọi số lượng ký tự trong **một tên**

```java
PathMatcher matcher = fs.getPathMatcher("glob:*.java");

matcher.matches(Path.of("Demo.java"));          // true
matcher.matches(Path.of("ExampleTest.java"));   // true
matcher.matches(Path.of("notes.txt"));          // false
```

Đây là mã minh họa với `fs` đã có. `*` có thể khớp chuỗi rỗng trong một tên, nhưng **không đi qua ranh giới thư mục**.

Vì vậy nếu ta so **cả relative path**:

```java
Path relative = Path.of("src", "Demo.java");

matcher.matches(relative);           // false theo hành vi ví dụ
matcher.matches(relative.getFileName()); // true
```

Đây chính là lý do bộ lọc có vẻ “không tìm thấy `.java` trong cây” dù pattern `*.java` là đúng: **đầu vào cho matcher là cả path nhiều thành phần**, không chỉ filename.

### 4.2. `**` — cho phép vượt qua ranh giới thư mục

`**` khớp 0 hoặc nhiều ký tự **có thể đi qua các thành phần thư mục**. Ví dụ với relative paths:

```java
PathMatcher deep = fs.getPathMatcher("glob:**.java");

deep.matches(Path.of("Demo.java"));                 // true
deep.matches(Path.of("src", "Demo.java"));          // true
deep.matches(Path.of("src", "app", "Util.java"));    // true
```

**Không tùy tiện thay `**.java` bằng `**/*.java` rồi cho rằng hai pattern luôn giống nhau.** Biểu thức có dấu phân cách `/` tường minh có thể không khớp file nằm ngay tại root theo cách bạn kỳ vọng. Để chọn tất cả filename kết thúc bằng `.java` bất kể độ sâu, hai chiến lược rõ nhất là:

1. Duyệt cây rồi kiểm tra **`path.getFileName()`** với `glob:*.java`.
2. Duyệt cây, chuyển sang đường dẫn tương đối và dùng mẫu `glob:**.java` phù hợp provider.

Cách thứ nhất thường dễ portable và dễ giải thích hơn khi chỉ lọc theo **đuôi tên tệp**.

### 4.3. `?` — đúng một ký tự

```java
PathMatcher one = fs.getPathMatcher("glob:Main?.java");

one.matches(Path.of("Main1.java"));  // true
one.matches(Path.of("MainA.java"));  // true
one.matches(Path.of("Main12.java")); // false
```

`?` không đồng nghĩa một chữ số. Nó có thể nhận chữ cái, số hoặc ký tự khác được provider chấp nhận trong một thành phần tên. Nếu cần “một hoặc nhiều chữ số”, dùng regex `\d+` hoặc một quy tắc khác đủ biểu đạt.

### 4.4. `[]` — một ký tự trong tập hoặc khoảng

```text
glob:Main[12].java    → Main1.java hoặc Main2.java
glob:Part[0-9].txt    → một chữ số ở vị trí đó
glob:[abc]*.java      → tên bắt đầu bằng a, b hoặc c
glob:[!a-c]*.java     → ký tự đầu không thuộc a, b, c
```

Trong **glob**, ký hiệu phủ định bên trong bracket expression là `!` sau `[`; trong **regex**, thường là `^`. Bracket expression chỉ chọn **một ký tự**, không phải một chuỗi có độ dài tùy ý.

### 4.5. `{}` — lựa chọn giữa nhiều subpattern

```java
PathMatcher codeFiles = fs.getPathMatcher(
        "glob:*.{java,class}");
```

Mẫu này chọn tên kết thúc bằng `.java` **hoặc** `.class`. Dấu phẩy phân cách các nhánh bên trong braces.

**Không lồng nhóm braces tùy ý:** tài liệu Java glob nói **groups cannot be nested**. Nếu cần cấu trúc điều kiện phức tạp, regex hoặc kết hợp nhiều matcher có thể phù hợp hơn.

### 4.6. Dấu chấm đầu tên: `*.java` có thể chọn `.Hidden.java`

Khác với một số shell nơi glob `*` mặc định bỏ qua tên bắt đầu bằng dấu chấm, **glob của Java xem dấu chấm đầu là ký tự bình thường**.

```java
PathMatcher javaFiles = fs.getPathMatcher("glob:*.java");

System.out.println(
        javaFiles.matches(Path.of(".Hidden.java"))); // true
```

**Đừng dùng glob làm phương thức xác định “file ẩn”**. Thuộc tính hidden phụ thuộc filesystem. Nếu cần lọc file ẩn, hãy xem `Files.isHidden(path)` và xử lý `IOException`, quyền truy cập, quy tắc hệ điều hành. Tên `.Hidden.java` chưa chắc được Windows đánh dấu hidden chỉ vì có dấu chấm đầu.

## 5. Biểu thức chính quy `regex`: khi nào cần sức biểu đạt lớn hơn?

`regex` dùng ngữ pháp của `java.util.regex.Pattern`, phù hợp khi điều kiện liên quan đến chữ số, nhóm, số lần lặp, tiền tố/hậu tố hoặc cấu trúc phức tạp.

### 5.1. Một hoặc nhiều chữ số

```java
PathMatcher numberedJava = fs.getPathMatcher(
        "regex:Main\\d+\\.java");
```

Khi kiểm tra **chỉ filename**:

| Tên | `glob:Main?.java` | `regex:Main\d+\.java` |
| --- | --- | --- |
| `Main1.java` | true | true |
| `Main12.java` | false | true |
| `MainA.java` | true | false |
| `Main.java` | false | false |
| `Main123.java` | false | true |

Giải thích regex `Main\d+\.java`:

- `Main`: bốn ký tự cố định.
- `\d`: một ký tự chữ số theo ngữ nghĩa regex Java.
- `+`: lặp **một hoặc nhiều** lần.
- `\.`: một dấu chấm thật.
- `java`: phần mở rộng cố định.

Trong Java source, viết **`\\d` và `\\.`** để string chuyển đúng xuống regex engine. Nếu viết `"regex:Main\d+\.java"`, Java source **không hợp lệ** vì escape `\d`/`\.` không phải escape hợp lệ trong Java string literal.

### 5.2. Regex có nhóm, hoặc, neo và quantifier

Ví dụ regex thuần:

```text
Main[0-9]+\.java        tên Main với 1+ chữ số ASCII
(Test|Spec).+\.java     tên bắt đầu bằng Test hoặc Spec, có phần sau
[a-zA-Z_]\w*\.java     một quy tắc ví dụ cho tên theo nhóm ký tự
.*\.java               bất kỳ chuỗi biểu diễn path kết thúc .java
```

Đây là **các biểu thức regex thuần**, không phải string literals hoàn chỉnh. Khi dùng `getPathMatcher("regex:...")`, cần escape backslash theo cú pháp chuỗi Java.

Nếu muốn áp regex chỉ lên một filename, hãy dùng `p.getFileName()`. Nếu muốn áp regex lên **đường dẫn tương đối nhiều cấp**, hãy dùng `root.relativize(p)` và viết pattern để xét đúng tên/dấu phân cách của provider.

**Đừng ép regex hiểu nghĩa “đường dẫn” theo mọi OS một cách tự động.** Regex `.*` có thể khớp dấu phân cách thư mục, còn đường dẫn Windows thường có dấu `\`, Unix thường có dấu `/`. Nếu pattern của bạn chứa chính ký tự phân cách, cần xây dựng và kiểm thử theo provider hoặc chọn giải pháp dựa trên các thành phần `Path` thay vì chuỗi path tự chế.

### 5.3. `PathMatcher.matches` không phải `Matcher.find`

`PathMatcher.matches(Path)` hỏi **đường dẫn có khớp pattern hay không**. Với cú pháp regex của default provider, việc so khớp được thực hiện theo **toàn bộ biểu diễn của Path**, không có ý nghĩa “tìm substring bất kỳ” như `java.util.regex.Matcher.find()`.

Ví dụ:

```java
PathMatcher onlyMain =
        fs.getPathMatcher("regex:Main");

onlyMain.matches(Path.of("Main"));      // true
onlyMain.matches(Path.of("Main1.java"));// false
```

Muốn một biểu thức rộng hơn:

```java
PathMatcher hasMain =
        fs.getPathMatcher("regex:.*Main.*");
```

Đừng nhầm regex `.*Main.*` (khớp toàn chuỗi có chứa Main) với `Matcher.find()` (tìm một vùng khớp) dù cả hai có thể cho cùng boolean trong một số tình huống.

### 5.4. Khi glob là lựa chọn tốt hơn regex

Nếu chỉ lọc đuôi file, chọn một tên hoặc vài extension, `glob` thường:

- Ngắn, dễ đọc.
- Giảm nguy cơ phải escape quá nhiều ký tự regex.
- Phù hợp với tư duy file name/path.
- Có khả năng giữ rõ giới hạn **một thành phần tên** qua ký hiệu `*` và `?`.

Nếu cần điều kiện “một hoặc nhiều chữ số”, nhóm phức tạp hoặc số lần lặp, regex có lợi. **Chọn cú pháp thể hiện đúng điều kiện**, không phải cú pháp “mạnh hơn” theo cảm tính.

## 6. Áp matcher lên cái gì: tên file, đường dẫn tương đối hay tuyệt đối?

### 6.1. `path.getFileName()` — chỉ tên mục cuối

Giả sử:

```text
root = /workspace/project
p    = /workspace/project/src/app/Util.java
```

Ta có:

```java
Path name = p.getFileName();      // Util.java
```

Nếu yêu cầu “tìm mọi file có đuôi .java ở bất cứ thư mục nào”, mẫu tên file thường phù hợp:

```java
if (javaMatcher.matches(p.getFileName())) {
    // Đây là một tệp có tên khớp mẫu.
}
```

Ưu điểm là không cần pattern biết file nằm sâu bao nhiêu cấp và không phụ thuộc separator trong tên các thư mục cha.

**Lưu ý:** `getFileName()` có thể trả `null` với một số root path, nên nếu duyệt cây có cả root, cần lọc file hoặc kiểm tra `null` trước khi gọi `matches`. Khi duyệt chỉ file regular, tên cuối thông thường tồn tại.

### 6.2. `root.relativize(p)` — đường dẫn đối với root của tác vụ

```java
Path relative = root.relativize(p);
// src/app/Util.java (hiển thị kiểu Unix)
```

Khi yêu cầu “chỉ lấy tệp trong nhánh `src` hoặc thư mục `test`”, dùng **đường tương đối** có thể giúp pattern có ngữ cảnh cây thư mục.

```java
PathMatcher recursiveJava =
        root.getFileSystem().getPathMatcher("glob:**.java");

if (recursiveJava.matches(root.relativize(p))) {
    // Tệp khớp cả phần đường tương đối.
}
```

Dùng `root.relativize` trên những `Path` thật sự nằm dưới root, cùng filesystem; đừng áp một cách mù quáng cho đường đến từ provider khác.

### 6.3. Toàn bộ absolute path — thường không cần cho bộ lọc extension

Nếu `p` là absolute path như `C:\Users\...\Util.java` hoặc `/home/.../Util.java`, một pattern `glob:*.java` **không khớp** vì path có nhiều thành phần; dấu phân cách và root làm pattern khác hoàn toàn.

Không dùng **absolute path** khi yêu cầu chỉ là tên file hoặc đường tương đối đối với một root. Nó còn khiến test phụ thuộc ổ đĩa, thư mục người dùng hoặc nơi process được chạy.

### 6.4. Đừng đổi `Path` thành string rồi tự nối bằng `/` chỉ để matcher nhận

`PathMatcher` nhận **`Path`** chứ không nhận `String`. Trong ứng dụng hãy giữ:

```java
Path relative = root.relativize(file);
boolean selected = matcher.matches(relative);
```

Nếu cần log/test portable, có thể chuyển dấu phân cách trong **chuỗi hiển thị** sau khi đã kiểm tra. Đừng ép `Path.toString().replace("\\", "/")` làm nền tảng logic cho mọi provider rồi lấy kết quả làm đường dẫn thật; điều này không bảo đảm đúng cho tất cả filesystem và tên tệp.

## 7. Kết hợp với `Files.walk`: duyệt sâu và lọc bằng matcher

`Files.walk(root)` trả về `Stream<Path>` duyệt các mục trong cây dưới `root`. Đây là thao tác **lấy danh sách đường dẫn**, còn matcher thực hiện **lọc những đường dẫn đã được duyệt**.

### 7.1. Mẫu tối thiểu cho file Java ở mọi độ sâu

```java
Path root = Path.of("project");
PathMatcher matcher = root.getFileSystem()
        .getPathMatcher("glob:*.java");

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p ->
            Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
         .filter(p -> matcher.matches(p.getFileName()))
         .forEach(System.out::println);
}
```

Đây là **mã minh họa trong phương thức** có xử lý `IOException`, cần import `java.nio.file` và `java.util.stream.Stream`. `Path.of` được hỗ trợ từ Java 11; toàn bộ bài chạy Java 17+.

Giải thích:

1. `Files.walk(root)` duyệt các entry của cây. Mặc định không theo symbolic link ở mức traversal.
2. `Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)` chỉ lấy **regular file** và không theo symbolic link khi xét thuộc tính mục.
3. `matcher.matches(p.getFileName())` kiểm tra **tên file**, không phải absolute path.
4. `forEach` chỉ thực hiện logic trên các path đã qua lọc.
5. `try-with-resources` đóng `Stream<Path>` ngay sau khi sử dụng để giải phóng tài nguyên mở phục vụ việc duyệt.

**Đặc biệt:** `Files.walk` là stream lười (*lazy*) và có thể giữ các directory handle đang mở. Không bỏ qua `close()` khi dùng để duyệt nhiều thư mục.

### 7.2. `Files.walk` không tự bảo đảm thứ tự

Thứ tự thư mục/file mà stream trả về **không được bảo đảm là thứ tự chữ cái hoặc thứ tự cố định giữa các lần chạy/provider**. Vì vậy:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p ->
            Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
         .sorted()
         .forEach(System.out::println);
}
```

`sorted()` cho một cách sắp xếp theo `Path.compareTo`, vẫn phụ thuộc provider và đường dẫn. Nếu cần một thứ tự **hiển thị được định nghĩa rõ** cho test đa OS, có thể chuyển mỗi đường tương đối thành một khóa hiển thị nhất quán rồi sort theo khóa đó. Chương trình mục 10 áp dụng cách này.

### 7.3. Vì sao không filter file chỉ bằng `p.toString().endsWith(".java")`?

Kiểm tra `endsWith` đủ cho một nhu cầu nhỏ và kiểm soát tốt, nhưng `PathMatcher` giúp:

- Diễn đạt cùng một quy tắc cho nhiều extension hoặc nhóm tên.
- Tách pattern khỏi logic duyệt.
- Dùng `glob:Main?.java` hoặc `regex:Main\\d+\\.java` khi có điều kiện về cấu trúc tên.
- Làm rõ sự khác nhau giữa **một tên file** và **cả đường dẫn**.
- Dễ chuyển pattern từ cấu hình hợp lệ sang một matcher đã được parse/validate.

Điều này không có nghĩa mọi ứng dụng cần regex. Nếu chỉ cần kiểm tra đúng phần mở rộng và case policy được xác định, một phép xử lý tên đơn giản có thể hoàn toàn hợp lý.

### 7.4. Các lỗi I/O trong khi duyệt

`Files.walk(root)` có thể ném `IOException` ngay khi mở traversal; lỗi phát sinh **sau đó trong lúc stream đang được duyệt** có thể xuất hiện như `UncheckedIOException`. Đừng chỉ catch lỗi khi tạo stream rồi giả định không còn lỗi trong pipeline.

Nếu ứng dụng cần chính sách rất chi tiết cho từng file/thư mục không đọc được, dùng `Files.walkFileTree` với các callback `visitFileFailed`, `preVisitDirectory`, `postVisitDirectory` thường rõ hơn.

## 8. Duyệt cây bằng `Files.walkFileTree` và `SimpleFileVisitor`

Khi cần điều khiển độ sâu, bỏ nhánh, xử lý lỗi theo từng thư mục hoặc duyệt lượng file lớn, `Files.walkFileTree` là công cụ thích hợp.

```java
PathMatcher matcher = root.getFileSystem()
        .getPathMatcher("glob:*.java");

Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs)
            throws IOException {

        if (attrs.isRegularFile()
                && matcher.matches(file.getFileName())) {
            System.out.println(file);
        }

        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFileFailed(
            Path file, IOException error)
            throws IOException {
        throw error; // Hoặc báo lỗi và tiếp tục theo chính sách riêng.
    }
});
```

Đây là **mã minh họa**, với `root` và các import của `java.nio.file`, `java.nio.file.attribute.BasicFileAttributes`, `java.io.IOException` được khai báo trong ngữ cảnh.

Tác dụng:

- `visitFile` nhận cả `Path` và `BasicFileAttributes`, nên có thể lọc file regular qua attributes đã đọc.
- `FileVisitResult.CONTINUE` yêu cầu tiếp tục duyệt.
- `SKIP_SUBTREE` trong `preVisitDirectory` dùng khi muốn bỏ qua một thư mục con (ví dụ thư mục generated output hoặc cache).
- `visitFileFailed` xử lý các lỗi truy cập file thay vì bỏ qua âm thầm.

**Đừng nhầm quyền của matcher:** nó quyết định **entry nào khớp**; không tự cấm visitor đi vào thư mục không khớp. Muốn tăng hiệu năng bằng cách bỏ cây con, phải viết logic ở callback duyệt cây.

### 8.1. Cấu hình tối đa độ sâu

`Files.walk(root, maxDepth)` và overload `Files.walkFileTree` có tham số độ sâu giúp giới hạn phạm vi traversal.

Ví dụ:

```java
try (Stream<Path> paths = Files.walk(root, 2)) {
    // Chỉ duyệt đến tối đa hai cấp từ root.
}
```

Giới hạn độ sâu khác với pattern `*`/`**`: **traversal depth** quyết định Java có đi tới một thư mục hay không; **glob/regex** quyết định có chọn entry đã đi tới hay không.

Một pattern `glob:**.java` không khiến `Files.walk(root, 0)` tự truy cập mọi thư mục.

## 9. `Files.newDirectoryStream` khi chỉ cần một thư mục

Không phải nhu cầu nào cũng cần đệ quy. Nếu chỉ đọc **các entry trực tiếp** trong thư mục `dir`:

```java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, "*.java")) {

    for (Path file : entries) {
        System.out.println(file);
    }
}
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException`, cần import `java.nio.file.DirectoryStream` và `Files`.

Cách này dùng glob filter của `DirectoryStream`, nhưng **không duyệt tự động các thư mục con**. Nếu `dir` chứa `src/app/Util.java` nằm trong nhánh con, lời gọi chỉ mở `dir` sẽ không tự tìm ra nó.

**Điểm giống/khác với `PathMatcher`:**

- Cùng họ cú pháp glob theo contract API.
- `newDirectoryStream(dir, glob)` kết hợp liệt kê một thư mục với lọc tên những entry trực tiếp.
- `PathMatcher` nhận `Path` và chỉ trả boolean; kết hợp với traversal tự chọn.
- `DirectoryStream` cũng là tài nguyên cần đóng.
- Khi duyệt có lỗi, iterator có thể ném `DirectoryIteratorException` bọc nguyên nhân I/O; cần chính sách lỗi phù hợp.

Chọn `DirectoryStream` cho danh sách trực tiếp, `Files.walk` cho pipeline ngắn duyệt sâu, `walkFileTree` khi cần kiểm soát sâu/branch/error.

## 10. Chương trình Java 17+ đầy đủ: kiểm chứng `glob` và `regex` khi duyệt cây

Chương trình tạo một **thư mục tạm riêng**, sinh các file ví dụ, rồi dùng `Files.walk` lấy danh sách file. Nó so khớp cùng danh sách theo hai cú pháp và hai loại đầu vào:

- `glob:*.java` áp lên **`getFileName()`**.
- `regex:Main\\d+\\.java` áp lên **`getFileName()`**.
- `glob:Main?.java` áp lên **`getFileName()`**.
- `glob:*.java` áp lên **relative path nhiều thành phần**.
- `glob:**.java` và `regex:.*\\.java` áp lên relative path.
- Một tên bắt đầu bằng dấu chấm và một tên **không tồn tại thật**, để chứng minh matcher không phụ thuộc shell hay I/O.

Chương trình sắp xếp đường dẫn **trước khi in**, chuẩn hóa dấu phân cách chỉ để **hiển thị**, và dùng `walkFileTree` dọn sạch đúng thư mục tạm vừa tạo.

Tạo tệp **`PathMatcherGlobRegexDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.stream.*;

public final class PathMatcherGlobRegexDemo {

    static String display(Path path) {
        return path.toString().replace('\\', '/');
    }

    static List<Path> collectFiles(Path root) throws IOException {
        try (Stream<Path> walk = Files.walk(root)) {
            return walk.filter(p ->
                        Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
                    .sorted(Comparator.comparing(
                            p -> display(root.relativize(p))))
                    .toList();
        }
    }

    static String select(
            Path root,
            List<Path> files,
            PathMatcher matcher,
            boolean nameOnly) {

        return files.stream()
                .filter(p -> matcher.matches(
                        nameOnly
                                ? p.getFileName()
                                : root.relativize(p)))
                .map(p -> display(root.relativize(p)))
                .collect(Collectors.joining(", "));
    }

    static void check(boolean value, String detail) {
        if (!value) throw new AssertionError(detail);
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error)
                    throws IOException {
                if (error != null) throw error;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("matcher-demo-");

        try {
            Path src = Files.createDirectories(
                    root.resolve("src"));

            Path app = Files.createDirectories(
                    src.resolve("app"));

            for (String name : List.of(
                    "Main1.java",
                    "Main12.java",
                    "MainA.java",
                    ".Hidden.java")) {

                Files.writeString(
                        src.resolve(name),
                        "class Demo {}",
                        StandardCharsets.UTF_8);
            }

            Files.writeString(
                    app.resolve("Util.java"),
                    "class Util {}",
                    StandardCharsets.UTF_8);

            Files.writeString(
                    root.resolve("README.md"),
                    "Read me",
                    StandardCharsets.UTF_8);

            List<Path> paths = collectFiles(root);
            FileSystem fs = root.getFileSystem();

            PathMatcher glob = fs.getPathMatcher("glob:*.java");
            PathMatcher regex = fs.getPathMatcher(
                    "regex:Main\\d+\\.java");
            PathMatcher oneCharacter = fs.getPathMatcher(
                    "glob:Main?.java");
            PathMatcher doubleStar = fs.getPathMatcher(
                    "glob:**.java");
            PathMatcher regexRelative = fs.getPathMatcher(
                    "regex:.*\\.java");

            Path example = src.resolve("Main1.java");
            Path nested = root.relativize(
                    app.resolve("Util.java"));

            String g = select(root, paths, glob, true);
            String r = select(root, paths, regex, true);
            String q = select(
                    root, paths, oneCharacter, true);

            System.out.println(
                    "files=" + paths.stream()
                            .map(p -> display(root.relativize(p)))
                            .collect(Collectors.joining(", ")));

            System.out.println("glob.names=" + g);
            System.out.println("regex.numeric=" + r);
            System.out.println("glob.oneChar=" + q);

            System.out.println("glob.relative="
                    + glob.matches(root.relativize(example)));

            System.out.println("glob.fileName="
                    + glob.matches(example.getFileName()));

            System.out.println("glob.doubleStar="
                    + doubleStar.matches(nested));

            System.out.println("regex.relative="
                    + regexRelative.matches(nested));

            System.out.println("glob.dotFile="
                    + glob.matches(Path.of(".Hidden.java")));

            System.out.println("regex.fullMatch="
                    + fs.getPathMatcher("regex:Main")
                            .matches(Path.of("Main1.java")));

            System.out.println("missingStillMatches="
                    + glob.matches(Path.of("Ghost.java")));

            check(g.equals(
                    "src/.Hidden.java, src/Main1.java, "
                    + "src/Main12.java, src/MainA.java, "
                    + "src/app/Util.java"), "glob");

            check(r.equals(
                    "src/Main1.java, src/Main12.java"), "regex");

            check(q.equals(
                    "src/Main1.java, src/MainA.java"),
                    "single-char");

            check(!glob.matches(root.relativize(example))
                    && glob.matches(example.getFileName()),
                    "file-name selection");

            check(doubleStar.matches(nested)
                    && regexRelative.matches(nested),
                    "path selection");

            System.out.println("checks=PASS");
        } finally {
            deleteTree(root);
        }
    }
}
```

Lệnh chạy với **JDK 17+**:

```bash
javac -encoding UTF-8 PathMatcherGlobRegexDemo.java
java PathMatcherGlobRegexDemo
```

**Stdout chính xác từ lần chạy kiểm thử trên default filesystem:**

```text
files=README.md, src/.Hidden.java, src/Main1.java, src/Main12.java, src/MainA.java, src/app/Util.java
glob.names=src/.Hidden.java, src/Main1.java, src/Main12.java, src/MainA.java, src/app/Util.java
regex.numeric=src/Main1.java, src/Main12.java
glob.oneChar=src/Main1.java, src/MainA.java
glob.relative=false
glob.fileName=true
glob.doubleStar=true
regex.relative=true
glob.dotFile=true
regex.fullMatch=false
missingStillMatches=true
checks=PASS
```

### 10.1. Giải thích kết quả theo từng nhóm

**Nhóm danh sách file:**

- `files=...` được sắp xếp theo khóa hiển thị dùng đường tương đối đã đổi dấu `\` thành `/`. Không dựa vào thứ tự duyệt vốn không được bảo đảm.
- `glob.names=...` chọn đủ các tệp `.java` ở nhiều thư mục khác nhau vì matcher chạy trên **`getFileName()`**.
- `regex.numeric=...` chỉ lấy `Main1.java` và `Main12.java`; `MainA.java` bị loại vì không có chữ số sau `Main`.
- `glob.oneChar=...` lấy `Main1.java` và `MainA.java`; `Main12.java` bị loại vì có hai ký tự sau `Main`.

**Nhóm phạm vi đường dẫn:**

- `glob.relative=false` nhưng `glob.fileName=true`: cùng một tệp có thể khớp hoặc không khớp tùy ta đưa **cả đường tương đối** hay chỉ **tên cuối** vào matcher.
- `glob.doubleStar=true`: `**` đi được qua ranh giới giữa `src`, `app` và `Util.java`.
- `regex.relative=true`: regex `.*\.java` có đủ phần để bao trọn relative path đa cấp.
- `glob.dotFile=true`: glob Java không tự loại tên bắt đầu dấu chấm.
- `regex.fullMatch=false`: `regex:Main` không khớp toàn bộ tên `Main1.java`.
- `missingStillMatches=true`: `PathMatcher` so mẫu với **Path expression**, không gọi `Files.exists` trước khi trả boolean.
- `checks=PASS`: các điều kiện quan trọng đã được kiểm tra. Nếu sai, code ném `AssertionError`.

### 10.2. Vì sao không dùng path tạm tuyệt đối khi in?

`Files.createTempDirectory` có thể tạo đường dẫn khác nhau trên từng máy. Chương trình chỉ in `root.relativize(path)` và giá trị boolean, nên stdout không phụ thuộc một tên random cụ thể.

**Giới hạn của độ portable:** Java API không quy định mọi provider có cùng chính sách case sensitivity hoặc cách diễn giải mọi root/separator. Chương trình tránh các so khớp phân biệt hoa/thường có thể thay đổi; khi triển khai trên provider đặc biệt vẫn cần integration test thực tế.

### 10.3. Ví dụ an toàn để thực hành

Chương trình chỉ tạo/xóa đúng cây tạm mới do nó sở hữu. **Không mang `deleteTree` áp trực tiếp lên thư mục dự án hoặc thư mục do người dùng cung cấp**: method xóa đệ quy là thao tác phá hủy dữ liệu; ở đây nó chỉ phục vụ cleanup của demo.

## 11. Cú pháp pattern, filesystem và khác biệt nền tảng

### 11.1. Case sensitivity không được Java bảo đảm chung

Một câu hỏi phổ biến: `glob:*.JAVA` có khớp `Main.java` không?

**Không có câu trả lời `true`/`false` phổ quát cho mọi filesystem/provider**. Tài liệu `getPathMatcher` nói chi tiết so khớp, bao gồm **có phân biệt chữ hoa/thường hay không**, là *implementation-dependent*.

Vì vậy:

- Không viết unit test bắt buộc `*.java` phải khớp `Main.JAVA` trên mọi OS.
- Nếu nghiệp vụ cần chính sách case-insensitive **độc lập hệ điều hành**, hãy thiết kế rõ quy tắc trên **tên tệp**, chẳng hạn so với tên đã biến đổi theo `Locale.ROOT` cho một tập ký tự/đuôi cố định phù hợp; với regex, có thể xây dựng `Pattern` có flags rõ ràng rồi áp vào tên tệp theo contract.
- Đừng tự `toLowerCase()` toàn bộ path rồi dùng nó để truy cập filesystem; case-folding có thể làm mất nghĩa tên file trên filesystem phân biệt hoa/thường.

### 11.2. Dấu phân cách và root

Mẫu glob có dấu `/` trong đường path **không được tự động diễn giải như path trên Windows** theo mọi tình huống. Tài liệu quy định một số chi tiết match separator và root là implementation-dependent.

Ví dụ dạng đường dẫn:

```text
UNIX:    src/app/Util.java
Windows: src\app\Util.java
```

Muốn chọn các tệp có cùng **tên cuối**, dùng `getFileName()` rồi glob/regex trên tên để giảm phụ thuộc separator. Muốn chọn theo **cấu trúc cây**, hãy xây matcher trên filesystem phù hợp, dùng `root.relativize(p)` và test trên những OS/provider được hỗ trợ.

### 11.3. Java `glob` không phải Shell glob

Không mặc định:

- Bash có các mở rộng như extglob hoặc globstar theo cấu hình shell và cách shell mở rộng pattern trước khi gọi chương trình.
- PowerShell hoặc một thư viện glob bên thứ ba hỗ trợ cùng cú pháp/escaping như Java.
- File bắt đầu dấu chấm bị Java `glob:*` loại khỏi kết quả như một số shell.
- Mọi biểu thức `[a-z]`/`[!...]` được xử lý theo cùng chính sách Unicode/case trên tất cả provider.

`FileSystem.getPathMatcher` có **đặc tả glob riêng của Java**, phải đọc đúng thay vì sao chép pattern của shell rồi mặc định đúng.

### 11.4. Regex trong `PathMatcher` cũng là một pattern trên `Path`

Cú pháp `regex` có nguồn từ `java.util.regex.Pattern`, nhưng đối tượng kiểm tra vẫn là `Path` và cách biểu diễn của provider. Khi làm việc với một tên file `getFileName()`, regex được áp cho **tên đó**. Khi làm việc với path nhiều cấp, regex phải bao phủ **cả chuỗi biểu diễn** của path theo provider.

Nếu code cần logic không phụ thuộc `Path` (ví dụ so nội dung các dòng trong file), dùng trực tiếp `Pattern`/`Matcher` trên `String`; không biến `PathMatcher` thành công cụ regex cho mọi loại văn bản.

## 12. Symbolic link, lỗi truy cập và hiệu năng của traversal

### 12.1. Mặc định `Files.walk` không theo symbolic link

Khi gọi `Files.walk(root)` mà không có `FileVisitOption.FOLLOW_LINKS`, traversal **mặc định không đi theo symbolic links** để mở các thư mục mà link trỏ đến.

Trong ví dụ, bước lọc còn dùng:

```java
Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)
```

để tránh việc kiểm tra thuộc tính *regular file* theo link tại lúc lọc. Điều này giúp các quyết định trong demo rõ hơn.

**Không nên bật `FOLLOW_LINKS` chỉ để “không bỏ sót file”** mà không xem mục đích: symlink có thể trỏ sang ngoài root hoặc tạo vòng lặp. Khi follow links, traversal cần xử lý loop/error và chính sách giới hạn root, ownership.

### 12.2. Pattern chỉ lọc, không cắt giảm traversal tự động

Giả sử pattern là `glob:*.java`. Nếu có 100.000 file và thư mục không liên quan, `Files.walk(root)` vẫn cần duyệt các mục cho đến khi pipeline xử lý hoặc dừng. Matcher không biến `walk` thành “chỉ đọc những tên khớp pattern” ở tầng filesystem.

Khi muốn bỏ hẳn nhánh `build` hoặc `node_modules`, visitor có thể dùng `SKIP_SUBTREE` ở `preVisitDirectory`. Cẩn thận lựa chọn điều kiện và xử lý trường hợp tên thư mục có cùng tên ở các vị trí khác nhau.

### 12.3. Khả năng phát sinh lỗi trong lúc stream đang chạy

Nếu một thư mục bị xóa hoặc mất quyền trong khi duyệt, `Files.walk` có thể gặp lỗi khi tiêu thụ stream. Tùy thời điểm, lỗi I/O được đưa ra qua `IOException` hoặc `UncheckedIOException`.

Nếu cần:

- Tiếp tục khi một thư mục không đọc được.
- Ghi log kèm file bị lỗi.
- Dừng tại một độ sâu nhất định.
- Ngăn tiếp cận một nhánh có tên cụ thể.
- Kiểm soát việc theo symbolic links.

…hãy ưu tiên `Files.walkFileTree` với callback thích hợp. Không viết `catch(Exception ignore)` quanh toàn bộ traversal rồi trả kết quả như thể danh sách file đầy đủ.

### 12.4. Hiệu năng chọn pattern

- **Tạo matcher một lần** cho một lượt quét, không gọi `getPathMatcher` trên từng file.
- Nếu chỉ cần extension đơn giản, `glob:*.java` trên tên cuối thường dễ đọc và đủ nhanh.
- Regex phức tạp có thể tốn chi phí CPU, nhất là mẫu có backtracking xấu. Nếu pattern đến từ người dùng, cần kiểm soát độ dài/độ phức tạp và thời gian xử lý theo mô hình tin cậy.
- Với cây lớn, không nhất thiết thu toàn bộ `List<Path>` như demo; có thể lọc stream hoặc xử lý theo visitor để giảm bộ nhớ.
- Sắp xếp mọi file để đầu ra ổn định có thể tăng bộ nhớ/CPU. Chỉ làm khi cần thứ tự.
- Giới hạn root, độ sâu, số file và quyền truy cập nếu hệ thống xử lý dữ liệu không tin cậy.

## 13. An toàn: `PathMatcher` không phải bộ kiểm tra quyền truy cập

Một pattern `glob:*.java` trả `true` cho một `Path` phù hợp cú pháp nhưng **không kiểm tra file đó có thuộc thư mục được phép**, không xác nhận nó tồn tại và không xác minh nội dung an toàn.

Ví dụ:

```java
PathMatcher matcher = FileSystems.getDefault()
        .getPathMatcher("glob:*.java");

boolean syntaxMatch =
        matcher.matches(Path.of("Secret.java"));
```

`syntaxMatch` có thể `true` dù đường dẫn đó không tồn tại. Matcher không thực hiện authorization.

Nếu ứng dụng cho người dùng tải file đã lọc, cần tách biệt:

1. **Validation** đối với input và các giới hạn định dạng.
2. **Authorization**: người gọi có được phép truy cập đường dẫn/tệp thật không?
3. **Traversal containment**: cây bắt đầu ở root nào, có theo symlink không, có nguy cơ path traversal không?
4. **Pattern matching**: file nào *trong tập được phép* đáp ứng mẫu?
5. **I/O**: mở/đọc tệp với quyền và chế độ truy cập an toàn.
6. **Failure handling**: báo lỗi nếu quét không đầy đủ hoặc file đã đổi trong thời gian quét.

Đừng tạo một matcher từ pattern do người dùng cung cấp rồi suy ra “khớp glob nghĩa là file an toàn”. Với dự án nhiều người dùng, chỉ duyệt trong root được phân quyền, không tự cấp quyền theo extension.

### 13.1. Cẩn thận nếu pattern được nhận từ người dùng

`getPathMatcher` có thể ném lỗi khi pattern sai; regex có thể khiến quá trình matching chậm nếu biểu thức quá phức tạp. Nên kiểm tra cú pháp trước khi bắt đầu traversal, đặt giới hạn độ dài/độ sâu/số file theo nghiệp vụ, và trả thông báo lỗi rõ thay vì tự thay syntax không được công bố.

Một mẫu `regex:.*` có thể khớp gần như mọi path; điều đó không tự cho phép mở mọi tệp trong filesystem.

## 14. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Dùng `getPathMatcher("*.java")` | Thiếu tiền tố `syntax:` | `getPathMatcher("glob:*.java")` |
| Đổi `glob:*.java` thành `regex:*.java` | `*` regex là quantifier, không phải wildcard đứng độc lập | `regex:.*\\.java` dưới dạng Java string |
| Tưởng `glob:*` đi qua thư mục | `*` chỉ match trong một name component | Dùng `**` hoặc match `getFileName()` |
| Tưởng `glob:Main?.java` yêu cầu một chữ số | `?` là một ký tự bất kỳ | Dùng regex `Main\\d+\\.java` |
| Đưa absolute path vào `glob:*.java` | Root và separator làm string path không thể khớp một tên | Dùng `p.getFileName()` |
| Áp glob cho chuỗi file path tự replace separator | Bỏ ngữ nghĩa provider của `Path` | Dùng `PathMatcher.matches(Path)` |
| Tưởng `matches` tìm substring | Matcher áp pattern với biểu diễn Path | Viết pattern bao trọn đường dẫn/tên cần match |
| Nhầm `[!a-z]` với phủ định regex | Glob dùng `!`, regex dùng `^` | Dùng đúng cú pháp tương ứng |
| Tưởng `*.java` tự loại file bắt đầu dấu chấm | Java glob xem leading dot bình thường | Lọc `Files.isHidden` nếu nghiệp vụ yêu cầu |
| Tưởng mọi filesystem case-insensitive | Case policy implementation-dependent | Test từng provider, quy định case riêng |
| Tưởng `PathMatcher` tự đọc cây | Nó chỉ trả boolean cho một Path | Kết hợp `Files.walk`/`walkFileTree` |
| Quên đóng stream từ `Files.walk` | Có thể giữ tài nguyên duyệt thư mục | `try-with-resources` |
| Tưởng glob filter giảm phạm vi file system được duyệt | Pattern chỉ lọc các mục đã được đi qua | Giới hạn root/depth và bỏ subtree ở visitor |
| Chỉ dùng `Files.walk` nhưng bỏ lỗi I/O | Danh sách có thể không đầy đủ | Xử lý `IOException`/`UncheckedIOException` |
| Bật `FOLLOW_LINKS` không kiểm soát | Có thể đi ngoài root hoặc gặp vòng lặp | Xác định symlink policy |
| Nhầm extension match với quyền mở file | Pattern không kiểm tra authorization | Phân quyền và mở file an toàn riêng |
| Hard-code path temp tuyệt đối trong stdout test | Phụ thuộc OS, tên random | Dùng `root.relativize(p)` và sort |
| Dùng matcher của default provider cho path ZIP rồi giả định đồng nhất | Provider có thể khác rule | Lấy matcher từ `path.getFileSystem()` |

## 15. Checklist trước khi dùng `PathMatcher` thực tế

- [ ] Chọn rõ **`glob`** hay **`regex`** theo điều kiện thực sự.
- [ ] Cấu trúc mẫu là `syntax:pattern` đúng của provider.
- [ ] Không nhầm `*`/`?` giữa glob và regex.
- [ ] Đã xét `**` khi muốn match qua nhiều directory components.
- [ ] Đã xác định cần match **filename** hay **relative path**.
- [ ] Đã dùng `path.getFileName()` khi chỉ lọc tên file/extension.
- [ ] Nếu lọc theo cây, dùng `root.relativize(path)` và path thuộc cùng filesystem.
- [ ] Đã xác định chính sách case sensitivity theo OS/provider.
- [ ] Đã hiểu cách xử lý file bắt đầu dấu chấm, hidden attribute và symbolic link.
- [ ] Đã chuẩn bị `Files.walk`/`walkFileTree`/`DirectoryStream` phù hợp phạm vi.
- [ ] Nếu dùng `Files.walk`, đã đóng stream.
- [ ] Với tree lớn, giới hạn độ sâu, quota hoặc skip các subtree không cần.
- [ ] Có xử lý pattern invalid và lỗi I/O phát sinh khi traversal.
- [ ] Có test cho tên có một/nhiều chữ số, extension, nested path, hidden dot và file không tồn tại.
- [ ] Không dùng pattern matching thay cho authorization, containment hoặc validation dữ liệu.
- [ ] Không sử dụng chuỗi absolute OS-specific khi mục đích là test portable.

## 16. Câu hỏi ôn tập

**Câu 1.** `PathMatcher` có tự liệt kê file trong thư mục không?  
**Đáp án:** Không. Nó chỉ kiểm tra `matches(Path)`; phải kết hợp với `Files.walk` hoặc API duyệt phù hợp.

**Câu 2.** `glob:*.java` khác `regex:*.java` như thế nào?  
**Đáp án:** `glob:*.java` hợp lệ và chọn tên kết thúc bằng `.java`. `regex:*.java` sai regex vì `*` không có biểu thức đứng trước.

**Câu 3.** Muốn chọn `Main1.java`, `Main12.java` nhưng không chọn `MainA.java`, dùng gì?  
**Đáp án:** Regex `Main\d+\.java`, viết trong Java string là `"regex:Main\\d+\\.java"`, rồi match với `path.getFileName()`.

**Câu 4.** `glob:Main?.java` có chọn `Main12.java` không?  
**Đáp án:** Không, `?` chỉ tương ứng một ký tự; tên `Main12.java` có hai ký tự `1`, `2` giữa Main và .java.

**Câu 5.** Vì sao `glob:*.java` không chọn một path tương đối `src/app/Util.java` khi match trực tiếp?  
**Đáp án:** Vì `*` không vượt qua dấu phân cách thư mục. Match với `getFileName()` hoặc chọn mẫu `**` thích hợp.

**Câu 6.** `glob:**.java` khác `glob:*.java` ở điểm nào?  
**Đáp án:** `**` có thể match qua nhiều thư mục, `*` chỉ trong một thành phần tên.

**Câu 7.** Có nên giả định `glob:*.java` bỏ qua `.Hidden.java` như shell không?  
**Đáp án:** Không. Java glob xem leading dot là ký tự bình thường; muốn xét hidden dùng quy tắc riêng.

**Câu 8.** Regex muốn match dấu chấm thật viết `.` hay `\.`?  
**Đáp án:** Viết `\.` ở mức regex; trong Java string literal là `"\\."`.

**Câu 9.** `matches(Path)` trả `true` có chứng minh file tồn tại hoặc được phép truy cập không?  
**Đáp án:** Không. Matcher là kiểm tra pattern, không thực hiện I/O hoặc authorization.

**Câu 10.** `Files.walk` có bảo đảm duyệt theo thứ tự tên tăng dần không?  
**Đáp án:** Không. Nếu thứ tự quan trọng, cần sort theo quy tắc đã chọn trước khi xuất kết quả.

**Câu 11.** Khi nào nên dùng `Files.walkFileTree` thay `Files.walk`?  
**Đáp án:** Khi cần skip subtree, quản lý lỗi truy cập từng entry, kiểm soát độ sâu hoặc symlink policy một cách rõ ràng.

**Câu 12.** Nếu `regex:Main` kiểm tra `Main1.java` mà trả false, có lỗi không?  
**Đáp án:** Không. `PathMatcher.matches` xét sự khớp của toàn bộ biểu diễn path, không thực hiện tìm substring như `Matcher.find()`.

## 17. Kết luận và tài liệu Oracle hiện hành

**Ghi nhớ bốn lớp trách nhiệm:**

1. **`FileSystem`** quyết định cách diễn giải path và tạo matcher.
2. **`PathMatcher`** kiểm tra một `Path` theo glob hoặc regex; nó không tìm file.
3. **`Files.walk`/`walkFileTree`** duyệt thư mục thật, có vấn đề I/O, symlink và tài nguyên.
4. **Ứng dụng** quyết định dùng filename hay relative path, xử lý lỗi, quyền truy cập và tính portable.

Chọn **glob** cho pattern tên đơn giản, **regex** cho điều kiện cần ngữ pháp regular expression; luôn phân biệt `*`, `**`, `?` và `.` giữa hai cú pháp. Trong bộ lọc extension chạy qua nhiều thư mục, giải pháp dễ bảo trì thường là:

```java
PathMatcher matcher = root.getFileSystem()
        .getPathMatcher("glob:*.java");

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p ->
            Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
         .filter(p -> matcher.matches(p.getFileName()))
         .forEach(System.out::println);
}
```

Đoạn code kết luận là minh họa trong một phương thức có `root` đã khai báo và các import phù hợp.

### Tài liệu chính thức còn hiệu lực

- [Java SE 17 — `FileSystem.getPathMatcher(String)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)): đặc tả `glob`, `regex`, `*`, `**`, `?`, `{}`, `[]`, leading dot và tính implementation-dependent.
- [Java SE 17 — `PathMatcher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/PathMatcher.html): contract `matches(Path)`.
- [Java SE 17 — `Files.walk`, `Files.find`, `Files.walkFileTree` và `Files.newDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): traversal, stream resource, options, error handling.
- [Java SE 17 — `Path.getFileName`, `relativize` và `getFileSystem`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): chọn phần Path muốn so.
- [Java SE 17 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): ngữ pháp regex và escaping.
- [Dev.java — Listing the Content of a Directory](https://dev.java/learn/api/io/java-io/file-system/listing/): ví dụ glob khi liệt kê file.