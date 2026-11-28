# Mã hóa văn bản, đường dẫn và quyền thực thi trên các nền tảng

Một ứng dụng Spring Shell có thể chạy đúng trên máy phát triển nhưng gặp lỗi khi được đóng gói và chuyển sang máy khác. Tiếng Việt hiển thị thành ký tự lỗi, file script không chạy, đường dẫn bị tách ở dấu cách, hoặc launcher hoạt động trên Linux nhưng thất bại trên Windows. Những vấn đề này thường đến từ khác biệt giữa hệ điều hành, terminal, encoding, line ending và quyền file.

Khi phân phối CLI, cần xem văn bản, đường dẫn và quyền thực thi là một phần của hợp đồng triển khai. File cấu hình phải được đọc bằng encoding đã thống nhất; đường dẫn phải được phân tích theo filesystem và shell đang dùng; launcher phải có line ending và quyền chạy phù hợp với nền tảng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Unicode, UTF-8, code page, BOM và line ending.
- Chọn encoding nhất quán cho file cấu hình, dữ liệu và output của ứng dụng Java.
- Hiểu thay đổi default charset từ JDK 17 trở về trước sang JDK 18 trở lên.
- Phân biệt encoding của file với encoding của console và luồng process.
- Xử lý khác biệt encoding giữa Windows PowerShell 5.1 và PowerShell 7+.
- Dùng Path và Files để xây dựng đường dẫn đa nền tảng.
- Truyền đường dẫn có dấu cách và ký tự Unicode an toàn qua shell và ProcessBuilder.
- Nhận biết đường dẫn tương đối, tuyệt đối, UNC, ký tự dành riêng và giới hạn độ dài.
- Thiết lập line ending cho shell script và Windows batch file.
- Quản lý executable bit trên Linux/macOS và metadata file mode trong Git.
- Tạo launcher phù hợp cho Windows, Linux và macOS.
- Kiểm tra artifact sau khi đóng gói, giải nén và chạy trên từng hệ điều hành.

## 1. Ba nhóm vấn đề thường bị nhầm

Khi một CLI đọc file, nhận đối số và in kết quả, có ít nhất ba lớp độc lập:

| Lớp | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Encoding văn bản | UTF-8, UTF-16LE, Windows-1258 | Những byte trong file hoặc stream được giải mã thành ký tự nào? |
| Đường dẫn và đối số | C:\Tools\Support CLI\config.yml, /opt/support/config.yml | Hệ điều hành và shell phân tích tên file/argument ra sao? |
| Quyền và cách khởi chạy | chmod +x, .cmd, .ps1, java -jar | Ai có thể đọc/chạy file và chương trình nào thực thi nó? |

Một file UTF-8 vẫn có thể không chạy nếu shell không hiểu launcher. Một đường dẫn hợp lệ vẫn có thể bị chia thành nhiều đối số nếu thiếu dấu nháy. Một script có nội dung đúng vẫn có thể bị từ chối vì thiếu execute permission hoặc bị chính sách PowerShell chặn.

Vì vậy, khi điều tra lỗi phân phối, hãy xác định lỗi thuộc lớp nào trước khi thay đổi cấu hình hệ thống.

## 2. Unicode và UTF-8

Unicode là chuẩn biểu diễn ký tự. UTF-8 là một cách mã hóa các điểm mã Unicode thành byte. Cùng một chuỗi tiếng Việt có thể được biểu diễn bằng các byte UTF-8; nếu một chương trình giải mã các byte đó bằng code page khác, nội dung có thể biến thành mojibake, tức chuỗi ký tự sai.

Ví dụ, file cấu hình:

~~~yaml
application:
  name: Công cụ quản trị khách hàng
  welcome-message: Xin chào, Nguyễn Văn An!
~~~

Nếu file được lưu bằng UTF-8 nhưng chương trình đọc theo Windows-1258 hoặc một code page khác, dấu tiếng Việt có thể bị sai. Ngược lại, nếu file thực tế được lưu theo encoding cũ nhưng chương trình luôn giả định UTF-8, việc giải mã cũng có thể thất bại.

Đối với artifact cấu hình và dữ liệu dùng chung giữa Windows, Linux và macOS, nên thống nhất UTF-8 trừ khi một định dạng hoặc hệ thống tích hợp yêu cầu encoding khác. Ghi encoding vào tài liệu phân phối để người tạo file và người đọc file sử dụng cùng quy ước.

### 2.1. BOM là gì?

Byte Order Mark (BOM) là một dấu hiệu ở đầu file có thể giúp nhận biết encoding hoặc byte order. UTF-8 không cần BOM để xác định byte order. Nhiều công cụ Unix và một số parser không mong đợi BOM ở đầu file, đặc biệt khi file bắt đầu bằng một cú pháp có ý nghĩa như shebang.

Quy tắc thực tế:

- File JSON, YAML, CSV, properties và dữ liệu cấu hình dùng chung: ưu tiên UTF-8 không BOM nếu định dạng/consumer không yêu cầu khác.
- Shell script có shebang: không đặt BOM trước ký tự #!; shebang phải ở đầu file.
- PowerShell script cần hỗ trợ Windows PowerShell 5.1 và có ký tự ngoài ASCII: dùng UTF-8 có BOM để PowerShell 5.1 nhận diện đúng encoding nguồn.
- PowerShell 7+ đọc và ghi UTF-8 không BOM theo mặc định ở các phiên bản hiện đại; vẫn nên quy định encoding rõ trong quy trình tạo file.

Không chọn BOM chỉ vì một editor hiển thị tiếng Việt đúng. Hãy kiểm tra consumer cuối cùng sẽ đọc file.

## 3. Default charset của Java thay đổi từ JDK 18

Trước JDK 18, default charset của Java phụ thuộc môi trường và cấu hình hệ điều hành. Trên Windows, nó thường là một code page theo locale; trên macOS và Linux thường là UTF-8, ngoại trừ một số locale đặc biệt.

Từ JDK 18, theo JEP 400, UTF-8 trở thành default charset của các Java SE API trên mọi hệ điều hành. Điều này giúp hành vi đọc/ghi dựa trên default charset nhất quán hơn, nhưng không có nghĩa mọi luồng I/O đều dùng cùng một encoding.

| Nền tảng Java | Default charset |
|---|---|
| JDK 17 và cũ hơn | Phụ thuộc môi trường, locale và cấu hình |
| JDK 18 trở lên | UTF-8 theo mặc định |

Kiểm tra cấu hình runtime:

~~~bash
java -XshowSettings:properties -version
~~~

Tìm thuộc tính file.encoding trong phần output. Trên Windows có thể lọc bằng findstr; trên Linux/macOS có thể lọc bằng grep.

Không nên dựa vào default charset cho file nghiệp vụ quan trọng. Hãy chỉ rõ charset trong code để ứng dụng hoạt động ổn định trên các JDK và môi trường khác nhau.

Tài liệu Oracle: [JDK 18 Release Notes — JEP 400](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html), [Supported Encodings](https://docs.oracle.com/en/java/javase/18/intl/supported-encodings.html).

## 4. Chỉ định encoding tường minh trong Java

Các API tiện dụng như FileReader, FileWriter, InputStreamReader hoặc PrintStream có thể dùng default charset nếu không chỉ định encoding. Với file dữ liệu, nên truyền StandardCharsets.UTF_8 một cách tường minh.

Đọc file:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public List<String> readLines(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines().toList();
    }
}
~~~

Ghi file:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public void writeReport(Path path, String report) throws IOException {
    try (BufferedWriter writer =
            Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
        writer.write(report);
    }
}
~~~

Với JDK 11 trở lên, Files.readString(Path) và Files.writeString(Path, CharSequence) mặc định dùng UTF-8. Khi muốn thể hiện hợp đồng encoding rõ ràng, có thể dùng overload nhận Charset:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Khi làm việc với byte array:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Không chuyển byte sang String bằng constructor không có charset nếu dữ liệu đến từ một file hoặc hệ thống có encoding đã biết.

### 4.1. Encoding của file khác encoding của console

Một điểm quan trọng: default charset của Java không nhất thiết là encoding dùng cho console. Java documentation nêu System.out và System.err sử dụng charset của console khi có console, thông qua Console.charset() ở các runtime hỗ trợ API đó.

Vì vậy, các trường hợp sau có thể xảy ra:

- File UTF-8 được đọc đúng nhưng terminal hiển thị tiếng Việt sai.
- Terminal hiển thị đúng nhưng file export bị sai do writer dùng encoding khác.
- Output chuyển hướng vào file có encoding khác với output hiển thị trực tiếp.
- Java process nhận dữ liệu qua pipe từ một chương trình có code page khác.

Khi command Spring Shell in tiếng Việt, cần kiểm tra cả chuỗi Java, writer của shell, terminal emulator và cách output được chuyển hướng. Đừng sửa encoding file chỉ vì terminal đang dùng font hoặc code page không phù hợp.

## 5. Encoding của Windows PowerShell và PowerShell 7

PowerShell có khác biệt đáng kể giữa Windows PowerShell 5.1 và PowerShell 6+/7+.

| Môi trường | Hành vi thường gặp |
|---|---|
| Windows PowerShell 5.1 | Encoding mặc định của nhiều cmdlet không đồng nhất; script không có BOM có thể được đọc theo ANSI code page |
| PowerShell 6+ | UTF-8 không BOM là mặc định cho nhiều thao tác text |
| PowerShell 7.1+ | Có các tên encoding rõ ràng như utf8, utf8NoBOM và utf8BOM |

Windows PowerShell 5.1 có thể hiểu sai script UTF-8 không BOM nếu nội dung chứa ký tự ngoài ASCII. Khi cần hỗ trợ 5.1, lưu script PowerShell bằng UTF-8 có BOM. Với file dữ liệu dùng chung cho Java/Linux/macOS, tiếp tục dùng UTF-8 không BOM theo hợp đồng dữ liệu; không biến mọi file trong dự án thành UTF-8 BOM chỉ để chiều một parser PowerShell cũ.

Ví dụ đọc và ghi file với PowerShell 7:

~~~powershell
$content = Get-Content -LiteralPath '.\config.yml' -Raw -Encoding utf8
Set-Content -LiteralPath '.\report.txt' -Value $content -Encoding utf8
~~~

Ví dụ tương thích Windows PowerShell 5.1 khi ghi file UTF-8 có BOM:

~~~powershell
Set-Content -LiteralPath '.\script.ps1' -Value $scriptText -Encoding utf8
~~~

Trong PowerShell 5.1, giá trị utf8 của cmdlet tạo UTF-8 có BOM. Trong PowerShell 7+, utf8 thường là UTF-8 không BOM; nếu cần kiểm soát rõ, dùng utf8BOM hoặc utf8NoBOM theo phiên bản.

Lưu ý thêm:

- Trong Windows PowerShell 5.1, Out-File và toán tử chuyển hướng > thường tạo UTF-16LE.
- Set-Content/Add-Content với file mới có thể dùng ANSI code page nếu không chỉ định encoding.
- Trong PowerShell 7+, output text mặc định thường là UTF-8 không BOM.
- Encoding của file output khác với encoding dùng khi PowerShell giao tiếp qua pipe với chương trình native; biến $OutputEncoding điều khiển một phần luồng này.

Tài liệu Microsoft: [about_Character_Encoding — PowerShell 5.1](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1), [about_Character_Encoding — PowerShell 7](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-7).

## 6. Encoding của terminal và output được chuyển hướng

Terminal emulator, shell và chương trình native có thể dùng các quy ước encoding khác nhau. Việc đổi code page của terminal không sửa byte của file cấu hình và cũng không tự sửa encoding mà Java dùng khi đọc file.

Khi tiếng Việt hiển thị sai, hãy kiểm tra theo thứ tự:

1. Chuỗi gốc trong file hoặc database có đúng không?
2. Java đọc nguồn bằng charset nào?
3. Chuỗi Java có đúng trước khi ghi ra output không?
4. Shell/terminal đang nhận và giải mã output theo encoding nào?
5. Font terminal có glyph cho các ký tự cần hiển thị không?
6. Nếu redirect output ra file, consumer của file đó mong đợi encoding nào?

Trên Windows, lệnh chcp có thể hiển thị hoặc đổi active console code page trong cmd.exe. Đây là công cụ chẩn đoán môi trường console, không phải cách thay thế việc chỉ định UTF-8 cho file I/O. Tránh đưa lệnh đổi code page toàn cục vào launcher nếu chưa xác nhận nó phù hợp với mọi chương trình mà launcher gọi.

## 7. Line ending: LF và CRLF

Line ending là chuỗi byte đánh dấu kết thúc một dòng:

| Kiểu | Byte | Nền tảng thường gặp |
|---|---|---|
| LF | \n | Linux, macOS, Unix |
| CRLF | \r\n | Windows |

Hầu hết editor hiện đại có thể đọc cả hai kiểu. Tuy nhiên, script và công cụ dòng lệnh có thể nhạy với line ending.

Shell script nên dùng LF. Nếu dòng đầu có shebang nhưng file dùng CRLF, một số môi trường Unix có thể đọc ký tự CR như một phần của tên interpreter và báo lỗi dạng /bin/bash^M: bad interpreter.

Windows batch file (.bat, .cmd) thường nên dùng CRLF để tương thích với các công cụ Windows cũ. PowerShell hỗ trợ line ending hiện đại, nhưng nên thống nhất quy ước trong repository.

## 8. Chuẩn hóa line ending bằng Git

Git có thể chuẩn hóa line ending trong repository và chuyển đổi khi checkout. Dùng file .gitattributes để quy định rõ từng loại script:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.bash text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
~~~

Ví dụ trên yêu cầu shell script dùng LF và batch file dùng CRLF trong working tree. Git chuẩn hóa nội dung text trong index theo quy tắc của gitattributes.

Một số khái niệm:

- text: Git xem file là văn bản và áp dụng chuyển đổi line ending.
- text=auto: Git tự nhận diện file văn bản để chuẩn hóa.
- eol=lf: checkout file với LF.
- eol=crlf: checkout file với CRLF.
- -text hoặc binary: không áp dụng chuyển đổi text.

Không dùng core.autocrlf như cách duy nhất để xử lý mọi loại file trong dự án đa nền tảng. Thuộc tính theo phần mở rộng giúp shell script và batch file có quy tắc riêng.

Ví dụ kiểm tra thay đổi line ending:

~~~bash
git diff --check
git config --get core.autocrlf
~~~

Tài liệu Git: [gitattributes — End-of-line conversion](https://git-scm.com/docs/gitattributes.html), [Git FAQ — Line endings](https://git-scm.com/docs/gitfaq).

## 9. Đường dẫn tuyệt đối và tương đối

Đường dẫn tuyệt đối bắt đầu từ root hoặc volume. Đường dẫn tương đối được phân giải dựa trên thư mục làm việc hiện tại của process.

Ví dụ:

| Hệ điều hành | Đường dẫn tuyệt đối | Đường dẫn tương đối |
|---|---|---|
| Windows | C:\Apps\Support\config.yml | config\config.yml |
| Linux | /opt/support/config.yml | config/config.yml |
| macOS | /Applications/Support/config.yml | config/config.yml |

Trong Java, đường dẫn tương đối được phân giải từ working directory của process, thường tương ứng với system property user.dir. Nó không tự động tương đối với thư mục chứa JAR hoặc thư mục chứa class.

Điều này ảnh hưởng trực tiếp đến CLI. Hai cách khởi chạy sau có thể cho kết quả khác nếu command dùng đường dẫn tương đối:

~~~bash
cd /opt/support
java -jar support-cli.jar report export --output reports/daily.csv
~~~

~~~bash
cd /tmp
java -jar /opt/support/support-cli.jar report export --output reports/daily.csv
~~~

Trong trường hợp thứ hai, reports/daily.csv được phân giải theo /tmp nếu ứng dụng dùng working directory mặc định. Nếu muốn output luôn nằm cạnh ứng dụng, hãy xác định app home rõ ràng trong launcher hoặc cấu hình.

## 10. Dùng Path thay vì nối chuỗi đường dẫn

Không nên tự nối chuỗi bằng dấu slash hoặc backslash:

~~~java
// Không nên: phụ thuộc separator và dễ tạo đường dẫn sai.
String config = baseDirectory + "\\" + "config" + "\\" + "app.yml";
~~~

Dùng Path và resolve:

~~~java
import java.nio.file.Path;
import java.nio.file.Paths;

Path baseDirectory = Paths.get("config");
Path configFile = baseDirectory.resolve("app.yml");
~~~

Khi cần đường dẫn tuyệt đối và chuẩn hóa các thành phần . hoặc ..:

~~~java
Path output = Paths.get(userInput)
        .toAbsolutePath()
        .normalize();
~~~

Path sử dụng provider của filesystem hiện tại, vì vậy Java tự chọn cách biểu diễn separator phù hợp. Dùng Path.resolve để ghép thành phần đường dẫn và Files để đọc/ghi.

Không giả định một chuỗi đường dẫn Windows như C:\data\file.csv có thể được phân giải như đường dẫn Windows khi ứng dụng chạy trên Linux. Path được tạo bởi default filesystem provider của hệ điều hành đang chạy.

## 11. Thư mục làm việc và thư mục ứng dụng

CLI thường cần hai khái niệm:

- **Working directory:** nơi process được khởi chạy; đường dẫn tương đối của người dùng thường được tính từ đây.
- **Application home:** thư mục chứa JAR, launcher hoặc cấu hình phân phối.

Không đồng nhất hai khái niệm. Người dùng có thể chạy launcher từ một thư mục bất kỳ trong PATH.

Với shell script, có thể xác định thư mục chứa script:

~~~bash
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_JAR="$SCRIPT_DIR/support-cli.jar"
exec java -jar "$APP_JAR" "$@"
~~~

Với Windows batch:

~~~bat
@echo off
setlocal
set "APP_HOME=%~dp0"
java -jar "%APP_HOME%support-cli.jar" %*
exit /b %ERRORLEVEL%
~~~

Với PowerShell, biến $PSScriptRoot cho biết thư mục chứa script:

~~~powershell
$jarPath = Join-Path $PSScriptRoot 'support-cli.jar'
& java -jar $jarPath @args
exit $LASTEXITCODE
~~~

Các launcher trên minh họa cách tìm JAR tương đối với vị trí script. Nếu cần cho phép người dùng chỉ định working directory hoặc thư mục output, hãy mô tả riêng option đó.

## 12. Dấu cách và ký tự Unicode trong đường dẫn

Tên thư mục có thể chứa dấu cách hoặc ký tự Unicode. Khi nhập đường dẫn ở shell, cần đặt dấu nháy để toàn bộ đường dẫn được truyền thành một argument.

PowerShell:

~~~powershell
& 'C:\Program Files\Java\bin\java.exe' -jar 'C:\Tools\Support CLI\support-cli.jar' report export --output 'C:\Reports Tháng 11\daily report.csv'
~~~

Bash:

~~~bash
java -jar "$HOME/tools/Support CLI/support-cli.jar" report export --output "$HOME/reports/Tháng 11/daily report.csv"
~~~

Không đặt dấu nháy vào chính tên file hoặc lưu dấu nháy thành một phần của đường dẫn. Dấu nháy là cú pháp của shell để gom argument, không phải ký tự đường dẫn.

### 12.1. Khi gọi process từ Java

Nếu ứng dụng khởi chạy một chương trình con bằng ProcessBuilder, truyền executable và từng argument thành các phần tử riêng:

~~~java
Path jar = Paths.get("C:/Tools/Support CLI/support-cli.jar");
Path output = Paths.get("C:/Reports Tháng 11/daily report.csv");

ProcessBuilder builder = new ProcessBuilder(
        "java",
        "-jar",
        jar.toString(),
        "report",
        "export",
        "--output",
        output.toString());

Process process = builder.start();
~~~

Không tự ghép thành một chuỗi command rồi thêm dấu nháy theo phỏng đoán. ProcessBuilder nhận danh sách executable và arguments; mỗi argument có khoảng trắng vẫn là một phần tử riêng.

Nếu thật sự cần chạy qua cmd.exe, PowerShell hoặc Bash để dùng cú pháp shell, khi đó phải escape theo đúng shell được gọi. Cú pháp quoting của Bash không thể dùng nguyên xi trong PowerShell hoặc cmd.exe.

Tài liệu Java: [ProcessBuilder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html).

## 13. UNC path và các giới hạn tên file trên Windows

Windows hỗ trợ đường dẫn ổ đĩa và UNC:

~~~text
C:\Apps\Support\config.yml
\\fileserver\shared\Support\config.yml
~~~

UNC path bắt đầu bằng hai dấu backslash, tiếp theo là server và share. Khi phân phối CLI trong mạng nội bộ, không giả định đường dẫn share sẽ tồn tại hoặc tài khoản chạy process có quyền đọc/ghi.

Một số khác biệt Windows cần lưu ý:

- Ký tự tên file không được chứa: < > : " / \ | ? *.
- Tên thiết bị như CON, PRN, AUX, NUL, COM1 và LPT1 có quy tắc dành riêng.
- Hệ thống thường không phân biệt chữ hoa/chữ thường trong tên file theo mặc định, dù NTFS có hỗ trợ cấu hình case-sensitive trong một số thư mục.
- Đường dẫn dài có thể gặp giới hạn MAX_PATH khoảng 260 ký tự ở các API hoặc ứng dụng chưa hỗ trợ long path.
- Dấu cách trong đường dẫn phải được quote khi truyền qua command line.

Để tăng tính di động, ưu tiên tên file ngắn, tránh ký tự đặc biệt và không dựa vào phân biệt hoa/thường. Nếu sản phẩm phải xử lý tên file do người dùng cung cấp, hãy validate theo quy tắc của hệ điều hành đích.

Tài liệu Microsoft: [Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file), [Maximum Path Length Limitation](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).

## 14. Chuẩn hóa đường dẫn và chống path traversal

Nếu command nhận tên file do người dùng nhập và chỉ cho phép truy cập bên trong một thư mục gốc, không chỉ nối chuỗi rồi mở file. Người dùng có thể truyền thành phần .. để đi lên thư mục cha.

Ví dụ:

~~~java
Path base = Paths.get("/var/lib/support/uploads")
        .toAbsolutePath()
        .normalize();

Path requested = base.resolve(userSuppliedName).normalize();

if (!requested.startsWith(base)) {
    throw new IllegalArgumentException("Path is outside the allowed directory");
}
~~~

Kiểm tra startsWith sau normalize giúp ngăn đường dẫn lexical thoát khỏi thư mục gốc. Tuy nhiên, normalize không giải quyết symbolic link. Một file hoặc thư mục bên trong base có thể là symlink trỏ ra ngoài.

Nếu ranh giới thư mục là yêu cầu bảo mật:

- Xác định rõ thư mục gốc được phép.
- Dùng toRealPath khi file tồn tại để giải quyết symlink và so sánh đường dẫn thực.
- Với file chưa tồn tại, kiểm tra parent directory thực và hạn chế quyền tạo symlink.
- Dùng API thao tác file an toàn theo provider nếu ứng dụng cần chống race condition.
- Kiểm tra quyền đọc/ghi ở thời điểm thực hiện, không chỉ lúc parse input.

Đừng coi việc normalize chuỗi là một cơ chế phân quyền hoàn chỉnh.

## 15. Shebang và shell script trên Linux/macOS

Shebang là dòng đầu của script, bắt đầu bằng hai ký tự #! và chỉ định interpreter. Ví dụ:

~~~bash
#!/usr/bin/env bash

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_JAR="$SCRIPT_DIR/support-cli.jar"

exec java -jar "$APP_JAR" "$@"
~~~

Khi người dùng chạy:

~~~bash
./support-cli
~~~

hệ điều hành dùng interpreter trong shebang để thực thi script. Đường dẫn interpreter nên tồn tại trên máy đích; /usr/bin/env bash giúp tìm bash thông qua PATH.

Các quy tắc:

- Shebang phải nằm ở byte đầu tiên của file.
- Không đặt UTF-8 BOM trước #!.
- Dùng LF line ending.
- Truyền lại arguments bằng "$@" để giữ từng argument, kể cả khi có dấu cách.
- Dùng exec để process Java thay thế process shell wrapper, giúp tín hiệu và exit status được truyền tự nhiên hơn.

Nếu script có thể chạy trong nhiều shell, hãy chọn cú pháp phù hợp với interpreter khai báo. Script dùng cú pháp Bash không nên khai báo /bin/sh nếu không bảo đảm shell đó là Bash.

## 16. Executable permission trên POSIX

Linux và macOS sử dụng permission bit để quyết định ai có thể đọc, ghi và thực thi file. Với shell launcher, file cần execute permission nếu người dùng chạy trực tiếp bằng đường dẫn:

~~~bash
chmod +x bin/support-cli
./bin/support-cli
~~~

Một file script có thể đọc được nhưng không chạy trực tiếp nếu thiếu execute bit. Người dùng vẫn có thể truyền file cho interpreter:

~~~bash
bash bin/support-cli
~~~

Trong trường hợp này, bash đọc file nên execute bit của chính file script không cần thiết, nhưng người dùng vẫn phải có quyền đọc file và quyền truy cập các thư mục cha.

Một số mode thường gặp:

| Mode | Ý nghĩa tổng quát |
|---|---|
| 644 | Chủ sở hữu đọc/ghi; group và others đọc |
| 755 | Chủ sở hữu đọc/ghi/thực thi; group và others đọc/thực thi |
| 700 | Chỉ chủ sở hữu đọc/ghi/thực thi |

Với launcher phân phối công khai, mode 755 thường được dùng để mọi người dùng có thể chạy. Với script chứa cấu hình nhạy cảm, không áp dụng 755 một cách máy móc; quyền file phải theo chính sách dữ liệu.

Kiểm tra:

~~~bash
ls -l bin/support-cli
test -x bin/support-cli
~~~

Execute bit trên thư mục có ý nghĩa cho phép traverse/đi vào thư mục. Không thay đổi permission đệ quy toàn bộ thư mục chỉ để sửa một launcher.

## 17. Git lưu executable bit như thế nào?

Git không lưu toàn bộ permission POSIX của file thường. Với file thường, Git chủ yếu ghi nhận hai mode:

| Git mode | Ý nghĩa |
|---|---|
| 100644 | File thường không executable |
| 100755 | File thường executable |

Để đánh dấu launcher executable:

~~~bash
chmod +x bin/support-cli
git add bin/support-cli
git ls-files --stage bin/support-cli
~~~

Kết quả trong index cần có mode 100755. Có thể kiểm tra thay đổi mode bằng:

~~~bash
git diff --summary
~~~

Trên filesystem không biểu diễn executable bit, hoặc khi repository được dùng qua một môi trường tương thích Windows, Git có thể đặt core.fileMode=false và bỏ qua thay đổi mode trong working tree. Khi cần ghi nhận mode trong index, có thể dùng:

~~~bash
git update-index --chmod=+x bin/support-cli
git ls-files --stage bin/support-cli
~~~

Chỉ dùng lệnh trên cho file thực sự phải executable. Không đổi core.fileMode toàn cục chỉ để che một khác biệt permission mà chưa hiểu nguyên nhân.

Tài liệu Git: [core.fileMode](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefileMode), [Git User Manual — Tree Object](https://git-scm.com/docs/user-manual.html).

## 18. Windows không dùng executable bit theo cách POSIX

Windows không dùng execute bit của file thường như Linux/macOS. Việc khởi chạy phụ thuộc vào loại file, phần mở rộng, file association, command interpreter và chính sách hệ thống.

Các kiểu launcher phổ biến:

| File | Cách chạy |
|---|---|
| .exe | Chạy executable trực tiếp |
| .cmd / .bat | Chạy qua Command Prompt |
| .ps1 | Chạy trong PowerShell |
| .jar | Gọi qua java -jar, trừ khi đã có launcher riêng |

PowerShell có Execution Policy điều khiển điều kiện chạy script. Chính sách có thể được đặt theo process, user, machine hoặc Group Policy. Execution Policy là một lớp kiểm soát vận hành, không phải security boundary; không hướng dẫn người dùng tắt chính sách toàn máy chỉ để launcher chạy được.

Khi phân phối script PowerShell cho tổ chức, cần tuân theo chính sách quản trị, chữ ký script và quy trình phát hành của môi trường đích. Nếu script bị chặn, kiểm tra policy đang có hiệu lực và yêu cầu quản trị viên cung cấp cách triển khai phù hợp.

Tài liệu Microsoft: [about_Execution_Policies](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies).

## 19. Thiết kế launcher cho từng nền tảng

Không nên phát hành một shell script rồi kỳ vọng Windows thực thi như Bash. Một gói CLI đa nền tảng thường có thể cung cấp:

~~~text
support-cli/
  support-cli.jar
  bin/
    support-cli
    support-cli.cmd
    support-cli.ps1
  config/
    application.yml
  README.txt
~~~

Launcher POSIX:

~~~bash
#!/usr/bin/env bash
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec java -jar "$SCRIPT_DIR/../support-cli.jar" "$@"
~~~

Launcher Windows CMD:

~~~bat
@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
java -jar "%SCRIPT_DIR%..\support-cli.jar" %*
exit /b %ERRORLEVEL%
~~~

Launcher PowerShell:

~~~powershell
$scriptDir = $PSScriptRoot
$jarPath = Join-Path $scriptDir '..\support-cli.jar'
& java -jar $jarPath @args
exit $LASTEXITCODE
~~~

Các ví dụ giả định JAR nằm ở thư mục cha của bin. Nếu layout package khác, cập nhật đường dẫn tương ứng và kiểm tra bằng cách chạy từ một working directory khác.

JAR không cần execute bit khi được gọi bằng java -jar. Execute bit cần thiết cho shell wrapper nếu người dùng chạy trực tiếp ./bin/support-cli.

## 20. Truyền arguments và giữ exit status qua launcher

Launcher cần giữ nguyên từng argument và trả lại exit status của Java process.

Trong Bash, "$@" giữ ranh giới giữa các argument. Không thay bằng $* nếu có thể có giá trị chứa khoảng trắng.

Trong batch file, %* chuyển tiếp phần arguments còn lại; người dùng cần quote giá trị có khoảng trắng tại lệnh gọi.

Trong PowerShell, splatting @args chuyển các argument còn lại tới chương trình native. $LASTEXITCODE chứa exit code của chương trình native gần nhất.

Ví dụ Bash:

~~~bash
exec java -jar "$APP_JAR" "$@"
~~~

Ví dụ CMD:

~~~bat
java -jar "%APP_JAR%" %*
exit /b %ERRORLEVEL%
~~~

Ví dụ PowerShell:

~~~powershell
& java -jar $jarPath @args
exit $LASTEXITCODE
~~~

Nếu wrapper luôn trả 0 hoặc bỏ qua exit code, scheduler và CI có thể đánh giá một lần chạy thất bại thành thành công. Hãy kiểm tra cả output lẫn exit status của launcher.

## 21. Đóng gói và giải nén có thể làm mất metadata

Artifact ZIP, TAR, package manager hoặc hệ thống lưu trữ có thể xử lý permission và line ending khác nhau. Không giả định mọi công cụ giải nén đều khôi phục executable bit theo cùng cách.

Đối với TAR trên POSIX, metadata mode thường được lưu cùng entry. Với ZIP, Unix file attributes có thể được lưu nhưng một số công cụ giải nén hoặc filesystem đích không khôi phục như mong đợi. Trên Windows, execute bit POSIX không có cùng ý nghĩa.

Sau khi tạo artifact:

1. Giải nén vào thư mục mới, không dùng working tree hiện tại.
2. Kiểm tra nội dung launcher và line ending.
3. Kiểm tra execute permission trên Linux/macOS.
4. Chạy launcher từ thư mục khác.
5. Kiểm tra đường dẫn có dấu cách và ký tự Unicode.
6. Kiểm tra output UTF-8 và exit status.
7. Xác nhận file JAR và file cấu hình nằm đúng vị trí tương đối.

Nếu gói ZIP không giữ executable bit, tài liệu cài đặt cần nêu lệnh chmod phù hợp hoặc hướng dẫn chạy qua interpreter. Với package manager, khai báo permission trong metadata package theo chuẩn của hệ sinh thái đó.

## 22. Một số cấu hình Git hữu ích cho repository đa nền tảng

Có thể kết hợp .gitattributes để chuẩn hóa text và line ending:

~~~gitattributes
* text=auto

*.sh text eol=lf
*.bash text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf

*.jar binary
*.zip binary
*.png binary
~~~

Đặt file script POSIX executable trong Git:

~~~bash
git update-index --chmod=+x bin/support-cli
git ls-files --stage bin/support-cli
~~~

Không đánh dấu JAR, ZIP hoặc file nhị phân là text. Git không nên chuyển đổi line ending trong file nhị phân.

Nếu thay đổi quy tắc line ending cho repository đã tồn tại, không chạy renormalize hàng loạt mà chưa xem diff. Hãy xác định file nào thực sự cần chuẩn hóa, kiểm tra working tree và phối hợp commit riêng để reviewer dễ đánh giá.

## 23. Kiểm thử encoding, path và permission trong CI

Một pipeline đa nền tảng nên có ma trận kiểm thử tối thiểu cho Windows, Linux và macOS nếu sản phẩm tuyên bố hỗ trợ cả ba.

| Nhóm kiểm thử | Windows | Linux | macOS |
|---|---|---|---|
| Đọc file UTF-8 có tiếng Việt | PowerShell/cmd và Java | Java | Java |
| Ghi file UTF-8 rồi đọc lại | Kiểm tra byte và nội dung | Kiểm tra byte và nội dung | Kiểm tra byte và nội dung |
| Đường dẫn có dấu cách | C:\Tools\Support CLI | /opt/Support CLI | /Applications/Support CLI |
| Đường dẫn Unicode | Tên thư mục tiếng Việt | Tên thư mục tiếng Việt | Tên thư mục tiếng Việt |
| Relative path | Chạy từ working directory khác | Chạy từ working directory khác | Chạy từ working directory khác |
| Launcher | .cmd/.ps1 | shell script | shell script |
| Execute permission | Kiểm tra loại launcher/policy | Kiểm tra mode 100755 và chmod | Kiểm tra mode 100755 và chmod |
| Line ending | CRLF cho batch | LF cho shell | LF cho shell |
| Exit status | Kiểm tra %ERRORLEVEL%/$LASTEXITCODE | Kiểm tra $? | Kiểm tra $? |

### 23.1. Test round-trip encoding

Tạo file có các ký tự ASCII, tiếng Việt có dấu và một số ký tự Unicode khác. Ghi bằng UTF-8, đọc lại bằng UTF-8 và so sánh chuỗi chính xác:

~~~java
String expected = "Xin chào, Nguyễn Văn An — 東京";
Files.writeString(path, expected, StandardCharsets.UTF_8);

String actual = Files.readString(path, StandardCharsets.UTF_8);
assertThat(actual).isEqualTo(expected);
~~~

Nếu ứng dụng hỗ trợ nhiều định dạng import/export, tạo fixture riêng cho từng định dạng và xác nhận consumer đọc được file.

### 23.2. Test path có khoảng trắng

Tạo thư mục test có tên chứa dấu cách và ký tự Unicode. Chạy launcher với output path nằm trong thư mục đó. Xác nhận chỉ tạo đúng một file, tên file không chứa dấu nháy và nội dung đọc lại được.

### 23.3. Test launcher từ thư mục khác

Không chỉ chạy launcher từ thư mục chứa nó. Chuyển working directory sang một thư mục khác rồi gọi launcher bằng đường dẫn tuyệt đối. Điều này phát hiện lỗi do wrapper giả định user.dir luôn bằng app home.

### 23.4. Test sau khi giải nén artifact

CI cần kiểm tra artifact thực sự được tạo, giải nén vào thư mục sạch và chạy launcher từ đó. Test trực tiếp trong build directory không phát hiện lỗi permission hoặc line ending bị thay đổi trong quá trình đóng gói.

## 24. Các lỗi thường gặp và cách chẩn đoán

### Tiếng Việt bị lỗi dấu trong output

Kiểm tra chuỗi gốc, encoding khi đọc file, encoding của output stream, code page/terminal và font. Phân biệt file output với output hiển thị trực tiếp.

### File cấu hình đọc được trên JDK 21 nhưng sai trên JDK 17

Kiểm tra code có phụ thuộc default charset hay không. JDK 18 trở lên mặc định UTF-8; JDK 17 và cũ hơn phụ thuộc môi trường. Dùng StandardCharsets.UTF_8 cho file có hợp đồng UTF-8.

### PowerShell 5.1 đọc script tiếng Việt sai

Kiểm tra file script có BOM không. Windows PowerShell 5.1 có thể diễn giải script không BOM theo ANSI code page. Nếu cần hỗ trợ 5.1, lưu script UTF-8 có BOM; giữ file dữ liệu dùng chung theo encoding được định nghĩa riêng.

### Shell báo bad interpreter hoặc /bin/bash^M

Kiểm tra shebang có ở byte đầu tiên không, file có BOM không và line ending có phải CRLF không. Dùng UTF-8 không BOM và LF cho shell script.

### Launcher báo permission denied

Trên POSIX, kiểm tra execute bit, quyền thư mục cha, mount option và quyền người dùng. Xác nhận Git index ghi mode 100755 nếu launcher được phân phối qua Git.

### Launcher chạy trên Windows nhưng không chạy trên Linux

Kiểm tra file có phải .cmd/.bat hay shell script, shebang, line ending, execute permission và lệnh interpreter. Cung cấp launcher riêng theo nền tảng.

### Đường dẫn có dấu cách bị chia thành nhiều argument

Quote đường dẫn khi gọi từ shell. Khi dùng ProcessBuilder, truyền đường dẫn thành một phần tử riêng trong danh sách arguments; không tự ghép chuỗi command.

### Đường dẫn tương đối ghi file vào vị trí bất ngờ

Kiểm tra working directory của process. Nếu cần đường dẫn tương đối với app home, resolve từ vị trí launcher hoặc cấu hình application home rõ ràng.

### File không tìm thấy trên Windows nhưng có trên Linux

Kiểm tra chữ hoa/chữ thường, dấu phân cách, tên dành riêng, ổ đĩa hiện hành và UNC path. Đừng dựa vào hành vi case-insensitive của Windows nếu ứng dụng phải chạy trên filesystem phân biệt hoa/thường.

### File không tìm thấy khi đường dẫn quá dài

Kiểm tra giới hạn MAX_PATH và hỗ trợ long path của Windows API, runtime và công cụ đóng gói. Giảm độ sâu thư mục hoặc tên file khi có thể; xác nhận cấu hình long path trên môi trường đích nếu cần.

## 25. Checklist trước khi phân phối CLI

- [ ] Encoding file cấu hình và dữ liệu được quy định rõ, ưu tiên UTF-8.
- [ ] Java đọc/ghi file bằng charset tường minh.
- [ ] Đã kiểm tra khác biệt default charset giữa JDK 17 và JDK 18+.
- [ ] Đã phân biệt encoding file, console và pipe/process.
- [ ] Đã kiểm thử tiếng Việt trên terminal của từng nền tảng hỗ trợ.
- [ ] BOM chỉ được dùng khi consumer yêu cầu; shell script không có BOM.
- [ ] Shell script dùng LF; batch file dùng CRLF theo quy ước repository.
- [ ] .gitattributes quy định line ending cho từng loại launcher.
- [ ] Đường dẫn được xử lý bằng Path/Files thay vì nối chuỗi separator.
- [ ] Đường dẫn có dấu cách và Unicode đã được kiểm thử.
- [ ] Working directory và application home được phân biệt.
- [ ] Đã kiểm tra UNC path, tên file dành riêng và giới hạn độ dài Windows.
- [ ] Input path được validate; path traversal và symlink được xử lý nếu cần.
- [ ] Shell launcher có shebang đúng và executable bit phù hợp.
- [ ] Git index ghi mode 100755 cho launcher POSIX cần chạy trực tiếp.
- [ ] Windows có launcher .cmd/.bat hoặc .ps1 phù hợp.
- [ ] PowerShell Execution Policy được xử lý theo chính sách môi trường.
- [ ] Launcher chuyển tiếp arguments và exit status chính xác.
- [ ] Artifact được giải nén và kiểm thử từ thư mục sạch.
- [ ] CI có kiểm thử Windows, Linux và macOS theo phạm vi hỗ trợ.

## 26. Tự kiểm tra

**Câu 1.** Vì sao JDK 18+ hiển thị file UTF-8 đúng nhưng ứng dụng vẫn có thể in tiếng Việt sai trên terminal?

**Gợi ý trả lời:** Default charset của Java SE API không đồng nhất với encoding của console, pipe và terminal. Cần kiểm tra từng lớp output và font hiển thị.

**Câu 2.** Khi nào nên chỉ định StandardCharsets.UTF_8 trong Java?

**Gợi ý trả lời:** Khi đọc hoặc ghi file có hợp đồng UTF-8, đặc biệt là cấu hình, dữ liệu import/export và file trao đổi giữa các nền tảng.

**Câu 3.** Vì sao shell script không nên có BOM và CRLF?

**Gợi ý trả lời:** BOM làm #! không còn ở byte đầu tiên; CRLF có thể khiến ký tự CR bị xem là một phần của tên interpreter trên môi trường Unix.

**Câu 4.** Tại sao nên dùng Path.resolve thay vì nối chuỗi với dấu backslash?

**Gợi ý trả lời:** Path dùng filesystem provider của nền tảng, tự xử lý separator và giúp code không phụ thuộc quy ước đường dẫn của Windows hoặc Unix.

**Câu 5.** ProcessBuilder xử lý argument có dấu cách như thế nào?

**Gợi ý trả lời:** Truyền executable và từng argument thành phần tử riêng của danh sách; một argument có dấu cách vẫn là một phần tử, không cần tự thêm dấu nháy.

**Câu 6.** Git lưu quyền executable của file thường dưới mode nào?

**Gợi ý trả lời:** 100644 cho file không executable và 100755 cho file executable. Git chủ yếu theo dõi executable bit, không lưu toàn bộ permission POSIX.

**Câu 7.** Vì sao chạy JAR bằng java -jar không cần execute bit?

**Gợi ý trả lời:** Java launcher mở và thực thi JAR như dữ liệu ứng dụng. Execute bit chỉ cần cho shell wrapper được chạy trực tiếp trên POSIX.

**Câu 8.** Vì sao cần kiểm thử artifact sau khi giải nén?

**Gợi ý trả lời:** Quá trình đóng gói/giải nén có thể làm thay đổi line ending, permission hoặc layout. Chạy trong build directory không xác nhận artifact phân phối hoạt động đúng.

## Kết luận

Đóng gói CLI đa nền tảng đòi hỏi kiểm soát đồng thời encoding, đường dẫn, line ending và quyền thực thi. Hãy thống nhất UTF-8 cho file dữ liệu, chỉ định charset tường minh trong Java, kiểm tra riêng encoding của console và lưu ý khác biệt giữa Windows PowerShell 5.1 với PowerShell 7+. Dùng Path để xử lý đường dẫn, quote argument theo shell và truyền argument riêng qua ProcessBuilder.

Với launcher, dùng LF, shebang và executable bit cho Linux/macOS; cung cấp .cmd/.bat hoặc .ps1 cho Windows theo chính sách môi trường. Để Git lưu đúng mode và line ending, khai báo .gitattributes và kiểm tra mode 100755. Cuối cùng, giải nén artifact vào thư mục sạch, chạy từ working directory khác và kiểm thử đường dẫn có dấu cách, ký tự Unicode, output và exit status. Những bước này giúp cùng một ứng dụng Spring Shell được phân phối với hành vi dự đoán được trên các nền tảng hỗ trợ.

## Tài liệu tham khảo

- [Oracle JDK 18 Release Notes — JEP 400: UTF-8 by Default](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html)
- [Oracle — Supported Encodings](https://docs.oracle.com/en/java/javase/18/intl/supported-encodings.html)
- [Java SE — Files API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [Java SE — ProcessBuilder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Microsoft — PowerShell 5.1 Character Encoding](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1)
- [Microsoft — PowerShell 7 Character Encoding](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-7)
- [Microsoft — PowerShell Execution Policies](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies)
- [Microsoft — Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
- [Microsoft — Maximum Path Length Limitation](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)
- [Git — gitattributes](https://git-scm.com/docs/gitattributes.html)
- [Git — core.fileMode](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefileMode)
- [OpenBSD — Interpreter Scripts and Shebang](https://man.openbsd.org/man7/script.7)
