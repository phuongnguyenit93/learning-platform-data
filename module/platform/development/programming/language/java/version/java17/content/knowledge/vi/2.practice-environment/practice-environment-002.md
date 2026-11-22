# Cài JDK 17 đúng hệ điều hành và kiến trúc CPU

Bạn có thể cài Java thành công nhưng vẫn không biên dịch được chương trình nếu chọn nhầm **JRE thay vì JDK**, nhầm **Windows với Linux**, nhầm **x64 với ARM64**, hoặc để terminal sử dụng một bản Java cũ. Bài này hướng dẫn cách chọn đúng gói cài đặt **Java Development Kit (JDK) 17**, cấu hình môi trường và tự kiểm chứng từ đầu đến cuối trên Windows, macOS và Linux.

## 1. Hiểu mình cần tải gì

**JDK (Java Development Kit)** chứa các công cụ để **viết, biên dịch, chạy và kiểm tra** ứng dụng Java:

| Thành phần | Vai trò | Kiểm tra |
|---|---|---|
| `java` | Chạy chương trình trên JVM | `java --version` |
| `javac` | Biên dịch mã nguồn `.java` thành bytecode `.class` | `javac --version` |
| `jar` | Đóng gói/xem nội dung tệp JAR | `jar --version` |
| `jshell` | Thử biểu thức Java tương tác | `jshell --version` |
| `javadoc` | Tạo tài liệu API từ mã nguồn | `javadoc --version` |

JDK đã có các thành phần cần thiết để chạy chương trình Java; **không cần cài thêm một JRE riêng để học lập trình Java 17**. Khi trang tải cho chọn **JDK/JRE**, hãy chọn **JDK**.

Trong khóa học Java 17, cần chọn **nhánh phiên bản 17**, chẳng hạn `17.0.x`, và ưu tiên bản cập nhật bảo mật mới nhất của nhánh đó. Bản Java có số lớn hơn (21, 25, 27...) không tự động thay thế đúng yêu cầu của dự án Java 17. `17.0.21` là một bản cập nhật thuộc Java 17, còn `21.0.x` thuộc nhánh Java 21.

### JDK của hãng nào?

Các bản phân phối phổ biến gồm:

- **Eclipse Temurin (Adoptium):** bản dựng OpenJDK phù hợp để học và phát triển trên nhiều hệ điều hành. Trang tải: [adoptium.net/temurin/releases?version=17](https://adoptium.net/temurin/releases?version=17).
- **Microsoft Build of OpenJDK:** cung cấp JDK 17 cho nhiều nền tảng, bao gồm bộ cài **Windows ARM64**. Trang tải: [Microsoft Learn — Download OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/download).
- **Gói OpenJDK từ kho hệ điều hành:** thuận tiện trên Ubuntu/Debian hoặc RHEL/Fedora vì có thể cập nhật qua trình quản lý gói.
- **Oracle JDK:** cũng là một lựa chọn, nhưng cần đọc điều khoản cấp phép và hỗ trợ tương ứng với cách sử dụng. Hướng dẫn: [JDK 17 Installation Guide](https://docs.oracle.com/en/java/javase/17/install/).

Chọn **một nguồn chính thức, có hỗ trợ đúng hệ điều hành và CPU**, thay vì tải một tệp có tên gần giống từ trang không rõ nguồn gốc.

## 2. Xác định đúng bộ ba: phiên bản Java — hệ điều hành — kiến trúc

Đừng chọn gói chỉ dựa vào việc máy được gọi là "64-bit". Kiến trúc **x64** (Intel/AMD) và **ARM64** đều 64-bit nhưng là hai loại mã máy khác nhau.

| Máy đang sử dụng | Tên kiến trúc thường thấy | Gói JDK 17 cần tìm |
|---|---|---|
| Windows chạy CPU Intel/AMD 64-bit | `x64`, `amd64`, `x86_64` | **Windows x64**: thường là `.msi` hoặc `.exe` |
| Windows chạy CPU ARM 64-bit | `ARM64`, `aarch64` | **Windows ARM64**: chọn nhà cung cấp có bản dựng ARM64 |
| Mac dùng chip Intel | `x86_64` | **macOS x64** |
| Mac dùng Apple Silicon (M1/M2/M3/M4/...) | `arm64`, `aarch64` | **macOS ARM64 / Apple Silicon** |
| Linux chạy CPU Intel/AMD 64-bit | `x86_64`, `amd64` | **Linux x64** |
| Linux chạy CPU ARM 64-bit | `aarch64`, `arm64` | **Linux ARM64** |

`amd64` là tên thường gặp của kiến trúc x86 64-bit, **không có nghĩa máy bắt buộc dùng CPU AMD**. `aarch64` thường đồng nghĩa với ARM64. Các hậu tố `.msi`, `.pkg`, `.deb`, `.rpm`, `.tar.gz` biểu thị **định dạng phân phối**, không thay thế thông tin kiến trúc.

Một số môi trường cần lưu ý:

- **Windows 32-bit:** dù CPU có khả năng 64-bit, hệ điều hành 32-bit không chạy được JDK x64. Java 17 cho x86 32-bit chỉ có ở một số nhà cung cấp; nếu không có bản phù hợp, hãy dùng hệ điều hành 64-bit được hỗ trợ.
- **Mac Apple Silicon:** nếu Terminal đang chạy qua **Rosetta**, một số lệnh có thể mô tả tiến trình là x86_64. Hãy xem loại **Chip** trong *About This Mac* để biết phần cứng thật; ưu tiên bản ARM64 chạy native.
- **WSL trên Windows:** khi mở terminal Ubuntu/Debian **bên trong WSL**, hãy cài **JDK Linux** với kiến trúc của môi trường WSL, không dùng tệp cài Windows.
- **Docker/container:** chọn JDK theo **hệ điều hành và kiến trúc của container cần chạy**; bản dựng cross-platform hoặc thư viện native có thể yêu cầu cấu hình riêng.
- **Alpine Linux:** thường dùng **musl libc**, khác nhiều bản Linux dùng **glibc**. Hãy chọn image/gói **Alpine/musl** tương thích, không áp dụng máy móc một tệp tar.gz Linux glibc.

### 2.1. Kiểm tra trên Windows

Vào **Settings → System → About**, xem mục **System type**. Máy có thể hiển thị bộ xử lý dựa trên **x64** hoặc **ARM**.

Nếu muốn kiểm tra bằng PowerShell:

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, Architecture
```

Trong thuộc tính `Architecture` của Windows, `9` thường là x64 và `12` là ARM64. Đọc thêm tên CPU nếu kết quả chưa rõ. Biến `PROCESSOR_ARCHITECTURE` chỉ phản ánh môi trường tiến trình trong một số tình huống, nên có thể gây hiểu nhầm khi chạy ứng dụng qua lớp giả lập.

### 2.2. Kiểm tra trên macOS

Chọn **Apple menu → About This Mac**:

- Hiện **Chip: Apple M...** → tải **macOS ARM64/aarch64**.
- Hiện **Processor: Intel...** → tải **macOS x64**.

Trong Terminal:

```bash
uname -m
```

Kết quả thường là `arm64` hoặc `x86_64`. Nếu đang dùng Rosetta, hãy ưu tiên thông tin chip ở *About This Mac*.

### 2.3. Kiểm tra trên Linux

```bash
uname -m
cat /etc/os-release
```

Ví dụ `uname -m` trả về `x86_64`, còn `/etc/os-release` cho biết hệ đang là Ubuntu, Debian, Fedora... Hệ điều hành cụ thể quyết định nên dùng `apt`, `dnf` hay một gói khác.

## 3. Cài JDK 17 trên Windows

### Cách A — Windows x64: cài Eclipse Temurin bằng MSI

1. Mở [trang tải Temurin 17](https://adoptium.net/temurin/releases?version=17).
2. Chọn **Version 17**, **Operating System: Windows**, **Architecture: x64**, **Package Type: JDK** và tệp **MSI**.
3. Chạy tệp `.msi` vừa tải và làm theo trình cài đặt.
4. Trong phần tùy chọn, bật **Add to PATH**. Nên bật thêm **Set/Update JAVA_HOME** nếu trình cài đặt cung cấp tùy chọn này; với MSI của Temurin, tùy chọn `JAVA_HOME` có thể phải được chọn thêm.
5. Kết thúc cài đặt, **đóng terminal cũ và mở PowerShell mới**.

Kiểm tra:

```powershell
java --version
javac --version
where.exe java
where.exe javac
```

Hai lệnh đầu phải báo **Java 17**; lệnh `javac` cần tồn tại. Đường dẫn thường nằm trong thư mục `C:\Program Files\Eclipse Adoptium\...` (tên thư mục chính xác phụ thuộc bản cập nhật).

> **Lưu ý:** tài liệu MSI của Temurin nêu trình cài Windows dạng MSI dành cho **Windows x64**. Với Windows ARM64, chọn nhà cung cấp/gói cài hỗ trợ ARM64 thực sự.

### Cách B — Windows ARM64: dùng gói JDK 17 ARM64 native

1. Mở [Microsoft Build of OpenJDK — Downloads](https://learn.microsoft.com/en-us/java/openjdk/download).
2. Tìm phần **OpenJDK 17**, mục **Windows — AArch64 / ARM64**.
3. Chọn `.msi`/`.exe` nếu trang cung cấp, hoặc `.zip` nếu muốn cài thủ công.
4. Cài đặt và kiểm tra `java`, `javac` giống Windows x64.

Không đổi tên tệp x64 thành ARM64: tên tệp không chuyển đổi được kiến trúc. Một số chương trình x64 có thể chạy dưới giả lập trên Windows ARM, nhưng **bản JDK ARM64 native** thường là lựa chọn thích hợp hơn khi có hỗ trợ.

### Thiết lập thủ công `JAVA_HOME` và `Path` trên Windows

Chỉ cần làm nếu trình cài chưa thiết lập hoặc đang trỏ nhầm JDK:

1. Mở **Edit the system environment variables → Environment Variables**.
2. Tạo/chỉnh **JAVA_HOME** thành **thư mục gốc của JDK 17**, ví dụ `C:\Program Files\Eclipse Adoptium\jdk-17.0.x...-hotspot`. **Không** thêm `\bin` vào giá trị `JAVA_HOME`.
3. Trong biến **Path** của user hoặc system phù hợp, thêm `%JAVA_HOME%\bin`.
4. Nếu `Path` chứa đường dẫn Java khác đứng trước, điều chỉnh thứ tự để JDK 17 được ưu tiên (đừng tùy tiện xóa các mục mà ứng dụng khác còn dùng).
5. Mở một terminal mới:

```powershell
$env:JAVA_HOME
Get-Command java | Select-Object Source
Get-Command javac | Select-Object Source
java --version
javac --version
```

Nếu chỉ muốn thử **trong phiên PowerShell hiện tại**, có thể cấu hình tạm, sau khi thay đường dẫn ví dụ bằng thư mục thực:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.x...-hotspot'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

Thiết lập tạm mất hiệu lực khi đóng cửa sổ. Khi chỉnh biến môi trường vĩnh viễn, dùng giao diện hệ thống để dễ nhìn thấy toàn bộ `Path` và tránh ghi đè nhầm.

## 4. Cài JDK 17 trên macOS

### Cách A — tải tệp PKG chính thức

1. Mở [Temurin 17 Releases](https://adoptium.net/temurin/releases?version=17).
2. Chọn đúng **macOS x64** cho Intel hoặc **macOS aarch64/ARM64** cho Apple Silicon.
3. Chọn **JDK** và tệp **PKG**; mở tệp để cài.
4. Mở Terminal mới và kiểm tra:

```bash
/usr/libexec/java_home -V
java --version
javac --version
```

Trên macOS, JDK dạng PKG thường được đặt trong `/Library/Java/JavaVirtualMachines/`. Lệnh `/usr/libexec/java_home` là công cụ tích hợp của macOS để tìm các JDK được hệ thống nhận diện.

### Cách B — sử dụng Homebrew nếu đã cài Homebrew

```bash
brew install --cask temurin@17
```

Cask `temurin@17` được đăng trong [Homebrew Formulae](https://formulae.brew.sh/cask/temurin@17). Nếu dùng Homebrew, hãy kiểm tra thông tin tương thích của cask với bản macOS đang chạy.

### Chọn JDK 17 khi máy có nhiều bản

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17 --exec javac --version
```

Để dùng JDK 17 cho phiên Terminal hiện tại:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
java --version
javac --version
```

Với **zsh**, có thể thêm hai lệnh `export` vào `~/.zshrc` nếu muốn áp dụng cho các phiên shell tương tác mới. Nếu đang dùng bash hoặc cách khởi tạo shell khác, chỉnh tệp cấu hình tương ứng. Sau khi sửa, mở Terminal mới.

> Nếu `/usr/libexec/java_home -v 17` không tìm thấy JDK, hãy xác nhận rằng bạn đã cài gói **JDK** đúng cho macOS và kiến trúc máy, rồi xem `/usr/libexec/java_home -V`.

## 5. Cài JDK 17 trên Linux

### 5.1. Ubuntu/Debian: sử dụng `apt`

Trên phiên bản Ubuntu/Debian có cung cấp gói JDK 17 trong repository đang cấu hình:

```bash
sudo apt update
sudo apt install openjdk-17-jdk

java --version
javac --version
```

Lệnh `apt` thường tự chọn gói đúng kiến trúc hệ điều hành. Không cần tự tải file `x64` cho máy ARM64 khi repository đã có biến thể tương ứng.

Kiểm tra đường dẫn thực tế:

```bash
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
```

Nếu nhiều Java đã được cài, Ubuntu/Debian thường dùng `update-alternatives`:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
```

Chọn mục của **JDK 17** cho **cả hai** lệnh. Đừng chỉ đổi `java` mà quên `javac`.

### 5.2. Fedora/RHEL: sử dụng `dnf` khi repository có JDK 17

```bash
sudo dnf install java-17-openjdk-devel

java --version
javac --version
```

Tên `-devel` chỉ gói chứa công cụ phát triển như `javac`. Trên các bản RHEL/Fedora, tính sẵn có của phiên bản JDK tùy release và repository; nếu báo không tìm thấy package, hãy kiểm tra nguồn gói đang bật và tài liệu của bản phân phối thay vì thay bừa thành Java mới hơn.

Khi có nhiều bản JDK, trên hệ dùng `alternatives` có thể chọn:

```bash
sudo alternatives --config java
sudo alternatives --config javac
```

### 5.3. Thiết lập `JAVA_HOME` trên Linux

Phần lớn gói JDK quản lý qua `apt`/`dnf` đã thiết lập đường dẫn thực thi. Một số công cụ xây dựng vẫn cần `JAVA_HOME`. Có thể xác định thư mục gốc từ `javac` đã chọn:

```bash
readlink -f "$(command -v javac)"
```

Ví dụ kết quả là `/usr/lib/jvm/java-17-openjdk-amd64/bin/javac` thì `JAVA_HOME` tương ứng là `/usr/lib/jvm/java-17-openjdk-amd64`. Đường dẫn trên ARM64 hoặc bản phân phối khác có thể khác; **không chép nguyên đường dẫn ví dụ**.

Để lấy đường dẫn tự động trong phiên bash hiện tại:

```bash
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
export PATH="$JAVA_HOME/bin:$PATH"

printf '%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/javac" --version
```

Khi cần giữ cấu hình qua các phiên làm việc, đặt lệnh `export` thích hợp vào tệp cấu hình shell của **người dùng**, cân nhắc cấu hình hiện có của hệ thống. Với build server, container và CI, thường nên khai báo JDK cụ thể trong cấu hình môi trường hoặc toolchain của dự án thay vì đổi Java toàn máy.

### 5.4. Khi không dùng được trình quản lý gói

Có thể tải bản `.tar.gz` từ nguồn chính thức tương thích với **Linux + CPU + libc**, giải nén vào thư mục do bạn quản lý, rồi đặt `JAVA_HOME` đến thư mục chứa `bin/java` và `bin/javac`:

```bash
mkdir -p "$HOME/.local/jdks"
tar -xzf /duong-dan/toi/jdk-17-dung-he-va-cpu.tar.gz -C "$HOME/.local/jdks"
```

Tên trong lệnh là **đường dẫn minh họa**, phải thay bằng tên tệp thực tế đã tải. Kiểm tra thư mục sau giải nén trước khi đặt biến:

```bash
ls "$HOME/.local/jdks"
```

Cách dùng tệp nén thuận tiện khi không có quyền quản trị hoặc cần giữ nhiều bản JDK cho các dự án. Tuy nhiên, bạn phải chủ động cập nhật JDK và sửa đường dẫn khi chuyển bản vá.

## 6. Kiểm tra thật sự đã dùng đúng JDK 17

Không chỉ nhìn thấy biểu tượng Java hoặc một ứng dụng khởi động được. Thực hiện đủ các bước sau trong **terminal mới**.

### Bước 1 — Kiểm tra phiên bản runtime và trình biên dịch

```text
java --version
javac --version
```

Một kết quả hợp lệ có dạng:

```text
openjdk 17.0.x ...
...
javac 17.0.x
```

Dấu `x` chỉ bản vá có thể thay đổi. Điều quan trọng là **hai công cụ cùng là 17**, không phải đúng một số bản vá cố định.

### Bước 2 — Xác định Java thực tế đang chạy

Trên **Windows PowerShell**:

```powershell
Get-Command java | Select-Object Source
Get-Command javac | Select-Object Source
java -XshowSettings:properties -version 2>&1 | Select-String 'java.home|os.arch'
```

Trên **macOS/Linux**:

```bash
command -v java
command -v javac
java -XshowSettings:properties -version 2>&1 | grep -E 'java.home|os.arch'
```

`java.home` chỉ runtime mà tiến trình đang dùng. `os.arch` mô tả kiến trúc của **JVM đang chạy** (thường `amd64` hoặc `aarch64`); nếu chạy thông qua giả lập, giá trị này có thể khác kiến trúc vật lý. Đối chiếu với kết quả phát hiện CPU ở phần 2.

### Bước 3 — Viết, biên dịch và chạy chương trình đầu tiên

Tạo tệp **`HelloJdk17.java`** với đúng tên và nội dung:

```java
public class HelloJdk17 {
    public static void main(String[] args) {
        System.out.println("Java " + Runtime.version().feature());
        System.out.println("JVM architecture: " + System.getProperty("os.arch"));
        System.out.println("JVM vendor: " + System.getProperty("java.vendor"));
    }
}
```

Trong terminal đang đứng ở thư mục chứa tệp:

```bash
javac --release 17 HelloJdk17.java
java HelloJdk17
```

Ví dụ đầu ra:

```text
Java 17
JVM architecture: amd64
JVM vendor: Eclipse Adoptium
```

Dòng kiến trúc và vendor tùy máy và bản phân phối. Nếu tạo được `HelloJdk17.class` và chương trình in `Java 17`, bạn đã xác nhận cả **trình biên dịch** và **runtime** hoạt động. Tham số `--release 17` yêu cầu trình biên dịch tạo bytecode/API mục tiêu cho Java 17; trong bài này đang sử dụng chính JDK 17.

## 7. Xử lý các lỗi phổ biến theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `java` hoặc `javac` không được nhận diện | Terminal chưa nhận `Path` mới; đường dẫn sai; chỉ cài JRE | Mở terminal mới; kiểm tra `Path` và thư mục `bin` của **JDK** |
| Có `java` nhưng không có `javac` | Đang dùng runtime/JRE hoặc chọn nhầm binary | Cài **JDK 17** và đưa `bin` của JDK vào `Path` |
| `java` hiện 21/25 nhưng `javac` hiện 17, hoặc ngược lại | Có nhiều bản JDK, thứ tự `Path`/alternatives không đồng bộ | Kiểm tra đường dẫn từng lệnh, chọn cùng JDK 17 cho cả hai |
| `JAVA_HOME` báo không hợp lệ | Trỏ đến `bin`, thư mục đã bị xóa hoặc sai tên bản vá | Đặt `JAVA_HOME` tới **thư mục gốc** có `bin/java` và `bin/javac` |
| Windows báo không chạy được ứng dụng | Chọn nhầm OS/kiến trúc, hoặc môi trường không hỗ trợ | Tải bản **Windows x64/ARM64** đúng với máy; kiểm tra OS 32/64-bit |
| macOS báo `bad CPU type in executable` | Binary không phù hợp kiến trúc/môi trường | Chọn đúng **macOS x64** hoặc **macOS ARM64**, kiểm tra Rosetta |
| Linux báo `Exec format error` | Tệp thực thi không cùng CPU/OS | Kiểm tra `uname -m`, chọn bản Linux đúng kiến trúc |
| Linux báo `No such file or directory` dù file tồn tại | Có thể sai dynamic loader/libc (ví dụ glibc và musl), hoặc binary không phù hợp | Kiểm tra distro/libc; chọn gói native cho hệ đang dùng |
| macOS `Unable to locate a Java Runtime` | Chưa cài đúng JDK hoặc macOS chưa nhận diện | Cài PKG chính thức và thử `/usr/libexec/java_home -V` |
| `UnsupportedClassVersionError` khi chạy class | Bytecode được biên dịch cho Java mới hơn runtime đang chạy | So sánh phiên bản compile/run; dùng Java 17 hoặc build với `--release 17` khi phù hợp |

**Nếu terminal chạy đúng nhưng IDE lại báo sai JDK:** hãy kiểm tra riêng **Project SDK**, **Gradle JVM**, **Maven JDK** hoặc **Java Toolchain** trong IDE/cấu hình dự án. IDE và hệ điều hành có thể chọn hai JDK khác nhau; đừng sửa mã nguồn để khắc phục lỗi chọn môi trường.

**Không nên** xử lý lỗi bằng cách xóa hết các JDK khác, chạy terminal với quyền quản trị liên tục, hay cấp quyền `chmod -R 777` cho thư mục Java. Trước hết xác định đúng phiên bản, đường dẫn và kiến trúc đang được gọi.

## 8. Cập nhật, an toàn và làm việc với nhiều dự án

- **Cập nhật trong cùng nhánh 17:** Java 17 vẫn nhận các bản vá theo chu kỳ của nhà cung cấp. Định kỳ kiểm tra trang phát hành chính thức, cài bản cập nhật Java 17 phù hợp và kiểm tra lại `java`/`javac`.
- **Xác minh tệp tải:** nếu bên phát hành cung cấp mã SHA-256, đối chiếu với tệp đã tải. Trên Windows PowerShell dùng `Get-FileHash .\ten-file.msi -Algorithm SHA256`; macOS dùng `shasum -a 256 ten-file.pkg`; Linux dùng `sha256sum ten-file.tar.gz`. Giá trị phải **khớp chính xác** với checksum công bố cho đúng tệp.
- **Không khóa cứng vào một đường dẫn bản vá:** tên thư mục có thể đổi từ `jdk-17.0.x` sang `jdk-17.0.y` khi cập nhật. Sau mỗi lần nâng cấp, kiểm tra lại `JAVA_HOME` nếu bạn tự đặt bằng đường dẫn tuyệt đối.
- **Phân biệt JDK hệ thống và JDK dự án:** Maven, Gradle, IDE, CI và container có thể có cấu hình riêng. Một dự án yêu cầu Java 17 nên khai báo rõ Java toolchain/target 17; đừng trông chờ môi trường của mọi đồng đội đều mặc định là 17.
- **Bản chạy và bản build phải tương thích:** bytecode Java 17 chạy trên JVM 17 và các runtime Java mới hơn tương thích, nhưng nếu dùng API mới hơn Java 17, cần cân nhắc target bằng `--release 17` và kiểm thử theo môi trường triển khai thực tế.

## 9. Ba tình huống tự quyết định gói tải

**Tình huống 1 — Windows 11, CPU Intel Core i5:** OS là Windows, CPU x86 64-bit. Chọn **JDK 17 / Windows / x64 / MSI**. Sau cài đặt, kiểm tra `java --version` và `javac --version`.

**Tình huống 2 — MacBook chip M2:** Apple Silicon là ARM64. Chọn **JDK 17 / macOS / aarch64 / PKG** hoặc `brew install --cask temurin@17`. Xác nhận bằng `/usr/libexec/java_home -V`.

**Tình huống 3 — Ubuntu chạy trong WSL trên máy Windows x64:** Bên trong WSL cần **JDK Linux x64**, cài qua `sudo apt install openjdk-17-jdk` nếu kho gói có sẵn. Cài JDK Windows ở phía host không tự động cấu hình JDK trong Linux WSL.

**Tự kiểm tra:** Trả lời được bốn câu hỏi sau là bạn đã chọn và thiết lập đúng môi trường: (1) Máy/terminal đang chạy hệ điều hành nào? (2) Kiến trúc của môi trường cần chạy Java là gì? (3) Đã cài **JDK 17** từ nguồn tin cậy chưa? (4) `java` và `javac` có cùng phiên bản 17, biên dịch và chạy được `HelloJdk17.java` không?

## Nguồn tham khảo chính thức

- [Eclipse Adoptium — Tải Temurin 17](https://adoptium.net/temurin/releases?version=17)
- [Eclipse Adoptium — Các nền tảng và kiến trúc được hỗ trợ](https://adoptium.net/supported-platforms/)
- [Eclipse Adoptium — Cài đặt Windows MSI](https://adoptium.net/installation/windows)
- [Eclipse Adoptium — Cài đặt Linux RPM/DEB/APK](https://adoptium.net/installation/linux)
- [Microsoft Learn — Microsoft Build of OpenJDK Downloads](https://learn.microsoft.com/en-us/java/openjdk/download)
- [Ubuntu — Thiết lập môi trường Java](https://ubuntu.com/developers/docs/howto/java-setup/)
- [Red Hat — Cài Red Hat Build of OpenJDK 17 trên RHEL](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/17/html-single/installing_and_using_red_hat_build_of_openjdk_17_on_rhel/index)
- [Homebrew Formulae — temurin@17](https://formulae.brew.sh/cask/temurin@17)
- [Oracle — Hướng dẫn cài JDK 17](https://docs.oracle.com/en/java/javase/17/install/)
