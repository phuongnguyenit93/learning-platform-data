# Khả năng đọc từ console khi chạy trong IDE, pipeline hoặc container

Một ứng dụng Spring Shell có thể chạy tốt trên máy phát triển với prompt tương tác nhưng không đọc được input khi được khởi chạy từ IDE, CI pipeline hoặc container. Nguyên nhân thường nằm ở cách tiến trình Java được khởi chạy và cách môi trường cấp các luồng vào/ra.

Để xử lý đúng, cần phân biệt ba khái niệm: Java Console API (`System.console()`), các luồng chuẩn (`System.in`, `System.out`, `System.err`) và execution mode của Spring Shell. Một IDE có thể hiển thị cửa sổ console nhưng không cung cấp terminal thật; một pipeline có thể truyền dữ liệu qua stdin nhưng không có bàn phím tương tác; một container có thể giữ stdin mở nhưng không cấp pseudo-terminal.

Bài học thuộc phạm vi SPRING_SHELL: xây dựng CLI bằng Spring Shell, nhận tham số, validation, trợ giúp và tự hoàn thành, đồng thời vận hành command trong môi trường phát triển, tự động hóa và triển khai. Trọng tâm là xác định ứng dụng có thể chờ người dùng nhập trực tiếp hay cần nhận dữ liệu qua command argument, file hoặc standard input.

## 1. Ba khái niệm thường bị nhầm lẫn

| Khái niệm | Java hoặc Spring API | Ý nghĩa |
|---|---|---|
| Console | `System.console()` | Đối tượng truy cập thiết bị console dạng ký tự nếu JVM được gắn với console phù hợp |
| Standard input | `System.in` | Luồng dữ liệu đầu vào của tiến trình; có thể đến từ bàn phím, pipe hoặc file |
| Interactive mode | `ShellRunner`, `ShellContext` | Spring Shell chạy REPL để người dùng nhập nhiều command trong một phiên |

Một tiến trình có thể đọc được `System.in` dù `System.console()` trả về `null`. Ví dụ, pipeline có thể chuyển nội dung file vào stdin. Ngược lại, một IDE có cửa sổ Output và cho phép xem log nhưng không cấp terminal device cho tiến trình Java.

Interactive mode cũng không có nghĩa chắc chắn đang có bàn phím hoặc TTY. `ShellContext.getInteractionMode()` cho biết Spring Shell đang chạy theo chế độ interactive hay non-interactive; nó không phải phép kiểm tra trực tiếp xem `System.console()` có tồn tại hay terminal có PTY hay không.

Có thể hình dung các lớp như sau:

~~~mermaid
flowchart TD
    A["IDE / Terminal / CI / Container"] --> B["Tiến trình Java"]
    B --> C["System.in / System.out / System.err"]
    B --> D["System.console() nếu có console device"]
    B --> E["Spring Boot ApplicationArguments"]
    E --> F["Spring Shell ShellApplicationRunner"]
    F --> G["InteractiveShellRunner"]
    F --> H["NonInteractiveShellRunner"]
    F --> I["ScriptShellRunner"]
    G --> J["JLine REPL"]
    H --> K["Chạy command từ arguments"]
    I --> L["Chạy command từ file script"]
~~~

Vì vậy, khi ứng dụng không đọc được input, trước tiên cần xác định dữ liệu được dự kiến đi vào qua console, stdin, tham số command hay script.

## 2. Vì sao System.console() có thể trả về null?

Java cung cấp `System.console()` để lấy đối tượng `java.io.Console` gắn với JVM. Đối tượng này thường có mặt khi ứng dụng được khởi chạy từ terminal tương tác và các luồng chuẩn chưa bị chuyển hướng.

Nếu `console` là `null`, không được gọi tiếp `console.readLine()` hoặc `console.readPassword()`. Những lời gọi đó sẽ gây `NullPointerException`.

Các trường hợp thường gặp:

- IDE chạy ứng dụng bằng cơ chế capture stdout/stderr riêng thay vì gắn tiến trình với terminal thật.
- Chương trình được chạy từ background job hoặc scheduler.
- Standard input hoặc output được chuyển hướng sang file hay pipe.
- CI runner khởi chạy process trong môi trường không có terminal tương tác.
- Container không được cấp TTY hoặc không giữ stdin mở.
- SSH hoặc terminal multiplexer được cấu hình theo cách không cung cấp console device cho tiến trình.

Không nên kết luận rằng mọi IDE đều không có console. Khả năng này phụ thuộc cấu hình Run/Debug, terminal tích hợp và cách IDE khởi chạy JVM. Hãy kiểm tra trong chính môi trường chạy ứng dụng.

### 2.1. Kiểm tra console và standard input khi khởi động

Có thể thêm một đoạn chẩn đoán ngắn trong giai đoạn phát triển:

~~~java
import java.io.Console;

public class ConsoleDiagnostics {

    public static void printStatus() {
        Console console = System.console();

        System.out.println(
                "javaConsoleAvailable=" + (console != null));

        System.out.println(
                "stdinClass=" + System.in.getClass().getName());

        System.out.println(
                "stdoutClass=" + System.out.getClass().getName());
    }
}
~~~

Kết quả ví dụ khi chạy từ terminal:

~~~text
javaConsoleAvailable=true
stdinClass=java.io.BufferedInputStream
stdoutClass=java.io.PrintStream
~~~

Kết quả ví dụ khi chạy từ pipeline:

~~~text
javaConsoleAvailable=false
stdinClass=java.io.BufferedInputStream
stdoutClass=java.io.PrintStream
~~~

Tên lớp của stream không đủ để xác định có TTY hay không. Đoạn mã chỉ giúp kiểm tra Java Console API có hiện diện và nhận diện các stream đang được sử dụng. Để xác định môi trường có PTY, cần kiểm tra terminal hoặc cấu hình runner/container tương ứng.

Không dùng `System.in.available()` như phép kiểm tra xem người dùng có thể nhập hay không. Giá trị này chỉ phản ánh số byte có thể đọc ngay mà không chặn, không phải phép kiểm tra TTY hoặc EOF đáng tin cậy.

## 3. Phân biệt System.console() và System.in

`System.console()` phục vụ tương tác với console device. `System.in` là luồng byte chuẩn đầu vào và có thể nhận dữ liệu từ nhiều nguồn.

| Nguồn chạy | `System.console()` | `System.in` |
|---|---|---|
| Terminal tương tác thông thường | Thường có | Thường nhận dữ liệu bàn phím |
| IDE Output console | Có thể là `null` | Có thể được IDE kết nối hoặc không |
| CI pipeline | Thường là `null` | Có thể nhận pipe, file hoặc EOF |
| Container chạy với `-it` | Có khả năng có console | Được nối với terminal |
| Container chạy với `-i` nhưng không có `-t` | Thường không có console device | Có thể nhận dữ liệu qua stdin |
| Input được redirect từ file | Không có console device | Đọc dữ liệu từ file |

### 3.1. Đọc một dòng từ Java Console

Nếu ứng dụng thực sự cần hỏi người dùng trực tiếp trong terminal, có thể dùng `Console.readLine()`:

~~~java
import java.io.Console;

public class ConfirmationReader {

    public boolean confirm() {
        Console console = System.console();

        if (console == null) {
            throw new IllegalStateException(
                    "Interactive console is unavailable. "
                    + "Pass the confirmation as a command option.");
        }

        String answer = console.readLine("Continue? [y/N] ");

        if (answer == null) {
            return false; // EOF
        }

        return "y".equalsIgnoreCase(answer.trim())
                || "yes".equalsIgnoreCase(answer.trim());
    }
}
~~~

`readLine()` trả về `null` khi đạt EOF, chẳng hạn người dùng nhấn Ctrl+D trên Unix hoặc Ctrl+Z trên Windows. Cần xử lý trường hợp này thay vì giả định luôn nhận được một chuỗi.

Trong Spring Shell, nếu command đã được chạy bên trong REPL do JLine quản lý, nên ưu tiên các cơ chế nhập liệu của shell hoặc command option. Đừng tự tạo thêm một `Scanner(System.in)` bên trong command method nếu JLine cũng đang đọc cùng luồng, vì hai bộ đọc có thể tranh nhau dữ liệu.

### 3.2. Đọc mật khẩu

`Console.readPassword()` đọc mật khẩu mà không echo ký tự ra terminal. Phương thức trả về `char[]`, vì vậy có thể xóa nội dung sau khi dùng:

~~~java
import java.io.Console;
import java.util.Arrays;

public class PasswordReader {

    public void authenticate() {
        Console console = System.console();

        if (console == null) {
            throw new IllegalStateException(
                    "A secure interactive console is required");
        }

        char[] password = console.readPassword("Password: ");

        if (password == null) {
            throw new IllegalStateException("No password was provided");
        }

        try {
            authenticateWithService(password);
        }
        finally {
            Arrays.fill(password, '\0');
        }
    }

    private void authenticateWithService(char[] password) {
        // Gọi dịch vụ xác thực.
    }
}
~~~

Không chuyển mật khẩu sang `String` nếu không cần thiết, vì `String` không thể bị ghi đè nội dung sau khi tạo. `char[]` có thể được xóa sau khi sử dụng, dù việc này chỉ giảm thời gian dữ liệu nhạy cảm tồn tại trong bộ nhớ chứ không bảo đảm xóa mọi bản sao ở cấp JVM.

Trong CI hoặc container chạy tự động, không nên chờ người dùng gõ mật khẩu. Hãy lấy secret từ cơ chế quản lý secret của môi trường, biến môi trường được cấp có kiểm soát hoặc file secret được mount với quyền truy cập phù hợp. Không in secret vào log.

### 3.3. Đọc dữ liệu được pipe qua System.in

Khi stdin là một nguồn dữ liệu có chủ đích, Java có thể đọc nó bằng `BufferedReader`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class StdinReader {

    public String readFirstLine() throws IOException {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in,
                        StandardCharsets.UTF_8));

        return reader.readLine();
    }
}
~~~

Ví dụ Bash:

~~~bash
printf 'inventory-api\n' | java -jar customer-cli.jar project import-from-stdin
~~~

Nếu command được thiết kế để đọc stdin, nó có thể nhận `inventory-api` từ pipe dù không có Java Console.

Lưu ý:

- `readLine()` trả về `null` nếu stream đã hết dữ liệu.
- Không đóng `System.in` trong command nếu tiến trình còn cần dùng stream đó.
- Tạo một reader dùng chung nếu cần đọc nhiều dòng; không tạo nhiều reader độc lập trên cùng một stream.
- Xác định encoding của dữ liệu, chẳng hạn UTF-8.
- Khi chạy Spring Shell interactive, JLine thường đã sở hữu luồng nhập của terminal. Chỉ đọc trực tiếp `System.in` khi command được thiết kế rõ ràng để nhận batch input từ stdin và không cạnh tranh với REPL.

## 4. Các execution mode trong Spring Shell 3.x

Spring Shell 3.x sử dụng `ShellApplicationRunner` để nhận `ApplicationArguments` của Spring Boot và chọn một `ShellRunner` phù hợp.

Ba runner chính:

| Runner | Chức năng | Trường hợp sử dụng |
|---|---|---|
| `InteractiveShellRunner` | Mở REPL, chờ người dùng nhập nhiều command | Terminal phát triển, terminal vận hành |
| `NonInteractiveShellRunner` | Chạy command từ tham số khởi động rồi kết thúc | CI pipeline, automation, container job |
| `ScriptShellRunner` | Đọc và chạy file script được chỉ định bằng đối số bắt đầu bằng `@` | Batch command theo thứ tự |

Trong Spring Shell 3.1.x và 3.2.x, cả ba runner được bật mặc định. Từ 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Vì vậy, một ứng dụng nâng từ 3.2 lên 3.3 có thể không còn tự mở prompt như trước nếu chưa bật interactive runner.

Các property điều khiển runner:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
~~~

Với ứng dụng Spring Shell 3.3.x cần REPL, phải bật `spring.shell.interactive.enabled=true`. Có thể cấu hình trong `application.yml`, profile riêng hoặc biến môi trường:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=true
~~~

Trong pipeline chỉ chạy command tự động, có thể tắt interactive runner:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: true
~~~

Không nên chỉ dựa vào việc có hay không có command argument để kết luận tiến trình đang có terminal. Runner selection và sự tồn tại của console/PTY là hai thông tin khác nhau.

## 5. Chọn command phù hợp với interactive và non-interactive mode

Một số command chỉ có ý nghĩa khi có phiên REPL đang hoạt động, ví dụ command mở wizard hoặc yêu cầu người dùng lựa chọn nhiều bước. Spring Shell legacy 3.x cho phép chỉ định `InteractionMode` trên `@ShellMethod`.

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class SetupCommands {

    @ShellMethod(
            value = "Open the interactive setup wizard.",
            interactionMode = InteractionMode.INTERACTIVE)
    public String setupWizard() {
        return "Starting setup wizard";
    }

    @ShellMethod(
            value = "Run a setup using supplied values.",
            interactionMode = InteractionMode.NONINTERACTIVE)
    public String setup(
            @ShellOption("--environment") String environment,
            @ShellOption("--project") String project) {
        return "Setting up " + project + " in " + environment;
    }
}
~~~

`InteractionMode` có ba giá trị:

- `ALL`: command dùng được ở cả hai chế độ.
- `INTERACTIVE`: command chỉ có ý nghĩa trong REPL.
- `NONINTERACTIVE`: command phù hợp cho một lần chạy tự động.

Nếu không khai báo, `@ShellMethod` mặc định dùng `InteractionMode.ALL`.

### 5.1. Đọc chế độ hiện tại qua ShellContext

Nếu cần biết shell đang chạy chế độ nào, có thể inject `ShellContext`:

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.context.ShellContext;
import org.springframework.stereotype.Component;

@Component
public class ExecutionModeInspector {

    private final ShellContext shellContext;

    public ExecutionModeInspector(ShellContext shellContext) {
        this.shellContext = shellContext;
    }

    public boolean isInteractive() {
        return shellContext.getInteractionMode()
                == InteractionMode.INTERACTIVE;
    }
}
~~~

`getInteractionMode()` cho biết mode của Spring Shell. Nó không chứng minh JVM có `System.console()` hoặc terminal có PTY. Nếu command cần khả năng tương tác thực sự, vẫn phải xử lý trường hợp không có console hoặc input kết thúc sớm.

### 5.2. Phân biệt interaction mode với PTY

PTY (pseudo-terminal) mô phỏng thiết bị terminal cho tiến trình. Nó cung cấp các đặc tính terminal như điều khiển echo, xử lý phím và tương tác theo dòng.

Trong Spring Shell 3.1.x, `ShellContext` cung cấp `getInteractionMode()` và không có phương thức `hasPty()`. Tài liệu API 3.4.x bổ sung `hasPty()` để cho biết shell có terminal PTY phù hợp hay không. Không gọi `hasPty()` trong ứng dụng biên dịch với API 3.1.x.

Lưu ý: thông tin về `hasPty()` ở đây dựa trên API nhánh 3.4-SNAPSHOT; hãy kiểm tra Javadoc của đúng bản 3.4.x đang dùng trước khi phụ thuộc vào phương thức này.

Ngay cả khi có PTY, command vẫn cần kiểm tra input và xử lý EOF. Ngược lại, một process không có PTY vẫn có thể đọc stdin từ pipe hoặc file.

## 6. Chạy ứng dụng trong IDE

IDE thường có hai cách chạy khác nhau:

- Run/Debug console: IDE thu nhận output và có thể cung cấp vùng nhập liệu riêng.
- Terminal tích hợp: IDE mở một shell hệ điều hành thực, chẳng hạn PowerShell, Bash hoặc zsh.

Run/Debug console không phải lúc nào cũng là TTY. Vì vậy, ứng dụng có thể in được log nhưng `System.console()` vẫn là `null`.

### 6.1. Khi cần REPL tương tác

Nếu muốn làm việc với Spring Shell như một terminal:

1. Bật `spring.shell.interactive.enabled=true` nếu phiên bản hoặc cấu hình dự án đang tắt runner.
2. Kiểm tra IDE có tùy chọn terminal emulation hoặc terminal integration cho cấu hình Run/Debug hay không.
3. Nếu JLine không hoạt động đúng trong Run console, chạy JAR từ Terminal tích hợp của IDE.
4. Kiểm tra `System.console()` nếu code Java có dùng trực tiếp Java Console API.
5. Không xem việc log được hiển thị là bằng chứng tiến trình có thể đọc input tương tác.

Ví dụ chạy trong terminal tích hợp:

~~~bash
java -jar customer-cli.jar
~~~

Prompt Spring Shell xuất hiện và người dùng có thể nhập command:

~~~text
shell:> help
shell:> project list
shell:> exit
~~~

### 6.2. Khi chỉ muốn chạy một command trong IDE

Có thể cấu hình Program arguments trong Run/Debug configuration:

~~~text
project show --id 1042
~~~

Spring Shell xử lý command theo non-interactive runner và tiến trình kết thúc sau khi chạy. Cách này dễ lặp lại trong debugger và phù hợp với integration test hoặc smoke test.

Không cần gọi `System.console().readLine()` trong command để lấy dữ liệu mà có thể khai báo thành `@ShellOption` hoặc argument. Điều đó giúp chạy cùng một command trong IDE, terminal và pipeline.

## 7. Chạy trong CI pipeline

CI pipeline thường chạy trong process không có người dùng trực tiếp. Standard input có thể bị đóng, nối với pipe hoặc không được cung cấp. Vì vậy, command không nên chờ nhập liệu không giới hạn.

### 7.1. Truyền dữ liệu bằng command arguments

Ví dụ:

~~~bash
java -jar customer-cli.jar deploy \
  --environment staging \
  --project inventory-api
~~~

Command nhận dữ liệu qua tham số:

~~~java
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class DeploymentCommands {

    @ShellMethod("Deploy a project.")
    public String deploy(
            @ShellOption("--environment") String environment,
            @ShellOption("--project") String project) {

        return "Deploying " + project + " to " + environment;
    }
}
~~~

Giá trị đã có ngay từ lúc khởi chạy. Không cần mở prompt để hỏi lại.

### 7.2. Truyền cấu hình qua environment

Pipeline có thể cung cấp giá trị từ biến môi trường:

~~~bash
export DEPLOY_ENV=staging
export PROJECT_NAME=inventory-api

java -jar customer-cli.jar deploy \
  --environment "$DEPLOY_ENV" \
  --project "$PROJECT_NAME"
~~~

Không ghi secret vào command line nếu hệ điều hành hoặc công cụ CI có thể lưu lại process arguments. Với thông tin nhạy cảm, ưu tiên secret store và cơ chế inject phù hợp của CI runner.

### 7.3. Không chờ xác nhận tương tác

Không nên viết command như sau cho pipeline:

~~~java
Console console = System.console();
String answer = console.readLine("Continue? [y/N] ");
~~~

Trong CI, `console` có thể là `null`, hoặc tiến trình sẽ chờ mãi nếu không có người nhập. Thay vào đó, cung cấp option rõ ràng:

~~~text
deploy --environment production --confirm true
~~~

Command cần kiểm tra `--confirm` và các điều kiện nghiệp vụ trước khi thực hiện thao tác quan trọng. Không tự động xem EOF hoặc thiếu input là xác nhận đồng ý.

### 7.4. Sử dụng file script

Spring Shell 3.x có `ScriptShellRunner`, nhận đối số bắt đầu bằng `@` và chạy các command trong file:

~~~bash
java -jar customer-cli.jar @deploy-steps.txt
~~~

Ví dụ `deploy-steps.txt`:

~~~text
project select --name inventory-api
environment select --name staging
deploy --confirm true
~~~

Ngoài ra, khi đang ở REPL, có thể dùng built-in command `script` để đọc file command:

~~~text
shell:> script --file deploy-steps.txt
~~~

File script phù hợp khi cần chạy nhiều command theo thứ tự. Mỗi dòng nên là một command có thể tái lập và không yêu cầu thao tác bàn phím.

## 8. Chạy trong container

Container không tự động có console tương tác. Việc có thể nhập từ terminal phụ thuộc cách container được khởi chạy và cách stdin/TTY được nối vào process.

Docker phân biệt hai tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-i` / `--interactive` | Giữ stdin mở để có thể gửi dữ liệu vào container |
| `-t` / `--tty` | Cấp pseudo-terminal cho container |

### 8.1. Chạy container cho người dùng tương tác

Dùng `-it` để giữ stdin mở và cấp PTY:

~~~bash
docker run --rm -it customer-cli:latest
~~~

Ứng dụng có thể mở REPL và đọc dữ liệu trực tiếp từ terminal:

~~~text
shell:> help
shell:> project list
~~~

Nếu container chạy một lệnh cần nhập password mà không có TTY, khả năng ẩn ký tự nhập có thể không hoạt động như mong đợi. Với tác vụ tương tác, cần cấp PTY và kiểm tra Java Console API thực tế.

### 8.2. Chạy container trong pipeline

Với tác vụ tự động, không cần `-t`:

~~~bash
docker run --rm customer-cli:latest \
  deploy --environment production \
  --project inventory-api
~~~

Nếu command được thiết kế để đọc dữ liệu pipe từ stdin, có thể dùng `-i`:

~~~bash
cat projects.txt | docker run --rm -i customer-cli:latest \
  project import-from-stdin
~~~

`-i` giữ stdin mở nhưng không tự cấp PTY. Do đó, dữ liệu có thể được đọc từ pipe dù Java Console API không có sẵn. Không dùng `-t` trong pipeline chỉ để cố làm `System.console()` khác `null`, vì TTY giả có thể làm hỏng output được chuyển hướng hoặc xử lý tín hiệu.

### 8.3. Khi dùng Kubernetes hoặc môi trường container khác

Các nền tảng container khác cũng phân biệt stdin và TTY. Khi cần phiên thao tác thủ công, cấu hình tương đương với giữ stdin mở và cấp TTY. Khi chạy Job hoặc pipeline, truyền command arguments, environment và volume chứa input file.

Đừng mặc định pod đang chạy có terminal chỉ vì có thể xem log. Log là output của process; nó không cho biết process có thiết bị nhập tương tác.

## 9. Tránh xung đột khi đọc System.in trong Spring Shell

Spring Shell với JLine cần đọc dòng lệnh, xử lý phím, lịch sử và completion. Nếu command method tự tạo một reader khác trên cùng `System.in`, hai thành phần có thể cùng tiêu thụ dữ liệu.

Ví dụ không nên dùng trong command chạy bên trong REPL:

~~~java
@ShellMethod("Import data.")
public void importData() {
    Scanner scanner = new Scanner(System.in);
    String value = scanner.nextLine();
    // ...
}
~~~

JLine có thể đã đọc trước dữ liệu vào buffer. Reader thứ hai không biết trạng thái buffer của JLine và có thể nhận dữ liệu thiếu hoặc bị treo.

Nên ưu tiên một trong các cách sau:

- Khai báo input thành `@ShellOption` hoặc argument để Spring Shell xử lý parsing và binding.
- Dùng file hoặc resource làm nguồn dữ liệu cho command batch.
- Nếu cần một prompt phụ trong REPL, dùng cơ chế terminal/JLine hoặc các component tương tác của Spring Shell thay vì tự mở reader mới.
- Nếu command được thiết kế chuyên để xử lý stdin trong non-interactive mode, bảo đảm không có REPL đồng thời đọc cùng stream.

## 10. Tách output, log và lỗi

Trong pipeline, stdout thường được dùng làm output chính và có thể được chuyển tiếp sang command khác. Nếu log khởi động hoặc log debug trộn với output dữ liệu, script phía sau có thể nhận dữ liệu sai.

Spring Boot mặc định ghi log ra console. Spring Shell 3.1.x tài liệu khuyến nghị có thể tắt console logging hoặc chuyển log sang file để tránh trộn với output command.

Ví dụ cấu hình:

~~~yaml
logging:
  file:
    name: customer-cli.log
~~~

Hoặc nếu muốn im lặng console logging:

~~~yaml
logging:
  pattern:
    console:
~~~

Quy ước nên áp dụng:

- stdout: kết quả command mà script hoặc người dùng cần nhận.
- stderr: thông báo lỗi và chẩn đoán.
- file log: log ứng dụng, debug và thông tin vận hành.
- Không in secret hoặc dữ liệu nhạy cảm vào bất kỳ stream nào.

Nếu command trả về JSON hoặc CSV, hãy giữ stdout chỉ chứa định dạng đó. Thông tin khởi động Spring Boot hoặc log không nên xuất hiện xen giữa các dòng dữ liệu.

## 11. Đóng ứng dụng sau khi chạy non-interactive command

Một command chạy trong CI thường cần kết thúc tiến trình sau khi hoàn thành. Spring Boot thường đóng `ApplicationContext` sau khi các `ApplicationRunner` hoàn tất nếu không còn thread non-daemon giữ JVM sống.

Nếu ứng dụng có scheduler, worker hoặc thread nền khiến process không kết thúc, Spring Shell 3.1.x có property:

~~~yaml
spring:
  shell:
    context:
      close: true
~~~

Property này đăng ký listener yêu cầu đóng context sau khi shell hoàn tất execution logic. Không bật tùy tiện cho ứng dụng cần tiếp tục chạy tác vụ nền; chỉ dùng khi command shell là công việc cần kết thúc theo tiến trình.

Pipeline cũng nên kiểm tra exit code của process thay vì chỉ kiểm tra output có chữ “success”. Exit code là tín hiệu mà shell hệ điều hành và CI runner có thể sử dụng để quyết định bước tiếp theo.

## 12. Khác biệt execution runner giữa các phiên bản Spring Shell

Cấu hình runner có thay đổi theo phiên bản:

| Phiên bản | Runner mặc định | Lưu ý |
|---|---|---|
| 3.1.x–3.2.x | `InteractiveShellRunner`, `NonInteractiveShellRunner`, `ScriptShellRunner` đều bật | Cần xem `ApplicationArguments` và runner precedence để biết runner nào xử lý |
| 3.3.x trở lên trong dòng 3.x | Chỉ `NonInteractiveShellRunner` bật mặc định | Cần bật `spring.shell.interactive.enabled=true` nếu muốn REPL |
| 4.x | Chọn mô hình runner khi khởi động | Không còn đánh dấu từng command bằng `InteractionMode`; tắt interactive để chạy command từ process arguments |

Spring Shell 4.x thay đổi thêm tên runner tương tác: `SystemShellRunner` dùng Java Console API, còn `JLineShellRunner` dùng JLine khi có dependency tương ứng. `NonInteractiveShellRunner` dành cho script và automation. Khi nâng từ 3.x lên 4.x, hãy xem migration guide và kiểm tra lại cấu hình terminal.

Không lấy hành vi mặc định của Spring Shell 3.1.x áp dụng cho 3.3.x hoặc 4.x. Ghi rõ phiên bản Spring Shell trong tài liệu triển khai và kiểm thử các runner trên phiên bản đang đóng gói.

## 13. Kiểm thử tương tác và non-interactive

Spring Shell 3.1.x cung cấp `spring-shell-test` và `ShellTestClient` để kiểm tra hai loại phiên.

Kiểm thử interactive nên xác minh:

- Shell mở được REPL.
- Prompt xuất hiện.
- Người dùng có thể gửi command và nhận output.
- Input nhiều bước hoạt động đúng.
- Command không yêu cầu console hoạt động khi chạy trong mode khác.

Kiểm thử non-interactive nên xác minh:

- Command được nhận từ application arguments.
- Output đúng định dạng.
- Command kết thúc mà không chờ bàn phím.
- Lỗi trả về exit code phù hợp.
- EOF hoặc stdin rỗng được xử lý rõ ràng.
- Script chạy theo đúng thứ tự.

Ví dụ kiểm thử interactive theo tài liệu Spring Shell 3.1.x:

~~~java
@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class InteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void opensInteractiveSession() {
        InteractiveShellSession session = client
                .interactive()
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("shell"));
    }
}
~~~

`ShellTestClient` cũng cung cấp phiên non-interactive để gửi command arguments và kiểm tra screen/output. Dùng đúng API của phiên bản đang cài vì tên method và test support có thể thay đổi giữa các dòng release.

Ngoài test trong bộ giả lập terminal, nên chạy smoke test thực tế ở môi trường tương ứng: Run/Debug console, terminal tích hợp, CI job và container. Test unit không thể xác nhận runner có được cấp TTY hoặc stdin từ hệ điều hành hay không.

## 14. Ma trận kiểm chứng theo môi trường

| Môi trường | Console API | stdin | Cấu hình/kiểm tra cần làm |
|---|---|---|---|
| Terminal local | Thường có | Bàn phím | Chạy interactive runner, kiểm tra JLine |
| IDE Run console | Có thể `null` | Tùy IDE | Kiểm tra terminal emulation; không phụ thuộc `System.console()` |
| IDE integrated terminal | Có khả năng có | Bàn phím | Chạy ứng dụng từ terminal tích hợp |
| CI pipeline | Thường `null` | Pipe, file hoặc EOF | Chạy non-interactive; truyền args/env/file |
| Docker `-it` | Có khả năng có | Terminal | Dùng cho thao tác thủ công |
| Docker `-i` | Thường `null` | Giữ stdin mở | Dùng để pipe dữ liệu batch |
| Docker không có `-i`/`-t` | Thường `null` | Có thể EOF | Dùng command arguments và file |
| Script runner | Không cần console | File script | Kiểm tra script, thứ tự command và exit status |

Khi xác minh, ghi lại:

1. Phiên bản Spring Shell và Spring Boot.
2. Cách khởi chạy tiến trình.
3. Runner nào được bật.
4. `System.console()` có `null` không.
5. stdin đến từ bàn phím, pipe, file hay EOF.
6. Có PTY/TTY hay không.
7. Command có prompt tương tác không.
8. Output và exit code có đúng kỳ vọng không.

## 15. Quy trình chẩn đoán khi ứng dụng không đọc được input

Khi ứng dụng hiển thị prompt nhưng không nhận dữ liệu, hoặc chạy trong IDE được nhưng CI bị treo, hãy kiểm tra theo thứ tự:

### Bước 1: Xác định nguồn input dự kiến

- Nếu là prompt của Spring Shell, kiểm tra interactive runner và terminal/JLine.
- Nếu là dữ liệu pipe, kiểm tra stdin có được nối vào tiến trình hay không.
- Nếu là command arguments, kiểm tra cách truyền arguments từ IDE hoặc CI.
- Nếu là file script, kiểm tra `ScriptShellRunner` hoặc command `script`.

### Bước 2: Kiểm tra Java Console API

Ghi nhận kết quả `System.console()`. Nếu là `null`, không gọi `readLine()` hoặc `readPassword()` trên console.

### Bước 3: Kiểm tra stdin và EOF

Nếu dùng stdin, thử gửi một dòng dữ liệu mẫu. Xử lý trường hợp `readLine()` trả `null` và không chờ thêm dữ liệu khi pipe đã kết thúc.

### Bước 4: Kiểm tra runner của Spring Shell

Xem các property `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled`. Xác minh default theo phiên bản: 3.1–3.2 khác 3.3 trở lên.

### Bước 5: Kiểm tra TTY/PTY của môi trường

Với Docker, xác minh `-i` và `-t` có được bật đúng mục tiêu không. Với CI, xác minh job có cấp pseudo-terminal hay không; nếu không, thiết kế job không yêu cầu prompt.

### Bước 6: Loại bỏ reader cạnh tranh

Tìm trong command method các chỗ tạo `Scanner(System.in)`, `BufferedReader(System.in)` hoặc gọi `System.console()`. Nếu JLine đang sở hữu input, chuyển dữ liệu thành option hoặc dùng API tương tác của shell.

### Bước 7: Kiểm tra output và tiến trình kết thúc

Đảm bảo log không trộn vào stdout, command có exit status rõ ràng và application context không bị thread nền giữ lại ngoài ý muốn.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `System.console()` là `null` trong IDE | IDE capture output hoặc không cấp console device | Dùng terminal tích hợp hoặc không phụ thuộc Java Console API |
| Command bị `NullPointerException` khi đọc console | Gọi `readLine()` khi console là `null` | Kiểm tra console trước khi đọc |
| Pipeline bị treo | Command đang chờ input tương tác | Truyền arguments, environment hoặc file |
| `System.in` đọc được trong container nhưng console là `null` | Có stdin nhưng không có PTY | Dùng stdin cho batch input; không gọi Console API |
| Spring Shell không mở prompt sau nâng cấp | Spring Shell 3.3 chỉ bật non-interactive runner mặc định | Bật `spring.shell.interactive.enabled=true` |
| Nhấn phím trong REPL không phản hồi | JLine không nhận terminal phù hợp hoặc reader khác đang tiêu thụ stdin | Kiểm tra terminal và loại bỏ reader cạnh tranh |
| Password hiển thị trên log | Đọc bằng `readLine()` hoặc stdin không có TTY echo control | Dùng secure prompt trong terminal hoặc secret injection |
| Output JSON bị lẫn log | Spring Boot logging ghi vào console | Chuyển log sang file/stderr và giữ stdout sạch |
| Container không nhận bàn phím | Không giữ stdin mở | Dùng `-i`; nếu cần terminal thì thêm `-t` |
| Command hoàn tất nhưng JVM không thoát | Thread nền còn sống | Kiểm tra lifecycle và cân nhắc `spring.shell.context.close` |

## 17. Bài thực hành: chạy cùng command trong ba môi trường

Tạo command `project import` nhận option `--file` và một command `project import-from-stdin` đọc dữ liệu từ stdin trong chế độ batch.

Yêu cầu:

1. Chạy ứng dụng trong terminal local và xác nhận REPL hoạt động.
2. Chạy từ IDE Run console, ghi nhận `System.console()` có thể khác terminal local.
3. Chạy từ IDE integrated terminal và so sánh kết quả.
4. Chạy `project import --file projects.csv` bằng non-interactive runner.
5. Pipe một dòng dữ liệu vào `project import-from-stdin`.
6. Chạy command trong Docker với `-it`.
7. Chạy command trong Docker với `-i` nhưng không `-t`.
8. Chạy cùng command trong CI job không có TTY.
9. Xác minh không có command nào chờ input vô hạn trong pipeline.
10. So sánh stdout, stderr, log và exit code.

Ví dụ:

~~~bash
java -jar customer-cli.jar project import --file projects.csv

printf 'inventory-api\n' \
  | java -jar customer-cli.jar project import-from-stdin

docker run --rm -it customer-cli:latest

docker run --rm customer-cli:latest \
  project import --file /workspace/projects.csv
~~~

Ghi lại môi trường, runner, console availability, nguồn stdin và kết quả. Mục tiêu là làm cho command có thể vận hành ổn định cả khi có người nhập trực tiếp và khi chạy tự động.

## 18. Checklist trước khi triển khai

- [ ] Đã phân biệt Java Console API, standard input và Spring Shell execution mode.
- [ ] Không giả định `System.console()` luôn tồn tại.
- [ ] Đã xử lý trường hợp `System.console()` trả `null`.
- [ ] Đã xử lý EOF khi đọc console hoặc stdin.
- [ ] Không tạo reader cạnh tranh với JLine trong REPL.
- [ ] Đã xác định runner phù hợp: interactive, non-interactive hoặc script.
- [ ] Đã kiểm tra default runner theo phiên bản Spring Shell.
- [ ] Đã truyền dữ liệu qua arguments, environment hoặc file trong CI.
- [ ] Đã cấu hình Docker `-i` và `-t` theo nhu cầu thực tế.
- [ ] Không yêu cầu nhập password hoặc xác nhận thủ công trong pipeline.
- [ ] Đã tách stdout, stderr và log.
- [ ] Đã kiểm tra exit code và thời điểm đóng ApplicationContext.
- [ ] Đã kiểm thử interactive và non-interactive bằng test support.
- [ ] Đã smoke test trong IDE, CI và container mục tiêu.

## 19. Kết luận

Khả năng đọc từ console phụ thuộc cách JVM và tiến trình được khởi chạy. `System.console()` chỉ có khi JVM được gắn với console device; `System.in` có thể tiếp tục nhận dữ liệu từ pipe hoặc file dù Java Console API không tồn tại. Spring Shell lại có execution mode riêng, được điều khiển bởi các `ShellRunner` và cấu hình theo phiên bản.

Trong IDE, hãy xác minh terminal integration và runner. Trong pipeline, truyền input bằng command arguments, environment hoặc file và tránh chờ người dùng. Trong container, dùng `-it` cho phiên tương tác, `-i` cho stdin dạng pipe và bỏ TTY khi chạy batch. Khi Spring Shell đang dùng JLine, để shell quản lý input của REPL thay vì tạo thêm reader trên `System.in`.

Thiết kế command nhận dữ liệu rõ ràng, xử lý EOF, tách log khỏi output và kiểm thử từng execution mode sẽ giúp cùng một ứng dụng chạy ổn định trong môi trường phát triển, tự động hóa và triển khai.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Execution and Shell Runners](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1.6 Reference: Testing](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: `ShellRunner`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/ShellRunner.html)
- [Spring Shell 3.1 API: `ShellContext`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/context/ShellContext.html)
- [Spring Shell 3.1 API: `InteractionMode`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/context/InteractionMode.html)
- [Spring Shell 3.1 API: `ScriptShellRunner`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/jline/ScriptShellRunner.html)
- [Spring Shell 3.3 Reference: Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.4-SNAPSHOT API: `ShellContext` and PTY detection](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/context/ShellContext.html)
- [Spring Shell v4 Migration Guide: Shell interactivity](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Java 17 API: `java.io.Console`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html)
- [Java 17 API: `System.in`, `System.out`, and `System.err`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Docker Docs: `docker run`, stdin and TTY options](https://docs.docker.com/reference/cli/docker/container/run/)

