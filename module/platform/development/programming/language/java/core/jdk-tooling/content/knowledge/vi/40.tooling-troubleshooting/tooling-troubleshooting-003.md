# Sửa lỗi JAVA_HOME sai trong Java

JAVA_HOME là biến môi trường chỉ tới thư mục gốc của JDK mà công cụ build hoặc script cần sử dụng. Lỗi JAVA_HOME thường xuất hiện khi biến chưa được đặt, trỏ tới sai thư mục, trỏ vào thư mục bin hoặc file java.exe, trỏ tới JRE không có javac, hoặc trỏ tới một JDK khác với java đang được tìm thấy qua PATH.

Cách xử lý đúng là kiểm tra ba thông tin riêng: giá trị JAVA_HOME, executable java/javac mà shell đang chạy và JDK mà Maven/Gradle/IDE thực sự sử dụng. Chỉ nhìn kết quả java -version chưa đủ để kết luận JAVA_HOME đúng, vì lệnh java có thể đến từ một thư mục khác trong PATH.

Bài này hướng dẫn chẩn đoán và sửa trên Windows, Linux và macOS, xử lý nhiều JDK cùng lúc, kiểm tra Maven/Gradle/IDE/CI, và dùng một chương trình Java nhỏ để xác nhận runtime thực tế.

## 1. JAVA_HOME là gì?

JAVA_HOME là quy ước environment variable được nhiều công cụ Java dùng để tìm JDK. Giá trị của nó phải là đường dẫn tới thư mục gốc cài đặt JDK.

Ví dụ:

~~~text
Windows:
C:\Java\jdk-17

Linux:
/opt/jdk-17

macOS:
/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
~~~

Trong thư mục này thường có các thư mục con như bin, conf, include, jmods và lib. Với một JDK đầy đủ, thư mục bin chứa các công cụ như java, javac, jar, javadoc và jshell.

JAVA_HOME không phải là:

- Đường dẫn tới thư mục bin.
- Đường dẫn trực tiếp tới java.exe hoặc file java.
- Thư mục cài Maven.
- Thư mục project.
- Một JRE chỉ có runtime nếu công việc cần biên dịch source bằng javac.

Nếu JAVA_HOME trỏ tới C:\Java\jdk-17\bin, nhiều công cụ sẽ tự nối thêm bin và tìm nhầm C:\Java\jdk-17\bin\bin. Nếu trỏ tới file java.exe, công cụ cần một thư mục JDK sẽ thất bại.

## 2. Phân biệt JAVA_HOME, PATH và java.home

Ba giá trị này liên quan nhưng không đồng nghĩa:

| Giá trị | Vai trò |
|---|---|
| JAVA_HOME | Đường dẫn JDK được công cụ build ưu tiên theo quy ước |
| PATH | Danh sách thư mục shell tìm executable khi gọi java hoặc javac |
| java.home | System property cho biết thư mục runtime mà JVM đang chạy sử dụng |

Shell không tự động dùng JAVA_HOME để tìm lệnh java. Khi gõ java, shell tra PATH. Một số launcher như Maven kiểm tra JAVA_HOME trước rồi mới tìm java trong PATH.

Vì vậy có thể xảy ra tình huống:

- JAVA_HOME trỏ tới JDK 17.
- PATH tìm thấy java từ JDK 21 trước.
- Gõ java -version hiển thị Java 21.
- Maven lại chạy bằng JDK 17 nếu launcher Maven ưu tiên JAVA_HOME.

Cũng có thể gặp tình huống ngược lại nếu IDE, Gradle daemon hoặc cấu hình toolchain chọn JDK riêng.

java.home là thông tin runtime bên trong JVM. Trên JDK hiện đại, giá trị thường trỏ tới JDK runtime home; với một số layout Java cũ, đặc biệt JDK 8, nó có thể trỏ tới thư mục jre nằm bên trong JDK. Hãy xem đây là bằng chứng về JVM đang chạy, không dùng nó để thay thế kiểm tra JAVA_HOME.

## 3. Triệu chứng thường gặp

Một số lỗi phổ biến:

| Thông báo/triệu chứng | Nguyên nhân có thể |
|---|---|
| The JAVA_HOME environment variable is not defined correctly | Biến chưa đặt, path sai hoặc trỏ tới bin/file |
| JAVA_HOME is set to an invalid directory | Thư mục không tồn tại hoặc không phải JDK home |
| Could not find java in JAVA_HOME | Thiếu bin/java hoặc bin/java.exe |
| javac is not recognized / command not found | PATH thiếu JDK bin hoặc chỉ cài runtime |
| java -version đúng nhưng mvn -version sai | Maven dùng JAVA_HOME, terminal/IDE cũ hoặc launcher khác |
| java và javac hiển thị version khác nhau | PATH chứa nhiều JDK hoặc hai executable đến từ thư mục khác nhau |
| Đổi JAVA_HOME nhưng kết quả không đổi | Shell/IDE/service chưa nhận environment mới hoặc PATH có entry đứng trước |
| Build chạy local nhưng lỗi trong CI | CI runner dùng JDK/path khác hoặc biến không được truyền vào job |

Đọc cả thông báo lỗi và lệnh đã tạo ra lỗi. Maven, Gradle, IDE và ứng dụng chạy trực tiếp có thể chọn JVM theo những cơ chế khác nhau.

## 4. Quy trình chẩn đoán nhanh

Thực hiện theo thứ tự:

1. In giá trị JAVA_HOME trong đúng terminal đang gặp lỗi.
2. Kiểm tra thư mục JAVA_HOME có tồn tại.
3. Kiểm tra trong đó có bin/java và bin/javac.
4. Tìm tất cả java/javac mà PATH có thể chọn.
5. Chạy java -version và javac -version.
6. Chạy mvn -version hoặc gradle --version nếu lỗi xảy ra trong build.
7. Kiểm tra cấu hình JDK riêng của IDE, toolchain hoặc CI.
8. Sửa biến trong đúng scope, mở process mới và kiểm tra lại.

Không sửa biến trước khi biết công cụ nào đang chọn JDK sai. Điều đó giúp tránh thay đổi một môi trường vốn đã đúng.

## 5. Kiểm tra JAVA_HOME trên Windows

Mở PowerShell và chạy:

~~~powershell
Write-Output "JAVA_HOME=$env:JAVA_HOME"

if ([string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
    Write-Output "JAVA_HOME is not set in this process."
}
else {
    Test-Path -LiteralPath $env:JAVA_HOME -PathType Container
    Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe') -PathType Leaf
    Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\javac.exe') -PathType Leaf
}
~~~

Ba kết quả Test-Path cần là True khi dự án yêu cầu một JDK đầy đủ. Nếu dòng đầu là False, kiểm tra xem JAVA_HOME có đang trỏ vào bin hoặc file executable hay không.

Tìm tất cả lệnh java/javac:

~~~powershell
Get-Command java -All | Select-Object CommandType, Source, Definition
Get-Command javac -All | Select-Object CommandType, Source, Definition

where.exe java
where.exe javac
~~~

Get-Command cho biết PowerShell sẽ chọn command nào. where.exe liệt kê các executable được tìm thấy qua PATH. Nếu có nhiều kết quả, entry đầu tiên thường là lệnh được chọn khi gọi java hoặc javac từ PATH.

Kiểm tra version:

~~~powershell
java -version
javac -version
mvn -version
~~~

Kiểm tra executable trực tiếp từ JAVA_HOME, không qua PATH:

~~~powershell
$javaExe = Join-Path $env:JAVA_HOME 'bin\java.exe'
$javacExe = Join-Path $env:JAVA_HOME 'bin\javac.exe'

& $javaExe -version
& $javacExe -version
~~~

Nếu executable trực tiếp từ JAVA_HOME có version đúng nhưng java -version cho kết quả khác, vấn đề nằm ở PATH hoặc shell resolution. Nếu executable trực tiếp không tồn tại, JAVA_HOME đang trỏ sai hoặc JDK chưa được cài đầy đủ.

## 6. Sửa JAVA_HOME tạm thời trên Windows

Để thử một JDK trong terminal hiện tại:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java -version
javac -version
mvn -version
~~~

Thay C:\Java\jdk-17 bằng thư mục JDK thật trên máy. Dùng dấu nháy quanh giá trị để path có khoảng trắng vẫn được giữ nguyên.

Thay đổi bằng $env: chỉ áp dụng cho process PowerShell hiện tại và các process con được khởi chạy từ nó. Đóng terminal sẽ mất thay đổi này. Đây là cách phù hợp để thử trước khi sửa cấu hình lâu dài.

Nếu đã có nhiều Java bin trong PATH, đưa JDK mong muốn lên trước trong terminal hiện tại như ví dụ trên. Kiểm tra lại bằng where.exe java để xác nhận đường dẫn đầu tiên.

## 7. Sửa JAVA_HOME lâu dài trên Windows

Có thể cấu hình qua giao diện Windows:

1. Mở Start và tìm Edit the system environment variables.
2. Chọn Environment Variables.
3. Trong User variables, tạo hoặc sửa JAVA_HOME.
4. Đặt giá trị bằng thư mục gốc JDK, ví dụ C:\Java\jdk-17.
5. Trong Path, thêm %JAVA_HOME%\bin.
6. Kiểm tra các Java bin cũ đứng trước và gây xung đột; điều chỉnh hoặc bỏ entry lỗi thời nếu không còn dùng.
7. Nhấn OK để lưu, đóng terminal và mở terminal mới.
8. Khởi động lại IDE, service hoặc terminal tích hợp đang cần nhận biến mới.

Nếu cần áp dụng cho tất cả user, chỉnh System variables và cần quyền quản trị. User variable chỉ ảnh hưởng tài khoản hiện tại.

Có thể đặt JAVA_HOME cho user hiện tại bằng PowerShell:

~~~powershell
[Environment]::SetEnvironmentVariable(
    'JAVA_HOME',
    'C:\Java\jdk-17',
    'User'
)
~~~

Lệnh trên lưu biến lâu dài cho user nhưng không cập nhật environment của terminal đang mở. Mở process mới để đọc giá trị. Quản lý thứ tự PATH trong Environment Variables để tránh xung đột với Java bin cũ; không ghi đè toàn bộ PATH bằng một lệnh setx PATH.

Trong CMD, cách xem biến là:

~~~cmd
echo %JAVA_HOME%
where java
where javac
~~~

Trong PowerShell dùng $env:JAVA_HOME; cú pháp %JAVA_HOME% là cú pháp mở rộng biến của CMD, không phải PowerShell.

## 8. Kiểm tra và sửa trên Linux

In biến, executable và version:

~~~bash
printf 'JAVA_HOME=%s\n' "${JAVA_HOME:-<unset>}"

if [ -n "${JAVA_HOME:-}" ]; then
  ls -ld "$JAVA_HOME"
  ls -l "$JAVA_HOME/bin/java" "$JAVA_HOME/bin/javac"
fi

command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
mvn -version
~~~

Nếu JAVA_HOME chưa đặt hoặc đang trỏ sai, chọn thư mục JDK thực tế. Ví dụ JDK 17 được cài ở /opt/jdk-17:

~~~bash
export JAVA_HOME="/opt/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Nếu JDK nằm trong /usr/lib/jvm, liệt kê thư mục trước:

~~~bash
ls -1 /usr/lib/jvm
~~~

Trên Debian/Ubuntu, có thể xem các lựa chọn Java:

~~~bash
update-alternatives --list java
update-alternatives --list javac
update-alternatives --config java
update-alternatives --config javac
~~~

Các lệnh --config thay đổi symlink hệ thống và có thể cần quyền sudo. Chỉ dùng khi muốn thay đổi lựa chọn Java mặc định của toàn máy. JAVA_HOME của một shell vẫn có thể trỏ tới JDK khác với symlink mặc định đó.

Trên các bản phân phối dùng alternatives thay cho update-alternatives, tên và tùy chọn có thể khác. Kiểm tra công cụ quản lý package của hệ điều hành trước khi thay đổi.

## 9. Lưu JAVA_HOME trên Linux

Với Bash interactive shell, có thể thêm vào ~/.bashrc:

~~~bash
export JAVA_HOME="/opt/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Sau đó nạp lại:

~~~bash
source ~/.bashrc
~~~

Với Zsh, thường dùng ~/.zshrc. Với login shell, kiểm tra ~/.profile hoặc ~/.bash_profile theo cách shell khởi chạy. Tránh đặt các giá trị mâu thuẫn trong nhiều file khởi tạo vì login shell và interactive shell có thể nạp file khác nhau.

Cấu hình cho mọi user có thể đặt trong file như /etc/profile.d/java.sh, nhưng cần quyền quản trị và phải tuân theo chính sách của máy. Trong container hoặc CI, nên khai báo environment trong image/job definition thay vì phụ thuộc file shell cá nhân.

## 10. Kiểm tra và sửa trên macOS

macOS cung cấp công cụ /usr/libexec/java_home để tìm JDK đã cài:

~~~bash
/usr/libexec/java_home -V
~~~

Lệnh liệt kê các JDK được hệ thống nhận diện. Chọn JDK 17:

~~~bash
/usr/libexec/java_home -v 17
~~~

Đặt cho terminal hiện tại:

~~~bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
mvn -version
~~~

macOS hiện đại thường dùng Zsh. Để lưu cấu hình cho Zsh, đặt các dòng export vào ~/.zshrc hoặc file login phù hợp với cách terminal khởi chạy shell. Mở terminal mới rồi xác minh lại.

Một số JDK cài qua package manager hoặc SDK manager có thể nằm ở vị trí riêng. Dùng /usr/libexec/java_home -V để xem những JDK macOS nhận diện trước khi tự đặt path.

## 11. Xử lý nhiều JDK cùng lúc

Nhiều dự án có thể cần Java 8, 11, 17 hoặc 21. Không nên đổi cứng toàn hệ thống mỗi khi chuyển project.

Một số cách quản lý:

- Dùng SDKMAN! trên Linux/macOS để cài và chọn JDK theo shell/project.
- Dùng jEnv để quản lý version theo user hoặc thư mục project.
- Dùng công cụ quản lý JDK của tổ chức hoặc IDE.
- Dùng Maven Toolchains để chọn compiler JDK riêng theo yêu cầu POM.
- Dùng Gradle Java Toolchains để chọn compiler/test launcher cho project.
- Dùng CI matrix để chạy test trên các runtime được hỗ trợ.

Với Maven, toolchains.xml mô tả các JDK đã cài và Maven Toolchains Plugin/Compiler Plugin chọn JDK phù hợp. Toolchain có thể khác JAVA_HOME của Maven runtime.

Với Gradle, Java toolchain có thể yêu cầu language version, vendor hoặc implementation. Gradle tìm JDK phù hợp đã cài hoặc có thể tự provision nếu cấu hình repository provisioning được bật.

Không đổi JAVA_HOME chỉ để sửa class-file target. JAVA_HOME chọn môi trường runtime/compiler launcher theo công cụ; release/source/target hoặc Java toolchain là cấu hình build riêng.

## 12. JAVA_HOME đúng nhưng java vẫn sai

Nếu JAVA_HOME hợp lệ nhưng java -version vẫn hiển thị JDK khác, kiểm tra PATH:

Windows:

~~~powershell
$env:PATH -split ';'
where.exe java
Get-Command java -All
~~~

Linux/macOS:

~~~bash
printf '%s\n' "$PATH" | tr ':' '\n'
command -v java
type -a java
~~~

Tìm entry JDK cũ đứng trước $JAVA_HOME/bin. Sửa thứ tự PATH hoặc xóa entry không còn sử dụng theo chính sách máy.

Bash và một số shell có thể cache vị trí command. Sau khi sửa PATH, làm mới cache:

~~~bash
hash -r
~~~

Sau đó chạy lại command -v java và java -version. Nếu vẫn sai, mở shell mới để loại trừ environment cũ.

Trên Windows, PowerShell tìm command theo environment process hiện tại. Nếu vừa thay biến lâu dài, terminal đang mở vẫn giữ environment cũ. Mở cửa sổ mới và kiểm tra lại.

## 13. Kiểm tra Maven đang dùng JDK nào

Maven launcher thường ưu tiên JAVA_HOME. Lệnh quan trọng nhất để xác minh Maven runtime là:

~~~powershell
mvn -version
~~~

Hoặc trên Linux/macOS:

~~~bash
mvn -version
~~~

Output có Maven version, Java version, vendor và Java home. Nếu Maven dùng JDK sai:

1. Kiểm tra JAVA_HOME trong chính terminal chạy Maven.
2. Kiểm tra executable Maven đang gọi bằng where.exe mvn hoặc command -v mvn.
3. Chạy mvn -version để xem JVM thực tế.
4. Kiểm tra Maven được IDE khởi chạy có environment khác terminal không.
5. Kiểm tra Maven Toolchains nếu compiler dùng JDK khác runtime Maven.

Maven Toolchains không nhất thiết thay JVM chạy Maven. Ví dụ Maven có thể chạy trên JDK 21 nhưng Compiler Plugin dùng JDK 17. Kiểm tra log toolchain và cấu hình compiler khi cần xác định javac.

MAVEN_HOME là đường dẫn Maven installation, không phải JDK home. Đừng gán JAVA_HOME bằng thư mục Maven hoặc MAVEN_HOME bằng thư mục JDK.

## 14. Kiểm tra Gradle đang dùng JDK nào

Dùng Gradle Wrapper nếu project có:

~~~powershell
.\gradlew.bat --version
~~~

Trên Linux/macOS:

~~~bash
./gradlew --version
~~~

Output hiển thị Gradle version và JVM dùng để chạy Gradle. Gradle daemon có thể giữ JVM đã khởi chạy từ trước; sau khi đổi JDK, dừng daemon:

~~~powershell
.\gradlew.bat --stop
~~~

Hoặc:

~~~bash
./gradlew --stop
~~~

Kiểm tra các cấu hình có thể override:

- org.gradle.java.home trong gradle.properties.
- JAVA_HOME của process chạy Gradle.
- JVM được cấu hình trong IDE.
- Java toolchain trong build.gradle/build.gradle.kts.

Ví dụ toolchain yêu cầu Java 17:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình toolchain điều khiển JDK dùng cho task Java tương ứng. Nó không nhất thiết thay đổi JVM chạy Gradle daemon.

## 15. Kiểm tra JDK trong IDE

IDE có thể lưu JDK riêng, vì vậy terminal đúng chưa bảo đảm project đúng.

Trong IntelliJ IDEA, kiểm tra:

- Project Structure > Project SDK.
- Project language level.
- Settings > Build Tools > Maven > Runner > JRE.
- Settings > Build Tools > Gradle > Gradle JVM.
- JDK được cấu hình cho từng module nếu có.

Trong Eclipse, kiểm tra:

- Installed JREs.
- Execution Environments.
- Java Compiler compliance level.
- JRE System Library của project.

Trong Visual Studio Code, kiểm tra Java runtimes trong Java extension settings và cấu hình build tool của project.

Sau khi đổi JAVA_HOME ở Windows/Linux/macOS, đóng và mở lại IDE để IDE nhận environment mới. Một IDE đã chạy trước khi thay biến có thể tiếp tục truyền environment cũ cho Maven/Gradle process con.

## 16. Kiểm tra trong CI, Docker và service

CI runner có environment riêng. Việc JAVA_HOME đúng trên laptop không chứng minh biến đã được đặt trong workflow.

Trong CI job, in các giá trị cần thiết:

~~~bash
printf 'JAVA_HOME=%s\n' "${JAVA_HOME:-<unset>}"
command -v java
command -v javac
java -version
javac -version
mvn -version
~~~

Không in toàn bộ environment nếu có secret. Chỉ log biến và tool version cần chẩn đoán.

Trong Dockerfile, đặt JAVA_HOME trỏ tới JDK/JRE trong image và thêm bin vào PATH:

~~~dockerfile
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"
~~~

Path thực tế phụ thuộc base image. Kiểm tra image bằng lệnh java -version và test -x "$JAVA_HOME/bin/javac" nếu image cần compiler.

Windows service, scheduled task, IDE service và CI agent có thể chạy dưới user khác. Mỗi user có environment riêng. Khi service không nhận JAVA_HOME mới, kiểm tra account chạy service và restart service sau khi cập nhật environment.

## 17. Path có khoảng trắng, symlink và quyền truy cập

Path JDK có thể chứa khoảng trắng, ví dụ C:\Program Files\Java\jdk-17. Luôn quote path trong shell:

PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
& "$env:JAVA_HOME\bin\java.exe" -version
~~~

Bash:

~~~bash
export JAVA_HOME="/opt/Java Development Kit/jdk-17"
"$JAVA_HOME/bin/java" -version
~~~

Không cắt chuỗi tại dấu cách hoặc tự thêm quote vào chính giá trị JAVA_HOME. Biến nên chứa path thuần; quote khi sử dụng.

Nếu JAVA_HOME là symlink, xác minh đích symlink còn tồn tại và user chạy build có quyền đọc/thực thi. JDK có thể bị gỡ hoặc nâng version khiến symlink cũ trỏ tới thư mục không còn tồn tại.

Trên Linux, có thể xem symlink:

~~~bash
ls -ld "$JAVA_HOME"
readlink "$JAVA_HOME"
~~~

Trên macOS, readlink có thể chỉ hiển thị target tương đối; không giả định tùy chọn readlink -f có sẵn như trên GNU/Linux.

Trên Windows, kiểm tra quyền đọc thư mục và quyền chạy file trong bin. Cũng xác nhận JDK đúng architecture với OS/runner nếu build có native tool hoặc thư viện JNI.

## 18. Chương trình Java kiểm tra runtime thực tế

Tạo file JdkProbe.java:

~~~java
public final class JdkProbe {
    private JdkProbe() {
    }

    public static void main(String[] args) {
        System.out.println("Runtime version: " + Runtime.version());
        System.out.println("Java version: " + System.getProperty("java.version"));
        System.out.println("Java vendor: " + System.getProperty("java.vendor"));
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("OS: " + System.getProperty("os.name"));
        System.out.println("Architecture: " + System.getProperty("os.arch"));
    }
}
~~~

Biên dịch bằng JDK được chọn:

~~~powershell
javac --release 17 -encoding UTF-8 JdkProbe.java
~~~

Chạy:

~~~powershell
java JdkProbe
~~~

Output minh họa khi chạy bằng JDK 17:

~~~text
Runtime version: 17.0.12+7
Java version: 17.0.12
Java vendor: Eclipse Adoptium
Java home: C:\Java\jdk-17
OS: Windows 11
Architecture: amd64
~~~

Giá trị thực tế thay đổi theo JDK, vendor, OS và máy. Chương trình này cho biết JVM đang chạy ứng dụng. Nó không chứng minh executable javac đến từ cùng thư mục; hãy kiểm tra Get-Command/where.exe hoặc command -v và javac -version riêng.

Nếu compile bằng JDK 24 với --release 17, class file vẫn hướng tới Java 17 nhưng runtime output có thể là Java 24. Đây là hai thông tin khác nhau.

## 19. Bảng xử lý lỗi theo triệu chứng

| Triệu chứng | Kiểm tra | Cách sửa |
|---|---|---|
| JAVA_HOME chưa được đặt | echo/Write-Output giá trị biến | Đặt biến trong session hoặc environment settings |
| JAVA_HOME trỏ tới bin | Kiểm tra cấu trúc thư mục | Bỏ phần bin, dùng thư mục JDK root |
| JAVA_HOME trỏ tới java.exe | Test-Path thư mục và file con | Đặt lại thành thư mục chứa bin |
| Thiếu javac | Kiểm tra bin/javac | Cài JDK đầy đủ, không dùng runtime-only |
| java và javac khác version | where/Get-Command/type -a | Sửa PATH để hai lệnh cùng JDK |
| Maven dùng Java khác terminal | mvn -version | Kiểm tra JAVA_HOME và Maven launcher/IDE |
| Gradle dùng Java cũ | gradlew --version, org.gradle.java.home | Sửa cấu hình, dừng daemon và chạy lại |
| IDE dùng JDK cũ | Project SDK, Maven Runner, Gradle JVM | Chọn JDK đúng trong IDE và restart |
| Chỉ lỗi ở CI | In JAVA_HOME, java/javac path, tool versions | Sửa workflow image/variables hoặc service account |
| Đổi biến nhưng không có hiệu lực | Mở shell/process mới, kiểm tra PATH | Restart terminal, IDE, daemon hoặc service |
| Path có dấu cách bị lỗi | Quote biến và path | Dùng path thuần trong biến, quote tại nơi sử dụng |
| Symlink hỏng | ls -ld/readlink hoặc Test-Path | Cập nhật symlink/JAVA_HOME tới JDK hiện có |

## 20. Quy trình sửa an toàn và xác minh sau sửa

Một quy trình sửa có thể lặp lại:

1. Ghi nhận JAVA_HOME hiện tại và output java/javac -version.
2. Xác định JDK cần dùng và thư mục cài đặt thật.
3. Kiểm tra thư mục có bin/java và bin/javac.
4. Đặt JAVA_HOME trỏ tới JDK root.
5. Đưa JAVA_HOME/bin lên trước Java bin cũ trong PATH.
6. Mở terminal mới hoặc reload shell config.
7. Kiểm tra command resolution và version của java/javac.
8. Chạy mvn -version hoặc gradle --version.
9. Kiểm tra toolchain/IDE setting nếu build vẫn chọn JDK khác.
10. Chạy lại build/test trong đúng môi trường ban đầu gây lỗi.

Nếu sửa cho CI, chạy lại đúng job trên runner tương ứng. Nếu sửa cho service, restart service để process mới nhận environment. Không cần đổi system-wide JDK nếu chỉ một project cần JDK riêng; Maven/Gradle toolchain hoặc IDE project SDK thường phù hợp hơn.

## 21. Best practices để tránh lỗi JAVA_HOME

- Đặt JAVA_HOME ở JDK root, không phải bin hoặc file java.
- Dùng JDK đầy đủ khi cần javac, javadoc hoặc công cụ build.
- Đảm bảo PATH không ưu tiên một JDK cũ ngoài ý muốn.
- Quote path có khoảng trắng trong Bash/PowerShell.
- Dùng một nguồn quản lý version JDK nhất quán trong team.
- Pin compiler JDK bằng Maven/Gradle Toolchains nếu dự án cần.
- Dùng Maven Wrapper hoặc Gradle Wrapper.
- Kiểm tra mvn -version/gradle --version trong CI.
- Cấu hình IDE Project SDK và build runner riêng.
- Restart terminal, IDE, daemon hoặc service sau khi đổi environment.
- Không ghi secret vào log khi debug CI.
- Ghi rõ JDK vendor, version và architecture trong tài liệu build.

## 22. Checklist chẩn đoán JAVA_HOME

- [ ] JAVA_HOME đã được đặt trong đúng process/user/service.
- [ ] Giá trị trỏ tới thư mục gốc của JDK.
- [ ] Thư mục JAVA_HOME tồn tại và có quyền truy cập.
- [ ] bin/java hoặc bin/java.exe tồn tại.
- [ ] bin/javac hoặc bin/javac.exe tồn tại nếu cần compile.
- [ ] PATH có JDK bin mong muốn ở vị trí ưu tiên.
- [ ] Get-Command/where.exe hoặc command -v chỉ ra executable đúng.
- [ ] java -version và javac -version hiển thị version mong muốn.
- [ ] mvn -version hoặc gradle --version dùng đúng JVM.
- [ ] Maven/Gradle Toolchains không override ngoài dự kiến.
- [ ] IDE Project SDK, Maven Runner và Gradle JVM đúng.
- [ ] Terminal/IDE/daemon/service đã được mở lại sau khi sửa.
- [ ] CI runner dùng cùng chính sách JDK với dự án.
- [ ] Chương trình JdkProbe xác nhận runtime thực tế khi cần.

JAVA_HOME đúng phải trỏ tới JDK root, còn PATH quyết định shell gọi java/javac nào. Khi xử lý lỗi, kiểm tra riêng biến, executable và runtime của Maven/Gradle/IDE. Sau khi sửa, mở process mới và xác minh lại bằng version, đường dẫn executable và một build thực tế.

## Tài liệu tham khảo

- Oracle Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 17 — The javac Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Apache Maven — Installation: https://maven.apache.org/install.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Gradle — Compatibility and Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Microsoft Learn — Environment Variables: https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables
- Microsoft Learn — PowerShell Environment Variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables
