# Path separator trong Java và cross-platform tooling

Trong Java, thuật ngữ “path separator” thường bị dùng cho hai ký tự khác nhau. Một ký tự ngăn cách các thành phần của đường dẫn file, ví dụ `\` trên Windows và `/` trên Linux/macOS. Ký tự còn lại ngăn cách nhiều đường dẫn trong một danh sách như classpath hoặc biến môi trường `PATH`, ví dụ `;` trên Windows và `:` trên Linux/macOS.

Hai giá trị này có mục đích khác nhau:

- `File.separator`: ký tự phân cách các thành phần của một đường dẫn file.
- `File.pathSeparator`: ký tự phân cách nhiều đường dẫn trong một danh sách.

Khi viết code dùng trên nhiều hệ điều hành, hãy dùng `Path`/`Files` để tạo và thao tác với đường dẫn; dùng `File.pathSeparator` khi phải tạo hoặc phân tích một chuỗi path-list. Không ghép chuỗi bằng dấu `\`, `/`, `;` hoặc `:` cố định.

Các ví dụ Java trong bài tương thích Java 17+. Demo được biên dịch với `javac --release 17 -Xlint:all -Werror` và chạy trên Zulu/OpenJDK 24.0.2 trên Windows 11.

## 1. Hai loại separator cần phân biệt

| API | Windows | Linux/macOS | Dùng để |
|---|---:|---:|---|
| `File.separator` | `\` | `/` | Ngăn cách thư mục và tên file trong một path |
| `File.separatorChar` | `\` | `/` | Phiên bản `char` của file separator |
| `File.pathSeparator` | `;` | `:` | Ngăn cách nhiều path trong một danh sách |
| `File.pathSeparatorChar` | `;` | `:` | Phiên bản `char` của path-list separator |
| `FileSystems.getDefault().getSeparator()` | `\` | `/` | Separator của default file system |

Ví dụ một đường dẫn:

~~~text
Windows: C:\work\app\config\settings.json
Linux:   /work/app/config/settings.json
macOS:   /Users/dev/work/app/config/settings.json
~~~

Mỗi ví dụ ở trên là **một path**. Separator giữa các phần tử thư mục là `File.separator`.

Ví dụ một classpath gồm hai entries:

~~~text
Windows: build\classes;lib\example.jar
Linux:   build/classes:lib/example.jar
macOS:   build/classes:lib/example.jar
~~~

Đây là **một danh sách path**. Separator giữa các entries là `File.pathSeparator`. Mỗi entry bên trong danh sách vẫn là một path có file separator riêng.

Đừng nhầm hai cấp này. Dùng `File.separator` để nối các entry của classpath sẽ tạo classpath sai; dùng `File.pathSeparator` để ghép tên thư mục sẽ tạo đường dẫn sai.

## 2. `File.separator` và `File.pathSeparator`

Hai hằng số nằm trong `java.io.File`:

~~~java
import java.io.File;

public class SeparatorValues {
    public static void main(String[] args) {
        System.out.println("FILE_SEPARATOR=" + File.separator);
        System.out.println("FILE_PATH_SEPARATOR=" + File.pathSeparator);
    }
}
~~~

Trên Windows, output:

~~~text
FILE_SEPARATOR=\
FILE_PATH_SEPARATOR=;
~~~

Trên Linux/macOS, output:

~~~text
FILE_SEPARATOR=/
FILE_PATH_SEPARATOR=:
~~~

`File.separator` và `File.pathSeparator` là các giá trị của default file system mà JVM đang chạy. Chúng không đại diện cho mọi filesystem provider mà ứng dụng có thể mở. Với một `Path` cụ thể, có thể lấy separator của provider bằng:

~~~java
String separator = path.getFileSystem().getSeparator();
~~~

Nếu làm việc với default filesystem, `File.separator` và `FileSystems.getDefault().getSeparator()` phản ánh cùng loại separator. `File.separatorChar` và `File.pathSeparatorChar` hữu ích khi API yêu cầu `char` thay vì `String`.

## 3. Dùng `Path` thay vì tự nối chuỗi

Từ Java 11, `Path.of(...)` là cách ngắn gọn để tạo path. Java 7+ có `Paths.get(...)`; cả hai đều tạo `Path` từ default filesystem khi dùng overload nhận chuỗi.

~~~java
import java.nio.file.Path;

public class BuildPath {
    public static void main(String[] args) {
        Path source = Path.of("src", "main", "java");
        Path config = Path.of("config").resolve("app.properties");

        System.out.println("SOURCE=" + source);
        System.out.println("CONFIG=" + config);
    }
}
~~~

`Path.of("src", "main", "java")` nhận từng thành phần riêng. Provider sẽ dùng đúng separator của hệ điều hành. Trên Windows, `toString()` thường in `src\main\java`; trên Linux/macOS, nó in `src/main/java`.

Cách dễ gây lỗi:

~~~java
String config = "config" + File.separator + "app.properties";
~~~

Cách nên dùng:

~~~java
Path config = Path.of("config", "app.properties");
~~~

`Path` biểu diễn cấu trúc path và cung cấp các thao tác chuyên biệt. Chỉ chuyển sang chuỗi ở ranh giới cần truyền path cho API hoặc hiển thị cho người dùng.

## 4. Ghép path bằng `resolve`, không dùng `+`

`resolve` thêm một path hoặc một thành phần vào path gốc:

~~~java
Path project = Path.of("build", "reports");
Path javadoc = project.resolve("javadoc").resolve("index.html");
~~~

Kết quả phụ thuộc filesystem:

~~~text
Windows: build\reports\javadoc\index.html
POSIX:   build/reports/javadoc/index.html
~~~

Có thể resolve một chuỗi nhiều thành phần:

~~~java
Path classes = Path.of("build").resolve(Path.of("classes", "java", "main"));
~~~

`resolveSibling` tạo path mới cùng thư mục cha:

~~~java
Path report = Path.of("build", "reports", "summary.html");
Path csv = report.resolveSibling("summary.csv");
~~~

Một lưu ý quan trọng: nếu đối số truyền vào `resolve` là absolute path, kết quả là path absolute đó. Nếu path con đến từ input bên ngoài, đừng giả định nó luôn nằm dưới thư mục gốc.

Ví dụ kiểm soát path con theo cách lexical:

~~~java
Path root = Path.of("data").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Path escapes the data directory");
}
~~~

Đối với dữ liệu nhạy cảm, kiểm tra lexical bằng `normalize`/`startsWith` chưa đủ nếu filesystem có symbolic link. Khi file đã tồn tại, cần cân nhắc `toRealPath()` và kiểm soát symlink theo threat model của ứng dụng.

## 5. Relative path, absolute path và normalize

`Path` có thể là relative hoặc absolute:

~~~java
Path relative = Path.of("logs", "application.log");
Path absolute = relative.toAbsolutePath();
Path normalized = Path.of("build", "reports", "..", "classes").normalize();

System.out.println(relative);
System.out.println(absolute);
System.out.println(normalized);
~~~

- `toAbsolutePath()` chuyển path thành absolute path dựa trên working directory hiện tại.
- `normalize()` loại bỏ các thành phần dư thừa như `.` và một số cặp `name/..` theo quy tắc lexical.
- `toRealPath()` trả về path thực của một file tồn tại, thường giải quyết symbolic link và các thành phần filesystem.

`normalize()` không truy cập filesystem, không kiểm tra file có tồn tại và không tự giải quyết symbolic link. `toRealPath()` cần file hoặc thư mục tồn tại; nếu path không tồn tại, thao tác có thể ném `IOException`.

Ví dụ:

~~~java
Path p = Path.of("build", "reports", "..", "classes");
System.out.println(p.normalize());
~~~

Kết quả tương ứng:

~~~text
Windows: build\classes
POSIX:   build/classes
~~~

Không dùng `normalize()` như một biện pháp duy nhất để chống path traversal hoặc symlink escape.

## 6. Đọc các thành phần của `Path`

`Path` có thể được phân tích mà không cần tách chuỗi theo dấu slash:

~~~java
Path path = Path.of("src", "main", "java", "com", "example", "Main.java");

System.out.println("FILE_NAME=" + path.getFileName());
System.out.println("PARENT=" + path.getParent());
System.out.println("ROOT=" + path.getRoot());
System.out.println("NAME_COUNT=" + path.getNameCount());
System.out.println("FIRST_NAME=" + path.getName(0));
~~~

Trên path relative ở trên, `getRoot()` trả `null`; `getFileName()` trả `Main.java`. Với absolute path, root phụ thuộc hệ điều hành và filesystem, ví dụ `/` trên POSIX hoặc `C:\` trên Windows.

`getNameCount()` và `getName(i)` truy cập các thành phần path. Không cần gọi `split("/")` hoặc `split("\\\\")`, vì những cách đó phụ thuộc cú pháp path và có thể xử lý sai root, UNC path hoặc tên có ký tự đặc biệt.

Có thể so sánh và tính path tương đối:

~~~java
Path base = Path.of("project", "src");
Path file = Path.of("project", "src", "Main.java");

System.out.println(base.relativize(file));
~~~

`relativize` yêu cầu hai path thuộc cùng filesystem và tương thích về root. Trên Windows, hai path nằm ở hai drive khác nhau thường không thể relativize với nhau.

## 7. Dùng `Files` để thao tác với file và thư mục

Sau khi có `Path`, dùng `Files` để đọc/ghi và tạo thư mục:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileOperations {
    public static void main(String[] args) throws IOException {
        Path output = Path.of("build", "reports", "summary.txt");
        Files.createDirectories(output.getParent());
        Files.writeString(output, "BUILD_OK", StandardCharsets.UTF_8);

        String content = Files.readString(output, StandardCharsets.UTF_8);
        System.out.println(content);
    }
}
~~~

Lệnh biên dịch và chạy:

~~~text
javac --release 17 -encoding UTF-8 -d out FileOperations.java
java -cp out FileOperations
~~~

Stdout:

~~~text
BUILD_OK
~~~

`Files.createDirectories` tạo cả các thư mục cha còn thiếu. Dùng `Path.resolve` để tạo file đích và `Files` để thao tác; không tự dựng chuỗi với separator. Trong ứng dụng thực tế, xử lý `IOException`, quyền truy cập, race condition và chính sách overwrite phù hợp với nghiệp vụ.

Một số API hữu ích:

| API | Công dụng |
|---|---|
| `Files.exists(path)` | Kiểm tra path có tồn tại tại thời điểm gọi |
| `Files.isDirectory(path)` | Kiểm tra thư mục |
| `Files.isRegularFile(path)` | Kiểm tra file thường |
| `Files.createDirectories(path)` | Tạo thư mục và các thư mục cha |
| `Files.copy(source, target, ...)` | Copy file |
| `Files.move(source, target, ...)` | Move/rename |
| `Files.deleteIfExists(path)` | Xóa nếu tồn tại |
| `Files.readString(path, charset)` | Đọc text |
| `Files.writeString(path, text, charset)` | Ghi text |

Các phép kiểm tra tồn tại/trạng thái chỉ phản ánh thời điểm gọi; file có thể thay đổi ngay sau đó. Nếu thao tác phải nguyên tử hoặc an toàn trước thay đổi đồng thời, thiết kế thao tác file dựa trên exception và các option của `Files` thay vì dựa vào check-then-act.

## 8. Tạo path-list và classpath đúng cách

Khi một API yêu cầu một chuỗi chứa nhiều path, dùng `File.pathSeparator`:

~~~java
import java.io.File;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

public class ClassPathBuilder {
    public static void main(String[] args) {
        List<Path> entries = List.of(
                Path.of("build", "classes"),
                Path.of("lib", "example.jar"),
                Path.of("lib", "logging.jar"));

        String classPath = entries.stream()
                .map(Path::toString)
                .collect(Collectors.joining(File.pathSeparator));

        System.out.println(classPath);
    }
}
~~~

Kết quả trên Windows:

~~~text
build\classes;lib\example.jar;lib\logging.jar
~~~

Kết quả trên Linux/macOS:

~~~text
build/classes:lib/example.jar:lib/logging.jar
~~~

`File.pathSeparator` được dùng giữa các entries; mỗi entry được tạo bằng `Path` nên nội dung của nó đã có separator đúng. Đừng hardcode `;` hoặc `:` trong code Java nếu danh sách cần chạy trên nhiều hệ điều hành.

Nếu chỉ có hai entries, `String.join` cũng phù hợp:

~~~java
String classPath = String.join(
        File.pathSeparator,
        Path.of("build", "classes").toString(),
        Path.of("lib", "example.jar").toString());
~~~

## 9. Phân tích một path-list

Nếu phải đọc `PATH` hoặc `java.class.path`, dùng `File.pathSeparator` làm delimiter. Vì `String.split` nhận regular expression, dùng `Pattern.quote` để thể hiện rõ delimiter là chuỗi literal:

~~~java
import java.io.File;
import java.util.regex.Pattern;

public class PathListReader {
    public static void main(String[] args) {
        String classPath = System.getProperty("java.class.path", "");
        String[] entries = classPath.split(
                Pattern.quote(File.pathSeparator), -1);

        for (String entry : entries) {
            System.out.println(entry);
        }
    }
}
~~~

Đối với `PATH` environment variable:

~~~java
String pathValue = System.getenv("PATH");
if (pathValue != null) {
    String[] directories = pathValue.split(
            Pattern.quote(File.pathSeparator), -1);
}
~~~

Không dùng `File.separator` để split classpath. Một classpath Windows có thể chứa nhiều dấu `\` bên trong từng entry, nhưng chỉ dấu `;` mới tách các entry. Trên POSIX, dấu `/` nằm bên trong mỗi entry và dấu `:` mới tách danh sách.

Path-list có thể chứa entry rỗng hoặc ký tự đặc biệt theo quy ước của hệ điều hành/launcher. Không tự viết parser tổng quát bằng `split` nếu định dạng đầu vào có quoting hoặc escaping riêng; hãy theo contract của API đang đọc.

## 10. `PATH`, `CLASSPATH` và Java classpath khác nhau

Ba khái niệm thường bị trộn lẫn:

- `PATH`: biến môi trường của hệ điều hành, giúp shell tìm executable như `java`, `javac`, `git`.
- `CLASSPATH`: biến môi trường Java cũ dùng để chỉ nơi tìm class/JAR nếu launcher không nhận classpath rõ ràng khác.
- `-cp`/`-classpath`: option của Java launcher hoặc compiler để chỉ classpath cho một lần chạy/biên dịch.

Cả `PATH` và classpath thường là path-list, vì vậy delimiter phụ thuộc hệ điều hành: `;` trên Windows và `:` trên POSIX. Tuy nhiên, mỗi phần tử của chúng là path tới thư mục hoặc file, nên file separator trong mỗi phần tử lại phụ thuộc filesystem.

Ví dụ:

~~~text
Windows PATH:
C:\Program Files\Java\jdk-24\bin;C:\Tools\Git\bin

POSIX PATH:
/usr/lib/jvm/jdk-24/bin:/usr/local/bin:/usr/bin
~~~

Ưu tiên truyền classpath rõ ràng bằng `-cp` hoặc để build tool quản lý dependency. Không phụ thuộc vào một `CLASSPATH` global trên máy developer, vì giá trị này có thể làm build local khác CI.

## 11. Chạy `java -cp` trên Windows và POSIX

Cùng một chương trình có thể cần cách viết command line khác nhau vì classpath delimiter và file path separator khác nhau.

Windows PowerShell hoặc CMD:

~~~powershell
java -cp "build\classes;lib\example.jar" com.example.Main
~~~

Linux/macOS shell:

~~~sh
java -cp "build/classes:lib/example.jar" com.example.Main
~~~

Nếu path có khoảng trắng, quote toàn bộ classpath argument:

~~~powershell
java -cp "build\classes;lib\example library.jar" com.example.Main
~~~

~~~sh
java -cp "build/classes:lib/example library.jar" com.example.Main
~~~

Quote giúp shell truyền classpath thành một argument. Nó không thay đổi delimiter mà Java launcher dùng để phân tách các entries. Tránh copy nguyên lệnh Windows sang Linux/macOS hoặc ngược lại.

Khi viết script cross-platform, có thể dùng script riêng cho từng shell, hoặc để Maven/Gradle/IDE tạo classpath thay vì tự ghép chuỗi.

## 12. Đường dẫn Windows, POSIX và UNC

Một số dạng path phổ biến:

| Dạng | Ví dụ | Ý nghĩa |
|---|---|---|
| Windows absolute | `C:\work\app` | Path trên drive C |
| Windows relative | `src\main\java` | Tương đối với working directory |
| Windows UNC | `\\server\share\folder` | Tài nguyên mạng |
| POSIX absolute | `/opt/app/config` | Bắt đầu từ root `/` |
| POSIX relative | `src/main/java` | Tương đối với working directory |
| Home-relative shell | `~/project` | Shell expansion, không phải cú pháp Java Path |

Không hardcode drive letter `C:` trong ứng dụng portable. Lấy base directory từ config, system property hoặc environment variable đã được định nghĩa, rồi resolve các thành phần còn lại.

`~` là cú pháp expansion của một số shell; `Path.of("~/project")` không tự mở rộng thành home directory. Trong Java, dùng:

~~~java
Path home = Path.of(System.getProperty("user.home"));
Path project = home.resolve("project");
~~~

Để lấy working directory:

~~~java
Path workingDirectory = Path.of("").toAbsolutePath().normalize();
~~~

Không giả định working directory là thư mục chứa JAR hoặc source code. Service manager, IDE, container và CI có thể khởi chạy process từ các thư mục khác nhau.

## 13. Phân biệt filesystem path với URI và URL

URI có cú pháp riêng và thường dùng `/` trong path component, kể cả khi tài nguyên nằm trên Windows. Đây không phải lý do để dùng slash làm file separator trong mọi chuỗi.

Ví dụ URI:

~~~text
file:///C:/work/app/config/settings.json
https://example.com/api/v1/items
~~~

Dùng `Path.toUri()` để chuyển một file path thành URI:

~~~java
Path file = Path.of("config", "settings.json");
java.net.URI uri = file.toAbsolutePath().toUri();
~~~

`Path.toUri()` tạo URI phù hợp với filesystem provider. Không tự thay `\` bằng `/` rồi ghép `file://`; việc đó có thể làm sai drive, UNC path, dấu cách hoặc ký tự Unicode.

Để tạo path từ URI `file:`, dùng `Path.of(uri)` khi URI thuộc provider phù hợp. URI `https:` không phải file path và không thể truyền tùy tiện vào `Path.of(URI)`. Dùng `URI`/HTTP client cho tài nguyên mạng.

Khi lưu path vào JSON, YAML hoặc properties, chú ý escaping của định dạng đó. Ví dụ trong JSON, backslash phải được escape theo JSON string syntax. Tốt nhất dùng thư viện serialize thay vì tự thay ký tự bằng `replace`.

## 14. Java chạy trong Docker, WSL và CI

Separator được quyết định bởi filesystem/provider mà JVM đang sử dụng, không nhất thiết là hệ điều hành của máy host.

Ví dụ:

- JVM chạy trực tiếp trên Windows thường dùng `\` và `;`.
- JVM chạy trong Linux container dùng `/` và `:`, kể cả khi Docker host là Windows.
- JVM chạy trong WSL dùng filesystem Linux cho process trong WSL.
- CI runner Windows và Linux có thể tạo cùng một artifact nhưng path trong log và classpath khác nhau.

Đừng suy ra separator từ biến CI như `RUNNER_OS` nếu JVM đã cung cấp `File.separator` và `File.pathSeparator`. Nếu cần ghi log chẩn đoán:

~~~java
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("file.separator=" + File.separator);
System.out.println("path.separator=" + File.pathSeparator);
System.out.println("user.dir=" + System.getProperty("user.dir"));
~~~

Với Docker volume, mount path phía trong container phải tuân theo OS của container. Một đường dẫn Windows ở host không tự động là đường dẫn hợp lệ bên trong Linux container.

## 15. Build tool và cross-platform classpath

Với Maven, Gradle hoặc Ant, nên khai báo source set và dependency bằng cấu hình của build tool. Build tool sẽ tạo classpath phù hợp với nền tảng.

Ví dụ Maven:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>example-library</artifactId>
  <version>1.2.0</version>
</dependency>
~~~

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'com.example:example-library:1.2.0'
}
~~~

Tránh nối thủ công chuỗi classpath trong `pom.xml`, `build.gradle` hoặc CI script nếu build tool đã có dependency model. Dùng wrapper scripts để pin phiên bản build tool:

~~~text
Windows: mvnw.cmd verify
POSIX:   ./mvnw verify
~~~

~~~text
Windows: gradlew.bat check
POSIX:   ./gradlew check
~~~

Với Ant, dùng nested `<classpath>` và `<pathelement>` thay vì tự dựng chuỗi theo OS:

~~~xml
<path id="compile.classpath">
  <pathelement location="lib/example.jar"/>
  <pathelement location="build/classes"/>
</path>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       classpathref="compile.classpath"/>
~~~

Các build tool này tự chọn separator phù hợp cho classpath; nhiệm vụ của người viết build là khai báo đúng dependency và file locations.

## 16. Những lỗi phổ biến

### Dùng `File.separator` để nối classpath

**Triệu chứng:** Java không tìm thấy class/JAR thứ hai trong classpath.

**Nguyên nhân:** `File.separator` ngăn cách thư mục bên trong một path, không ngăn cách các entries trong path-list.

**Cách sửa:** dùng `File.pathSeparator` giữa entries và `Path` để tạo từng entry.

### Dùng `File.pathSeparator` để ghép thư mục

**Triệu chứng:** path chứa `;` trên Windows hoặc `:` trên POSIX và file không tồn tại.

**Nguyên nhân:** path-list delimiter bị dùng như filesystem separator.

**Cách sửa:** dùng `Path.of("dir", "subdir", "file.txt")` hoặc `resolve`.

### Hardcode slash hoặc backslash

**Triệu chứng:** chương trình hoạt động trên máy developer nhưng fail trên CI khác OS.

**Nguyên nhân:** path string phụ thuộc cú pháp của một filesystem.

**Cách sửa:** tạo path bằng `Path` API; chỉ dùng literal path khi định dạng đó được quy định rõ và gắn với một nền tảng cụ thể.

### Split classpath theo `/` hoặc `\`

**Triệu chứng:** một classpath entry bị tách thành nhiều mảnh hoặc không tìm thấy JAR.

**Nguyên nhân:** code split theo separator bên trong path thay vì delimiter giữa entries.

**Cách sửa:** `split(Pattern.quote(File.pathSeparator))`.

### Dùng `replace("\\", "/")` để portable

**Triệu chứng:** tên file hợp lệ trên POSIX bị thay đổi hoặc URI/path sai.

**Nguyên nhân:** thay chuỗi ký tự không hiểu filesystem semantics.

**Cách sửa:** giữ path ở dạng `Path`; chuyển sang URI bằng `toUri()` khi cần.

### Giả định `~` tự mở rộng

**Triệu chứng:** ứng dụng tìm thư mục có tên literal `~`.

**Nguyên nhân:** shell expansion không được thực hiện khi Java nhận argument.

**Cách sửa:** dùng `System.getProperty("user.home")`.

### Dùng `normalize()` để kiểm tra file tồn tại

**Triệu chứng:** code tưởng rằng path đã hợp lệ nhưng thao tác file vẫn thất bại.

**Nguyên nhân:** `normalize()` chỉ xử lý lexical components, không truy cập filesystem.

**Cách sửa:** dùng `Files.exists`, `Files.isRegularFile`, `toRealPath` hoặc trực tiếp thực hiện operation và xử lý exception phù hợp.

### Giả định working directory cố định

**Triệu chứng:** relative path hoạt động trong IDE nhưng fail trong service hoặc CI.

**Nguyên nhân:** `user.dir` khác giữa các launcher.

**Cách sửa:** xác định base directory rõ ràng và resolve path từ base đó.

### Dùng path của host trong container

**Triệu chứng:** ứng dụng trong Linux container không mở được `C:\...`.

**Nguyên nhân:** JVM nhìn thấy filesystem của container.

**Cách sửa:** mount volume và cấu hình đường dẫn phía trong container theo OS của container.

## 17. Ví dụ Java 17+: kiểm tra separator và thao tác file

Tạo `PathSeparatorDemo.java`:

~~~java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

public final class PathSeparatorDemo {
    private PathSeparatorDemo() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("FILE_SEPARATOR=" + File.separator);
        System.out.println("FILE_PATH_SEPARATOR=" + File.pathSeparator);
        System.out.println("FILESYSTEM_SEPARATOR="
                + FileSystems.getDefault().getSeparator());

        Path javadoc = Path.of("build", "reports")
                .resolve("javadoc")
                .resolve("index.html");
        Path normalized = Path.of("build", "reports", "..", "classes")
                .normalize();
        System.out.println("JAVADOC_PATH=" + javadoc);
        System.out.println("NORMALIZED_PATH=" + normalized);

        String classPath = String.join(
                File.pathSeparator,
                Path.of("build", "classes").toString(),
                Path.of("lib", "example.jar").toString());
        String[] entries = classPath.split(
                Pattern.quote(File.pathSeparator), -1);
        System.out.println("CLASSPATH=" + classPath);
        System.out.println("CLASSPATH_ENTRIES=" + entries.length);

        Path tempDir = Files.createTempDirectory("path-separator-demo-");
        Path output = tempDir.resolve("nested").resolve("result.txt");
        Files.createDirectories(output.getParent());
        Files.writeString(output, "PATH_SEPARATOR_OK",
                StandardCharsets.UTF_8);
        String content = Files.readString(output, StandardCharsets.UTF_8);
        System.out.println("FILE_ROUND_TRIP="
                + ("PATH_SEPARATOR_OK".equals(content) ? "PASS" : "FAIL"));

        Files.deleteIfExists(output);
        Files.deleteIfExists(output.getParent());
        Files.deleteIfExists(tempDir);
    }
}
~~~

Biên dịch:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror PathSeparatorDemo.java
~~~

Chạy:

~~~text
java PathSeparatorDemo
~~~

Stdout trên Windows:

~~~text
FILE_SEPARATOR=\
FILE_PATH_SEPARATOR=;
FILESYSTEM_SEPARATOR=\
JAVADOC_PATH=build\reports\javadoc\index.html
NORMALIZED_PATH=build\classes
CLASSPATH=build\classes;lib\example.jar
CLASSPATH_ENTRIES=2
FILE_ROUND_TRIP=PASS
~~~

Stdout trên Linux/macOS có các separator tương ứng:

~~~text
FILE_SEPARATOR=/
FILE_PATH_SEPARATOR=:
FILESYSTEM_SEPARATOR=/
JAVADOC_PATH=build/reports/javadoc/index.html
NORMALIZED_PATH=build/classes
CLASSPATH=build/classes:lib/example.jar
CLASSPATH_ENTRIES=2
FILE_ROUND_TRIP=PASS
~~~

Kết quả trên Windows 11 với Zulu/OpenJDK 24.0.2 khớp chính xác với block Windows. Demo được biên dịch bằng `--release 17`, `-Xlint:all` và `-Werror`; phần ghi/đọc file dùng thư mục tạm và xóa các file sau khi kiểm tra.

## 18. Kiểm thử cross-platform trong CI

Một chương trình dùng `Path` vẫn nên được kiểm tra trên những OS mà sản phẩm hỗ trợ. Một ma trận GitHub Actions tối giản:

~~~yaml
name: Cross-platform path test

on:
  pull_request:
  push:
    branches: [main]

jobs:
  path-demo:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Compile
        run: javac --release 17 -encoding UTF-8 -Xlint:all -Werror PathSeparatorDemo.java

      - name: Run
        run: java PathSeparatorDemo
~~~

Không so sánh stdout nguyên văn giữa Windows và POSIX vì separator khác nhau theo thiết kế. Test nên kiểm tra invariant như:

- `File.separator` bằng separator của default filesystem.
- `File.pathSeparator` dùng để tách classpath thành đúng số entries.
- `Path.resolve` tạo path có các thành phần mong đợi.
- `Files.createDirectories`, write/read và delete hoạt động.
- Không có path string nào bị hardcode theo OS không phù hợp.

Nếu CI matrix dùng cùng test, hãy kiểm tra hành vi và file contents thay vì yêu cầu path text giống hệt giữa các OS.

## 19. Checklist viết Java path portable

- [ ] Dùng `Path.of`/`Paths.get` để tạo path.
- [ ] Dùng `resolve`/`resolveSibling` để ghép path.
- [ ] Dùng `Files` để tạo, đọc, ghi, copy, move và xóa.
- [ ] Chỉ dùng `File.separator` khi thật sự cần ký tự phân cách thành phần path.
- [ ] Chỉ dùng `File.pathSeparator` khi tạo/phân tích path-list hoặc classpath.
- [ ] Dùng `Pattern.quote(File.pathSeparator)` khi split chuỗi path-list.
- [ ] Không hardcode `\`, `/`, `;` hoặc `:` trong code portable.
- [ ] Không dùng string replace để biến Windows path thành POSIX path hoặc ngược lại.
- [ ] Không coi URI/URL là filesystem path.
- [ ] Xác định base directory; không giả định working directory.
- [ ] Phân biệt normalize lexical với real path và symbolic link.
- [ ] Kiểm soát path con nếu dữ liệu đến từ người dùng.
- [ ] Dùng dependency model của Maven/Gradle/Ant thay vì ghép classpath thủ công.
- [ ] Chạy test trên Windows, Linux và macOS nếu sản phẩm hỗ trợ các nền tảng đó.
- [ ] Kiểm tra path trong container theo filesystem của container.

## 20. Tài liệu tham khảo

- Java SE 24 — `java.io.File`, `separator` và `pathSeparator`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/File.html
- Java SE 24 — `java.nio.file.Path`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Path.html
- Java SE 24 — `java.nio.file.FileSystem`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/FileSystem.html
- Java SE 24 — `java.nio.file.Files`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Files.html
- Oracle JDK 24 — `java` launcher và classpath: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — `javac` command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Java SE 24 — `java.net.URI`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/net/URI.html
- Gradle — Java Plugin và dependency configurations: https://docs.gradle.org/current/userguide/java_plugin.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html

Hãy nhớ hai cấp separator: `File.separator` phân cách thành phần của một file path; `File.pathSeparator` phân cách nhiều path trong classpath hoặc path-list. Dùng `Path`/`Files` cho filesystem và chỉ ghép path-list bằng delimiter do nền tảng cung cấp. Khi cần hỗ trợ nhiều OS, kiểm thử trên từng runner và xác minh hành vi thay vì giả định chuỗi path phải giống nhau.