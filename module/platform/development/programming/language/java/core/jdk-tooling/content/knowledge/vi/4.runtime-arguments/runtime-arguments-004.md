# Environment variables trong Java runtime

Environment variables (biến môi trường) là các cặp tên–giá trị mà hệ điều hành cung cấp cho một tiến trình. Khi chạy ứng dụng Java, môi trường này có thể ảnh hưởng đến việc tìm JDK, chọn Java executable, xác định classpath mặc định, truyền tùy chọn cho JVM hoặc cấu hình công cụ build. Một số biến được Java launcher/JVM nhận biết trực tiếp; một số khác chỉ có ý nghĩa với shell, IDE, Maven, Gradle hoặc chính ứng dụng.

Điều quan trọng là phân biệt **environment variable**, **JVM option** và **Java system property**:

- Environment variable thuộc môi trường của tiến trình, ví dụ `JAVA_HOME` hoặc `APP_ENV`.
- JVM option là tham số truyền khi khởi chạy JVM, ví dụ `-Xmx1g`, `-ea` hoặc `-Dapp.mode=prod`.
- System property là giá trị JVM lưu trong hệ thống thuộc tính, có thể đọc bằng `System.getProperty("app.mode")`.
- Ứng dụng Java đọc environment variable bằng `System.getenv("APP_ENV")`.

Một biến môi trường chỉ tác động đến Java khi launcher, JVM, thư viện, công cụ bên ngoài hoặc chính ứng dụng có quy định đọc biến đó. Không phải mọi biến môi trường đều tự động trở thành system property.

## 1. Môi trường của tiến trình hoạt động như thế nào?

Khi người dùng mở terminal, shell có một môi trường gồm nhiều biến. Khi shell khởi chạy `java`, tiến trình Java thường nhận một bản môi trường được kế thừa từ tiến trình cha. Các tiến trình con do Java tạo ra cũng thường kế thừa môi trường của tiến trình Java, trừ khi ứng dụng chủ động thay đổi môi trường khi tạo tiến trình.

Ví dụ, nếu terminal có:

~~~text
APP_ENV=staging
~~~

thì một chương trình Java được khởi chạy từ terminal đó có thể đọc `APP_ENV` bằng `System.getenv("APP_ENV")`.

Các điểm cần nhớ:

- Thay đổi biến môi trường trong một terminal thường chỉ ảnh hưởng terminal đó và các tiến trình con được tạo sau thay đổi.
- Thay đổi môi trường trong terminal hiện tại không tự cập nhật môi trường của một IDE đã mở trước đó.
- Mỗi tiến trình có môi trường riêng; một tiến trình Java không thể thay đổi môi trường của tiến trình cha đang chạy nó.
- Biến môi trường được kế thừa tại thời điểm tạo tiến trình. Nếu sửa biến trong shell sau khi Java đã chạy, tiến trình Java hiện tại không tự nhận giá trị mới.
- Tên biến môi trường phân biệt chữ hoa/chữ thường trên Unix-like systems; trên Windows, tên biến thường không phân biệt hoa/thường. Dùng tên viết hoa nhất quán giúp cấu hình dễ đọc.

Mô hình này giải thích vì sao một lệnh chạy được trong terminal này nhưng thất bại trong terminal khác, IDE, dịch vụ hệ thống hoặc container: các tiến trình đó có thể nhận những môi trường khác nhau.

## 2. Các biến môi trường quan trọng khi phát triển Java

### 2.1. `JAVA_HOME`

`JAVA_HOME` thường được dùng để chỉ thư mục gốc của JDK mà dự án hoặc công cụ build nên sử dụng. Đây là quy ước phổ biến trong hệ sinh thái Java và nhiều công cụ bên ngoài đọc biến này.

Ví dụ đường dẫn:

~~~text
Windows:  C:\Program Files\Java\jdk-17
macOS:    /Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
Linux:    /usr/lib/jvm/jdk-17
~~~

Các đường dẫn chỉ là ví dụ; thư mục thật phụ thuộc nhà cung cấp, cách cài đặt và hệ điều hành.

`JAVA_HOME` nên trỏ đến thư mục gốc JDK, nơi có các thư mục như `bin`, `lib` và các thành phần khác. Không đặt nó trỏ trực tiếp đến `bin`.

`JAVA_HOME` thường được công cụ build như Maven, Gradle wrapper hoặc script dự án dùng để tìm JDK. Bản thân Java launcher không cần `JAVA_HOME` nếu shell đã tìm đúng executable `java` thông qua PATH. Vì vậy, việc đặt `JAVA_HOME` đúng không tự bảo đảm lệnh `java` và `javac` đang được chọn từ cùng một JDK.

### 2.2. `PATH`

`PATH` là danh sách thư mục mà shell hoặc hệ điều hành tìm kiếm khi người dùng chạy lệnh mà không ghi đường dẫn đầy đủ. Đưa thư mục `bin` của JDK vào PATH giúp gọi `java`, `javac`, `jar`, `javadoc` và các công cụ khác từ bất kỳ thư mục làm việc nào.

Ví dụ, nếu `JAVA_HOME` trỏ đến JDK thì thư mục cần thêm thường là:

~~~text
Windows:  %JAVA_HOME%\bin
macOS/Linux: $JAVA_HOME/bin
~~~

Khi có nhiều bản Java, thứ tự thư mục trong PATH quyết định executable nào được tìm thấy trước. Vì thế, `java --version` và `javac --version` có thể phản ánh một JDK khác với `JAVA_HOME`.

Kiểm tra trên Windows:

~~~powershell
where.exe java
where.exe javac
Get-Command java
~~~

Kiểm tra trên macOS/Linux:

~~~sh
command -v java
command -v javac
which -a java
which -a javac
~~~

Nếu có nhiều đường dẫn kết quả, kiểm tra thứ tự PATH và cấu hình của IDE/build tool. Tránh giả định rằng bản Java hiển thị đầu tiên là bản mà mọi công cụ trên máy đều sử dụng.

### 2.3. `CLASSPATH`

`CLASSPATH` có thể cung cấp classpath mặc định cho Java launcher khi lệnh chạy lớp thông thường không chỉ định `-cp`, `-classpath` hoặc `--class-path`.

Classpath xác định các thư mục và JAR mà JVM dùng để tìm lớp và tài nguyên. Ví dụ:

~~~text
Windows:  .;lib/app.jar;lib/*
macOS/Linux: .:lib/app.jar:lib/*
~~~

Ký tự phân cách các mục phụ thuộc hệ điều hành:

- Windows dùng dấu chấm phẩy `;`.
- macOS/Linux dùng dấu hai chấm `:`.

Dấu chấm `.` đại diện cho thư mục làm việc hiện tại. Mẫu `lib/*` đưa các JAR trong thư mục `lib` vào classpath.

Trong dự án có build tool, nên để Maven/Gradle hoặc script chạy cung cấp classpath cần thiết thay vì dựa vào CLASSPATH toàn cục. Một CLASSPATH được đặt từ trước có thể khiến ứng dụng tìm thấy phiên bản thư viện không mong muốn.

Lệnh `java -cp ...` hoặc `--class-path ...` chỉ định classpath tường minh cho lần chạy đó và thay thế giá trị mặc định từ biến CLASSPATH. Khi dùng `java -jar app.jar`, classpath mặc định từ CLASSPATH không được dùng để bổ sung dependency như chế độ chạy lớp thông thường; hãy cấu hình dependency theo cách đóng gói JAR hoặc cách khởi chạy phù hợp.

## 3. Biến môi trường truyền tùy chọn cho JVM

### 3.1. `JDK_JAVA_OPTIONS`

`JDK_JAVA_OPTIONS` được Java launcher hỗ trợ từ JDK 9. Nội dung của biến này được launcher thêm vào trước các tùy chọn và đối số trên dòng lệnh khi khởi chạy Java.

Ví dụ:

~~~text
JDK_JAVA_OPTIONS=-Dapp.mode=staging -Xmx512m
~~~

Khi chạy:

~~~text
java -cp out Main
~~~

JVM nhận system property `app.mode=staging` và heap tối đa 512 MB. Ứng dụng có thể đọc property bằng `System.getProperty("app.mode")`.

Biến này hữu ích khi muốn áp dụng một nhóm tùy chọn cho nhiều lệnh `java` trong cùng môi trường, ví dụ cấu hình logging hoặc một system property chung. Tuy nhiên, vì launcher tự động thêm các tùy chọn này, người vận hành có thể không nhận ra vì sao ứng dụng có cấu hình khác với lệnh hiển thị trong script.

Một số lưu ý:

- Nội dung được phân tích thành các đối số theo quy tắc của launcher; đường dẫn có dấu cách cần được quote đúng.
- Tùy chọn trong biến được thêm trước tùy chọn trên dòng lệnh. Với các tùy chọn lặp lại, cách xử lý giá trị cuối cùng phụ thuộc quy tắc của tùy chọn đó; không giả định mọi cờ đều có cùng quy tắc ghi đè.
- Java launcher có thể in thông báo cho biết `JDK_JAVA_OPTIONS` đang được sử dụng.
- Biến này áp dụng cho các lần chạy Java launcher được tạo trong môi trường kế thừa biến đó. Nếu ứng dụng khởi chạy tiến trình Java con, tiến trình con có thể tiếp tục nhận biến này.

Khi một lệnh có hành vi bất ngờ, hãy kiểm tra `JDK_JAVA_OPTIONS` trước khi kết luận script đang thiếu tùy chọn.

### 3.2. `JAVA_TOOL_OPTIONS`

`JAVA_TOOL_OPTIONS` được JVM xem xét khi một máy ảo được tạo. Nó cho phép bổ sung các tùy chọn JVM ngay cả trong tình huống JVM được khởi tạo bởi một ứng dụng hoặc môi trường nhúng, nơi người dùng không trực tiếp điều khiển dòng lệnh Java launcher.

Ví dụ:

~~~text
JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8 -Xmx512m
~~~

Một trường hợp thường gặp là cấu hình Java agent:

~~~text
JAVA_TOOL_OPTIONS=-javaagent:/opt/agents/monitoring-agent.jar
~~~

Java agent có thể dùng để giám sát, instrument hoặc hỗ trợ chẩn đoán ứng dụng. Chỉ bật agent khi đã tin cậy nguồn cung cấp và hiểu tác động của nó.

Lưu ý:

- JVM thường in thông báo `Picked up JAVA_TOOL_OPTIONS` khi biến được áp dụng.
- Biến này có thể tác động đến nhiều tiến trình Java trong cùng môi trường, kể cả công cụ build, ứng dụng con hoặc JVM được nhúng.
- Một số tùy chọn bị giới hạn trong ngữ cảnh này; không phải mọi cờ của launcher đều có thể đặt ở đây.
- Trên một số hệ thống, JVM có thể bỏ qua biến này khi tiến trình chạy với danh tính người dùng/nhóm hiệu lực khác danh tính thực nhằm hạn chế rủi ro bảo mật.
- Nếu agent hoặc tùy chọn được thêm ngoài ý muốn, ứng dụng có thể khởi động chậm, dùng thêm bộ nhớ hoặc thay đổi hành vi.

Không nên đặt `JAVA_TOOL_OPTIONS` toàn cục cho toàn bộ máy nếu chỉ một ứng dụng cần cấu hình đó. Nên giới hạn phạm vi ở script, service hoặc container tương ứng.

### 3.3. Phân biệt `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS`

Hai biến đều có thể bổ sung tùy chọn cho JVM, nhưng được áp dụng ở những tầng khác nhau:

| Biến | Thành phần đọc | Thời điểm áp dụng | Phạm vi thường gặp |
|---|---|---|---|
| `JDK_JAVA_OPTIONS` | Java launcher | Khi launcher xử lý dòng lệnh, trước các tùy chọn được truyền trực tiếp | Các tiến trình được chạy qua Java launcher và kế thừa biến |
| `JAVA_TOOL_OPTIONS` | JVM khi tạo VM | Trong quá trình khởi tạo JVM | Cả trường hợp JVM được tạo bởi launcher hoặc môi trường nhúng phù hợp |

Khi cần tùy chỉnh lệnh `java` trong một script chạy ứng dụng, `JDK_JAVA_OPTIONS` thường dễ hiểu vì thuộc tầng launcher. Khi cần cung cấp tùy chọn cho một JVM được khởi tạo từ ứng dụng khác, `JAVA_TOOL_OPTIONS` có thể phù hợp hơn.

Không nên đặt cùng một tùy chọn ở cả hai biến nếu chưa hiểu cách launcher/JVM xử lý các giá trị trùng lặp. Việc lặp lại `-D`, `-Xmx` hoặc `-javaagent` có thể gây nhầm lẫn hoặc thay đổi kết quả theo thứ tự xử lý.

### 3.4. `_JAVA_OPTIONS`

`_JAVA_OPTIONS` xuất hiện trong một số triển khai JVM, đặc biệt các bản dựa trên HotSpot, như một cơ chế bổ sung tùy chọn. Đây không phải giao diện môi trường Java chuẩn, portable được đặc tả giống `JDK_JAVA_OPTIONS` hoặc `JAVA_TOOL_OPTIONS`.

Có thể bắt gặp thông báo `Picked up _JAVA_OPTIONS` trong terminal. Nếu thấy thông báo này mà không hiểu nguồn gốc, hãy kiểm tra biến môi trường và cấu hình hệ thống.

Không nên xây dựng quy trình triển khai phụ thuộc vào `_JAVA_OPTIONS` vì tính di động và hành vi của nó phụ thuộc triển khai. Ưu tiên dùng tùy chọn tường minh trong lệnh chạy hoặc biến được tài liệu JDK hiện tại hỗ trợ.

## 4. Biến dành riêng cho công cụ build

Không phải biến nào có chữ `JAVA` cũng được Java launcher hoặc JVM xử lý trực tiếp. Một số biến được các công cụ khác đọc:

| Biến | Công cụ thường sử dụng | Mục đích |
|---|---|---|
| `MAVEN_OPTS` | Maven | Tùy chọn JVM cho tiến trình Maven |
| `JAVA_HOME` | Maven, Gradle, IDE và script | Chọn cài đặt JDK |
| `GRADLE_OPTS` | Gradle launcher | Tùy chọn JVM cho tiến trình Gradle client |
| `JAVA_OPTS` | Nhiều script hoặc ứng dụng | Tên quy ước, ý nghĩa tùy script |
| `JDK_JAVA_OPTIONS` | Java launcher | Bổ sung tùy chọn cho lệnh Java |
| `JAVA_TOOL_OPTIONS` | JVM | Bổ sung tùy chọn khi tạo VM |

Đừng nhầm `JAVA_OPTS` với một biến chuẩn được JVM tự động đọc. Một script có thể mở rộng `$JAVA_OPTS` khi gọi `java`, nhưng một lệnh `java` độc lập không có nghĩa vụ phải đọc biến này.

Với Gradle, cấu hình JVM của Gradle daemon còn có thể đến từ `org.gradle.jvmargs` trong `gradle.properties`. Với IDE, JDK dùng để chạy IDE, JDK dùng để build và JDK dùng để chạy ứng dụng có thể là ba cấu hình khác nhau.

Khi thay đổi phiên bản JDK, hãy kiểm tra cả terminal, IDE, Maven/Gradle wrapper, CI và cấu hình runtime của ứng dụng.

## 5. Đặt biến môi trường trên Windows

### 5.1. Chỉ đặt cho phiên PowerShell hiện tại

Trong PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$env:APP_ENV = 'staging'
$env:JDK_JAVA_OPTIONS = '-Dapp.mode=debug -Xmx512m'
~~~

Sau đó kiểm tra:

~~~powershell
java --version
javac --version
$env:JAVA_HOME
$env:APP_ENV
$env:JDK_JAVA_OPTIONS
where.exe java
where.exe javac
~~~

Các thay đổi qua `$env:` chỉ áp dụng cho tiến trình PowerShell hiện tại và các tiến trình con được khởi chạy từ đó. Đóng terminal sẽ kết thúc phạm vi thay đổi tạm này.

Xóa một biến khỏi môi trường PowerShell hiện tại:

~~~powershell
Remove-Item Env:JDK_JAVA_OPTIONS
~~~

### 5.2. Đặt biến bền vững cho tài khoản người dùng

Có thể đặt biến ở phạm vi User bằng PowerShell:

~~~powershell
[Environment]::SetEnvironmentVariable(
    'JAVA_HOME',
    'C:\Program Files\Java\jdk-17',
    'User'
)
~~~

Để thay đổi PATH bền vững, cần cẩn thận giữ nguyên các mục đang có. Có thể thao tác qua giao diện Environment Variables của Windows để thêm `%JAVA_HOME%\bin` vào PATH người dùng. Sau khi thay đổi, mở terminal hoặc IDE mới để tiến trình nhận môi trường cập nhật.

Không nên ghi đè toàn bộ PATH bằng một giá trị chỉ chứa thư mục JDK, vì có thể làm các lệnh khác không còn được tìm thấy. Khi máy có nhiều JDK, sắp xếp thứ tự PATH có chủ đích và kiểm tra lại `where.exe java` cùng `where.exe javac`.

## 6. Đặt biến môi trường trên macOS và Linux

Trong Bash hoặc Zsh, có thể đặt biến cho terminal hiện tại bằng `export`:

~~~sh
export JAVA_HOME=/path/to/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
export APP_ENV=staging
export JDK_JAVA_OPTIONS="-Dapp.mode=debug -Xmx512m"
~~~

Kiểm tra:

~~~sh
java --version
javac --version
printf '%s\n' "$JAVA_HOME" "$APP_ENV" "$JDK_JAVA_OPTIONS"
command -v java
command -v javac
~~~

Xóa biến trong shell hiện tại:

~~~sh
unset JDK_JAVA_OPTIONS
~~~

Trên macOS, có thể lấy đường dẫn JDK phù hợp từ tiện ích hệ thống:

~~~sh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Để thiết lập bền vững cho shell, thêm các lệnh export phù hợp vào file cấu hình được shell sử dụng, chẳng hạn `~/.zshrc` hoặc `~/.bashrc`. Tên file cần chỉnh phụ thuộc shell và cách terminal khởi tạo login/non-login shell.

Đối với dịch vụ hệ thống, không giả định service sẽ đọc file cấu hình shell của người dùng. Hãy đặt biến trong cấu hình service manager, container hoặc script khởi chạy dịch vụ.

## 7. Đọc environment variable và system property trong Java

Ứng dụng Java có hai API khác nhau để đọc hai loại cấu hình:

- `System.getenv("NAME")` đọc environment variable.
- `System.getProperty("name")` đọc JVM system property.

Tạo tệp `Main.java`:

~~~java
public class Main {
    public static void main(String[] args) {
        String env = System.getenv().getOrDefault("APP_ENV", "local");
        String mode = System.getProperty("app.mode", "default");

        System.out.println("APP_ENV=" + env);
        System.out.println("app.mode=" + mode);
    }
}
~~~

Biên dịch:

~~~text
javac Main.java
~~~

Chạy trên PowerShell:

~~~powershell
$env:APP_ENV = 'staging'
java -Dapp.mode=debug Main
~~~

Chạy trên macOS/Linux:

~~~sh
APP_ENV=staging java -Dapp.mode=debug Main
~~~

Kết quả stdout ở cả hai trường hợp:

~~~text
APP_ENV=staging
app.mode=debug
~~~

Trong ví dụ này:

- `APP_ENV` được shell đặt trong môi trường tiến trình và Java đọc bằng `System.getenv`.
- `app.mode` được truyền qua tùy chọn `-D` và Java đọc bằng `System.getProperty`.
- Giá trị mặc định `local` và `default` được dùng nếu hai cấu hình tương ứng không tồn tại.

Không dùng `System.getenv()` để đọc một system property và cũng không dùng `System.getProperty()` để đọc một biến môi trường. Tên và cách đặt giá trị của hai loại cấu hình này không tự động ánh xạ qua lại.

### Khi nào dùng biến môi trường, khi nào dùng system property?

| Tiêu chí | Environment variable | System property |
|---|---|---|
| Phạm vi | Môi trường của tiến trình và các tiến trình con được kế thừa | Một JVM cụ thể |
| Cách đọc trong Java | `System.getenv("APP_ENV")` | `System.getProperty("app.mode")` |
| Cách truyền | Shell, service manager, container hoặc hệ điều hành | `-Dapp.mode=value` hoặc mã Java |
| Thích hợp | Cấu hình triển khai, thông tin môi trường, vị trí công cụ | Cấu hình JVM/ứng dụng cho một lần chạy |
| Tính kế thừa | Thường được tiến trình con kế thừa | Không tự động truyền sang JVM con |

Không có quy tắc rằng một loại luôn tốt hơn loại kia. Hãy chọn theo phạm vi cần áp dụng và cách vận hành của ứng dụng.

## 8. Kiểm tra và chẩn đoán môi trường Java

Khi ứng dụng chạy sai phiên bản Java hoặc nhận cấu hình ngoài dự kiến, hãy kiểm tra theo thứ tự:

1. **Executable thực tế:** dùng `where.exe java`/`where.exe javac` trên Windows hoặc `command -v`/`which -a` trên macOS/Linux.
2. **Phiên bản runtime và compiler:** chạy `java --version` và `javac --version`.
3. **JAVA_HOME:** kiểm tra biến này có trỏ đến đúng thư mục gốc JDK không.
4. **PATH:** xác định JDK nào đứng trước trong thứ tự tìm kiếm.
5. **Các biến thêm tùy chọn:** kiểm tra `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS` và `_JAVA_OPTIONS` nếu có.
6. **Classpath mặc định:** kiểm tra `CLASSPATH` nếu lệnh không chỉ định `-cp`.
7. **Cấu hình công cụ:** kiểm tra JDK của IDE, Maven, Gradle, CI runner hoặc service.
8. **Môi trường tiến trình:** xác nhận terminal, service hoặc container thực sự nhận các biến mà bạn vừa đặt.

Để xem một số thuộc tính JVM:

~~~text
java -XshowSettings:properties -version
~~~

Lệnh này hiển thị các system properties và thông tin runtime hữu ích như `java.home`, `java.version`, `os.name`, `user.dir` và `file.encoding`. Nó không phải danh sách đầy đủ environment variables. Để xem biến môi trường trong ứng dụng, hãy dùng `System.getenv()` hoặc đọc từng biến cụ thể.

Có thể chạy một đoạn mã chẩn đoán nhỏ:

~~~java
public class EnvironmentCheck {
    public static void main(String[] args) {
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("user.dir=" + System.getProperty("user.dir"));
        System.out.println("JAVA_HOME=" + System.getenv("JAVA_HOME"));
        System.out.println("CLASSPATH=" + System.getenv("CLASSPATH"));
        System.out.println("JDK_JAVA_OPTIONS=" + System.getenv("JDK_JAVA_OPTIONS"));
        System.out.println("JAVA_TOOL_OPTIONS=" + System.getenv("JAVA_TOOL_OPTIONS"));
    }
}
~~~

Đây là ví dụ chẩn đoán; khi chia sẻ log, cần xem xét dữ liệu nhạy cảm có thể xuất hiện trong environment variables. Không in toàn bộ môi trường vào log production nếu chưa lọc giá trị.

## 9. Môi trường khác nhau giữa terminal, IDE, service và container

### Terminal và IDE

Một IDE thường được khởi chạy từ môi trường desktop hoặc shortcut, không nhất thiết kế thừa các biến bạn vừa đặt trong một terminal. IDE còn có thể lưu JDK riêng cho:

- Runtime của chính IDE.
- Project SDK hoặc Java toolchain dùng để biên dịch.
- JRE/JDK dùng để chạy cấu hình Run/Debug.
- Maven/Gradle importer hoặc daemon.

Nếu terminal chạy Java 17 nhưng IDE chạy Java 21, hãy kiểm tra từng cấu hình độc lập. Sau khi thay đổi biến môi trường cấp User/System, khởi động lại IDE để nó nhận môi trường mới.

### Dịch vụ hệ thống

Dịch vụ chạy dưới tài khoản riêng có thể có PATH, JAVA_HOME và quyền truy cập khác người dùng đăng nhập. Cấu hình service cần khai báo biến môi trường ở đúng service manager hoặc wrapper. Không dựa vào file `.bashrc`, `.zshrc` hoặc profile tương tác nếu service không chạy shell đó.

### CI/CD

Trong CI, nên khai báo JDK rõ ràng ở bước setup toolchain và kiểm tra phiên bản ngay trong job. Không giả định runner luôn có cùng JAVA_HOME hoặc PATH giữa các image/agent. Nếu có cache build, kiểm tra cache không trộn artifact tạo bởi các phiên bản JDK không tương thích.

### Container

Trong container, đặt JAVA_HOME và PATH trong image hoặc cấu hình runtime theo base image đã chọn. Nếu dùng biến như `JDK_JAVA_OPTIONS`, hãy xác định rõ container nào cần nhận nó và có ảnh hưởng đến tiến trình Java phụ trợ hay không. Biến môi trường khai báo trong container có thể được xem qua metadata/container inspection; không dùng environment variable làm kho bí mật nếu nền tảng có secret manager chuyên dụng.

## 10. Bảo mật và vận hành

Environment variables thuận tiện cho cấu hình, nhưng không phải kho bí mật tuyệt đối.

- Tránh đặt mật khẩu, token dài hạn hoặc private key trực tiếp trong biến môi trường nếu có giải pháp secret management phù hợp.
- Biến môi trường có thể bị lộ qua công cụ chẩn đoán, log, crash report, cấu hình CI hoặc quyền đọc tiến trình tùy hệ điều hành.
- `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS` có thể âm thầm thêm agent hoặc thay đổi heap, system property và hành vi JVM. Hãy kiểm soát nơi thiết lập hai biến này.
- Một Java agent có thể thực thi mã trong tiến trình ứng dụng. Chỉ sử dụng agent từ nguồn đáng tin và quản lý phiên bản của agent như dependency quan trọng.
- Tránh ghi toàn bộ môi trường vào log. Chỉ ghi tên và giá trị đã được cho phép, đồng thời che thông tin nhạy cảm.
- Khi chạy ứng dụng bằng service account, container hoặc CI runner, giới hạn quyền đọc/ghi và quyền truy cập secret theo nguyên tắc cần thiết tối thiểu.

Với môi trường production, hãy ghi lại các biến cấu hình cần thiết, giá trị mặc định an toàn và nguồn quản lý chúng. Thay đổi cấu hình phải có thể kiểm tra và tái hiện.

## 11. Lỗi thường gặp

### `JAVA_HOME` trỏ sai thư mục

**Biểu hiện:** Maven/Gradle hoặc script báo không tìm thấy Java, dù lệnh `java` có thể chạy.

**Nguyên nhân:** JAVA_HOME trỏ đến `bin`, đến JRE cũ hoặc một thư mục JDK không còn tồn tại.

**Cách xử lý:** đặt JAVA_HOME về thư mục gốc JDK, kiểm tra thư mục `bin` bên trong và chạy lại công cụ từ terminal mới.

### `java` và `javac` dùng hai JDK khác nhau

**Biểu hiện:** compiler báo một phiên bản, runtime hiển thị phiên bản khác; có thể gặp lỗi class version.

**Nguyên nhân:** PATH có nhiều JDK hoặc JAVA_HOME và PATH không đồng bộ.

**Cách xử lý:** xem tất cả đường dẫn bằng `where.exe` hoặc `which -a`, chỉnh thứ tự PATH và cấu hình IDE/build tool về đúng JDK.

### JVM tự nhận tùy chọn ngoài ý muốn

**Biểu hiện:** terminal in `Picked up ...`; ứng dụng có heap hoặc system property không giống script.

**Nguyên nhân:** `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS` hoặc `_JAVA_OPTIONS` được đặt ở môi trường người dùng, service hay container.

**Cách xử lý:** kiểm tra từng biến trong đúng tiến trình cha; xóa hoặc điều chỉnh biến ở nguồn cấu hình. Mở tiến trình mới sau khi thay đổi và xác nhận lại bằng lệnh chạy.

### `ClassNotFoundException` hoặc `NoClassDefFoundError`

**Biểu hiện:** ứng dụng không tìm được lớp hoặc dependency lúc chạy.

**Nguyên nhân:** CLASSPATH sai, thiếu JAR, thư mục làm việc khác dự kiến hoặc classpath bị biến môi trường ảnh hưởng.

**Cách xử lý:** kiểm tra `CLASSPATH`, dùng `-cp` tường minh và xác nhận đường dẫn đến package/JAR. Với executable JAR, kiểm tra manifest và cách đóng gói dependency.

### Terminal đúng nhưng IDE sai

**Biểu hiện:** cùng một lệnh hoặc project chạy được từ terminal nhưng thất bại trong IDE.

**Nguyên nhân:** IDE dùng môi trường hoặc JDK đã lưu riêng, hoặc chưa được khởi động lại sau khi cập nhật biến môi trường.

**Cách xử lý:** kiểm tra Project SDK, Run Configuration, Maven/Gradle JDK và khởi động lại IDE nếu cần.

### Biến thay đổi nhưng Java đang chạy không cập nhật

**Biểu hiện:** sửa biến trong terminal nhưng ứng dụng đang chạy vẫn dùng giá trị cũ.

**Nguyên nhân:** tiến trình đã nhận bản sao môi trường lúc được tạo.

**Cách xử lý:** khởi chạy lại tiến trình Java từ môi trường đã cập nhật. Thay đổi môi trường của shell không cập nhật ngược vào tiến trình con đang tồn tại.

## 12. Checklist cấu hình Java runtime

Trước khi chạy ứng dụng hoặc điều tra sự cố, kiểm tra:

- [ ] `JAVA_HOME` trỏ đến thư mục gốc của JDK mong muốn.
- [ ] PATH ưu tiên đúng thư mục `bin`.
- [ ] `java --version` và `javac --version` phản ánh phiên bản dự kiến.
- [ ] `CLASSPATH` không vô tình đưa dependency cũ vào ứng dụng.
- [ ] `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS` chỉ chứa tùy chọn được chủ đích áp dụng.
- [ ] Không phụ thuộc vào `_JAVA_OPTIONS` trong quy trình cần tính di động.
- [ ] Biến môi trường của IDE, service, CI và container được cấu hình đúng phạm vi.
- [ ] Cấu hình nhạy cảm được quản lý an toàn và không bị ghi vào log.
- [ ] Có thể tái hiện lệnh chạy và môi trường cần thiết ở máy khác.

Environment variables là một phần của cấu hình runtime vì chúng ảnh hưởng đến cách công cụ tìm JDK, cách launcher khởi chạy JVM và cách ứng dụng nhận cấu hình. Khi phân biệt rõ `JAVA_HOME`, `PATH`, `CLASSPATH`, `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS` và biến riêng của build tool, bạn sẽ kiểm soát môi trường Java tốt hơn và tìm nguyên nhân lỗi nhanh hơn.