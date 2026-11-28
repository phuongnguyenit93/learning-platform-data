# Cấu hình JAVA_HOME, PATH và kiểm tra java với javac

Để phát triển bằng Java 27, máy cần có **JDK 27** và hệ điều hành phải tìm được các lệnh trong thư mục công cụ của JDK. Hai biến môi trường thường dùng là **JAVA_HOME** và **PATH**:

- **JAVA_HOME** trỏ tới thư mục gốc của JDK đang chọn. Các công cụ xây dựng và môi trường phát triển có thể đọc biến này để xác định bộ JDK cần dùng.
- **PATH** chứa danh sách thư mục mà hệ điều hành tìm kiếm khi người dùng chạy một lệnh. Thêm thư mục **bin** của JDK vào PATH để có thể gọi **java** và **javac** từ bất kỳ thư mục làm việc nào.

Khi cấu hình, hãy dùng đường dẫn thực tế của JDK 27 đã cài trên máy. Tên thư mục có thể khác nhau theo nhà cung cấp và số bản cập nhật.

## 1. Phân biệt JDK, JAVA_HOME và PATH

**JDK (Java Development Kit)** là bộ công cụ dùng để phát triển ứng dụng Java. Trong đó có:

- **java**: khởi chạy máy ảo Java để chạy chương trình.
- **javac**: biên dịch mã nguồn Java thành bytecode.
- Các công cụ phát triển và chẩn đoán khác đi kèm JDK.

Khi lập trình, hãy cài JDK 27. Chỉ có lệnh chạy Java mà thiếu trình biên dịch **javac** thì chưa đủ cho quy trình biên dịch thông thường.

| Thành phần | Giá trị cần cấu hình | Vai trò |
|---|---|---|
| **JAVA_HOME** | Đường dẫn tới thư mục gốc JDK 27 | Cho công cụ phát triển biết vị trí JDK |
| **PATH** | Đường dẫn tới thư mục **bin** của JDK | Cho phép gọi **java**, **javac** từ terminal |
| **java** | Tệp thực thi trong **JAVA_HOME/bin** | Chạy chương trình Java |
| **javac** | Tệp thực thi trong **JAVA_HOME/bin** | Biên dịch mã nguồn Java |

Ví dụ, nếu JDK được cài tại **C:\Program Files\Java\jdk-27** trên Windows thì:

- **JAVA_HOME** là **C:\Program Files\Java\jdk-27**.
- Mục PATH cần thêm là **%JAVA_HOME%\bin**.
- Không đặt **JAVA_HOME** thành **C:\Program Files\Java\jdk-27\bin**; biến này trỏ tới thư mục gốc JDK.

Trên macOS và Linux, nguyên tắc tương tự: **JAVA_HOME** trỏ tới thư mục gốc, còn PATH chứa thư mục **bin** bên trong thư mục đó.

## 2. Xác định thư mục cài đặt JDK 27

Trước khi sửa biến môi trường, cần xác định đúng thư mục JDK. Đường dẫn cài đặt không cố định giữa các nhà cung cấp hoặc cách cài đặt.

### Windows

Mở PowerShell và kiểm tra các lệnh Java hiện có:

~~~powershell
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
~~~

Nếu JDK đã được cài nhưng chưa có trong PATH, các lệnh trên có thể chưa tìm thấy kết quả. Khi đó, kiểm tra thư mục cài đặt mà bạn đã chọn hoặc thư mục cài đặt của nhà cung cấp JDK. Thư mục gốc hợp lệ phải chứa thư mục **bin**, bên trong có **java.exe** và **javac.exe**.

### macOS

macOS cung cấp công cụ **java_home** để liệt kê và chọn JDK đã cài:

~~~bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 27
~~~

Lệnh thứ hai in ra thư mục gốc của một JDK có phiên bản chính 27. Nếu không tìm thấy kết quả phù hợp, hãy kiểm tra lại việc cài đặt JDK 27.

### Linux

Đường dẫn cài đặt phụ thuộc vào bản phân phối Linux và cách cài JDK. Một số hệ thống đặt JDK dưới **/usr/lib/jvm**, nhưng tên thư mục cụ thể có thể khác.

Nếu lệnh **javac** đã được tìm thấy, có thể xem đường dẫn thực của trình biên dịch:

~~~bash
readlink -f "$(command -v javac)"
~~~

Kết quả thường kết thúc bằng **/bin/javac**; thư mục cha của **bin** là thư mục gốc JDK tương ứng. Nếu chưa tìm thấy **javac**, hãy kiểm tra vị trí cài đặt JDK bằng công cụ quản lý gói hoặc hướng dẫn của nhà cung cấp.

## 3. Cấu hình trên Windows

Có thể cấu hình biến môi trường ở cấp tài khoản người dùng hoặc toàn hệ thống. Với máy phát triển cá nhân, cấu hình ở cấp người dùng thường là đủ.

### Cấu hình lâu dài bằng giao diện Windows

1. Mở Start và tìm **Edit environment variables for your account** hoặc **Edit the system environment variables**.
2. Trong cửa sổ Environment Variables, tạo biến mới có tên **JAVA_HOME**.
3. Đặt giá trị của **JAVA_HOME** bằng đường dẫn thư mục gốc JDK 27, ví dụ **C:\Program Files\Java\jdk-27**.
4. Chọn biến **Path** trong phạm vi người dùng, mở **Edit**, rồi thêm một mục mới: **%JAVA_HOME%\bin**.
5. Đưa mục JDK 27 lên trước các mục Java cũ hơn nếu chúng cùng xuất hiện trong PATH.
6. Lưu các cửa sổ cấu hình và mở một cửa sổ terminal mới.

Không nhập dấu ngoặc kép bao quanh giá trị đường dẫn khi điền vào ô giá trị biến môi trường. Nếu JDK được cài ở vị trí khác, hãy dùng đường dẫn thực tế thay cho ví dụ.

### Cấu hình tạm thời trong PowerShell

Các lệnh sau chỉ có hiệu lực trong cửa sổ PowerShell hiện tại:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-27'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
~~~

Kiểm tra ngay trong cửa sổ đó:

~~~powershell
$env:JAVA_HOME
java --version
javac --version
~~~

Đóng cửa sổ PowerShell sẽ kết thúc cấu hình tạm thời này. Muốn áp dụng cho các phiên làm việc sau, hãy cấu hình biến môi trường bằng giao diện Windows như phần trên.

### Cấu hình tạm thời trong Command Prompt

Nếu đang dùng Command Prompt (**cmd.exe**), có thể đặt biến cho cửa sổ hiện tại:

~~~bat
set "JAVA_HOME=C:\Program Files\Java\jdk-27"
set "PATH=%JAVA_HOME%\bin;%PATH%"
~~~

Sau đó chạy:

~~~bat
java --version
javac --version
where java
where javac
~~~

## 4. Cấu hình trên macOS

Trên macOS, có thể lấy đường dẫn JDK 27 bằng **/usr/libexec/java_home** thay vì tự ghi nhớ đường dẫn cài đặt.

Trong terminal đang dùng, chạy:

~~~bash
export JAVA_HOME="$(/usr/libexec/java_home -v 27)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Hai lệnh trên áp dụng cho phiên terminal hiện tại. Để tự động cấu hình ở các phiên sau, thêm chúng vào tệp khởi tạo phù hợp với shell đang dùng. Với zsh, thường dùng **~/.zshrc**; với bash, thường dùng **~/.bash_profile** hoặc **~/.bashrc** tùy cách terminal khởi chạy shell.

Sau khi lưu tệp, mở terminal mới hoặc nạp lại tệp cấu hình. Ví dụ với zsh:

~~~bash
source ~/.zshrc
~~~

Kiểm tra đường dẫn JDK và phiên bản công cụ:

~~~bash
printf '%s\n' "$JAVA_HOME"
java --version
javac --version
command -v java
command -v javac
~~~

Nếu **java_home -v 27** không trả về đường dẫn, hãy xác nhận JDK 27 đã được cài và được macOS nhận diện.

## 5. Cấu hình trên Linux

Trên Linux, đặt **JAVA_HOME** theo thư mục JDK thực tế. Ví dụ dưới đây giả sử JDK nằm trong **/usr/lib/jvm/jdk-27**; hãy thay bằng tên thư mục đúng trên máy:

~~~bash
export JAVA_HOME="/usr/lib/jvm/jdk-27"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Để giữ cấu hình sau khi đăng xuất hoặc mở terminal mới, thêm hai dòng này vào tệp khởi tạo của shell:

- Bash tương tác thường đọc **~/.bashrc**.
- Zsh tương tác thường đọc **~/.zshrc**.
- Với shell đăng nhập, có thể cần dùng tệp khởi tạo đăng nhập tương ứng, tùy cấu hình hệ thống.

Nạp lại tệp cấu hình hoặc mở terminal mới. Ví dụ với Bash:

~~~bash
source ~/.bashrc
~~~

Sau đó kiểm tra:

~~~bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
java --version
javac --version
~~~

Đường dẫn được in bởi **command -v** cho biết terminal đang gọi lệnh ở đâu. Nếu có nhiều JDK, hãy bảo đảm mục **$JAVA_HOME/bin** đứng trước các thư mục Java cũ hơn trong PATH.

## 6. Kiểm tra Java và trình biên dịch

Sau khi cấu hình, hãy kiểm tra cả biến môi trường, vị trí lệnh và phiên bản công cụ.

### Kiểm tra phiên bản

Chạy hai lệnh:

~~~bash
java --version
javac --version
~~~

Kết quả cần thể hiện phiên bản chính là **27** cho cả runtime và compiler. Chuỗi hiển thị chi tiết có thể khác nhau theo nhà cung cấp JDK và bản cập nhật.

Trên Windows PowerShell, có thể kiểm tra thêm:

~~~powershell
$env:JAVA_HOME
Get-Command java, javac | Select-Object Name, Source
where.exe java
where.exe javac
~~~

Trên macOS và Linux, dùng:

~~~bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
type -a java
type -a javac
~~~

**command -v** cho biết lệnh được chọn đầu tiên. **type -a** liệt kê các vị trí mà shell có thể tìm thấy, hữu ích khi máy có nhiều phiên bản Java.

### Biên dịch và chạy một chương trình thử

Tạo tệp **Java27Check.java** với nội dung:

~~~java
public class Java27Check {
    public static void main(String[] args) {
        System.out.println(
            "Java feature version: " + Runtime.version().feature()
        );
    }
}
~~~

Tại thư mục chứa tệp, chạy:

~~~bash
javac Java27Check.java
java Java27Check
~~~

Nếu cấu hình đúng với JDK 27, chương trình biên dịch thành công và in ra:

~~~text
Java feature version: 27
~~~

Bài kiểm tra này xác nhận terminal gọi được trình biên dịch và runtime có thể chạy chương trình vừa biên dịch. Nếu muốn kiểm tra riêng đường dẫn đang được sử dụng, hãy đối chiếu kết quả của **command -v** hoặc **where.exe** với thư mục JDK đã đặt trong **JAVA_HOME**.

## 7. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **java** không được nhận diện | PATH chưa chứa thư mục **bin** của JDK hoặc terminal chưa nhận cấu hình mới | Kiểm tra PATH, thêm mục JDK 27 rồi mở terminal mới |
| **javac** không được nhận diện nhưng **java** chạy được | PATH đang trỏ tới một runtime không có compiler hoặc trỏ nhầm thư mục | Cài JDK 27 và đưa đúng **JAVA_HOME/bin** vào PATH |
| **JAVA_HOME** kết thúc bằng **/bin** hoặc **\bin** | Đã đặt biến tới thư mục công cụ thay vì thư mục gốc JDK | Bỏ phần **bin** khỏi giá trị **JAVA_HOME** |
| **java --version** hiển thị phiên bản cũ | Một thư mục Java cũ đứng trước JDK 27 trong PATH | Kiểm tra thứ tự PATH và đưa JDK 27 lên trước |
| **java** và **javac** hiển thị hai phiên bản khác nhau | Hai lệnh được phân giải từ các thư mục cài đặt khác nhau | Kiểm tra vị trí của cả hai lệnh và điều chỉnh PATH |
| Terminal nhận JDK 27 nhưng IDE hoặc công cụ build dùng bản khác | IDE hoặc công cụ build có cấu hình JDK riêng | Chọn JDK 27 trong cấu hình SDK/JDK hoặc JVM của công cụ đó |

Một số điểm cần nhớ khi xử lý:

- **JAVA_HOME** và PATH có vai trò liên quan nhưng khác nhau. Chỉ đặt **JAVA_HOME** không bảo đảm lệnh **java** và **javac** được tìm thấy; thư mục **bin** vẫn cần nằm trong PATH.
- **JAVA_HOME** phải trỏ tới thư mục gốc JDK, không trỏ tới thư mục **bin**, một tệp thực thi hoặc thư mục chỉ chứa runtime.
- Thứ tự các mục trong PATH quyết định chương trình nào được gọi khi có nhiều bản Java cùng tồn tại.
- Terminal đã mở trước khi thay đổi biến môi trường có thể vẫn giữ giá trị cũ. Hãy mở phiên terminal mới để kiểm tra cấu hình lâu dài.
- IDE, Maven, Gradle và các công cụ xây dựng có thể có lựa chọn JDK riêng. Khi kết quả trong terminal đúng nhưng dự án vẫn dùng phiên bản khác, hãy kiểm tra cấu hình JDK của chính công cụ đó.

## 8. Quy trình kiểm tra nhanh

Khi thiết lập một máy phát triển mới, có thể thực hiện lần lượt:

1. Cài JDK 27 phù hợp với hệ điều hành và kiến trúc máy.
2. Xác định thư mục gốc JDK 27.
3. Đặt **JAVA_HOME** tới thư mục gốc đó.
4. Thêm **JAVA_HOME/bin** vào đầu PATH (trên Windows dùng **%JAVA_HOME%\bin**).
5. Mở terminal mới.
6. Chạy **java --version** và **javac --version**; xác nhận cả hai có phiên bản chính 27.
7. Kiểm tra vị trí lệnh nếu có nhiều JDK.
8. Biên dịch và chạy chương trình thử để xác nhận toàn bộ luồng hoạt động.

Khi cả **java** và **javac** đều được phân giải từ JDK 27, các lệnh hiển thị phiên bản 27 và chương trình thử chạy thành công, môi trường dòng lệnh đã sẵn sàng cho việc phát triển Java 27.
