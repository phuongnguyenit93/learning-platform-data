# Kiểm chứng cú pháp trên Windows, Bash hoặc môi trường đích thực tế

Một command Spring Shell có thể chạy đúng trong bài kiểm thử nhưng gặp lỗi khi người dùng nhập từ PowerShell, Command Prompt, Bash, terminal từ xa hoặc một script triển khai. Nguyên nhân thường nằm ở một trong ba lớp: shell của hệ điều hành biến đổi dòng lệnh trước khi khởi chạy Java, parser của Spring Shell tách command thành tên/option/argument, hoặc môi trường chạy xử lý đường dẫn, encoding, quyền truy cập và tài nguyên theo cách khác.

Vì vậy, kiểm chứng cú pháp cần được thực hiện ở đúng nơi người dùng sẽ nhập lệnh. Bài học này trình bày cách phân biệt các lớp phân tích, cách kiểm tra cú pháp Spring Shell 4.x, cách chạy ứng dụng từ PowerShell, Command Prompt và Bash, cách kiểm thử file script và cách lập ma trận xác minh trên môi trường triển khai.

Nội dung thuộc phạm vi **SPRING_SHELL**: xây dựng ứng dụng CLI bằng khai báo command, xử lý đối số, validation, trợ giúp và tự hoàn thành; đồng thời bảo đảm command hoạt động ổn định khi người dùng chạy tương tác hoặc tự động hóa bằng script.

## 1. Vì sao cần kiểm chứng trên môi trường thật?

Một dòng lệnh không phải lúc nào cũng được xử lý trực tiếp bởi Spring Shell. Trước khi ứng dụng nhận được dữ liệu, văn bản có thể đi qua terminal và shell của hệ điều hành.

Ví dụ, khi người dùng mở PowerShell và chạy:

~~~powershell
java -jar "C:\Apps\Customer CLI\customer-cli.jar"
~~~

PowerShell phân tích lệnh gọi Java, xử lý dấu nháy và truyền các đối số khởi động cho tiến trình. Sau khi ứng dụng Spring Shell mở prompt, người dùng nhập:

~~~text
shell:> report export --file "C:\Data Reports\monthly report.csv" --format json
~~~

Dòng lệnh này được Spring Shell phân tích. PowerShell không tiếp tục phân tích nội dung người dùng gõ bên trong prompt của Spring Shell.

Điểm phân biệt này rất quan trọng. Quy tắc dấu nháy, biến môi trường và ký tự đặc biệt của PowerShell hoặc Bash áp dụng khi shell hệ điều hành đang xử lý một lệnh gọi tiến trình. Khi người dùng đã ở trong prompt của Spring Shell, parser của Spring Shell chịu trách nhiệm xử lý command line.

Có thể hình dung các lớp như sau:

~~~mermaid
flowchart TD
    U["Người dùng / script"] --> H["Shell hệ điều hành<br/>PowerShell, cmd.exe, Bash"]
    H --> P["Tiến trình Java<br/>Spring Boot"]
    P --> T["Terminal / JLine"]
    T --> S["Spring Shell CommandParser"]
    S --> B["Binding option và argument"]
    B --> V["Validation và chuyển đổi kiểu"]
    V --> C["Command method / service"]
    C --> O["Output và mã thoát"]
~~~

Nếu lỗi xảy ra trước khi Java khởi động, cần kiểm tra shell hệ điều hành. Nếu ứng dụng nhận được dòng nhập nhưng báo thiếu option hoặc sai cú pháp, cần kiểm tra parser và metadata command. Nếu command đã chạy nhưng không mở được file, cần kiểm tra đường dẫn, quyền và working directory.

## 2. Ba lớp cần kiểm tra riêng

| Lớp | Thành phần xử lý | Ví dụ lỗi | Cách kiểm tra |
|---|---|---|---|
| Gọi tiến trình | PowerShell, cmd.exe, Bash, script wrapper | Không tìm thấy file JAR; đường dẫn có khoảng trắng bị tách | Kiểm tra lệnh khởi động và đối số tiến trình |
| Phân tích command | Spring Shell CommandParser | Command không nhận đúng option hoặc argument | Gửi raw command vào parser hoặc ShellTestClient |
| Môi trường thực thi | JVM, hệ điều hành, filesystem, terminal | Không đọc được file, sai encoding, thiếu quyền | Chạy thử trên môi trường đích với dữ liệu đại diện |

Không nên dùng một kết quả kiểm thử ở lớp này để kết luận hai lớp còn lại đã đúng. Ví dụ, ShellTestClient có thể xác nhận Spring Shell hiểu đúng chuỗi report export --file "Monthly Report.csv", nhưng nó không kiểm tra PowerShell có truyền đúng đường dẫn tới file JAR khi khởi động tiến trình hay không.

Ngược lại, lệnh java -jar chạy thành công chỉ xác nhận ứng dụng khởi động được. Nó chưa chứng minh command report export nhận đúng đối số hoặc xử lý file theo yêu cầu.

## 3. Xác định cú pháp mà Spring Shell đang sử dụng

Trước khi kiểm thử, cần xác định phiên bản Spring Shell mà ứng dụng thực sự đóng gói. Các thế hệ API có thể khác nhau về annotation, parser và cách đăng ký command.

Với Spring Shell 4.0.3, tài liệu cú pháp mô tả command path gồm tên command, các từ subcommand, option và argument. Option có thể dùng dạng dài hoặc ngắn:

~~~text
--key=value
--key value
-k=value
-k value
~~~

Ví dụ:

~~~text
report export --format=json --file "Monthly Report.csv"
report export --format json --file "Monthly Report.csv"
report export -f=json --file "Monthly Report.csv"
report export -f json --file "Monthly Report.csv"
~~~

Các option và argument có thể xuất hiện theo thứ tự khác nhau. Argument vị trí được đánh chỉ số từ 0 trong nhóm argument. Khi có subcommand hoặc nhiều tham số, nên ưu tiên option có tên để lời gọi dễ đọc và ít nhập nhằng.

Có hai điểm cần kiểm tra theo tài liệu Spring Shell 4.0.3:

- Khi một option được chỉ định, option luôn cần có giá trị, kể cả option kiểu boolean. Ví dụ --dry-run true, không nên mặc định rằng chỉ viết --dry-run là đủ.
- Các short option không hỗ trợ gộp thành nhóm như -abc. Hãy dùng từng option riêng, ví dụ -a true -b value -c 3.

Cấu trúc khái quát:

~~~text
CommandSyntax ::= CommandName [SubCommandName]* [Option | Argument]*
~~~

Trong Spring Shell 4.x, CommandParser là API có thể thay thế để tùy chỉnh cách phân tích nếu quy tắc mặc định không đáp ứng yêu cầu. Nếu ứng dụng có parser tùy chỉnh, các ca kiểm thử phải dùng parser thực tế được đăng ký trong ApplicationContext, không chỉ kiểm tra giả định theo parser mặc định.

## 4. Tạo command đại diện để kiểm chứng

Một command kiểm tra cú pháp nên có đủ loại dữ liệu thường gây lỗi: đường dẫn có khoảng trắng, option có tên, giá trị Unicode, giá trị có dấu gạch ngang và argument vị trí.

Ví dụ với Spring Shell 4.x:

~~~java
package com.example.customercli.command;

import org.springframework.shell.command.annotation.Argument;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(name = "report export", description = "Export a report")
    public String export(
            @Option(longName = "file") String file,
            @Option(longName = "format", defaultValue = "csv") String format,
            @Option(longName = "dry-run", defaultValue = "false") boolean dryRun,
            @Argument(index = 0, defaultValue = "monthly") String reportType) {

        return "file=" + file
                + "; format=" + format
                + "; dryRun=" + dryRun
                + "; reportType=" + reportType;
    }
}
~~~

Một số ví dụ đầu vào:

~~~text
report export --file "Monthly Reports/sales.csv" --format json --dry-run true
report export monthly --format=csv --file "Monthly Reports/sales.csv"
report export --file "Báo cáo tháng 11.csv" --format json --dry-run false
~~~

Đầu ra giúp kiểm tra giá trị đã được binding:

~~~text
file=Monthly Reports/sales.csv; format=json; dryRun=true; reportType=monthly
~~~

Đây là command minh họa để kiểm chứng cú pháp. Trong ứng dụng thực tế, command nên chuyển đường dẫn sang Path hoặc một kiểu dữ liệu phù hợp và giao việc xuất báo cáo cho service.

## 5. Kiểm tra từ PowerShell trên Windows

PowerShell có quy tắc phân tích riêng. Khi gọi một chương trình bên ngoài, PowerShell xử lý token, chuỗi, biến và ký tự đặc biệt trước khi truyền đối số cho tiến trình.

### 5.1. Khởi động JAR có đường dẫn chứa khoảng trắng

Có thể dùng toán tử gọi & khi đường dẫn tới executable có khoảng trắng:

~~~powershell
& 'C:\Program Files\Java\bin\java.exe' -jar 'C:\Apps\Customer CLI\customer-cli.jar'
~~~

Trong PowerShell:

- Chuỗi nháy đơn giữ nguyên nội dung bên trong.
- Chuỗi nháy kép có thể nội suy biến như $env:USERPROFILE.
- Dấu backtick là ký tự escape của PowerShell.
- Dấu gạch chéo ngược \ không phải ký tự escape của PowerShell.

Ví dụ:

~~~powershell
$jar = 'C:\Apps\Customer CLI\customer-cli.jar'
& java -jar $jar
~~~

Nếu đường dẫn chứa khoảng trắng, hãy giữ nó thành một giá trị chuỗi duy nhất. Không tự thêm dấu nháy vào giá trị biến nếu mục tiêu chỉ là truyền đường dẫn cho chương trình.

### 5.2. Nhập command bên trong Spring Shell

Sau khi prompt Spring Shell xuất hiện, nhập command theo cú pháp Spring Shell:

~~~text
shell:> report export --file 'C:\Data Reports\monthly report.csv' --format json
~~~

Dấu nháy trong ví dụ này được parser Spring Shell xử lý. PowerShell không nội suy biến hoặc diễn giải dấu nháy trong dòng lệnh đang được nhập bên trong REPL.

Nếu ứng dụng hỗ trợ đường dẫn Windows có dấu gạch chéo ngược, hãy kiểm tra cách parser của phiên bản đang dùng xử lý giá trị đó. Có thể dùng đường dẫn có dấu gạch chéo xuôi nếu API và filesystem đích hỗ trợ:

~~~text
shell:> report export --file "C:/Data Reports/monthly report.csv" --format json
~~~

Không suy luận rằng quy tắc escape của PowerShell và quy tắc escape của Spring Shell giống nhau.

### 5.3. Biến môi trường và ký tự đặc biệt

PowerShell truy cập biến môi trường bằng cú pháp $env:NAME:

~~~powershell
$env:REPORT_DIR = 'C:\Data Reports'
& java -jar 'C:\Apps\customer-cli.jar'
~~~

Ứng dụng Java có thể đọc biến môi trường bằng System.getenv("REPORT_DIR"). Nhưng nếu người dùng gõ chuỗi $env:REPORT_DIR trong prompt Spring Shell, parser Spring Shell không tự động áp dụng cú pháp biến môi trường PowerShell.

Nếu command cần sử dụng biến môi trường, hãy đọc giá trị trong ứng dụng hoặc truyền giá trị đã được PowerShell mở rộng trước khi khởi chạy tiến trình.

Một số ký tự như &, |, < và > có ý nghĩa đặc biệt trong PowerShell hoặc Command Prompt. Khi truyền chúng trong lệnh khởi chạy tiến trình, cần dùng quoting/escaping theo đúng shell. Khi nhập bên trong Spring Shell, hãy kiểm tra quy tắc parser của ứng dụng.

### 5.4. Khác biệt PowerShell 5.1 và PowerShell 7.x

PowerShell 7.3 thay đổi cách truyền đối số cho chương trình native so với Windows PowerShell 5.1. Điều này có thể ảnh hưởng đến script cũ có nhiều dấu nháy lồng nhau hoặc truyền chuỗi rỗng.

Nếu ứng dụng được gọi từ automation PowerShell, hãy kiểm tra phiên bản PowerShell thực tế:

~~~powershell
$PSVersionTable.PSVersion
~~~

Khi cần truyền nhiều đối số phức tạp, nên dùng các API hoặc cấu trúc argument list thay vì nối một chuỗi command dài rồi tự xử lý dấu nháy. Tài liệu PowerShell mô tả các chế độ truyền đối số native và các trường hợp khác nhau giữa phiên bản.

## 6. Kiểm tra từ Command Prompt (cmd.exe)

Command Prompt có quy tắc riêng và không dùng cú pháp biến môi trường của PowerShell.

### 6.1. Khởi động ứng dụng

~~~bat
set "APP_JAR=C:\Apps\Customer CLI\customer-cli.jar"
java -jar "%APP_JAR%"
~~~

Dạng set "NAME=value" giúp tránh đưa dấu cách ở cuối vào giá trị biến. Khi thay biến, dùng cú pháp %APP_JAR%.

Đường dẫn có khoảng trắng cần được đặt trong dấu nháy kép khi truyền cho chương trình:

~~~bat
java -jar "C:\Apps\Customer CLI\customer-cli.jar"
~~~

### 6.2. Ký tự điều khiển của cmd.exe

Trong Command Prompt, các ký tự như &, |, <, > và ^ có ý nghĩa đặc biệt. Nếu cần truyền chúng như dữ liệu, phải quote hoặc escape đúng quy tắc cmd.exe.

Ví dụ, & có thể dùng để nối hai lệnh. Nếu nó nằm trong giá trị cần truyền cho chương trình, không được để cmd.exe hiểu nhầm là dấu phân cách lệnh.

### 6.3. Đừng nhầm biến của cmd với dữ liệu command

Trong batch file, %REPORT_DIR% được cmd.exe thay thế trước khi gọi tiến trình. Khi người dùng nhập chuỗi này tại prompt Spring Shell, nó không tự được thay bằng giá trị biến của cmd.exe.

Nếu cần kiểm tra giá trị sau khi khởi chạy, có thể để command hiển thị giá trị cấu hình đã được Java đọc từ environment:

~~~java
@Command(name = "config show-report-dir")
public String showReportDirectory() {
    return System.getenv("REPORT_DIR");
}
~~~

## 7. Kiểm tra từ Bash trên Linux hoặc macOS

Bash cũng xử lý lệnh trước khi khởi chạy Java, nhưng cách quote và mở rộng biến khác PowerShell và cmd.exe.

### 7.1. Khởi động JAR có đường dẫn chứa khoảng trắng

~~~bash
APP_JAR='/opt/customer cli/customer-cli.jar'
java -jar "$APP_JAR"
~~~

Hoặc:

~~~bash
java -jar "/opt/customer cli/customer-cli.jar"
~~~

Trong Bash:

- Nháy đơn giữ nguyên mọi ký tự bên trong.
- Nháy kép vẫn cho phép mở rộng biến và command substitution.
- Backslash không nằm trong dấu nháy có thể escape ký tự tiếp theo.
- Giá trị biến không được quote có thể bị word splitting và pathname expansion.

Vì vậy, khi truyền biến làm một đối số, hãy quote biến:

~~~bash
REPORT_FILE='/data/Monthly Reports/sales.csv'
printf '%s\n' "$REPORT_FILE"
~~~

Dùng "$REPORT_FILE" để giữ toàn bộ giá trị thành một đối số.

### 7.2. Nhập command bên trong Spring Shell

Sau khi Java mở prompt, nhập command theo cú pháp Spring Shell:

~~~text
shell:> report export --file '/data/Monthly Reports/sales.csv' --format json
~~~

Dấu nháy đơn ở đây được xử lý bởi parser Spring Shell. Bash không mở rộng $HOME, $(...) hay wildcard trong dòng người dùng nhập bên trong prompt Spring Shell.

Nếu muốn sử dụng thư mục home, hãy truyền giá trị thực hoặc để ứng dụng tự phân giải home directory bằng Java:

~~~java
Path home = Path.of(System.getProperty("user.home"));
~~~

Không nên dựa vào việc chuỗi ~/reports sẽ luôn được shell Spring mở rộng như Bash. Tilde expansion là hành vi của shell hệ điều hành, không phải quy tắc mặc định của mọi parser CLI.

### 7.3. Wildcard và command substitution

Trong Bash, wildcard như *.csv có thể được mở rộng thành danh sách file trước khi chương trình nhận đối số. Biểu thức $(...) có thể thực thi command substitution. Điều này chỉ xảy ra khi Bash đang xử lý dòng lệnh.

Nếu cần truyền wildcard nguyên dạng cho ứng dụng từ Bash, hãy quote nó:

~~~bash
java -jar customer-cli.jar
~~~

Sau khi prompt xuất hiện, nếu command của ứng dụng nhận pattern, hãy nhập pattern có quote:

~~~text
shell:> report list --pattern '*.csv'
~~~

Còn khi nhập bên trong Spring Shell, hãy kiểm tra parser và command của ứng dụng có hỗ trợ pattern hay không. Không giả định rằng Spring Shell sẽ tự tìm tất cả file khớp wildcard.

## 8. So sánh nhanh các shell hệ điều hành

| Nhu cầu | PowerShell | cmd.exe | Bash |
|---|---|---|---|
| Chuỗi giữ nguyên | Nháy đơn | Nháy kép | Nháy đơn |
| Chuỗi có mở rộng biến | Nháy kép | %NAME% được thay | Nháy kép cho phép $NAME |
| Cú pháp biến môi trường | $env:NAME | %NAME% | $NAME |
| Escape phổ biến | Backtick | Caret ^ | Backslash \ |
| Ký tự pipe | \| là pipeline | \| là pipeline | \| là pipeline |
| Wildcard | Phụ thuộc ngữ cảnh và command | Tùy chương trình xử lý | Bash có pathname expansion |
| Thư mục home | $HOME hoặc $env:USERPROFILE | %USERPROFILE% | $HOME hoặc ~ |

Bảng này mô tả shell hệ điều hành. Khi người dùng đã ở prompt Spring Shell, cú pháp biến, wildcard và escape phải theo parser và logic của ứng dụng.

## 9. Kiểm tra đường dẫn và filesystem trên môi trường đích

Một command có thể parse đúng nhưng vẫn thất bại khi mở file. Các khác biệt thường gặp giữa Windows và Linux gồm:

- Dấu phân cách thư mục: Windows thường dùng \, Linux/macOS dùng /.
- Quy tắc phân biệt chữ hoa/chữ thường: filesystem Windows thường không phân biệt case theo mặc định, còn filesystem Linux thường phân biệt.
- Quyền truy cập: tài khoản chạy service hoặc container có thể không có quyền đọc/ghi thư mục.
- Working directory: đường dẫn tương đối được tính từ thư mục làm việc của tiến trình, không nhất thiết là thư mục chứa JAR.
- Đường dẫn mạng: ổ đĩa mapped trên Windows có thể không tồn tại trong phiên chạy service hoặc tài khoản khác.
- Symlink và mount: đường dẫn hợp lệ trên máy phát triển có thể không tồn tại trong container hoặc máy đích.

### 9.1. Dùng Path thay vì nối chuỗi đường dẫn

Trong Java, nên dùng Path và Files để làm việc với filesystem:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

// Giả sử fileArgument là giá trị đã được binding từ option --file.
Path outputPath = Path.of(fileArgument).toAbsolutePath().normalize();

if (outputPath.getParent() == null || !Files.isDirectory(outputPath.getParent())) {
    throw new IllegalArgumentException(
            "Output directory does not exist: " + outputPath.getParent());
}
~~~

Không tự nối đường dẫn bằng cách ghép chuỗi với dấu / hoặc \. API Path và Paths giúp xử lý đường dẫn theo filesystem của hệ điều hành hiện tại.

### 9.2. Kiểm tra working directory

Có thể hiển thị thư mục làm việc trong một command chẩn đoán:

~~~java
@Command(name = "environment show-working-directory")
public String showWorkingDirectory() {
    return Path.of("").toAbsolutePath().normalize().toString();
}
~~~

Nếu command nhận đường dẫn tương đối, hãy ghi rõ đường dẫn được tính từ working directory. Khi triển khai service, container hoặc scheduled task, cần đặt working directory rõ ràng.

### 9.3. Kiểm tra file có khoảng trắng và Unicode

Tạo các file kiểm thử có tên đại diện:

~~~text
report.csv
monthly report.csv
Báo cáo tháng 11.csv
data (final).csv
sales & tax.csv
~~~

Thử từng file trên môi trường đích. Các tên có khoảng trắng, dấu tiếng Việt, ngoặc hoặc ký tự đặc biệt giúp phát hiện lỗi parsing và encoding mà tên file đơn giản không bộc lộ.

## 10. Kiểm tra encoding, terminal và đầu ra

Cú pháp có thể đúng nhưng output hiển thị sai nếu terminal và tiến trình không dùng cùng cách mã hóa hoặc font không có ký tự cần thiết.

Cần kiểm tra:

- JVM sử dụng encoding nào khi đọc/ghi file.
- File script được lưu bằng UTF-8 hay encoding khác.
- Terminal hỗ trợ và hiển thị tiếng Việt ra sao.
- Log và output có giữ nguyên dấu tiếng Việt không.
- Khi redirect output ra file, file có thể được đọc lại đúng không.
- Màu ANSI và ký tự điều khiển có được terminal hỗ trợ không.

Ví dụ, command có thể trả về:

~~~text
Đã xuất báo cáo thành công: Báo cáo tháng 11.csv
~~~

Hãy kiểm tra kết quả trong terminal thực tế, đồng thời redirect output nếu quy trình triển khai có sử dụng:

~~~powershell
java -jar 'C:\Apps\customer-cli.jar' *> .\run-output.txt
~~~

~~~bash
java -jar ./customer-cli.jar > ./run-output.txt 2>&1
~~~

Cú pháp redirect khác nhau giữa các shell. Hãy đọc lại file output bằng encoding phù hợp để xác nhận nội dung thực sự được ghi đúng.

## 11. Kiểm tra file script của Spring Shell

Spring Shell có command tích hợp script để thực thi nhiều command từ một file. Theo tài liệu Spring Shell 4.0.3, file script chứa một command trên mỗi dòng và các dòng được thực thi theo thứ tự. Dòng bắt đầu bằng // được dùng làm comment.

Ví dụ file setup-shell.txt:

~~~text
// Prepare the working session
project select --name demo
config set --key output-format --value json
report export --file "reports/monthly report.csv"
~~~

Trong prompt Spring Shell, gọi script:

~~~text
shell:> script --file "C:/Apps/Customer CLI/scripts/setup-shell.txt"
~~~

Trên Linux hoặc macOS:

~~~text
shell:> script --file "/opt/customer-cli/scripts/setup-shell.txt"
~~~

Cần phân biệt file script Spring Shell với file script của hệ điều hành:

| Loại file | Được xử lý bởi | Nội dung |
|---|---|---|
| Spring Shell script, ví dụ .txt | Command script của Spring Shell | Mỗi dòng là một command Spring Shell |
| PowerShell script, .ps1 | PowerShell | Lệnh khởi chạy Java, đặt biến và điều phối tiến trình |
| Batch file, .bat hoặc .cmd | cmd.exe | Lệnh dành cho Windows Command Processor |
| Shell script, .sh | Bash hoặc shell tương thích | Lệnh khởi chạy Java và xử lý môi trường Unix |

Các file .ps1, .cmd và .sh có cú pháp riêng. Không thể lấy nguyên cú pháp của file script Spring Shell rồi chạy trực tiếp trong Bash hoặc PowerShell.

### 11.1. Kiểm tra line ending và encoding của script

Khi chạy script trên nhiều hệ điều hành, hãy xác minh:

- File được lưu bằng UTF-8.
- Mỗi command nằm trên dòng riêng.
- Không có dấu nháy chưa đóng.
- Không có ký tự điều khiển thừa ở cuối dòng.
- Đường dẫn trong script tồn tại trên máy đích.
- Thứ tự command phù hợp với trạng thái ứng dụng.
- Script không phụ thuộc vào thư mục làm việc ngầm định.

Với shell script hệ điều hành trên Linux, file .sh thường cần line ending LF và quyền thực thi phù hợp. Đây là yêu cầu của shell hệ điều hành; không nên áp dụng máy móc cho file script Spring Shell.

## 12. Kiểm thử parser bằng ShellTestClient

Spring Shell 4.0.3 cung cấp ShellTestClient, ShellScreen và ShellAssertions để mô phỏng người dùng gửi command và kiểm tra output.

Ví dụ:

~~~java
@ShellTest
@ContextConfiguration(classes = CustomerCliApplication.class)
class ReportCommandSyntaxTests {

    @Autowired
    private ShellTestClient client;

    @Test
    void shouldAcceptQuotedPathWithSpaces() throws Exception {
        ShellScreen screen = client.sendCommand(
                "report export --file 'Monthly Reports/sales.csv' --format json");

        ShellAssertions.assertThat(screen)
                .containsText("Monthly Reports/sales.csv");
        ShellAssertions.assertThat(screen)
                .containsText("format=json");
    }

    @Test
    void shouldAcceptOptionsInDifferentOrder() throws Exception {
        ShellScreen screen = client.sendCommand(
                "report export monthly --format=csv --file report.csv");

        ShellAssertions.assertThat(screen)
                .containsText("reportType=monthly");
        ShellAssertions.assertThat(screen)
                .containsText("format=csv");
    }
}
~~~

Test client gửi chuỗi trực tiếp vào shell parser và thu lại output. Nó kiểm tra cách Spring Shell hiểu dòng lệnh, binding option/argument và thực thi command.

Test này không khởi chạy PowerShell, cmd.exe hoặc Bash. Vì vậy, nó không xác nhận các shell hệ điều hành truyền đối số đúng khi khởi động tiến trình.

### 12.1. Kiểm thử command không hợp lệ

Bổ sung trường hợp thiếu option hoặc nhập sai kiểu:

~~~java
@Test
void shouldRejectUnknownCommand() {
    Assertions.assertThatThrownBy(() -> client.sendCommand("report unknown"))
            .isInstanceOf(CommandNotFoundException.class);
}
~~~

Các lỗi validation và chuyển đổi kiểu nên được kiểm tra riêng. Ví dụ, truyền chuỗi vào option yêu cầu số nguyên, bỏ thiếu option bắt buộc hoặc truyền giá trị không nằm trong miền hợp lệ.

### 12.2. Kiểm thử parser tùy chỉnh

Nếu ứng dụng thay thế CommandParser, test cần xác minh parser bean thực tế được sử dụng. API CommandParser.parse(String) nhận raw input và trả ParsedInput. Có thể viết unit test cho quy tắc tùy chỉnh, sau đó dùng ShellTestClient để kiểm tra tích hợp từ input tới command output.

## 13. Kiểm tra cách khởi chạy tiến trình Java

Nếu một chương trình khác gọi Spring Shell, nên kiểm tra cách chương trình đó truyền đối số.

Khi dùng Java ProcessBuilder, truyền mỗi đối số như một phần tử riêng:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        "java",
        "-jar",
        "C:/Apps/Customer CLI/customer-cli.jar"
);

processBuilder.directory(new File("C:/Apps/Customer CLI"));
Process process = processBuilder.start();
~~~

Không cần tự thêm dấu nháy vào từng phần tử của danh sách đối số. ProcessBuilder nhận các đối số riêng lẻ và chịu trách nhiệm tạo lời gọi tiến trình phù hợp với nền tảng.

Nếu chủ động gọi qua một shell như cmd.exe /c hoặc bash -lc, lúc đó shell trung gian sẽ phân tích một chuỗi lệnh. Cần quote theo đúng shell được chọn. Hãy hạn chế thêm shell trung gian nếu không cần expansion, pipe hoặc redirect.

## 14. Ma trận kiểm chứng theo môi trường

Không phải dự án nào cũng cần kiểm tra mọi tổ hợp terminal. Hãy chọn ma trận theo hệ điều hành và cách người dùng thực sự chạy ứng dụng.

| Môi trường | Cách khởi động | Ca kiểm tra quan trọng |
|---|---|---|
| Windows PowerShell 5.1 | java -jar ... từ PowerShell | Đường dẫn có khoảng trắng, biến môi trường, dấu nháy lồng |
| PowerShell 7.x | java -jar ... từ pwsh | Truyền đối số native, chuỗi rỗng, ký tự quote |
| Windows cmd.exe | java -jar ... từ Command Prompt | %VAR%, ký tự &/pipe, đường dẫn có khoảng trắng |
| Linux Bash | java -jar ... từ Bash | Quote biến, wildcard, command substitution, path Unix |
| macOS terminal | java -jar ... từ zsh hoặc Bash | Path, quyền file, encoding và phiên bản Java |
| Container/SSH | Lệnh entrypoint hoặc remote shell | Working directory, environment, mount, quyền và terminal không tương tác |

Với mỗi môi trường, nên kiểm tra ít nhất:

1. Ứng dụng khởi động và hiển thị prompt.
2. Command cơ bản chạy được.
3. Command có nhiều option chạy được ở cả hai dạng --key=value và --key value.
4. Giá trị có khoảng trắng được giữ nguyên.
5. Đường dẫn file có khoảng trắng và Unicode được mở đúng.
6. Giá trị boolean và giá trị mặc định được binding đúng.
7. Lỗi cú pháp hiển thị thông báo có thể hiểu được.
8. Command trợ giúp và completion hoạt động trong terminal tương tác.
9. Script Spring Shell chạy theo đúng thứ tự.
10. Output và mã thoát phù hợp với cách ứng dụng được gọi.

## 15. Quy trình chẩn đoán khi cú pháp hoạt động khác nhau

Khi cùng một command chạy trên máy này nhưng lỗi trên máy khác, hãy thu thập thông tin trước khi sửa parser.

### Bước 1: Ghi nhận môi trường

Ghi lại:

- Hệ điều hành và phiên bản.
- Shell đang dùng: PowerShell, cmd.exe, Bash, zsh hoặc shell khác.
- Phiên bản PowerShell nếu chạy Windows.
- Phiên bản Java.
- Phiên bản Spring Shell thực tế trong dependency/package.
- Terminal tương tác, SSH, container hay tiến trình không có terminal.
- Working directory và tài khoản chạy ứng dụng.

### Bước 2: Xác nhận ứng dụng nhận được gì

Nếu command nhận sai giá trị, tạo một command chẩn đoán tạm thời hoặc log giá trị đã binding. Nên hiển thị từng giá trị dưới dạng có dấu phân cách để nhận ra khoảng trắng đầu/cuối:

~~~java
@Command(name = "debug show-arguments")
public String showArguments(
        @Option(longName = "value") String value) {
    return "value=[" + value + "], length=" + value.length();
}
~~~

Ví dụ output:

~~~text
value=[Monthly Reports/sales.csv], length=25
~~~

Nếu giá trị đã sai trước khi vào command, hãy xác định lỗi ở shell hệ điều hành hay Spring Shell parser.

### Bước 3: Tách ca kiểm thử nhỏ

Thử lần lượt:

~~~text
report export --file report.csv
report export --file "Monthly Reports/sales.csv"
report export --file "Báo cáo tháng 11.csv"
report export --format=json --file report.csv
report export --file report.csv --format json
~~~

Bắt đầu từ chuỗi đơn giản, sau đó thêm khoảng trắng, Unicode, option và đường dẫn. Không thay nhiều yếu tố trong cùng một lần thử vì sẽ khó xác định nguyên nhân.

### Bước 4: Kiểm tra filesystem và quyền

Nếu command nhận đúng đường dẫn nhưng không mở được file, kiểm tra:

- File có tồn tại trên máy đích không?
- Đường dẫn tương đối được tính từ thư mục nào?
- Tài khoản chạy ứng dụng có quyền đọc/ghi không?
- Thư mục cha có tồn tại không?
- File có đang bị tiến trình khác khóa không?
- Container hoặc service có mount đúng volume không?

### Bước 5: So sánh parser và cấu hình

Nếu chỉ một phiên bản Spring Shell gặp lỗi, kiểm tra:

- Dependency có đúng phiên bản mong muốn không?
- Có CommandParser tùy chỉnh không?
- Có parser hoặc converter khác nhau theo profile không?
- Có thay đổi metadata option/argument không?
- Có khác biệt giữa test classpath và runtime package không?

Không nên thêm xử lý đặc biệt cho Windows hoặc Bash trước khi xác định lớp nào thực sự làm thay đổi input.

## 16. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Java không tìm thấy JAR | Shell hệ điều hành tách đường dẫn có khoảng trắng | Quote đường dẫn trong lệnh khởi động |
| Giá trị option bị chia thành nhiều phần | Thiếu quote ở nơi parser đang xử lý | Quote giá trị theo parser của lớp tương ứng |
| Biến môi trường không được thay | Gõ cú pháp biến của OS shell trong prompt Spring Shell | Đọc biến trong Java hoặc truyền giá trị thực |
| Bash truyền nhiều file thay vì một wildcard | Pathname expansion diễn ra trước khi gọi tiến trình | Quote wildcard nếu cần truyền nguyên dạng |
| PowerShell truyền dấu nháy khác dự kiến | Khác biệt native argument passing giữa phiên bản | Kiểm tra PowerShell 5.1/7.x và cách gọi native |
| cmd.exe thực thi phần sau dấu & | Ký tự điều khiển bị hiểu là toán tử | Quote hoặc escape theo cmd.exe |
| File không mở được trên Linux | Khác biệt chữ hoa/thường hoặc quyền | Kiểm tra tên file chính xác và permission |
| Đường dẫn tương đối không đúng | Working directory khác | Dùng đường dẫn tuyệt đối hoặc đặt working directory rõ ràng |
| Tiếng Việt hiển thị lỗi | Encoding, code page hoặc font terminal | Kiểm tra encoding đầu vào/đầu ra và terminal |
| Script dừng giữa chừng | Một command lỗi hoặc trạng thái trước đó chưa sẵn sàng | Kiểm tra từng dòng và thứ tự thực thi |
| Test parser pass nhưng môi trường thật fail | Test không chạy qua shell hệ điều hành | Bổ sung smoke test trên OS/terminal đích |

## 17. Bài thực hành: kiểm chứng command export trên Windows và Bash

Xây dựng command report export nhận ba option:

- --file: đường dẫn file đầu ra.
- --format: định dạng csv hoặc json.
- --dry-run: giá trị boolean cho chế độ chạy thử.

Thực hiện các nhiệm vụ:

1. Kiểm thử parser bằng ShellTestClient với đường dẫn đơn giản.
2. Kiểm thử đường dẫn có khoảng trắng.
3. Kiểm thử tên file chứa tiếng Việt.
4. Kiểm thử cả --format=json và --format json.
5. Khởi động ứng dụng từ PowerShell và nhập command trong prompt.
6. Khởi động ứng dụng từ cmd.exe và lặp lại ca kiểm tra.
7. Khởi động ứng dụng từ Bash và lặp lại ca kiểm tra.
8. Chạy một file script Spring Shell có nhiều command.
9. Chạy trên một môi trường triển khai thực tế hoặc container.
10. So sánh giá trị đã binding, file đầu ra và thông báo lỗi giữa các môi trường.

Kịch bản mẫu:

~~~text
report export --file "Monthly Reports/sales.csv" --format csv --dry-run false
report export --file "Báo cáo tháng 11.csv" --format json --dry-run true
report export --format=json --file report.json --dry-run false
~~~

Ghi lại hệ điều hành, terminal, phiên bản Java, phiên bản Spring Shell, input, output và kết quả. Nếu một ca chỉ lỗi trong một môi trường, xác định lớp xử lý khác nhau trước khi thay đổi code.

## 18. Checklist trước khi phát hành

- [ ] Đã xác định phiên bản Spring Shell và parser đang sử dụng.
- [ ] Đã kiểm tra cú pháp option dài, option ngắn và thứ tự option.
- [ ] Đã kiểm tra option boolean có giá trị theo quy tắc phiên bản.
- [ ] Đã kiểm tra argument vị trí và named option.
- [ ] Đã kiểm tra giá trị có khoảng trắng, dấu nháy và Unicode.
- [ ] Đã kiểm tra đường dẫn Windows và POSIX trên đúng filesystem.
- [ ] Đã kiểm tra biến môi trường ở lớp OS shell và lớp ứng dụng.
- [ ] Đã kiểm tra ký tự đặc biệt trong PowerShell, cmd.exe hoặc Bash.
- [ ] Đã kiểm tra script Spring Shell và script wrapper của hệ điều hành riêng biệt.
- [ ] Đã kiểm tra line ending và encoding của file script.
- [ ] Đã kiểm tra working directory, quyền truy cập và volume mount.
- [ ] Đã chạy ShellTestClient để xác minh parser và output.
- [ ] Đã chạy smoke test trên các OS/terminal được hỗ trợ.
- [ ] Đã xác minh output, log và mã thoát trong môi trường đích.
- [ ] Đã ghi lại môi trường và các lệnh tái hiện lỗi.

## 19. Kết luận

Kiểm chứng cú pháp Spring Shell trên Windows, Bash và môi trường triển khai cần phân biệt rõ shell hệ điều hành, parser của Spring Shell và môi trường thực thi Java. PowerShell, cmd.exe và Bash có cách quote, mở rộng biến và xử lý ký tự đặc biệt khác nhau. Khi người dùng đã ở prompt Spring Shell, parser của ứng dụng mới là thành phần xử lý dòng command.

Hãy kiểm thử parser bằng ShellTestClient, kiểm tra cách khởi động tiến trình trên từng hệ điều hành, sau đó chạy smoke test với đường dẫn, encoding, quyền truy cập và script thực tế. Cách tiếp cận theo từng lớp giúp tìm đúng nguyên nhân và bảo đảm command hoạt động ổn định ở nơi người dùng sẽ sử dụng.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 Reference: Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.0.3 Reference: Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 API: CommandParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html)
- [Spring Shell 4.0.3 Reference: Script command](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Microsoft Learn: about_Parsing (PowerShell)](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing)
- [Microsoft Learn: about_Quoting_Rules (PowerShell)](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules)
- [Microsoft Learn: cmd command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd)
- [GNU Bash Reference Manual: Quoting](https://www.gnu.org/software/bash/manual/html_node/Quoting.html)
- [GNU Bash Reference Manual: Shell Expansions](https://www.gnu.org/software/bash/manual/html_node/Shell-Expansions.html)

