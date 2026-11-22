# Lỗi không tìm thấy java

Lỗi **không tìm thấy lệnh `java`** xuất hiện khi hệ điều hành không tìm được chương trình Java trong môi trường hiện tại. Nguyên nhân thường là JDK/JRE chưa được cài, thư mục `bin` của Java chưa có trong `PATH`, hoặc terminal/IDE/service đang dùng biến môi trường cũ.

Cần xác định đúng tầng đang lỗi trước khi sửa. Lệnh `java` dùng để chạy chương trình; `javac` là compiler nằm trong JDK. Máy có thể chạy Java nhưng không biên dịch được nếu chỉ có runtime hoặc PATH chưa trỏ tới JDK.

## 1. Nhận diện thông báo lỗi

Các hệ điều hành thường hiển thị thông báo khác nhau:

| Thông báo | Ý nghĩa thường gặp |
|---|---|
| Linux/macOS: `java: command not found` | Shell không tìm thấy executable tên `java` trong PATH |
| PowerShell: `'java' is not recognized as the name of a cmdlet...` | PATH hiện tại không tìm thấy `java.exe` |
| Command Prompt: `'java' is not recognized as an internal or external command...` | Windows không tìm thấy Java executable |
| macOS: `Unable to locate a Java Runtime` hoặc thông báo không có runtime | Java launcher của macOS không tìm thấy runtime phù hợp |
| `javac: command not found` trong khi `java -version` chạy được | Runtime có thể đã cài, nhưng compiler của JDK chưa có trong PATH hoặc chỉ có JRE |
| `java -version` chạy nhưng hiện phiên bản cũ | Có nhiều Java installation; PATH đang ưu tiên bản khác |

Đừng nhầm lỗi tìm executable với lỗi chạy ứng dụng:

| Thông báo | Tầng lỗi |
|---|---|
| `java: command not found` | Không tìm thấy Java launcher |
| `Could not find or load main class` | Java launcher đã chạy; class hoặc classpath không đúng |
| `NoClassDefFoundError` | Thiếu class/dependency trong lúc chạy |
| `UnsupportedClassVersionError` | Runtime đang dùng cũ hơn phiên bản bytecode mà chương trình yêu cầu |
| `Permission denied` khi chạy file Java | Quyền thực thi hoặc quyền truy cập file; cần kiểm tra đường dẫn và quyền |

Nếu `java -version` không chạy, hãy xử lý việc cài đặt/PATH trước khi điều tra classpath hoặc source code.

## 2. Hiểu vai trò của PATH và JAVA_HOME

`PATH` là danh sách các thư mục hệ điều hành tìm kiếm khi người dùng gõ tên lệnh. Nếu thư mục chứa `java` không nằm trong PATH, shell không thể tìm thấy lệnh dù file Java đã có trên máy.

`JAVA_HOME` là biến môi trường trỏ tới thư mục gốc của JDK. Nhiều build tool như Maven và Gradle dùng biến này để xác định Java installation.

Với một JDK được cài tại thư mục ví dụ:

~~~text
/opt/jdk-21
~~~

Cấu hình đúng trên Linux/macOS thường có dạng:

~~~sh
export JAVA_HOME="/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Trên Windows, nếu JDK nằm tại:

~~~text
C:\Program Files\Java\jdk-21
~~~

thì:

- `JAVA_HOME` trỏ tới `C:\Program Files\Java\jdk-21`.
- `PATH` có một entry là `%JAVA_HOME%\bin`.

`JAVA_HOME` trỏ tới thư mục gốc JDK, không thêm `bin` và không trỏ trực tiếp vào `java.exe`.

`PATH` cần thư mục `bin` vì `java` và `javac` nằm trong đó. Với ứng dụng chỉ chạy Java, `JAVA_HOME` có thể không bắt buộc nếu PATH đã trỏ đúng; nhưng Maven, Gradle và nhiều công cụ phát triển thường cần biến này.

## 3. Bước chẩn đoán chung trước khi thay đổi cấu hình

Chạy các lệnh phù hợp với shell đang dùng. Mục tiêu là biết Java đã cài chưa, shell đang tìm executable ở đâu và biến môi trường có giá trị gì.

### 3.1. Linux và macOS

~~~sh
java -version
javac -version
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
~~~

Có thể xem tất cả vị trí trùng tên mà shell nhận diện:

~~~sh
type -a java
type -a javac
~~~

Nếu `command -v java` không trả về đường dẫn và `java -version` báo command not found, shell không tìm thấy Java trong PATH.

Nếu `JAVA_HOME` đã có giá trị, kiểm tra installation trực tiếp:

~~~sh
ls -ld "$JAVA_HOME"
ls -l "$JAVA_HOME/bin/java"
ls -l "$JAVA_HOME/bin/javac"
~~~

Nếu file tồn tại, chạy bằng đường dẫn tuyệt đối để tách lỗi PATH khỏi lỗi cài đặt:

~~~sh
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
~~~

Nếu lệnh chạy bằng đường dẫn tuyệt đối nhưng `java` vẫn không tìm thấy, vấn đề nằm ở PATH hoặc shell chưa nạp cấu hình mới.

### 3.2. Windows PowerShell

~~~powershell
java -version
javac -version
Get-Command -All java -ErrorAction SilentlyContinue
Get-Command -All javac -ErrorAction SilentlyContinue
where.exe java
where.exe javac
$env:JAVA_HOME
$env:Path -split ';'
~~~

`where.exe` là chương trình của Windows. Trong PowerShell, `where` thường là alias của `Where-Object`, vì vậy hãy dùng đầy đủ tên `where.exe`.

Nếu `JAVA_HOME` đã được đặt, kiểm tra trực tiếp:

~~~powershell
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
~~~

Nếu đường dẫn tuyệt đối chạy được nhưng `java` không chạy, sửa PATH hoặc mở lại terminal để nhận môi trường mới.

### 3.3. Command Prompt (cmd.exe)

~~~bat
java -version
javac -version
where java
where javac
echo %JAVA_HOME%
echo %PATH%
~~~

Nếu `where java` không trả về đường dẫn, Windows không tìm được Java qua PATH của cửa sổ Command Prompt hiện tại.

## 4. Cách khắc phục trên Windows

### 4.1. Cài JDK nếu máy chưa có

Có thể cài Microsoft Build of OpenJDK 21 bằng Windows Package Manager:

~~~powershell
winget install Microsoft.OpenJDK.21
~~~

Hoặc cài Eclipse Temurin 21:

~~~powershell
winget install EclipseAdoptium.Temurin.21.JDK
~~~

Nếu không dùng `winget`, tải installer từ trang chính thức của vendor và chọn đúng kiến trúc Windows x64 hoặc ARM64.

Sau khi cài, kiểm tra thư mục JDK thực tế. Ví dụ:

~~~text
C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot
~~~

Tên thư mục phụ thuộc phiên bản và vendor; không sao chép nguyên đường dẫn ví dụ nếu nó không tồn tại trên máy.

### 4.2. Đặt JAVA_HOME và PATH lâu dài

1. Mở Start và tìm `Edit the system environment variables`.
2. Chọn **Environment Variables**.
3. Trong User variables hoặc System variables, tạo `JAVA_HOME` nếu chưa có.
4. Đặt giá trị bằng thư mục gốc JDK, ví dụ `C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot`.
5. Chọn biến `Path`, bấm Edit và thêm entry `%JAVA_HOME%\bin`.
6. Đưa entry JDK phù hợp lên trước các entry Java cũ nếu có nhiều bản cài.
7. Lưu thay đổi và mở cửa sổ PowerShell/Command Prompt mới.

Không đặt dấu ngoặc kép bao quanh giá trị từng entry PATH trong cửa sổ Environment Variables. Dùng một entry riêng cho `%JAVA_HOME%\bin`.

### 4.3. Thử ngay trong PowerShell hiện tại

Để kiểm tra trước khi thay đổi cấu hình lâu dài, gán biến trong cửa sổ PowerShell hiện tại. Thay đường dẫn ví dụ bằng JDK thực tế:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
~~~

Cấu hình trong `$env:` chỉ có hiệu lực với process PowerShell hiện tại và các process được mở từ nó. Đóng cửa sổ này sẽ mất thay đổi tạm thời.

Không dùng `setx PATH ...` để ghi lại toàn bộ PATH theo một chuỗi tự ghép. Cách này dễ làm mất entry hiện có hoặc tạo PATH sai. Dùng giao diện Environment Variables để sửa từng entry an toàn hơn.

### 4.4. Nếu Windows vẫn chạy phiên bản Java cũ

Windows tìm executable theo thứ tự các thư mục trong PATH. Nếu có nhiều JDK hoặc shim, entry đứng trước có thể được chọn.

Kiểm tra:

~~~powershell
where.exe java
where.exe javac
Get-Command -All java | Format-Table CommandType, Source, Definition -AutoSize
~~~

Đối chiếu từng đường dẫn với JDK mong muốn. Có thể tồn tại `javapath` của một installer cũ ở trước JDK mới. Sửa thứ tự PATH để JDK mong muốn được ưu tiên, hoặc gỡ bản cài cũ bằng trình uninstall của vendor nếu không còn dùng.

Sau khi sửa PATH, mở terminal mới rồi chạy lại `where.exe java` và `java -version`. Nếu IDE hoặc service đã chạy từ trước, khởi động lại process đó để nó nhận biến môi trường mới.

## 5. Cách khắc phục trên macOS

### 5.1. Kiểm tra JDK đã cài

macOS cung cấp công cụ `/usr/libexec/java_home` để tìm JDK đã cài:

~~~sh
/usr/libexec/java_home -V
java -version
javac -version
command -v java
echo "$JAVA_HOME"
~~~

Nếu `/usr/libexec/java_home -V` không liệt kê JDK nào, hãy cài JDK từ vendor đáng tin cậy. Chọn package đúng kiến trúc: macOS x64 cho Intel hoặc macOS AArch64 cho Apple Silicon.

JDK cài bằng installer thường nằm dưới:

~~~text
/Library/Java/JavaVirtualMachines/jdk-<FEATURE>.jdk/Contents/Home
~~~

### 5.2. Chọn JDK và thiết lập PATH

Ví dụ chọn JDK 21 trong terminal hiện tại:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Nếu `java_home` báo không tìm thấy version 21, kiểm tra lại danh sách JDK bằng `/usr/libexec/java_home -V` và cài đúng version.

Có thể chạy một executable trực tiếp để xác minh:

~~~sh
/usr/libexec/java_home -v 21 --exec java -version
/usr/libexec/java_home -v 21 --exec javac -version
~~~

### 5.3. Lưu cấu hình cho shell

macOS hiện đại thường dùng zsh. Với login shell, cấu hình môi trường thường đặt trong `~/.zprofile`; cấu hình interactive shell thường đặt trong `~/.zshrc`.

Thêm đoạn sau vào file phù hợp với cách terminal được khởi chạy:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Nạp lại file hoặc mở terminal mới:

~~~sh
source ~/.zprofile
java -version
javac -version
~~~

Nếu dùng bash, hãy đặt cấu hình trong file khởi tạo bash phù hợp, thường là `~/.bash_profile` cho login shell hoặc `~/.bashrc` cho interactive shell.

Không xóa các file trong `/usr/bin` để sửa lỗi Java. Cài đặt JDK của macOS nằm trong `/Library/Java/JavaVirtualMachines`; dùng installer hoặc công cụ quản lý JDK để cài/gỡ.

## 6. Cách khắc phục trên Linux

### 6.1. Cài Java từ package manager

Trên Ubuntu/Debian, làm mới danh sách package và cài runtime nếu chỉ cần chạy ứng dụng:

~~~sh
sudo apt update
sudo apt install openjdk-21-jre
~~~

Nếu cần compiler và công cụ phát triển, cài JDK:

~~~sh
sudo apt install openjdk-21-jdk
~~~

Tên package và version có thể khác theo phiên bản distribution và repository đã bật. Kiểm tra package có sẵn trước khi cài:

~~~sh
apt-cache policy openjdk-21-jdk
apt-cache search openjdk
~~~

Trên Fedora hoặc một số distribution họ RHEL:

~~~sh
sudo dnf install java-21-openjdk
~~~

Nếu cần `javac` và development tools, cài package devel tương ứng:

~~~sh
sudo dnf install java-21-openjdk-devel
~~~

Nếu repository không có Java 21, chọn phiên bản được distribution cung cấp hoặc thêm repository/vendor phù hợp theo chính sách máy.

### 6.2. Kiểm tra và chọn Java mặc định

Trên Ubuntu/Debian, xem các lựa chọn đã đăng ký:

~~~sh
sudo update-alternatives --display java
sudo update-alternatives --display javac
~~~

Chọn Java mặc định:

~~~sh
sudo update-alternatives --config java
~~~

Chọn compiler tương ứng nếu có nhiều JDK:

~~~sh
sudo update-alternatives --config javac
~~~

`java` và `javac` là hai nhóm lựa chọn có thể được quản lý riêng. Sau khi chuyển Java, hãy kiểm tra cả runtime lẫn compiler để tránh trường hợp `java -version` và `javac -version` thuộc hai JDK khác nhau.

Trên Fedora/RHEL, công cụ tương đương thường có tên `alternatives`:

~~~sh
sudo alternatives --display java
sudo alternatives --config java
~~~

Lệnh và lựa chọn cụ thể tùy package đã cài. Không tự tạo symbolic link vào `/usr/bin/java` nếu distribution đang quản lý đường dẫn đó bằng alternatives.

### 6.3. Nếu cài JDK từ archive

Nếu tải JDK dạng `.tar.gz` và giải nén vào thư mục người dùng, package có thể không tự đăng ký vào alternatives và PATH.

Ví dụ JDK được giải nén tại `$HOME/opt/jdk-21`:

~~~sh
export JAVA_HOME="$HOME/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Kiểm tra file thực tế:

~~~sh
ls -l "$JAVA_HOME/bin/java"
ls -l "$JAVA_HOME/bin/javac"
"$JAVA_HOME/bin/java" -version
~~~

Nếu chạy trực tiếp được nhưng gõ `java` không chạy, cấu hình PATH đang thiếu `$JAVA_HOME/bin`.

### 6.4. Lưu cấu hình cho shell

Với bash interactive shell, có thể thêm vào `~/.bashrc`; với login shell, kiểm tra `~/.bash_profile` hoặc `~/.profile` tùy distribution.

~~~sh
export JAVA_HOME="$HOME/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Với zsh, dùng `~/.zshrc` hoặc `~/.zprofile` theo loại shell session.

Nạp lại cấu hình:

~~~sh
source ~/.bashrc
java -version
javac -version
~~~

Nếu bash đã ghi nhớ một vị trí lệnh cũ, làm mới command hash:

~~~sh
hash -r
command -v java
~~~

Trong zsh, có thể chạy:

~~~sh
rehash
command -v java
~~~

## 7. Phân biệt lỗi thiếu runtime và thiếu JDK

Một số máy có Java runtime để chạy ứng dụng nhưng không có Java compiler. Khi đó:

~~~sh
java -version
~~~

có thể chạy được, còn:

~~~sh
javac -version
~~~

báo không tìm thấy lệnh.

Nếu chỉ chạy một ứng dụng Java đã được biên dịch, runtime phù hợp có thể đủ. Nếu học Java, biên dịch source, chạy Maven/Gradle build hoặc tạo JAR, hãy cài JDK.

Một JDK thông thường có cả `java` và `javac` trong thư mục `bin`. Kiểm tra trực tiếp:

~~~sh
ls "$JAVA_HOME/bin/java" "$JAVA_HOME/bin/javac"
~~~

Trên Windows:

~~~powershell
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
~~~

Nếu chỉ thiếu `javac`, hãy kiểm tra package đang cài và `JAVA_HOME` trước khi cài thêm runtime lần nữa.

## 8. Những môi trường thường có PATH riêng

### 8.1. WSL và Windows là hai môi trường riêng

Cài JDK trong Windows không tự động cài JDK trong Ubuntu chạy bằng WSL. Mỗi môi trường có filesystem, PATH và package manager riêng.

Trong WSL, kiểm tra:

~~~sh
uname -a
command -v java
java -version
echo "$JAVA_HOME"
~~~

Nếu dùng Linux toolchain trong WSL, cài JDK bằng package manager bên trong WSL và dùng đường dẫn Linux như `/usr/lib/jvm/...`. Không trộn `JAVA_HOME` của Windows với đường dẫn Linux trong cùng một cấu hình build.

### 8.2. Docker container

Java cài trên host không tự xuất hiện bên trong container. Kiểm tra ngay trong container đang chạy:

~~~sh
docker exec -it <container-name> sh
java -version
command -v java
echo "$JAVA_HOME"
~~~

Nếu container thiếu Java, cập nhật base image hoặc Dockerfile. Ví dụ image build dùng JDK:

~~~dockerfile
FROM eclipse-temurin:21-jdk
WORKDIR /app
COPY . .
RUN ./mvnw --batch-mode verify
~~~

Một runtime image có thể chỉ chứa JRE nếu chỉ chạy ứng dụng đã build. Build stage cần compiler nên phải dùng JDK. Hãy kiểm tra đúng container, đúng stage và đúng image tag.

### 8.3. IDE và build tool

Terminal có thể dùng đúng Java trong khi IDE hoặc Maven/Gradle dùng JDK khác. Các ứng dụng desktop có thể khởi chạy với môi trường riêng và không nạp file cấu hình shell của terminal.

Kiểm tra:

- Project SDK hoặc Project Structure trong IntelliJ IDEA.
- Java runtime và Java configuration trong VS Code.
- Gradle JVM được chọn trong IDE.
- Maven importer JDK và Maven runner JDK.
- Run Configuration đang trỏ tới runtime nào.

Với Maven, chạy:

~~~sh
mvn -version
~~~

Với Gradle wrapper:

~~~sh
./gradlew --version
~~~

Hai lệnh cho biết build tool đang dùng Java nào. Nếu terminal `java -version` đúng nhưng Maven/Gradle báo thiếu Java, kiểm tra `JAVA_HOME` và cấu hình JVM riêng của IDE.

### 8.4. Service và CI runner

Service chạy bằng systemd, launchd hoặc Windows Service có thể không đọc cấu hình `.bashrc`, `.zshrc` hay môi trường của terminal đang mở. Hãy khai báo rõ `JAVA_HOME` và đường dẫn executable trong cấu hình service hoặc service manager.

Trong CI, mỗi job có môi trường riêng. Cài/setup JDK trong chính job trước bước build, sau đó in ra:

~~~sh
java -version
javac -version
echo "$JAVA_HOME"
~~~

Trên PowerShell runner:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
where.exe java
~~~

Không lấy kết quả từ terminal trên máy developer để kết luận runner đã có Java. Luôn kiểm tra bên trong đúng runner/container đang chạy job.

## 9. Dùng chương trình Java để xác nhận runtime thực tế

Sau khi `java` đã chạy được, có thể dùng chương trình sau để in version, vendor, kiến trúc và JDK home của process.

Tạo file `JavaRuntimeProbe.java`:

~~~java
public class JavaRuntimeProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~sh
javac --release 17 JavaRuntimeProbe.java
java JavaRuntimeProbe
~~~

Chương trình in ra các property của runtime hiện tại. `java.home` cho biết Java home thực sự mà process đang dùng; `java.version` và `java.vendor` giúp xác định version/vendor; `os.arch` giúp kiểm tra kiến trúc.

Nếu `javac` không tìm thấy nhưng `java` chạy, hãy sửa JDK/PATH trước khi biên dịch chương trình này.

## 10. Bảng xử lý nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| `java: command not found` | `command -v java`, `echo "$PATH"` | Cài JDK/runtime hoặc thêm thư mục bin vào PATH |
| Windows không nhận `java` | `where.exe java`, `$env:Path` | Đặt JAVA_HOME và thêm `%JAVA_HOME%\bin` |
| macOS không tìm thấy runtime | `/usr/libexec/java_home -V` | Cài JDK đúng kiến trúc và chọn version |
| `java` chạy nhưng `javac` không có | Kiểm tra `JAVA_HOME/bin/javac` | Cài JDK hoặc sửa PATH tới JDK |
| Java chạy phiên bản cũ | `type -a java` hoặc `where.exe java` | Sửa thứ tự PATH hoặc chọn JDK mặc định |
| Java chạy ở terminal nhưng không chạy trong IDE | Kiểm tra Project SDK, Maven/Gradle JVM | Chọn đúng JDK trong IDE |
| Java chạy ở host nhưng không chạy trong Docker | Kiểm tra bên trong container | Cập nhật base image/Dockerfile |
| Java chạy ở Windows nhưng không chạy trong WSL | Kiểm tra `command -v java` trong WSL | Cài JDK Linux trong WSL |
| `JAVA_HOME is not defined correctly` | Kiểm tra đường dẫn và thư mục con bin | Đặt JAVA_HOME vào thư mục gốc JDK |
| `Could not find or load main class` | Kiểm tra classpath và tên class | Sửa classpath/working directory; Java launcher đã chạy |
| `UnsupportedClassVersionError` | So sánh compiler và runtime version | Chạy bằng runtime mới hơn hoặc compile với target thấp hơn |
| `Permission denied` | Kiểm tra quyền file và đường dẫn executable | Sửa quyền hoặc gọi đúng executable |

## 11. Quy trình khắc phục theo thứ tự

1. Chạy `java -version` để ghi nhận thông báo chính xác.
2. Dùng `command -v java` trên Linux/macOS hoặc `where.exe java` trên Windows để tìm executable.
3. Kiểm tra `JAVA_HOME` và xác nhận thư mục `bin` có file Java.
4. Nếu JDK/runtime chưa được cài, cài từ vendor hoặc package manager đáng tin cậy.
5. Nếu đã cài, thêm đúng thư mục `bin` vào PATH.
6. Nếu có nhiều JDK, chọn đúng bản và sửa thứ tự PATH hoặc alternatives.
7. Mở terminal mới; khởi động lại IDE/service nếu chúng giữ môi trường cũ.
8. Chạy lại `java -version` và `javac -version`.
9. Chạy `mvn -version` hoặc `./gradlew --version` nếu lỗi xuất hiện trong build tool.
10. Nếu dùng WSL, Docker hoặc CI, kiểm tra bên trong đúng môi trường đó.
11. Nếu Java launcher đã chạy nhưng ứng dụng vẫn lỗi, chuyển sang kiểm tra classpath, runtime version hoặc dependency theo thông báo lỗi cụ thể.

### Checklist

- [ ] Đã xác định thông báo lỗi chính xác và hệ điều hành/shell.
- [ ] Đã kiểm tra `java -version`.
- [ ] Đã kiểm tra executable bằng `command -v`, `where.exe` hoặc `Get-Command`.
- [ ] Đã xác nhận JDK/runtime thực sự tồn tại trên máy.
- [ ] Đã kiểm tra JAVA_HOME trỏ tới thư mục gốc JDK.
- [ ] Đã thêm đúng thư mục bin vào PATH.
- [ ] Đã kiểm tra thứ tự PATH khi có nhiều JDK.
- [ ] Đã phân biệt thiếu runtime với thiếu javac/JDK.
- [ ] Đã mở terminal mới sau khi sửa biến môi trường.
- [ ] Đã kiểm tra IDE, Maven hoặc Gradle nếu lỗi chỉ xảy ra trong công cụ đó.
- [ ] Đã kiểm tra riêng WSL, Docker, service hoặc CI runner nếu đang sử dụng.
- [ ] Đã xác nhận version/vendor thực tế sau khi khắc phục.

Lỗi không tìm thấy Java thường được xử lý bằng cách cài đúng JDK/runtime và bảo đảm thư mục `bin` được đưa vào PATH của đúng môi trường đang chạy lệnh. Kiểm tra lại `java -version`, `javac -version` và `JAVA_HOME` sau khi sửa để xác nhận terminal, IDE và build tool đều đang dùng đúng Java.

## Tài liệu tham khảo

- [Microsoft Learn — Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java)
- [Microsoft Learn — Install the Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/install)
- [Oracle JDK 26 — Installation of the JDK on Linux Platforms](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-linux-platforms.html)
- [Oracle JDK 26 — Installation of the JDK on macOS](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-macos.html)
- [Oracle — How do I set or change the PATH system variable?](https://www.java.com/en/download/help/path.html)
- [Oracle Java Tutorials — PATH and CLASSPATH](https://docs.oracle.com/javase/tutorial/essential/environment/paths.html)