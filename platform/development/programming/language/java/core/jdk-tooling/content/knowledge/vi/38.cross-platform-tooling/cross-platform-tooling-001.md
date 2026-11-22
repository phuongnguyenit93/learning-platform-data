# Khác biệt Windows và Linux khi phát triển Java

Ứng dụng Java chạy trên nhiều hệ điều hành nhờ JVM, nhưng filesystem, process, shell và native libraries vẫn có hành vi khác nhau. Vì vậy, cùng một build có thể chạy trên Windows nhưng lỗi trên Linux do sai chữ hoa/thường, line ending, permission, đường dẫn hoặc command line. Cross-platform development cần dùng API chuẩn, xác định rõ các quy ước của project và kiểm tra trên mọi OS được hỗ trợ.

## 1. Những khác biệt chính

| Khu vực | Windows thường gặp | Linux thường gặp | Ảnh hưởng |
| --- | --- | --- | --- |
| File separator | `\` | `/` | Dùng `Path` thay vì nối chuỗi |
| Path-list separator | `;` | `:` | Khác nhau trong classpath và PATH |
| Case sensitivity | Thường không phân biệt theo mặc định | Thường phân biệt | Sai case có thể chỉ lỗi trên Linux |
| Absolute path | Drive letter hoặc UNC | Bắt đầu từ `/` | Không hardcode root |
| Line ending | CRLF | LF | Script và text file có thể lỗi |
| Permission | Windows ACL | POSIX owner/group/other | Không giả định POSIX API có sẵn |
| Shell | PowerShell/cmd.exe | Bash/dash hoặc shell khác | Command syntax khác nhau |
| Script wrapper | `.bat`/`.cmd` | `./script` | Gọi đúng wrapper theo OS |
| Native library | `.dll` | `.so` | Binary phụ thuộc OS/CPU |
| Process stop | Windows process/control events | POSIX signals | Shutdown behavior khác nhau |

Đây là các mặc định thường gặp, không phải quy luật tuyệt đối. Filesystem, mount options, WSL, container và cấu hình riêng có thể thay đổi hành vi. Kiểm tra capability thực tế thay vì chỉ suy luận từ `os.name`.

## 2. Đường dẫn: dùng Path thay vì nối chuỗi

Java cung cấp `java.nio.file.Path` và `Files` để làm việc với filesystem. `Path` dùng filesystem provider mặc định của JVM, nên provider xử lý cú pháp path của nền tảng.

Hai separator có ý nghĩa khác nhau:

| Java API | Windows | Linux | Ý nghĩa |
| --- | --- | --- | --- |
| `File.separator` | `\` | `/` | Phân cách thành phần trong một path |
| `File.pathSeparator` | `;` | `:` | Phân cách nhiều path trong classpath/path list |

Không viết path cố định như `"build\\reports\\daily\\test.txt"`. Hãy dùng:

```java
Path report = Path.of("build", "reports", "daily", "test.txt");
Path output = Path.of("build").resolve("reports").resolve("daily");
Path absolute = report.toAbsolutePath().normalize();
```

`Path.of(String, String...)` ghép các thành phần theo filesystem hiện tại. `resolve` nối path con vào path cha. `normalize` loại bỏ thành phần dư về mặt cú pháp như `.` và `..`, nhưng không truy cập filesystem hoặc resolve symbolic link.

Khi cần path thực tế của file tồn tại, dùng `toRealPath()`. Phương thức này thực hiện I/O và có thể resolve symbolic link. Không dùng `normalize()` như biện pháp bảo mật cho path do người dùng nhập; cần kiểm tra path sau khi resolve và cân nhắc symlink/path traversal.

### Home, temporary và working directory

Không hardcode `C:\\Users\\name\\...` hoặc `/home/name/...`. Dùng Java properties:

```java
Path home = Path.of(System.getProperty("user.home"));
Path temp = Path.of(System.getProperty("java.io.tmpdir"));
Path working = Path.of(System.getProperty("user.dir"));
Path config = home.resolve(".myapp").resolve("config.json");
```

`user.home` là thư mục home. `java.io.tmpdir` là thư mục tạm. `user.dir` thường là working directory lúc JVM khởi động; nó không nhất thiết là thư mục chứa JAR hoặc source code.

Nếu process cần chạy ở thư mục dự án, đặt rõ bằng `ProcessBuilder.directory(...)`. Đừng giả định runner luôn khởi chạy ở repository root.

### Drive letter và UNC

Windows hỗ trợ drive path như `C:\\work\\app` và UNC path như `\\\\server\\share\\folder`. `C:temp.txt` là đường dẫn tương đối với current directory trên drive C, khác `C:\\temp.txt` là đường dẫn từ root của drive.

Linux thường dùng một cây filesystem bắt đầu từ `/` và không có drive letter. Không đổi path bằng cách thay thủ công `\\` thành `/`; dùng `Path` và URI API phù hợp.

## 3. Case sensitivity và tên file

Filesystem Windows thường giữ nguyên chữ hoa/thường nhưng so sánh tên không phân biệt hoa/thường theo mặc định. Linux filesystem phổ biến như ext4 thường phân biệt:

- `Config.java` và `config.java` có thể là cùng file trên Windows.
- Trên Linux, hai tên này có thể là hai file riêng.
- Import hoặc resource path sai case có thể vẫn chạy trên Windows nhưng thất bại trên Linux.

Không phải mọi volume Windows đều case-insensitive; NTFS có thể bật case sensitivity cho từng thư mục. WSL và mount configuration cũng có thể thay đổi hành vi.

Thực hành:

1. Tên file phải khớp chính xác với tên class public, package và resource.
2. Dùng quy ước đặt tên nhất quán.
3. Không tạo hai file chỉ khác chữ hoa/thường trong cùng repository.
4. Nếu đổi riêng chữ hoa/thường, kiểm tra Git diff và xác nhận rename được ghi nhận.
5. Dùng `Files.isSameFile(pathA, pathB)` khi cần xác định hai path có cùng trỏ tới một file không.

### Tên file portable

Windows dành riêng các ký tự `< > : " / \\ | ? *` trong tên file. Một số tên thiết bị như `CON`, `PRN`, `AUX`, `NUL`, `COM1` và `LPT1` vẫn reserved khi có extension, ví dụ `NUL.txt`. Tên kết thúc bằng dấu chấm hoặc dấu cách cũng gây vấn đề với nhiều API Windows.

Linux cho phép nhiều ký tự hơn; `/` và byte NUL không thể xuất hiện trong một thành phần tên. Một tên hợp lệ trên Linux chưa chắc dùng được trên Windows.

Ưu tiên tên gồm chữ cái ASCII, chữ số, dấu gạch ngang, dấu gạch dưới và dấu chấm ở giữa tên. Tránh reserved names, trailing dot/space và path quá dài.

## 4. Line ending và encoding

### CRLF và LF

Windows thường dùng CRLF (`\\r\\n`); Linux thường dùng LF (`\\n`). Java cung cấp `System.lineSeparator()` để lấy line separator native:

```java
String report = "first line" + System.lineSeparator()
              + "second line" + System.lineSeparator();
```

Chỉ dùng line separator native khi định dạng cho phép. JSON, protocol, shell script hoặc file version-control có thể yêu cầu line ending cụ thể. Khi format yêu cầu LF, hãy ghi LF tường minh. Khi đọc text, dùng `BufferedReader.readLine()` hoặc API phù hợp thay vì tự split chỉ theo `\\n`.

### Chuẩn hóa bằng Git

Dùng `.gitattributes` để thống nhất line ending:

```gitattributes
* text=auto
*.java       text eol=lf
*.gradle     text eol=lf
*.properties text eol=lf
*.yml        text eol=lf
*.yaml       text eol=lf
*.sh         text eol=lf
*.bat        text eol=crlf
*.cmd        text eol=crlf
*.ps1        text eol=crlf
*.jar        binary
*.class      binary
```

Git có thể chuẩn hóa text về LF trong repository và chuyển sang CRLF khi checkout theo cấu hình. `*.sh` nên giữ LF để Linux đọc đúng shebang; batch file có thể dùng CRLF. Binary cần được đánh dấu để Git không chuyển đổi byte.

Nếu project đã có line ending lẫn lộn, xem diff trước khi dùng `git add --renormalize .`. Không đổi `core.autocrlf` toàn cục chỉ để chữa một repository; xác định chính sách trong `.gitattributes`.

### Charset và UTF-8

Từ JDK 18, UTF-8 là default charset của Java SE API trên các hệ điều hành. Trên JDK 17 trở xuống, default charset phụ thuộc runtime, locale và môi trường; Windows có thể dùng code page khác UTF-8.

Dù JDK mới mặc định UTF-8, nên chỉ rõ charset cho dữ liệu lưu trữ hoặc giao tiếp:

```java
Path file = Path.of("data", "customers.txt");
Files.writeString(file, "Nguyễn An", StandardCharsets.UTF_8);
String value = Files.readString(file, StandardCharsets.UTF_8);
```

Với source code, đặt encoding cho compiler:

```bash
javac --release 17 -encoding UTF-8 -d out src/main/java/com/example/App.java
```

Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Maven:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Encoding của file, default charset của Java API và encoding của terminal/stdout không đồng nhất. JEP 400 không có nghĩa mọi console Windows đều hiển thị Unicode giống nhau. Khi giao tiếp với process khác, xác định charset mà process đó dùng.


## 5. Quyền truy cập file và symbolic link

### POSIX permission và Windows ACL

Linux thường dùng quyền owner/group/other với bit read, write, execute. Windows chủ yếu dùng Access Control List (ACL), cùng thuộc tính file và quyền truy cập theo user/group.

Java cung cấp các attribute view:

| API | Mục đích |
| --- | --- |
| `BasicFileAttributeView` | Thuộc tính cơ bản như type, size, thời gian |
| `PosixFileAttributeView` | POSIX owner, group và permission bits |
| `AclFileAttributeView` | Access Control List nếu provider hỗ trợ |
| `DosFileAttributeView` | Thuộc tính DOS như hidden, read-only và archive |

Không gọi `Files.setPosixFilePermissions()` vô điều kiện trên Windows. Provider không hỗ trợ POSIX view có thể trả `null` khi gọi `Files.getFileAttributeView(...)` hoặc ném `UnsupportedOperationException` khi thao tác không được hỗ trợ.

Ví dụ kiểm tra capability:

```java
Path file = Path.of("run.sh");
PosixFileAttributeView posix =
    Files.getFileAttributeView(file, PosixFileAttributeView.class);

if (posix != null) {
    System.out.println(posix.readAttributes().permissions());
} else {
    System.out.println("POSIX permissions are not supported here");
}
```

`Files.isReadable()`, `isWritable()` và `isExecutable()` hữu ích để kiểm tra khả năng truy cập ở mức tổng quát. Chúng không thay thế việc xử lý `IOException` khi thực hiện I/O thật và không phải security check chống race condition.

Trên Linux, shell script thường cần executable bit:

```bash
chmod +x gradlew mvnw
```

Git cần ghi nhận mode executable để checkout trên Linux giữ được khả năng chạy script. Windows không có POSIX executable bit theo cùng cách; wrapper thường được gọi bằng `.bat` hoặc `.cmd`.

### Symbolic link

Linux hỗ trợ symbolic link như một phần thông thường của filesystem. Windows cũng hỗ trợ link, nhưng việc tạo có thể phụ thuộc quyền user, Developer Mode, policy và filesystem.

`Files.createSymbolicLink()` hoặc `Files.readSymbolicLink()` có thể thất bại nếu provider không hỗ trợ hoặc user không có quyền. Nếu ứng dụng cần link, hãy kiểm tra capability và xử lý exception thay vì giả định luôn tạo được.

### File đang mở, rename và delete

Hành vi với file đang mở có thể khác giữa OS và filesystem. Trên Windows, rename/delete có thể thất bại nếu process khác đang giữ handle với sharing mode không cho phép. Trên Linux, file có thể bị unlink khỏi directory trong khi process vẫn giữ file descriptor đang mở; dữ liệu chỉ được giải phóng khi handle cuối cùng đóng.

Vì vậy:

- Đóng stream trước khi rename hoặc delete file.
- Dùng try-with-resources cho stream, channel và file lock.
- Không viết test giả định mọi OS đều cho phép xóa file đang mở.
- Với file lock, xử lý `OverlappingFileLockException` và `IOException`; đừng dùng file lock thay cho đồng bộ thread trong cùng JVM.

## 6. ProcessBuilder, shell và command line

### ProcessBuilder không tự chạy shell

`ProcessBuilder` tạo process với command và danh sách argument. Nó không tự hiểu cú pháp shell như pipe, redirect, biến môi trường hoặc `&&`.

Cách nên dùng:

```java
Process process = new ProcessBuilder(
    "java",
    "-version"
).redirectErrorStream(true).start();

int exitCode = process.waitFor();
```

Truyền mỗi argument thành một phần tử riêng. Không nối toàn bộ command thành chuỗi rồi tự quote; quy tắc tokenize của Windows command interpreter khác shell Linux.

Nếu thực sự cần shell syntax, gọi shell tường minh:

```java
// Windows
new ProcessBuilder("cmd.exe", "/c", "dir").start();

// Linux
new ProcessBuilder("sh", "-c", "ls -la").start();
```

Chỉ dùng shell khi cần pipe, glob, redirect hoặc shell built-in. Nếu có dữ liệu từ user, tránh nối dữ liệu đó vào shell command; ưu tiên gọi executable trực tiếp với argument list để giảm command injection.

### Environment variables

| Mục đích | Windows thường gặp | Linux thường gặp |
| --- | --- | --- |
| Home directory | `USERPROFILE` | `HOME` |
| Temporary directory | `TEMP`, `TMP` | `TMPDIR` |
| Executable search path | `Path` hoặc `PATH` | `PATH` |
| Shell | `ComSpec` | `SHELL` |

Dùng `System.getProperty("user.home")` và `System.getProperty("java.io.tmpdir")` cho các nhu cầu Java tương ứng. Không giả định tên environment variable giống nhau. `ProcessBuilder.environment()` cung cấp map phụ thuộc hệ thống và thường case-sensitive trong Java API, kể cả khi OS xử lý tên biến theo cách khác.

Ví dụ truyền environment variable cho child process:

```java
ProcessBuilder builder = new ProcessBuilder("java", "-version");
builder.environment().put("APP_MODE", "test");
builder.directory(Path.of(System.getProperty("user.dir")).toFile());

Process process = builder.start();
```

Biến `APP_MODE` sẽ có trong environment của process con. Shell expansion như `$HOME` hoặc `%USERPROFILE%` không tự diễn ra khi dùng `ProcessBuilder` trực tiếp.

### Tìm executable và script wrapper

Executable có thể có tên hoặc extension khác nhau. Java trên Windows thường là `java.exe`, còn Linux là `java`. Với build tool, dùng wrapper của project đáng tin cậy hơn dựa vào Gradle/Maven cài toàn cục.

```bash
# Linux/macOS
./gradlew clean test
./mvnw --batch-mode verify
```

```powershell
# Windows PowerShell
.\gradlew.bat clean test
.\mvnw.cmd --batch-mode verify
```

Nếu tạo process từ Java, chọn wrapper phù hợp với OS hoặc gọi Java executable qua đường dẫn từ `java.home`. Đặt working directory rõ ràng. Không hardcode `C:\\Program Files\\...` hoặc `/usr/bin/...` nếu tool có thể tìm qua PATH hoặc wrapper.

## 7. Locale, timezone và tên hệ điều hành

Ứng dụng có thể chạy trên cả hai OS nhưng cho kết quả khác do locale hoặc timezone mặc định.

- Dùng `Locale.ROOT` khi chuẩn hóa identifier, key hoặc chuỗi kỹ thuật không phụ thuộc ngôn ngữ.
- Chọn locale rõ ràng khi format tiền, ngày và số cho người dùng.
- Dùng `Instant` để lưu thời điểm tuyệt đối; dùng `ZoneId` rõ ràng khi hiển thị theo vùng.
- Không giả định timezone của Windows runner và Linux container giống nhau.
- Không dùng chuỗi ngày giờ đã format theo locale làm khóa hoặc dữ liệu máy đọc.

Nếu phải rẽ nhánh theo OS, có thể kiểm tra `System.getProperty("os.name")` và `os.arch`. Dùng `Locale.ROOT` khi chuyển thành chữ thường. Tránh kiểm tra chuỗi quá rộng như `contains("win")`, vì tên `Darwin` cũng chứa `win`.

Chỉ rẽ nhánh theo OS khi thực sự cần gọi script/native tool hoặc dùng tính năng đặc thù. Với file, path và permission, ưu tiên hỏi filesystem provider có hỗ trợ capability tương ứng không.

## 8. Native library và kiến trúc CPU

Java bytecode có tính portable, nhưng JNI/JNA hoặc thư viện native phụ thuộc OS và kiến trúc:

| Nền tảng | Native library thường gặp |
| --- | --- |
| Windows | `.dll` |
| Linux | `.so` |
| macOS | `.dylib` |

Ngoài OS, cần khớp CPU architecture như `amd64`/`x86_64` hoặc `aarch64`/`arm64`. Native binary sai OS hoặc sai kiến trúc có thể gây `UnsatisfiedLinkError` dù Java source biên dịch thành công.

Thực hành:

1. Phát hành native binary riêng cho từng OS/architecture.
2. Đặt resource theo convention rõ ràng, ví dụ `native/windows-x86_64/`.
3. Kiểm tra `os.name` và `os.arch` trước khi chọn binary.
4. Xử lý trường hợp không có binary tương ứng bằng thông báo rõ ràng.
5. Không ghi đè native library đang được process sử dụng.
6. Kiểm tra dependency native gián tiếp, không chỉ file JNI chính.

## 9. Process termination và shutdown

Trên Linux, process thường nhận signal như SIGTERM khi service manager yêu cầu dừng; SIGKILL buộc dừng process và không cho ứng dụng cleanup. Windows có cơ chế process termination và console control event khác POSIX signals.

Java có `Process.destroy()`, `destroyForcibly()` và shutdown hook, nhưng chi tiết gửi tín hiệu và chờ process kết thúc phụ thuộc implementation/platform. Shutdown hook chỉ chạy khi JVM đi qua quá trình shutdown có trật tự; không thể dựa vào hook khi process bị kill cưỡng bức, máy mất điện hoặc runtime crash.

Với service:

- Ngừng nhận request mới khi bắt đầu graceful shutdown.
- Hoàn tất hoặc timeout các request đang chạy.
- Flush và đóng resource.
- Đặt timeout tổng thể để service manager không phải chờ vô hạn.
- Ghi dữ liệu quan trọng an toàn trong quá trình xử lý bình thường, không chỉ ở shutdown hook.

## 10. Ví dụ thực hành Java 17+: kiểm tra môi trường và chạy process con

Ví dụ kiểm tra thuộc tính filesystem, charset và line ending, sau đó dùng `ProcessBuilder` chạy một class Java con. Argument có dấu cách được truyền như một argument duy nhất; environment variable được truyền sang process con.

Tệp `src/PlatformProbe.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Comparator;
import java.util.Locale;
import java.util.stream.Stream;

public final class PlatformProbe {
    private PlatformProbe() {
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        String osName = System.getProperty("os.name");
        boolean windows = osName.toLowerCase(Locale.ROOT).startsWith("windows");

        System.out.println("os.name=" + osName);
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("file.separator=" + java.io.File.separator);
        System.out.println("path.separator=" + java.io.File.pathSeparator);
        System.out.println("default.charset=" + Charset.defaultCharset().name());
        System.out.println("line.separator=" +
            System.lineSeparator().replace("\r", "CR").replace("\n", "LF"));

        Path report = Path.of("build", "reports", "daily", "test report.txt");
        System.out.println("portable.path=" + report);
        System.out.println("absolute.path.isAbsolute=" +
            report.toAbsolutePath().isAbsolute());

        Path tempDir = Files.createTempDirectory("platform-probe-");
        try {
            Path text = tempDir.resolve("Readme.txt");
            Files.writeString(
                text,
                "Tiếng Việt — café — 東京",
                StandardCharsets.UTF_8
            );

            System.out.println("utf8.roundtrip=" +
                Files.readString(text, StandardCharsets.UTF_8));
            System.out.println("case.variant.exists=" +
                Files.exists(tempDir.resolve("README.txt")));
            System.out.println("posix.attributes.available=" +
                (Files.getFileAttributeView(
                    text, PosixFileAttributeView.class) != null));
            System.out.println("file.executable=" + Files.isExecutable(text));
        } finally {
            try (Stream<Path> paths = Files.walk(tempDir)) {
                paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException error) {
                        throw new UncheckedIOException(error);
                    }
                });
            }
        }

        Path java = Path.of(
            System.getProperty("java.home"),
            "bin",
            windows ? "java.exe" : "java"
        );

        ProcessBuilder builder = new ProcessBuilder(
            java.toString(),
            "-cp",
            System.getProperty("java.class.path"),
            "EchoArgs",
            "two words"
        );
        builder.directory(Path.of(System.getProperty("user.dir")).toFile());
        builder.environment().put("APP_MODE", "test");
        builder.redirectErrorStream(true);

        Process process = builder.start();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                    process.getInputStream(), StandardCharsets.UTF_8))) {
            reader.lines().forEach(line ->
                System.out.println("child=" + line));
        }
        System.out.println("child.exit=" + process.waitFor());
    }
}

final class EchoArgs {
    public static void main(String[] args) {
        System.out.println("argument.count=" + args.length);
        System.out.println("argument.0=" + args[0]);
        System.out.println("env.APP_MODE=" + System.getenv("APP_MODE"));
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 -g -d out src/PlatformProbe.java
java -cp out PlatformProbe
```

`--release 17` kiểm soát API/source compatibility; class có thể chạy trên JDK mới hơn. `-encoding UTF-8` xác định encoding source. Ví dụ dùng Java API thay cho việc nối path, dùng charset rõ ràng và truyền process argument bằng list.

### Output đã kiểm tra trên Windows 11, JDK 24.0.2

```text
os.name=Windows 11
os.arch=amd64
file.separator=\
path.separator=;
default.charset=UTF-8
line.separator=CRLF
portable.path=build\reports\daily\test report.txt
absolute.path.isAbsolute=true
utf8.roundtrip=Tiếng Việt — café — 東京
case.variant.exists=true
posix.attributes.available=false
file.executable=true
child=argument.count=1
child=argument.0=two words
child=env.APP_MODE=test
child.exit=0
```

Một số dòng sẽ khác trên Linux:

- `file.separator` thường là `/`; `path.separator` thường là `:`.
- `line.separator` thường là `LF`.
- Filesystem Linux phổ biến phân biệt hoa/thường, nên `case.variant.exists` thường là `false` nếu chỉ tạo `Readme.txt`.
- POSIX attribute view thường có trên filesystem Linux; vẫn kiểm tra vì provider hoặc mount có thể không hỗ trợ.
- `file.executable` phụ thuộc permission và filesystem; không suy ra POSIX execute bit chỉ từ giá trị này.

Chương trình đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy thành công trên Windows 11/JDK 24.0.2. Môi trường kiểm thử này không có Linux shell hoạt động, vì vậy các giá trị Linux ở trên được mô tả theo tài liệu API/OS, không phải kết quả chạy trực tiếp trên Linux trong lần kiểm thử này.

## 11. Cross-platform CI: kiểm tra cả Windows và Linux

Một build chỉ chạy trên máy developer không đủ để phát hiện sai case, permission, script line ending hoặc path. Nên có CI matrix cho các OS mà sản phẩm hỗ trợ.

Ví dụ GitHub Actions cho Gradle, tệp `.github/workflows/cross-platform.yml`:

```yaml
name: Java Cross-platform CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        java: ['17', '21', '25']

    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Test on Linux
        if: runner.os == 'Linux'
        run: ./gradlew --no-daemon clean check

      - name: Test on Windows
        if: runner.os == 'Windows'
        run: .\gradlew.bat --no-daemon clean check

      - name: Upload test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: test-reports-${{ matrix.os }}-jdk-${{ matrix.java }}
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
          if-no-files-found: ignore
```

Với Maven, giữ cùng matrix nhưng thay cache thành `maven` và gọi wrapper tương ứng:

```yaml
- name: Test on Linux
  if: runner.os == 'Linux'
  run: ./mvnw --batch-mode --no-transfer-progress clean verify

- name: Test on Windows
  if: runner.os == 'Windows'
  run: .\mvnw.cmd --batch-mode --no-transfer-progress clean verify
```

Ma trận tạo sáu job: hai OS nhân ba JDK. Điều chỉnh theo support policy; không cần test mọi tổ hợp nếu chi phí quá lớn. Có thể chạy một JDK baseline trên cả OS ở mỗi pull request và chạy matrix rộng hơn theo lịch hoặc trước release.

Khi build chạy trong container Linux trên Windows host, container vẫn dùng Linux semantics cho filesystem và process bên trong container. Một job Docker trên Windows không thay thế test trực tiếp trên Windows runner nếu sản phẩm hỗ trợ Windows.

## 12. Các lỗi thường gặp khi chuyển giữa Windows và Linux

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `FileNotFoundException` chỉ trên Linux | Sai chữ hoa/thường trong path hoặc resource | Kiểm tra chính xác tên file, package và resource |
| Script báo `bad interpreter` | Shell script có CRLF hoặc shebang trỏ tới shell không tồn tại | Đặt `*.sh text eol=lf`, kiểm tra shebang |
| `gradlew: Permission denied` | Thiếu executable bit trong checkout Linux | `chmod +x gradlew`; commit mode executable |
| Windows không tạo được file | Tên chứa ký tự reserved hoặc tên thiết bị | Dùng tên portable, tránh `CON`, `NUL`, `COM1`... |
| Classpath không hoạt động | Dùng `:` trên Windows hoặc `;` trên Linux | Dùng build tool hoặc `File.pathSeparator` |
| Tiếng Việt bị lỗi | Encoding source/file/terminal không đồng nhất | Dùng UTF-8 rõ ràng; kiểm tra console charset |
| Test fail do line ending | Test giả định chỉ có LF hoặc CRLF | Chuẩn hóa Git và đọc text theo dòng |
| Không set được POSIX permission trên Windows | Filesystem provider không hỗ trợ POSIX view | Kiểm tra attribute view và dùng API phù hợp |
| Process không khởi động | Sai executable, extension hoặc working directory | Dùng wrapper theo OS, kiểm tra PATH và working directory |
| Argument có dấu cách bị tách | Tự nối command thành chuỗi và quote sai | Dùng argument list trong `ProcessBuilder` |
| Test xóa file thất bại trên Windows | Stream/process khác vẫn giữ handle | Đóng resource trước khi rename/delete |
| Native library không load | Sai extension, OS hoặc CPU architecture | Phát hành binary riêng cho từng nền tảng |
| Build khác nhau do locale/timezone | Dùng default locale/timezone | Dùng `Locale.ROOT`, `ZoneId` và `Instant` |
| Wrapper chạy local nhưng không chạy CI | Gọi sai wrapper hoặc checkout mất file mode | Dùng `gradlew.bat`/`gradlew`, `mvnw.cmd`/`mvnw` đúng OS |

## 13. Checklist trước khi phát hành cross-platform

1. Tất cả path được tạo bằng `Path`, `resolve` hoặc API filesystem.
2. Không có hardcoded drive letter, `/home/...` hoặc separator.
3. Tên file, package, class và resource khớp case.
4. Không có tên file Windows reserved hoặc path quá dài ngoài policy hỗ trợ.
5. Source và text resource dùng encoding đã xác định.
6. `.gitattributes` quy định line ending cho shell, batch và text files.
7. Wrapper có executable bit trên Linux và wrapper Windows được giữ trong Git.
8. Không gọi shell syntax qua `ProcessBuilder` nếu chưa chọn shell rõ ràng.
9. Process arguments, working directory và environment được cấu hình tường minh.
10. Code kiểm tra capability của POSIX/ACL/symlink thay vì giả định.
11. Native library có artifact đúng OS và CPU architecture.
12. Locale, timezone và console encoding không bị giả định.
13. CI chạy trên Windows và Linux với JDK theo support matrix.
14. Test report được giữ lại khi job thất bại.
15. Integration test không phụ thuộc service, file hoặc port dùng chung giữa các job.

## 14. Ghi nhớ

- JVM portable không làm cho mọi API hệ điều hành giống nhau; filesystem, process, shell và native code vẫn khác biệt.
- `File.separator` là separator giữa thành phần path; `File.pathSeparator` là delimiter của path list.
- Dùng `Path.of`, `resolve` và `Files` thay vì nối chuỗi đường dẫn.
- Windows thường case-insensitive theo mặc định; Linux filesystem phổ biến case-sensitive, nhưng cấu hình filesystem có thể thay đổi hành vi.
- Windows có reserved filename và ký tự không hợp lệ; dùng tên portable.
- Git `.gitattributes` giúp thống nhất LF/CRLF giữa contributor.
- JDK 18+ mặc định UTF-8 cho Java SE API; với JDK 17 và dữ liệu liên hệ thống, hãy chỉ rõ charset.
- POSIX permission view không có trên mọi filesystem; Windows chủ yếu dùng ACL.
- `ProcessBuilder` không tự gọi shell; truyền argument thành danh sách và gọi đúng wrapper theo OS.
- Home, temp và working directory nên lấy từ Java system properties.
- Native library cần khớp OS và CPU architecture.
- Kiểm thử trên Windows và Linux trong CI giúp phát hiện sớm lỗi portability.

Phát triển Java đa nền tảng hiệu quả bằng cách xác định rõ contract của file, encoding, process và build; dùng API chuẩn để xử lý khác biệt; rồi xác nhận hành vi trên từng OS trong CI. Khi các giả định được kiểm tra tự động, ứng dụng sẽ dễ build, debug và phát hành hơn trên Windows lẫn Linux.

## Tài liệu tham khảo

- [Java SE 24: Path API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Path.html)
- [Java SE 24: Files API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 24: ProcessBuilder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java SE 24: PosixFileAttributeView](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [Oracle JDK 24 Migration Guide: Default Charset and JEP 400](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Microsoft: Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
- [Microsoft: Case Sensitivity in Windows and WSL](https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity)
- [Debian Reference: GNU/Linux File Basics](https://www.debian.org/doc/manuals/debian-reference/ch01.en.html)
- [Git: gitattributes and End-of-line Conversion](https://git-scm.com/docs/gitattributes)
