# Cấu hình và kiểm tra JAVA_HOME

JAVA_HOME là biến môi trường trỏ đến **thư mục gốc của một JDK (Java Development Kit)**. Các công cụ như Gradle, Maven, Ant, IDE và script có thể dùng biến này để tìm bộ công cụ Java cần thiết. Cấu hình đúng JAVA_HOME giúp các công cụ dùng cùng một JDK và giảm lỗi do máy có nhiều phiên bản Java.

JAVA_HOME chỉ lưu đường dẫn đến JDK. Lệnh java hoặc javac được tìm thấy qua PATH, vì vậy hai biến này có vai trò liên quan nhưng khác nhau:

- **JAVA_HOME**: đường dẫn đến thư mục gốc của JDK, ví dụ `C:\Program Files\Eclipse Adoptium\jdk-21...` hoặc `/usr/lib/jvm/java-21-openjdk-amd64`.
- **PATH**: danh sách thư mục hệ điều hành tìm kiếm khi chạy lệnh. Thêm thư mục bin của JDK vào PATH để gọi java, javac từ mọi thư mục.

Cấu trúc cài đặt thường có dạng:

~~~text
<JDK_HOME>/
├── bin/
│   ├── java
│   ├── javac
│   └── ...
├── conf/
├── include/
└── lib/
~~~

Trên Windows, các tệp thực thi có phần mở rộng .exe. Thư mục JAVA_HOME phải là thư mục gốc JDK, không phải thư mục bin, không phải đường dẫn đến java.exe hoặc javac.exe. Hãy dùng JDK đầy đủ; một môi trường chỉ có runtime có thể chạy chương trình Java nhưng không có trình biên dịch javac.

## 1. Xác định đúng thư mục JDK

Trước khi đặt biến, hãy xác định phiên bản JDK cần dùng và vị trí cài đặt thực tế. Nếu máy có nhiều JDK, hãy chọn phiên bản phù hợp với dự án thay vì lấy ngẫu nhiên kết quả đầu tiên.

**Windows (PowerShell):**

~~~powershell
java -version
javac -version
where.exe java
where.exe javac
~~~

`where.exe javac` cho biết vị trí trình biên dịch đang được tìm thấy qua PATH. Nếu kết quả là `C:\...\jdk-21\bin\javac.exe`, JAVA_HOME tương ứng là thư mục `C:\...\jdk-21` ở phía trên bin. Nếu có nhiều kết quả, kiểm tra từng đường dẫn và chọn đúng JDK.

**macOS:**

~~~sh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 21
~~~

Lệnh thứ nhất liệt kê các JDK macOS nhận diện được. Lệnh thứ hai trả về đường dẫn của JDK phiên bản 21 nếu phiên bản đó đã được cài đặt và đăng ký với hệ thống.

**Linux:**

~~~sh
java -version
javac -version
command -v javac
readlink -f "$(command -v javac)"
~~~

Trên Linux, `readlink -f` giúp lần theo liên kết tượng trưng để tìm tệp javac thực tế. Nếu kết quả là `/usr/lib/jvm/java-21-openjdk-amd64/bin/javac`, thư mục gốc JDK là `/usr/lib/jvm/java-21-openjdk-amd64`. Đường dẫn cụ thể thay đổi theo bản phân phối và cách cài JDK.

Một thư mục JDK hợp lệ thường có cả `bin/java` và `bin/javac` (hoặc các tệp .exe tương ứng trên Windows). Có thể kiểm tra trực tiếp hai tệp này trước khi lưu cấu hình.

## 2. Cấu hình trên Windows

Có thể đặt JAVA_HOME cho tài khoản hiện tại hoặc cho toàn bộ máy. Nên bắt đầu với biến người dùng nếu chỉ tài khoản hiện tại cần JDK đó. Thiết lập biến hệ thống ảnh hưởng đến nhiều tài khoản và thường cần quyền quản trị.

1. Mở **Start**, tìm **Edit the system environment variables**, sau đó mở **Environment Variables**.
2. Trong **User variables**, chọn **New**.
3. Đặt **Variable name** là `JAVA_HOME`.
4. Đặt **Variable value** là đường dẫn thư mục gốc JDK đã xác định, ví dụ `C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot`. Thay ví dụ này bằng đường dẫn thực tế trên máy.
5. Trong danh sách biến người dùng, chọn `Path` → **Edit** → **New**, rồi thêm `%JAVA_HOME%\bin`.
6. Xác nhận các hộp thoại. Mở một cửa sổ PowerShell hoặc Command Prompt mới để nhận biến môi trường vừa cập nhật.

Không thêm dấu ngoặc kép vào giá trị JAVA_HOME trong hộp thoại Windows, kể cả khi đường dẫn có khoảng trắng. Trong PATH, dùng `%JAVA_HOME%\bin`; không đặt PATH trỏ đến tệp java.exe.

Có thể đặt JAVA_HOME ở phạm vi người dùng bằng PowerShell với đường dẫn JDK thực tế:

~~~powershell
[Environment]::SetEnvironmentVariable(
    'JAVA_HOME',
    'C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot',
    'User'
)
~~~

Lệnh trên lưu biến cho tài khoản hiện tại; nó không tự cập nhật môi trường của cửa sổ PowerShell đang mở. Hãy mở terminal mới. Có thể thêm `%JAVA_HOME%\bin` vào Path bằng giao diện Environment Variables như các bước trên.

Để thử tạm trong cửa sổ PowerShell hiện tại trước khi lưu cấu hình lâu dài:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
~~~

Các lệnh gán `$env:` chỉ tác động đến tiến trình PowerShell hiện tại và các tiến trình con được mở từ nó. Đóng cửa sổ sẽ mất thay đổi tạm này.

## 3. Cấu hình trên macOS

macOS thường dùng Zsh làm shell mặc định. Nếu cần JDK 21 và hệ thống đã nhận diện JDK đó, có thể dùng công cụ `java_home` để tránh ghi cứng một thư mục cài đặt có thể thay đổi:

~~~sh
/usr/libexec/java_home -V
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Hai lệnh export chỉ có hiệu lực trong shell hiện tại. Để giữ cấu hình cho các phiên Zsh mới, thêm chúng vào `~/.zshrc` (shell tương tác) hoặc tệp khởi tạo phù hợp với cách terminal khởi chạy shell, chẳng hạn `~/.zprofile` cho shell đăng nhập. Không cần thêm cùng một cấu hình nhiều lần vào các tệp khác nhau.

Sau khi lưu tệp, nạp lại cấu hình:

~~~sh
source ~/.zshrc
~~~

Nếu đã đặt cấu hình trong `~/.zprofile`, nạp lại tệp đó hoặc mở terminal mới. Nếu dùng Bash, hãy đặt cấu hình trong tệp khởi tạo Bash mà môi trường của bạn thực sự đọc, thường là `~/.bash_profile` hoặc `~/.bashrc`.

Nếu `java_home -v 21` báo không tìm thấy phiên bản phù hợp, hãy cài JDK 21 hoặc chọn phiên bản JDK đang có trong danh sách từ `java_home -V`.

## 4. Cấu hình trên Linux

Trên Linux, vị trí JDK phụ thuộc bản phân phối và phương thức cài đặt. Có thể dùng `readlink -f "$(command -v javac)"` để tìm tệp javac, sau đó lấy thư mục nằm phía trên bin làm JAVA_HOME.

Ví dụ, nếu JDK được cài tại `/usr/lib/jvm/java-21-openjdk-amd64`, thêm hai dòng sau vào tệp khởi tạo shell:

~~~sh
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Thay đường dẫn ví dụ bằng thư mục JDK thực tế. Với Bash tương tác, tệp thường dùng là `~/.bashrc`; với shell đăng nhập, có thể cần `~/.profile` hoặc `~/.bash_profile`. Nếu dùng Zsh, thường đặt trong `~/.zshrc`.

Nạp lại tệp tương ứng, ví dụ:

~~~sh
source ~/.bashrc
~~~

Sau đó mở terminal mới hoặc chạy lại lệnh source để nhận cấu hình. Các lệnh export chỉ thiết lập biến cho shell hiện tại và tiến trình con; việc thêm chúng vào tệp khởi tạo mới làm cấu hình được áp dụng ở những phiên shell sau.

## 5. Kiểm tra cấu hình

Sau khi cấu hình, mở terminal mới rồi kiểm tra cả biến JAVA_HOME, các tệp thực thi bên trong JDK và kết quả phân giải lệnh qua PATH.

**Windows (PowerShell):**

~~~powershell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
where.exe java
where.exe javac
~~~

Hai lệnh `Test-Path` nên trả về `True`. Hai lệnh chạy bằng đường dẫn đầy đủ xác nhận JDK mà JAVA_HOME trỏ đến có thể thực thi. `where.exe` cho biết lệnh java và javac được tìm thấy ở đâu qua PATH.

**macOS và Linux:**

~~~sh
printf '%s\n' "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo "java: OK"
test -x "$JAVA_HOME/bin/javac" && echo "javac: OK"
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
command -v java
command -v javac
~~~

Nếu các tệp tồn tại và có quyền thực thi, hai lệnh kiểm tra sẽ in `java: OK` và `javac: OK`. Các lệnh chạy bằng đường dẫn đầy đủ kiểm tra đúng JDK được chỉ định bởi JAVA_HOME; `command -v` kiểm tra lệnh nào được shell chọn qua PATH.

Kết quả mong đợi là:

- JAVA_HOME in ra thư mục gốc JDK, không kết thúc bằng `/bin` hoặc `\bin`.
- `java -version` và `javac -version` hiển thị phiên bản phù hợp với JDK đã chọn.
- java và javac qua PATH trỏ đến JDK mong muốn. Trên Windows, kết quả đầu tiên của `where.exe` là đường dẫn được ưu tiên; trên macOS/Linux, `command -v` cho biết lệnh shell chọn.

Không bắt buộc đầu ra phiên bản phải giống hệt ví dụ trên mạng: số bản vá và tên nhà phân phối có thể khác. Điều cần kiểm tra là phiên bản và đường dẫn đúng với JDK dự án yêu cầu.

## 6. Kiểm tra từ công cụ build và IDE

Một terminal có JAVA_HOME đúng chưa chắc mọi công cụ đều dùng cùng JDK. Hãy kiểm tra từ chính công cụ đang chạy dự án:

**Gradle Wrapper:**

~~~sh
./gradlew --version
~~~

Trên Windows, dùng:

~~~powershell
.\gradlew.bat --version
~~~

Phần thông tin JVM trong kết quả cho biết JVM mà Gradle đang dùng để chạy. Nếu kết quả khác JAVA_HOME, kiểm tra cấu hình ghi đè như `org.gradle.java.home` trong `gradle.properties`, cấu hình daemon của môi trường hoặc thiết lập của IDE. Sau khi đổi JDK, có thể dừng daemon cũ bằng `./gradlew --stop` (hoặc `.\gradlew.bat --stop` trên Windows), rồi chạy lại Wrapper.

**Maven:**

~~~sh
mvn -version
~~~

Kết quả hiển thị phiên bản Maven, phiên bản Java và Java home mà Maven đang sử dụng. Nếu Java home khác JAVA_HOME dự kiến, kiểm tra terminal, script khởi chạy Maven và cấu hình môi trường.

**IDE:** IntelliJ IDEA, Eclipse và các IDE khác có thể có cấu hình JDK riêng cho Project SDK, Gradle JVM hoặc Maven runner. Hãy kiểm tra đúng mục mà dự án sử dụng. Đổi JAVA_HOME của hệ điều hành không nhất thiết tự đổi Project SDK đã chọn trong IDE.

Cũng cần phân biệt JVM chạy công cụ build với JDK dùng để biên dịch mã nguồn. Gradle Java Toolchains có thể chọn một JDK riêng cho tác vụ biên dịch, kể cả khi JVM chạy Gradle là phiên bản khác. Vì vậy, khi `gradlew --version` đúng nhưng compiler vẫn dùng phiên bản không mong muốn, hãy kiểm tra cấu hình toolchain của dự án.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| JAVA_HOME trỏ đến thư mục không tồn tại | Gõ sai đường dẫn, JDK đã được nâng cấp hoặc gỡ cài đặt | Xác định lại thư mục cài đặt và cập nhật JAVA_HOME |
| Công cụ báo không tìm thấy Java | JAVA_HOME chưa được đặt, terminal cũ chưa nhận biến hoặc PATH thiếu thư mục bin | Mở terminal mới, kiểm tra JAVA_HOME và thêm %JAVA_HOME%\bin hoặc $JAVA_HOME/bin vào PATH |
| Có java nhưng không có javac | Đường dẫn trỏ đến runtime không có compiler hoặc trỏ nhầm thư mục | Cài JDK đầy đủ và đặt JAVA_HOME đến đúng thư mục gốc JDK |
| java -version hiển thị phiên bản khác JAVA_HOME | Một JDK khác đứng trước trong PATH | Kiểm tra where.exe java hoặc command -v java, rồi điều chỉnh thứ tự PATH |
| Gradle hoặc Maven dùng JDK khác | Công cụ có cấu hình JVM riêng, daemon cũ hoặc IDE ghi đè môi trường | Kiểm tra gradlew --version, mvn -version, org.gradle.java.home và cấu hình runner của IDE |
| Đã sửa biến nhưng terminal vẫn thấy giá trị cũ | Tiến trình hiện tại giữ bản sao môi trường từ lúc được mở | Mở terminal mới; nếu IDE đã mở trước đó, khởi động lại IDE |
| Đường dẫn có khoảng trắng gây lỗi | Đường dẫn bị đặt sai hoặc lệnh shell không được trích dẫn | Lưu giá trị JAVA_HOME không kèm dấu ngoặc kép trong giao diện Windows; khi viết lệnh shell, đặt biến đường dẫn trong dấu nháy phù hợp |

### Checklist hoàn tất

- [ ] JAVA_HOME trỏ đến thư mục gốc của JDK đã cài đặt.
- [ ] Thư mục bin bên trong JAVA_HOME có cả java và javac.
- [ ] PATH có thư mục bin của JDK và thứ tự ưu tiên đúng.
- [ ] Terminal mới hiển thị phiên bản Java mong muốn.
- [ ] Công cụ build và IDE dùng đúng JVM/JDK theo cấu hình dự án.

Khi các bước trên đều đúng, JAVA_HOME đã được cấu hình và có thể được các công cụ Java sử dụng. Nếu dự án có yêu cầu JDK cụ thể, hãy lấy phiên bản đó làm chuẩn khi chọn JAVA_HOME và khi kiểm tra Gradle, Maven hoặc IDE.