# Đường dẫn Windows, Unix, dấu phân cách và tính phân biệt hoa thường trong Java `Path`

`java.nio.file.Path` biểu diễn **đường dẫn theo một hệ thống tệp (`FileSystem`) cụ thể**. Một chuỗi nhìn giống đường dẫn hợp lệ trên Windows có thể mang ý nghĩa hoàn toàn khác trên Unix/Linux, và ngược lại. Để viết Java I/O chạy được trên nhiều nền tảng, cần phân biệt:

1. **Dấu phân cách thư mục** (`/` hoặc `\`) với **dấu phân cách các phần tử trong danh sách đường dẫn** (`:` hoặc `;`).
2. **Quy tắc gốc và đường dẫn tuyệt đối**: `/home/...` trên Unix, `C:\...` và `\\server\share\...` trên Windows, cùng các dạng Windows *drive-relative*.
3. **Tính phân biệt hoa–thường**: phụ thuộc filesystem, volume, thư mục và đôi khi cấu hình provider; không thể quyết định chỉ từ `System.getProperty("os.name")`.
4. **Chuỗi đường dẫn so với đối tượng tệp thực tế**: `Path.equals()` khác về mục đích với `Files.isSameFile()`, còn `normalize()` không truy cập hệ thống tệp.
5. **Tính an toàn khi ghép đường dẫn**: xử lý `..`, symbolic link, tên file từ đầu vào bên ngoài và điều kiện thay đổi giữa lúc kiểm tra/sử dụng.

Quy tắc nền tảng: **hãy ghép các thành phần bằng `Path.of(...)`/`resolve(...)` thay vì tự nối chuỗi dấu `/` hoặc `\`**. Khi cần làm việc với một đường dẫn của hệ điều hành *khác* máy đang chạy Java, đừng giao nguyên chuỗi ấy cho default filesystem rồi giả định nó sẽ được phân tích theo cú pháp của hệ điều hành nguồn.

## 1. `Path` thuộc về `FileSystem`, không chỉ là `String`

Một đường dẫn có thể được biểu diễn bằng:

```java
Path path = Path.of("data", "reports", "summary.txt");
```

Đây là đoạn minh họa, cần `import java.nio.file.Path;`. `Path.of(...)` tạo đường dẫn trên **default filesystem** của JVM. Nó không tự tạo file, không cần file tồn tại, và không mở bất kỳ luồng dữ liệu nào. Dạng chuỗi trả về khi gọi `path.toString()` do filesystem/provider xác định.

Các phần của một `Path` thường gồm:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Root | `/` trên Unix; `C:\` với một ổ đĩa Windows; `\\server\share\` của UNC | Điểm gốc theo quy tắc filesystem |
| Name elements | `data`, `reports`, `summary.txt` | Các thành phần đường dẫn |
| Parent | `data/reports` (viết theo kiểu Unix) | Phần đường dẫn trước tên cuối |
| File name | `summary.txt` | Thành phần cuối cùng, không phải tên file đã được kiểm tra tồn tại |
| Absolute path | `/home/ana/data/...` hoặc `C:\Users\Ana\data\...` | Đã có root theo filesystem tương ứng |
| Relative path | `data/reports/summary.txt` | Được diễn giải tương đối với ngữ cảnh làm việc |

`getRoot()`, `getParent()`, `getFileName()`, `getNameCount()`, `isAbsolute()` là các phép phân tích đường dẫn, **không phải phép truy vấn xem file tồn tại**. Ví dụ `getFileName()` có thể trả `null` với một số đường dẫn chỉ chứa root. `Path` còn có thể được tạo bởi filesystem khác default, ví dụ hệ thống tệp ZIP do provider hỗ trợ; vì vậy không nên mặc định rằng mọi `Path` đều mang quy tắc tên của đĩa cục bộ.

### Ví dụ 1 — ghép đường dẫn theo từng thành phần, không phụ thuộc dấu phân cách

```java
// PathComponentsDemo.java
import java.io.File;
import java.nio.file.Path;

public class PathComponentsDemo {
    public static void main(String[] args) {
        Path path = Path.of("data", "logs", "app.log");
        Path messy = Path.of("data", ".", "cache", "..", "report.txt");
        Path cleaned = messy.normalize();

        System.out.println("relative=" + !path.isAbsolute());
        System.out.println("nameCount=" + path.getNameCount());
        System.out.println("fileName=" + path.getFileName());
        System.out.println("parentName=" + path.getParent().getFileName());
        System.out.println("joinedCorrectly=" + path.toString().equals(
                "data" + File.separator + "logs"
                        + File.separator + "app.log"));
        System.out.println("cleanedNames=" + cleaned.getNameCount());
        System.out.println("cleanedFileName=" + cleaned.getFileName());
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac PathComponentsDemo.java
java PathComponentsDemo
```

Đầu ra trên default filesystem Windows hoặc Unix thông dụng:

```text
relative=true
nameCount=3
fileName=app.log
parentName=logs
joinedCorrectly=true
cleanedNames=2
cleanedFileName=report.txt
```

Trên Windows, `path.toString()` thường dùng `data\logs\app.log`; trên Unix, thường dùng `data/logs/app.log`. Bài kiểm tra `joinedCorrectly` dựa trên `File.separator` của chính nền tảng hiện tại nên vẫn cho cùng kết quả. `normalize()` rút gọn `.` và cặp thành phần `cache/..` theo **ngữ nghĩa đường dẫn thuần túy**, không kiểm tra `data` hay `cache` có tồn tại.

### Relative path không tự dựa vào thư mục chứa mã nguồn

`Path.of("data", "file.txt")` là tương đối. Khi một API cần giải quyết nó thành đường dẫn tuyệt đối, ngữ cảnh thường là **working directory của tiến trình Java**. Không giả định Java tự dùng thư mục đặt file `.java`, thư mục IDE project, hay vị trí `.class`. Các môi trường IDE, CI, container và dịch vụ hệ thống có thể khởi chạy ứng dụng với working directory khác nhau.

Dùng `toAbsolutePath()` nếu cần xem đường dẫn tuyệt đối theo default filesystem; nếu muốn xác định rõ gốc dữ liệu của ứng dụng, hãy truyền một `Path base` đã chọn, rồi gọi `base.resolve(...)`.

## 2. Dấu phân cách thư mục của Windows và Unix

### Unix/Linux và nhiều hệ thống POSIX

Đường dẫn Unix thông dụng dùng dấu **`/`**:

```text
/etc/hosts
/home/ana/projects/report.txt
var/log/app.log
```

- `/` ở đầu thường chỉ **root**.
- `var/log/app.log` không có `/` ở đầu là đường dẫn **tương đối**.
- Dấu gạch chéo ngược `\` **không phải** dấu phân cách thư mục của filesystem Unix thông thường; nó có thể là ký tự thuộc tên file (dù shell thường dùng backslash làm ký tự escape khi nhập lệnh).
- Tên file trên Unix thường không chứa `/` và ký tự NUL. Những quy tắc khác (Unicode, độ dài tên, normalization) còn tùy hệ thống tệp/provider.

### Windows

Windows thường hiển thị dấu **`\`**:

```text
C:\Users\Ana\report.txt
D:\data\log.txt
\\server\share\reports\summary.txt
```

- `C:\Users\Ana\report.txt` có drive `C:` cùng root `\`, là dạng **absolute** theo cú pháp Windows.
- `\\server\share\reports\summary.txt` là **UNC path** (đường dẫn mạng) gồm server, share và những thành phần phía sau.
- Trên default Windows filesystem của Java, dấu `/` thường cũng được chấp nhận như dấu phân cách đầu vào: `C:/Users/Ana/report.txt`. Tuy nhiên không suy rộng khả năng này cho mọi API Windows, tên dạng mở rộng hoặc provider khác.
- Windows có các dạng đường dẫn không có nghĩa tương đương nhau: `C:notes.txt` và `C:\notes.txt` **không giống nhau**.

### Ba dạng đường dẫn Windows dễ bị lẫn

| Dạng | Cách hiểu trên Windows |
| --- | --- |
| `C:\data\file.txt` | Absolute với root trên ổ `C:` |
| `C:data\file.txt` | **Drive-relative**: tương đối với thư mục hiện tại gắn với ổ `C:`, không phải mặc nhiên `C:\data\file.txt` |
| `\data\file.txt` | Root-relative trên **ổ hiện hành** theo ngữ cảnh Windows; không chỉ định ổ độc lập |
| `data\file.txt` | Relative thuần túy |
| `\\server\share\file.txt` | UNC, gốc được xác định bởi server/share |

Đừng xử lý đường dẫn `C:folder` bằng cách kiểm tra nó “bắt đầu bằng `C:`” rồi kết luận đã tuyệt đối. Muốn biết absolute theo provider hiện tại, dùng `path.isAbsolute()`. Lưu ý: nếu Java chạy trên Linux thì default provider **không phân tích `C:` thành drive Windows**, nên `Path.of("C:\\data\\file.txt").isAbsolute()` không thể thay cho phép kiểm tra cú pháp Windows ở hệ thống khác.

## 3. Hai loại dấu phân cách rất khác nhau

`java.io.File` cung cấp hai nhóm hằng số:

| Hằng số | Mục đích | Giá trị phổ biến trên Unix | Giá trị phổ biến trên Windows |
| --- | --- | --- | --- |
| `File.separator` | Phân cách **thư mục** trong một đường dẫn | `/` | `\` |
| `File.separatorChar` | Phiên bản `char` của `separator` | `/` | `\` |
| `File.pathSeparator` | Phân cách **nhiều đường dẫn** trong danh sách, như classpath | `:` | `;` |
| `File.pathSeparatorChar` | Phiên bản `char` của `pathSeparator` | `:` | `;` |

Ví dụ:

```text
Unix PATH:    /usr/local/bin:/usr/bin:/bin
Windows PATH: C:\Windows\System32;C:\Tools
```

Không được dùng `File.pathSeparator` để ghép hai thư mục. Nó dùng cho **danh sách nhiều mục đường dẫn**. Ngược lại, không được dùng `File.separator` để nối các phần tử classpath. Các giá trị trên là **phổ biến trên các nền tảng**, không phải một lời hứa rằng mọi provider ảo dùng đúng quy tắc của default filesystem.

API đáng ưu tiên khi xây dựng một path:

```java
Path file = Path.of("documents", "2026", "report.txt");
// Thay cho "documents/" + "2026/" + "report.txt".
```

Với classpath do launcher Java xử lý, cấu trúc phân cách danh sách do nền tảng quy định. Hạn chế tự thao tác classpath như một chuỗi nếu đã có API cho mục đích đó.

### Ví dụ 2 — quan sát dấu phân cách và chuỗi đường dẫn

```java
// PathSeparatorsDemo.java
import java.io.File;
import java.nio.file.FileSystems;
import java.nio.file.Path;

public class PathSeparatorsDemo {
    public static void main(String[] args) {
        Path path = Path.of("src", "main", "App.java");

        System.out.println("directorySeparator=" + File.separator);
        System.out.println("pathListSeparator=" + File.pathSeparator);
        System.out.println("defaultFsSeparator="
                + FileSystems.getDefault().getSeparator());
        System.out.println("constructed=" + path);
        System.out.println("nameCount=" + path.getNameCount());
    }
}
```

```bash
javac PathSeparatorsDemo.java
java PathSeparatorsDemo
```

Đầu ra ví dụ **trên Unix/Linux**:

```text
directorySeparator=/
pathListSeparator=:
defaultFsSeparator=/
constructed=src/main/App.java
nameCount=3
```

Đầu ra ví dụ **trên Windows**:

```text
directorySeparator=\
pathListSeparator=;
defaultFsSeparator=\
constructed=src\main\App.java
nameCount=3
```

Đây là ví dụ minh họa hai môi trường điển hình. Cần đọc giá trị từ máy thật khi chạy; không nên tự suy từ `os.name` rồi hard-code logic. `FileSystems.getDefault()` liên quan default filesystem; một `Path` của provider khác có thể có quy tắc riêng, kiểm tra bằng `path.getFileSystem().getSeparator()`.

## 4. Dấu `\` trong Java source code cũng là ký tự escape

Một bẫy thường gặp: **cú pháp Java string literal** khác cú pháp filesystem.

Ví dụ Java đúng khi muốn tạo các chuỗi chứa dấu `\` thực:

```java
String windowsAbsolute = "C:\\Users\\Ana\\report.txt";
String windowsUnc = "\\\\server\\share\\report.txt";
String unixAbsolute = "/home/ana/report.txt";
```

Đây là các **đoạn minh họa**, cần đặt trong một lớp/phương thức Java nếu muốn biên dịch. Trong một Java string literal:

- `\\` ở **source code** biểu diễn **một** dấu backslash trong chuỗi runtime.
- `\n` là newline, `\t` là tab, `\r` là carriage return; nếu viết `"C:\new\test.txt"` có thể vô tình chèn ký tự điều khiển thật vào chuỗi thay vì các đoạn thư mục `new` và `test`.
- Chuỗi `"C:\Users\Ana\report.txt"` không escape đúng `\U`, `\A` và có thể **không biên dịch**.

**Phân biệt ba lớp khác nhau:** Chuỗi mà Java biên dịch tạo ra, cách filesystem provider diễn giải các ký tự ấy, và cách một shell (PowerShell/bash) diễn giải tham số dòng lệnh. Một backslash có thể là escape ở lớp này, nhưng lại chỉ là ký tự thông thường ở lớp khác.

### Trên Unix, backslash không tự biến thành directory separator

Nếu code Java chạy trên Linux/Unix:

```java
Path foreign = Path.of("C:\\Users\\Ana\\report.txt");
```

Đây là **đoạn minh họa** có import `Path`. Provider Unix mặc định không hiểu chuỗi trên thành đường dẫn `C:` và các thư mục `Users`, `Ana`. Nó có thể coi phần lớn chuỗi thành **một tên tương đối chứa dấu backslash**.

Nếu ứng dụng phải xử lý *văn bản đường dẫn Windows* khi chạy trên Unix (ví dụ đọc một file manifest từ máy Windows), bạn cần mô hình/logic phân tích cú pháp nguồn được xác định rõ. Không thể giả sử `Path.of(rawWindowsText)` trên Unix làm nhiệm vụ đó. Nếu muốn thao tác file thực trên **máy hiện tại**, cách bền vững hơn là nhận các **thành phần đường dẫn logic** và ghép bằng `Path.of(base, segments...)` theo provider hiện tại.

Ngược lại, một đường dẫn Unix `/var/log/...` có ý nghĩa với filesystem Unix; chạy nó qua Windows default provider không tự tạo ra Linux root `/var`.

## 5. Có nên tự gọi `replace("\\", "/")` không?

Không dùng phép thay thế này như một “công cụ chuyển đổi đường dẫn đa nền tảng” tổng quát.

- Trên Unix, `\` có thể là **ký tự tên file hợp lệ**, nên thay bằng `/` có thể đổi tên file thành nhiều thư mục.
- Trên Windows, một dấu backslash có thể thuộc phần UNC/root hoặc cú pháp mở rộng; thay đổi tùy tiện có thể làm sai ngữ nghĩa trong một API cụ thể.
- Một file path có thể xuất hiện bên trong **URI**, **URL**, **JSON**, **shell command** hoặc regex. Mỗi tầng có bộ quy tắc escape riêng; không thể dùng `replace()` ở mọi tầng.
- Các filesystem ảo như ZIP và provider tùy biến có thể có cấu trúc khác default filesystem.

Nếu nhận một *tên đường dẫn logic do ứng dụng quy định*, hãy định nghĩa input gồm các phần độc lập, ví dụ `["users", "ana", "report.txt"]`, rồi ghép. Nếu nhận một chuỗi đường dẫn **từ hệ thống khác**, cần parser/metadata nói rõ nó đến từ hệ thống nào, chứ không thể đoán từ một dấu.

### Tránh `String.split(File.separator)`

`String.split()` nhận **regex**, không nhận dấu phân cách literal. Trên Windows, `File.separator` thường là `\`, vốn là escape character trong regex; dùng thẳng `text.split(File.separator)` có thể gây `PatternSyntaxException`.

Với văn bản có delimiter được kiểm soát, `Pattern.quote(delimiter)` có thể giải quyết phần **escape regex**. Nhưng nó không giải quyết root của đường dẫn, UNC, chuỗi có nhiều dấu phân cách, hoặc sự khác nhau của filesystem:

```java
// Đoạn minh họa cho một chuỗi dữ liệu được biết trước, không
// thay cho parser đường dẫn thật.
String[] tokens = text.split(
        java.util.regex.Pattern.quote(File.separator), -1);
```

Khi mục tiêu là thao tác đường dẫn thật của provider hiện tại, dùng `Path`:

```java
Path parent = path.getParent();
Path leaf = path.getFileName();
```

`Path` có khả năng phân tích các thành phần theo quy tắc filesystem tốt hơn việc tự tách chuỗi theo delimiter.

## 6. Phân biệt hoa–thường thuộc về filesystem, không chỉ hệ điều hành

Dễ gặp hai kiểu:

- **Case-sensitive:** `README.md` và `readme.md` có thể là **hai file khác nhau**.
- **Case-insensitive, case-preserving:** khi người dùng tạo `README.md`, filesystem có thể lưu cách viết ấy nhưng tra cứu bằng `readme.md` vẫn trỏ tới cùng tệp.

Ví dụ theo thực tế **thường gặp**, không phải định luật:

| Hệ thống | Hành vi phổ biến | Điều cần thận trọng |
| --- | --- | --- |
| Linux + ext4 cấu hình thông thường | Case-sensitive | Có filesystem/ thư mục được cấu hình khác, ví dụ cơ chế casefold |
| Windows + NTFS cấu hình thông thường | Thường case-insensitive, giữ nguyên hoa–thường | Windows/NTFS có trường hợp điều chỉnh hành vi theo thư mục hoặc cấu hình; không suy mọi volume giống nhau |
| macOS + APFS | Có thể case-insensitive hoặc case-sensitive tùy volume | Không suy từ `os.name` rằng luôn là một kiểu |
| Network filesystem, archive, ZIP, virtual providers | Do server, provider và cấu hình quyết định | Không mặc định cùng quy tắc với máy chạy chương trình |

Điều này ảnh hưởng tới tên resource, cấu hình build, đường dẫn trong Git repository, bộ nhớ cache theo pathname, so khớp tên file và logic bảo mật. Một dự án tạo cả `config.json` lẫn `Config.json` có thể hoạt động trên filesystem phân biệt hoa–thường nhưng gây xung đột khi triển khai sang filesystem không phân biệt.

### Đừng tự dùng `equalsIgnoreCase()` để nhận diện cùng một file

So sánh hai chuỗi bằng `equalsIgnoreCase()` không mô phỏng chính xác mọi quy tắc ánh xạ tên file của provider. Các filesystem còn có thể áp dụng những quy tắc Unicode normalization/case folding hoặc namespace đặc biệt. Mặt khác, hai đường dẫn khác chuỗi vẫn có thể trỏ tới một đối tượng thật do symbolic link, hard link hoặc cùng một tài nguyên có nhiều tên.

Có ba câu hỏi khác nhau:

1. **Hai chuỗi có giống nhau?** `text1.equals(text2)` trả lời theo ký tự Java.
2. **Hai đối tượng `Path` có bằng nhau theo logic provider?** `path1.equals(path2)` trả lời theo hợp đồng `Path`/provider; thường không truy cập filesystem và không phải phép thử file identity.
3. **Hai đường dẫn hiện trỏ đến cùng file?** `Files.isSameFile(path1, path2)` kiểm tra thực thể file qua provider và có thể ném `IOException`.

Ngay cả khi `Path.equals(...)` trả `true`, đừng coi đó là biện pháp ủy quyền truy cập hoặc bảo đảm file đã tồn tại. Hai `Path` bằng nhau không giải quyết mọi vấn đề symbolic link, thay đổi filesystem hoặc truy cập.

### Ví dụ 3 — quan sát môi trường chạy thay vì giả định case sensitivity

```java
// PathCaseDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathCaseDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("path-case-");
        Path original = directory.resolve("Report.txt");
        Path alternate = directory.resolve("report.txt");
        Path dotted = directory.resolve(".").resolve("Report.txt");

        try {
            Files.writeString(original, "data", StandardCharsets.UTF_8);

            System.out.println("originalExists=" + Files.exists(original));
            System.out.println("sameThroughDot="
                    + Files.isSameFile(original, dotted));

            boolean alternateExists = Files.exists(alternate);
            System.out.println("alternateExists=" + alternateExists);

            if (alternateExists) {
                System.out.println("alternateSameFile="
                        + Files.isSameFile(original, alternate));
            } else {
                System.out.println("alternateSameFile=not-checked");
            }
        } finally {
            Files.deleteIfExists(original);
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy Java 17+:

```bash
javac PathCaseDemo.java
java PathCaseDemo
```

Hai dòng đầu khi các thao tác tạo tệp thành công:

```text
originalExists=true
sameThroughDot=true
```

Các dòng `alternateExists` và `alternateSameFile` **phụ thuộc filesystem**. Trên filesystem phân biệt hoa–thường thông thường, có thể thấy:

```text
alternateExists=false
alternateSameFile=not-checked
```

Trên filesystem không phân biệt hoa–thường thông thường, có thể thấy:

```text
alternateExists=true
alternateSameFile=true
```

Những kết quả trên là **trường hợp minh họa**, không phải stdout cố định cho mọi Windows/macOS/Linux. Bài test tạo **một file duy nhất** rồi hỏi về hai cách viết tên; không cố tạo đồng thời hai tên vốn có thể trùng nhau trên hệ thống không phân biệt hoa–thường.

`Files.isSameFile()` làm việc với các đối tượng đang tồn tại và có thể báo `IOException` nếu file biến mất hoặc không truy vấn được. Nó cung cấp thông tin về identity tại thời điểm kiểm tra, chứ không khóa file để bảo đảm identity không thay đổi về sau.

## 7. Các thao tác `Path`: `resolve`, `normalize`, `toAbsolutePath`, `toRealPath`

### `resolve(...)`

```java
Path base = Path.of("data");
Path output = base.resolve("reports").resolve("summary.txt");
```

Đây là đoạn minh họa: `output` là đường dẫn ghép theo provider hiện tại. **Nếu đối số `resolve` là absolute**, nhiều trường hợp kết quả sẽ trở thành chính đường dẫn absolute ấy thay vì tiếp tục nằm trong `base`; hợp đồng cụ thể với rooted/drive-relative path phải xem theo provider. Không bao giờ dùng `base.resolve(userProvidedPath)` rồi tự khẳng định kết quả luôn ở dưới base.

### `normalize()`

`normalize()` xóa các thành phần `.` và cặp `name/..` có thể giản lược **theo cú pháp**, không truy cập filesystem. Nó không mở/kiểm tra symbolic link, không xác định file có tồn tại.

```text
data/logs/../report.txt
  -> sau normalize(): data/report.txt
```

Trong một đường dẫn có symbolic link, bỏ `name/..` theo cú pháp có thể **khác** với việc đi qua filesystem thật. Vì vậy `normalize()` không phải phép kiểm tra bảo mật hoàn chỉnh hay phép tìm “đích thực” của link.

### `toAbsolutePath()`

Lấy đường dẫn tuyệt đối theo ngữ cảnh filesystem hiện tại. Nó không mặc nhiên xác định target, không mở file và không đảm bảo tồn tại.

### `toRealPath(...)`

Thường yêu cầu đường dẫn thực sự tồn tại và có thể truy cập; phương thức có thể ném `IOException`, có xử lý thành phần `.`/`..` và symbolic link theo tùy chọn. Nếu dùng `LinkOption.NOFOLLOW_LINKS`, ngữ nghĩa với link thay đổi theo hợp đồng. `toRealPath()` có ích khi cần biết vị trí thực tế được provider cung cấp, **nhưng không khóa trạng thái đó trong suốt các thao tác về sau**.

| Phương thức | Có truy cập filesystem? | Có thể xác nhận target tồn tại? | Ghi nhớ |
| --- | --- | --- | --- |
| `normalize()` | Không | Không | Biến đổi cú pháp, không giải symbolic link |
| `toAbsolutePath()` | Không dùng như phép kiểm tra tồn tại | Không | Bổ sung ngữ cảnh root/working directory |
| `toRealPath(...)` | Có | Thông thường cần target tồn tại để thành công | Có thể ném IOException; tùy chọn link quan trọng |
| `Files.exists(path)` | Có kiểm tra trạng thái | Trả boolean khi provider xác định được | `false` không luôn chứng minh chắc chắn không tồn tại |
| `Files.isSameFile(a, b)` | Có thể phải truy vấn danh tính file | Kiểm tra identity, có thể ném IOException | Không thay cho chính sách quyền và chống race |

## 8. `startsWith()` và dấu phân cách: kiểm tra ranh giới thành phần

Một lỗi thường thấy khi xét đường dẫn nằm dưới root:

```java
String candidate = "/srv/app-data/file.txt";
boolean inside = candidate.startsWith("/srv/app");
```

Đây là **đoạn minh họa logic sai**: so sánh chuỗi có thể cho `true` dù `/srv/app-data` không phải con của `/srv/app`.

`Path.startsWith(Path)` so theo **thành phần đường dẫn của provider**, thay vì tiền tố ký tự mù quáng. Với các đường dẫn cùng loại, cùng filesystem, nó tránh lỗi ranh giới tên kiểu `app`/`app-data`. Tuy nhiên bước này **chỉ kiểm tra quan hệ đường dẫn theo ngữ nghĩa `Path`**, không bảo đảm an ninh trước symbolic link, junction và race.

### Ví dụ 4 — kiểm tra quan hệ *lexical* một cách tường minh

```java
// PathLexicalBoundaryDemo.java
import java.nio.file.Path;

public class PathLexicalBoundaryDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "allowed")
                .toAbsolutePath().normalize();

        Path inside = base.resolve("docs")
                .resolve("..").resolve("readme.txt").normalize();

        Path outside = base.resolve("..")
                .resolve("allowed-backup").resolve("readme.txt").normalize();

        System.out.println("insideLexically=" + inside.startsWith(base));
        System.out.println("outsideLexically=" + outside.startsWith(base));
    }
}
```

Chạy:

```bash
javac PathLexicalBoundaryDemo.java
java PathLexicalBoundaryDemo
```

Đầu ra với default Windows/Unix filesystem thông dụng:

```text
insideLexically=true
outsideLexically=false
```

Đây **không phải** một kiểm tra an toàn cho đường dẫn không tin cậy trong môi trường có symbolic link hoặc đối thủ thay đổi filesystem. Nó chỉ chứng minh `Path.startsWith` quan sát **ranh giới thành phần** đúng hơn `String.startsWith`.

Nếu ứng dụng phải giới hạn truy cập trong một thư mục:

- Quyết định chính sách có cho phép symbolic link/junction hay không.
- Xác định root đáng tin cậy và tránh dùng tên file từ người dùng để tạo absolute path ngoài phạm vi.
- Không xem `normalize().startsWith(root)` là phép xác thực đủ trong môi trường có cạnh tranh.
- Xem xét API thao tác tương đối với directory handle, `SecureDirectoryStream` khi provider hỗ trợ, các tùy chọn không theo symbolic link và chính sách quyền hệ điều hành.
- Xử lý lỗi khi mở/đọc/ghi thật, không chỉ kiểm tra rồi tin trạng thái sẽ không đổi (**TOCTOU: time-of-check to time-of-use**).

## 9. Quy tắc file name cũng có thể khác nhau

Không chỉ dấu phân cách và chữ hoa–thường, filesystem còn có khác biệt về tên:

- Windows thông thường hạn chế một số ký tự trong thành phần tên file (chẳng hạn `<>:"/\|?*`), đồng thời có các tên thiết bị hoặc quy tắc đặc biệt; cấu hình/API có thể thay đổi một số giới hạn.
- Unix/Linux thông thường không cho `/` và NUL trong tên phần tử; những ký tự như `:` hoặc `\` có thể là ký tự tên hợp lệ.
- Độ dài, khoảng trắng cuối tên, dấu chấm cuối tên, Unicode normalization và tên tương đương có thể được xử lý khác theo provider và nền tảng.
- Một tên được chấp nhận khi tạo `Path` chưa chắc file **tạo được**: thao tác `Files.createFile(...)` còn có thể lỗi do quyền, policy hoặc giới hạn filesystem.

Nếu tên file đến từ người dùng hoặc hệ thống ngoài, không tự viết “bảng thay ký tự” chung mà giả định sẽ hợp lệ trên mọi filesystem. Hãy xác định phạm vi ứng dụng, chuẩn hóa **tên logic** ở tầng ứng dụng, giới hạn thành phần rỗng/`..` khi cần, và để thao tác thực tế báo lỗi qua exception. `InvalidPathException` có thể xuất hiện ngay khi phân tích chuỗi thành `Path`; `IOException` xuất hiện khi thao tác I/O thất bại.

Một quy ước ứng dụng tương đối dễ di chuyển là đặt tên đơn giản bằng chữ/số ASCII, dấu gạch ngang và gạch dưới, nhưng đó chỉ là **quy ước do ứng dụng chọn**, không phải tập ký tự duy nhất hợp lệ của mọi filesystem. Đồng thời phải xử lý xung đột tên nếu triển khai sang hệ thống không phân biệt hoa–thường.

## 10. Các trường hợp trong phát triển và triển khai

### 10.1. Dự án chạy trên máy cá nhân nhưng lỗi trong CI

Máy phát triển có thể có filesystem case-insensitive, còn runner Linux thường dùng filesystem case-sensitive. Dòng code:

```java
Path config = Path.of("config", "Settings.json");
```

Có thể hoạt động cục bộ khi file thật tên `settings.json`, nhưng lỗi khi triển khai vào môi trường phân biệt chữ hoa–thường. Cách sửa là **thống nhất chính xác cách viết tên file trong code/config và dữ liệu đóng gói**, không phải tự dùng `equalsIgnoreCase()` để tìm mọi file gần giống.

### 10.2. Build hoặc script tự nối dấu phân cách

```java
// Cách không nên dùng:
String location = root + "\\" + "data" + "\\" + "result.txt";
```

Đoạn minh họa trên giả định biến `root` tồn tại. Nó mang giả định Windows và có thể tạo tên file chứa `\` trên Unix. Dùng `Path base = Path.of(root); Path location = base.resolve("data").resolve("result.txt");`, rồi truyền `Path` vào `Files`/API tương ứng.

### 10.3. File path trong URL khác file path của hệ điều hành

URL và URI dùng cú pháp riêng. Đừng lấy đường dẫn Windows `C:\data\a.txt` rồi tự nối `"file://" + path`: dấu backslash, space và các ký tự đặc biệt cần tuân cú pháp URI. Khi đã có `Path`, dùng `path.toUri()` nếu cần `file:` URI; ở chiều ngược lại, dùng API chuyển URI sang `Path` phù hợp provider. **Không** dùng URI path string như một đường dẫn local mà chưa chuyển qua API.

### 10.4. Symbolic link và case sensitivity trong cache

Một cache dựa trên `Path.toString()` có thể tạo nhiều khóa cho cùng một file hoặc gộp sai các file khác nhau khi so sánh không đúng. Nếu cache phụ thuộc danh tính đối tượng thực, cân nhắc thuộc tính file, `Files.isSameFile`, `fileKey()` khi provider hỗ trợ, và ranh giới vòng đời của cache. Không khẳng định một cách chuẩn hóa chuỗi duy nhất luôn tương ứng 1:1 với file vật lý ở mọi hệ thống.

### 10.5. So sánh root trên các filesystem khác nhau

Hai `Path` đến từ những provider khác nhau không nhất thiết so sánh/resolve như các path cùng provider. Một số thao tác có thể ném `ProviderMismatchException`. Dùng provider của chính `Path` (`path.getFileSystem()`) khi cần thao tác tương thích; không cố trộn `Path` ZIP với `Path` default rồi giả định có một dấu phân cách toàn cục.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Luôn nối `"/"` hoặc `"\\"` thủ công | Đường dẫn không tương thích provider/OS | `Path.of(segments...)`, `resolve(...)` |
| Nhầm `File.pathSeparator` với `File.separator` | Dùng `;`/`:` giữa thư mục hoặc `\`/`/` để ghép classpath | Hiểu rõ directory separator khác path-list separator |
| Truyền `"C:\\foo\\bar"` vào `Path.of` trên Unix và nghĩ đó là Windows path | Sai root, sai thành phần | Dùng provider/cú pháp đúng với nguồn dữ liệu |
| Coi `C:foo` là absolute Windows path | Thư mục hiện hành của drive có thể ảnh hưởng kết quả | Phân biệt drive-relative và drive-rooted |
| Viết `String.split(File.separator)` | Trên Windows có thể lỗi regex | Ưu tiên `Path` hoặc `Pattern.quote` cho văn bản đơn giản |
| Dựa vào `os.name` để suy case-sensitivity | Sai với volume/thư mục cấu hình khác | Kiểm tra theo filesystem và xử lý tồn tại/thao tác thật |
| Dùng `equalsIgnoreCase()` để nhận biết cùng file | Gộp sai hoặc vẫn bỏ sót alias/symlink | Hiểu `Path.equals`, dùng `Files.isSameFile` nếu cần identity |
| Nghĩ `normalize()` giải symbolic link | Có thể sai thực thể file | Phân biệt lexical normalization với `toRealPath()` |
| Dùng `String.startsWith(base)` để kiểm tra child path | Tên `app-data` có thể trông như con của `app` | `Path.startsWith` cho thành phần, và biện pháp bảo mật bổ sung |
| Quên kiểm tra absolute RHS khi gọi `resolve` | Input có thể thay root dự kiến | Ràng buộc input và kiểm tra ngữ nghĩa đường dẫn |
| Chỉ gọi `Files.exists()` rồi mở | File/quyền có thể thay đổi trong lúc chờ | Bắt `IOException` tại thao tác thật, tránh TOCTOU |
| Giả định path thực luôn giữ nguyên | Symbolic link, mount, rename có thể thay đổi | Xem xét handle và cơ chế bảo vệ phù hợp |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `File.separator` và `File.pathSeparator` khác gì?

**Đáp án:** `separator` phân cách **các thư mục trong một path**; `pathSeparator` phân cách **nhiều path trong một danh sách** như PATH/classpath. Thường là `/` và `:` trên Unix; `\` và `;` trên Windows.

**Câu 2.** `Path.of("data", "logs", "app.log")` có cần tự chọn dấu `/` hay `\` không?

**Đáp án:** Không. Default filesystem/provider xử lý các thành phần và định dạng đường dẫn.

**Câu 3.** Trên Windows, `C:notes.txt` có giống `C:\notes.txt` không?

**Đáp án:** Không. Dạng đầu là **drive-relative**; dạng sau có root trên drive `C:`.

**Câu 4.** Chạy trên Unix, `Path.of("C:\\work\\note.txt")` có tự phân tích thành root Windows không?

**Đáp án:** Không. Default provider Unix không hiểu cú pháp ổ đĩa Windows theo nghĩa native Windows filesystem.

**Câu 5.** File `Readme.txt` và `README.txt` có luôn là hai file khác nhau không?

**Đáp án:** Không. Tùy filesystem, volume/thư mục và cấu hình phân biệt hoa–thường. Cũng không được đoán chắc chỉ theo `os.name`.

**Câu 6.** Vì sao `Path.equals()` không phải phép kiểm tra hai path trỏ cùng file?

**Đáp án:** Nó so sánh các đối tượng path theo quy tắc provider, không bắt buộc truy cập filesystem. `Files.isSameFile()` được thiết kế cho câu hỏi về identity file hiện tại và có thể ném `IOException`.

**Câu 7.** `normalize()` và `toRealPath()` khác nhau cơ bản ở đâu?

**Đáp án:** `normalize()` chỉ biến đổi cú pháp; `toRealPath()` truy vấn filesystem, xử lý đường dẫn thực theo các tùy chọn và có thể ném `IOException`.

**Câu 8.** `normalizedCandidate.startsWith(normalizedRoot)` đã đủ đảm bảo người dùng không truy cập ra ngoài thư mục gốc?

**Đáp án:** Chưa. Nó hữu ích cho kiểm tra **lexical** nhưng không xử lý hết symbolic link, junction, thay đổi đồng thời và chính sách truy cập. Cần kiểm soát nguồn và sử dụng các cơ chế I/O/bảo mật phù hợp.

**Câu 9.** Vì sao `String.split(File.separator)` có thể lỗi trên Windows?

**Đáp án:** `split` dùng **regex**, trong đó `\` là ký tự escape; đường phân cách `\` không thể dùng như regex literal mà không quote đúng. Với Path thật, hãy dùng API `Path` thay vì tách string.

**Câu 10.** Khi cần tạo `file:` URI từ một `Path`, nên tự ghép `"file://"` với `Path.toString()` không?

**Đáp án:** Không. Dùng `path.toUri()` để chuyển theo API, tránh lỗi escape và cú pháp URI.

**Ghi nhớ:** `Path` là **đối tượng thuộc một filesystem/provider**, không phải chuỗi phân cách tùy tiện. Ghép tên bằng `Path.of(...)`/`resolve(...)`, phân biệt `/`, `\`, `:` và `;`, không nhầm Windows drive-relative với absolute, không mặc định filesystem nào cũng phân biệt hoa–thường giống nhau. Phân biệt **so sánh chuỗi**, **so sánh Path**, **danh tính file thực**, và nhớ rằng phép chuẩn hóa đường dẫn không thay thế bảo vệ truy cập vào filesystem.
