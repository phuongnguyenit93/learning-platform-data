# Khác biệt hệ điều hành: đường dẫn, dấu phân cách và quyền thực thi

Một dự án Java có thể được phát triển trên Windows, Linux và macOS, sau đó được build trên máy lập trình viên, máy chủ CI hoặc container. Mã Java thường có tính di động cao, nhưng các lệnh build, đường dẫn tệp, biến môi trường và quyền truy cập hệ thống lại chịu ảnh hưởng của hệ điều hành.

Ví dụ, cùng một dự án có thể chạy bằng `gradlew.bat` trên Windows và `./gradlew` trên Linux/macOS. Một classpath được viết đúng trên Windows có thể dùng dấu phân cách sai khi chuyển sang Linux. Một script có nội dung hợp lệ vẫn có thể không chạy nếu thiếu quyền execute hoặc dùng line ending không phù hợp.

Hiểu các khác biệt này giúp thiết kế build script có thể chạy ổn định trên nhiều máy và chẩn đoán lỗi môi trường chính xác hơn. Trong chương Môi trường build, cần chú ý bốn nhóm vấn đề: **cách biểu diễn đường dẫn**, **dấu phân cách trong danh sách đường dẫn**, **cách gọi chương trình và biến môi trường**, và **quyền truy cập tệp**.

## 1. Những khác biệt hệ điều hành thường gặp

| Khía cạnh | Windows | Linux | macOS |
|---|---|---|---|
| Dấu phân cách thư mục thông dụng | `\` | `/` | `/` |
| Dấu phân cách phần tử trong `PATH` và Java classpath | `;` | `:` | `:` |
| Đường dẫn tuyệt đối thường có dạng | `C:\work\app` hoặc UNC | `/home/user/app` | `/Users/user/app` |
| Lệnh chạy Gradle Wrapper | `gradlew.bat` | `./gradlew` | `./gradlew` |
| Quyền execute kiểu POSIX | Không dùng bit execute POSIX làm cơ chế chính | Có | Có |
| Phân biệt chữ hoa/thường của tên tệp | Thường không phân biệt trên volume mặc định | Thường phân biệt | Thường không phân biệt trên volume mặc định; có thể cấu hình volume phân biệt |
| Quyền truy cập tệp | ACL và quyền của Windows | Quyền owner/group/other và ACL tùy cấu hình | Quyền POSIX, ACL và cơ chế bảo mật của macOS |

Các mô tả trong bảng là hành vi thường gặp. Windows có thể chạy trong môi trường WSL hoặc volume có đặc tính khác; Linux có thể dùng filesystem không phân biệt hoa/thường; macOS có thể được cài trên volume phân biệt hoa/thường. Không nên suy luận mọi máy trong cùng một hệ điều hành đều có cấu hình filesystem giống nhau.

## 2. Đường dẫn tệp và thư mục

### 2.1. Dấu phân cách thư mục

Trên Windows, đường dẫn thường dùng dấu gạch chéo ngược:

```text
C:\projects\java-demo\src\main\java
```

Trên Linux và macOS, đường dẫn thường dùng dấu gạch chéo xuôi:

```text
/home/user/projects/java-demo/src/main/java
/Users/user/projects/java-demo/src/main/java
```

Windows cũng chấp nhận dấu `/` trong nhiều API và công cụ, nhưng shell và một số chương trình native có quy tắc riêng. Vì vậy, không nên tự nối chuỗi đường dẫn bằng cách chèn một ký tự `\` hoặc `/` cố định.

Trong Java, dùng `Path` và `Paths` để ghép thành phần đường dẫn theo filesystem hiện tại:

```java
import java.nio.file.Path;

Path sourceFile = Path.of(
    "src",
    "main",
    "java",
    "com",
    "example",
    "Application.java"
);

System.out.println(sourceFile);
```

Trên Windows, đường dẫn được hiển thị với dấu phân cách phù hợp, thường là `\`. Trên Linux/macOS, kết quả thường dùng `/`. Mã nguồn không cần tự kiểm tra hệ điều hành để ghép từng đoạn.

Với Java cũ hơn, có thể dùng `Paths.get(...)`:

```java
Path configFile = java.nio.file.Paths.get(
    "config", "application.yml"
);
```

`Path.of(...)` được bổ sung từ Java 11. Nếu dự án cần tương thích Java 8, dùng `Paths.get(...)`.

### 2.2. Đường dẫn tương đối và tuyệt đối

Đường dẫn tuyệt đối mô tả vị trí từ gốc filesystem hoặc một gốc định danh của hệ điều hành. Ví dụ:

```text
Windows: C:\work\java-demo\config\application.yml
Linux:   /home/user/work/java-demo/config/application.yml
macOS:   /Users/user/work/java-demo/config/application.yml
```

Đường dẫn tương đối được diễn giải từ một thư mục gốc nào đó, thường là **working directory** của tiến trình. Ví dụ:

```text
config/application.yml
```

Nếu chương trình chạy từ thư mục gốc dự án, đường dẫn trên có thể trỏ tới `java-demo/config/application.yml`. Nếu tiến trình được khởi chạy từ một thư mục khác, cùng chuỗi đó có thể trỏ tới vị trí khác hoặc không tồn tại.

Trong Java, working directory hiện tại có thể quan sát bằng:

```java
System.out.println(System.getProperty("user.dir"));
```

`user.dir` phản ánh thư mục làm việc của tiến trình. Đường dẫn tương đối không tự động được tính từ vị trí tệp `.java`, vị trí class file hay package của lớp.

Với NIO, có thể chuyển đường dẫn tương đối thành đường dẫn tuyệt đối dựa trên working directory:

```java
Path relative = Path.of("config", "application.yml");
Path absolute = relative.toAbsolutePath().normalize();

System.out.println("Working directory: " + System.getProperty("user.dir"));
System.out.println("Config path: " + absolute);
```

`normalize()` loại bỏ các thành phần dư thừa như `.` và một số cặp `..` theo quy tắc đường dẫn. Nó không nhất thiết truy cập filesystem hoặc xác nhận tệp thật sự tồn tại. Muốn xác nhận, dùng `Files.exists(...)`, `Files.isRegularFile(...)` hoặc thao tác đọc tệp và xử lý ngoại lệ.

### 2.3. Ghép và phân giải đường dẫn bằng `resolve`

Nên ghép từng thành phần bằng API đường dẫn thay vì nối chuỗi:

```java
Path projectRoot = Path.of("workspace", "java-demo");
Path sourceRoot = projectRoot.resolve("src").resolve("main");
Path sourceFile = sourceRoot.resolve(Path.of("java", "com", "example", "App.java"));

System.out.println(sourceFile);
```

`resolve(...)` tạo đường dẫn con từ đường dẫn hiện tại. Nếu đối số truyền vào là một đường dẫn tuyệt đối, nó có thể thay thế đường dẫn gốc trong kết quả. Vì vậy, khi xử lý đầu vào từ người dùng, cần kiểm tra xem đường dẫn có nằm trong vùng được phép hay không; không nên cho rằng `resolve` tự bảo đảm đường dẫn con luôn nằm bên trong thư mục gốc.

Nếu cần kiểm tra một đường dẫn nằm trong thư mục gốc sau khi chuẩn hóa, có thể so sánh quan hệ `startsWith` trên `Path`:

```java
Path root = Path.of("uploads").toAbsolutePath().normalize();
Path candidate = root.resolve("reports", "daily.txt").normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Path is outside the allowed directory");
}
```

Đây là kiểm tra cấu trúc đường dẫn đã chuẩn hóa. Trong tình huống có symlink hoặc filesystem thay đổi đồng thời, cần cân nhắc thêm việc phân giải đường dẫn thực bằng `toRealPath()` và xử lý các vấn đề truy cập tương ứng.

### 2.4. Dấu phân cách trong đường dẫn Java

Java cung cấp các hằng để lấy dấu phân cách của filesystem mặc định:

```java
System.out.println(java.io.File.separator);
System.out.println(java.io.File.separatorChar);
```

Thông thường:

| API | Windows | Linux/macOS | Ý nghĩa |
|---|---|---|---|
| `File.separator` | `\` | `/` | Dấu phân cách thư mục |
| `File.pathSeparator` | `;` | `:` | Dấu phân cách phần tử trong danh sách đường dẫn |

Trong mã Java, ưu tiên `Path` thay vì tự tạo chuỗi bằng `File.separator`. Hai hằng trên hữu ích khi phải giao tiếp với API hoặc định dạng yêu cầu chuỗi đường dẫn.

## 3. Phân biệt các loại dấu phân cách

Một lỗi phổ biến là nhầm dấu phân cách thư mục với dấu phân cách các phần tử trong một danh sách đường dẫn. Đây là hai khái niệm khác nhau.

### 3.1. Dấu phân cách thư mục

Dấu phân cách thư mục nối các thành phần trong cùng một đường dẫn:

```text
Windows: C:\app\lib\example.jar
Linux:   /opt/app/lib/example.jar
```

### 3.2. Dấu phân cách danh sách đường dẫn

Một biến môi trường hoặc tùy chọn classpath có thể chứa nhiều thư mục và JAR. Các phần tử trong danh sách được phân tách theo quy tắc của hệ điều hành:

```text
Windows PATH: C:\Java\jdk\bin;C:\tools\gradle\bin
Linux PATH:   /usr/lib/jvm/java/bin:/usr/local/bin
macOS PATH:   /Library/Java/JavaVirtualMachines/.../bin:/usr/bin
```

Với Java launcher, classpath cũng dùng quy tắc phân tách tương ứng:

```powershell
# Windows PowerShell hoặc Command Prompt
java -cp "build/classes/java/main;lib/*" com.example.App
```

```bash
# Linux/macOS
java -cp "build/classes/java/main:lib/*" com.example.App
```

Trong Java, `File.pathSeparator` trả về dấu phân cách phù hợp nếu cần tự xây dựng danh sách classpath. Tuy nhiên, trong ứng dụng và build script, nên dùng `FileCollection`, `Path`, `ProcessBuilder` hoặc API chuyên dụng thay vì tự nối chuỗi classpath khi có thể.

### 3.3. URL và URI không phải đường dẫn filesystem

URL/URI thường dùng `/` làm dấu phân cách theo cú pháp của chúng, kể cả khi ứng dụng chạy trên Windows:

```text
https://example.com/api/v1/orders
```

Không nên chuyển URL thành đường dẫn filesystem bằng cách thay `/` thành `\`. Ngược lại, cũng không nên dùng `File` hoặc `Path` để xử lý URL như thể đó là tệp cục bộ. Java có các API riêng cho URI, URL và filesystem.

## 4. Biến môi trường và cách gọi lệnh

### 4.1. Cú pháp truy cập biến môi trường theo shell

Tên biến môi trường thường quen thuộc như `JAVA_HOME`, `PATH`, `GRADLE_USER_HOME`, nhưng cú pháp đọc và gán phụ thuộc shell.

| Thao tác | Windows PowerShell | Windows CMD | Linux/macOS shell (bash/zsh) |
|---|---|---|---|
| Đọc `JAVA_HOME` | `$env:JAVA_HOME` | `%JAVA_HOME%` | `$JAVA_HOME` |
| Gán cho phiên hiện tại | `$env:JAVA_HOME = 'C:\Java\jdk-21'` | `set JAVA_HOME=C:\Java\jdk-21` | `export JAVA_HOME=/opt/jdk-21` |
| Nối thêm vào `PATH` | `$env:PATH += ';C:\tools\bin'` | `set PATH=%PATH%;C:\tools\bin` | `export PATH="$PATH:/opt/tools/bin"` |

Các lệnh gán trên chỉ minh họa cho phiên shell hiện tại. Cách cấu hình biến môi trường lâu dài phụ thuộc hệ điều hành, tài khoản và môi trường phát triển. Khi chạy trong CI, nên cấu hình biến qua cơ chế environment/secret của nền tảng CI.

Tên biến môi trường trên Unix thường phân biệt chữ hoa/thường. `JAVA_HOME` và `java_home` có thể là hai biến khác nhau. Windows thông thường xử lý tên biến môi trường không phân biệt chữ hoa/thường. Để tương thích, nên dùng đúng cách viết quy ước, chẳng hạn `JAVA_HOME`.

### 4.2. Working directory khi chạy build

Gradle và Maven thường diễn giải đường dẫn tương đối trong build theo project directory hoặc working directory tùy API được sử dụng. Với lệnh chạy chương trình, working directory của tiến trình cũng có thể ảnh hưởng đến việc tìm file cấu hình, log và dữ liệu.

Ví dụ, hai lệnh sau có thể tạo kết quả khác nếu chạy từ các thư mục khác nhau:

```bash
java -cp build/classes/java/main com.example.App
```

```bash
java -cp ../java-demo/build/classes/java/main com.example.App
```

Khi chẩn đoán, hãy ghi nhận thư mục hiện tại (`pwd` trên Linux/macOS/Git Bash; `Get-Location` trong PowerShell; `cd` trong CMD) và đường dẫn thực tế mà chương trình sử dụng.

### 4.3. Khoảng trắng và ký tự đặc biệt trong đường dẫn

Đường dẫn có thể chứa dấu cách:

```text
C:\Users\Nguyen Van A\projects\java-demo
/home/nguyen van a/projects/java-demo
```

Khi truyền đường dẫn qua shell, cần đặt trong dấu nháy phù hợp:

```powershell
Set-Location "C:\Users\Nguyen Van A\projects\java-demo"
```

```bash
cd "/home/nguyen van a/projects/java-demo"
```

Trong script, phải phân biệt dấu nháy dùng để nhóm một đối số với dấu nháy là một phần của giá trị. Không nên tự ghép một lệnh shell lớn từ chuỗi đầu vào không đáng tin cậy.

Với Java `ProcessBuilder`, truyền mỗi thành phần lệnh như một phần tử riêng để tránh phải tự escape chuỗi theo shell:

```java
import java.nio.file.Path;
import java.util.List;

Path input = Path.of("data files", "orders.json").toAbsolutePath();

List<String> command = List.of(
    "java",
    "-version"
);

Process process = new ProcessBuilder(command)
    .directory(Path.of(".").toAbsolutePath().toFile())
    .inheritIO()
    .start();

int exitCode = process.waitFor();
System.out.println("Exit code: " + exitCode);
```

Ví dụ này minh họa cách truyền danh sách đối số và working directory; biến `input` chỉ để thể hiện cách biểu diễn một đường dẫn có dấu cách và chưa được đưa vào lệnh. Khi gọi công cụ ngoài, cần chọn đúng executable cho hệ điều hành, kiểm tra exit code và xử lý lỗi khởi chạy.

`ProcessBuilder` không tự mở shell để diễn giải `*`, pipe (`|`), chuyển hướng (`>`) hay biến shell. Nếu thực sự cần các tính năng đó, phải gọi shell tương ứng và xử lý quoting/escaping theo đúng shell. Tránh dựa vào shell khi không cần thiết vì cú pháp và hành vi không đồng nhất giữa các hệ điều hành.

## 5. Chạy Gradle Wrapper và Maven Wrapper

Wrapper giúp dự án sử dụng phiên bản build tool được khai báo trong repository. Cách gọi wrapper khác nhau giữa Windows và hệ điều hành Unix-like.

### 5.1. Gradle Wrapper

Các tệp wrapper thường có dạng:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

Trên Linux và macOS:

```bash
./gradlew clean build
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean build
```

Trên Windows CMD:

```bat
gradlew.bat clean build
```

`gradlew` là script dành cho shell Unix-like; `gradlew.bat` là script batch dành cho Windows. Cả hai đều đọc cấu hình wrapper để tải và sử dụng phiên bản Gradle của dự án nếu chưa có trong cache.

### 5.2. Quyền thực thi của `gradlew`

Trên Linux/macOS, một tệp script cần quyền execute để được gọi trực tiếp theo dạng `./gradlew`. Nếu thiếu quyền này, shell có thể báo `Permission denied`.

Có thể cấp quyền bằng:

```bash
chmod +x gradlew
```

Sau đó kiểm tra:

```bash
ls -l gradlew
```

Kết quả thường có ký tự `x` trong nhóm quyền, ví dụ `-rwxr-xr-x`. Bit execute của tệp cũng cần được lưu đúng trong Git để checkout trên Linux/macOS giữ được khả năng chạy wrapper.

Trên Windows, thông thường chạy `gradlew.bat` qua CMD hoặc PowerShell nên không cần bit execute POSIX. Khi dùng Git Bash hoặc WSL, cần phân biệt đang gọi wrapper từ filesystem Windows hay filesystem của môi trường Unix đó.

### 5.3. Maven Wrapper

Maven Wrapper có cách tổ chức tương tự:

```text
mvnw
mvnw.cmd
.mvn/wrapper/
```

Trên Linux/macOS:

```bash
./mvnw clean verify
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd clean verify
```

Trên Windows CMD:

```bat
mvnw.cmd clean verify
```

Nếu `mvnw` không chạy trên Linux/macOS, kiểm tra quyền execute, line ending và nội dung shebang ở đầu script. Nếu `mvnw.cmd` không chạy trên Windows, kiểm tra tên file, working directory và lỗi từ batch script.

## 6. Quyền truy cập tệp và thư mục

### 6.1. Quyền POSIX trên Linux và macOS

Các hệ điều hành Unix-like thường biểu diễn quyền cơ bản theo ba nhóm:

- **Owner:** người sở hữu tệp.
- **Group:** nhóm sở hữu tệp.
- **Others:** những người dùng còn lại.

Mỗi nhóm có thể có quyền đọc (`r`), ghi (`w`) và thực thi (`x`). Ví dụ:

```text
-rwxr-xr-x  gradlew
drwxr-xr-x  src
-rw-r--r--  build.gradle
```

Với tệp thông thường:

- `r`: đọc nội dung tệp.
- `w`: thay đổi nội dung tệp.
- `x`: thực thi tệp nếu định dạng và môi trường cho phép.

Với thư mục:

- `r`: liệt kê tên các mục bên trong, nếu các quyền khác cũng cho phép truy cập.
- `w`: tạo, xóa hoặc đổi tên mục bên trong khi quyền trên thư mục và các điều kiện liên quan cho phép.
- `x`: đi qua/truy cập thư mục (search/traverse) để phân giải đường dẫn bên trong.

Quyền `x` trên thư mục không có nghĩa là chạy thư mục như một chương trình. Nó cho phép tiến trình đi qua thư mục để truy cập các mục con.

Một số lệnh kiểm tra và thay đổi quyền:

```bash
ls -l gradlew
chmod +x gradlew
chmod u+x scripts/build.sh
```

`chmod +x` thêm quyền thực thi theo cách áp dụng cho các nhóm quyền hiện tại. Nếu muốn đặt quyền cụ thể, có thể dùng dạng số như `chmod 755 gradlew`, nhưng cần cân nhắc chính sách bảo mật và quyền mong muốn thay vì mặc định cấp quyền rộng cho mọi tệp.

### 6.2. Quyền trên Windows

Windows thường quản lý quyền bằng Access Control List (ACL), gắn với người dùng và nhóm. Một tiến trình có thể được phép đọc nhưng không được phép ghi vào thư mục, hoặc không được quyền thay đổi một tệp dù tệp đó không có bit execute như trên POSIX.

Các lỗi có thể xuất hiện khi:

- Tài khoản hiện tại không có quyền ghi vào thư mục dự án hoặc thư mục cache.
- Tệp đang bị tiến trình khác giữ theo cách ngăn thao tác sửa/xóa.
- Phần mềm bảo mật hoặc chính sách tổ chức chặn việc chạy executable.
- Build được chạy bằng một tài khoản khác với tài khoản tạo thư mục output.

PowerShell có thể xem ACL bằng `Get-Acl`:

```powershell
Get-Acl .\build | Format-List
```

Không nên mặc định chạy toàn bộ build với quyền Administrator hoặc root chỉ để vượt qua lỗi permission. Hãy xác định chính xác thư mục và tài khoản nào đang thiếu quyền, sau đó sửa quyền ở phạm vi cần thiết.

### 6.3. Quyền ghi vào thư mục build và cache

Build tool thường cần ghi vào:

- Thư mục `build/` của Gradle hoặc `target/` của Maven.
- Thư mục cache của Gradle/Maven trong profile người dùng.
- Thư mục tạm của hệ điều hành.
- Thư mục output được cấu hình riêng trong dự án.

Nếu build chạy trong container hoặc CI, user bên trong container có thể khác chủ sở hữu thư mục được mount từ host. Khi đó, một build chạy tốt trên máy lập trình viên có thể thất bại trong container vì không có quyền ghi.

Nên để build chạy bằng tài khoản có quyền phù hợp trên workspace và cache. Tránh tạo output bằng root rồi tiếp tục build bằng user thường, vì các tệp do root sở hữu có thể gây lỗi ở bước tiếp theo.

## 7. Bit executable và Git

Trên hệ điều hành POSIX, Git có thể lưu trạng thái executable cơ bản của một tệp trong index. Khi xem thay đổi mode, có thể thấy:

```text
100644 -> 100755
```

Trong đó `100644` là tệp thông thường không có bit executable; `100755` là tệp thông thường có bit executable. Vì vậy, một thay đổi quyền của `gradlew` có thể là thay đổi quan trọng dù nội dung script không đổi.

Kiểm tra trạng thái Git:

```bash
git ls-files --stage gradlew
git diff --summary
```

Nếu cần cập nhật executable bit trong Git index:

```bash
git update-index --chmod=+x gradlew
```

Sau đó kiểm tra diff và commit thay đổi cùng với những chỉnh sửa phù hợp. Trên Windows, Git có thể không phản ánh mọi khác biệt permission của filesystem host; cấu hình `core.filemode` ảnh hưởng cách Git phát hiện mode change. Không nên tắt hoặc bật cấu hình này một cách tùy tiện nếu chưa hiểu ảnh hưởng trong môi trường làm việc.

Đối với một script cần chạy trực tiếp trên Linux/macOS, repository nên lưu executable bit đúng. Nếu bit này bị mất, người dùng có thể phải chạy `chmod +x` sau mỗi lần checkout, hoặc không thể chạy wrapper theo hướng dẫn thông thường.

## 8. Line ending và encoding

### 8.1. LF và CRLF

Hai kiểu kết thúc dòng thường gặp:

- **LF (`\n`):** phổ biến trên Linux và macOS.
- **CRLF (`\r\n`):** phổ biến trên Windows.

Phần lớn trình biên tập hiện đại có thể đọc cả hai, nhưng shell script trên Linux/macOS có thể gặp lỗi nếu dùng CRLF không phù hợp. Ví dụ, shebang `#!/bin/sh` có thể bị diễn giải kèm ký tự `\r`, dẫn tới lỗi kiểu `bad interpreter` hoặc không tìm thấy interpreter.

Có thể kiểm tra line ending bằng editor hoặc công cụ phù hợp. Trên Linux, `file gradlew` có thể cung cấp thông tin định dạng; không phải mọi phiên bản công cụ đều hiển thị chi tiết giống nhau.

### 8.2. Chuẩn hóa bằng `.gitattributes`

Repository có thể quy định line ending bằng `.gitattributes`, ví dụ:

```gitattributes
* text=auto
*.sh text eol=lf
gradlew text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
```

Các quy tắc trên yêu cầu Git xử lý tệp văn bản và checkout shell script theo LF, batch script theo CRLF. Dự án có thể điều chỉnh quy tắc theo loại tệp và công cụ đang sử dụng. Sau khi thay đổi `.gitattributes`, cần kiểm tra diff vì Git có thể chuẩn hóa lại nội dung nhiều tệp.

`core.autocrlf` là cấu hình Git thường gặp trên Windows, nhưng `.gitattributes` giúp repository ghi rõ chính sách theo loại tệp. Không nên chỉ dựa vào cấu hình cá nhân của từng lập trình viên để bảo đảm shell script luôn có line ending đúng.

### 8.3. Encoding và Unicode

Tên thư mục hoặc tệp có thể chứa ký tự Unicode. Các hệ điều hành, filesystem và công cụ có thể có cách xử lý/chuẩn hóa tên khác nhau. Để giảm lỗi khi chuyển môi trường, nên ưu tiên tên file source và thư mục ổn định, tránh các tên khác nhau chỉ do cách biểu diễn Unicode hoặc khác biệt hoa/thường.

Đối với nội dung văn bản của dự án Java, nên thống nhất encoding, thường là UTF-8, và cấu hình compiler/build tool tương ứng khi cần. Encoding của nội dung tệp là vấn đề riêng với cách filesystem biểu diễn tên tệp.

## 9. Chữ hoa/thường và tên tệp

Linux thường phân biệt chữ hoa/thường trong tên tệp:

```text
Application.java
application.java
```

Hai tên trên có thể là hai tệp khác nhau. Trên volume Windows mặc định và phần lớn volume macOS mặc định, chúng thường được xem là cùng một tên. Vì vậy, code có thể build trên Windows nhưng thất bại trên Linux nếu import, package hoặc đường dẫn sai chữ hoa/thường.

Ví dụ, tệp thực tế là:

```text
src/main/java/com/example/OrderService.java
```

Nhưng một cấu hình lại tham chiếu:

```text
src/main/java/com/example/orderservice.java
```

Máy Windows có thể vẫn tìm thấy tệp trong một số trường hợp, còn Linux báo không tồn tại. Cần giữ nhất quán tên tệp, tên package và đường dẫn.

Khi đổi tên chỉ khác chữ hoa/thường trên filesystem không phân biệt case, Git hoặc IDE đôi khi không nhận ra thay đổi như mong muốn. Có thể đổi qua một tên trung gian:

```bash
git mv OrderService.java OrderService.tmp
git mv OrderService.tmp orderService.java
```

Sau đó kiểm tra `git status` và diff để bảo đảm Git ghi nhận đúng tên cuối cùng.

Trên Windows, một số ký tự không được phép trong tên tệp, và có các tên thiết bị dành riêng như `CON`, `PRN`, `AUX`, `NUL`, `COM1` hoặc `LPT1`. Tên kết thúc bằng dấu chấm hoặc dấu cách cũng có thể gây vấn đề. Repository muốn dùng trên nhiều hệ điều hành nên tránh các tên đặc thù như vậy.

## 10. Đường dẫn dài, ổ đĩa và symbolic link

Windows có thể sử dụng đường dẫn bắt đầu bằng ký tự ổ đĩa như `C:\`, đường dẫn mạng UNC như `\\server\share\folder`, hoặc các dạng namespace đặc biệt. Hỗ trợ đường dẫn dài phụ thuộc phiên bản Windows, cấu hình hệ thống và khả năng của từng ứng dụng. Một công cụ cũ có thể gặp giới hạn dù filesystem hoặc API mới hỗ trợ đường dẫn dài hơn.

Linux và macOS thường có một cây thư mục bắt đầu từ `/`; thiết bị, volume và thư mục mạng được mount vào cây này. Đường dẫn không có ký tự ổ đĩa theo cách thông thường của Windows.

Các thư mục dự án lồng quá sâu, tên thư mục quá dài hoặc thư mục cache nằm trong một đường dẫn dài có thể làm một số plugin/công cụ thất bại trên Windows. Giữ workspace ở đường dẫn ngắn, dễ đọc thường giúp giảm rủi ro.

Symbolic link (symlink) cũng có thể ảnh hưởng đường dẫn thực tế. Một đường dẫn có vẻ nằm trong workspace có thể trỏ tới vị trí khác. Nếu build tool hoặc chương trình cần xác định vị trí vật lý, hãy dùng API tương ứng như `Path.toRealPath()` và xử lý trường hợp link không tồn tại hoặc không có quyền truy cập.

## 11. Viết build script có tính di động

### 11.1. Dùng API đường dẫn của Gradle

Trong Gradle, dùng `layout.projectDirectory`, `layout.buildDirectory`, `file(...)` hoặc các API `Directory`/`RegularFile` thay vì nối chuỗi đường dẫn theo hệ điều hành.

Ví dụ:

```groovy
plugins {
    id 'java'
}

def schemaFile = layout.projectDirectory.file('src/main/schema/api.yml')
def generatedDir = layout.buildDirectory.dir('generated/sources/api/main')

tasks.register('inspectSchema') {
    inputs.file(schemaFile)
    outputs.dir(generatedDir)

    doLast {
        println "Schema: ${schemaFile.asFile}"
        println "Generated output: ${generatedDir.get().asFile}"
    }
}
```

Các đường dẫn tương đối trong ví dụ được cung cấp dưới dạng thành phần theo quy ước của Gradle; Gradle xử lý chúng theo môi trường chạy. Khi cần thao tác filesystem trong task, lấy `asFile` hoặc dùng API provider tương ứng ở giai đoạn thực thi.

### 11.2. Dùng file collection thay cho chuỗi classpath

Không nên tạo classpath bằng cách tự nối chuỗi có `:` hoặc `;` trong build script. Gradle có `files(...)`, `fileTree(...)` và các dependency configuration để biểu diễn tập hợp tệp.

Ví dụ:

```groovy
def localLibraries = fileTree('libs') {
    include '*.jar'
}

tasks.register('showLibraries') {
    doLast {
        localLibraries.files.each { library ->
            println library
        }
    }
}
```

Khi cấu hình dependency cho Java, nên dùng `dependencies { implementation(...) }`, `runtimeOnly(...)`, `compileOnly(...)` hoặc cấu hình phù hợp thay vì tự xây classpath thủ công. Build tool sẽ xử lý classpath theo nền tảng.

### 11.3. Tránh gọi shell nếu không cần

Một tác vụ build có thể gọi executable trực tiếp bằng API của Gradle hoặc Java. Nếu gọi qua shell, cú pháp có thể phụ thuộc PowerShell, CMD, bash hoặc zsh. Các ký tự như `*`, `$`, `|`, `>` và dấu nháy có thể được shell diễn giải khác nhau.

Khi phải gọi công cụ ngoài, hãy:

1. Chọn executable phù hợp cho hệ điều hành hoặc dùng wrapper của công cụ nếu có.
2. Truyền đối số riêng biệt, không nối thành một dòng lệnh tùy ý.
3. Chỉ định working directory nếu đường dẫn tương đối phụ thuộc vị trí chạy.
4. Kiểm tra exit code và thông báo lỗi.
5. Khai báo input/output để build tool có thể quản lý tác vụ.

### 11.4. Không hard-code vị trí JDK

Tránh giả định JDK luôn nằm ở `C:\Program Files\Java\...` hoặc `/usr/lib/jvm/...`. Vị trí cài đặt khác nhau theo hệ điều hành, package manager, IDE và cấu hình máy.

Có thể dùng `JAVA_HOME`, Gradle Java toolchain hoặc cấu hình JDK của CI để chọn môi trường Java. Với Gradle, Java toolchain giúp khai báo version mong muốn mà không phải hard-code đường dẫn cài đặt của từng máy:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Gradle có thể tìm một JDK phù hợp trên máy hoặc tải toolchain nếu repository/cấu hình cho phép. Điều kiện tải và nguồn JDK phụ thuộc cấu hình toolchain resolver và môi trường mạng.

## 12. Kiểm tra môi trường trên từng hệ điều hành

Khi build thất bại, hãy thu thập thông tin từ đúng shell và đúng máy đang chạy.

### 12.1. Windows PowerShell

```powershell
Get-Location
java -version
javac -version
$env:JAVA_HOME
$env:PATH
Get-ChildItem .\gradlew* 
Get-Acl .\build
```

### 12.2. Linux

```bash
pwd
java -version
javac -version
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
ls -l gradlew
file gradlew
```

### 12.3. macOS

```bash
pwd
java -version
javac -version
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
ls -l gradlew
file gradlew
```

Các lệnh trên kiểm tra working directory, phiên bản Java, biến môi trường và trạng thái wrapper. Lệnh cụ thể có thể khác nếu máy dùng shell khác hoặc không cài đủ công cụ hệ thống.

## 13. Những lỗi thường gặp và cách xác định nguyên nhân

| Thông báo hoặc hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `./gradlew: Permission denied` | Script không có quyền execute hoặc thư mục cha không cho phép truy cập | `ls -l gradlew`, `chmod +x gradlew`, kiểm tra quyền thư mục |
| `bad interpreter: No such file or directory` | Shebang sai, interpreter không tồn tại hoặc script có CRLF không phù hợp | `head -1 gradlew`, `file gradlew`, kiểm tra line ending |
| `gradlew` không được nhận diện trên Windows | Đang gọi sai wrapper hoặc thư mục hiện tại không chứa script | Dùng `./gradlew` trên Unix-like hoặc `gradlew.bat` trên Windows |
| `The system cannot find the path specified` | Đường dẫn Windows sai, working directory không đúng hoặc tệp không tồn tại | `Get-Location`, `Test-Path`, kiểm tra ký tự ổ đĩa và dấu nháy |
| Build chạy trên Windows nhưng lỗi file không tồn tại trên Linux | Khác biệt chữ hoa/thường hoặc đường dẫn hard-code | Kiểm tra tên file thật và mọi tham chiếu tới nó |
| `AccessDeniedException` hoặc `Permission denied` khi ghi output | User không có quyền ghi vào build/cache/temp directory | Kiểm tra owner, ACL, quyền thư mục và user chạy build |
| `CreateProcess error=2` | Không tìm thấy executable hoặc đường dẫn executable sai | Kiểm tra `PATH`, `JAVA_HOME`, executable path và working directory |
| `CreateProcess error=193` trên Windows | Tệp được gọi không phải executable phù hợp hoặc sai định dạng/kiến trúc | Kiểm tra loại tệp, wrapper `.bat` hay binary và kiến trúc |
| Classpath hoạt động trên Windows nhưng lỗi trên Linux | Dùng `;` thay vì `:` hoặc ngược lại | Kiểm tra classpath được tạo bởi build tool và shell |
| Tên file đúng trên Windows nhưng sai trên Linux | Khác biệt case sensitivity | So sánh chính xác chữ hoa/thường trong source và đường dẫn |
| Script chạy trên máy cá nhân nhưng thất bại trong CI | Khác quyền, shell, line ending, biến môi trường hoặc working directory | So sánh OS image, user, env và lệnh CI |

Không nên sửa mọi lỗi bằng cách đổi đường dẫn hoặc cấp quyền rộng hơn ngay lập tức. Trước tiên, xác định lỗi phát sinh ở bước nào: shell không khởi chạy được script, hệ điều hành không tìm thấy tệp, build tool không truy cập được output, hay JVM không tìm thấy class/dependency.

## 14. Kiểm thử tính di động trong CI

Một build chạy thành công trên máy phát triển chỉ chứng minh rằng cấu hình hiện tại hoạt động trong môi trường đó. Để phát hiện phụ thuộc hệ điều hành, nên chạy các tác vụ quan trọng trên nhiều môi trường CI.

Ví dụ ma trận kiểm thử có thể gồm:

| Runner | Hệ điều hành | Lệnh wrapper |
|---|---|---|
| Windows runner | Windows | `gradlew.bat clean build` |
| Linux runner | Ubuntu/Linux | `./gradlew clean build` |
| macOS runner | macOS | `./gradlew clean build` |

Một pipeline thực tế có thể dùng matrix job để chạy cùng lệnh build trên nhiều runner. Nên kiểm tra các điểm dễ khác biệt như:

- Wrapper script có executable bit đúng trong Git.
- Các tệp script có line ending phù hợp.
- Không có đường dẫn tuyệt đối phụ thuộc tài khoản hoặc ổ đĩa của lập trình viên.
- Tên tệp và package thống nhất chữ hoa/thường.
- Build tool quản lý classpath và file collection thay vì chuỗi phân cách hard-code.
- Tác vụ generate và compile có quan hệ đầu vào/đầu ra rõ ràng.
- Build không phụ thuộc vào một biến môi trường chỉ có trên máy cá nhân.
- User của CI có quyền đọc source, ghi output và ghi cache cần thiết.

Nếu một job chỉ thất bại trên một hệ điều hành, hãy giữ lại log và so sánh working directory, shell, Java version, biến môi trường, quyền file và đường dẫn output. Khác biệt nhỏ ở một trong các yếu tố này có thể làm lộ một giả định không di động trong build script.

## 15. Quy trình xử lý một lỗi phụ thuộc hệ điều hành

Khi gặp lỗi build chỉ xuất hiện trên một hệ điều hành, có thể lần theo trình tự sau:

1. **Xác định môi trường thực thi:** OS, shell, user, Java version và build tool version.
2. **Xác định working directory:** kiểm tra lệnh được gọi từ thư mục nào và đường dẫn tương đối được tính từ đâu.
3. **Kiểm tra đường dẫn:** phân biệt dấu phân cách thư mục, dấu phân cách danh sách và URL; kiểm tra chữ hoa/thường, khoảng trắng và ký tự đặc biệt.
4. **Kiểm tra cách gọi chương trình:** dùng đúng wrapper script hoặc executable cho hệ điều hành.
5. **Kiểm tra quyền:** xác nhận script có thể chạy và tiến trình có quyền đọc/ghi thư mục cần thiết.
6. **Kiểm tra line ending và encoding:** đặc biệt với shell script, batch script và tệp cấu hình.
7. **Kiểm tra task graph và output:** xác nhận generator chạy đúng thời điểm, compiler nhìn thấy source và artifact được tạo ở vị trí mong đợi.
8. **Tái hiện trong CI hoặc môi trường tương ứng:** xác nhận thay đổi giải quyết đúng lỗi trên hệ điều hành gặp sự cố.

## 16. Nguyên tắc cần ghi nhớ

- Dùng `Path`/`Paths` trong Java và API đường dẫn của Gradle/Maven thay vì tự nối dấu `\` hoặc `/`.
- Phân biệt dấu phân cách thư mục (`File.separator`) với dấu phân cách phần tử trong classpath/PATH (`File.pathSeparator`).
- Đường dẫn tương đối phụ thuộc working directory của tiến trình; không mặc định nó tính từ vị trí source file.
- Dùng `gradlew.bat` trên Windows và `./gradlew` trên Linux/macOS; Maven Wrapper cũng có script riêng cho từng nền tảng.
- Giữ executable bit của script POSIX trong Git và chuẩn hóa line ending bằng `.gitattributes` khi repository có script đa nền tảng.
- Không giả định filesystem luôn phân biệt hoặc luôn bỏ qua chữ hoa/thường.
- Cấp quyền đúng cho user chạy build, thư mục output và cache; tránh dùng quyền Administrator/root như giải pháp mặc định.
- Dùng Java toolchain và cấu hình môi trường thay vì hard-code đường dẫn cài JDK.
- Kiểm tra build trên các runner tương ứng nếu dự án hỗ trợ nhiều hệ điều hành.

Khả năng build đa nền tảng đến từ việc tách logic dự án khỏi những giả định riêng của máy. Khi đường dẫn được xử lý bằng API phù hợp, task build khai báo rõ input/output, wrapper được gọi đúng, và quyền truy cập được cấu hình chính xác, cùng một dự án Java có thể được build nhất quán trên Windows, Linux và macOS.
