# Lỗi không tìm thấy javac: kiểm tra JDK, JAVA_HOME và PATH

**Lỗi không tìm thấy javac** xuất hiện khi shell, IDE hoặc build runner không tìm được Java compiler tại vị trí mà môi trường hiện tại đang tra cứu. Trên Windows, thông báo thường là “javac is not recognized as the name of a cmdlet” hoặc “not recognized as an internal or external command”. Trên Linux/macOS, thường là “javac: command not found”.

javac là trình biên dịch Java, nằm trong thư mục bin của JDK. Máy có thể chạy được java -version nhưng vẫn không có javac trên PATH: runtime có thể được cài riêng, JDK có thể chưa được thêm vào PATH, hoặc PATH đang trỏ tới một bản Java khác.

Cách chẩn đoán hiệu quả là kiểm tra ba điều theo thứ tự: JDK có thật sự được cài không, file compiler có tồn tại trong JDK đó không, và shell hiện tại có tìm đúng file đó không.

## 1. Phân biệt java và javac

| Lệnh | Chức năng | Dùng khi |
|---|---|---|
| java | Khởi chạy JVM để chạy ứng dụng/class/JAR | Chạy chương trình Java |
| javac | Biên dịch source .java thành bytecode .class | Phát triển và build source Java |
| jar | Tạo, xem hoặc thao tác với Java archive | Đóng gói JAR |
| jshell | REPL tương tác cho Java | Thử biểu thức và đoạn code nhỏ |

Một JDK đầy đủ có compiler javac trong thư mục bin. Một runtime-only package hoặc custom runtime image có thể chỉ chứa các thành phần để chạy ứng dụng. Vì vậy, hai lệnh dưới đây trả lời hai câu hỏi khác nhau:

~~~bash
java -version
javac -version
~~~

Nếu java -version thành công nhưng javac -version thất bại, chưa thể kết luận Java đã được cài đầy đủ cho việc phát triển.

javac thuộc module jdk.compiler. Một custom runtime image được tạo bằng jlink có thể bỏ module này để giảm kích thước; image như vậy có thể chạy ứng dụng nhưng không cung cấp compiler. Oracle mô tả jdk.compiler là module triển khai system Java compiler và command-line tool javac.

## 2. Hiểu JAVA_HOME và PATH

JAVA_HOME nên trỏ tới **thư mục gốc của JDK**. PATH cần chứa thư mục bin bên trong JDK để shell tìm thấy javac.

Ví dụ trên Windows:

~~~text
JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17
PATH=...;%JAVA_HOME%\bin;...
~~~

Ví dụ trên Linux:

~~~text
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
PATH=...:$JAVA_HOME/bin:...
~~~

Ví dụ trên macOS:

~~~text
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
PATH=...:$JAVA_HOME/bin:...
~~~

Không đặt JAVA_HOME thành đường dẫn tới bin, javac.exe hoặc java.exe. Đặt đúng thư mục gốc giúp Maven, Gradle, IDE và các công cụ Java tự tìm các thành phần trong JDK.

PATH là danh sách thư mục mà hệ điều hành/shell tìm executable. Windows phân tách các mục bằng dấu chấm phẩy; Linux và macOS phân tách bằng dấu hai chấm. Khi có nhiều JDK, mục xuất hiện trước có thể quyết định phiên bản javac được gọi.

JAVA_HOME tự nó không khiến shell tìm được lệnh javac. Công cụ đọc JAVA_HOME có thể dùng biến này trực tiếp; còn khi gõ javac, shell vẫn cần tìm thấy JAVA_HOME/bin trong PATH hoặc bạn phải gọi compiler bằng đường dẫn đầy đủ.

## 3. Chẩn đoán nhanh trước khi thay đổi cấu hình

Ghi nhận cả phiên bản Java runtime lẫn compiler:

~~~bash
java -version
javac -version
~~~

Tiếp theo, xác định executable mà shell đang chọn.

Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command javac -All
where.exe javac
where.exe java
~~~

Windows cmd.exe:

~~~bat
echo %JAVA_HOME%
where javac
where java
~~~

Linux/macOS:

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v javac
type -a javac
command -v java
type -a java
~~~

Trên PowerShell, where là alias của Where-Object trong nhiều phiên bản; dùng where.exe để gọi tiện ích tìm file của Windows. Get-Command javac -All còn giúp phát hiện alias, function hoặc executable trùng tên.

Nếu lệnh tra cứu trả về nhiều đường dẫn, kiểm tra từng đường dẫn và thứ tự ưu tiên. Mục tiêu là java và javac cùng thuộc JDK mà dự án yêu cầu.

## 4. Kiểm tra file compiler bên trong JDK

Nếu đã có JAVA_HOME, kiểm tra file thực tế trước khi sửa PATH.

PowerShell:

~~~powershell
$javacPath = Join-Path $env:JAVA_HOME 'bin\javac.exe'
Test-Path $javacPath
& $javacPath -version
~~~

cmd.exe:

~~~bat
if exist "%JAVA_HOME%\bin\javac.exe" (
  "%JAVA_HOME%\bin\javac.exe" -version
) else (
  echo javac.exe was not found under JAVA_HOME
)
~~~

Linux/macOS:

~~~bash
test -x "$JAVA_HOME/bin/javac" && "$JAVA_HOME/bin/javac" -version
ls -l "$JAVA_HOME/bin/javac"
~~~

Nếu file tồn tại và gọi bằng đường dẫn đầy đủ thành công, compiler đã được cài. Vấn đề thường nằm ở PATH, shell session hoặc thứ tự các JDK.

Nếu file không tồn tại, kiểm tra lại JAVA_HOME. Nếu đường dẫn đúng nhưng bin/javac vẫn không có, package đang dùng có thể là runtime-only hoặc custom runtime image. Hãy cài một JDK đầy đủ.

## 5. Sửa tạm thời trên Windows PowerShell

Để kiểm tra nhanh trong cửa sổ PowerShell hiện tại, đặt JAVA_HOME tới thư mục JDK thực tế rồi thêm bin lên đầu PATH:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
Get-Command javac -All
~~~

Thay đường dẫn mẫu bằng thư mục JDK đã cài trên máy. Dùng dấu nháy quanh giá trị khi gán để PowerShell giữ nguyên dấu cách trong path.

Cấu hình này chỉ tác động tới PowerShell hiện tại và tiến trình con được khởi chạy từ đó. Khi đóng cửa sổ, thay đổi phiên này mất đi. Đây là cách tốt để xác nhận nguyên nhân trước khi sửa cấu hình lâu dài.

## 6. Sửa lâu dài trên Windows 10/11

1. Mở Start và tìm Edit the system environment variables.
2. Chọn Environment Variables.
3. Tạo hoặc sửa biến JAVA_HOME trong User variables hoặc System variables.
4. Đặt giá trị là thư mục gốc JDK, ví dụ C:\Program Files\Eclipse Adoptium\jdk-17.
5. Chọn biến Path, bấm Edit và thêm %JAVA_HOME%\bin.
6. Đặt mục JDK mong muốn trước các đường dẫn Java cũ nếu có nhiều bản cài.
7. Xác nhận các hộp thoại và mở terminal mới.

Kiểm tra trong terminal mới:

~~~powershell
$env:JAVA_HOME
where.exe javac
where.exe java
javac -version
java -version
~~~

Nếu dùng cmd.exe:

~~~bat
echo %JAVA_HOME%
where javac
javac -version
java -version
~~~

Đóng và mở lại terminal sau khi thay đổi Environment Variables vì tiến trình mới kế thừa environment khi được khởi chạy. IDE đã mở trước khi sửa PATH cũng có thể giữ environment cũ; khởi động lại IDE rồi kiểm tra lại terminal tích hợp.

Không nên dùng setx PATH "%PATH%;..." một cách tùy tiện để sửa PATH. Cách đó có thể tạo mục trùng, lưu giá trị đã mở rộng hoặc làm mất phần PATH trong một số môi trường Windows. Dùng giao diện Environment Variables để chỉnh sửa lâu dài và giữ nguyên các mục hiện có.

## 7. Cài JDK trên Windows khi máy chỉ có runtime

Nếu JAVA_HOME\bin\javac.exe không tồn tại, cài một JDK từ nhà cung cấp đáng tin cậy, chẳng hạn Eclipse Temurin, Oracle JDK, Microsoft Build of OpenJDK hoặc Azul Zulu.

Chọn đúng:

- Phiên bản Java mà dự án yêu cầu, ví dụ 17 hoặc 21.
- Kiến trúc máy, thường là x64 hoặc ARM64.
- Gói JDK, có compiler và development tools.
- Nhà cung cấp và bản cập nhật phù hợp với chính sách dự án.

Sau khi cài, xác định thư mục cài thực tế. Oracle JDK trên Windows thường cài dưới C:\Program Files\Java\jdk-<FEATURE>; các nhà cung cấp khác có thể dùng thư mục riêng. Đặt JAVA_HOME trỏ tới đúng thư mục đó rồi thêm bin vào PATH.

Không cần gỡ một runtime cũ chỉ để cài JDK. Nếu có nhiều bản Java, dùng where.exe java và where.exe javac để xem bản nào được chọn trước.

## 8. Sửa trên Linux

Trước tiên xác định shell và executable đang được dùng:

~~~bash
echo "$SHELL"
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v javac || echo "javac is not on PATH"
type -a javac
ls -ld "$JAVA_HOME" "$JAVA_HOME/bin" 2>/dev/null
~~~

Nếu JDK đã có nhưng PATH thiếu bin, thử sửa trong terminal hiện tại:

~~~bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Đường dẫn /usr/lib/jvm/java-17-openjdk-amd64 là ví dụ thường gặp trên Ubuntu/Debian x86-64; tên thư mục phụ thuộc distro, kiến trúc và nhà cung cấp. Hãy xác định thư mục thực tế trước khi gán.

Trên Bash, cấu hình lâu dài thường nằm trong ~/.bashrc cho interactive shell hoặc ~/.profile cho login environment. Thêm hai dòng export phù hợp vào file mà terminal của bạn đọc, rồi nạp lại:

~~~bash
source ~/.bashrc
~~~

Nếu bạn dùng login shell và đã đặt biến trong ~/.profile, mở phiên đăng nhập mới hoặc nạp file tương ứng. Với Zsh, kiểm tra ~/.zprofile và ~/.zshrc theo cách terminal khởi động shell.

## 9. Cài JDK trên Ubuntu/Debian

Để cài OpenJDK 17 development kit:

~~~bash
sudo apt update
sudo apt install openjdk-17-jdk
~~~

Gói openjdk-17-jdk cung cấp bộ công cụ phát triển, gồm javac. Gói runtime-only như openjdk-17-jre được thiết kế để chạy Java và có thể không chứa compiler.

Kiểm tra:

~~~bash
javac -version
java -version
command -v javac
readlink -f "$(command -v javac)"
~~~

Nếu máy có nhiều phiên bản OpenJDK, Debian/Ubuntu có thể quản lý lựa chọn bằng update-alternatives:

~~~bash
sudo update-alternatives --display javac
sudo update-alternatives --config javac
sudo update-alternatives --display java
~~~

Chọn compiler và runtime tương ứng với phiên bản dự án. update-alternatives là cơ chế của các hệ thống Debian/Ubuntu; distro khác có thể dùng package manager hoặc công cụ quản lý phiên bản riêng.

## 10. Sửa trên macOS

Oracle JDK thường được cài dưới:

~~~text
/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
~~~

Để xem các JDK đã cài:

~~~bash
/usr/libexec/java_home -V
~~~

Chọn JDK 17 cho terminal hiện tại:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
command -v javac
~~~

/usr/libexec/java_home giúp chọn JDK theo phiên bản và trả về đường dẫn home thực tế. Nếu lệnh báo không tìm thấy JDK 17, hãy cài JDK 17 trước hoặc chọn phiên bản đã được cài.

Muốn cấu hình lâu dài cho Zsh, có thể thêm các dòng export vào ~/.zprofile (login shell) hoặc file startup phù hợp với terminal đang dùng. Sau đó mở terminal mới và xác minh lại. Trên macOS Intel và Apple Silicon, hãy tải đúng gói JDK cho kiến trúc tương ứng.

## 11. Chọn đúng JDK khi có nhiều phiên bản

Khi máy có Java 8, 11, 17 và 21, việc cài nhiều JDK không tự động đảm bảo shell đang dùng phiên bản bạn muốn.

Windows:

~~~powershell
where.exe java
where.exe javac
$env:JAVA_HOME
Get-Command javac -All
~~~

Linux:

~~~bash
type -a java
type -a javac
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
~~~

macOS:

~~~bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
~~~

So sánh đường dẫn thực tế của java và javac. Nếu hai lệnh trỏ tới các JDK khác nhau, sắp xếp lại PATH hoặc chọn JDK rõ ràng bằng JAVA_HOME.

Trên Bash, shell có thể lưu cache đường dẫn executable đã tìm được. Sau khi thay PATH, chạy:

~~~bash
hash -r
command -v javac
~~~

Với Zsh, có thể dùng rehash. Nếu vẫn thấy đường dẫn cũ, mở terminal mới và kiểm tra các file startup có thêm PATH khác hay không.

## 12. javac tồn tại nhưng terminal vẫn báo không tìm thấy

Trường hợp này thường do một trong các nguyên nhân sau:

- PATH đang chứa JAVA_HOME thay vì JAVA_HOME/bin.
- PATH chứa đường dẫn bin của một runtime-only package.
- PATH có JDK cũ hoặc thư mục shim đứng trước JDK đúng.
- Biến JAVA_HOME có dấu nháy literal hoặc trỏ nhầm vào bin.
- Terminal/IDE đã mở trước khi biến môi trường được cập nhật.
- Shell alias/function hoặc command cache che khuất executable thật.
- Đường dẫn cài đặt có ký tự hoặc dấu cách nhưng bị ghép sai trong script.

Gọi compiler bằng đường dẫn đầy đủ để phân biệt lỗi PATH với lỗi cài đặt:

PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\javac.exe" -version
~~~

Bash/Zsh:

~~~bash
"$JAVA_HOME/bin/javac" -version
~~~

Nếu gọi trực tiếp thành công, sửa PATH và khởi tạo lại shell. Nếu gọi trực tiếp cũng thất bại, kiểm tra file tồn tại, quyền thực thi, symlink và loại JDK đang cài.

## 13. java chạy được nhưng javac không có

Đây là một dấu hiệu phổ biến khi máy chỉ cài runtime hoặc đang dùng một runtime image được tối giản.

Kiểm tra runtime đang dùng:

~~~bash
java -version
java --list-modules
~~~

Tìm module compiler:

Windows PowerShell:

~~~powershell
java --list-modules | Select-String '^jdk.compiler@'
~~~

Linux/macOS:

~~~bash
java --list-modules | grep '^jdk.compiler@'
~~~

Nếu jdk.compiler không có trong image, image đó không cung cấp system compiler. Điều này thường gặp ở runtime image do jlink tạo với danh sách module tối thiểu hoặc container image chỉ phục vụ chạy ứng dụng.

Hãy dùng JDK đầy đủ trong môi trường build. Với ứng dụng production, có thể tiếp tục dùng runtime image nhỏ gọn sau khi đã biên dịch và đóng gói artifact ở build stage.

## 14. Kiểm tra JDK có thật sự đầy đủ không

Thư mục JDK thường có các thành phần như:

~~~text
jdk/
├── bin/
│   ├── java
│   ├── javac
│   ├── jar
│   └── javadoc
├── conf/
├── include/
├── jmods/
└── lib/
~~~

Tên file executable trên Windows thường có phần mở rộng .exe. Một số runtime image không có đủ các thư mục hoặc launcher giống JDK đầy đủ.

Có thể kiểm tra nhanh:

PowerShell:

~~~powershell
Get-ChildItem "$env:JAVA_HOME\bin\javac*"
Test-Path "$env:JAVA_HOME\jmods\jdk.compiler.jmod"
~~~

Linux/macOS:

~~~bash
ls -l "$JAVA_HOME/bin/javac"
test -f "$JAVA_HOME/jmods/jdk.compiler.jmod" && echo "Compiler module file exists"
~~~

Không dùng riêng sự tồn tại của jmods làm tiêu chí duy nhất: package tùy biến có thể phân phối module theo cách khác. Bằng chứng trực tiếp tốt nhất là gọi đúng bin/javac -version và biên dịch một file Java thử.

## 15. Kiểm tra trong IDE

Terminal bên ngoài có thể tìm được javac trong khi IDE vẫn báo thiếu compiler, hoặc ngược lại. IDE có thể dùng JDK riêng cho project và build tool.

Kiểm tra:

- Project SDK/JDK của workspace.
- JDK mà Maven runner sử dụng.
- Gradle JVM hoặc Java toolchain của Gradle.
- JDK được cấu hình trong VS Code Java extension.
- Environment của IDE được kế thừa tại thời điểm IDE khởi động.

Trong IntelliJ IDEA, kiểm tra Project Structure để xem Project SDK; với Gradle, kiểm tra Gradle JVM; với Maven, kiểm tra JRE của Maven runner. Các cấu hình này có thể độc lập với terminal PATH.

Trong VS Code, kiểm tra Java runtime được cấu hình cho workspace và terminal tích hợp. Sau khi cài JDK hoặc đổi PATH, khởi động lại IDE nếu process IDE vẫn giữ environment cũ.

## 16. Kiểm tra Maven và Gradle

Maven Wrapper và Gradle Wrapper giúp chọn phiên bản build tool của dự án. Wrapper không tự biến một runtime-only installation thành JDK có compiler.

Kiểm tra Maven:

~~~bash
mvn -version
./mvnw --version
~~~

Trên Windows:

~~~powershell
mvn -version
.\mvnw.cmd --version
~~~

Thông tin Maven hiển thị Java version và Java home mà Maven đang dùng. Nếu khác JDK mong muốn, kiểm tra JAVA_HOME, PATH hoặc cấu hình Maven Toolchains.

Kiểm tra Gradle:

~~~bash
gradle --version
./gradlew --version
./gradlew javaToolchains
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
~~~

Gradle có thể dùng JVM để chạy Gradle daemon và một Java toolchain riêng cho compile task. Nếu build khai báo toolchain, kiểm tra phiên bản JDK được cài và cách resolver của dự án tìm toolchain.

## 17. Cấu hình JDK trong GitHub Actions

CI runner cần một JDK có compiler trước khi chạy compile task. Dùng actions/setup-java để cài JDK, đặt JAVA_HOME và thêm JDK vào PATH:

~~~yaml
name: Java compile check

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  compile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Set up JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Verify compiler
        run: |
          java -version
          javac -version

      - name: Compile and test
        run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Với Gradle, thay bước cuối bằng:

~~~yaml
      - name: Compile and test
        run: ./gradlew --no-daemon clean build
~~~

Nếu chạy trên Windows runner, dùng .\mvnw.cmd hoặc .\gradlew.bat. setup-java có trách nhiệm cài JDK và cập nhật environment của job; cache Maven/Gradle chỉ giúp tải dependency nhanh hơn, không thay thế JDK.

## 18. JDK trong Docker và container

Một container build cần compiler. Nếu Dockerfile dùng runtime-only base image, lệnh javac sẽ không tồn tại.

Ví dụ multi-stage build:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /app
COPY HelloJavac.java .
RUN javac --release 17 HelloJavac.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/HelloJavac.class .
CMD ["java", "HelloJavac"]
~~~

Build stage sử dụng JDK để biên dịch. Runtime stage chỉ cần môi trường chạy class đã biên dịch. Đây là mẫu phù hợp khi muốn image triển khai nhỏ hơn.

Nếu build diễn ra bên trong container, cài JDK trong container build. JDK trên máy host không tự xuất hiện trong container vì mỗi container có filesystem và PATH riêng.

## 19. Khác biệt giữa lỗi javac và lỗi source/classpath

Không phải mọi lỗi có chữ Java đều có nghĩa là compiler không được tìm thấy.

| Thông báo | Ý nghĩa | Hướng kiểm tra |
|---|---|---|
| javac: command not found | Shell không tìm thấy compiler | JDK, PATH, JAVA_HOME |
| javac is not recognized | Windows không phân giải được lệnh | JDK bin, PATH, terminal mới |
| error: file not found: Hello.java | Compiler đã chạy nhưng không tìm thấy source | Thư mục hiện tại và tên file |
| package ... does not exist | Thiếu dependency hoặc source/module path | Classpath/module path |
| cannot find symbol | Không phân giải được class, method hoặc field | Source, dependency, import, generated source |
| invalid source release: 17 | Compiler quá cũ so với release yêu cầu | javac -version, PATH order |
| Could not find or load main class | JVM không tìm được class khi chạy | Classpath, package, working directory |
| java is not recognized | Runtime launcher không có trên PATH | JDK/JRE và PATH |

Nếu javac -version đã chạy, chuyển sang kiểm tra file source, classpath, module path và phiên bản compiler. Không cài lại JDK chỉ vì một lỗi file not found hoặc cannot find symbol.

## 20. Lỗi invalid source release sau khi đã tìm thấy javac

Ví dụ dự án cần Java 17 nhưng shell đang gọi compiler Java 8 hoặc Java 11:

~~~bash
javac --release 17 HelloJavac.java
~~~

Nếu compiler không hỗ trợ release 17, lệnh sẽ báo lỗi dù javac tồn tại.

Kiểm tra:

~~~bash
javac -version
java -version
command -v javac
command -v java
~~~

Trên Windows dùng where.exe javac và where.exe java. Đặt JDK 17 hoặc mới hơn lên đầu PATH, rồi mở terminal mới. Nếu Maven/Gradle dùng toolchain, kiểm tra JDK được chọn cho compile task thay vì chỉ xem java -version của terminal.

## 21. Quy trình xác minh sau khi sửa PATH

Sau khi cấu hình, thực hiện theo thứ tự:

1. Mở terminal mới.
2. In JAVA_HOME.
3. Xác định đường dẫn java và javac.
4. Chạy java -version và javac -version.
5. Gọi javac bằng đường dẫn đầy đủ một lần.
6. Biên dịch source Java 17 thử nghiệm.
7. Chạy class vừa tạo.
8. Chạy lại Maven/Gradle build nếu lỗi xuất hiện trong dự án.

Đừng chỉ dựa vào một giá trị JAVA_HOME nhìn có vẻ đúng. Phải xác nhận executable được chọn và chương trình thực sự biên dịch được source.

## 22. Ví dụ Java 17+ để kiểm tra compiler

Tạo file HelloJavac.java:

~~~java
public final class HelloJavac {
    public static void main(String[] args) {
        System.out.println("JAVAC_OK release=17");
    }
}
~~~

Biên dịch và chạy trên Bash, Linux, macOS hoặc PowerShell:

~~~bash
mkdir -p "out classes"
javac --release 17 -d "out classes" HelloJavac.java
java -cp "out classes" HelloJavac
~~~

PowerShell có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force 'out classes' | Out-Null
javac --release 17 -d 'out classes' .\HelloJavac.java
java -cp 'out classes' HelloJavac
~~~

Trong cmd.exe:

~~~bat
if not exist "out classes" mkdir "out classes"
javac --release 17 -d "out classes" HelloJavac.java
if errorlevel 1 exit /b 1
java -cp "out classes" HelloJavac
~~~

Output chính xác:

~~~text
JAVAC_OK release=17
~~~

Lệnh --release 17 yêu cầu compiler kiểm tra source, bytecode target và Java SE API theo Java 17. Tùy chọn này có từ JDK 9; ví dụ cần JDK 17 trở lên.

## 23. Khi gọi javac bằng đường dẫn tuyệt đối

Nếu PATH vẫn chưa được sửa, bạn có thể xác minh hoặc chạy compiler bằng đường dẫn đầy đủ.

PowerShell:

~~~powershell
$javac = Join-Path $env:JAVA_HOME 'bin\javac.exe'
& $javac --release 17 -d 'out classes' .\HelloJavac.java
~~~

Bash/Zsh:

~~~bash
"$JAVA_HOME/bin/javac" --release 17 -d "out classes" HelloJavac.java
~~~

Cách này hữu ích để kiểm tra một JDK cụ thể hoặc script build cần chọn rõ compiler. Tuy nhiên, các công cụ như Maven, Gradle, IDE và script khác vẫn có thể dùng JDK từ JAVA_HOME, PATH hoặc toolchain riêng; hãy cấu hình môi trường nhất quán cho toàn bộ build.

## 24. Lỗi quyền thực thi, symlink và kiến trúc

Nếu file javac tồn tại nhưng gọi không chạy, thông báo có thể là Permission denied, No such file or directory, Exec format error hoặc lỗi khởi chạy DLL.

Trên Linux/macOS:

~~~bash
ls -l "$JAVA_HOME/bin/javac"
file "$JAVA_HOME/bin/javac"
readlink -f "$JAVA_HOME/bin/javac"
~~~

Kiểm tra quyền execute và symlink có trỏ tới file tồn tại hay không. Không dùng chmod bừa bãi cho toàn bộ JDK; nếu package bị hỏng hoặc thiếu file, cài lại JDK từ nguồn chính thức.

Trên Windows, kiểm tra file javac.exe, kiến trúc JDK và kiến trúc hệ điều hành. Nếu cài nhầm package hoặc file bị antivirus/quản trị thiết bị cách ly, sửa installation theo chính sách máy.

## 25. Các nguyên nhân hay bị bỏ sót trong CI và môi trường nhóm

- JDK được cài trên máy developer nhưng không có trong runner.
- Build container dùng runtime image thay cho JDK image.
- Job cài Java sau bước compile.
- JAVA_HOME của runner trỏ tới bản Java khác với PATH.
- Matrix build chọn runtime version khác với compiler toolchain.
- Self-hosted runner có PATH cũ từ service account.
- IDE và terminal dùng hai JDK khác nhau.
- Custom jlink image bỏ jdk.compiler.
- Wrapper được commit đầy đủ nhưng môi trường chạy wrapper không có JDK tương thích.

Trong pipeline, in java -version, javac -version, mvn -version hoặc gradle --version ngay trước bước build. Những dòng này giúp xác định môi trường thực tế của job khi build thất bại.

## 26. Checklist xử lý lỗi javac không tìm thấy

- Xác nhận thông báo là lỗi tìm compiler, không phải lỗi source hoặc classpath.
- Chạy java -version và javac -version riêng biệt.
- Kiểm tra JAVA_HOME trỏ tới thư mục gốc JDK.
- Xác nhận JAVA_HOME/bin/javac hoặc JAVA_HOME\bin\javac.exe tồn tại.
- Gọi compiler bằng đường dẫn đầy đủ để kiểm tra installation.
- Thêm JDK bin vào PATH với đúng separator của hệ điều hành.
- Kiểm tra thứ tự nhiều JDK và executable trùng tên.
- Mở terminal/IDE mới sau khi sửa environment.
- Kiểm tra Project SDK, Maven runner JDK và Gradle JVM.
- Cài JDK development package nếu chỉ có runtime.
- Kiểm tra module jdk.compiler nếu đang dùng custom runtime image.
- Chạy ví dụ HelloJavac với --release 17.
- Xác minh lại trong chính CI runner hoặc container đang build.

Khi đã tìm đúng JDK và compiler, lỗi javac không tìm thấy sẽ biến mất. Việc ghi nhận cả JAVA_HOME, đường dẫn executable, phiên bản compiler và kết quả compile giúp nhóm phát hiện sớm khi một máy developer, IDE hoặc CI runner sử dụng môi trường Java khác dự kiến.

## Tài liệu tham khảo

- Oracle JDK 26 — [The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html).
- Oracle JDK 26 — [JDK Installation Guide](https://docs.oracle.com/en/java/javase/26/install/index.html).
- Oracle JDK 26 — [Installation of the JDK on Windows](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-microsoft-windows-platforms.html).
- Oracle JDK 26 — [Installation of the JDK on macOS](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-macos.html).
- Oracle Java SE 26 — [jdk.compiler Module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/module-summary.html).
- Microsoft Learn — [Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java/).
- Microsoft Learn — [PATH command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/path).
- Microsoft Learn — [where command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/where).
- Ubuntu for Developers — [Set up a Java development environment](https://ubuntu.com/developers/docs/howto/java-setup/).
- GitHub — [actions/setup-java](https://github.com/actions/setup-java).
