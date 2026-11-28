# Không đọc được console khi chạy trong IDE hoặc môi trường không có TTY

Spring Shell thường chạy như một REPL: hiển thị prompt, nhận dòng lệnh, hỗ trợ lịch sử và tự hoàn thành. Khi chạy trong IDE, Docker, CI hoặc qua một process chuyển tiếp input/output bằng pipe, ứng dụng có thể không đọc được bàn phím, prompt không xuất hiện hoặc phím mũi tên và Tab không hoạt động.

Nguyên nhân thường nằm ở cách tiến trình được khởi chạy và cách môi trường cấp luồng nhập liệu, không nhất thiết ở command Spring Shell. Cần phân biệt console của Java, luồng System.in, terminal TTY và runner mà Spring Shell lựa chọn.

## 1. Phân biệt Console, stdin và TTY

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Dấu hiệu |
| --- | --- | --- |
| Java Console | Thiết bị console trực tiếp mà JVM có thể truy cập | System.console() |
| Standard input | Luồng byte mà ứng dụng đọc dữ liệu | System.in |
| TTY/PTY | Terminal thật hoặc terminal giả lập cung cấp chế độ dòng lệnh tương tác | JLine có thể nhận diện terminal và các khả năng của nó |

System.console() trả về null nếu JVM không có console device trực tiếp. Điều này thường xảy ra khi ứng dụng được chạy tự động hoặc input/output bị redirect. Nhưng null không chứng minh System.in không thể đọc: luồng này vẫn có thể được nối với pipe hoặc file. [Java 17 Console API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html).

TTY cung cấp thêm khả năng điều khiển terminal như xử lý phím, cursor, kích thước cửa sổ, tín hiệu và chế độ nhập. Một IDE có thể cho nhập văn bản vào Console View nhưng không cung cấp đầy đủ các khả năng TTY mà JLine cần.

## 2. Nhận biết đúng triệu chứng

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| System.console() là null | JVM không có console device trực tiếp |
| Gõ lệnh nhưng ứng dụng không nhận | stdin bị đóng, không được nối hoặc đã đến EOF |
| Prompt không xuất hiện | Interactive runner chưa được bật hoặc runner khác đã xử lý application arguments |
| Gõ được nhưng Tab/history/phím mũi tên không hoạt động | JLine đang dùng dumb terminal hoặc IDE không hỗ trợ terminal feature |
| Báo Unable to create a system terminal | JLine không khởi tạo được terminal provider hoặc môi trường không có TTY |
| Chạy từ terminal được nhưng Run/Debug trong IDE không được | Cấu hình IDE chuyển input/output qua internal console hoặc pipe |
| Docker chạy được command một lần nhưng không mở prompt | Container không có TTY hoặc không giữ stdin mở |

Đừng xử lý mọi triệu chứng bằng cách thêm thư viện native cho JLine. Thư viện terminal provider giúp truy cập terminal của hệ điều hành; nó không tự tạo TTY nếu process được chạy trong môi trường không cấp terminal.

## 3. Kiểm tra Java Console và standard input

Tạm thời thêm chẩn đoán sau vào một điểm khởi động của ứng dụng:

```java
import java.io.Console;

public class ConsoleDiagnostics {

    public static void printStatus() {
        Console console = System.console();
        System.err.println("Java console: "
                + (console == null ? "unavailable" : "available"));
        System.err.println("stdin implementation: "
                + System.in.getClass().getName());
        System.err.println("TERM: " + System.getenv("TERM"));
    }
}
```

Kết quả giúp xác định JVM có console trực tiếp và biến môi trường terminal có được truyền vào hay không. Kiểu lớp của System.in chỉ là thông tin chẩn đoán; nó không cho biết chắc chắn người dùng có thể nhập tương tác.

Không dùng System.in.available() để kết luận có TTY hoặc có dữ liệu sắp đến. Phương thức này chỉ báo số byte có thể đọc mà không chặn; giá trị bằng 0 không có nghĩa input bị hỏng. Khi đọc từ terminal, thao tác đọc thường chờ người dùng nhập.

## 4. Kiểm tra JLine có nhận diện terminal hay không

Spring Shell sử dụng JLine cho phần tương tác terminal. Khi tự xây dựng một ứng dụng JLine độc lập, có thể kiểm tra terminal bằng TerminalBuilder:

```java
import java.io.IOException;

import org.jline.terminal.Terminal;
import org.jline.terminal.TerminalBuilder;

public class JLineTerminalCheck {

    public static void main(String[] args) throws IOException {
        try (Terminal terminal = TerminalBuilder.builder()
                .system(true)
                .dumb(true)
                .build()) {

            System.out.println("Terminal type: " + terminal.getType());
            System.out.println("Terminal size: "
                    + terminal.getWidth() + "x" + terminal.getHeight());
        }
    }
}
```

Nếu kết quả là dumb, JLine đang dùng terminal dự phòng với khả năng hạn chế. Basic text input/output có thể vẫn hoạt động, nhưng các tính năng như chỉnh sửa dòng, lịch sử và tự hoàn thành có thể không đầy đủ. JLine mô tả system terminal, virtual terminal và dumb terminal trong tài liệu [Terminal](https://jline.org/versions/3.x/docs/terminal/).

Đây là chương trình chẩn đoán độc lập. Không tạo thêm một Terminal thứ hai trong ứng dụng Spring Shell chỉ để kiểm tra, vì việc mở nhiều terminal reader có thể tranh chấp cùng luồng input.

## 5. Kiểm tra runner của Spring Shell

Spring Shell phân biệt chế độ interactive, non-interactive và chạy script. Từ Spring Shell 3.3.x, chỉ NonInteractiveShellRunner được bật mặc định; InteractiveShellRunner và ScriptShellRunner cần được bật bằng cấu hình. Vì vậy, một ứng dụng không mở prompt có thể đang chạy đúng theo runner hiện được bật. [Execution — Spring Shell 3.3](https://docs.spring.io/spring-shell/reference/3.3/execution.html).

Để bật chế độ interactive:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Hoặc đặt trong biến môi trường:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=true
```

Nếu muốn chạy một command rồi kết thúc, giữ chế độ non-interactive và truyền command cùng option qua application arguments:

```bash
java -jar app.jar user list --active
```

Không dùng interactive runner cho một tác vụ CI cần kết quả xác định rồi chờ prompt. Ngược lại, bật interactive runner không thể khắc phục việc IDE hoặc process launcher không cấp input/TTY.

## 6. Bật script runner khi cần chạy nhiều lệnh

Nếu không có TTY nhưng cần chạy một chuỗi command từ file, Spring Shell có ScriptShellRunner. Bật runner:

```yaml
spring:
  shell:
    script:
      enabled: true
```

Ví dụ file deploy.shell:

```text
project validate --id orders
project deploy --id orders
project status --id orders
```

Chạy script:

```bash
java -jar app.jar @deploy.shell
```

Script runner phù hợp với pipeline hoặc môi trường tự động hóa không có bàn phím. Các command trong file vẫn đi qua parser và command registration của Spring Shell. [ScriptShellRunner API — Spring Shell 3.4](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html).

## 7. Chạy trong IntelliJ IDEA

Console trong cửa sổ Run/Debug của IDE có thể hiển thị stdout và nhận một số input, nhưng không nhất thiết cung cấp đầy đủ khả năng TTY. JLine cũng ghi nhận một số IDE console, trong đó có IntelliJ, không hỗ trợ đầy đủ terminal features. [JLine Troubleshooting Guide](https://jline.org/versions/3.x/docs/troubleshooting/).

Để thử chế độ interactive:

1. Mở View > Tool Windows > Terminal.
2. Chạy ứng dụng từ terminal tích hợp, ví dụ ./mvnw spring-boot:run hoặc java -jar target/app.jar.
3. Xác nhận spring.shell.interactive.enabled=true.
4. Thử nhập command, dùng Tab, phím mũi tên và history.

Nếu chạy bằng Run/Debug Configuration, hãy kiểm tra tùy chọn terminal emulator nếu phiên bản IDE và loại cấu hình hỗ trợ. Khi Run console vẫn không cung cấp TTY, dùng Terminal tool window hoặc một terminal bên ngoài.

## 8. Chạy trong Eclipse

Eclipse có thể cấp Console View để hiển thị output và gửi input đến tiến trình:

1. Mở Run > Run Configurations.
2. Chọn cấu hình Java Application của Spring Shell.
3. Mở tab Common.
4. Bật Allocate console.
5. Chạy lại ứng dụng và thử nhập command.

Theo tài liệu Eclipse, Allocate console cấp Console View để nhận output và gửi user input đến process. Tuy nhiên, việc cấp Console View không đồng nghĩa có đầy đủ PTY. Nếu input hoạt động nhưng JLine không hỗ trợ history, Tab hoặc phím điều hướng, chạy ứng dụng trong terminal thật. [Eclipse Launch Configuration — Common Tab](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.user/reference/ref-launchconfiguration-commontab.htm).

## 9. Chạy Java trong Visual Studio Code

Java Debug Console mặc định của VS Code không hỗ trợ input. Chọn Integrated Terminal hoặc External Terminal trong launch.json:

```json
{
  "type": "java",
  "name": "Spring Shell",
  "request": "launch",
  "mainClass": "com.example.Application",
  "console": "integratedTerminal"
}
```

Có thể đổi thành externalTerminal nếu muốn chạy trong cửa sổ terminal riêng. Tránh internalConsole cho Spring Shell interactive. Tài liệu Java Debugger của VS Code mô tả rõ internalConsole không hỗ trợ input và khuyến nghị Integrated Terminal hoặc External Terminal khi ứng dụng cần đọc terminal input. [Running and Debugging Java — VS Code](https://code.visualstudio.com/docs/java/java-debugging).

## 10. Chạy trong terminal hệ điều hành

Đây là cách kiểm tra tốt để tách lỗi ứng dụng khỏi giới hạn của IDE:

Windows PowerShell:

```powershell
java -jar .\target\app.jar
```

Linux/macOS:

```bash
java -jar target/app.jar
```

Nếu chạy bằng terminal hệ điều hành hoạt động nhưng IDE không hoạt động, kiểm tra cấu hình Run/Debug và loại console mà IDE dùng. Nếu cả hai đều không hoạt động, kiểm tra runner, dependencies JLine, input stream và log khởi động của Spring Shell.

## 11. Chạy trong Docker

Docker cần hai cờ khác nhau cho một phiên terminal tương tác:

- -i giữ standard input mở.
- -t cấp pseudo-TTY cho container.

Chạy shell tương tác:

```bash
docker run --rm -it my-spring-shell-app
```

Nếu container đã chạy:

```bash
docker exec -it spring-shell-container java -jar /app/app.jar
```

Nếu chỉ chạy một command tự động, không cần cấp TTY:

```bash
docker run --rm my-spring-shell-app user list --active
```

Không thêm -t vào mọi pipeline. Một số hệ thống CI không cấp TTY; ép cấp TTY trong môi trường đó có thể gây lỗi hoặc làm output chứa escape sequence không mong muốn.

## 12. Chạy trong CI hoặc process launcher có pipe

CI, Maven plugin hoặc wrapper process có thể chuyển stdin/stdout qua pipe. Khi JLine không phát hiện TTY, nó có thể chuyển sang dumb terminal. JLine mô tả tình huống này với process launcher dùng redirected streams. [JLine Terminal — Piped Streams](https://jline.org/versions/3.x/docs/terminal/).

Trong CI:

- Truyền command và option qua application arguments.
- Đưa cấu hình vào application properties hoặc biến môi trường.
- Dùng script runner nếu cần chạy nhiều command tuần tự.
- Tắt interactive runner cho job không có prompt.
- Đảm bảo command thất bại trả exit code khác 0 để pipeline nhận biết.

Ví dụ:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar app.jar user list --active
```

Không để job CI chờ người dùng nhập password hoặc xác nhận trên prompt. Cung cấp secret qua secret store hoặc cơ chế bảo mật của CI; tránh truyền password trực tiếp trong command line vì command line có thể xuất hiện trong danh sách process.

## 13. Dùng /dev/tty khi input/output bị pipe trên POSIX

Trên Linux và macOS, một process có thể có controlling terminal dù stdin/stdout đang được chuyển qua pipe. JLine 3 hỗ trợ thử mở /dev/tty để truy cập controlling terminal:

```bash
java -Dorg.jline.terminal.devtty=true -jar app.jar
```

Tùy chọn này chỉ có ý nghĩa trên hệ thống POSIX khi process thực sự còn controlling terminal. Nó không tạo TTY trong Docker/CI headless và không phải giải pháp cho Windows. Chỉ dùng khi launcher chuyển stream qua pipe nhưng người dùng vẫn có terminal điều khiển phiên process. [JLine Terminal — /dev/tty fallback](https://jline.org/versions/3.x/docs/terminal/).

## 14. Dumb terminal và giới hạn tính năng

Dumb terminal là chế độ dự phòng khi JLine không thể tạo system terminal đầy đủ. Chế độ này hữu ích cho basic text I/O, nhưng có thể thiếu:

- Tab completion.
- Lịch sử command và di chuyển trong dòng nhập.
- Điều khiển cursor, màu và định dạng terminal nâng cao.
- Phát hiện resize hoặc xử lý terminal signal theo cách đầy đủ.

Trong ứng dụng tự tích hợp JLine, có thể yêu cầu dumb fallback bằng TerminalBuilder.builder().system(true).dumb(true).build(). Với Spring Shell, để framework quản lý terminal và runner; không tự tạo thêm terminal để cố ghi đè cấu hình bên trong.

Nếu cần interactive experience đầy đủ, cấp TTY thực hoặc PTY. Nếu chỉ cần nhận command văn bản đơn giản, dùng non-interactive runner hoặc script runner.

## 15. Phân biệt lỗi TTY với lỗi terminal provider

Thông báo Unable to create a system terminal cũng có thể do thiếu provider native hoặc không tương thích hệ điều hành. JLine 3 có các provider khác nhau; tài liệu troubleshooting phân biệt lỗi dependency provider với lỗi môi trường không interactive. [JLine Troubleshooting Guide](https://jline.org/versions/3.x/docs/troubleshooting/).

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| Lỗi load native library hoặc provider class | Kiểm tra dependency JLine được Spring Shell quản lý và tương thích OS/JDK |
| stdin/stdout là pipe, không có TTY | Chạy bằng terminal/PTY hoặc chọn non-interactive runner |
| JLine dùng dumb nhưng vẫn đọc được dòng | Chấp nhận basic input hoặc cấp TTY nếu cần line editing |
| Windows không nhận console feature | Kiểm tra terminal host và provider tương thích; thử Windows Terminal hoặc PowerShell |

Không tự thêm một phiên bản jline-terminal-* khác với dependency management của Spring Shell. Trộn các phiên bản JLine có thể gây NoSuchMethodError, ClassNotFoundException hoặc lỗi khởi tạo provider.

## 16. Xử lý nhập mật khẩu khi không có console

Console.readPassword() được thiết kế để đọc password mà không echo ký tự ra console. Nếu System.console() là null, ứng dụng không thể dùng API đó. Không thay bằng cách đọc password qua Scanner(System.in) rồi giả định input được che; dữ liệu có thể hiển thị trên màn hình hoặc log.

Trong môi trường tự động:

- Dùng secret store hoặc secret injection của nền tảng triển khai.
- Hạn chế quyền đọc biến môi trường hoặc file secret.
- Không ghi secret vào log.
- Tránh đặt password trong application arguments.
- Xóa mảng ký tự sau khi xử lý nếu ứng dụng nhận password dưới dạng char[].

Nếu ứng dụng yêu cầu người dùng nhập password tương tác, chạy trong terminal có TTY và dùng API nhập mật khẩu an toàn phù hợp với terminal implementation.

## 17. Checklist chẩn đoán theo thứ tự

Khi console không nhận input, kiểm tra theo thứ tự:

1. System.console() có null không?
2. System.in có được cấp và có dữ liệu đầu vào hay đã EOF?
3. Process đang chạy trong terminal/PTY hay qua pipe?
4. JLine đang dùng system terminal hay dumb terminal?
5. Spring Shell có bật spring.shell.interactive.enabled không?
6. Ứng dụng có đang chạy non-interactive command hoặc script runner không?
7. IDE có cấp input cho process hay chỉ hiển thị output?
8. Docker có cần -i -t không?
9. Có lỗi native provider hoặc dependency version mismatch không?
10. Nếu không có TTY, có thể chuyển tác vụ sang command arguments hoặc script không?

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| System.console() là null trong IDE | IDE không cấp console device trực tiếp | Dùng IDE terminal hoặc terminal ngoài |
| Eclipse chỉ hiện output, không nhận input | Chưa bật Allocate console | Bật tùy chọn trong tab Common |
| VS Code không nhập được trong Debug Console | Java Debug Console không hỗ trợ input | Chọn integratedTerminal hoặc externalTerminal |
| Spring Shell không mở prompt | Interactive runner chưa bật | Đặt spring.shell.interactive.enabled=true |
| Tab và history không hoạt động | JLine chạy bằng dumb terminal | Chạy với TTY/PTY hoặc chấp nhận basic I/O |
| Docker không nhận bàn phím | Container không giữ stdin hoặc không có PTY | Dùng docker run -it khi thực sự cần tương tác |
| CI bị treo ở prompt | Job tự động đang chạy interactive flow | Dùng command arguments hoặc script runner |
| Lỗi tạo system terminal | Thiếu provider hoặc môi trường không có TTY | Phân biệt dependency/native error với pipe/no-TTY |
| Password prompt không hoạt động | System.console() không có | Dùng TTY an toàn hoặc secret injection |

## 19. Bài thực hành tổng hợp

Tạo một Spring Shell CLI có command system info và user list:

1. Chạy ứng dụng từ terminal thật và kiểm tra prompt, Tab, history.
2. Chạy từ IDE Debug Console và ghi lại kết quả System.console().
3. Chuyển cấu hình IDE sang integrated terminal rồi chạy lại.
4. Thử bật/tắt spring.shell.interactive.enabled.
5. Chạy command trực tiếp bằng application arguments.
6. Bật spring.shell.script.enabled và chạy một file script.
7. Chạy Docker container với và không có -it.
8. Chạy command trong CI không có TTY.
9. So sánh hành vi khi JLine dùng terminal đầy đủ và dumb terminal.
10. Viết hướng dẫn vận hành: khi nào dùng interactive terminal, khi nào dùng command/script.

## 20. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Console | Giải thích được vì sao System.console() có thể là null |
| Standard input | Phân biệt stdin với Java Console |
| TTY/PTY | Hiểu terminal đầy đủ và dumb terminal |
| JLine | Nhận biết lỗi terminal provider và fallback |
| Spring Shell runner | Cấu hình interactive, non-interactive và script runner |
| IDE | Cấu hình input phù hợp trong IntelliJ, Eclipse hoặc VS Code |
| Container | Biết khi nào cần docker run -it |
| CI | Chạy command/script không phụ thuộc prompt |
| Secrets | Không đọc password qua input không được bảo vệ |
| Troubleshooting | Xác định đúng tầng gây lỗi trước khi thay đổi dependency |

## Tài liệu tham khảo

- [Java 17 — Console API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html)
- [Spring Shell 3.3 — Execution and Shell Runners](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.4 — InteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/InteractiveShellRunner.html)
- [JLine 3 — Terminal](https://jline.org/versions/3.x/docs/terminal/)
- [JLine 3 — Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/)
- [Eclipse — Launch Configuration Common Tab](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.user/reference/ref-launchconfiguration-commontab.htm)
- [VS Code — Running and Debugging Java](https://code.visualstudio.com/docs/java/java-debugging)
