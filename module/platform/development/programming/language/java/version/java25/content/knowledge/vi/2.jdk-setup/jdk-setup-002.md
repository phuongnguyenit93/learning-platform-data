# Cài đặt JDK, cấu hình JAVA_HOME và xác minh phiên bản java cùng javac

> **Chương:** Thiết lập JDK 25  
> **Phạm vi:** Java 25 (JDK 25, bản hỗ trợ dài hạn/LTS) trên Windows, macOS và Linux.  
> **Kết quả cuối:** Máy có JDK 25 hợp lệ; `JAVA_HOME` trỏ đúng thư mục JDK; lệnh `java` và `javac` được gọi từ bản JDK mong muốn và đều báo phiên bản 25.

## 1. Vì sao cần kiểm tra cả Java và javac?

Để học và sử dụng Java 25, cần **Java Development Kit (JDK)**. JDK chứa JVM/runtime để chạy chương trình, compiler `javac` để biên dịch mã nguồn, cùng các công cụ phát triển như `jar`, `javadoc`, `jshell` và `jfr`.

Trên máy đã cài nhiều JDK, việc mở terminal rồi thấy `java --version` trả về 25 **chưa đủ**: `javac` có thể đang trỏ đến JDK khác. Maven, Gradle, IDE hoặc một terminal cũ cũng có thể dùng phiên bản riêng. Vì vậy bài này xác minh **bốn điều độc lập**:

| Thành phần | Chức năng | Điều cần đạt |
|---|---|---|
| `JAVA_HOME` | Đường dẫn thư mục **gốc** của JDK | Trỏ vào JDK 25, bên trong có `bin/java` và `bin/javac` |
| `PATH` | Thứ tự thư mục hệ điều hành tìm chương trình | Tìm thấy `$JAVA_HOME/bin` (Unix) hoặc `%JAVA_HOME%\bin` (Windows) trước JDK không mong muốn |
| `java` | Chạy ứng dụng / báo runtime | `java --version` hiển thị feature release **25** |
| `javac` | Biên dịch mã nguồn | `javac --version` hiển thị feature release **25** |

**Phân biệt:** `JAVA_HOME` không phải tên lệnh Java. Khi gõ `java`, shell tra cứu trong `PATH`. Các công cụ build thường cũng đọc `JAVA_HOME`. Nếu hai giá trị không thống nhất, project có thể chạy bằng một JDK và biên dịch bằng JDK khác.

Ví dụ hình dung:

~~~mermaid
flowchart TD
    A["JAVA_HOME = thư mục gốc JDK 25"]
    A --> B["bin/java\nJava runtime"]
    A --> C["bin/javac\nJava compiler"]
    D["PATH chứa JAVA_HOME/bin ở vị trí ưu tiên"] --> B
    D --> C
    E["Maven / Gradle / IDE"] -. "Có thể có cấu hình JDK riêng" .-> A
~~~

Java 25 là nhánh LTS vẫn phù hợp cho phát triển Java hiện đại. Chọn **bản cập nhật bảo mật mới nhất của dòng 25** tại thời điểm cài, thay vì cố định vào bản 25.0.0 ban đầu hoặc một đường dẫn mang số patch đã lỗi thời.

## 2. Chọn bản phân phối và đúng kiến trúc CPU

Có nhiều nhà cung cấp JDK tuân theo đặc tả Java SE. Hai nguồn chính thống, dễ dùng:

- **Eclipse Temurin 25 (OpenJDK)**: [adoptium.net/temurin/releases](https://adoptium.net/temurin/releases/) — cung cấp bộ cài cho các nền tảng được hỗ trợ.
- **Oracle JDK 25**: [oracle.com/java/technologies/downloads](https://www.oracle.com/java/technologies/downloads/) — có hướng dẫn riêng cho [Windows/macOS/Linux](https://docs.oracle.com/en/java/javase/25/install/). Khi chọn Oracle JDK, đọc điều khoản sử dụng áp dụng cho phiên bản và mục đích triển khai.

Trong toàn bộ bài, phần lệnh cài đặt lấy **Eclipse Temurin 25** làm ví dụ chính. Có thể dùng Oracle JDK 25 nếu dự án yêu cầu; nguyên tắc đặt `JAVA_HOME` và kiểm tra `java`/`javac` vẫn giống nhau.

Chọn đúng bộ cài theo hệ điều hành và kiến trúc:

| Hệ điều hành | Kiểm tra kiến trúc | Ví dụ phân loại |
|---|---|---|
| Windows | `$env:PROCESSOR_ARCHITECTURE` trong PowerShell, hoặc System Information | Windows x64 → bộ cài x64 |
| macOS | `uname -m` | Apple Silicon thường là `arm64`; Intel là `x86_64` |
| Linux | `uname -m` | `x86_64` thường tương ứng x64; `aarch64` tương ứng ARM64 |

Chọn **JDK**, không chọn gói chỉ có runtime nếu mục tiêu cần `javac`. Với các máy dùng Apple Silicon hoặc ARM64, không mặc định tải gói x64 nếu đã có bản native ARM64. Nếu nền tảng đang dùng không nằm trong danh sách được hỗ trợ của nhà phát hành, kiểm tra mục Supported Platforms thay vì đoán rằng mọi gói Java đều chạy được.

**Xác thực tệp cài:** tải từ website chính thức, kiểm tra tên bản phát hành, kiến trúc và mã SHA-256 nếu nhà cung cấp công bố checksum. Ví dụ sau khi đã tải file vào thư mục hiện tại:

~~~powershell
# Windows PowerShell; thay ten-file.msi bằng tên thực tế.
Get-FileHash -Algorithm SHA256 .\ten-file.msi
~~~

~~~bash
# Linux: thay ten-file.tar.gz bằng tên thực tế.
sha256sum ten-file.tar.gz

# macOS:
shasum -a 256 ten-file.pkg
~~~

So sánh giá trị trả về với checksum **của đúng bản và kiến trúc** trên trang tải về. Tên tệp trong các lệnh là chỗ điền mẫu, không phải file đã tồn tại trên máy.

## 3. Trước khi cài: ghi nhận JDK đang sử dụng

Nếu máy chưa có Java, các lệnh dưới đây có thể báo `command not found` hoặc không tìm thấy lệnh; đó là trạng thái đầu vào hợp lệ.

### Windows PowerShell

~~~powershell
$env:PROCESSOR_ARCHITECTURE
java --version
javac --version
$env:JAVA_HOME
Get-Command java -All -ErrorAction SilentlyContinue
Get-Command javac -All -ErrorAction SilentlyContinue
~~~

### macOS / Linux

~~~bash
uname -m
java --version
javac --version
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
~~~

Ghi lại vị trí của các executable hiện có. Không gỡ JDK cũ nếu dự án khác đang cần nó; các major release có thể cùng tồn tại. Sau khi cài Java 25, ta chỉ cần **chọn rõ phiên bản** cho terminal và công cụ build của bài này.

## 4. Cài JDK 25 trên Windows

### 4.1. Cách 1 — WinGet (PowerShell)

Nếu máy đã có Windows Package Manager (WinGet), mở PowerShell rồi chạy:

~~~powershell
winget install --id EclipseAdoptium.Temurin.25.JDK --exact
~~~

Xem thông tin gói trước khi cài nếu cần:

~~~powershell
winget show --id EclipseAdoptium.Temurin.25.JDK --exact
~~~

Lệnh WinGet trên được công bố ở [hướng dẫn cài Temurin](https://adoptium.net/installation). Trong quá trình cài, Windows có thể yêu cầu xác nhận quyền cài đặt. Khi hoàn thành, **đóng cửa sổ terminal cũ và mở PowerShell mới** để nạp lại biến môi trường.

### 4.2. Cách 2 — MSI từ Adoptium

Tải gói **JDK 25, Windows x64, MSI** tại [trang tải Temurin](https://adoptium.net/temurin/releases/) nếu nền tảng của bạn được hỗ trợ.

Khi chạy MSI, ở màn hình cấu hình thành phần:

1. Giữ tính năng cài JDK và thêm `bin` vào `PATH`.
2. Bật thêm tùy chọn **Update JAVA_HOME variable** (`FeatureJavaHome`) nếu muốn installer thiết lập giúp.
3. Hoàn tất cài đặt, mở PowerShell mới để kiểm tra.

Theo tài liệu [Adoptium Windows MSI](https://adoptium.net/installation/windows), việc cập nhật `JAVA_HOME` là **tính năng tùy chọn**, không nên mặc định nó đã được bật. Thư mục cài thường có dạng:

~~~text
C:\Program Files\Eclipse Adoptium\jdk-25...-hotspot\
    bin\
        java.exe
        javac.exe
~~~

Đoạn `jdk-25...-hotspot` chỉ biểu diễn kiểu tên thư mục; **không dán nguyên văn** vào `JAVA_HOME`. Hãy lấy đúng đường dẫn thực tế xuất hiện trong File Explorer hoặc lệnh sau:

~~~powershell
Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory
~~~

Nếu cài Oracle JDK, thư mục thường thuộc `C:\Program Files\Java\...`, không dùng đường dẫn Temurin ở trên.

### 4.3. Cấu hình JAVA_HOME vĩnh viễn bằng Windows UI

Nếu MSI chưa tạo biến hoặc bạn muốn tự quản lý phiên bản:

1. Mở **Start → Edit the system environment variables → Environment Variables**.
2. Trong **User variables** (chỉ người dùng hiện tại) hoặc **System variables** (toàn hệ thống, cần quyền phù hợp), tạo hoặc sửa `JAVA_HOME`.
3. Gán **giá trị thư mục gốc JDK 25**, ví dụ một đường dẫn thật dạng `C:\Program Files\Eclipse Adoptium\jdk-25.0.x.y-hotspot`. Không thêm `\bin` vào `JAVA_HOME`.
4. Sửa biến `Path` ở cùng phạm vi, thêm dòng `%JAVA_HOME%\bin` và ưu tiên nó trước các đường dẫn Java cũ nếu muốn Java 25 là bản mặc định.
5. Xác nhận các hộp thoại, **mở PowerShell mới** rồi kiểm tra.

**Quan trọng:** Máy có thể có cả User Path và System Path cùng nhiều Java executable. Nếu `where.exe java` liệt kê bản Java cũ ở vị trí ưu tiên, hãy kiểm tra các mục Path liên quan và cách Windows kết hợp chúng. Không cần xóa các JDK cũ nếu vẫn có dự án sử dụng.

### 4.4. Thiết lập riêng cho phiên PowerShell hiện tại

Nếu chỉ muốn thử mà chưa sửa biến vĩnh viễn:

~~~powershell
# THAY đường dẫn ví dụ bằng thư mục JDK 25 thật trên máy.
$jdkHome = 'C:\Program Files\Eclipse Adoptium\jdk-25.0.x.y-hotspot'

if (-not (Test-Path (Join-Path $jdkHome 'bin\javac.exe'))) {
    throw 'Khong tim thay javac.exe; hay kiem tra duong dan JDK.'
}

$env:JAVA_HOME = $jdkHome
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
~~~

Các lệnh này chỉ thay đổi **process environment** của phiên PowerShell hiện tại và các tiến trình con; khi mở terminal mới, hãy dùng cấu hình vĩnh viễn nếu muốn giữ nguyên.

### 4.5. Xác minh trên Windows

~~~powershell
$env:JAVA_HOME
Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe')
Test-Path (Join-Path $env:JAVA_HOME 'bin\javac.exe')

java --version
javac --version

where.exe java
where.exe javac

# Gọi trực tiếp Java/Javac theo JAVA_HOME, không phụ thuộc PATH.
& (Join-Path $env:JAVA_HOME 'bin\java.exe') --version
& (Join-Path $env:JAVA_HOME 'bin\javac.exe') --version
~~~

Hai lệnh `Test-Path` phải trả `True`. Nếu lệnh gọi trực tiếp hiển thị 25 nhưng `java` hoặc `javac` không phải 25, lỗi nằm ở `PATH` hoặc cách shell tìm executable.

## 5. Cài JDK 25 trên macOS

### 5.1. Cài bộ PKG phù hợp

Tải **Eclipse Temurin JDK 25** cho `aarch64/ARM64` hoặc `x64` tùy `uname -m`, chọn gói `.pkg` từ [Adoptium](https://adoptium.net/temurin/releases/). Mở installer và làm theo hướng dẫn. Gói PKG có thể cài vào một thư mục dưới:

~~~text
/Library/Java/JavaVirtualMachines/
~~~

Nếu dùng Oracle JDK, có thể chọn gói DMG theo [hướng dẫn macOS của Oracle JDK 25](https://docs.oracle.com/en/java/javase/25/install/installation-jdk-macos.html). Đừng tự gán đường dẫn macOS giống Windows hoặc Linux.

### 5.2. Tìm đúng JDK 25 bằng công cụ hệ thống

macOS cung cấp `/usr/libexec/java_home` để chọn đường dẫn theo phiên bản. Mở Terminal:

~~~bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 25
~~~

Lệnh `-V` liệt kê các JDK mà macOS nhận diện; `-v 25` chọn thư mục `Home` của JDK thuộc dòng 25. Với JDK cài bằng PKG, đường dẫn thường có dạng:

~~~text
/Library/Java/JavaVirtualMachines/temurin-25.jdk/Contents/Home
~~~

Đây là ví dụ cấu trúc; **dùng output của `java_home` làm giá trị chính xác** vì tên thư mục có thể khác theo nhà cung cấp.

### 5.3. Thiết lập biến cho Terminal hiện tại

~~~bash
export JAVA_HOME="$(/usr/libexec/java_home -v 25)"
export PATH="$JAVA_HOME/bin:$PATH"

printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
java --version
javac --version
~~~

Để duy trì với terminal dùng **zsh** (shell mặc định trên macOS hiện đại), thêm hai dòng `export` trên vào `~/.zshrc`, sau đó mở Terminal mới hoặc chạy `source ~/.zshrc`. Với bash, thêm vào file cấu hình tương ứng của shell đang dùng. Tránh khai báo lặp nhiều lần dẫn đến `PATH` có nhiều mục JDK trùng nhau.

### 5.4. Kiểm tra macOS

~~~bash
printf '%s\n' "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo 'java exists'
test -x "$JAVA_HOME/bin/javac" && echo 'javac exists'

"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version

java --version
javac --version
command -v java
command -v javac
~~~

**Lưu ý:** `command -v java` có thể trả `/usr/bin/java`, là launcher của macOS. Để biết JDK thật đang được chọn, so thêm `/usr/libexec/java_home -v 25`, `JAVA_HOME` và kết quả version. Nếu đang dùng IDE, kiểm tra **Project SDK/Gradle JVM** riêng; IDE có thể không kế thừa environment của Terminal.

## 6. Cài JDK 25 trên Linux

Có thể dùng gói DEB/RPM từ nhà cung cấp, repository của Adoptium hoặc bản archive đúng nền tảng. Với Ubuntu/Debian có repository hỗ trợ, gói Temurin mang tên **`temurin-25-jdk`**; không mặc định gói đó đã tồn tại trong repository mặc định của hệ điều hành.

### 6.1. Ubuntu/Debian — cài qua Adoptium APT

Các lệnh sau dành cho Ubuntu/Debian **được Adoptium hỗ trợ**, chạy với tài khoản có quyền `sudo`. Ví dụ sử dụng keyring riêng và `signed-by` cho APT:

~~~bash
sudo apt update
sudo apt install -y ca-certificates wget gpg
sudo install -d -m 0755 /etc/apt/keyrings

wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public \
  | sudo gpg --dearmor -o /etc/apt/keyrings/adoptium.gpg
sudo chmod 0644 /etc/apt/keyrings/adoptium.gpg

echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print $2}' /etc/os-release) main" \
  | sudo tee /etc/apt/sources.list.d/adoptium.list

sudo apt update
sudo apt install -y temurin-25-jdk
~~~

Nếu máy đã có file keyring, `gpg` có thể hỏi xác nhận trước khi ghi đè; kiểm tra trạng thái thay vì tự động xóa key hiện hữu. Với distro dẫn xuất như Linux Mint, codename repository có thể cần dùng `UBUNTU_CODENAME` thay cho `VERSION_CODENAME`. Đối chiếu danh sách distro và đường dẫn package trong [hướng dẫn Linux của Adoptium](https://adoptium.net/installation/linux/).

Sau cài đặt:

~~~bash
java --version
javac --version
ls -d /usr/lib/jvm/temurin-25-*
~~~

Không mặc định apt sẽ tự chọn JDK 25 làm Java mặc định nếu máy đã có JDK khác.

### 6.2. Linux khác — dùng gói phù hợp hoặc bản archive

Với Fedora/RHEL, openSUSE/SLES hoặc Alpine, xem chính xác gói và cách cấu hình repository ở [Adoptium Linux Installation](https://adoptium.net/installation/linux/). Không dùng lệnh APT trên những hệ điều hành có package manager khác.

Nếu tải archive `.tar.gz` từ nguồn chính thức, giải nén vào thư mục do người dùng kiểm soát hoặc thư mục quản trị, ví dụ:

~~~bash
# Ví dụ: file archive đã được tải từ nhà cung cấp, checksum đã đối chiếu.
mkdir -p "$HOME/jdks"
tar -xzf temurin-25-linux-archive.tar.gz -C "$HOME/jdks"
~~~

Tên `temurin-25-linux-archive.tar.gz` chỉ là **placeholder**; đổi thành tên archive thực tế trước khi chạy. Sau giải nén, mở thư mục và xác định **thư mục gốc chứa `bin/java` và `bin/javac`**, không lấy chính `$HOME/jdks` làm `JAVA_HOME` nếu bên trong còn thư mục con.

Đối với bản Oracle JDK, tham khảo [hướng dẫn JDK 25 trên Linux](https://docs.oracle.com/en/java/javase/25/install/installation-jdk-linux-platforms.html). Các gói khác nhau có thể đặt JDK ở những đường dẫn và symlink khác nhau.

### 6.3. Cấu hình JAVA_HOME trên Linux

Đầu tiên tìm đường dẫn JDK 25 đang cài. Nếu cài `temurin-25-jdk` qua APT trên Linux x64, một ví dụ đường dẫn là:

~~~text
/usr/lib/jvm/temurin-25-jdk-amd64
~~~

**Không chắc chắn đó là đường dẫn trên máy bạn**: tên có thể khác tùy kiến trúc và bản cài. Hãy kiểm tra `ls -d /usr/lib/jvm/temurin-25-*` rồi chọn đường dẫn có `bin/javac`.

Thiết lập trong phiên Bash hiện tại, thay bằng đường dẫn thật:

~~~bash
export JAVA_HOME="/usr/lib/jvm/temurin-25-jdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"

test -x "$JAVA_HOME/bin/javac" || echo "JAVA_HOME chua tro den JDK co javac"
java --version
javac --version
~~~

Để duy trì qua các phiên terminal, thêm hai dòng `export` vào `~/.bashrc` nếu dùng Bash tương tác; dùng `~/.zshrc` nếu dùng zsh. Mở shell mới hoặc chạy `source ~/.bashrc`. Nếu chạy bằng systemd, container, IDE hoặc CI, cấu hình environment của **tiến trình đó** có thể khác với shell tương tác.

### 6.4. Nhiều bản Java và update-alternatives

Trên Debian/Ubuntu, kiểm tra các lựa chọn mặc định:

~~~bash
update-alternatives --list java
update-alternatives --list javac
~~~

Nếu muốn Java 25 là mặc định toàn hệ thống, có thể chọn từng chương trình bằng:

~~~bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
~~~

Chọn các mục trỏ vào **cùng một JDK 25**. Đây là thao tác ảnh hưởng tới mặc định của hệ thống, nên nếu nhiều dự án yêu cầu các JDK khác nhau, ưu tiên cấu hình `JAVA_HOME` và `PATH` theo từng project/shell thay vì thay lựa chọn của toàn máy.

Để kiểm tra đường dẫn thực sự sau symlink trên Linux:

~~~bash
command -v java
command -v javac
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
~~~

`readlink -f` ở đây áp dụng cho Linux, không giả định tùy chọn này có cùng hành vi trên macOS.

## 7. Xác minh đầy đủ Java 25 và compiler

Sau khi cài xong, mở một terminal mới và chạy:

~~~text
java --version
javac --version
~~~

Một kết quả hợp lệ sẽ có dạng sau (chỉ minh họa, chuỗi vendor/build/ngày phát hành thay đổi theo bản cập nhật):

~~~text
openjdk 25.0.x ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...

javac 25.0.x
~~~

**Tiêu chí:** cả `java` và `javac` báo feature release **25**. Bản cập nhật (phần `.0.x`) có thể khác tùy thời điểm cài; tốt nhất runtime và compiler cùng đến từ một bộ JDK nhất quán.

Ngoài version, gọi trực tiếp binary từ `JAVA_HOME` để loại trừ lỗi `PATH`:

~~~bash
# macOS / Linux
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
~~~

~~~powershell
# Windows PowerShell
$env:JAVA_HOME
& (Join-Path $env:JAVA_HOME 'bin\java.exe') --version
& (Join-Path $env:JAVA_HOME 'bin\javac.exe') --version
~~~

Có thể kiểm tra `java.home` do runtime thực sự dùng:

~~~bash
java -XshowSettings:properties -version
~~~

Trong output, tìm thuộc tính `java.home`. Nếu nó chỉ đến JDK khác, shell đang gọi runtime khác với mong đợi. `java.home` là thuộc tính của runtime đang chạy và không nhất thiết có chuỗi ký tự giống tuyệt đối với biến `JAVA_HOME` (do canonical path/symlink), nhưng cả hai cần quy về đúng JDK 25.

### 7.1. Thử biên dịch và chạy chương trình Java tiêu chuẩn

Tạo file `VerifyJdk.java` trong một thư mục thử nghiệm riêng:

~~~java
public class VerifyJdk {
    public static void main(String[] args) {
        System.out.println("JDK feature = " + Runtime.version().feature());
    }
}
~~~

Trong terminal đang đứng tại thư mục chứa file:

~~~bash
javac VerifyJdk.java
java VerifyJdk
~~~

Kết quả mong đợi:

~~~text
JDK feature = 25
~~~

Bước này chứng minh `javac` **thực sự biên dịch được**, còn `java` chạy được class vừa tạo. Nếu muốn thêm kiểm tra Java 25 mới mà không phụ thuộc preview, có thể thử **compact source file và instance main** (đã là tính năng chính thức của Java 25):

~~~java
// Lưu thành Hello25.java
void main() {
    IO.println("Hello from Java " + Runtime.version().feature());
}
~~~

Chạy:

~~~bash
java Hello25.java
~~~

Dự kiến:

~~~text
Hello from Java 25
~~~

Ví dụ này sử dụng `IO.println` và cách viết chương trình nguồn gọn thuộc Java 25; **không cần `--enable-preview`**. Nếu không chạy được, hãy đối chiếu `java --version` và xác nhận file đang được mở bởi Java 25 thật. Những chủ đề khác của Java 25 như module import, flexible constructor bodies, `ScopedValue`, key derivation API, AOT cache và JFR sẽ được học riêng sau khi nền tảng JDK đã được kiểm tra.

## 8. IDE, Maven, Gradle và CI phải cùng chọn JDK

Lệnh `java` trong terminal đúng chưa đồng nghĩa mọi công cụ đang dùng Java 25:

- **IntelliJ IDEA / Eclipse / VS Code Java:** kiểm tra JDK/SDK được cấu hình cho workspace và cho project; có thể phải chọn lại đường dẫn sau khi cài.
- **Maven:** kiểm tra runtime Maven bằng `mvn -version`. Nếu build dùng compiler khác, xem thêm Maven Toolchains và cấu hình compiler.
- **Gradle:** kiểm tra `./gradlew --version` (Unix/macOS) hoặc `.\gradlew.bat --version` (Windows) khi project có Gradle Wrapper. Gradle daemon và Java toolchain có thể dùng JDK khác nhau.
- **CI/CD:** cấu hình JDK 25 tường minh trong job hoặc toolchain; không dựa vào `java` mặc định của runner.

Ví dụ đặt mục tiêu Java 25 cho build Maven (khi Maven compiler plugin và các tool đang dùng hỗ trợ):

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
~~~

Với Gradle Groovy DSL và bản Gradle có hỗ trợ toolchain Java 25:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
~~~

Toolchain giúp build chọn Java 25 có chủ đích. Nhưng một dự án đang chạy trên runtime thấp hơn Java 25 có thể yêu cầu `--release` khác để bảo đảm tương thích ngược; **không tự tăng release mục tiêu chỉ vì vừa cài thêm JDK 25**. Khi nâng cấp, kiểm tra framework, plugin build, test, thư viện và môi trường triển khai trước khi đổi target bytecode.

## 9. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách xác minh và khắc phục |
|---|---|---|
| `java` không được nhận diện | Không có `bin` trong `PATH` hoặc terminal chưa nạp environment mới | Kiểm tra `JAVA_HOME`, cập nhật `PATH` rồi mở terminal mới |
| `java --version` là 25, `javac --version` là 21 | `PATH` có nhiều JDK, mỗi lệnh được tìm từ vị trí khác | Dùng `where.exe` (Windows) hoặc `command -v`/`readlink -f` (Linux) và gọi binary trực tiếp trong `JAVA_HOME` |
| `JAVA_HOME` trỏ vào `.../bin` | Đặt sai mức thư mục | Đổi sang thư mục **gốc** chứa `bin` |
| Biến `JAVA_HOME` đúng nhưng lệnh `java` vẫn cũ | Java cũ xuất hiện trước trong `PATH`; terminal chưa mở lại | Kiểm tra thứ tự PATH và khởi động terminal/IDE mới |
| `JAVA_HOME` trống, nhưng `java` vẫn chạy | Java được tìm từ PATH, chưa thiết lập biến cho công cụ build | Thiết lập `JAVA_HOME` theo JDK đã kiểm chứng |
| Không thấy `javac` | Chỉ có runtime hoặc đường dẫn bộ compiler không có trong PATH | Cài gói **JDK**, kiểm tra `bin/javac` |
| `/usr/libexec/java_home -v 25` thất bại trên macOS | JDK chưa cài hoặc chưa được macOS nhận diện | Kiểm tra gói PKG/DMG, `java_home -V` và đúng kiến trúc |
| `sudo apt install temurin-25-jdk` không tìm thấy gói | Chưa thêm Adoptium APT repository hoặc distro/codename không được hỗ trợ | Kiểm tra keyring, source list và repo trong hướng dẫn Adoptium |
| Maven/Gradle vẫn dùng Java cũ | Tool hoặc daemon chọn JDK riêng | Xem `mvn -version`, `gradlew --version`, cấu hình toolchain và khởi động lại daemon/IDE |
| `UnsupportedClassVersionError` khi chạy class build bằng JDK 25 | Runtime quá cũ để đọc class file của Java 25 (major version 69) | Nâng runtime mục tiêu hoặc build với `--release` phù hợp |
| `error: release version 25 not supported` | Compiler `javac` thực sự thuộc JDK thấp hơn 25 | Kiểm tra `javac --version` và build toolchain |
| Java chạy trên container nhưng khác host | Container mang JDK riêng, không kế thừa `JAVA_HOME` của host | Kiểm tra trực tiếp trong container và chỉnh base image/toolchain |
| Cài đúng nhưng lệnh kết quả không nhất quán theo shell | PowerShell, CMD, zsh, bash hoặc IDE khởi tạo môi trường riêng | Kiểm tra trong **đúng process/shell** chạy build hoặc test |

### Cách khoanh vùng không làm hỏng cấu hình cũ

Với mọi hệ điều hành, ưu tiên trình tự:

1. Xác minh tồn tại của `bin/java` và `bin/javac` **ngay trong thư mục JDK 25 thật**.
2. Gọi hai binary bằng **đường dẫn tuyệt đối** để xem version của chính bộ JDK đó.
3. Chỉnh `JAVA_HOME` trỏ về thư mục gốc và bảo đảm `PATH` ưu tiên thư mục `bin` tương ứng.
4. Mở terminal mới, xác minh lại `java` và `javac`, sau đó kiểm tra Maven/Gradle/IDE.
5. Khi môi trường ổn định, mới chạy thử compile/execute hoặc bài thực hành Java 25.

Cách này cũng hữu ích khi machine đang cần đồng thời Java 21 và Java 25. Không cần xóa Java 21 để dùng Java 25: hãy chọn phiên bản theo công việc và giữ cấu hình build có thể tái hiện.

## 10. Tiêu chí hoàn thành và câu hỏi tự kiểm tra

### Checklist nghiệm thu

- [ ] Đã tải JDK 25 từ nguồn chính thống, đúng OS/CPU; đã kiểm tra file cài và checksum khi có.
- [ ] Thư mục JDK có cả `bin/java` và `bin/javac`.
- [ ] `JAVA_HOME` trỏ vào **thư mục gốc** của JDK 25.
- [ ] `PATH` cho phép gọi đúng binary JDK 25 đang chọn.
- [ ] `java --version` và `javac --version` cùng hiển thị feature release **25**.
- [ ] Gọi trực tiếp executable qua `JAVA_HOME` cũng trả bản 25.
- [ ] File `VerifyJdk.java` biên dịch và chạy, in `JDK feature = 25`.
- [ ] IDE/build tool đang dùng chọn đúng JDK hoặc toolchain theo mục tiêu project.
- [ ] Có thể giải thích khác biệt giữa `JAVA_HOME`, `PATH`, `java` và `javac`.

### Câu hỏi ôn tập

1. Vì sao nhìn thấy `java --version = 25` **chưa đủ** để kết luận máy đã cấu hình JDK 25 đúng?
2. Nếu `JAVA_HOME` trỏ vào `.../bin`, điều gì sẽ xảy ra khi công cụ build ghép thêm `/bin/javac`?
3. Vì sao macOS có thể trả `command -v java = /usr/bin/java` dù đang chạy JDK 25?
4. Trên máy có Java 21 và 25, nên kiểm tra gì trước khi thay đổi `update-alternatives` hoặc thứ tự PATH?
5. Khi Maven báo target 25 không được hỗ trợ nhưng `java --version` đã là 25, bạn sẽ kiểm tra lệnh và cấu hình nào?

## 11. Tài liệu chính thức

- [Eclipse Adoptium — Install Eclipse Temurin](https://adoptium.net/installation): đường tải JDK, WinGet và lựa chọn cài đặt đa nền tảng.
- [Eclipse Adoptium — Windows MSI](https://adoptium.net/installation/windows): tính năng PATH và JAVA_HOME của MSI installer.
- [Eclipse Adoptium — macOS PKG](https://adoptium.net/installation/macOS): cài JDK qua gói PKG trên macOS.
- [Eclipse Adoptium — Linux packages](https://adoptium.net/installation/linux/): repository và tên gói `temurin-25-jdk`.
- [Oracle — JDK 25 Installation Guide](https://docs.oracle.com/en/java/javase/25/install/): cài và xác minh Oracle JDK 25 trên Windows, macOS và Linux.
- [Oracle — Java SE 25 Language Changes](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): các thay đổi ngôn ngữ đã có hiệu lực trong Java 25, gồm compact source files và instance main methods.

> **Ghi nhớ:** Điều quan trọng không chỉ là “đã cài Java 25”, mà là **đường dẫn JDK đúng, runtime và compiler cùng phiên bản, công cụ build dùng đúng toolchain**. Đây là nền tảng để thực hành các tính năng Java 25 hiện hành và đánh giá an toàn tác động nâng cấp JDK.
