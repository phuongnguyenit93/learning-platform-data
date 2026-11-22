# Thiết lập JAVA_HOME và xác minh Java thực tế trên dòng lệnh

## 1. Mục tiêu và phạm vi

Khi làm việc với **Spring Boot Build Tooling Packaging**, Java Development Kit (JDK) là nền tảng để biên dịch và chạy ứng dụng, cũng như khởi động những build tool như Gradle hoặc Maven. Cài một JDK thành công **chưa đủ** để khẳng định terminal, IDE và Gradle Wrapper đang dùng đúng JDK đó. Máy có thể chứa nhiều JDK, và mỗi công cụ có thể chọn đường dẫn riêng.

Sau bài này, bạn có thể:

1. Phân biệt biến môi trường `JAVA_HOME`, biến `PATH`, lệnh `java`, `javac` và thuộc tính `java.home` của JVM đang chạy.
2. Thiết lập JDK cho phiên terminal hiện tại trên Windows PowerShell, Windows Command Prompt, Linux và macOS; biết cách duy trì thiết lập ở phiên mới.
3. Kiểm tra chính xác lệnh `java` đang gọi chương trình nào và runtime thực tế là phiên bản nào.
4. Kiểm chứng Gradle Wrapper dùng phiên bản Gradle nào, JVM khởi động/daemon nào, và vì sao JVM của build có thể khác JDK biên dịch qua Java Toolchains.
5. Chẩn đoán lỗi Java sai phiên bản, `JAVA_HOME` không hợp lệ, thiếu `javac` hoặc kết quả CLI không giống IDE/CI.

**Quy ước ví dụ:** dùng **JDK 21** để minh họa. Đó là ví dụ cấu hình, không có nghĩa mọi dự án đều bắt buộc Java 21. Phiên bản cần cài phải dựa trên yêu cầu dự án và bảng tương thích của Gradle/Spring Boot tương ứng. Đường dẫn trên từng máy sẽ khác; chỉ thay ví dụ bằng **đường dẫn JDK thực sự đã cài**.

## 2. Hiểu đúng bốn thông tin về Java

| Tên | Vai trò | Điều dễ nhầm |
| --- | --- | --- |
| `JAVA_HOME` | Biến môi trường chỉ đến **thư mục gốc của JDK** để công cụ tìm Java, ví dụ `C:\Program Files\Java\jdk-21` hoặc `/usr/lib/jvm/java-21-openjdk-amd64` | Đặt `JAVA_HOME` không tự bảo đảm lệnh `java` trên `PATH` trùng JDK ấy |
| `PATH` | Danh sách thư mục shell tra cứu khi gõ tên chương trình như `java` hoặc `javac` | Nếu một thư mục JDK cũ đứng trước, shell có thể gọi bản cũ |
| `java -version` và `javac -version` | Báo phiên bản **chương trình thực sự được shell gọi** khi chạy hai lệnh | `java` và `javac` thậm chí có thể trỏ đến hai bản khác nhau |
| `java.home` | Thuộc tính hệ thống được một **JVM đang chạy** báo về thư mục runtime của chính nó | Không phải tên khác của biến môi trường `JAVA_HOME` |

**JDK** chứa Java runtime và các công cụ phát triển, trong đó có compiler `javac`. Một Java runtime tối giản có thể chạy chương trình nhưng không cung cấp `javac`. Vì thế, khi chuẩn bị môi trường biên dịch Spring Boot, hãy chọn một **JDK**, không chỉ một runtime.

**Quy tắc nhớ:** `JAVA_HOME` là nơi bạn *muốn công cụ dùng*; `PATH` ảnh hưởng `java`/`javac` mà shell *sẽ chọn*; `java.home` giúp xác minh JVM *đã thật sự khởi chạy ở đâu*. Với Gradle, còn có JVM dùng chạy Gradle và Java toolchain dùng biên dịch/test; chúng có thể là hai bản khác nhau.

### 2.1. Giá trị JAVA_HOME đúng hình dạng nào?

Ví dụ hợp lệ:

- Windows: `C:\Program Files\Java\jdk-21`
- Linux (Ubuntu/Debian điển hình): `/usr/lib/jvm/java-21-openjdk-amd64`
- macOS (một bản JDK cài dạng bundle): `/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home`

Đây là **ví dụ**; vendor và đường dẫn tùy máy. `JAVA_HOME` phải trỏ đến thư mục chứa `bin/java` và `bin/javac` (Windows là `bin\java.exe` và `bin\javac.exe`). **Không** đặt `JAVA_HOME` thành chính file `java.exe`, thư mục `bin` hoặc thư mục mẹ chưa chứa executable đúng nơi. Khi lưu biến môi trường trong giao diện hệ điều hành, bản thân giá trị là đường dẫn thuần; dấu ngoặc kép là cú pháp bảo vệ khoảng trắng trong lệnh shell, không phải phần của tên thư mục.

### 2.2. Một ví dụ dễ gặp

Giả sử JDK 21 được đặt trong `JAVA_HOME` nhưng thư mục `jdk-17/bin` đứng trước `jdk-21/bin` trong `PATH`. Khi gõ `java -version`, terminal vẫn có thể gọi Java 17. Nếu chạy thẳng file Java trong `JAVA_HOME/bin`, kết quả sẽ là bản JDK 21. Vì thế phải kiểm tra **cả biến môi trường lẫn executable thực tế** sau mọi thay đổi.

## 3. Bộ lệnh kiểm chứng chung: xác minh thay vì suy đoán

Sau khi mở terminal phù hợp, thực hiện lần lượt:

1. In `JAVA_HOME` để biết shell đang nhìn thấy giá trị nào.
2. Tìm executable `java` và `javac` mà shell có thể gọi.
3. Chạy `java -version` và `javac -version`.
4. Chạy **trực tiếp** `java` và `javac` bên dưới `JAVA_HOME/bin` để đối chiếu.
5. Hỏi JVM đang chạy thông tin `java.home`, `java.version` và `java.vendor`.

Lệnh kiểm tra JVM có thể dùng ở mọi hệ điều hành:

~~~text
java -XshowSettings:properties -version
~~~

Tìm các dòng `java.home = ...`, `java.version = ...` và `java.vendor = ...`. Đó là thông tin do tiến trình Java vừa khởi chạy báo, không phải giá trị suy ra từ tên thư mục. Lệnh này và `java -version` thường xuất thông tin chẩn đoán lên **stderr**, nên nếu lọc hoặc redirect, cần tính cả `2>&1`.

Nếu `java -version` báo đúng major version nhưng `java.home` là thư mục khác với JDK bạn mong đợi, bạn đã phát hiện một chênh lệch quan trọng. Hai bản JDK cùng major version vẫn có thể khác vendor, patch version hoặc kiến trúc.

## 4. Windows PowerShell

### 4.1. Kiểm tra trạng thái hiện tại

Mở **PowerShell** rồi chạy:

~~~powershell
$env:JAVA_HOME
$env:Path -split ';'
Get-Command java -All | Select-Object CommandType, Source
Get-Command javac -All | Select-Object CommandType, Source
where.exe java
where.exe javac
java -version
javac -version
java -XshowSettings:properties -version 2>&1 | Select-String 'java.home|java.version|java.vendor'
~~~

Ý nghĩa:

- `Get-Command java -All` cho biết cách **PowerShell** phân giải tên lệnh; nó có thể hiển thị cả alias/function và application nếu tồn tại.
- `where.exe java` tìm các file thực thi trong thư mục thuộc `PATH`, theo thứ tự tra cứu. Trong PowerShell, **phải viết `where.exe`** nếu muốn dùng chương trình Windows này: `where` đứng riêng có thể là alias của `Where-Object`.
- `java -version` cho biết Java được thực thi từ shell; `javac -version` giúp xác nhận compiler có tồn tại và cùng major version cần dùng.
- `java.home` là bằng chứng thêm về JVM thực tế.

Nếu `Get-Command` cho thấy alias/function tên `java`, cách chạy có thể không giống `where.exe`. Trong trường hợp ấy, cần đọc đúng kết quả phân giải của shell.

### 4.2. Cấu hình tạm thời cho đúng một phiên PowerShell

Giả sử bạn đã xác nhận JDK nằm tại `C:\Program Files\Java\jdk-21`:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version

Get-Command java -All | Select-Object CommandType, Source
where.exe java
java -version
javac -version
~~~

Hai lệnh `Test-Path` phải trả `True` nếu đường dẫn hợp lệ và có đủ công cụ. Dấu `&` là **call operator** của PowerShell, dùng để thực thi đường dẫn đặt trong chuỗi có khoảng trắng. Chèn `JAVA_HOME\bin` vào **đầu** `PATH` làm thư mục đó được ưu tiên trước các thư mục JDK cũ cho các lệnh external thông thường.

Thiết lập bằng ` $env:... ` chỉ sống trong **tiến trình PowerShell hiện tại** và các tiến trình con của nó. Sau khi đóng terminal hoặc mở cửa sổ độc lập mới, các thay đổi này không nhất thiết còn hiệu lực.

### 4.3. Cấu hình lâu dài trên Windows

Dùng giao diện **Environment Variables** của Windows (ví dụ `System Properties → Advanced → Environment Variables`):

1. Trong **User variables** hoặc **System variables** phù hợp, tạo/sửa `JAVA_HOME` thành đường dẫn gốc JDK đã kiểm tra.
2. Trong `Path`, thêm `%JAVA_HOME%\bin`. Đặt nó trước những đường dẫn Java khác nếu cần ưu tiên JDK này.
3. Mở **terminal mới** và chạy lại bộ kiểm chứng ở mục 4.1. Ứng dụng đang mở, IDE hoặc terminal cũ có thể vẫn giữ môi trường được nạp từ trước.

Chọn phạm vi User khi chỉ cần thay đổi cho tài khoản của mình; System ảnh hưởng rộng hơn và có thể cần quyền quản trị. Không dùng lệnh thay thế toàn bộ biến `Path` chỉ để đổi một JDK. `setx` khi được sử dụng chỉ ảnh hưởng các tiến trình tạo **sau này**, không sửa ngay môi trường của phiên PowerShell hiện tại; thao tác ghi `Path` bằng `setx` có thể gây mất hoặc thay đổi các mục không mong muốn.

### 4.4. Windows Command Prompt (cmd.exe)

Cú pháp `cmd.exe` khác PowerShell. Để đặt tạm một phiên `cmd`:

~~~bat
set "JAVA_HOME=C:\Program Files\Java\jdk-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"
echo %JAVA_HOME%
where java
where javac
"%JAVA_HOME%\bin\java.exe" -version
"%JAVA_HOME%\bin\javac.exe" -version
java -version
javac -version
~~~

`set` và `%JAVA_HOME%` là cú pháp của `cmd.exe`; đưa nguyên dòng `set ...` vào PowerShell sẽ không có cùng nghĩa. Khi chạy chương trình bằng đường dẫn có khoảng trắng, giữ cặp dấu ngoặc kép bao quanh đường dẫn.

## 5. Linux (bash và các shell tương thích)

### 5.1. Tìm Java đang dùng

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH" | tr ':' '\n'
command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
readlink -f "$(command -v java)"
java -XshowSettings:properties -version 2>&1 | grep -E 'java.home|java.version|java.vendor'
~~~

`readlink -f` phổ biến trên Linux/GNU: nó phân giải symlink đến đích cuối, rất hữu ích khi `/usr/bin/java` trỏ qua cơ chế `update-alternatives`. Nếu `command -v` chỉ ra alias/function, `readlink -f` trên tên đó không có ý nghĩa; hãy quan sát `type -a` và xác định đường dẫn thực thi. Lệnh `readlink -f` ở đây **không dành cho macOS mặc định**.

### 5.2. Thiết lập một phiên terminal

Giả sử JDK thực tế được cài ở `/usr/lib/jvm/java-21-openjdk-amd64`:

~~~bash
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"

test -x "$JAVA_HOME/bin/java" && echo 'java executable exists'
test -x "$JAVA_HOME/bin/javac" && echo 'javac executable exists'
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version

command -v java
command -v javac
java -version
javac -version
~~~

`export` cho phép các tiến trình con kế thừa `JAVA_HOME` và `PATH`. Điều chỉnh trong terminal không tự đổi JDK của tiến trình IDE, server hoặc terminal khác đã được khởi động trước đó.

Để giữ thiết lập khi mở terminal mới, thêm hai dòng `export` tương ứng vào file khởi tạo shell **được phiên shell thực sự nạp**, ví dụ `~/.bashrc` cho bash tương tác hoặc `~/.zshrc` cho zsh. Với login shell hoặc CI, file được nạp có thể khác; hãy xác định shell/kiểu phiên trước khi sửa và mở phiên mới để kiểm chứng. Máy dùng package manager hay `update-alternatives` có thể có thêm cơ chế quản lý Java; chỉnh một symlink hệ thống và đặt `JAVA_HOME` là hai thao tác khác nhau.

## 6. macOS (zsh)

macOS cung cấp tiện ích `/usr/libexec/java_home` để xác định các bản JDK đã được hệ thống nhận diện:

~~~zsh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 21
java -version
javac -version
which -a java
which -a javac
java -XshowSettings:properties -version 2>&1 | grep -E 'java.home|java.version|java.vendor'
~~~

Trong đó `-V` liệt kê JDK được nhận diện, còn `-v 21` yêu cầu chọn bản phù hợp Java 21. Nếu không tìm được, cần cài/đăng ký JDK phù hợp trước khi cấu hình.

Đặt biến cho phiên zsh hiện tại:

~~~zsh
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"

printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
java -version
javac -version
~~~

Để dùng ở những phiên zsh tương tác mới, có thể thêm hai dòng `export` vào `~/.zshrc`, rồi mở terminal mới và kiểm tra lại. Với shell khác hoặc lệnh khởi động qua IDE, cơ chế nạp biến môi trường có thể khác.

**Lưu ý macOS:** `/usr/bin/java` có thể là launcher do hệ điều hành quản lý, nên chỉ thấy vị trí đó qua `which` chưa đủ kết luận JDK nào đã thực sự được gọi. Kết hợp `java -version`, `java.home` và `/usr/libexec/java_home` để xác minh.

## 7. Kiểm tra bằng một chương trình Java chạy được

Lệnh shell là lớp kiểm tra đầu tiên. Để biết **chính tiến trình Java** nhìn thấy điều gì, tạo file `RuntimeIdentity.java` với nội dung đầy đủ:

~~~java
public class RuntimeIdentity {
    public static void main(String[] args) {
        System.out.println("JAVA_HOME=" + System.getenv("JAVA_HOME"));
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
    }
}
~~~

Trong thư mục chứa file, chạy:

~~~bash
javac RuntimeIdentity.java
java RuntimeIdentity
~~~

Ví dụ này tương thích Java 17+ và cũng chạy trên các bản JDK Java thông dụng khác. `javac` biên dịch file thành `RuntimeIdentity.class`, sau đó `java` khởi chạy main class. Đầu ra gồm **bốn dòng theo đúng thứ tự trong code**; các giá trị phụ thuộc máy thật, nên không thể gán sẵn một phiên bản hoặc thư mục cố định làm stdout chung.

Hãy so sánh dòng `JAVA_HOME=...` với dòng `java.home=...`. Nếu khác, điều đó chưa tự động là lỗi: nó cho biết **biến môi trường do shell truyền** không nhất thiết trùng **runtime thực tế của tiến trình**. Nếu yêu cầu môi trường là dùng cùng một JDK, cần tiếp tục kiểm tra `PATH`, alias và cách khởi chạy.

Để đối chiếu không qua `PATH`, sau khi biên dịch hãy thay lệnh `java RuntimeIdentity` bằng executable trong `JAVA_HOME`:

- PowerShell: `& "$env:JAVA_HOME\bin\java.exe" RuntimeIdentity`
- cmd.exe: `"%JAVA_HOME%\bin\java.exe" RuntimeIdentity`
- Linux/macOS: `"$JAVA_HOME/bin/java" RuntimeIdentity`

Kết quả có thể khác nếu lệnh `java` mặc định đã chọn một JDK khác. Chạy file class với runtime cũ hơn version biên dịch có thể dẫn đến `UnsupportedClassVersionError`; lỗi này thường cho biết độ tương thích Java compile/runtime không khớp.

## 8. JAVA_HOME, Gradle Wrapper, Gradle JVM và Java Toolchains

### 8.1. Wrapper cố định phiên bản Gradle, không thay mọi thiết lập Java

Trong một dự án đã có **Gradle Wrapper**, gọi tại thư mục gốc dự án:

~~~bash
# Linux/macOS
./gradlew --version
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat --version
~~~

Wrapper gồm `gradlew`/`gradlew.bat` và các file bên dưới `gradle/wrapper`; cấu hình `gradle/wrapper/gradle-wrapper.properties` định danh **bản phân phối Gradle** cần chạy. Wrapper có thể tải bản Gradle đó khi chưa có sẵn. Nó không tự cài một JDK theo yêu cầu mọi task, cũng không bảo đảm bản JDK chạy Gradle là JDK dùng compile.

`./gradlew --version` hoặc `.\gradlew.bat --version` hiển thị thông tin Gradle và JVM/launcher tương ứng theo phiên bản Gradle. Tuy nhiên, một hệ thống có thể chạy **Gradle Daemon** với JVM được chỉ định riêng. Trong các phiên bản Gradle mới, thông tin launcher/daemon JVM có thể được trình bày riêng. Vì vậy, đừng chỉ suy ra toàn bộ Java compile/test từ một dòng phiên bản của Wrapper.

Gradle thường chọn JVM chạy build dựa trên môi trường khởi động (`JAVA_HOME` hoặc `java` trên `PATH`) **trừ khi** có thiết lập ghi đè, chẳng hạn `org.gradle.java.home` hoặc **Daemon JVM criteria**. Theo Gradle hiện hành, Daemon JVM criteria (nếu được cấu hình) có thể ưu tiên hơn cả `JAVA_HOME` và `org.gradle.java.home`. `org.gradle.java.home` điều chỉnh Java home của quá trình build/daemon, không trực tiếp thay JVM khởi động Gradle client. Do đó, sửa `JAVA_HOME` chưa chắc làm daemon chạy ngay JDK mới.

### 8.2. JVM chạy Gradle có thể khác JDK biên dịch

Giả sử dự án sử dụng Gradle Java plugin và khai báo trong `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Đây là **một đoạn build Gradle tối thiểu minh họa Java Toolchains**, không phải cấu hình đầy đủ cho một ứng dụng Spring Boot. Khi task Java phù hợp sử dụng toolchain này, Gradle chọn JDK 21 để biên dịch; JVM chạy chính Gradle vẫn có thể là bản khác, miễn bản đó tương thích với Gradle đang dùng. Toolchains có thể tự phát hiện JDK đã cài hoặc tải JDK nếu môi trường và repository cung cấp toolchain được cấu hình.

Ở dự án có Java toolchain support, một cách tham khảo các Java installations Gradle nhận diện là:

~~~bash
./gradlew -q javaToolchains
~~~

Trên Windows dùng `.\gradlew.bat -q javaToolchains`. Danh sách Gradle thấy được **không phải** bằng chứng rằng tất cả task chắc chắn dùng cùng một JDK; xem khai báo toolchain, task `JavaCompile`, `Test` và các override nếu có.

Một bảng phân biệt cần ghi nhớ:

| Thành phần | Thiết lập điều khiển thường gặp | Cách kiểm chứng |
| --- | --- | --- |
| `java` gọi từ terminal | Shell command resolution, `PATH`, alias | `where.exe` / `Get-Command` / `type -a`, `java -version`, `java.home` |
| Gradle distribution | Wrapper properties | `gradlew --version` |
| JVM chạy Gradle build/daemon | Môi trường, `org.gradle.java.home`, Daemon JVM criteria hoặc IDE Gradle JVM | Thông tin JVM Gradle và cấu hình daemon tương ứng |
| JDK compiler/test của Gradle | Java Toolchains hoặc task configuration | `javaToolchains`, khai báo build và thông tin task thực thi |
| JVM chạy sản phẩm đóng gói | Lệnh khởi chạy sản phẩm và môi trường deploy | `java -version` đúng nơi chạy, `java.home`, startup logs khi phù hợp |

Java **toolchain** có thể quyết định JDK compile/test độc lập `JAVA_HOME`. Mặt khác, `sourceCompatibility` hoặc `targetCompatibility` đặt mức tương thích ngôn ngữ/bytecode nhưng **không tự chọn JDK compiler**; khi cần ngăn dùng API mới hơn mức runtime đích, phải xem xét tùy chọn `--release` của compiler và chính sách toolchain.

Nếu vừa đổi thiết lập JVM của Gradle nhưng thấy daemon vẫn có hành vi cũ, có thể kiểm tra cấu hình daemon, rồi sử dụng `./gradlew --stop` / `.\gradlew.bat --stop` để dừng Gradle daemons của Gradle version tương ứng trước khi xác minh lại. Chỉ làm việc này khi thực sự cần vì nó tác động đến các build/daemon đang dùng trên máy.

### 8.3. Maven Wrapper cũng cần Java

Với dự án dùng Maven Wrapper, `./mvnw -version` (Linux/macOS) hoặc `.\mvnw.cmd -version` (Windows PowerShell) cho biết phiên bản Maven đang chạy và Java runtime mà Maven sử dụng. Wrapper giúp dự án chọn bản Maven; nó không có nghĩa `JAVA_HOME` và toolchain sẽ tự khớp ở mọi môi trường. Với Maven toolchains hoặc IDE launcher, cần kiểm tra thêm cấu hình cụ thể của dự án.

## 9. Các môi trường dễ cho kết quả khác nhau

- **Terminal và IDE:** JDK của Project SDK, Gradle JVM của IDE và `java` trong terminal có thể khác nhau. Khi chạy Gradle qua IntelliJ IDEA, kiểm tra phần Gradle JVM trong cấu hình IDE; mở terminal tích hợp mới nếu vừa đổi biến môi trường. Đừng lấy `java -version` trong terminal làm bằng chứng duy nhất cho một build do IDE khởi chạy.
- **CI/CD:** mỗi runner/job có biến môi trường và đường dẫn Java riêng. Cần in thông tin Java trong **đúng job/step** dùng build; cấu hình Java ở máy lập trình không tự lan sang runner. Nếu CI có bước setup JDK, kiểm tra thứ tự step và job nơi build chạy.
- **Docker/Container:** `JAVA_HOME` của máy host không quyết định Java bên trong image. Kiểm tra Java từ bên trong container hoặc build stage tương ứng.
- **WSL:** Windows PowerShell và Linux shell trong WSL là hai môi trường khác nhau. Dùng JDK, biến môi trường và cú pháp shell đúng bên đang xây dựng ứng dụng.
- **Nhiều JDK và trình quản lý phiên bản:** SDKMAN!, asdf, jEnv hoặc cơ chế tương tự có thể thay `PATH`/`JAVA_HOME` khi vào thư mục hay mở terminal. Sau mỗi lần chuyển phiên bản, kiểm tra lại executable và JVM thực tế.
- **Shell đang cache vị trí chương trình:** một số shell ghi nhớ lệnh từng tìm thấy. Nếu đã đổi `PATH` mà kết quả chưa cập nhật, mở phiên mới hoặc dùng cơ chế làm mới của shell (ví dụ `hash -r` trong bash) rồi kiểm tra lại.

## 10. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý và bằng chứng |
| --- | --- | --- |
| `java` không được nhận diện | Không cài JDK hoặc `PATH` thiếu thư mục `bin` đúng | Xác nhận file Java thật sự tồn tại, thêm đường dẫn phù hợp, mở terminal mới và tìm lại executable |
| `JAVA_HOME is set to an invalid directory` | `JAVA_HOME` trỏ đến `bin`, file `java`, JDK đã di chuyển hoặc đường dẫn sai | Chỉ định lại **thư mục gốc JDK**, kiểm tra tồn tại `bin/java` và `bin/javac` |
| `java -version` vẫn là phiên bản cũ | Java cũ đứng trước trên `PATH`, alias/function, terminal cũ hoặc version manager thay đường dẫn | Đọc `Get-Command`/`where.exe`/`type -a`, `PATH` và `java.home`; đối chiếu lệnh Java trực tiếp trong `JAVA_HOME` |
| `javac` không tồn tại nhưng `java` chạy được | Runtime tối giản, JDK thiếu hoặc compiler không ở `PATH` | Cài/đổi sang JDK có `javac`, dùng đường dẫn trực tiếp để thử |
| `javac -version` khác `java -version` | Compiler và runtime từ hai thư mục khác nhau | Tìm từng executable; sửa `PATH` và `JAVA_HOME`, xác minh cả hai |
| Gradle/Wrapper báo không hỗ trợ Java hiện tại | Phiên bản Gradle hoặc plugin không tương thích với JVM khởi động build | Đọc lỗi thật, kiểm tra Gradle wrapper version và bảng compatibility; chọn JVM phù hợp hoặc nâng Gradle theo quy trình dự án |
| Gradle compile vẫn dùng JDK khác `JAVA_HOME` | Java Toolchains, `org.gradle.java.home`, Daemon JVM criteria hoặc IDE JVM khác | Kiểm tra đúng cấu hình và task; phân biệt daemon JVM với compiler toolchain |
| Bản build chạy được trên máy A nhưng lỗi `UnsupportedClassVersionError` trên máy B | Runtime máy B cũ hơn class-file version được compile | Xem runtime thực tế của máy B và bytecode target của bản build; điều chỉnh toolchain/target hoặc runtime |
| Thay `JAVA_HOME` xong nhưng build trong IDE/CI chưa đổi | Tiến trình chưa nhận biến mới hoặc môi trường cách ly | Mở lại tiến trình liên quan hoặc sửa đúng CI job/IDE setting, chạy lại lệnh xác minh tại nơi build thực hiện |

**Không xử lý sai JDK bằng cách xóa bừa JDK khác, thay toàn bộ `PATH`, bỏ qua test hoặc sửa cấu hình ứng dụng Spring Boot không liên quan.** Trước tiên chỉ rõ công cụ nào đang chạy bản Java nào.

## 11. Quy trình kiểm tra ngắn trước khi build Spring Boot

### Trường hợp sử dụng Gradle Wrapper

1. Xác nhận JDK mục tiêu thực sự có `bin/java` và `bin/javac`.
2. Đặt `JAVA_HOME` thành **JDK root** và bảo đảm `PATH` ưu tiên `JAVA_HOME/bin` nếu muốn lệnh `java` trong shell trùng với nó.
3. In `JAVA_HOME`, vị trí executable; chạy `java -version`, `javac -version` và `java -XshowSettings:properties -version`.
4. Ở thư mục dự án, chạy `./gradlew --version` hoặc `.\gradlew.bat --version` để xác nhận phiên bản Gradle/JVM; đối chiếu giới hạn tương thích.
5. Nếu dự án dùng Java Toolchains, xem cấu hình toolchain và `javaToolchains` khi khả dụng. Khi cần xác nhận compiler/test JVM thực tế, kiểm tra task/build logs thích hợp.
6. **Sau khi** chọn đúng toolchain và lệnh build, mới chạy task build/packaging theo quy trình dự án. Nếu app dùng `bootJar`, nhớ rằng JVM để chạy `java -jar` tại môi trường triển khai cũng cần được kiểm chứng riêng.

Với người học, cách diễn giải kết quả có giá trị nhất là: “Terminal này đang gọi `java` từ đâu, báo phiên bản gì? `JAVA_HOME` trỏ đến JDK nào? Gradle được chạy bằng JVM nào? Gradle compile bằng JDK nào?” Khi trả lời được bốn câu đó bằng bằng chứng, việc chẩn đoán lỗi Java và Wrapper trở nên rõ ràng.

## 12. Tài liệu chính thống tham khảo

- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Gradle Daemon: https://docs.gradle.org/current/userguide/gradle_daemon.html
- Gradle — Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
- Gradle — Java Compatibility: https://docs.gradle.org/current/userguide/compatibility.html
- Oracle JDK 21 — `java` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

Lệnh, giao diện terminal, cơ chế Gradle daemon và mức Java hỗ trợ có thể khác theo hệ điều hành và phiên bản công cụ. Vì vậy, kết quả trên **máy và job thật** cùng tài liệu đúng phiên bản luôn là căn cứ cuối cùng.