# JDK theo hệ điều hành

JDK (Java Development Kit) là bộ công cụ dùng để phát triển và chạy ứng dụng Java. Một bản JDK hiện đại có trình biên dịch `javac`, máy ảo và lệnh chạy `java`, công cụ đóng gói `jar`, tài liệu `javadoc` và môi trường tương tác `jshell`. Khi học hoặc xây dựng dự án Java, hãy cài **JDK đầy đủ** thay vì chỉ cài một runtime rút gọn: lệnh `javac` là cách nhanh nhất để xác nhận máy có trình biên dịch.

Các bước cài đặt khác nhau theo Windows, macOS và Linux, nhưng kết quả cần đạt giống nhau: hệ điều hành tìm đúng thư mục JDK, biến `JAVA_HOME` trỏ đến thư mục gốc của JDK, và `java` cùng `javac` sử dụng cùng phiên bản chính.

Ví dụ lệnh bên dưới dùng JDK 21. Nếu khóa học hoặc dự án yêu cầu phiên bản khác, thay số phiên bản và tên gói tương ứng. Hãy ưu tiên phiên bản được khai báo trong cấu hình dự án, chẳng hạn Gradle toolchain hoặc Maven compiler release.

## 1. Chọn đúng bản JDK trước khi cài

Một bản JDK được xác định bởi ba yếu tố:

- **Phiên bản Java:** chọn đúng major version mà dự án yêu cầu. Hai bản cùng major version có thể khác số bản vá, ví dụ 21.0.1 và 21.0.2.
- **Nhà phân phối:** OpenJDK là dự án mã nguồn mở; các nhà cung cấp đóng gói và kiểm thử các bản phân phối như Eclipse Temurin, Oracle JDK, Amazon Corretto, Azul Zulu hoặc Microsoft Build of OpenJDK. Hãy dùng nguồn được tổ chức hoặc dự án chấp nhận.
- **Kiến trúc CPU:** chọn gói tương ứng với máy, thường là x64/amd64 hoặc ARM64/aarch64. Gói sai kiến trúc có thể không cài được hoặc không chạy được.

Có thể kiểm tra kiến trúc trên macOS và Linux bằng:

```sh
uname -m
```

Kết quả thường gặp là `x86_64` cho máy Intel/AMD 64-bit và `arm64` hoặc `aarch64` cho ARM 64-bit. Trên Windows, xem **Settings → System → About → System type** để biết hệ điều hành và bộ xử lý đang dùng.

Tải bộ cài từ trang chính thức của nhà phân phối. Kiểm tra tên phiên bản và kiến trúc trước khi cài; không lấy bộ cài từ các trang chia sẻ không rõ nguồn gốc. Nếu dự án có yêu cầu cụ thể về vendor, phiên bản hoặc giấy phép, hãy tuân theo yêu cầu đó.

## 2. Cài JDK trên Windows

### 2.1. Cài bằng bộ cài MSI

1. Xác định máy dùng x64 hay ARM64.
2. Tải gói JDK phù hợp, ví dụ Eclipse Temurin JDK 21 cho Windows.
3. Chạy tệp MSI và làm theo hướng dẫn cài đặt.
4. Nếu bộ cài có tùy chọn thêm JDK vào `PATH` hoặc tạo `JAVA_HOME`, có thể bật các tùy chọn đó. Tên tùy chọn thay đổi theo nhà phân phối và phiên bản bộ cài.
5. Hoàn tất cài đặt, sau đó mở một cửa sổ PowerShell mới.

Thư mục cài đặt thường nằm dưới `C:\Program Files\`, nhưng tên thư mục cụ thể phụ thuộc nhà phân phối và bản phát hành. Ví dụ:

```text
C:\Program Files\Eclipse Adoptium\jdk-21...
```

Dấu ba chấm biểu thị phần tên phiên bản thực tế trên máy; hãy dùng đúng thư mục đã được cài.

### 2.2. Thiết lập JAVA_HOME và PATH

`JAVA_HOME` phải trỏ đến **thư mục gốc của JDK**, không trỏ đến thư mục `bin`. Trong thư mục gốc phải có thư mục con `bin`, bên trong chứa `java.exe` và `javac.exe`.

Để thiết lập lâu dài bằng giao diện Windows:

1. Mở Start và tìm **Edit the system environment variables**.
2. Chọn **Environment Variables**.
3. Trong phần User variables (chỉ áp dụng cho tài khoản hiện tại) hoặc System variables (áp dụng toàn máy), tạo biến `JAVA_HOME`.
4. Đặt giá trị của `JAVA_HOME` là đường dẫn thư mục gốc JDK, ví dụ `C:\Program Files\Eclipse Adoptium\jdk-21...`.
5. Chọn biến `Path`, bấm Edit và thêm một mục mới: `%JAVA_HOME%\bin`.
6. Lưu các cửa sổ cấu hình. Mở PowerShell hoặc Terminal mới để nhận biến môi trường vừa thay đổi.

Không đặt dấu ngoặc kép quanh giá trị trong hộp thoại Environment Variables. Khi chỉnh `Path`, hãy thêm một mục riêng và giữ lại các mục đang có; không thay toàn bộ `Path` bằng một đường dẫn Java duy nhất.

Nếu chỉ muốn thử trong cửa sổ PowerShell hiện tại, dùng lệnh sau và thay đường dẫn bằng thư mục JDK thật:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21...'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

Các lệnh PowerShell trên chỉ thay đổi môi trường của cửa sổ hiện tại và những tiến trình được khởi chạy từ cửa sổ đó. Muốn áp dụng lâu dài, hãy dùng giao diện Environment Variables hoặc cấu hình môi trường theo chính sách của máy.

### 2.3. Kiểm tra trên Windows

```powershell
$env:JAVA_HOME
java -version
javac -version
where.exe java
where.exe javac
```

`where.exe` hiển thị các tệp thực thi tìm được theo thứ tự tra cứu trong `PATH`. Nếu có nhiều kết quả, mục đầu tiên thường là lệnh được gọi. Đường dẫn đầu tiên phải thuộc bản JDK mong muốn. Trong PowerShell, có thể xem thêm:

```powershell
Get-Command java -All
Get-Command javac -All
```

## 3. Cài JDK trên macOS

### 3.1. Chọn bộ cài đúng kiến trúc

Kiểm tra kiến trúc bằng:

```sh
uname -m
```

- `arm64`: thường là máy Apple Silicon.
- `x86_64`: thường là máy Mac dùng bộ xử lý Intel.

Tải gói macOS JDK đúng kiến trúc từ nhà phân phối đã chọn. Với bộ cài dạng `.pkg`, mở tệp và làm theo hướng dẫn. macOS thường đặt JDK trong thư mục:

```text
/Library/Java/JavaVirtualMachines/<ten-jdk>.jdk/Contents/Home
```

Tên thư mục thực tế thay đổi theo nhà phân phối và phiên bản. Không cần tự tạo thư mục này; bộ cài sẽ quản lý vị trí cài đặt.

### 3.2. Chọn JDK và thiết lập JAVA_HOME

macOS cung cấp lệnh `/usr/libexec/java_home` để tìm JDK đã cài. Liệt kê các JDK:

```sh
/usr/libexec/java_home -V
```

Chọn JDK 21 cho cửa sổ Terminal hiện tại:

```sh
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"
```

Để áp dụng cho các phiên Terminal zsh tiếp theo, thêm hai dòng `export` vào cuối tệp `~/.zshrc`, rồi nạp lại cấu hình:

```sh
source ~/.zshrc
```

zsh là shell mặc định trên các phiên bản macOS hiện đại. Nếu đang dùng bash hoặc một shell khác, hãy đặt cấu hình trong tệp khởi tạo phù hợp với shell đó. Không sao chép nguyên cấu hình zsh sang một shell có quy tắc khởi tạo khác.

Khi có nhiều JDK, tham số `-v 21` giúp chọn major version 21. Nếu phiên bản yêu cầu không được cài, lệnh `java_home` có thể báo lỗi; hãy cài đúng phiên bản trước khi đặt `JAVA_HOME`.

### 3.3. Kiểm tra trên macOS

```sh
echo "$JAVA_HOME"
java -version
javac -version
command -v java
command -v javac
```

`command -v` cho biết lệnh được shell phân giải thành đường dẫn nào. Đường dẫn đó cần dẫn đến JDK vừa chọn.

## 4. Cài JDK trên Linux

Linux có nhiều bản phân phối. Cách cài phụ thuộc hệ quản lý gói và kho phần mềm của từng bản phân phối. Hai ví dụ dưới đây dùng Debian/Ubuntu và Fedora; hãy thay tên gói theo phiên bản hệ điều hành đang dùng.

### 4.1. Debian hoặc Ubuntu

Cập nhật danh sách gói và cài JDK:

```sh
sudo apt update
sudo apt install openjdk-21-jdk
```

Gói `openjdk-21-jdk` cung cấp bộ công cụ phát triển, gồm trình biên dịch `javac`. Khả năng có sẵn gói phụ thuộc phiên bản và kho phần mềm được bật trên hệ thống. Nếu trình quản lý gói không tìm thấy gói, kiểm tra phiên bản Ubuntu/Debian và kho chính thức; không cài một gói ngẫu nhiên có tên gần giống.

### 4.2. Fedora

Cài gói phát triển OpenJDK bằng DNF:

```sh
sudo dnf install java-21-openjdk-devel
```

Hậu tố `-devel` biểu thị gói phát triển có công cụ như trình biên dịch. Nếu cần một major version khác, tìm gói tương ứng trong kho của phiên bản Fedora đang dùng.

### 4.3. Chọn phiên bản mặc định khi có nhiều JDK

Trên Debian/Ubuntu, `update-alternatives` có thể quản lý phiên bản mặc định của các lệnh Java. Xem và chọn bản cho lệnh chạy:

```sh
sudo update-alternatives --config java
```

Chọn tiếp phiên bản trình biên dịch:

```sh
sudo update-alternatives --config javac
```

Hãy bảo đảm `java` và `javac` được chọn từ cùng một major version. Không phải bản phân phối Linux nào cũng dùng `update-alternatives`; hãy dùng cơ chế quản lý phiên bản được hệ điều hành cung cấp.

### 4.4. Thiết lập JAVA_HOME trên Linux

Sau khi đã chọn đúng JDK, có thể suy ra thư mục JDK từ đường dẫn thực của `javac` trên các hệ thống có lệnh GNU `readlink -f`:

```sh
JAVAC_PATH="$(readlink -f "$(command -v javac)")"
export JAVA_HOME="$(dirname "$(dirname "$JAVAC_PATH")")"
export PATH="$JAVA_HOME/bin:$PATH"
```

Ví dụ, nếu đường dẫn thực của trình biên dịch là `/usr/lib/jvm/java-21-openjdk-amd64/bin/javac`, thì `JAVA_HOME` sẽ là `/usr/lib/jvm/java-21-openjdk-amd64`.

Để lưu cấu hình cho các phiên shell mới, thêm các dòng `export` vào tệp khởi tạo của shell đang dùng, thường là `~/.bashrc` với bash hoặc `~/.zshrc` với zsh. Sau đó nạp lại tệp tương ứng, ví dụ:

```sh
source ~/.bashrc
```

Nếu hệ thống không có `readlink -f`, lấy đường dẫn JDK từ thông tin gói đã cài hoặc công cụ quản lý phiên bản của bản phân phối. Không đặt `JAVA_HOME` thành `/usr/bin` hay thành thư mục `bin` của JDK.

### 4.5. Kiểm tra trên Linux

```sh
echo "$JAVA_HOME"
java -version
javac -version
command -v java
command -v javac
```

Nếu có nhiều JDK, một số bản phân phối còn hỗ trợ `which -a java` để liệt kê các lệnh cùng tên trên `PATH`.

## 5. Xác nhận JDK hoạt động bằng cách biên dịch chương trình

Chỉ chạy được `java -version` chưa đủ để chứng minh đã cài JDK đầy đủ; máy có thể chỉ tìm thấy runtime. Hãy kiểm tra cả `javac`, sau đó biên dịch và chạy một chương trình nhỏ.

Tạo tệp `JdkCheck.java` với nội dung:

```java
public class JdkCheck {
    public static void main(String[] args) {
        System.out.println("JDK is ready");
    }
}
```

Mở Terminal tại thư mục chứa tệp và chạy:

```sh
javac JdkCheck.java
java JdkCheck
```

Kết quả mong đợi:

```text
JDK is ready
```

Nếu lệnh `javac` tạo được `JdkCheck.class` và lệnh `java` in đúng dòng trên, trình biên dịch và runtime cơ bản đang hoạt động. Xóa các tệp thử nghiệm sau khi hoàn tất nếu không cần giữ lại.

Đối chiếu major version của hai công cụ:

```sh
java -version
javac -version
```

Ví dụ, nếu dự án yêu cầu Java 21, cả hai lệnh cần báo phiên bản major 21. Số bản vá và cách trình bày chuỗi phiên bản có thể khác theo nhà phân phối.

## 6. Hiểu và cấu hình JAVA_HOME, PATH

Hai biến này có vai trò khác nhau:

- `JAVA_HOME` xác định thư mục gốc của JDK mà công cụ xây dựng hoặc script có thể sử dụng.
- `PATH` là danh sách thư mục hệ điều hành tìm kiếm khi người dùng gõ một lệnh. Đưa `%JAVA_HOME%\bin` (Windows) hoặc `$JAVA_HOME/bin` (macOS/Linux) vào `PATH` giúp gọi `java`, `javac` từ mọi thư mục.

Ví dụ cấu trúc đúng:

```text
JAVA_HOME
└── JDK root
    └── bin
        ├── java
        ├── javac
        ├── jar
        └── javadoc
```

Không đặt `JAVA_HOME` thành đường dẫn kết thúc bằng `/bin` hoặc `\bin`. Nếu `JAVA_HOME` trỏ sai, nhiều công cụ sẽ không tìm thấy cấu trúc JDK dù lệnh `java` vẫn có thể chạy nhờ một mục khác trong `PATH`.

Thứ tự các mục trong `PATH` có ý nghĩa. Khi có nhiều JDK, hệ điều hành thường chạy lệnh ở mục phù hợp đầu tiên. Vì vậy, hãy kiểm tra đường dẫn thực tế thay vì chỉ nhìn giá trị `JAVA_HOME`.

## 7. Sử dụng nhiều phiên bản JDK

Một máy có thể cài nhiều major version để phục vụ các dự án khác nhau. Cách chọn bản mặc định tùy hệ điều hành:

- **Windows:** đổi `JAVA_HOME` và thứ tự mục `%JAVA_HOME%\bin` trong `Path`, sau đó mở Terminal mới. Có thể dùng biến môi trường theo từng cửa sổ PowerShell để thử mà không thay đổi cấu hình lâu dài.
- **macOS:** dùng `/usr/libexec/java_home -v <major>` để lấy đường dẫn của major version cần dùng, rồi đặt `JAVA_HOME`.
- **Debian/Ubuntu:** dùng `update-alternatives --config java` và `update-alternatives --config javac` nếu các bản JDK đã được đăng ký với hệ thống.

Không giả định rằng mọi công cụ đều lấy Java từ cùng một nơi. IDE có thể có cấu hình Project SDK riêng; Gradle có thể dùng JVM được cấu hình trong IDE hoặc toolchain của dự án; Maven cũng có thể chạy bằng một JDK khác với lệnh bạn đang kiểm tra trong Terminal.

Khi cần xác nhận JVM mà công cụ xây dựng đang sử dụng, chạy lệnh tương ứng từ thư mục dự án:

```sh
./gradlew -version
mvn -version
```

Chỉ chạy lệnh của công cụ mà dự án thực sự sử dụng. Trên Windows, Gradle Wrapper thường được gọi bằng `gradlew.bat -version`. Nếu vừa đổi JDK nhưng IDE hoặc Gradle vẫn báo bản cũ, đóng và mở lại Terminal/IDE; với Gradle, có thể dừng daemon cũ bằng:

```sh
./gradlew --stop
```

Sau đó chạy lại lệnh kiểm tra. Nếu dự án có cấu hình toolchain, hãy kiểm tra cấu hình đó trước khi thay đổi JDK mặc định toàn hệ thống.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Windows báo `java is not recognized`; macOS/Linux báo `command not found` | Thư mục `bin` của JDK chưa có trong `PATH`, hoặc Terminal được mở trước khi cập nhật biến môi trường | Kiểm tra `JAVA_HOME`, thêm đúng thư mục `bin` vào `PATH`, mở Terminal mới rồi thử lại |
| `java` chạy được nhưng `javac` không tồn tại | Máy chỉ có runtime hoặc `PATH` đang trỏ đến một bản cài không có công cụ phát triển | Cài JDK đầy đủ và bảo đảm `PATH` trỏ đến thư mục `bin` của JDK đó |
| `java -version` báo phiên bản cũ | Một JDK khác đứng trước trong `PATH`, hoặc hệ thống đang chọn bản mặc định khác | Dùng `where.exe java` trên Windows hoặc `command -v java`/ `which -a java` trên macOS/Linux; sửa thứ tự `PATH` hoặc chọn lại alternatives |
| `JAVA_HOME` không hợp lệ | Biến trỏ đến `bin`, đến một thư mục không tồn tại hoặc đến JDK đã bị gỡ | Đặt lại biến về thư mục gốc JDK thực tế, nơi có thư mục con `bin` |
| Terminal dùng đúng Java nhưng IDE dùng bản khác | IDE lưu Project SDK hoặc Gradle JVM riêng | Chọn đúng JDK trong cấu hình SDK/JVM của dự án và khởi động lại tiến trình IDE nếu cần |
| `java` và `javac` có major version khác nhau | Hai lệnh được phân giải từ các bản cài khác nhau | Kiểm tra đường dẫn của cả hai lệnh; đồng bộ `PATH`, `JAVA_HOME` và cơ chế chọn phiên bản mặc định |
| Bộ cài không chạy hoặc báo sai kiến trúc | Tải nhầm gói x64/ARM64 hoặc nhầm hệ điều hành | Kiểm tra kiến trúc máy, tải lại đúng gói từ nhà phân phối |
| Trình quản lý gói không tìm thấy gói JDK | Kho phần mềm hoặc phiên bản hệ điều hành chưa cung cấp major version đó | Kiểm tra kho chính thức và tên gói cho bản phân phối; dùng gói chính thức của nhà cung cấp nếu cần |

Một số lỗi biên dịch hoặc chạy ứng dụng không xuất phát từ việc cài JDK. Ví dụ, lỗi do dự án yêu cầu Java mới hơn, plugin Gradle không tương thích, hoặc cấu hình source/target không khớp cần được xử lý ở cấu hình dự án. Trước khi thay đổi mã nguồn, hãy xác định chính xác phiên bản JDK mà dự án yêu cầu và phiên bản mà công cụ xây dựng đang dùng.

## 9. Checklist sau khi cài

Trước khi bắt đầu học hoặc chạy dự án, kiểm tra lần lượt:

1. Đã chọn đúng major version theo yêu cầu dự án.
2. Bộ cài phù hợp với hệ điều hành và kiến trúc CPU.
3. `JAVA_HOME` trỏ đến thư mục gốc JDK.
4. `PATH` có thư mục `bin` của JDK mong muốn.
5. `java -version` và `javac -version` báo cùng major version.
6. Chương trình `JdkCheck.java` biên dịch và chạy thành công.
7. IDE và công cụ xây dựng của dự án cũng đang sử dụng JDK đúng phiên bản.

Khi hoàn thành các bước này, máy đã có môi trường JDK cơ bản để biên dịch và chạy chương trình Java.