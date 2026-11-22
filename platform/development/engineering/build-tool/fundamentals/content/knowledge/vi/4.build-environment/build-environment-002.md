# JAVA_HOME, PATH và cách xác định JDK thực tế được sử dụng

Một máy tính có thể cài nhiều phiên bản Java cùng lúc: JDK 17 cho một dự án cũ, JDK 21 cho dự án mới, hoặc một bản JDK do IDE hay công cụ quản lý phiên bản cung cấp. Vì vậy, câu hỏi “máy đã cài Java chưa?” chưa đủ để xác định một lần build sẽ dùng JDK nào. Cần biết shell tìm thấy lệnh Java ở đâu, biến môi trường `JAVA_HOME` đang trỏ đến đâu, và build tool hoặc IDE có lựa chọn JDK riêng hay không.

Hai thành phần thường gặp nhất là `JAVA_HOME` và `PATH`. Chúng có liên quan nhưng giữ hai vai trò khác nhau: `JAVA_HOME` cho biết một thư mục JDK mà nhiều công cụ có thể sử dụng; `PATH` giúp hệ điều hành tìm chương trình khi người dùng gõ tên lệnh như `java` hoặc `javac`. Việc hiểu cách hai biến này phối hợp sẽ giúp xác định đúng JDK mà terminal, Maven, Gradle, IDE và CI đang sử dụng.

## 1. Phân biệt JDK, Java runtime và các lệnh Java

**JDK (Java Development Kit)** là bộ công cụ dành cho phát triển Java. Một JDK hiện đại thường bao gồm JVM và các công cụ như:

- `java`: khởi chạy ứng dụng Java.
- `javac`: biên dịch mã nguồn `.java` thành bytecode `.class`.
- `jar`: tạo và thao tác với tệp JAR.
- `javadoc`: tạo tài liệu API từ mã nguồn.
- Các công cụ chẩn đoán và phát triển khác.

JVM (Java Virtual Machine) thực thi bytecode Java. Lệnh `java` là launcher để khởi động JVM; bản thân lệnh `java` không phải trình biên dịch. Muốn biên dịch mã nguồn Java bằng bộ công cụ dòng lệnh thông thường, cần có `javac` từ một JDK tương thích.

Ngày nay, JDK thường cung cấp đầy đủ môi trường chạy ứng dụng cùng công cụ phát triển. Vì vậy, trong môi trường build, cách cấu hình phổ biến là trỏ `JAVA_HOME` đến thư mục gốc của JDK.

Ví dụ một JDK trên Windows:

```text
C:\Program Files\Eclipse Adoptium\jdk-21.0.5.11-hotspot\
├── bin\
│   ├── java.exe
│   ├── javac.exe
│   └── jar.exe
├── conf\
├── include\
├── jmods\
└── lib\
```

Với cấu trúc này, `JAVA_HOME` phải trỏ đến thư mục `jdk-21.0.5.11-hotspot`, tức thư mục chứa `bin`, `conf`, `include` và `lib`. Nó không trỏ trực tiếp đến thư mục `bin`.

## 2. JAVA_HOME là gì?

`JAVA_HOME` là biến môi trường thường được các công cụ Java dùng để xác định thư mục cài đặt JDK. Maven, Gradle Wrapper, máy chủ ứng dụng, script build và nhiều công cụ khác có thể đọc biến này để tìm bộ công cụ Java.

Ví dụ trên Windows:

```text
JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.5.11-hotspot
```

Trên Linux:

```text
JAVA_HOME=/usr/lib/jvm/temurin-21-jdk
```

Trên macOS, đường dẫn có thể nằm trong thư mục cài đặt JDK của nhà cung cấp hoặc được xác định bằng tiện ích hệ thống `java_home`.

`JAVA_HOME` là một quy ước được nhiều công cụ Java hiểu; nó không phải biến bắt buộc do bản thân JVM yêu cầu trong mọi trường hợp. Nếu lệnh `java` đã nằm trong `PATH`, bạn có thể chạy `java` dù `JAVA_HOME` chưa được thiết lập. Tuy nhiên, một số launcher hoặc build tool yêu cầu hoặc ưu tiên `JAVA_HOME`, nên môi trường build thường nên khai báo biến này rõ ràng.

### JAVA_HOME phải trỏ đến đâu?

Giá trị đúng là thư mục gốc của JDK:

```text
JAVA_HOME=C:\Java\jdk-21
```

Giá trị sai thường gặp là trỏ thẳng vào thư mục `bin`:

```text
JAVA_HOME=C:\Java\jdk-21\bin
```

Nhiều công cụ tự nối `bin\java.exe`, `bin\javac.exe` hoặc đường dẫn công cụ khác vào `JAVA_HOME`. Nếu biến đã chứa `bin`, công cụ có thể tìm nhầm `bin\bin\java.exe` và không khởi động được.

Không cần đặt dấu ngoặc kép bao quanh giá trị lưu trong biến môi trường. Dấu cách trong đường dẫn được xử lý khi công cụ sử dụng biến đó. Ví dụ:

```text
C:\Program Files\Java\jdk-21
```

## 3. PATH là gì và cách hệ điều hành tìm lệnh

`PATH` là biến môi trường chứa danh sách các thư mục mà shell hoặc hệ điều hành sẽ tìm khi người dùng nhập tên chương trình mà không ghi đầy đủ đường dẫn.

Ví dụ, khi gõ:

```powershell
java -version
```

shell cần tìm tệp thực thi `java` trong các thư mục có trong `PATH`. Trên Windows, các thư mục thường được phân cách bằng dấu chấm phẩy (`;`). Trên Linux và macOS, các thư mục được phân cách bằng dấu hai chấm (`:`).

Một `PATH` trên Windows có thể chứa:

```text
C:\Java\jdk-21\bin;
C:\Windows\System32;
C:\Windows;
```

Khi `C:\Java\jdk-21\bin` xuất hiện trước các thư mục chứa bản Java khác, lệnh `java` thường được tìm thấy ở JDK 21 trước. Nếu có nhiều thư mục chứa `java.exe`, thứ tự tìm kiếm có thể quyết định phiên bản được chạy.

### Mối quan hệ giữa JAVA_HOME và PATH

Hai biến thường được cấu hình kết hợp:

```text
JAVA_HOME = C:\Java\jdk-21
PATH      = %JAVA_HOME%\bin;...
```

`JAVA_HOME` xác định thư mục JDK. `PATH` chứa thư mục `bin` của JDK để shell có thể tìm các lệnh Java bằng tên ngắn.

Hai biến có thể không trỏ đến cùng một JDK. Ví dụ:

```text
JAVA_HOME = C:\Java\jdk-21
PATH      = C:\Java\jdk-17\bin;...
```

Trong tình huống này, shell có thể chạy `java.exe` của JDK 17 vì thư mục JDK 17 đứng trước trong `PATH`, trong khi một công cụ đọc `JAVA_HOME` có thể chọn JDK 21. Do đó, chỉ kiểm tra một trong hai biến chưa đủ để kết luận toàn bộ môi trường đang dùng phiên bản nào.

## 4. Cách kiểm tra trên Windows

Các ví dụ dưới đây sử dụng PowerShell. Nếu đang dùng Command Prompt (`cmd.exe`), cú pháp đọc biến môi trường sẽ khác.

### Bước 1: xem JAVA_HOME

```powershell
$env:JAVA_HOME
```

Lệnh in ra giá trị `JAVA_HOME` trong tiến trình PowerShell hiện tại. Nếu kết quả rỗng, biến chưa được đặt trong môi trường của shell này.

Có thể kiểm tra thư mục có tồn tại và chứa lệnh Java hay không:

```powershell
if ([string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
    Write-Output 'JAVA_HOME is not set'
} else {
    Test-Path $env:JAVA_HOME
    Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe')
    Test-Path (Join-Path $env:JAVA_HOME 'bin\javac.exe')
}
```

Kết quả `True` cho hai đường dẫn executable cho biết thư mục đang trỏ đến có cả launcher và compiler tương ứng.

### Bước 2: xem các thư mục trong PATH

```powershell
$env:Path -split ';'
```

Lệnh tách `PATH` thành từng thư mục để dễ đọc. Tìm các mục có chứa `Java`, `jdk`, `jre`, thư mục `bin` hoặc đường dẫn của công cụ quản lý phiên bản Java.

### Bước 3: tìm lệnh java mà PowerShell sẽ gọi

```powershell
Get-Command java -All
Get-Command javac -All
```

`Get-Command` cho biết PowerShell nhận diện các lệnh có tên tương ứng ở đâu. Tùy cấu hình, kết quả có thể gồm executable, alias, function hoặc shim do một công cụ quản lý phiên bản tạo ra.

Để xem các tệp thực thi tìm thấy theo cơ chế tìm kiếm của Windows, dùng `where.exe`:

```powershell
where.exe java
where.exe javac
```

`where.exe` có thể trả về nhiều đường dẫn. Đường dẫn đầu tiên thường là ứng viên được chọn khi gọi lệnh bằng tên ngắn trong môi trường đó. Nếu kết quả chứa thư mục của nhiều JDK, cần xem lại thứ tự `PATH` và cấu hình của công cụ đang chạy.

### Bước 4: kiểm tra phiên bản runtime và compiler

```powershell
java -version
javac -version
```

Hai lệnh kiểm tra phiên bản của `java` và `javac` mà shell đang tìm thấy. Nếu `java` chạy được nhưng `javac` không được nhận diện, `PATH` có thể đang trỏ đến một runtime không có compiler, hoặc thư mục JDK chưa được thêm đúng cách.

Để kiểm tra trực tiếp JDK được chỉ định bởi `JAVA_HOME`, gọi executable bằng đường dẫn đầy đủ:

```powershell
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
```

Cách này bỏ qua việc tìm lệnh `java` hoặc `javac` trong `PATH`, nhờ đó có thể so sánh JDK tại `JAVA_HOME` với JDK mà shell đang gọi.

### Cú pháp tương ứng trong Command Prompt

```bat
echo %JAVA_HOME%
echo %PATH%
where java
where javac
java -version
javac -version
```

Trong Command Prompt, `where` là lệnh tìm executable. Trong PowerShell, tên `where` thường là alias của `Where-Object`, vì vậy nên viết rõ `where.exe` khi cần gọi chương trình Windows.

## 5. Cách kiểm tra trên Linux và macOS

Trong shell kiểu POSIX như Bash hoặc Zsh, có thể kiểm tra biến và lệnh như sau:

```bash
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
```

`command -v` cho biết shell sẽ phân giải tên lệnh thành đường dẫn hoặc đối tượng nào. `type -a` liệt kê các cách phân giải được tìm thấy, hữu ích khi có nhiều JDK hoặc có shim đứng trước executable thật.

Trên Linux, `PATH` thường được phân cách bằng dấu `:`. Có thể in mỗi thư mục trên một dòng bằng:

```bash
printf '%s\n' "$PATH" | tr ':' '\n'
```

Trên macOS, tiện ích `/usr/libexec/java_home` có thể liệt kê các JDK đã được hệ thống nhận diện:

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 21
```

Lệnh thứ hai trả về đường dẫn JDK phù hợp với phiên bản 21 nếu đã cài và được hệ thống nhận diện. Có thể dùng kết quả này để đặt `JAVA_HOME` trong phiên shell hiện tại:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"
```

## 6. Thiết lập JAVA_HOME và PATH

### Thiết lập tạm thời trên PowerShell

Để thử một JDK trong cửa sổ PowerShell hiện tại:

```powershell
$env:JAVA_HOME = 'C:\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Các phép gán `$env:` chỉ thay đổi môi trường của tiến trình PowerShell hiện tại và các tiến trình con được khởi chạy từ nó. Chúng không tự cập nhật biến môi trường lâu dài của tài khoản Windows.

### Thiết lập tạm thời trên Command Prompt

```bat
set "JAVA_HOME=C:\Java\jdk-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"

java -version
javac -version
```

Lệnh `set` chỉ thay đổi môi trường của cửa sổ Command Prompt hiện tại và các tiến trình con.

### Thiết lập tạm thời trên Linux

```bash
export JAVA_HOME=/opt/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

### Lưu cấu hình lâu dài

Trên Windows, có thể mở phần quản lý Environment Variables trong System Properties, thêm biến `JAVA_HOME` ở phạm vi User hoặc System, sau đó thêm `%JAVA_HOME%\bin` vào `Path` tương ứng. Chọn phạm vi User nếu chỉ tài khoản hiện tại cần JDK đó; chọn phạm vi System khi máy cần cấu hình dùng chung và bạn có quyền quản trị phù hợp.

Trên Linux hoặc macOS, cấu hình thường được đặt trong tệp khởi tạo shell phù hợp, chẳng hạn `~/.bashrc`, `~/.bash_profile` hoặc `~/.zshrc`, tùy shell và cách đăng nhập. Ví dụ:

```bash
export JAVA_HOME=/opt/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
```

Sau khi thay đổi cấu hình lâu dài, mở terminal mới hoặc nạp lại tệp cấu hình tương ứng. Mỗi tiến trình chỉ nhận môi trường tại thời điểm nó được khởi chạy; terminal hoặc IDE đang mở có thể vẫn giữ giá trị cũ.

## 7. Vì sao thay đổi JAVA_HOME nhưng Java vẫn chạy phiên bản cũ?

Đây là tình huống thường gặp khi máy cài nhiều JDK. Có một số nguyên nhân cần phân biệt:

**PATH vẫn ưu tiên JDK cũ.** `JAVA_HOME` đã đổi sang JDK 21 nhưng thư mục `C:\Java\jdk-17\bin` vẫn đứng trước `%JAVA_HOME%\bin` trong `PATH`. Khi gõ `java`, shell vẫn tìm thấy JDK 17 trước.

**Terminal chưa nhận môi trường mới.** Một terminal được mở trước khi cập nhật biến môi trường có thể tiếp tục giữ bản sao cũ của `PATH` và `JAVA_HOME`. Hãy mở terminal mới rồi kiểm tra lại.

**IDE đã được khởi chạy từ trước.** IDE là một tiến trình riêng và thường giữ môi trường được kế thừa khi khởi động. Đóng rồi mở lại IDE nếu muốn nó nhận môi trường mới; đồng thời kiểm tra JDK được cấu hình trực tiếp trong IDE.

**Công cụ dùng cấu hình riêng.** Gradle, Maven, IDE hoặc script có thể chọn JDK từ một thiết lập khác. Khi đó, thay đổi `JAVA_HOME` trong terminal chưa chắc thay đổi JVM hoặc compiler mà công cụ sử dụng.

**Lệnh Java được cung cấp bởi shim hoặc trình quản lý phiên bản.** Các công cụ như SDKMAN, jenv, asdf hoặc những trình quản lý JDK trên Windows có thể đặt một shim vào `PATH`. Shim sẽ chọn JDK theo cấu hình riêng của nó. Kết quả `command -v`, `type -a`, `Get-Command` hoặc `where.exe` giúp nhận diện tình huống này.

## 8. Xác định JDK mà Gradle thực tế sử dụng

Khi làm việc với Gradle, cần phân biệt ít nhất ba lựa chọn:

1. **JDK chạy Gradle client:** JVM được dùng để khởi động Gradle Wrapper hoặc lệnh `gradle`.
2. **JDK chạy Gradle daemon:** JVM thực hiện phần lớn công việc của build. Nó có thể chịu ảnh hưởng của cấu hình Gradle như `org.gradle.java.home`, cấu hình daemon JVM hoặc thiết lập của IDE.
3. **JDK toolchain:** JDK mà các task biên dịch, kiểm thử hoặc chạy ứng dụng sử dụng khi dự án khai báo Java toolchain. Toolchain có thể khác JDK chạy Gradle.

### Kiểm tra JVM chạy Gradle

Trên Windows:

```powershell
.\gradlew.bat -version
```

Trên Linux hoặc macOS:

```bash
./gradlew -version
```

Kết quả hiển thị phiên bản Gradle cùng thông tin JVM/Java home liên quan đến launcher và daemon. Đọc các dòng `Launcher JVM` và `Daemon JVM` nếu phiên bản Gradle đang dùng hiển thị cả hai. Chúng giúp xác định JVM mà Gradle client và daemon sử dụng.

Nếu hai giá trị khác nhau, hãy kiểm tra cấu hình Gradle và môi trường khởi chạy. Một nguồn ghi đè phổ biến là thuộc tính `org.gradle.java.home` trong `gradle.properties`, có thể nằm ở thư mục dự án hoặc Gradle User Home. IDE cũng có thể có thiết lập Gradle JVM riêng.

Ví dụ cấu hình trong `gradle.properties`:

```properties
org.gradle.java.home=C:/Java/jdk-21
```

Đường dẫn cần trỏ đến thư mục JDK. Cấu hình này cho Gradle biết Java home dùng cho tiến trình build/daemon theo cơ chế của Gradle. Khi kiểm tra, cần xem cả cấu hình cấp dự án lẫn cấu hình trong Gradle User Home vì chúng có thể ảnh hưởng đến kết quả.

### Kiểm tra JDK toolchain

Một dự án có thể yêu cầu compiler JDK 21 dù Gradle daemon đang chạy bằng JDK khác. Ví dụ:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Khai báo này yêu cầu Gradle chọn Java toolchain có phiên bản ngôn ngữ 21 cho các task được tích hợp với toolchain. Nó không có nghĩa JVM đang chạy Gradle tự động đổi thành JDK 21.

Với Gradle có hỗ trợ task báo cáo toolchain, có thể chạy:

```powershell
.\gradlew.bat javaToolchains
```

Hoặc:

```bash
./gradlew javaToolchains
```

Task này giúp xem các toolchain Gradle phát hiện được, vị trí cài đặt và thông tin liên quan. Khi cần xác định compiler được chọn cho một task cụ thể, hãy đối chiếu khai báo `java.toolchain` hoặc `javaCompiler` trong build logic với log của task đó.

### Phân biệt toolchain với phiên bản bytecode đích

Các cấu hình như `sourceCompatibility`, `targetCompatibility` hoặc tùy chọn `--release` mô tả mức ngôn ngữ, bytecode hoặc API đích mà quá trình biên dịch cần tuân theo. Chúng không tự xác định JVM dùng để chạy Gradle và cũng không nhất thiết chọn một JDK cài đặt cụ thể.

Ví dụ, một build có thể chạy Gradle trên JDK 21, dùng compiler toolchain JDK 21, nhưng yêu cầu tạo đầu ra tương thích Java 17 bằng cấu hình release phù hợp. Đây là ba quyết định riêng: JVM chạy build, compiler được chọn và nền tảng Java mà sản phẩm hướng tới.

## 9. Xác định JDK mà Maven thực tế sử dụng

Để xem Maven đang chạy bằng Java nào, dùng:

```powershell
mvn -version
```

Hoặc trên Linux/macOS:

```bash
mvn -version
```

Kết quả thường hiển thị phiên bản Maven, phiên bản Java, nhà cung cấp Java và `Java home`. Đây là thông tin quan trọng để biết JVM đang chạy tiến trình Maven.

Nếu sử dụng Maven Wrapper, có thể chạy:

```powershell
.\mvnw.cmd -version
```

hoặc:

```bash
./mvnw -version
```

Wrapper cố định phiên bản Maven cho dự án, nhưng bản thân Maven vẫn cần một JDK để chạy. Vì vậy, Wrapper không đồng nghĩa với việc dự án tự mang theo một JDK.

### Maven Toolchains

Maven cũng có cơ chế Toolchains để một plugin như Maven Compiler Plugin sử dụng JDK được chọn riêng. Khi cấu hình này được dùng, JDK chạy Maven và JDK dùng để biên dịch có thể khác nhau.

Thông tin toolchain có thể được khai báo trong `~/.m2/toolchains.xml`, sau đó dự án hoặc plugin lựa chọn toolchain phù hợp. Vì thế, `mvn -version` xác nhận Java home của tiến trình Maven, nhưng chưa đủ để chứng minh compiler plugin đang dùng cùng JDK nếu dự án có cấu hình Toolchains.

Khi điều tra, hãy xem:

- Kết quả `mvn -version` để biết JVM chạy Maven.
- Cấu hình `~/.m2/toolchains.xml` nếu dự án sử dụng Maven Toolchains.
- Cấu hình Maven Compiler Plugin và log thực thi khi cần xác nhận compiler được chọn.

## 10. IDE có thể dùng JDK khác terminal

IDE thường có nhiều lựa chọn Java độc lập. Một dự án có thể đồng thời có:

- **Project SDK/JDK:** JDK mà IDE dùng để phân tích mã nguồn và hỗ trợ dự án.
- **JDK chạy Maven hoặc Gradle:** JVM dùng khi IDE khởi chạy build tool.
- **JDK compiler/toolchain:** JDK được chọn để biên dịch mã nguồn.
- **JRE/JDK của cấu hình chạy:** Java executable dùng khi chạy một ứng dụng hoặc test configuration cụ thể.

Ví dụ, IntelliJ IDEA có Project SDK và Gradle JVM riêng. Project SDK là lựa chọn của dự án trong IDE; Gradle JVM là lựa chọn cho tiến trình Gradle được IDE khởi chạy. Chọn JDK 21 ở một mục không tự động bảo đảm tất cả các mục còn lại cũng là JDK 21.

VS Code và các IDE khác cũng có thể lưu lựa chọn runtime hoặc build tool riêng trong workspace, user settings hoặc cấu hình extension. Khi terminal tích hợp hiển thị một phiên bản nhưng nút Build/Run trong IDE dùng phiên bản khác, hãy kiểm tra thiết lập của IDE và build tool tương ứng.

## 11. CI và môi trường chạy tự động

Trên CI, không nên suy luận JDK đang dùng chỉ từ máy phát triển. Mỗi job chạy trong một môi trường riêng, có thể là máy runner, container hoặc image đã được cấu hình sẵn.

Các nguồn quyết định JDK trên CI thường gồm:

- Image/container được chọn cho job.
- Bước cài đặt hoặc thiết lập JDK của pipeline.
- `JAVA_HOME` và `PATH` được runner cung cấp.
- Gradle/Maven configuration hoặc Java toolchain của dự án.
- JDK được cấu hình riêng trong script khởi chạy.

Để chẩn đoán, thêm các lệnh chỉ đọc vào bước log của pipeline:

```bash
echo "JAVA_HOME=$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
```

Nếu job dùng Gradle hoặc Maven, in thêm thông tin của chính build tool:

```bash
./gradlew -version
mvn -version
```

Trên Windows runner, dùng cú pháp PowerShell tương ứng như `$env:JAVA_HOME`, `Get-Command java -All`, `where.exe java` và `java -version`.

Log cần được tạo trong đúng job và đúng bước đang gặp vấn đề. Một bước cài JDK có thể đặt biến cho các bước tiếp theo nhưng không thay đổi tiến trình đã chạy trước đó. Tương tự, một container có `JAVA_HOME` riêng không nhất thiết dùng cùng JDK với máy host.

## 12. Quy trình chẩn đoán khi build dùng sai JDK

Khi build thất bại do sai phiên bản Java hoặc báo `invalid source release`, `Unsupported class file major version`, thiếu compiler hay không tìm thấy Java, hãy xác định từng lớp lựa chọn thay vì chỉ đổi `JAVA_HOME` một cách phỏng đoán.

### Bước 1: xác nhận JDK mong muốn

Đọc yêu cầu của dự án: phiên bản JDK tối thiểu/tối đa mà build tool hỗ trợ, phiên bản toolchain được khai báo và phiên bản Java đích của sản phẩm. Không mặc định phiên bản Java trong `PATH` là yêu cầu của dự án.

### Bước 2: kiểm tra môi trường shell

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
java -version
javac -version
```

Trên Linux/macOS:

```bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
```

Ghi lại đường dẫn và phiên bản thực tế, sau đó so sánh với JDK mong muốn.

### Bước 3: kiểm tra build tool

Với Gradle:

```powershell
.\gradlew.bat -version
```

Với Maven:

```powershell
mvn -version
```

So sánh Java home của build tool với kết quả kiểm tra shell. Nếu khác nhau, xem biến môi trường tại thời điểm khởi chạy, `org.gradle.java.home`, Gradle JVM của IDE hoặc cấu hình Maven Toolchains.

### Bước 4: kiểm tra compiler/toolchain của dự án

Tìm cấu hình `java.toolchain`, `javaCompiler`, Maven Toolchains hoặc cấu hình compiler tương ứng. Một build tool có thể chạy trên JDK A nhưng biên dịch bằng JDK B. Cần xác định đúng compiler được task sử dụng.

### Bước 5: kiểm tra tiến trình và daemon cũ

Nếu vừa đổi JDK, hãy mở terminal mới và khởi động lại IDE nếu cần. Gradle có thể tái sử dụng daemon đã chạy với JVM trước đó. Có thể dừng daemon Gradle bằng:

```powershell
.\gradlew.bat --stop
```

Hoặc:

```bash
./gradlew --stop
```

Sau đó chạy lại lệnh kiểm tra `-version`. Lệnh `--stop` dừng các Gradle daemon thuộc phiên bản Gradle tương ứng; nó không thay đổi cấu hình JDK. Cần xác nhận lại JVM được chọn sau khi daemon khởi động lại.

### Bước 6: kiểm tra lại từ đúng nơi chạy build

Nếu lỗi xảy ra khi nhấn nút Build trong IDE, hãy xác nhận bằng cấu hình IDE. Nếu lỗi chỉ xảy ra trên CI, hãy xem log của job CI. Kết quả từ một terminal độc lập không chứng minh rằng IDE hoặc CI dùng cùng môi trường.

## 13. Bảng phân biệt các nguồn chọn JDK

| Thành phần | Vai trò | Cách kiểm tra thường dùng |
|---|---|---|
| `JAVA_HOME` | Thư mục JDK mà công cụ có thể tham chiếu | `$env:JAVA_HOME` hoặc `echo "$JAVA_HOME"` |
| `PATH` | Danh sách thư mục dùng để tìm lệnh | `$env:Path -split ';'` hoặc `printf '%s\n' "$PATH"` |
| `java` | Launcher được shell phân giải | `Get-Command java -All`, `command -v java`, `java -version` |
| `javac` | Compiler được shell phân giải | `Get-Command javac -All`, `command -v javac`, `javac -version` |
| Gradle JVM | JVM chạy Gradle client/daemon | `gradlew -version`, cấu hình Gradle JVM và `org.gradle.java.home` |
| Gradle toolchain | JDK cho task tích hợp với toolchain | `javaToolchains`, `java.toolchain`, log task |
| Maven JVM | JVM chạy tiến trình Maven | `mvn -version` |
| Maven toolchain | JDK plugin Maven chọn riêng | `~/.m2/toolchains.xml` và cấu hình plugin |
| IDE SDK/Runtime | JDK do IDE hoặc cấu hình chạy chọn | Project SDK, Gradle JVM, Maven runner, Run Configuration |
| CI runtime | JDK của job/container | Log `JAVA_HOME`, `PATH`, `java -version` và build tool |

Không có một lệnh duy nhất luôn xác định được mọi JDK trong mọi tầng. Cần kiểm tra đúng thành phần thực hiện công việc đang được điều tra.

## 14. Ví dụ thực tế: máy có JDK 17 và JDK 21

Giả sử máy Windows có hai thư mục:

```text
C:\Java\jdk-17
C:\Java\jdk-21
```

Bạn đặt:

```text
JAVA_HOME=C:\Java\jdk-21
```

Nhưng `PATH` lại có thứ tự:

```text
C:\Java\jdk-17\bin
%JAVA_HOME%\bin
...
```

Khi chạy:

```powershell
java -version
```

shell có thể gọi JDK 17 vì thư mục của JDK 17 xuất hiện trước. Trong khi đó, nếu một launcher ưu tiên `JAVA_HOME`, nó có thể khởi chạy bằng JDK 21.

Để làm môi trường shell nhất quán với `JAVA_HOME`, đưa `%JAVA_HOME%\bin` lên trước thư mục JDK cũ trong `PATH`, hoặc loại bỏ mục cũ nếu không còn cần. Sau khi cập nhật, mở terminal mới và kiểm tra lại:

```powershell
$env:JAVA_HOME
where.exe java
where.exe javac
java -version
javac -version
```

Tiếp theo, chạy `.\gradlew.bat -version` hoặc `mvn -version` để kiểm tra build tool. Nếu dự án có toolchain, kiểm tra thêm cấu hình toolchain. Khi đó, bạn có thể phân biệt được shell đang gọi JDK nào, build tool đang chạy trên JDK nào và compiler đang được chọn từ JDK nào.

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Đặt `JAVA_HOME` là đủ để lệnh `java` đổi phiên bản | Shell thường tìm lệnh theo `PATH`; `PATH` có thể vẫn ưu tiên JDK khác. |
| `JAVA_HOME` phải trỏ đến thư mục `bin` | Thông thường nó trỏ đến thư mục gốc JDK; công cụ tự tìm executable bên trong `bin`. |
| `java -version` cho biết JDK mà mọi công cụ đang dùng | Lệnh chỉ cho biết launcher mà shell hiện tại phân giải; IDE và build tool có thể chọn JDK riêng. |
| `java -version` chạy được nghĩa là có thể biên dịch Java | Cần kiểm tra thêm `javac -version` hoặc compiler toolchain. |
| JDK chạy Gradle luôn là JDK biên dịch dự án | Java toolchain có thể chọn compiler JDK khác JVM chạy Gradle. |
| Maven Wrapper tự cung cấp JDK | Wrapper cố định phiên bản Maven; JVM chạy Maven vẫn đến từ môi trường hoặc cấu hình được chọn. |
| Đổi biến môi trường sẽ cập nhật mọi terminal và IDE đang mở | Tiến trình đang chạy thường giữ môi trường đã nhận lúc khởi động. |
| `targetCompatibility` hoặc `--release` chọn JDK chạy build | Chúng mô tả mức tương thích đầu ra; JVM chạy build và compiler toolchain là lựa chọn riêng. |

## 16. Checklist xác định JDK thực tế

Khi cần ghi nhận môi trường build, hãy lưu lại các thông tin sau:

1. Giá trị `JAVA_HOME` trong đúng terminal hoặc job đang chạy build.
2. Đường dẫn mà shell phân giải cho `java` và `javac`.
3. Kết quả `java -version` và `javac -version`.
4. Kết quả `gradlew -version` hoặc `mvn -version` của đúng wrapper/lệnh được sử dụng.
5. Cấu hình Gradle/Maven toolchain và JDK do IDE chọn, nếu có.
6. Môi trường CI/container, nếu lỗi chỉ xuất hiện trong pipeline.

Khi các thông tin này được ghi nhận cùng nhau, có thể lần theo chính xác tầng nào đang chọn JDK khác mong đợi. Đây là nền tảng để xử lý các lỗi build liên quan đến phiên bản Java mà không nhầm lẫn giữa môi trường shell, JVM của build tool và compiler của dự án.
