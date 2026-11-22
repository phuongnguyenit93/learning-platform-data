# Quản lý version JDK

## 1. Vì sao cần quản lý nhiều phiên bản JDK?

Trong thực tế, một máy phát triển có thể cần nhiều phiên bản Java cùng lúc. Dự án cũ có thể vẫn chạy trên Java 8 hoặc 11, trong khi dự án mới yêu cầu Java 17, 21 hoặc phiên bản mới hơn. Một số thư viện, framework, plugin build và môi trường triển khai cũng đặt ra yêu cầu phiên bản riêng.

**Quản lý version JDK** là quá trình cài đặt, lựa chọn, chuyển đổi và cố định phiên bản JDK phù hợp cho từng dự án hoặc môi trường. Mục tiêu là bảo đảm các lệnh biên dịch, chạy, kiểm thử và đóng gói đều sử dụng đúng bộ công cụ.

Ví dụ, cùng một máy có thể có:

- JDK 17 để duy trì một dịch vụ cũ.
- JDK 21 để phát triển ứng dụng mới.
- JDK 25 để thử nghiệm khả năng tương thích với một bản Java mới hơn.

Việc cài nhiều JDK không có nghĩa là chúng tự động được sử dụng đúng. Terminal, IDE, Maven, Gradle và CI có thể đang trỏ tới những JDK khác nhau. Vì vậy, cần biết công cụ nào đang chọn phiên bản nào và cách xác minh lựa chọn đó.

## 2. Phân biệt phiên bản Java, nhà cung cấp và bản cập nhật

Khi nói một dự án dùng Java 21, thông tin đó mới chỉ cho biết **feature release**. Một bản JDK còn có nhà cung cấp và số bản cập nhật cụ thể.

Ví dụ một chuỗi phiên bản có thể có dạng:

```text
21.0.5+11
│  │ │  └─ số build
│  │ └──── bản cập nhật
│  └────── phiên bản feature
└───────── phiên bản Java
```

Cách hiển thị chính xác có thể khác giữa các nhà cung cấp và bản phân phối.

### 2.1. Feature release và LTS

Java phát hành các feature release theo chu kỳ định kỳ. Một số phiên bản được nhà cung cấp hỗ trợ dài hạn (Long-Term Support, LTS), trong khi các phiên bản khác có thời gian hỗ trợ ngắn hơn.

Các feature release LTS thường được sử dụng làm mốc cho hệ thống doanh nghiệp. Ví dụ, Java 8, 11, 17, 21 và 25 là những mốc LTS phổ biến. Chính sách hỗ trợ và thời hạn cập nhật cụ thể phụ thuộc nhà cung cấp, hợp đồng hỗ trợ và chính sách của tổ chức.

Khi chọn phiên bản cho dự án, cần xem:

- Phiên bản tối thiểu mà framework và thư viện hỗ trợ.
- Phiên bản JDK mà môi trường production đang chạy.
- Thời gian hỗ trợ và cập nhật bảo mật.
- Khả năng tương thích của plugin build, công cụ kiểm thử và IDE.
- Kế hoạch nâng cấp của đội phát triển.

### 2.2. Nhà cung cấp JDK

Nhiều nhà cung cấp phân phối JDK tương thích với đặc tả Java, ví dụ Eclipse Temurin, Oracle JDK, Amazon Corretto, Azul Zulu và Microsoft Build of OpenJDK.

Các bản phân phối cùng feature release thường hướng tới khả năng tương thích Java, nhưng có thể khác về lịch phát hành bản vá, hỗ trợ nền tảng, chính sách cấp phép, công cụ đi kèm và dịch vụ hỗ trợ.

Với dự án nhóm hoặc production, nên thống nhất cả feature release và nhà cung cấp JDK khi có yêu cầu về hỗ trợ, kiểm toán hoặc tái lập môi trường. Không nên chỉ ghi “dùng Java 21” nếu đội cần một bản phân phối cụ thể.

## 3. Cài đặt song song nhiều JDK

Có thể cài nhiều JDK trên cùng máy. Mỗi bản nên nằm trong thư mục riêng để dễ nhận biết và tránh ghi đè lên nhau.

Ví dụ cách tổ chức thư mục:

```text
Windows:
C:\Dev\Java\jdk-17
C:\Dev\Java\jdk-21
C:\Dev\Java\jdk-25

Linux:
 /opt/jdks/jdk-17
 /opt/jdks/jdk-21
 /opt/jdks/jdk-25

macOS:
 /Library/Java/JavaVirtualMachines/
```

Trên macOS, bộ cài JDK thường tạo thư mục bundle có tên dạng `jdk-21.jdk` trong `/Library/Java/JavaVirtualMachines/`.

Có thể tải JDK từ website của nhà cung cấp hoặc cài bằng trình quản lý gói phù hợp hệ điều hành. Khi cài, hãy kiểm tra kiến trúc CPU (x64 hay ARM64), hệ điều hành và phiên bản cần dùng. Không tải bộ cài từ nguồn không đáng tin cậy.

Sau khi cài, ghi lại đường dẫn gốc của từng JDK. Đường dẫn gốc là thư mục chứa `bin`, `conf`, `include` và các thành phần JDK khác; `JAVA_HOME` phải trỏ đến thư mục này, không trỏ thẳng vào `bin`.

## 4. JAVA_HOME và PATH quyết định phiên bản đang được dùng như thế nào?

Hai cơ chế thường gặp nhất là `JAVA_HOME` và `PATH`.

- `JAVA_HOME` chỉ ra thư mục JDK mà công cụ build hoặc script có thể sử dụng.
- `PATH` xác định thứ tự hệ điều hành tìm chương trình khi bạn gõ lệnh như `java` hoặc `javac`.

Ví dụ, nếu `JAVA_HOME` trỏ tới JDK 21 nhưng `PATH` có đường dẫn JDK 17 đứng trước, lệnh `java` trong terminal vẫn có thể chạy JDK 17.

Do đó, chỉ thay đổi `JAVA_HOME` chưa chắc đã chuyển phiên bản đang chạy. Sau khi chuyển, cần xác minh cả hai biến và kết quả của lệnh Java.

### 4.1. Kiểm tra phiên bản và đường dẫn hiện tại

Trên mọi hệ điều hành, bắt đầu bằng:

```bash
java --version
javac --version
```

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

`Get-Command ... -All` cho biết những lệnh trùng tên mà PowerShell có thể tìm thấy. `where.exe` liệt kê các tệp thực thi tìm thấy trong PATH.

Trên Linux hoặc macOS:

```bash
echo "$JAVA_HOME"
type -a java
type -a javac
command -v java
command -v javac
```

Trên Linux, có thể kiểm tra đường dẫn thực của lệnh:

```bash
readlink -f "$(command -v java)"
```

Để xem runtime thực tế đang dùng thư mục nào, chạy:

```bash
java -XshowSettings:properties -version
```

Tìm thuộc tính `java.home` trong phần kết quả. Lưu ý `java.home` là thư mục runtime mà JVM đang dùng, không nhất thiết là đường dẫn gốc của bộ JDK cài đặt.

### 4.2. Chuyển JDK tạm thời trong Windows PowerShell

Đặt biến môi trường trong cửa sổ PowerShell hiện tại:

```powershell
$env:JAVA_HOME = "C:\Dev\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
```

Cách này có hiệu lực trong phiên PowerShell hiện tại và các tiến trình con được mở từ phiên đó. Nó không tự thay đổi cấu hình hệ thống hoặc các cửa sổ terminal đang mở khác.

Nếu PATH đã chứa thư mục `bin` của một JDK cũ đứng trước JDK mới, lệnh trên có thể để lại các đường dẫn cũ phía sau. Vì đường dẫn mới được đặt ở đầu, nó sẽ được ưu tiên trong phiên hiện tại.

Để cấu hình lâu dài, có thể mở phần **Environment Variables** của Windows:

1. Tạo hoặc cập nhật biến người dùng `JAVA_HOME` trỏ đến thư mục gốc của JDK mong muốn.
2. Trong biến `Path`, thêm `%JAVA_HOME%\bin`.
3. Đưa mục này lên trước các mục JDK cũ hoặc loại bỏ các mục cũ nếu không còn cần thiết.
4. Mở terminal mới rồi kiểm tra lại `java --version`, `javac --version` và `Get-Command java -All`.

Không đặt `JAVA_HOME` thành `C:\Dev\Java\jdk-21\bin`. Cần trỏ tới `C:\Dev\Java\jdk-21`.

### 4.3. Chuyển JDK trong Linux

Trong một phiên shell, có thể đặt biến như sau:

```bash
export JAVA_HOME=/opt/jdks/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

Các lệnh `export` chỉ tác động đến shell hiện tại và tiến trình con. Muốn áp dụng cho các phiên đăng nhập mới, có thể thêm cấu hình phù hợp vào `~/.bashrc`, `~/.zshrc` hoặc file cấu hình shell đang dùng.

Trên các bản phân phối Debian/Ubuntu, `update-alternatives` có thể quản lý lựa chọn mặc định của các lệnh Java:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
```

Cần chọn cả `java` và `javac` sao cho cùng một phiên bản. `update-alternatives` quản lý đường dẫn lệnh; nó không bảo đảm `JAVA_HOME` được cập nhật tương ứng. Hãy kiểm tra và đặt `JAVA_HOME` riêng nếu công cụ build cần biến này.

Tên lệnh và cấu hình có thể khác trên các bản phân phối Linux khác. Trên môi trường container hoặc máy chủ do tổ chức quản lý, cần tuân theo cách cài đặt và quản lý phần mềm của môi trường đó.

### 4.4. Chuyển JDK trong macOS

macOS cung cấp công cụ `/usr/libexec/java_home` để tìm các JDK đã cài.

Liệt kê các JDK:

```bash
/usr/libexec/java_home -V
```

Chọn JDK 21 cho phiên shell hiện tại:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

Để tự động chọn JDK 21 khi mở shell, có thể thêm hai dòng `export` vào `~/.zshrc` nếu đang dùng zsh, hoặc file cấu hình tương ứng của shell. Muốn chuyển sang bản khác, thay `-v 21` bằng feature release cần dùng.

## 5. Dùng trình quản lý phiên bản JDK

Khi thường xuyên chuyển qua lại giữa nhiều dự án, việc sửa `JAVA_HOME` và `PATH` bằng tay dễ gây nhầm lẫn. Trình quản lý phiên bản giúp cài đặt và chọn JDK theo lệnh, đôi khi còn cho phép cố định phiên bản theo thư mục dự án.

Một số lựa chọn phổ biến:

| Công cụ | Nền tảng thường dùng | Cách quản lý |
|---|---|---|
| SDKMAN! | Linux, macOS và môi trường Unix tương thích | Cài nhiều bản Java, chuyển phiên bản theo shell hoặc đặt mặc định |
| jenv | macOS và Linux | Chọn JDK theo global, thư mục hoặc shell |
| mise | macOS, Linux và Windows | Quản lý nhiều runtime/tool, chọn phiên bản toàn cục hoặc theo dự án |
| asdf | macOS và Linux; nền tảng khác tùy môi trường | Plugin quản lý Java và phiên bản theo thư mục |
| Công cụ của IDE | Tùy IDE | Chọn JDK cho project, module và build runner |

Không cần cài tất cả các công cụ. Hãy chọn một cách quản lý phù hợp hệ điều hành, chính sách công ty và thói quen làm việc của nhóm.

### 5.1. SDKMAN!

SDKMAN! thường được dùng trên Linux và macOS. Sau khi cài SDKMAN! theo hướng dẫn chính thức, có thể liệt kê các bản Java có sẵn:

```bash
sdk list java
```

Cài một candidate cụ thể được hiển thị trong danh sách:

```bash
sdk install java <candidate>
```

Chuyển sang phiên bản đã cài trong shell hiện tại:

```bash
sdk use java <candidate>
```

Đặt phiên bản mặc định cho các shell mới:

```bash
sdk default java <candidate>
```

`<candidate>` là mã phiên bản đầy đủ do SDKMAN! liệt kê, thường bao gồm feature release, update và nhà cung cấp. Hãy sao chép mã đúng từ danh sách tại thời điểm cài đặt thay vì đoán chuỗi phiên bản.

### 5.2. jenv

jenv quản lý lựa chọn Java bằng cách điều chỉnh đường dẫn lệnh trong shell. Sau khi cài jenv và đăng ký các JDK đã có, có thể sử dụng các lệnh:

```bash
jenv versions
jenv add /path/to/jdk
jenv global 21
jenv local 17
jenv shell 21
```

Ý nghĩa:

- `jenv versions`: liệt kê các phiên bản jenv biết.
- `jenv add`: đăng ký một JDK đã cài.
- `jenv global`: đặt lựa chọn mặc định cho người dùng.
- `jenv local`: đặt lựa chọn cho thư mục dự án thông qua file cấu hình của jenv.
- `jenv shell`: đặt lựa chọn tạm thời cho shell hiện tại.

Tên phiên bản được jenv nhận diện có thể chứa cả thông tin nhà cung cấp hoặc bản cập nhật. Dùng đúng tên trong kết quả `jenv versions`.

Nếu cần jenv quản lý cả `JAVA_HOME`, hãy bật plugin `export` theo hướng dẫn của phiên bản jenv đang cài. Nếu chưa bật, `java` có thể đổi theo jenv trong khi một số công cụ đọc `JAVA_HOME` vẫn thấy giá trị cũ.

### 5.3. mise

mise có thể quản lý nhiều công cụ phát triển, bao gồm Java. Sau khi cài mise và bật nó trong shell, có thể đặt một phiên bản Java cho dự án:

```bash
mise use java@21
```

Lệnh này ghi cấu hình phiên bản vào thư mục dự án. Để đặt phiên bản toàn cục:

```bash
mise use --global java@21
```

Kiểm tra cấu hình và phiên bản đang được chọn:

```bash
mise current
java --version
javac --version
```

Cách cài đặt JDK, khả năng tự tải phiên bản và cấu hình nguồn phân phối phụ thuộc vào cấu hình mise và plugin backend Java. Kiểm tra trạng thái cài đặt nếu lệnh yêu cầu tải hoặc chọn một bản JDK chưa có.

### 5.4. Chọn công cụ nào?

- Chỉ có một JDK và ít khi đổi phiên bản: đặt `JAVA_HOME` và PATH là đủ.
- Phát triển nhiều dự án trên macOS/Linux: SDKMAN! hoặc jenv là lựa chọn quen thuộc.
- Muốn một công cụ quản lý nhiều runtime và pin phiên bản theo dự án: cân nhắc mise hoặc asdf.
- Làm việc trên Windows: có thể dùng cấu hình môi trường của Windows, mise hoặc các công cụ quản lý phiên bản phù hợp. SDKMAN! thường được sử dụng trong WSL hơn là PowerShell thuần.
- Làm việc trong nhóm: ưu tiên một cách pin phiên bản rõ ràng và được ghi vào tài liệu dự án để mọi thành viên dùng nhất quán.

## 6. Cố định phiên bản JDK theo dự án

Một máy có thể có JDK mặc định, nhưng mỗi dự án nên khai báo rõ phiên bản cần dùng. Như vậy, mở dự án cũ sẽ không vô tình dùng JDK mới chỉ vì đó là phiên bản mặc định trên máy.

Có ba lớp cấu hình thường cần xem xét:

1. JDK chạy các công cụ build (Maven hoặc Gradle).
2. JDK compiler dùng để biên dịch mã nguồn.
3. Phiên bản Java mục tiêu mà ứng dụng hỗ trợ khi chạy.

Ba giá trị này có liên quan nhưng không nhất thiết giống nhau.

### 6.1. Dùng --release khi biên dịch trực tiếp

Nếu đã cài một JDK mới hơn nhưng muốn biên dịch ứng dụng tương thích Java 17:

```bash
javac --release 17 -d out src/com/example/Hello.java
```

`--release 17` yêu cầu compiler dùng bộ quy tắc ngôn ngữ, bytecode và API công khai tương ứng Java 17. Nó hữu ích khi build trên JDK mới hơn cho runtime cũ hơn.

Tùy chọn này không thay thế việc chọn JDK chạy ứng dụng. Nó cũng không biến một JDK quá cũ thành compiler của phiên bản mới. Nếu mã nguồn cần cú pháp chỉ có trong Java 21, compiler Java 17 không thể biên dịch mã đó.

### 6.2. Cấu hình Maven

Với Maven, có thể khai báo phiên bản Java mục tiêu trong `pom.xml` bằng thuộc tính `maven.compiler.release`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Cấu hình này yêu cầu Maven Compiler Plugin sử dụng release 17 khi biên dịch. Phiên bản plugin phải hỗ trợ cấu hình `release` tương ứng.

Maven còn có **Toolchains** để chọn một JDK cài trên máy dành riêng cho các plugin build. File `~/.m2/toolchains.xml` có thể khai báo các JDK đã cài:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:\Dev\Java\jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

Đây là ví dụ minh họa: giá trị `vendor` và `jdkHome` phải khớp JDK thực tế đã cài và cách plugin yêu cầu toolchain. Trên Linux/macOS, thay `jdkHome` bằng đường dẫn thực tế của JDK.

Toolchains giúp Maven chọn compiler JDK cho các plugin hỗ trợ toolchain. Tuy nhiên, Maven launcher và JVM chạy Maven vẫn có thể là một JDK khác. Kiểm tra phiên bản JVM của Maven bằng:

```bash
mvn -version
```

### 6.3. Cấu hình Gradle Java Toolchains

Gradle hỗ trợ khai báo toolchain trong `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Cấu hình này yêu cầu Gradle dùng JDK có Java language version 17 cho các tác vụ Java tương ứng, ví dụ biên dịch và kiểm thử. Có thể bổ sung yêu cầu vendor khi đội cần thống nhất nhà cung cấp.

Kiểm tra môi trường Gradle:

```bash
./gradlew --version
```

Trên Windows, dùng `gradlew.bat --version`.

Cần phân biệt JDK chạy Gradle daemon với JDK toolchain dùng cho tác vụ của dự án. Chúng có thể khác nhau. Phiên bản Gradle phải hỗ trợ JDK dùng để chạy chính Gradle; hãy kiểm tra ma trận tương thích của Gradle khi nâng JDK cho build runner.

## 7. Cấu hình JDK trong IDE

IDE có thể giữ cấu hình JDK riêng, vì vậy terminal chạy đúng Java chưa bảo đảm nút Build hoặc Run trong IDE cũng dùng cùng phiên bản.

### 7.1. IntelliJ IDEA

Các vị trí thường cần kiểm tra:

- **Project SDK:** JDK chính của project.
- **Project language level:** mức cú pháp Java mà project cho phép.
- **Module SDK:** JDK riêng của module nếu project có nhiều module.
- **Gradle JVM:** JDK chạy Gradle daemon.
- **Maven Runner JRE:** JDK chạy Maven trong IDE.

Khi thay đổi JDK, kiểm tra cả Project SDK lẫn Gradle JVM hoặc Maven Runner nếu dự án dùng hệ thống build tương ứng.

### 7.2. Eclipse

Trong Eclipse, có thể đăng ký các JDK tại phần **Installed JREs**. Sau đó chọn JDK cho project trong phần **Java Build Path** hoặc chọn execution environment phù hợp.

Mức compiler compliance của project cần tương thích với phiên bản Java mục tiêu. Một project có thể dùng JDK mới hơn để chạy IDE nhưng vẫn đặt mức biên dịch thấp hơn nếu cấu hình phù hợp.

### 7.3. Visual Studio Code

Với Extension Pack for Java, có thể khai báo các runtime trong `settings.json`:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "C:\\Dev\\Java\\jdk-17"
    },
    {
      "name": "JavaSE-21",
      "path": "C:\\Dev\\Java\\jdk-21",
      "default": true
    }
  ]
}
```

Đường dẫn cần trỏ tới thư mục gốc của JDK. Tùy chọn `default` xác định runtime mặc định mà extension sử dụng trong những trường hợp thích hợp. Với dự án Maven hoặc Gradle, vẫn cần kiểm tra cấu hình build của chính dự án.

## 8. Quản lý JDK trong CI và môi trường triển khai

Máy lập trình viên chỉ là một phần của môi trường build. CI, máy build, container và production cũng cần dùng phiên bản Java phù hợp.

Các nguyên tắc quan trọng:

- Khai báo rõ feature release, nhà cung cấp và bản cập nhật khi dự án yêu cầu khả năng tái lập chặt chẽ.
- Dùng cấu hình CI cố định phiên bản JDK, tránh chọn một alias thay đổi theo thời gian nếu không chủ động cập nhật.
- Kiểm tra cả JDK chạy build và compiler toolchain của dự án.
- Chạy test trên phiên bản runtime mà production sẽ sử dụng.
- Nếu hỗ trợ nhiều phiên bản Java, dùng ma trận build để kiểm tra từng phiên bản mục tiêu.
- Với Docker, chọn image có tag phiên bản cụ thể; khi yêu cầu tính tái lập cao, cân nhắc cố định cả digest của image.
- Cập nhật các bản vá bảo mật theo lịch bảo trì và kiểm tra lại tương thích sau khi nâng cấp.

Một build thành công trên máy cá nhân chưa đủ chứng minh ứng dụng sẽ chạy đúng trên production. CI cần kiểm tra đúng JDK và runtime mục tiêu, còn môi trường triển khai cần cung cấp runtime tương thích với bytecode và API mà ứng dụng sử dụng.

## 9. Lỗi thường gặp khi chuyển phiên bản JDK

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `java --version` không đổi sau khi sửa `JAVA_HOME` | PATH vẫn ưu tiên JDK cũ | Kiểm tra thứ tự PATH và mở terminal mới |
| `java` và `javac` khác phiên bản | Hai lệnh được tìm từ hai thư mục JDK khác nhau | Kiểm tra `Get-Command -All`, `where.exe`, `type -a`; đồng bộ đường dẫn |
| Terminal dùng đúng JDK nhưng IDE dùng bản khác | IDE lưu Project SDK hoặc build JVM riêng | Kiểm tra Project SDK, module SDK và runner JVM |
| Maven chạy bằng JDK không mong muốn | `JAVA_HOME`, PATH hoặc cấu hình IDE trỏ tới JDK khác | Dùng `mvn -version`, kiểm tra Maven Runner và toolchains |
| Gradle không khởi động sau khi nâng JDK | Phiên bản Gradle hiện tại không hỗ trợ JDK đang chạy Gradle | Kiểm tra ma trận tương thích, nâng Gradle Wrapper khi phù hợp |
| `UnsupportedClassVersionError` | Runtime thấp hơn phiên bản bytecode của ứng dụng hoặc dependency | Chọn runtime tương thích hoặc build với release mục tiêu thấp hơn |
| Plugin hoặc thư viện không tương thích | Plugin, annotation processor hoặc dependency chưa hỗ trợ JDK mới | Kiểm tra release notes và nâng phiên bản thành phần liên quan |
| `JAVA_HOME` hợp lệ nhưng công cụ báo không tìm thấy Java | Biến trỏ sai thư mục, trỏ vào `bin`, hoặc đường dẫn không tồn tại | Kiểm tra thư mục có `bin/java` hoặc `bin/javac` tương ứng |

Một số thao tác kiểm tra nhanh sau khi chuyển phiên bản:

```bash
java --version
javac --version
mvn -version
./gradlew --version
```

Không phải dự án nào cũng dùng cả Maven lẫn Gradle. Chạy lệnh tương ứng với hệ thống build của dự án và kiểm tra JDK được báo trong kết quả.

## 10. Quy trình chuẩn khi đổi JDK cho một dự án

Khi cần nâng hoặc chuyển JDK, thực hiện theo trình tự:

1. **Xác định yêu cầu:** đọc cấu hình dự án, framework, dependency, plugin build và phiên bản runtime của môi trường triển khai.
2. **Cài JDK:** cài đúng feature release và nhà cung cấp được chọn; ghi lại đường dẫn cài đặt.
3. **Chọn JDK cho dự án:** cập nhật toolchain, file pin phiên bản hoặc cấu hình IDE phù hợp.
4. **Kiểm tra công cụ build:** xác minh JDK chạy Maven/Gradle và JDK compiler toolchain.
5. **Biên dịch và kiểm thử:** chạy build sạch, unit test và integration test trên phiên bản mục tiêu.
6. **Kiểm tra runtime:** chạy ứng dụng với JDK hoặc runtime image dự kiến triển khai.
7. **Cập nhật CI và tài liệu:** đồng bộ cấu hình pipeline, Docker image và hướng dẫn cho thành viên nhóm.
8. **Theo dõi sau nâng cấp:** kiểm tra log, cảnh báo, hiệu năng và các lỗi tương thích khi triển khai.

Không nên xóa ngay JDK cũ khi vẫn còn dự án hoặc công cụ phụ thuộc vào nó. Sau khi các dự án đã chuyển đổi, có thể gỡ những bản không còn cần thiết theo chính sách quản lý phần mềm của máy hoặc tổ chức.

## 11. Tổng kết

Quản lý version JDK giúp mỗi dự án sử dụng đúng bộ công cụ Java trong suốt quá trình phát triển và triển khai. Những điểm cần nhớ:

- Có thể cài nhiều JDK song song; mỗi bản nên nằm trong thư mục riêng.
- `JAVA_HOME` chỉ ra JDK cho các công cụ đọc biến này, còn `PATH` quyết định lệnh `java` và `javac` nào được tìm thấy trước.
- Kiểm tra phiên bản bằng `java --version`, `javac --version` và kiểm tra đường dẫn thực tế.
- SDKMAN!, jenv, mise hoặc asdf giúp chuyển đổi phiên bản thuận tiện; chọn một công cụ phù hợp thay vì dùng nhiều cơ chế chồng chéo.
- Maven Toolchains, Gradle Java Toolchains và cấu hình IDE giúp cố định JDK theo dự án.
- Phải kiểm tra riêng JDK chạy build, JDK compiler và phiên bản Java mục tiêu.
- CI và production cần được cấu hình nhất quán với phiên bản mà dự án yêu cầu.

Khi quản lý JDK có chủ đích, bạn có thể duy trì nhiều dự án Java trên cùng máy, nâng cấp từng dự án có kiểm soát và giảm lỗi do môi trường phát triển không đồng nhất.
