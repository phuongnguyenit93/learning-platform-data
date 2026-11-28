# Chạy bằng java -jar và truyền đối số có khoảng trắng

Sau khi đóng gói Spring Shell thành executable JAR, người dùng có thể gọi command trực tiếp từ Bash, PowerShell, Windows Command Prompt hoặc một script tự động hóa. Khi tham số chứa dấu cách, cần truyền nó thành một đối số duy nhất qua từng lớp: terminal shell, Java launcher và bộ phân tích command của Spring Shell.

Ví dụ, tên khách hàng `Nguyễn Văn An` phải đến method command dưới dạng một giá trị duy nhất. Nếu dấu cách bị tách thành nhiều đối số, command có thể nhận sai dữ liệu hoặc báo thừa argument.

## 1. Tạo executable JAR

Spring Shell thường được đóng gói cùng Spring Boot. Executable JAR chứa ứng dụng và các dependency cần thiết; manifest chỉ ra entry point để `java -jar` khởi chạy.

Với Maven, cần có `spring-boot-maven-plugin` để thực hiện goal `repackage`. Nếu dự án dùng `spring-boot-starter-parent`, execution này đã được cấu hình sẵn khi plugin được khai báo:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu không dùng Spring Boot parent, hãy khai báo execution có goal `repackage` và đặt version plugin tương ứng với Spring Boot của dự án. Với Gradle, plugin Spring Boot cung cấp task `bootJar`. Một JAR thông thường không có manifest/loader phù hợp có thể không chạy được bằng `java -jar`.

Với Maven Wrapper:

~~~bash
./mvnw clean package
~~~

Với Gradle Wrapper:

~~~bash
./gradlew clean bootJar
~~~

Sau khi build, JAR thường nằm trong `target/` với Maven hoặc `build/libs/` với Gradle. Tên file phụ thuộc `artifactId`, `version` và cấu hình dự án.

Ví dụ:

~~~text
target/admin-cli-1.0.0.jar
~~~

Kiểm tra Java runtime trước khi chạy:

~~~text
java -version
~~~

Runtime phải đáp ứng phiên bản Java tối thiểu mà ứng dụng Spring Boot/Spring Shell được build yêu cầu.

## 2. Cấu trúc lệnh java -jar

Cú pháp tổng quát của Java launcher:

~~~text
java [JVM_OPTIONS] -jar JAR_FILE [APPLICATION_ARGUMENTS...]
~~~

Các phần có ý nghĩa khác nhau:

| Phần | Vai trò | Ví dụ |
|---|---|---|
| `java` | Khởi chạy JVM | `java` |
| `JVM_OPTIONS` | Cấu hình JVM trước khi ứng dụng chạy | `-Xmx512m`, `-Dfile.encoding=UTF-8` |
| `-jar` | Yêu cầu chạy ứng dụng từ JAR | `-jar` |
| `JAR_FILE` | Đường dẫn tới executable JAR | `target/admin-cli.jar` |
| `APPLICATION_ARGUMENTS` | Đối số được chuyển cho ứng dụng | `greet --name "Nguyễn Văn An"` |

Ví dụ:

~~~bash
java -Xmx512m -Dfile.encoding=UTF-8 -jar target/admin-cli-1.0.0.jar help
~~~

Các tùy chọn JVM phải đứng trước `-jar`. Những token sau tên JAR được chuyển vào ứng dụng qua `main(String[] args)`.

Nếu đường dẫn JAR có dấu cách, hãy đặt riêng đường dẫn đó trong dấu nháy:

~~~bash
java -jar "build/release files/admin-cli-1.0.0.jar" help
~~~

Đường dẫn JAR và giá trị của command là hai đối số khác nhau; mỗi đối số có thể cần được trích dẫn riêng.

## 3. Chạy command Spring Shell ở chế độ non-interactive

Spring Shell 3.3.x trở lên chỉ bật `NonInteractiveShellRunner` theo mặc định. Vì vậy, khi truyền command sau tên JAR, ứng dụng chạy command rồi kết thúc thay vì mở REPL.

Ví dụ:

~~~bash
java -jar target/admin-cli-1.0.0.jar help
java -jar target/admin-cli-1.0.0.jar version
java -jar target/admin-cli-1.0.0.jar greet --name Lan
~~~

Nếu muốn mở REPL tương tác khi chạy không truyền command, bật interactive runner:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
~~~

Thuộc tính này có thể đặt trong `application.yml` hoặc cấu hình môi trường triển khai. Không nhầm `spring.shell.interactive.enabled` với option nghiệp vụ của một command.

## 4. Tạo command minh họa có giá trị chứa khoảng trắng

Command sau nhận một option `--name` và trả lại đúng chuỗi đã nhận:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class GreetingCommands {

    @ShellMethod(key = "greet", value = "Chào một người")
    public String greet(
            @ShellOption(value = "--name") String name) {
        return "Xin chào, " + name;
    }
}
~~~

Trong REPL, có thể nhập:

~~~text
shell:>greet --name "Nguyễn Văn An"
Xin chào, Nguyễn Văn An
~~~

Spring Shell hỗ trợ cả dấu nháy đơn và dấu nháy kép để bao quanh giá trị có khoảng trắng. Dấu nháy bao ngoài được parser loại bỏ; nội dung bên trong trở thành giá trị của tham số.

## 5. Truyền một giá trị có khoảng trắng từ terminal

Khi gọi `java -jar`, terminal shell xử lý dấu nháy trước. Dấu nháy của Bash, PowerShell hoặc `cmd.exe` có nhiệm vụ giữ các từ thành một đối số khi gọi chương trình native.

Ví dụ chung:

~~~text
java -jar target/admin-cli-1.0.0.jar greet --name "Nguyễn Văn An"
~~~

Sau khi terminal xử lý lệnh, Java nhận các đối số ứng dụng tương đương:

~~~text
args[0] = "greet"
args[1] = "--name"
args[2] = "Nguyễn Văn An"
~~~

Đối số thứ ba là một chuỗi có dấu cách, không phải ba đối số `Nguyễn`, `Văn` và `An`. `NonInteractiveShellRunner` chuyển các đối số ứng dụng thành command để Spring Shell phân tích và thực thi.

Trong cách gọi thông thường, hãy đặt toàn bộ giá trị có dấu cách trong một cặp dấu nháy của terminal. Không đặt dấu nháy quanh toàn bộ command nếu bạn muốn terminal truyền riêng command, option và value.

## 6. Bash và các shell tương thích POSIX

Trong Bash, Zsh hoặc shell POSIX, dấu nháy kép giữ dấu cách trong cùng một đối số:

~~~bash
java -jar "target/admin-cli-1.0.0.jar" greet --name "Nguyễn Văn An"
~~~

Dấu nháy đơn giữ nguyên nội dung literal, không mở rộng biến hoặc biểu thức:

~~~bash
java -jar "target/admin-cli-1.0.0.jar" greet --name 'Nguyễn Văn An'
~~~

Nếu giá trị chứa dấu `$`, dấu backtick hoặc ký tự `!`, dấu nháy đơn thường dễ dự đoán hơn vì Bash không mở rộng biến hoặc history expansion bên trong chuỗi đó:

~~~bash
java -jar "target/admin-cli-1.0.0.jar" greet --name 'An $ Minh'
~~~

Nếu cần có dấu nháy đơn bên trong một chuỗi đã bao bằng nháy đơn, đóng chuỗi, thêm dấu nháy đã escape rồi mở chuỗi lại:

~~~bash
java -jar "target/admin-cli-1.0.0.jar" greet --name 'O'\''Brien'
~~~

Giá trị ứng dụng nhận được là `O'Brien`.

## 7. PowerShell

PowerShell dùng dấu nháy đơn cho chuỗi literal và dấu nháy kép cho chuỗi có thể mở rộng biến:

~~~powershell
java -jar "target/admin-cli-1.0.0.jar" greet --name 'Nguyễn Văn An'
~~~

Nếu muốn nội suy biến PowerShell:

~~~powershell
$customerName = 'Nguyễn Văn An'
java -jar "target/admin-cli-1.0.0.jar" greet --name "$customerName"
~~~

Nếu giá trị có dấu nháy đơn, nhân đôi dấu nháy đơn bên trong literal:

~~~powershell
java -jar "target/admin-cli-1.0.0.jar" greet --name 'O''Brien'
~~~

PowerShell 7.3 thay đổi cách truyền đối số tới chương trình native so với Windows PowerShell 5.1. Nếu script phụ thuộc vào dấu nháy lồng nhau, hãy kiểm thử trên đúng phiên bản PowerShell triển khai. Tránh dùng `--%` như giải pháp chung cho script có biến, vì token này ngừng phân tích phần còn lại của dòng theo quy tắc PowerShell.

## 8. Windows Command Prompt (cmd.exe)

Trong `cmd.exe`, dùng dấu nháy kép để giữ đường dẫn hoặc giá trị có dấu cách:

~~~bat
java -jar "target\admin-cli-1.0.0.jar" greet --name "Nguyễn Văn An"
~~~

Với đường dẫn Windows:

~~~bat
java -jar "C:\Program Files\Company Tools\admin-cli.jar" import --file "C:\Users\Lan Nguyen\Documents\monthly report.csv"
~~~

Dấu nháy kép giữ cả đường dẫn JAR và đường dẫn file thành từng đối số. Các ký tự như `&`, `|`, `<` và `>` có ý nghĩa đặc biệt trong `cmd.exe`; đặt giá trị chứa chúng trong dấu nháy kép và kiểm tra kết quả trong đúng loại script đang chạy.

Lưu ý `%NAME%` vẫn có thể được `cmd.exe` mở rộng thành biến môi trường ngay cả khi nằm trong dấu nháy kép. Nếu cần truyền dấu `%` nguyên dạng trong file batch, phải xử lý theo quy tắc escape của batch.

## 9. Phân biệt hai lớp phân tích dấu nháy

Khi gọi ứng dụng từ terminal, có hai bộ phân tích khác nhau:

1. Shell của hệ điều hành phân tích dòng lệnh và tạo danh sách đối số cho tiến trình Java.
2. Spring Shell phân tích command và option sau khi `NonInteractiveShellRunner` chuyển các application arguments thành command input.

Dấu nháy ở lớp thứ nhất giúp shell hệ điều hành giữ dấu cách trong cùng một đối số. Dấu nháy theo cú pháp Spring Shell giúp parser hiểu giá trị command có khoảng trắng. Runner non-interactive mặc định chuyển các application arguments thành command và bảo toàn các đối số có khoảng trắng khi tạo command input.

Ví dụ:

~~~bash
java -jar target/admin-cli-1.0.0.jar greet --name "Nguyễn Văn An"
~~~

Terminal giữ `Nguyễn Văn An` thành một đối số. Runner chuyển đối số đó thành một giá trị được trích dẫn cho parser của Spring Shell. Command nhận một chuỗi duy nhất.

Nếu ứng dụng tự đăng ký `NonInteractiveShellRunnerCustomizer` hoặc thay đổi cách `commandsFromArgs` tạo command, hãy kiểm tra lại quy tắc trích dẫn của mapping tùy chỉnh. Mapping phải bảo toàn ranh giới giữa command, option và giá trị có dấu cách.

## 10. Option có khoảng trắng và argument vị trí

Spring Shell hỗ trợ option dạng tách riêng tên và giá trị:

~~~text
greet --name "Nguyễn Văn An"
~~~

Và option dạng gán:

~~~text
greet --name="Nguyễn Văn An"
~~~

Khi gọi từ nhiều hệ điều hành, dạng tách riêng tên và giá trị thường dễ đọc và dễ kiểm tra hơn:

~~~bash
java -jar target/admin-cli-1.0.0.jar greet --name "Nguyễn Văn An"
~~~

Nếu command nhận tham số vị trí thay vì option, hãy trích dẫn toàn bộ giá trị:

~~~bash
java -jar target/admin-cli-1.0.0.jar greet "Nguyễn Văn An"
~~~

Chỉ dùng cách gọi positional khi command được khai báo có argument tương ứng. Với command có nhiều tham số, option có tên giúp tránh nhầm lẫn vị trí.

## 11. Giá trị có dấu nháy hoặc ký tự đặc biệt

Trong cú pháp command của Spring Shell, có thể dùng loại dấu nháy này để bao giá trị chứa loại dấu nháy còn lại:

~~~text
greet --name 'He said "Hello"'
greet --name "I'm here!"
~~~

Nếu cần chứa chính loại dấu nháy đang dùng để bao giá trị, escape dấu nháy đó bằng backslash theo quy tắc parser:

~~~text
greet --name "He said \"Hello\""
greet --name 'I\'m here!'
~~~

Khi gọi từ Bash, PowerShell hoặc `cmd.exe`, các ký tự escape còn phải đi qua parser của terminal trước khi đến Java. Vì vậy, với giá trị có nhiều dấu nháy, dấu `$`, dấu backtick, `!`, `&` hoặc `|`, hãy thử lệnh trên đúng shell và hệ điều hành mục tiêu. Nếu phải lặp lại lệnh phức tạp, dùng `ProcessBuilder` hoặc một script có kiểm thử thay vì ghép chuỗi command thủ công.

## 12. Truyền đường dẫn Windows có khoảng trắng

Một đường dẫn như:

~~~text
C:\Users\Lan Nguyen\Documents\monthly report.csv
~~~

có hai vị trí chứa dấu cách. Khi truyền cho command, đặt toàn bộ đường dẫn trong một cặp dấu nháy:

~~~powershell
java -jar "C:\Program Files\Company Tools\admin-cli.jar" import --file "C:\Users\Lan Nguyen\Documents\monthly report.csv"
~~~

Để tránh nhầm lẫn giữa backslash dùng trong đường dẫn và backslash escape của parser, có thể dùng dấu gạch chéo xuôi trong path Windows:

~~~powershell
java -jar "C:/Program Files/Company Tools/admin-cli.jar" import --file "C:/Users/Lan Nguyen/Documents/monthly report.csv"
~~~

Java NIO chấp nhận dấu gạch chéo xuôi trên Windows. Sau khi nhận path, ứng dụng nên chuyển thành `Path` bằng `Path.of(value)` hoặc `Paths.get(value)` và kiểm tra điều kiện file theo nghiệp vụ.

## 13. Phân biệt JVM option với option của command

Vị trí của option quyết định chương trình nào nhận nó:

~~~bash
java -Dspring.profiles.active=prod -Xmx512m -jar target/admin-cli-1.0.0.jar report export --file "C:/Reports/monthly report.csv"
~~~

- `-Dspring.profiles.active=prod` là system property của JVM, phải đứng trước `-jar`.
- `-Xmx512m` là tùy chọn bộ nhớ của JVM, cũng phải đứng trước `-jar`.
- `report export --file ...` là command và option của Spring Shell, nằm sau tên JAR.

Nếu đặt `-Dspring.profiles.active=prod` sau tên JAR, nó trở thành application argument chứ không còn là tùy chọn JVM. Với cấu hình Spring Boot, hãy dùng system property trước `-jar` hoặc biến môi trường như `SPRING_PROFILES_ACTIVE`; không giả định mọi `--key=value` sau JAR sẽ được xử lý như cấu hình Spring Boot, vì Spring Shell có thể nhận chúng như command input.

Ví dụ biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar target/admin-cli-1.0.0.jar report export --file "C:/Reports/monthly report.csv"
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'prod'
java -jar "target/admin-cli-1.0.0.jar" report export --file "C:/Reports/monthly report.csv"
~~~

## 14. Gọi JAR từ một chương trình Java bằng ProcessBuilder

Nếu một ứng dụng Java khác cần khởi chạy Spring Shell CLI, dùng `ProcessBuilder` với từng đối số là một phần tử riêng. Không ghép toàn bộ command thành một chuỗi rồi tự thêm dấu nháy:

~~~java
import java.nio.file.Path;

Process process = new ProcessBuilder(
        "java",
        "-jar",
        Path.of("build", "libs", "admin-cli-1.0.0.jar").toString(),
        "greet",
        "--name",
        "Nguyễn Văn An"
).inheritIO().start();

int exitCode = process.waitFor();
~~~

Mỗi phần tử trong danh sách là một đối số riêng. `ProcessBuilder` tự chuyển danh sách đó thành cách gọi tiến trình phù hợp với hệ điều hành, nên code không phải tự xử lý quy tắc dấu nháy của Bash, PowerShell hoặc `cmd.exe`.

Trong ứng dụng thực tế:

- Kiểm tra `exitCode` sau khi tiến trình kết thúc.
- Nếu không dùng `inheritIO()`, đọc stdout và stderr để tránh tiến trình con bị chặn khi buffer đầy.
- Đặt timeout nếu command có thể chạy lâu.
- Dùng đường dẫn JAR tuyệt đối hoặc tính từ thư mục cài đặt rõ ràng.
- Không ghép dữ liệu người dùng không tin cậy vào chuỗi shell rồi thực thi qua `cmd /c` hoặc `sh -c`.

## 15. Khi nào nên dùng file script?

Nếu phải truyền nhiều command, nhiều giá trị có dấu nháy hoặc một chuỗi thao tác dài, file script Spring Shell dễ kiểm tra hơn một dòng `java -jar` phức tạp.

Ví dụ nội dung `deploy.shell`:

~~~text
login --profile production
report export --name "Monthly report" --file "C:/Reports/monthly report.csv"
cache refresh --region "Asia Pacific"
~~~

Spring Shell 3.4 có `ScriptShellRunner`; trạng thái bật/tắt được điều khiển bởi `spring.shell.script.enabled`. Khi runner script được bật, có thể gọi file script bằng tiền tố `@`:

~~~bash
java --disable-@files -jar target/admin-cli-1.0.0.jar @deploy.shell
~~~

Có một điểm cần chú ý: Java launcher cũng dùng tiền tố `@file` cho argument file của chính nó và có thể mở rộng file đó trước khi gọi ứng dụng. Tùy chọn `--disable-@files` tắt việc mở rộng này, nhờ đó Spring Shell nhận được đối số `@deploy.shell` và chuyển nó cho `ScriptShellRunner`.

Trong script, mỗi dòng là command input của Spring Shell nên dùng cú pháp trích dẫn của parser Spring Shell. Kiểm tra `spring.shell.script.enabled` trong cấu hình triển khai; không giả định script runner được bật mặc định cùng với non-interactive runner.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Command nhận `Nguyễn` thay vì `Nguyễn Văn An` | Shell hệ điều hành tách giá trị tại dấu cách | Bao toàn bộ giá trị bằng dấu nháy của shell |
| `java` báo không tìm thấy JAR | Đường dẫn JAR có khoảng trắng nhưng không được trích dẫn | Đặt riêng đường dẫn JAR trong dấu nháy |
| Ứng dụng mở REPL thay vì chạy command | Runner hoặc cấu hình interactive không đúng | Kiểm tra `spring.shell.interactive.enabled` và `spring.shell.noninteractive.enabled` |
| Command báo thừa argument | Giá trị có dấu cách bị tách thành nhiều token | Kiểm tra ranh giới đối số ở terminal và mapping của runner |
| Giá trị có `$` bị thay đổi trong Bash | Dùng dấu nháy kép khiến shell mở rộng biến | Dùng dấu nháy đơn nếu cần chuỗi literal |
| Giá trị có `$name` bị nội suy trong PowerShell | Dùng dấu nháy kép | Dùng dấu nháy đơn hoặc escape theo quy tắc PowerShell |
| `&` hoặc `|` làm command bị chia tách trong `cmd.exe` | Ký tự có ý nghĩa điều khiển shell | Trích dẫn và kiểm thử trên `cmd.exe`; cân nhắc `ProcessBuilder` |
| Đường dẫn Windows bị sai | Backslash bị hiểu như escape trong parser hoặc đường dẫn chưa được trích dẫn | Dùng dấu nháy và cân nhắc dấu `/` trong path |
| `-D...` không có tác dụng | Đặt JVM option sau tên JAR | Chuyển option JVM lên trước `-jar` |
| Script `@deploy.shell` không chạy | Script runner đang bị tắt hoặc file không tìm thấy | Bật `spring.shell.script.enabled` và kiểm tra đường dẫn |
| Kết quả khác nhau giữa máy dev và CI | Shell, phiên bản PowerShell hoặc thư mục làm việc khác nhau | Kiểm tra lệnh trong đúng môi trường triển khai và dùng đường dẫn rõ ràng |

## 17. Checklist trước khi phân phối

Trước khi công bố cách chạy CLI, kiểm tra:

1. Executable JAR được tạo ra từ build và chạy được bằng `java -jar`.
2. Tài liệu ghi rõ phiên bản Java runtime tối thiểu.
3. Đường dẫn JAR có khoảng trắng vẫn được trích dẫn đúng.
4. Command có positional argument chứa khoảng trắng được kiểm thử.
5. Command có option chứa khoảng trắng được kiểm thử.
6. Các ví dụ Bash, PowerShell và `cmd.exe` dùng đúng quy tắc trích dẫn của từng shell.
7. JVM options đứng trước `-jar`; command options đứng sau tên JAR.
8. Cấu hình interactive/non-interactive được công bố rõ.
9. Script runner được bật nếu tài liệu hướng dẫn dùng file script.
10. Script hoặc chương trình gọi kiểm tra mã thoát của tiến trình.
11. Giá trị chứa ký tự đặc biệt được kiểm thử trong môi trường thực tế.
12. Không ghép chuỗi đầu vào không tin cậy thành lệnh shell để thực thi.

## 18. Bài tập thực hành

Tạo command `report export` nhận:

- `--name`: tên báo cáo, có thể chứa khoảng trắng.
- `--file`: đường dẫn file đích, có thể chứa khoảng trắng.

Ví dụ command:

~~~text
report export --name "Monthly report Q4" --file "C:/Reports/Monthly report Q4.csv"
~~~

Thực hiện:

1. Build executable JAR bằng Maven hoặc Gradle.
2. Chạy command từ Bash với tên báo cáo `Monthly report Q4`.
3. Chạy lại từ PowerShell và `cmd.exe`.
4. Thử đường dẫn JAR đặt trong thư mục có khoảng trắng.
5. Thêm một system property bằng `-D` và xác nhận nó được đọc trong ứng dụng.
6. Gọi JAR bằng `ProcessBuilder` và truyền tên báo cáo thành một phần tử riêng.
7. Thử một file script có ít nhất hai command và kiểm tra cấu hình script runner.
8. Xác nhận command nhận đúng chuỗi, file được tạo đúng vị trí và mã thoát phản ánh kết quả.

Sau bài tập, hãy giải thích được sự khác nhau giữa dấu nháy dùng để gọi tiến trình Java và dấu nháy dùng trong cú pháp command của Spring Shell.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.4/getting-started.html)
- [Spring Shell 3.4.3 – Execution and Shell Runners](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Shell 3.4 API – NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/NonInteractiveShellRunner.html)
- [Spring Boot 3.5 – Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Java 17 Launcher – java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [PowerShell – about_Quoting_Rules](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules)
- [PowerShell – about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing)
- [Spring Shell 3.4 – Script Runner Configuration](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
