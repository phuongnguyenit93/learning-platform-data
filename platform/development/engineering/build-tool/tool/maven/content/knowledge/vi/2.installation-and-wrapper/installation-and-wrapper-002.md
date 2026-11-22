# Cài Apache Maven và cấu hình JAVA_HOME, PATH trên Windows, Linux và macOS

## 1. Mục tiêu và nguyên lý

Sau bài này, bạn có thể cài Apache Maven, cấu hình JDK và biến môi trường trên cả ba hệ điều hành, rồi xác nhận lệnh `mvn` chạy với đúng phiên bản Java.

**Maven** là công cụ quản lý dự án và build Java dựa trên `pom.xml`. Lệnh `mvn` cần Java để chạy; khi biên dịch chương trình Java, dự án thường cần **JDK** (có `javac`), không chỉ Java Runtime.

Ba đường dẫn cần phân biệt:

| Thành phần | Trỏ tới đâu? | Ví dụ |
| --- | --- | --- |
| `JAVA_HOME` | Thư mục **gốc của JDK**, nơi có thư mục con `bin` | `C:\Program Files\Java\jdk-21` hoặc `/usr/lib/jvm/java-21-openjdk-amd64` |
| `MAVEN_HOME` | Thư mục **gốc của bản Maven đã giải nén**; tùy chọn, dùng để quản lý đường dẫn thuận tiện | `C:\tools\apache-maven-3.10.0` hoặc `/opt/maven/apache-maven-3.10.0` |
| `PATH` | Danh sách thư mục chứa chương trình được tìm khi gõ lệnh | Bao gồm `JAVA_HOME/bin` và `MAVEN_HOME/bin` (Windows dùng dấu `\`) |

`JAVA_HOME` **không** được trỏ vào `bin`, `java.exe`, thư mục JRE hoặc tập tin cài đặt. `PATH` thì chứa các thư mục `bin`. Trên Windows, các mục `Path` được ngăn bằng dấu chấm phẩy (`;`); Linux/macOS dùng dấu hai chấm (`:`). Hệ điều hành tìm lệnh theo thứ tự trong `PATH`, vì vậy các bản Java/Maven cũ có thể được chọn trước bản mới.

Tại thời điểm biên soạn (11/2026), ví dụ trong bài dùng **Apache Maven 3.10.0** và **JDK 21**. Maven 3.10.0 yêu cầu tối thiểu JDK 8 để chạy; tuy nhiên JDK dùng để build phải đáp ứng yêu cầu của dự án và plugin. Nếu dự án quy định phiên bản Maven/JDK khác, hãy ưu tiên phiên bản đã được dự án kiểm chứng.

## 2. Chuẩn bị chung trước khi cài Maven

1. Cài **JDK** phù hợp với hệ điều hành và kiến trúc CPU (x64 hoặc ARM64). Có thể lấy JDK từ nhà cung cấp uy tín như Eclipse Temurin/Adoptium hoặc bộ cài chính thức của hệ điều hành. Ghi lại thư mục JDK thực tế sau khi cài.
2. Mở **terminal mới** và kiểm tra:

~~~text
java -version
javac -version
~~~

Cả hai lệnh cần chạy được. `java -version` có thể chạy được với JRE; `javac -version` giúp xác nhận đã có trình biên dịch JDK. Số phiên bản in ra tùy vào JDK bạn cài.

3. Từ https://maven.apache.org/download.cgi, tải **Binary** của Maven (`apache-maven-3.10.0-bin.zip` hoặc `apache-maven-3.10.0-bin.tar.gz`); không chọn gói `-src` nếu chỉ cần dùng Maven. Trang phát hành có mã SHA-512/chữ ký để đối chiếu tính toàn vẹn. Tên phiên bản bên dưới là ví dụ nhất quán; khi dùng bản mới khác, thay tên tệp và thư mục tương ứng.
4. Giải nén vào thư mục ổn định, bên ngoài thư mục mã nguồn dự án. Thư mục giải nén phải chứa `bin/mvn` (Unix) hoặc `bin/mvn.cmd` (Windows), cùng `conf` và `lib`. Bạn **không** cần biên dịch Maven từ source.

## 3. Windows 10/11

### Bước 1 — Cài JDK và giải nén Maven

Cài JDK 21 bằng bộ cài cho Windows. Ví dụ, nếu JDK thực sự được cài tại `C:\Program Files\Java\jdk-21` thì tập tin `C:\Program Files\Java\jdk-21\bin\javac.exe` phải tồn tại. Nhà phân phối JDK khác có thể tạo đường dẫn khác: luôn dùng đường dẫn trên máy của bạn.

Giải nén `apache-maven-3.10.0-bin.zip` thành:

~~~text
C:\tools\apache-maven-3.10.0\
  bin\
    mvn.cmd
  conf\
  lib\
~~~

Tránh tạo nhầm đường dẫn lồng hai lần, chẳng hạn `C:\tools\apache-maven-3.10.0\apache-maven-3.10.0\bin`, trừ khi bạn sử dụng đúng đường dẫn thực tế đó.

Nếu muốn kiểm tra SHA-512 trước khi giải nén, mở PowerShell trong thư mục chứa file tải về:

~~~powershell
Get-FileHash .\apache-maven-3.10.0-bin.zip -Algorithm SHA512
~~~

So sánh giá trị với tệp kiểm tra SHA-512 được liên kết từ trang tải Maven; chỉ dùng tệp khi khớp.

### Bước 2 — Cấu hình biến môi trường lâu dài bằng giao diện Windows

Mở **Start → Edit the system environment variables → Environment Variables**. Chọn **User variables** nếu chỉ dùng tài khoản hiện tại, hoặc **System variables** khi cần mọi người dùng và có quyền quản trị.

Tạo hoặc sửa:

- `JAVA_HOME` = `C:\Program Files\Java\jdk-21` (thay bằng **đường dẫn JDK thật**).
- `MAVEN_HOME` = `C:\tools\apache-maven-3.10.0`.
- Trong `Path`, thêm **hai mục riêng biệt**: `%JAVA_HOME%\bin` và `%MAVEN_HOME%\bin`.

Không xóa toàn bộ `Path` có sẵn. Nếu nhiều bản JDK/Maven cùng xuất hiện, điều chỉnh thứ tự các mục để bản mong muốn được ưu tiên. Nhấn OK để lưu mọi cửa sổ và **đóng rồi mở lại** PowerShell, Command Prompt, terminal của IDE.

### Bước 3 — Kiểm tra bằng đúng cú pháp của terminal

Trong **PowerShell**:

~~~powershell
$env:JAVA_HOME
$env:MAVEN_HOME
where.exe java
where.exe javac
where.exe mvn
java -version
javac -version
mvn -version
~~~

Trong **Command Prompt (cmd.exe)**, cú pháp in biến khác PowerShell:

~~~bat
echo %JAVA_HOME%
echo %MAVEN_HOME%
where java
where javac
where mvn
java -version
javac -version
mvn -version
~~~

Lệnh `mvn -version` cần hiển thị phiên bản Maven, `Maven home` và Java đang được Maven sử dụng. Kiểm tra đường dẫn `Java home` và số phiên bản Java khớp JDK mong muốn.

Để **thử tạm trong một cửa sổ PowerShell**, chưa ghi vào môi trường hệ thống:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:MAVEN_HOME = 'C:\tools\apache-maven-3.10.0'
$env:Path = "$env:JAVA_HOME\bin;$env:MAVEN_HOME\bin;$env:Path"
mvn -version
~~~

Cách này chỉ có hiệu lực trong phiên PowerShell hiện tại và các tiến trình con; hãy thay đường dẫn JDK nếu khác thực tế. Không dùng `setx PATH` một cách tùy tiện vì dễ lưu đè hoặc làm sai `Path` hiện có.

## 4. Linux (Ubuntu/Debian, Fedora/RHEL và các bản phân phối khác)

### Bước 1 — Cài JDK và xác định JAVA_HOME

Ví dụ với Ubuntu/Debian có gói OpenJDK 21:

~~~bash
sudo apt update
sudo apt install openjdk-21-jdk
java -version
javac -version
readlink -f "$(command -v javac)"
~~~

Ví dụ với Fedora hoặc bản phân phối dùng `dnf` có gói tương ứng:

~~~bash
sudo dnf install java-21-openjdk-devel
java -version
javac -version
readlink -f "$(command -v javac)"
~~~

Tên gói và vị trí JDK khác nhau tùy phiên bản bản phân phối; nếu không có gói trên, hãy chọn gói JDK do bản phân phối hỗ trợ. `readlink -f "$(command -v javac)"` trả về đường dẫn tuyệt đối đến `javac` thật, ví dụ `/usr/lib/jvm/java-21-openjdk-amd64/bin/javac`. Bỏ phần `/bin/javac` để lấy `JAVA_HOME`; ví dụ đó cho `/usr/lib/jvm/java-21-openjdk-amd64`.

### Bước 2 — Cài Maven bằng bản binary chính thức

Giả sử archive vừa tải nằm trong `~/Downloads`:

~~~bash
cd "$HOME/Downloads"
sha512sum apache-maven-3.10.0-bin.tar.gz
sudo mkdir -p /opt/maven
sudo tar -xzf apache-maven-3.10.0-bin.tar.gz -C /opt/maven
ls /opt/maven/apache-maven-3.10.0/bin/mvn
~~~

So sánh SHA-512 in ra với checksum chính thức trước khi tin cậy archive. Khi giải nén theo cách này, `MAVEN_HOME` là `/opt/maven/apache-maven-3.10.0`. `sudo` chỉ dùng cho thao tác cài vào `/opt`, **không cần** dùng `sudo mvn` khi build dự án.

### Bước 3 — Thêm biến vào shell profile

Nếu dùng **Bash**, mở `~/.bashrc` và thêm (đường dẫn JDK là ví dụ Ubuntu, cần thay theo kết quả `readlink`):

~~~bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export MAVEN_HOME=/opt/maven/apache-maven-3.10.0
export PATH="$JAVA_HOME/bin:$MAVEN_HOME/bin:$PATH"
~~~

Nạp cấu hình trong phiên Bash hiện tại rồi kiểm tra:

~~~bash
source ~/.bashrc
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
command -v mvn
java -version
javac -version
mvn -version
~~~

Nếu dùng **Zsh** trên Linux, đặt các dòng `export` trong `~/.zshrc` rồi chạy `source ~/.zshrc`. Với Bash login shell, có thể cần cấu hình ở `~/.profile` hoặc `~/.bash_profile` tùy bản phân phối; kiểm tra shell và nơi profile được nạp. Tránh thêm nhiều lần cùng mục `PATH` trong các file profile vì có thể tạo mục trùng.

**Tùy chọn qua package manager:** `sudo apt install maven` (Debian/Ubuntu) hoặc `sudo dnf install maven` (Fedora/RHEL nếu repo có) cài Maven vào vị trí do hệ thống quản lý; phiên bản có thể khác bản trên trang Apache. Khi chọn cách này, không cần cài thêm bản tar vào `/opt` hoặc tự thêm `MAVEN_HOME/bin`. Vẫn dùng `mvn -version` để biết bản thực tế.

## 5. macOS (Apple Silicon và Intel)

### Bước 1 — Cài JDK và lấy đúng đường dẫn JDK

Cài JDK 21 dành cho chip máy từ bộ cài `.pkg` của nhà cung cấp JDK. macOS cung cấp tiện ích `/usr/libexec/java_home` để liệt kê và chọn JDK:

~~~bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 21
java -version
javac -version
~~~

Lệnh `/usr/libexec/java_home -v 21` phải trả về thư mục JDK phù hợp, thường nằm bên trong `/Library/Java/JavaVirtualMachines/.../Contents/Home`. Nếu báo không tìm thấy Java 21, cài đúng JDK trước khi thiết lập `JAVA_HOME`.

### Bước 2 — Giải nén Maven vào thư mục của người dùng

Ví dụ khi tệp tải về nằm ở `~/Downloads`:

~~~bash
shasum -a 512 "$HOME/Downloads/apache-maven-3.10.0-bin.tar.gz"
mkdir -p "$HOME/tools"
tar -xzf "$HOME/Downloads/apache-maven-3.10.0-bin.tar.gz" -C "$HOME/tools"
ls "$HOME/tools/apache-maven-3.10.0/bin/mvn"
~~~

Đối chiếu checksum với trang Apache. Với cách này, không cần `sudo` và `MAVEN_HOME` sẽ là `$HOME/tools/apache-maven-3.10.0`.

### Bước 3 — Cấu hình Zsh (shell mặc định của macOS hiện đại)

Mở `~/.zshrc` và thêm:

~~~zsh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export MAVEN_HOME="$HOME/tools/apache-maven-3.10.0"
export PATH="$JAVA_HOME/bin:$MAVEN_HOME/bin:$PATH"
~~~

Sau đó mở terminal mới hoặc nạp lại cấu hình:

~~~zsh
source ~/.zshrc
printf '%s\n' "$JAVA_HOME"
command -v mvn
java -version
javac -version
mvn -version
~~~

Nếu bạn dùng Bash thay Zsh, đặt cấu hình vào profile mà Bash thực sự đọc (thường là `~/.bash_profile` với login shell), rồi nạp file tương ứng.

**Tùy chọn Homebrew:** Nếu đã cài Homebrew và cấu hình `brew shellenv`, có thể chạy `brew install maven`. Khi đó `brew` quản lý bản Maven và đường dẫn `mvn`; không cần giải nén tar thủ công hoặc thêm `MAVEN_HOME/bin`. Cài/chọn JDK đúng yêu cầu dự án riêng biệt và kiểm tra bằng `mvn -version`.

## 6. Kiểm chứng kết quả và phân biệt lỗi môi trường với lỗi dự án

**Kiểm tra tối thiểu trên bất kỳ hệ điều hành nào** sau khi mở terminal mới:

~~~text
java -version
javac -version
mvn -version
~~~

Dùng đường dẫn in ra bởi `mvn -version` để xác minh **Maven home**, **Java version** và **Java home**. Nội dung cụ thể thay đổi theo máy nên không nên sao chép nguyên một output mẫu rồi coi là tiêu chuẩn duy nhất.

Kiểm tra lệnh nào đang được chạy khi có nhiều bản cài:

| Windows PowerShell / cmd | Linux / macOS |
| --- | --- |
| `where.exe java`, `where.exe javac`, `where.exe mvn` (trong cmd dùng `where`) | `command -v java`, `command -v javac`, `command -v mvn`; `type -a mvn` để tìm các bản trùng |
| PowerShell: `$env:JAVA_HOME`, `$env:Path`; cmd: `echo %JAVA_HOME%`, `echo %PATH%` | `printf '%s\n' "$JAVA_HOME"` và `printf '%s\n' "$PATH"` |

Nếu đang ở thư mục **đã có `pom.xml`**, thử chạy `mvn validate` để Maven đọc và kiểm tra mô hình dự án. Lần đầu build có thể cần Internet để tải plugin/phụ thuộc. `mvn -version` thành công mới chứng minh Maven khởi chạy được; `mvn validate` thất bại có thể là lỗi `pom.xml`, phiên bản plugin, proxy hoặc kho phụ thuộc.

### Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mvn: command not found` / `'mvn' is not recognized` | `bin` của Maven chưa nằm trong `PATH` của terminal hiện tại | Kiểm tra đúng thư mục có `mvn`/`mvn.cmd`, sửa `PATH`, mở terminal mới rồi chạy `command -v mvn` hoặc `where.exe mvn` |
| `JAVA_HOME is not defined correctly` | `JAVA_HOME` đang trỏ tới `bin`, JRE, đường dẫn không tồn tại hoặc JDK đã bị chuyển chỗ | Đặt về **gốc JDK**; bảo đảm có `bin/java` và `bin/javac` (Windows là `.exe`) |
| `java -version` đúng nhưng `javac` không chạy | Chỉ có JRE hoặc `PATH` đang trỏ bộ cài thiếu compiler | Cài JDK đầy đủ; kiểm tra `JAVA_HOME/bin/javac` và thứ tự `PATH` |
| `mvn -version` dùng Java khác mong muốn | `JAVA_HOME` hoặc profile/terminal/IDE dùng bản Java cũ; có nhiều JDK | So sánh `JAVA_HOME`, `where.exe java`/`command -v java` và dòng `Java home` của Maven; sửa biến, mở lại IDE/terminal |
| Có nhiều Maven và `mvn` gọi sai bản | Bản Maven cũ đứng trước trong `PATH`, hoặc package manager cung cấp bản khác | Dùng `where.exe mvn` / `type -a mvn`; sắp lại `PATH` hoặc dùng Maven Wrapper của dự án |
| `Permission denied` trên Linux/macOS | File thực thi thiếu quyền chạy, thường do sao chép sai cách | Kiểm tra quyền `ls -l "$MAVEN_HOME/bin/mvn"`; với bản tar chính thức bình thường quyền đã đúng, chỉ cấp `chmod +x` khi thực sự thiếu |
| Lỗi tải dependency/plugin hoặc SSL/proxy | Maven đã khởi chạy nhưng không kết nối kho phụ thuộc | Kiểm tra kết nối, proxy, mirror/`settings.xml` và CA của JDK; không nhầm với lỗi cài `mvn` |
| Cài ở Windows nhưng `mvn` không chạy trong WSL (hoặc ngược lại) | Windows và WSL là hai môi trường khác nhau | Cài/chọn JDK, Maven và `PATH` riêng trong Linux WSL, hoặc chạy trong terminal Windows |

### Lưu ý khi có nhiều JDK, IDE hoặc CI

- Terminal, VS Code, IntelliJ IDEA và môi trường CI có thể chọn JDK khác nhau. Ngoài `java -version`, hãy luôn xem `mvn -version` **ngay trong môi trường thực sự build**. IDE có thể có cấu hình riêng cho Maven runner và Project SDK.
- Nếu dự án cần biên dịch bằng JDK khác JDK chạy Maven, xem **Maven Toolchains**; đổi `JAVA_HOME` chỉ thay Java chạy Maven, không tự động đáp ứng mọi mức `release` và plugin.
- `MAVEN_HOME` là tùy chọn đối với Maven cài thủ công. Chỉ cần `bin` Maven có mặt trong `PATH`; tránh khai báo `M2_HOME` cũ khi không có công cụ bắt buộc yêu cầu. Đừng trộn nhiều bản Maven trong `PATH`.
- Với dự án có **Maven Wrapper**, ưu tiên script được commit cùng dự án: Windows `.\mvnw.cmd -version`; Linux/macOS `./mvnw -version`. Wrapper quản lý phiên bản Maven theo dự án và có thể tải distribution lúc chạy; vẫn cần JDK phù hợp. Không tự tạo wrapper nếu bài tập chỉ yêu cầu cài Maven hệ thống.

## 7. Danh sách tự kiểm tra

- Đã cài **JDK đầy đủ**, và cả `java -version` lẫn `javac -version` chạy được.
- `JAVA_HOME` là **thư mục gốc** của đúng JDK; không có đuôi `bin`.
- `mvn`/`mvn.cmd` tồn tại trong thư mục `bin` của bản Maven chọn; `PATH` trỏ đúng vào thư mục này.
- Đã mở terminal mới sau khi đổi biến môi trường; `mvn -version` hiển thị đúng Maven và JDK.
- Nếu `mvn` chạy được nhưng build lỗi, đã kiểm tra `pom.xml`, cấu hình mạng và yêu cầu Java của **dự án** trước khi cài lại Maven.

**Tài liệu chính thức:** [Maven Installation](https://maven.apache.org/install.html) · [Maven Downloads](https://maven.apache.org/download.cgi) · [Maven Release History](https://maven.apache.org/docs/history) · [Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html) · [Temurin JDK](https://adoptium.net/temurin/releases/).
