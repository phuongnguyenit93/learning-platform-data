# Quản lý nhiều JDK trên cùng một máy

Cài đặt nhiều phiên bản JDK trên một máy là cách phổ biến để phát triển, bảo trì và kiểm thử các dự án Java có yêu cầu phiên bản khác nhau. Một dự án cũ có thể cần Java 8 hoặc 11, trong khi dự án mới dùng Java 17 hoặc 21. Máy của nhà phát triển, máy build và môi trường triển khai cũng có thể sử dụng các phiên bản khác nhau.

Các JDK có thể cùng tồn tại trong những thư mục cài đặt riêng. Điều cần kiểm soát là **JDK nào được chọn cho từng terminal, IDE và dự án**. Nếu cấu hình không rõ ràng, lệnh `java`, `javac` hoặc công cụ build có thể gọi nhầm phiên bản, dẫn đến lỗi biên dịch, lỗi tương thích hoặc kết quả khác nhau giữa máy cá nhân và CI.

## 1. Hiểu cách nhiều JDK cùng tồn tại

Một JDK thường được cài trong một thư mục riêng, ví dụ:

```text
Windows:
C:\Java\jdk-17
C:\Java\jdk-21

Linux:
/usr/lib/jvm/jdk-17
/usr/lib/jvm/jdk-21

macOS:
/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home
```

Đây là các đường dẫn minh họa; vị trí thực tế phụ thuộc nhà cung cấp JDK, trình cài đặt, kiến trúc máy và hệ điều hành. Mỗi thư mục chứa một bộ công cụ độc lập, bao gồm trình chạy `java`, trình biên dịch `javac` và các công cụ JDK khác.

Việc cài thêm JDK thường không tự động làm hỏng JDK hiện có. Xung đột xảy ra khi môi trường chọn sai executable hoặc khi một ứng dụng dùng JDK khác với phiên bản mà dự án yêu cầu.

Cần phân biệt ba khái niệm:

- **JDK đã cài:** tất cả bộ JDK đang có trên máy.
- **JDK mặc định của terminal:** bộ JDK mà lệnh `java` và `javac` được tìm thấy thông qua cấu hình môi trường hiện tại.
- **JDK của dự án:** phiên bản mà dự án yêu cầu để biên dịch, chạy kiểm thử hoặc đóng gói. IDE và công cụ build có thể chọn JDK riêng cho dự án.

Một máy có thể cài JDK 17 và JDK 21, dùng JDK 21 mặc định trong terminal, nhưng vẫn biên dịch một dự án bằng toolchain Java 17. Không cần gỡ một JDK chỉ vì dự án khác đang dùng phiên bản mới hơn.

### Cài đặt song song các phiên bản

Chọn bản phân phối JDK phù hợp với chính sách của nhóm và nền tảng cần hỗ trợ. Một số bản phân phối OpenJDK phổ biến gồm Eclipse Temurin, Oracle JDK, Amazon Corretto, Microsoft Build of OpenJDK và Azul Zulu. Chúng có thể khác nhau về lịch phát hành, hỗ trợ dài hạn, giấy phép và cách đóng gói; hãy dùng nguồn tải chính thức và thống nhất bản phân phối trong dự án khi cần khả năng tái lập.

- **Windows:** chạy bộ cài cho từng phiên bản và đặt mỗi JDK vào thư mục riêng, chẳng hạn `C:\Java\jdk-17` và `C:\Java\jdk-21`. Không chọn cùng một thư mục đích cho hai phiên bản.
- **macOS:** cài từng gói JDK hoặc archive riêng. Các gói cài đặt thường đăng ký JDK trong `/Library/Java/JavaVirtualMachines`; dùng `/usr/libexec/java_home -V` để kiểm tra hệ thống nhận diện những bản nào.
- **Linux:** có thể cài nhiều gói JDK song song bằng package manager nếu repository của bản phân phối cung cấp các phiên bản đó. Ví dụ trên hệ Debian/Ubuntu có thể là `openjdk-17-jdk` và `openjdk-21-jdk`; trên Fedora/RHEL có thể là `java-17-openjdk-devel` và `java-21-openjdk-devel`. Tên gói và phiên bản sẵn có tùy repository và phiên bản hệ điều hành.

Sau khi cài, xác minh từng thư mục có `bin/java` và `bin/javac`. Package manager có thể tự cập nhật alternatives hoặc PATH; hãy kiểm tra lựa chọn mặc định trước khi thay đổi cấu hình.

## 2. Vai trò của JAVA_HOME và PATH

Hai biến môi trường thường quyết định JDK được sử dụng:

- **JAVA_HOME** trỏ đến thư mục gốc của JDK được chọn. Ví dụ: `C:\Java\jdk-21` hoặc `/usr/lib/jvm/jdk-21`. Không thêm `bin` vào cuối giá trị.
- **PATH** là danh sách thư mục mà hệ điều hành tìm executable khi người dùng nhập lệnh. Để gọi công cụ của JDK được chọn, thêm `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên macOS/Linux vào PATH.

Khi nhiều thư mục chứa `java` xuất hiện trong PATH, hệ điều hành thường dùng executable được tìm thấy đầu tiên theo thứ tự tìm kiếm. Vì vậy, thứ tự PATH rất quan trọng. Nếu thư mục JDK 17 đứng trước JDK 21, lệnh `java` có thể vẫn chạy Java 17 dù JAVA_HOME đã trỏ tới JDK 21.

**JAVA_HOME và PATH có liên quan nhưng không phải cùng một thứ.** Chỉ thay đổi JAVA_HOME chưa chắc làm thay đổi lệnh `java` đang được gọi; PATH phải trỏ tới thư mục `bin` của JDK mong muốn. Ngược lại, PATH có thể gọi một executable Java dù JAVA_HOME chưa được đặt.

Ngoài ra, `java` và `javac` cần được kiểm tra riêng. Một cấu hình PATH lẫn lộn có thể khiến trình chạy đến từ JDK này nhưng trình biên dịch đến từ JDK khác.

## 3. Kiểm tra các JDK và phiên bản đang được sử dụng

Trước khi đổi cấu hình, hãy xác định máy đang gọi công cụ nào. Các lệnh sau chỉ kiểm tra, không thay đổi cài đặt. Dùng `-version` để tương thích cả với các bản JDK cũ như Java 8.

### Trên Windows

Mở PowerShell:

```powershell
java -version
javac -version

# Liệt kê các lệnh java tìm thấy trong PATH
where.exe java

# Xem tất cả kết quả phân giải lệnh java trong PowerShell
Get-Command java -All

# Kiểm tra biến JAVA_HOME hiện tại
$env:JAVA_HOME
```

Dùng `where.exe` để gọi chương trình Windows có tên `where`; trong PowerShell, `where` còn có thể là bí danh của `Where-Object`.

### Trên Linux và macOS

Mở terminal:

```bash
java -version
javac -version

# Xem các vị trí java được shell tìm thấy
type -a java
type -a javac

# Kiểm tra JAVA_HOME
echo "$JAVA_HOME"
```

Trên macOS có thể liệt kê các JDK mà hệ thống nhận diện bằng:

```bash
/usr/libexec/java_home -V
```

Trên một số bản Linux dùng cơ chế alternatives, có thể xem các lựa chọn Java bằng:

```bash
update-alternatives --list java
update-alternatives --list javac
```

Tên và khả năng của lệnh alternatives tùy bản phân phối. Nếu lệnh không có, hãy kiểm tra tài liệu của trình quản lý gói đang dùng.

### Xác định thư mục runtime thực tế

Để kiểm tra JVM đang chạy lấy thông tin từ đâu, dùng:

```bash
java -XshowSettings:properties -version
```

Trong phần kết quả, tìm thuộc tính `java.home`. Đây là đường dẫn runtime đang được tiến trình Java sử dụng. Có thể đối chiếu nó với thư mục JDK dự định chọn.

Không nên chỉ dựa vào tên thư mục cài đặt. Hãy kiểm tra cả phiên bản của `java`, `javac` và đường dẫn thực tế để tránh trường hợp PATH trỏ tới một bản cài khác.

## 4. Chuyển JDK tạm thời trên Windows

Nếu chỉ cần dùng JDK khác trong một cửa sổ PowerShell, đặt biến môi trường cho phiên làm việc đó:

```powershell
$env:JAVA_HOME = 'C:\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Thay đường dẫn ví dụ bằng thư mục JDK thực tế trên máy. Sau khi chạy, cửa sổ PowerShell hiện tại sẽ ưu tiên `bin` của JDK 21. Những terminal khác và cấu hình hệ thống không bị thay đổi.

Để chuyển sang JDK 17 trong một cửa sổ PowerShell khác hoặc ngay trong cửa sổ hiện tại, thay giá trị JAVA_HOME:

```powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Lưu ý: nếu thực hiện thao tác prepend PATH nhiều lần trong cùng một phiên shell, PATH có thể chứa nhiều mục JDK lặp lại. Cách sạch hơn là mở một terminal mới cho mỗi cấu hình, hoặc cập nhật PATH theo cách có kiểm soát.

Để thiết lập lâu dài trên Windows:

1. Mở **System Properties** và chọn **Environment Variables**.
2. Tạo hoặc cập nhật biến người dùng hay biến hệ thống `JAVA_HOME` trỏ tới thư mục gốc của JDK mặc định.
3. Trong biến `Path`, thêm mục `%JAVA_HOME%\bin`.
4. Đặt mục này trước các đường dẫn Java cũ nếu chúng có thể được tìm thấy trước.
5. Mở terminal mới và kiểm tra lại `java -version`, `javac -version`, `where.exe java`.

Terminal đang mở thường giữ bản sao môi trường từ lúc khởi chạy. Sau khi sửa biến môi trường bằng giao diện Windows, hãy mở terminal mới để nhận cấu hình cập nhật. Nếu máy có cài Java thông qua nhiều trình cài đặt hoặc package manager, kiểm tra các mục PATH do chúng thêm vào để tránh đường dẫn cũ chiếm ưu tiên.

## 5. Chuyển JDK trên macOS

macOS có tiện ích `/usr/libexec/java_home` để tìm JDK đã đăng ký với hệ thống. Khi có nhiều JDK, có thể chọn phiên bản mong muốn:

```bash
# Liệt kê JDK đã được hệ thống nhận diện
/usr/libexec/java_home -V

# Chọn JDK 21 cho terminal hiện tại
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

Để chuyển sang JDK 17:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

Tùy chọn `-v 21` yêu cầu một JDK phù hợp với phiên bản 21. Nếu không tìm thấy bản cài tương ứng, lệnh có thể không trả về đường dẫn hợp lệ; hãy kiểm tra danh sách bằng `-V` trước.

Nếu muốn chọn mặc định cho các terminal mới, có thể đặt các dòng cấu hình phù hợp vào file khởi tạo shell, thường là `~/.zshrc` với zsh hoặc `~/.bash_profile`/`~/.bashrc` với bash tùy cách cấu hình. Sau khi sửa, mở terminal mới hoặc nạp lại file cấu hình. Nếu thường xuyên chuyển phiên bản theo dự án, trình quản lý phiên bản Java có thể tiện hơn việc sửa file shell liên tục.

## 6. Chuyển JDK trên Linux

Trên Linux, JDK thường được cài vào một thư mục dưới `/usr/lib/jvm`, nhưng vị trí có thể khác tùy bản phân phối và cách cài. Kiểm tra thư mục cài đặt:

```bash
ls /usr/lib/jvm
```

Để chọn JDK 21 trong terminal hiện tại:

```bash
export JAVA_HOME=/usr/lib/jvm/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

Thay `/usr/lib/jvm/jdk-21` bằng đường dẫn thực tế. Nếu muốn giữ cấu hình cho các terminal mới, thêm các dòng `export` vào file khởi tạo shell thích hợp như `~/.bashrc` hoặc `~/.zshrc`.

Một số bản phân phối Linux quản lý các lệnh mặc định thông qua alternatives. Trên hệ Debian/Ubuntu, có thể chọn đường dẫn cho `java` và `javac` bằng:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
```

Trên các hệ dùng lệnh `alternatives`, cú pháp thường là:

```bash
sudo alternatives --config java
sudo alternatives --config javac
```

Chọn đúng mục JDK mong muốn trong danh sách. Hãy kiểm tra cả `java` lẫn `javac`, vì thay đổi một lệnh không đảm bảo lệnh còn lại được chuyển theo. Cơ chế alternatives chủ yếu điều khiển các liên kết lệnh hệ thống; nó không phải lúc nào cũng tự cập nhật JAVA_HOME. Nếu ứng dụng hoặc build tool dựa vào JAVA_HOME, hãy cấu hình biến này riêng.

Việc thay đổi alternatives thường ảnh hưởng tới người dùng khác trên máy. Chỉ dùng khi bạn thực sự muốn đổi Java mặc định toàn hệ thống và có quyền quản trị. Với nhu cầu riêng của một dự án hoặc một tài khoản, cấu hình trong shell hoặc dùng version manager thường ít ảnh hưởng hơn.

## 7. Dùng trình quản lý phiên bản Java

Khi phải chuyển đổi JDK thường xuyên, có thể dùng công cụ quản lý phiên bản thay vì chỉnh JAVA_HOME và PATH bằng tay.

### SDKMAN!

SDKMAN! phổ biến trên Linux và macOS, đồng thời có thể dùng trong môi trường Linux như WSL. Công cụ cho phép cài nhiều bản JDK, chọn bản cho terminal hiện tại hoặc đặt bản mặc định.

Một quy trình điển hình:

```bash
# Liệt kê các bản Java có thể cài
sdk list java

# Cài một candidate cụ thể lấy từ danh sách
sdk install java <candidate>

# Chuyển bản JDK cho terminal hiện tại
sdk use java <candidate>

# Đặt bản mặc định cho các terminal mới
sdk default java <candidate>

# Kiểm tra phiên bản đang dùng
java -version
javac -version
```

`<candidate>` là mã phiên bản đầy đủ do `sdk list java` hiển thị; không nên tự đoán mã vì nó thay đổi theo bản phát hành và nhà cung cấp. Lệnh `sdk use` chỉ đổi phiên làm việc hiện tại, còn `sdk default` đặt lựa chọn mặc định.

### jEnv

jEnv là công cụ chuyển phiên bản Java trên macOS/Linux bằng cách quản lý các shim và cấu hình theo thư mục. Nó thường không tự tải và cài JDK; trước hết cần cài JDK bằng trình cài đặt hoặc package manager, sau đó đăng ký đường dẫn JDK với jEnv.

Ví dụ quy trình sau khi jEnv đã được cài và cấu hình trong shell:

```bash
# Đăng ký một JDK đã có trên máy
jenv add /path/to/jdk-21

# Liệt kê các phiên bản đã đăng ký
jenv versions

# Chọn phiên bản cho thư mục dự án hiện tại
jenv local <version>

# Chọn phiên bản mặc định của người dùng
jenv global <version>

java -version
javac -version
```

Thay `<version>` bằng đúng tên phiên bản hiển thị trong `jenv versions`. Nếu công cụ build cần JAVA_HOME, có thể bật plugin export của jEnv bằng `jenv enable-plugin export`, sau đó mở terminal mới và xác minh giá trị JAVA_HOME. `jenv local` thường tạo hoặc cập nhật file cấu hình phiên bản trong thư mục hiện tại; hãy kiểm tra file đó có phù hợp để đưa vào Git hay không theo quy ước của nhóm.

Nếu một nhóm dùng SDKMAN!, nhóm khác dùng jEnv, hoặc PATH tự chỉnh tay cùng lúc, việc tìm nguyên nhân khi chọn sai JDK sẽ khó hơn. Nên thống nhất một cơ chế quản lý trong môi trường phát triển của nhóm.

## 8. Chọn JDK riêng cho từng dự án

JDK mặc định của terminal không nhất thiết là JDK mà dự án cần. Có thể chọn toolchain theo yêu cầu của dự án để mọi thành viên và máy build sử dụng cùng phiên bản ngôn ngữ/API mục tiêu.

### Với Gradle

Nếu dự án dùng Java plugin của Gradle và file build sử dụng Groovy DSL, có thể khai báo toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Cấu hình này yêu cầu Gradle sử dụng JDK phù hợp phiên bản 21 cho các tác vụ Java có hỗ trợ toolchain, chẳng hạn biên dịch và kiểm thử. Tùy cấu hình Gradle và môi trường, JDK phù hợp có thể được phát hiện từ máy hoặc được cấp phát tự động nếu dự án đã thiết lập cơ chế provisioning.

Cần phân biệt JDK chạy chính tiến trình Gradle với JDK toolchain dùng để biên dịch hoặc chạy tác vụ của dự án. `JAVA_HOME` thường ảnh hưởng tới JVM khởi chạy Gradle; toolchain cho phép dự án chọn một JDK khác cho tác vụ Java. Kiểm tra `gradle --version` để biết JVM đang chạy Gradle và đảm bảo phiên bản Gradle tương thích với JVM đó.

### Với Maven

Maven có thể chạy bằng một JDK và chọn JDK khác cho một số plugin thông qua Maven Toolchains. Nhóm dự án khai báo các JDK có sẵn trong file cấu hình toolchains của người dùng, thường ở `~/.m2/toolchains.xml`, rồi cấu hình plugin tương ứng trong dự án để yêu cầu phiên bản phù hợp.

Việc chỉ tạo `toolchains.xml` không tự động buộc mọi plugin Maven sử dụng JDK đó. Cần kiểm tra cấu hình plugin và kết quả build để chắc chắn toolchain được áp dụng. Lệnh `mvn -version` cho biết Java mà Maven đang dùng để khởi chạy.

### Với IDE

IDE thường có cấu hình JDK riêng ở cấp máy, dự án hoặc module. Ví dụ:

- IntelliJ IDEA có Project SDK và cấu hình SDK riêng cho module hoặc build tool.
- Eclipse quản lý các JRE/JDK đã cài trong Installed JREs và cho phép dự án chọn execution environment.
- Visual Studio Code với Java extensions cho phép đăng ký các runtime Java và chọn runtime phù hợp.

Tên mục cấu hình thay đổi theo phiên bản IDE. Sau khi chọn JDK, hãy kiểm tra cả Project SDK, mức ngôn ngữ, cấu hình build tool và runtime dùng để chạy ứng dụng. Nếu terminal chạy Java 21 nhưng IDE build bằng Java 17, đó có thể là do hai nơi đang có cấu hình riêng.

## 9. Biên dịch cho một phiên bản Java thấp hơn

Một tình huống thường gặp là máy đã cài JDK mới nhưng dự án cần chạy trên Java cũ hơn. Có thể dùng tùy chọn `--release` của `javac` để chọn phiên bản Java mục tiêu được hỗ trợ.

Ví dụ, dùng JDK 21 để biên dịch mã nguồn hướng tới Java 17:

```bash
javac --release 17 -d out src/HelloApp.java
```

`--release 17` điều khiển phiên bản ngôn ngữ, bytecode và tập API nền tảng Java được phép sử dụng cho mục tiêu 17. Điều này giúp tránh biên dịch bằng API chỉ có ở Java 21 rồi vô tình triển khai trên Java 17.

Sau khi biên dịch, cần kiểm thử chương trình bằng runtime Java 17 thực tế. `--release` không bảo đảm các thư viện bên ngoài, native library, cấu hình hệ điều hành hoặc hành vi lúc chạy đều tương thích.

Nếu biên dịch mặc định bằng JDK 21 rồi chạy bytecode đó trên Java 17, có thể gặp lỗi:

```text
UnsupportedClassVersionError
```

Lỗi này thường cho biết JVM đang chạy quá cũ để hiểu phiên bản bytecode của lớp. Cách xử lý là chạy bằng runtime đủ mới hoặc biên dịch lại với phiên bản mục tiêu phù hợp, đồng thời kiểm tra API và dependency.

## 10. Những lỗi thường gặp khi có nhiều JDK

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `java -version` không đúng phiên bản mong muốn | PATH ưu tiên một thư mục Java khác. | Dùng `where.exe java` trên Windows hoặc `type -a java` trên macOS/Linux; sửa thứ tự PATH. |
| JAVA_HOME đúng nhưng lệnh `java` vẫn chạy bản cũ | PATH chưa chứa `%JAVA_HOME%\bin` hoặc `$JAVA_HOME/bin`, hoặc mục Java cũ đứng trước. | Kiểm tra PATH và mở terminal mới sau khi sửa. |
| `javac` và `java` báo hai phiên bản khác nhau | Các executable được phân giải từ những thư mục khác nhau. | Kiểm tra riêng đường dẫn của cả hai lệnh và đồng bộ cấu hình. |
| Terminal dùng đúng JDK nhưng IDE dùng bản khác | IDE có Project SDK hoặc runtime riêng. | Kiểm tra cấu hình JDK trong IDE và cấu hình build tool. |
| Maven hoặc Gradle dùng JDK không như dự án mong muốn | Build tool được khởi chạy bằng JDK khác hoặc toolchain chưa được cấu hình. | Dùng `mvn -version`, `gradle --version` và kiểm tra toolchains. |
| Mở terminal mới nhưng phiên bản không đổi | File cấu hình shell chưa được nạp hoặc biến hệ thống vẫn ưu tiên đường dẫn cũ. | Kiểm tra shell đang dùng, file khởi tạo và PATH thực tế. |
| Chạy ứng dụng gặp UnsupportedClassVersionError | Runtime thấp hơn phiên bản bytecode đã biên dịch. | Chọn runtime đủ mới hoặc biên dịch với `--release` phù hợp. |
| Công cụ hoạt động ở máy này nhưng thất bại trên máy khác | Khác phiên bản JDK, kiến trúc CPU, biến môi trường hoặc dependency. | Ghi rõ toolchain trong dự án và xác minh môi trường CI/deployment. |

Một nguyên tắc quan trọng là kiểm tra phiên bản ở đúng nơi thực thi. Chạy `java -version` trong terminal không chứng minh rằng IDE, Maven, Gradle, service hoặc pipeline CI cũng đang dùng cùng JDK.

## 11. Quy trình thực tế khi chuyển giữa nhiều JDK

Khi nhận một dự án mới hoặc chuyển phiên bản Java, có thể làm theo trình tự sau:

1. **Đọc yêu cầu của dự án:** xác định phiên bản Java tối thiểu, phiên bản dùng để build và phiên bản runtime ở môi trường đích.
2. **Kiểm tra JDK đã cài:** dùng lệnh liệt kê phù hợp hệ điều hành và xác định đường dẫn từng JDK.
3. **Chọn cách quản lý:** dùng cấu hình JAVA_HOME/PATH cho trường hợp đơn giản, hoặc version manager/toolchain khi phải chuyển đổi thường xuyên.
4. **Chọn JDK cho terminal:** cập nhật biến môi trường trong phạm vi phù hợp và kiểm tra `java -version`, `javac -version`.
5. **Cấu hình IDE và build tool:** chọn Project SDK, Gradle toolchain hoặc Maven Toolchains theo yêu cầu dự án.
6. **Biên dịch và kiểm thử:** chạy build sạch, kiểm tra target release và chạy thử bằng runtime mục tiêu.
7. **Ghi lại yêu cầu:** lưu phiên bản Java cần thiết trong tài liệu dự án, cấu hình build và pipeline CI để thành viên khác có thể tái tạo môi trường.

Ví dụ, một máy có cả JDK 17 và 21 có thể được tổ chức như sau:

| Phạm vi | JDK được chọn | Lý do |
|---|---:|---|
| Terminal mặc định | 21 | Dùng cho học tập và dự án mới. |
| Dự án A | 17 | Dự án đang duy trì trên Java 17. |
| Dự án B | 21 | Dự án mới yêu cầu Java 21. |
| CI của dự án A | 17 | Đảm bảo build và test theo môi trường mục tiêu. |

Bảng trên chỉ là ví dụ về cách phân công phiên bản; giá trị thực tế phải theo yêu cầu của từng dự án.

## 12. Nguyên tắc quản lý lâu dài

- Cài mỗi JDK vào thư mục riêng và giữ nguyên các đường dẫn cài đặt để IDE, script và build tool tham chiếu ổn định.
- Chọn một JDK mặc định rõ ràng cho terminal; tránh để nhiều thư mục Java không cần thiết cùng cạnh tranh ở đầu PATH.
- Đặt JAVA_HOME trỏ tới thư mục gốc của JDK và kiểm tra PATH có trỏ tới `bin` tương ứng.
- Cấu hình toolchain theo dự án để việc build không phụ thuộc hoàn toàn vào JDK mặc định của máy lập trình viên.
- Kiểm tra riêng JDK chạy IDE/build tool và JDK dùng để biên dịch, chạy ứng dụng.
- Cập nhật các bản vá bảo mật theo chính sách của tổ chức; trước khi gỡ phiên bản cũ, xác nhận không còn dự án, IDE, service hoặc script nào phụ thuộc vào nó.
- Ghi rõ phiên bản JDK trong README, tài liệu onboarding hoặc cấu hình CI để môi trường của nhóm nhất quán.

Quản lý nhiều JDK tốt giúp một máy phát triển có thể hỗ trợ nhiều thế hệ dự án Java cùng lúc. Khi tách bạch JDK đã cài, JDK mặc định của terminal và toolchain của từng dự án, việc chuyển phiên bản trở nên có kiểm soát, dễ kiểm tra và ít gây lỗi môi trường.
