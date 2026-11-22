# Kiểm tra cài đặt JDK

Sau khi cài Java Development Kit (JDK), cần kiểm tra rằng hệ thống tìm thấy đúng chương trình Java, có trình biên dịch `javac`, và có thể biên dịch rồi chạy một chương trình đơn giản. Việc kiểm tra bằng vài lệnh trong terminal giúp phát hiện sớm lỗi cài đặt, cấu hình `PATH`, `JAVA_HOME` hoặc nhiều phiên bản Java cùng tồn tại.

## 1. Mở terminal phù hợp

Mở một cửa sổ terminal mới sau khi cài JDK hoặc thay đổi biến môi trường:

- **Windows:** Command Prompt (CMD) hoặc Windows PowerShell.
- **macOS:** Terminal hoặc terminal tích hợp trong IDE.
- **Linux:** terminal của môi trường desktop hoặc terminal từ xa.

Lệnh được chạy trong terminal có thể sử dụng phiên bản Java khác với phiên bản mà IDE hoặc công cụ build đang cấu hình. Vì vậy, hãy kiểm tra đúng môi trường mà bạn định dùng.

## 2. Kiểm tra lệnh Java

Chạy:

```bash
java -version
```

Lệnh này gọi trình khởi chạy `java` đầu tiên mà hệ điều hành tìm thấy theo cấu hình hiện tại. Kết quả thường cho biết:

- Phiên bản Java, ví dụ `17.0.12`.
- Nhà cung cấp bản phân phối, chẳng hạn OpenJDK hoặc một bản build của nhà cung cấp khác.
- Thông tin runtime và kiến trúc máy ảo.

Ví dụ một kết quả có thể bắt đầu như sau:

```text
openjdk version "17.0.12"
OpenJDK Runtime Environment
OpenJDK 64-Bit Server VM
```

Đây chỉ là minh họa; nội dung đầy đủ thay đổi theo nhà cung cấp và bản cập nhật. Điều cần kiểm tra là lệnh chạy thành công và phiên bản phù hợp với dự án.

Có thể dùng `java -version` trên cả các phiên bản Java cũ lẫn mới. Cú pháp `java --version` cũng được hỗ trợ từ Java 9 trở lên.

Nếu terminal báo không tìm thấy lệnh `java`, hãy kiểm tra việc cài đặt và biến `PATH` ở các phần dưới.

## 3. Kiểm tra trình biên dịch javac

Chạy:

```bash
javac -version
```

Ví dụ kết quả:

```text
javac 17.0.12
```

`javac` là trình biên dịch mã nguồn Java thành bytecode và được cung cấp bởi JDK. Vì vậy, đây là bước quan trọng để xác nhận máy có công cụ phát triển Java.

Diễn giải kết quả:

- **Cả `java` và `javac` đều chạy:** hệ thống tìm thấy runtime và trình biên dịch.
- **`java` chạy nhưng `javac` không được nhận diện:** có thể bạn chỉ cài runtime-only, hoặc `PATH` chưa trỏ đến thư mục `bin` của JDK.
- **Cả hai đều không chạy:** có thể JDK chưa được cài, đường dẫn chưa được cấu hình hoặc terminal chưa nạp lại biến môi trường.

Với môi trường phát triển, phiên bản chính (major version) của `java` và `javac` nên tương thích, thường là cùng phiên bản JDK. Nếu hai lệnh cho thấy hai major version khác nhau, hãy kiểm tra xem chúng có đang trỏ đến hai bản cài Java riêng biệt hay không.

Lưu ý về cách hiển thị phiên bản:

- Java 9 trở lên thường hiển thị major version trực tiếp, ví dụ `17.0.12`.
- Java 8 thường hiển thị dạng bắt đầu bằng `1.8`, ví dụ `1.8.0_402`.

## 4. Xác định chương trình Java đang được sử dụng

Một máy có thể cài nhiều JDK, chẳng hạn Java 8, Java 17 và Java 21. Lệnh `java` và `javac` được chọn dựa trên thứ tự tìm kiếm của hệ điều hành, đặc biệt là thứ tự các thư mục trong `PATH`.

### Windows

Trong CMD hoặc PowerShell, chạy:

```powershell
where.exe java
where.exe javac
```

Lệnh có thể trả về một hoặc nhiều đường dẫn, ví dụ:

```text
C:\Program Files\Java\jdk-17\bin\java.exe
C:\Program Files\Java\jdk-21\bin\java.exe
```

Khi có nhiều kết quả, mục được tìm thấy đầu tiên trong thứ tự tìm kiếm thường là chương trình được gọi khi gõ tên lệnh. Dùng kết quả này cùng với `java -version` và `javac -version` để xác định bản đang hoạt động.

Trong PowerShell, có thể xem thêm cách PowerShell phân giải lệnh:

```powershell
Get-Command java -All
Get-Command javac -All
```

### macOS và Linux

Chạy:

```bash
type -a java
type -a javac
```

Lệnh hiển thị các vị trí mà shell tìm thấy. Để xem đường dẫn được chọn đầu tiên:

```bash
command -v java
command -v javac
```

Nếu các đường dẫn của `java` và `javac` thuộc hai thư mục JDK khác nhau, hãy điều chỉnh `PATH` để chúng cùng trỏ đến bản cài mong muốn.

## 5. Kiểm tra biến môi trường JAVA_HOME

Nhiều công cụ phát triển như Maven, Gradle và một số IDE sử dụng biến môi trường `JAVA_HOME` để tìm JDK.

**`JAVA_HOME` nên trỏ đến thư mục gốc của JDK**, không trỏ trực tiếp đến thư mục `bin`.

Ví dụ cấu trúc cài đặt:

```text
jdk-17/
  bin/
    java
    javac
  conf/
  include/
  jmods/
  lib/
```

Trong ví dụ này, `JAVA_HOME` trỏ đến `jdk-17`; thư mục chứa lệnh là `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên macOS/Linux.

### Windows PowerShell

Xem giá trị hiện tại:

```powershell
$env:JAVA_HOME
```

Kiểm tra các tệp thực thi trong JDK được khai báo:

```powershell
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
```

Nếu cả hai kết quả là `True`, hai tệp tương ứng tồn tại ở vị trí đó. Có thể gọi trực tiếp chúng để kiểm tra đúng JDK mà `JAVA_HOME` trỏ tới:

```powershell
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
```

### Windows CMD

Xem giá trị biến:

```bat
echo %JAVA_HOME%
```

Sau khi xác nhận biến đã trỏ đến thư mục gốc của JDK, gọi trực tiếp:

```bat
"%JAVA_HOME%\bin\java.exe" -version
"%JAVA_HOME%\bin\javac.exe" -version
```

### macOS và Linux

Xem giá trị biến:

```bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
```

Nếu biến đã được thiết lập, kiểm tra các chương trình bên trong:

```bash
test -x "$JAVA_HOME/bin/java" && "$JAVA_HOME/bin/java" -version
test -x "$JAVA_HOME/bin/javac" && "$JAVA_HOME/bin/javac" -version
```

Nếu `JAVA_HOME` trống hoặc không tồn tại các tệp tương ứng, hãy cấu hình lại biến theo thư mục JDK thực tế.

## 6. Kiểm tra PATH

`PATH` là danh sách các thư mục mà hệ điều hành tìm kiếm khi bạn gõ một lệnh như `java` hoặc `javac`.

Để gọi được các công cụ JDK từ bất kỳ thư mục làm việc nào, thư mục `bin` của JDK cần có trong `PATH`.

Ví dụ, nếu JDK được cài tại:

```text
C:\Program Files\Java\jdk-17
```

thì thư mục cần thêm vào `PATH` là:

```text
C:\Program Files\Java\jdk-17\bin
```

Trên macOS/Linux, nếu JDK ở `/opt/jdk-17`, thư mục cần thêm là `/opt/jdk-17/bin`.

### Cấu hình tạm thời trong Windows PowerShell

Ví dụ sau chỉ ảnh hưởng đến cửa sổ PowerShell hiện tại. Thay đường dẫn minh họa bằng nơi JDK thực tế được cài:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

### Cấu hình tạm thời trong macOS/Linux

Ví dụ sau chỉ ảnh hưởng đến terminal hiện tại. Thay đường dẫn minh họa bằng nơi JDK thực tế được cài:

```bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
```

Muốn cấu hình lâu dài, hãy cập nhật biến môi trường trong phần Environment Variables của Windows hoặc trong tệp cấu hình shell mà bạn sử dụng trên macOS/Linux, chẳng hạn `~/.zshrc` hoặc `~/.bashrc`. Sau khi lưu cấu hình, mở terminal mới để nạp lại giá trị.

Không bắt buộc phải có `JAVA_HOME` để chạy được lệnh `java`; tuy nhiên, nhiều công cụ build và IDE dựa vào biến này. Cấu hình `JAVA_HOME` và `PATH` nhất quán giúp tránh việc mỗi công cụ sử dụng một JDK khác nhau.

## 7. Kiểm tra bằng cách biên dịch và chạy chương trình thật

Hai lệnh xem phiên bản chưa chứng minh toàn bộ quy trình phát triển hoạt động. Hãy tạo một chương trình nhỏ để kiểm tra cả biên dịch lẫn thực thi.

Tạo tệp **`JdkCheck.java`**:

```java
public class JdkCheck {
    public static void main(String[] args) {
        System.out.println("JDK installation OK");
    }
}
```

Mở terminal tại thư mục chứa tệp và chạy:

```bash
javac JdkCheck.java
java -cp . JdkCheck
```

Kết quả mong đợi:

```text
JDK installation OK
```

Giải thích:

1. `javac JdkCheck.java` biên dịch mã nguồn và tạo `JdkCheck.class`.
2. `java -cp . JdkCheck` khởi chạy lớp `JdkCheck`.
3. `-cp .` đặt thư mục hiện tại (`.`) vào classpath để JVM tìm thấy tệp lớp vừa biên dịch.
4. Nếu thông báo xuất hiện chính xác, trình biên dịch, classpath và runtime đều đã hoạt động cho ví dụ này.

Nếu `javac` thành công nhưng `java` báo không tìm thấy lớp, hãy kiểm tra bạn có đang ở đúng thư mục chứa `JdkCheck.class` và có gõ đúng tên lớp hay không. Nếu tệp khai báo một package, cần chạy lớp bằng tên đầy đủ của package và cấu trúc thư mục tương ứng.

## 8. Các lỗi kiểm tra thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `java` không được nhận diện | Chưa cài Java hoặc thư mục `bin` chưa có trong `PATH` | Kiểm tra nơi cài JDK và thêm đúng thư mục `bin` vào `PATH` |
| `javac` không được nhận diện | Chỉ có runtime, hoặc `PATH` đang trỏ đến runtime/bản cài khác | Cài JDK đầy đủ và đưa `bin` của JDK mong muốn lên đúng vị trí trong `PATH` |
| `java` và `javac` khác major version | Nhiều bản Java được cài hoặc thứ tự `PATH` không như dự kiến | Dùng `where.exe` hoặc `type -a` để tìm đường dẫn, sau đó điều chỉnh cấu hình |
| `JAVA_HOME` không hợp lệ | Trỏ đến thư mục không tồn tại, thư mục `bin`, hoặc runtime không có compiler | Đặt lại về thư mục gốc của một JDK đầy đủ |
| Đã sửa `PATH` nhưng lệnh vẫn dùng bản cũ | Terminal hoặc IDE đang giữ môi trường cũ; thư mục khác đứng trước trong `PATH` | Mở terminal mới, kiểm tra thứ tự đường dẫn và khởi động lại IDE nếu cần |
| Terminal chạy đúng nhưng IDE báo thiếu JDK | IDE hoặc công cụ build đang dùng cấu hình JDK riêng | Kiểm tra Project SDK, Gradle JVM hoặc JDK được cấu hình trong công cụ build |
| `UnsupportedClassVersionError` | Runtime đang chạy cũ hơn phiên bản bytecode mà chương trình yêu cầu | Dùng runtime tương thích hoặc biên dịch theo phiên bản mục tiêu phù hợp |

Không nên chỉ nhìn tên thư mục hoặc giá trị `JAVA_HOME` để kết luận lệnh đang chạy đúng bản Java. Hãy đối chiếu cả phiên bản và đường dẫn thực tế của `java` lẫn `javac`.

## 9. Checklist xác nhận JDK đã sẵn sàng

Có thể đánh dấu lần lượt các mục sau:

- [ ] `java -version` chạy thành công và hiển thị phiên bản mong muốn.
- [ ] `javac -version` chạy thành công và hiển thị phiên bản compiler mong muốn.
- [ ] Đường dẫn `java` và `javac` thuộc JDK dự định sử dụng.
- [ ] `JAVA_HOME` (nếu được dùng) trỏ đến thư mục gốc của JDK.
- [ ] `PATH` có thư mục `bin` của JDK mong muốn.
- [ ] Chương trình `JdkCheck.java` biên dịch và chạy thành công.

Khi tất cả các mục phù hợp với môi trường dự án đều đạt, JDK đã sẵn sàng cho việc học, biên dịch và chạy các chương trình Java. Với Maven, Gradle hoặc IDE, hãy kiểm tra thêm cấu hình JDK riêng của từng công cụ để bảo đảm chúng sử dụng cùng phiên bản dự kiến.
