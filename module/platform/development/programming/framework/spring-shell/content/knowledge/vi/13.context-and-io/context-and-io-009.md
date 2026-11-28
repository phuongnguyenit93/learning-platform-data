# Phân biệt stdout, stderr và đầu ra phục vụ tương tác

Một ứng dụng Spring Shell có thể chạy như REPL để người dùng nhập nhiều lệnh, hoặc chạy một command rồi kết thúc để script và CI nhận kết quả. Cùng một thông báo có thể được hiển thị trên terminal, ghi vào standard output, hoặc được gửi vào standard error. Chọn sai kênh có thể làm hỏng JSON/CSV, khiến log chen vào bảng đang hiển thị hoặc làm automation hiểu nhầm command đã thành công.

Khi thiết kế đầu ra, cần phân biệt ba khái niệm:

- **stdout (standard output):** luồng dữ liệu chính mà caller có thể đọc, lưu vào file hoặc nối vào pipeline.
- **stderr (standard error):** luồng dành cho lỗi, cảnh báo và thông tin chẩn đoán.
- **Đầu ra tương tác:** nội dung được hiển thị trong terminal như prompt, câu hỏi, trạng thái, bảng, thông báo và kết quả mà người dùng đọc trong phiên shell.

Spring Shell 3.1.6 sử dụng JLine Terminal và cơ chế ResultHandler để trình bày kết quả command. Bài học dùng phiên bản này làm mốc API, đồng thời giải thích cách tách dữ liệu máy đọc được khỏi phần hiển thị tương tác.

## 1. Vì sao phải phân biệt các kênh đầu ra?

Xét command xuất danh sách dự án ở dạng JSON:

~~~text
project list --format json
~~~

Một script có thể lưu stdout thành file rồi parse:

~~~bash
project-cli project list --format json > projects.json
jq '.[] | .name' projects.json
~~~

Nếu ứng dụng in banner Spring Boot, log khởi động hoặc dòng “Loading projects...” vào cùng stdout, file JSON không còn hợp lệ. Script thất bại dù command đã truy vấn dữ liệu đúng.

Ở chiều ngược lại, nếu mọi kết quả đều ghi vào stderr, người dùng có thể nhìn thấy chúng trên terminal nhưng pipeline không nhận được dữ liệu như mong đợi.

Với REPL, người dùng cần prompt, câu hỏi xác nhận và thông báo tiến trình. Các nội dung này cần được vẽ trong terminal theo cách phối hợp với JLine, thay vì tùy tiện ghi ra một stream toàn cục.

Do đó, đầu ra cần được thiết kế theo **mục đích của caller**:

| Mục đích | Kênh phù hợp |
|---|---|
| Kết quả chính để script xử lý | stdout |
| JSON hoặc CSV thuần | stdout |
| Lỗi cú pháp, lỗi nghiệp vụ trong CLI một lệnh | stderr hoặc result handler được cấu hình phù hợp |
| Log chẩn đoán | File log hoặc hệ thống logging |
| Prompt và câu hỏi trong REPL | Terminal/JLine |
| Bảng, tiến trình và thông báo tương tác | Terminal/JLine |
| Mã thoát | Exit status của process trong non-interactive mode |

Không nên quyết định kênh chỉ dựa trên việc nội dung “trông giống lỗi” hay “trông giống kết quả”. Hãy xem caller cần đọc nó bằng cách nào.

## 2. stdout và stderr của tiến trình Java

JDK cung cấp hai stream toàn cục:

- **System.out:** standard output.
- **System.err:** standard error.

Ví dụ:

~~~java
System.out.println("Project created: 101");
System.err.println("Cannot connect to database");
~~~

Khi chạy từ shell hệ điều hành, caller có thể chuyển hướng từng stream:

~~~bash
project-cli project create --name inventory-api \
  > result.txt \
  2> diagnostics.log
~~~

Trong ví dụ này, kết quả chính đi vào result.txt, còn lỗi và diagnostic đi vào diagnostics.log.

Có thể nối stdout vào pipeline trong khi vẫn để stderr hiển thị trên terminal:

~~~bash
project-cli project list --format json | jq '.[]'
~~~

Hoặc gộp hai stream:

~~~bash
project-cli project list > combined.log 2>&1
~~~

Khi dùng 2>&1, stderr được chuyển vào cùng đích với stdout. Đây là lựa chọn hữu ích khi lưu toàn bộ output để điều tra, nhưng không phù hợp nếu stdout cần giữ JSON/CSV thuần.

### 2.1. Hai stream không tự quyết định command thành công hay thất bại

Việc một dòng được ghi vào stderr không tự làm process trả mã khác 0. Tương tự, ghi thông báo lỗi vào stdout không làm process tự động thất bại.

Caller thường kiểm tra cả hai:

- Nội dung stdout/stderr để hiểu kết quả.
- Exit code để xác định command thành công hay không.

Trong shell script:

~~~bash
project-cli project show --id 999 > result.txt 2> error.txt
status=$?

if [ "$status" -ne 0 ]; then
  cat error.txt >&2
  exit "$status"
fi
~~~

Không dùng việc có hay không có text trong stderr làm quy tắc duy nhất để xác định thành công.

## 3. Spring Shell xử lý kết quả command như thế nào?

Trong Spring Shell, command method có thể trả về một giá trị. Kết quả đó đi qua cơ chế xử lý kết quả của shell, thường được điều phối bởi **ResultHandlerService** và các implementation của **ResultHandler**.

Ví dụ annotation legacy:

~~~java
@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod(
            key = "project show",
            value = "Show a project.")
    public String show(@ShellOption("--id") Long id) {
        ProjectSummary project = projectService.getProject(id);

        return """
                ID: %d
                Name: %s
                Status: %s
                """.formatted(
                project.id(),
                project.name(),
                project.status());
    }
}
~~~

Method trả về nội dung. Spring Shell nhận kết quả và chuyển tới result handler phù hợp để hiển thị. Cách này phù hợp khi command tạo ra một kết quả có thể trình bày sau khi xử lý xong.

Spring Shell 3.1.x cũng có **DefaultResultHandler**. Đây là handler dự phòng cho object chưa có handler chuyên biệt; nó in giá trị **Object.toString()** ra standard output. Những handler khác có thể sử dụng JLine Terminal để render nội dung theo kiểu terminal.

Điều quan trọng là **return value và ghi trực tiếp stream là hai cách xuất kết quả khác nhau**. Nếu vừa return một chuỗi vừa ghi cùng nội dung qua Terminal writer, người dùng có thể thấy kết quả bị lặp.

## 4. Dùng Terminal.writer() cho đầu ra tương tác

Spring Shell 3.1.6 khuyến nghị dùng JLine **Terminal** để ghi nội dung vào console khi command cần chủ động điều khiển việc hiển thị. **Terminal.writer()** trả về **PrintWriter**.

Ví dụ:

~~~java
import java.io.PrintWriter;

import org.jline.terminal.Terminal;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class MaintenanceCommands {

    private final Terminal terminal;

    public MaintenanceCommands(Terminal terminal) {
        this.terminal = terminal;
    }

    @ShellMethod(
            key = "maintenance refresh",
            value = "Refresh application data.")
    public void refresh() {
        PrintWriter writer = terminal.writer();

        writer.println("Refreshing application data...");
        writer.flush();

        // Thực hiện công việc cần thiết.
        // ...

        writer.println("Refresh completed.");
        writer.flush();
    }
}
~~~

Dùng Terminal khi command cần:

- Ghi nhiều dòng trong lúc xử lý.
- Hiển thị trạng thái trước khi công việc hoàn tất.
- Cập nhật nội dung tương tác.
- Phối hợp với prompt hoặc component của Spring Shell.
- Chủ động flush để nội dung xuất hiện ngay.

**Terminal.writer()** là writer của terminal do JLine quản lý. Nó là kênh hiển thị cho shell, **không phải một API riêng để ghi stderr**. Không nên giả định mọi nội dung ghi qua writer này sẽ được chuyển vào standard error.

### 4.1. Ghi qua CommandContext trong programmatic registration

Với command đăng ký bằng **CommandRegistration**, target dạng consumer nhận **CommandContext**. Context cung cấp Terminal:

~~~java
@Bean
CommandRegistration statusCommand() {
    return CommandRegistration.builder()
            .command("system status")
            .withTarget()
                .consumer(ctx -> {
                    PrintWriter writer = ctx.getTerminal().writer();

                    writer.println("System is ready");
                    writer.flush();
                })
                .and()
            .build();
}
~~~

Consumer không trả về kết quả. Nó chủ động ghi nội dung qua Terminal writer.

Nếu dùng target dạng function, giá trị return được dùng làm kết quả command và đi qua result handling. Chọn function khi muốn trả dữ liệu; chọn consumer khi cần tự điều khiển output hoặc thực hiện một hành động không có return value.

## 5. Khi nào nên dùng System.out và System.err?

Spring Shell 3.1.6 cho phép dùng trực tiếp **System.out**, vì đó là standard stream của JDK. Tuy nhiên, tài liệu khuyến nghị JLine Terminal writer khi cần ghi vào console của shell.

Có thể áp dụng quy tắc sau:

| Cách ghi | Trường hợp phù hợp |
|---|---|
| Return value từ command | Kết quả command được xử lý bởi Spring Shell |
| Terminal.writer() | Output tương tác hoặc nội dung command cần ghi trực tiếp lên terminal |
| System.out | Dữ liệu chính của process trong CLI đơn giản/non-interactive, khi đã kiểm soát result handling |
| System.err | Diagnostic hoặc lỗi process-level trong non-interactive mode |
| Logging framework | Log kỹ thuật, trace, debug và thông tin vận hành |
| Custom ResultHandler | Kiểu kết quả cần format hoặc route riêng |

Trong một REPL đang chạy, ghi trực tiếp System.out hoặc System.err có thể chen vào prompt, bảng hoặc màn hình do JLine quản lý. Khi đó, ưu tiên Terminal writer hoặc result handling.

Trong một command chạy một lần, System.out và System.err có thể hữu ích vì caller hệ điều hành chuyển hướng chúng độc lập. Nhưng cần kiểm tra cách Spring Shell render return value để tránh output trùng.

## 6. Giữ stdout thuần cho JSON và CSV

Khi một command hỗ trợ output máy đọc được, stdout nên chỉ chứa payload đã công bố.

Ví dụ command trả JSON:

~~~java
@ShellComponent
public class ProjectExportCommands {

    private final ProjectService projectService;

    public ProjectExportCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod(
            key = "project export",
            value = "Export projects as JSON.")
    public String export() {
        return projectService.exportJson();
    }
}
~~~

Caller có thể lưu kết quả:

~~~bash
project-cli project export > projects.json
~~~

Một số nội dung không nên chen vào JSON stdout:

- Banner Spring Boot.
- Log startup.
- Dòng “Starting export...”.
- Spinner hoặc progress bar.
- Warning không thuộc schema.
- Stack trace.
- Prompt tương tác.

Nếu cần thông báo tiến trình, hãy đưa nó vào logging hoặc stderr theo contract. Nếu cần ghi log, có thể chuyển log sang file:

~~~yaml
logging:
  file:
    name: logs/project-cli.log
~~~

Nếu cần tắt console logging để bảo vệ stdout, Spring Shell 3.1.6 hướng dẫn cấu hình:

~~~yaml
logging:
  pattern:
    console: ""
  file:
    name: logs/project-cli.log
~~~

Có thể tắt banner Spring Boot khi command cần output máy đọc thuần:

~~~yaml
spring:
  main:
    banner-mode: "off"
~~~

Sau khi cấu hình, vẫn phải chạy process thật và kiểm tra stdout. Không kết luận stdout thuần chỉ từ việc đã thêm property.

## 7. Dùng stderr cho diagnostic của non-interactive command

Trong CLI một lệnh, stderr thường phù hợp với thông báo lỗi dành cho caller hoặc người vận hành.

Ví dụ:

~~~java
public void reportFailure(String message) {
    System.err.println("ERROR: " + message);
}
~~~

Tuy nhiên, với command Spring Shell, nên ưu tiên exception handling/result handling khi lỗi thuộc quá trình xử lý command. Cách này giúp message và exit code được quản lý cùng nhau. Lưu ý: message trong kết quả resolver được chuyển qua result handling để hiển thị trên console; nó không tự động được gửi vào stderr. Nếu contract yêu cầu tách stderr, cần định tuyến diagnostic rõ ràng như ví dụ ở mục 8.2.

Nếu tự ghi stderr, cần quyết định rõ:

- Command có tiếp tục chạy hay kết thúc?
- Process sẽ trả exit code nào?
- Có cần giữ stdout trống khi thất bại không?
- Có cần ghi stack trace hay chỉ thông báo ngắn?
- Có cần log đầy đủ cause vào file không?

Ví dụ một lỗi validation có thể chỉ cần một dòng:

~~~text
ERROR: Project name is required
~~~

Còn stack trace đầy đủ có thể dành cho log hoặc chế độ debug. Không nên bắt người dùng CLI đọc một stack trace dài cho lỗi nhập liệu thông thường.

Trong interactive REPL, dùng stderr trực tiếp có thể làm hỏng bố cục màn hình. Hãy dùng exception resolver hoặc Terminal-aware result handler để trình bày lỗi theo cách nhất quán với shell.

## 8. Xử lý exception bằng ResultHandler và CommandExceptionResolver

Spring Shell 3.1.6 chuyển exception chưa được xử lý qua **ResultHandlerService**, sau đó tới **ResultHandler**. Có thể dùng **CommandExceptionResolver** để ánh xạ exception thành message và exit code.

Ví dụ resolver:

~~~java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

public class ProjectExceptionResolver
        implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception exception) {
        if (exception instanceof ProjectNotFoundException notFound) {
            return CommandHandlingResult.of(
                    "Project not found: " + notFound.getProjectId(),
                    3);
        }

        return null;
    }
}
~~~

Đăng ký resolver thành bean:

~~~java
@Bean
ProjectExceptionResolver projectExceptionResolver() {
    return new ProjectExceptionResolver();
}
~~~

**CommandHandlingResult** có thể chứa message và exit code:

~~~java
CommandHandlingResult result =
        CommandHandlingResult.of("Project not found", 3);
~~~

Exit code trong CommandHandlingResult chỉ có ý nghĩa khi shell chạy ở non-interactive mode. Trong REPL, người dùng có thể nhận thông báo lỗi rồi tiếp tục nhập command khác.

### 8.1. @ExceptionResolver trong mô hình annotation legacy

Với command khai báo bằng **@ShellComponent**, có thể đặt method **@ExceptionResolver** trong component:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod("Show a project.")
    public String show(@ShellOption("--id") Long id) {
        // ...
        return "Project details";
    }

    @ExceptionResolver
    public CommandHandlingResult handleNotFound(
            ProjectNotFoundException exception) {
        return CommandHandlingResult.of(
                "Project not found: " + exception.getProjectId(),
                3);
    }
}
~~~

Resolver có thể trả về:

- **String:** message được ghi ra console; Spring Shell 3.1.6 dùng exit code 1.
- **CommandHandlingResult:** message và exit code được xác định rõ.
- **void:** exception được xem là đã xử lý xong; mặc định exit code là 0, trừ khi có cấu hình exit code riêng.

Điểm cuối rất quan trọng: nếu resolver bắt lỗi thất bại rồi trả về void mà không đặt mã lỗi, automation có thể nhận exit code 0 và hiểu nhầm command đã thành công.

### 8.2. Khi contract yêu cầu stderr riêng trong non-interactive mode

`CommandHandlingResult` chứa message được gửi qua result handling của Spring Shell, không phải một cam kết rằng message sẽ nằm ở stderr. Nếu CLI một lệnh cần giữ stdout trống và gửi diagnostic vào stderr, có thể chủ động ghi `System.err` trong resolver rồi trả về kết quả chỉ có exit code:

~~~java
@Bean
CommandExceptionResolver projectExceptionResolver() {
    return exception -> {
        if (exception instanceof ProjectNotFoundException notFound) {
            System.err.println(
                    "Project not found: " + notFound.getProjectId());
            return CommandHandlingResult.of(null, 3);
        }
        return null;
    };
}
~~~

Cách này dành cho non-interactive mode, nơi process stream được caller chuyển hướng độc lập. Trong REPL, ưu tiên để Spring Shell hiển thị lỗi qua Terminal/result handler; ghi trực tiếp stderr có thể chen vào màn hình do JLine quản lý. Khi dùng resolver ghi stderr, không đồng thời trả lại cùng message trong `CommandHandlingResult`, nếu không nội dung có thể xuất hiện hai lần hoặc sai stream.

## 9. Phân biệt lỗi hiển thị với exit code

Một lỗi có thể được trình bày bằng màu đỏ, nhưng màu sắc không quyết định process thất bại. Exit code được xác định bởi result/exception handling và chỉ được dùng làm kết quả tiến trình trong non-interactive mode.

Spring Shell 3.1.6 có mapping mặc định:

| Tình huống | Exit code mặc định |
|---|---:|
| Parse option thất bại | 2 |
| Lỗi chung | 1 |
| Thành công | 0 |

Có thể tùy chỉnh mapping qua CommandRegistration hoặc dùng ExitCodeGenerator theo tích hợp Spring Boot.

Không nên dựa vào message để đoán exit code. Hãy kiểm tra cả message lẫn process status.

Một quy ước tốt cho CLI:

- 0: command hoàn tất thành công.
- Khác 0: command thất bại, input không hợp lệ hoặc điều kiện nghiệp vụ không được đáp ứng.
- stdout: kết quả chính.
- stderr: diagnostic hoặc lỗi process-level.
- Log: thông tin kỹ thuật chi tiết.

## 10. Đầu ra trong interactive mode

Trong REPL, output hướng đến người đang tương tác. Nó có thể bao gồm:

- Prompt hiện tại.
- Câu hỏi nhập dữ liệu.
- Lựa chọn menu.
- Trạng thái đang xử lý.
- Kết quả command.
- Cảnh báo và thông báo lỗi.
- Bảng và nội dung có màu.

Ví dụ một phiên:

~~~text
project-cli:> project create
Project name: inventory-api
Owner: platform

Creating project...
Created project 101: inventory-api

project-cli:>
~~~

Các prompt và component tương tác thuộc UI của shell. Khi cần nhập dữ liệu, dùng component hoặc input abstraction của Spring Shell thay vì tự đọc System.in trong command. Cách này giúp shell kiểm soát input, phím điều hướng và terminal state.

Không nên in progress bằng nhiều dòng System.out.println() trong khi JLine đang điều khiển prompt. Nếu cần hiển thị trạng thái, dùng Terminal writer hoặc component UI phù hợp.

### 10.1. Đầu ra tương tác không phải output máy đọc

Một bảng được thiết kế để người dùng đọc có thể có border, màu, căn cột và header. Đây không phải schema ổn định cho script parse.

Nếu command cần hỗ trợ cả người dùng và automation, cung cấp lựa chọn format:

~~~text
project list --format table
project list --format json
~~~

- **table:** dành cho người dùng terminal.
- **json:** dành cho script và công cụ khác.

Không cố gắng dùng cùng một chuỗi output vừa đẹp cho terminal vừa bảo đảm là JSON/CSV hợp lệ.

## 11. Prompt và input phải phù hợp execution mode

Spring Shell phân biệt interactive và non-interactive mode. Một prompt có thể hợp lý trong REPL nhưng khiến script bị treo vì không có người trả lời.

Ví dụ:

~~~java
@ShellMethod("Delete a project.")
public String delete(@ShellOption("--id") Long id) {
    // Hỏi người dùng xác nhận trong REPL.
    // ...
    return "Deleted";
}
~~~

Nếu command được gọi từ script, nên yêu cầu option xác nhận tường minh:

~~~text
project delete --id 101 --force
~~~

Thiết kế cần xác định:

- Interactive mode có hỏi xác nhận không?
- Non-interactive mode có yêu cầu --force không?
- Nếu thiếu option thì trả lỗi hay từ chối thao tác?
- Prompt có thể được vô hiệu hóa không?
- Output khi từ chối có message và exit code nào?

Không dùng prompt như một cách thay thế validation. Caller non-interactive cần biết chính xác phải truyền option nào.

## 12. Logging có thể làm nhiễu output shell

Spring Boot logging trên console có thể xen vào output command. Trong một shell tương tác, log startup hoặc log từ service có thể chen giữa prompt và kết quả.

Spring Shell 3.1.6 khuyến nghị điều chỉnh logging cho shell application. Có thể tắt console logging bằng logging.pattern.console rỗng và ghi log vào file:

~~~yaml
logging:
  pattern:
    console: ""
  file:
    name: logs/shell.log
  level:
    root: INFO
~~~

Khi cần debug Spring Shell:

~~~yaml
logging:
  file:
    name: logs/shell.log
  level:
    org.springframework.shell: DEBUG
~~~

Các nguyên tắc:

- Dùng logger cho log kỹ thuật, không dùng logger thay output command.
- Không log payload JSON/CSV vào console nếu stdout là dữ liệu chính.
- Không ghi credential, token hoặc dữ liệu nhạy cảm vào log.
- Tách mức INFO/WARN/ERROR theo mục đích vận hành.
- Bật debug trong môi trường chẩn đoán, không mặc định trong mọi lần chạy.

Nếu logging vẫn xuất hiện trên console, kiểm tra cấu hình logging thực tế và process output; đừng giả định logger luôn ghi vào stderr hoặc stdout theo một quy tắc cố định.

## 13. Flush và buffering

**PrintWriter** và các stream có thể buffer dữ liệu. Nếu command ghi trạng thái trong khi xử lý lâu, người dùng có thể không nhìn thấy dòng vừa ghi cho đến khi buffer được flush.

Ví dụ:

~~~java
PrintWriter writer = terminal.writer();

writer.println("Starting export...");
writer.flush();

// Thực hiện export.

writer.println("Export completed.");
writer.flush();
~~~

Flush đặc biệt hữu ích khi:

- Hiển thị trạng thái trước tác vụ dài.
- Ghi prompt hoặc câu hỏi cần phản hồi.
- Gửi output qua pipe mà caller đang chờ.
- Command sẽ kết thúc ngay sau khi ghi.

Không cần flush sau từng ký tự hoặc mọi thao tác nhỏ. Flush quá thường xuyên có thể làm giảm hiệu năng. Hãy flush tại ranh giới có ý nghĩa với người dùng.

## 14. Newline, encoding và output ổn định

Output là một contract. Với script, cần quan tâm:

- Encoding, thường là UTF-8.
- Newline cuối dòng.
- Cách biểu diễn null và chuỗi rỗng.
- Decimal separator và locale.
- Timezone của ngày giờ.
- Thứ tự field trong JSON hoặc cột CSV.
- ANSI color có được bật hay không.
- Ký tự Unicode và độ rộng hiển thị.

Nếu command xuất JSON, dùng JSON serializer thay vì tự nối chuỗi. Điều này tránh lỗi escape dấu nháy, newline, backslash và Unicode.

Ví dụ không nên:

~~~java
return "{\"name\":\"" + project.getName() + "\"}";
~~~

Nên dùng serializer đã có trong ứng dụng:

~~~java
return objectMapper.writeValueAsString(projectSummary);
~~~

Với CSV, dùng thư viện hoặc writer có quy tắc quote và escape rõ ràng. Không giả định dấu phẩy trong một trường dữ liệu sẽ luôn an toàn nếu chỉ nối chuỗi thủ công.

## 15. ANSI color và terminal rendering

Màu sắc có thể giúp người dùng nhận biết trạng thái, nhưng mã điều khiển ANSI có thể làm output khó parse khi redirect vào file.

Quy tắc thực tế:

- Màu và style chỉ dùng cho output hướng người dùng.
- JSON/CSV không chứa ANSI escape sequence.
- Không tự ghép ANSI code vào dữ liệu nghiệp vụ.
- Dùng API styling của JLine/Spring Shell khi cần màu.
- Kiểm tra output khi stdout được redirect vào file.
- Có chế độ plain text nếu automation cần output không màu.

Một file log hoặc JSON chứa chuỗi ESC[31m có thể gây lỗi parser hoặc hiển thị ký tự lạ. Hãy test cả trường hợp terminal tương tác và trường hợp output được chuyển hướng.

## 16. Kiểm thử từng kênh đầu ra

Một unit test gọi trực tiếp method command không đủ để xác minh output stream. Nên chia kiểm thử thành các lớp:

| Loại test | Điều cần xác minh |
|---|---|
| Unit test command/service | Giá trị trả về và quy tắc xử lý |
| Shell test | Command registration, kết quả và màn hình tương tác |
| Process integration test | stdout, stderr và exit code thật |
| Script test | Chuyển hướng stream, pipeline và hành vi khi lỗi |

**ShellTestClient** và **ShellAssertions** phù hợp để kiểm tra output được render trong shell giả lập. Nhưng để xác minh stdout/stderr của process hệ điều hành, hãy chạy executable thật và redirect hai stream riêng biệt.

### 16.1. Kiểm thử process bằng ProcessBuilder

Ví dụ:

~~~java
@Test
void commandWritesDataAndDiagnosticToSeparateStreams() throws Exception {
    Path stdout = tempDir.resolve("stdout.txt");
    Path stderr = tempDir.resolve("stderr.txt");

    Process process = new ProcessBuilder(
            javaExecutable,
            "-jar",
            cliJar.toString(),
            "project", "show",
            "--id", "999")
            .redirectOutput(stdout.toFile())
            .redirectError(stderr.toFile())
            .start();

    boolean completed = process.waitFor(10, TimeUnit.SECONDS);

    if (!completed) {
        process.destroyForcibly();
        process.waitFor(5, TimeUnit.SECONDS);
        fail("CLI did not finish before timeout");
    }

    int exitCode = process.exitValue();
    String out = Files.readString(stdout);
    String err = Files.readString(stderr);

    assertThat(exitCode).isEqualTo(3);
    assertThat(out).isEmpty();
    assertThat(err).contains("Project not found");
}
~~~

Ví dụ giả định test đã cung cấp tempDir, javaExecutable, cliJar, JUnit và AssertJ imports. Exit code 3 là contract minh họa, cần thay bằng mã thực tế của ứng dụng.

Để assertion stdout rỗng và stderr có message khớp với ví dụ, process test cần chạy cùng resolver định tuyến stderr ở mục 8.2, đồng thời tắt banner và console logging như các cấu hình ở trên. Nếu dùng resolver trả message trong CommandHandlingResult, message sẽ đi qua result handling và test phải kiểm tra kênh console thực tế của cấu hình đó.

Test này kiểm tra ba điều độc lập:

1. stdout có đúng payload hay không.
2. stderr có diagnostic đúng hay không.
3. Process có trả đúng exit code hay không.

Dùng timeout để tránh test treo nếu command không thoát. Nếu process tạo nhiều output, dùng redirect file hoặc đọc hai stream đồng thời để tránh pipe bị đầy.

## 17. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách tổ chức tốt hơn |
|---|---|---|
| Dùng System.out.println() cho mọi output | Không kiểm soát được UI của REPL | Return result hoặc dùng Terminal writer |
| Ghi lỗi vào stdout | Script parse output thất bại | Dùng error handling hoặc stderr theo contract |
| Ghi mọi thứ vào stderr | Pipeline không nhận kết quả chính | Giữ dữ liệu chính ở stdout |
| Dùng Terminal writer như stderr | Nhầm terminal output với error stream | Xác định rõ process stream cần dùng |
| Return chuỗi rồi ghi cùng chuỗi qua Terminal | Output bị lặp | Chọn một đường xuất |
| Log vào console khi xuất JSON | JSON không còn hợp lệ | Ghi log vào file hoặc tách stream |
| In stack trace cho mọi lỗi nhập liệu | Output khó đọc | Thông báo ngắn, giữ cause trong log |
| Prompt trong non-interactive mode | Script có thể treo | Dùng option bắt buộc hoặc --force |
| Không flush output trạng thái | Người dùng tưởng command bị treo | Flush tại mốc cần hiển thị |
| Gắn ANSI vào JSON/CSV | Caller không parse được | Tách format terminal và machine-readable |
| Dùng void exception resolver cho lỗi thất bại | Có thể nhận exit code 0 | Trả CommandHandlingResult có mã lỗi |

## 18. Quy trình thiết kế output cho một command mới

Trước khi triển khai command, trả lời các câu hỏi:

1. Command chạy trong REPL, non-interactive hay cả hai?
2. Caller chính là người dùng hay script?
3. Kết quả chính là text, table, JSON, CSV hay file?
4. Kết quả được trả về qua ResultHandler hay ghi trực tiếp?
5. Có cần Terminal writer để hiển thị trạng thái hoặc prompt không?
6. Lỗi nào cần hiển thị cho người dùng?
7. Diagnostic nào nên ghi vào stderr hoặc log file?
8. Exit code nào đại diện thành công và từng loại lỗi?
9. Có banner/log/progress nào làm nhiễu stdout không?
10. Output có ổn định khi redirect vào file hoặc pipe không?
11. Có cần tắt prompt, color hoặc interactive UI trong script không?
12. Test nào sẽ kiểm tra màn hình, stream và exit code?

Sau đó ghi contract ngắn cho command:

| Thuộc tính | Ví dụ |
|---|---|
| Command | project export |
| Mode | Non-interactive |
| Input | --format json |
| stdout | JSON array |
| stderr | Lỗi kết nối và diagnostic |
| Exit code | 0 thành công, 1 lỗi chung |
| Prompt | Không |
| Logging | File |
| Color | Không |
| Test | Process test với redirect hai stream |

## 19. Bài thực hành: tách kết quả và diagnostic

Tạo command project export có hai trường hợp:

- Thành công: xuất JSON ra stdout.
- Thất bại: không xuất JSON dở dang, ghi thông báo lỗi ra stderr và trả exit code khác 0.

Yêu cầu:

1. Dùng service trả DTO hoặc dữ liệu có cấu trúc.
2. Serialize dữ liệu bằng ObjectMapper.
3. Để command trả kết quả qua result handling hoặc dùng output writer theo thiết kế đã chọn.
4. Cấu hình logging để không chen vào stdout.
5. Không in banner trong chế độ machine-readable.
6. Ánh xạ exception sang message và exit code bằng CommandExceptionResolver.
7. Viết shell test để xác minh command được đăng ký và output hiển thị.
8. Viết process test để redirect stdout/stderr riêng.
9. Kiểm tra exit code khi thành công và thất bại.
10. Chạy command qua pipe và xác minh JSON parse được.

Kịch bản thành công:

~~~bash
project-cli project export > projects.json 2> diagnostics.log
jq 'length' projects.json
~~~

Kịch bản thất bại:

~~~bash
project-cli project export > projects.json 2> diagnostics.log
status=$?

if [ "$status" -ne 0 ]; then
  echo "Export failed with code $status" >&2
  exit "$status"
fi
~~~

Đừng chỉ kiểm tra rằng terminal có hiển thị dòng “Export completed”. Hãy xác minh payload, diagnostic và exit code đúng kênh.

## 20. Checklist trước khi phát hành

- [ ] Đã xác định output dành cho người dùng hay máy đọc.
- [ ] Đã phân biệt stdout, stderr và JLine Terminal writer.
- [ ] Command return value được xử lý qua result handling.
- [ ] Không vừa return vừa ghi lặp cùng một nội dung.
- [ ] JSON/CSV stdout không chứa banner, log, prompt hoặc ANSI.
- [ ] Diagnostic và lỗi có kênh được quy định rõ.
- [ ] Logging không chen vào output command.
- [ ] Prompt chỉ xuất hiện trong mode phù hợp.
- [ ] Non-interactive command không phụ thuộc stdin tương tác.
- [ ] Terminal writer được flush tại các mốc cần thiết.
- [ ] Encoding, newline và format output ổn định.
- [ ] Exception resolver trả exit code đúng khi thất bại.
- [ ] Không dùng void resolver khiến lỗi bị coi là thành công.
- [ ] Có shell test cho nội dung hiển thị.
- [ ] Có process test cho stdout, stderr và exit code.
- [ ] Đã kiểm tra output khi redirect và khi dùng pipeline.

## 21. Kết luận

stdout, stderr và đầu ra tương tác phục vụ những caller khác nhau. stdout mang dữ liệu chính để script hoặc pipeline xử lý; stderr dành cho diagnostic và lỗi process-level; JLine Terminal writer phục vụ nội dung hiển thị trong shell đang chạy.

Trong Spring Shell 3.1.6, command có thể trả kết quả qua result-handling pipeline hoặc ghi chủ động qua Terminal.writer(). Dùng System.out và System.err khi cần làm việc với stream của tiến trình, nhưng tránh ghi tùy tiện vào các stream toàn cục trong REPL. Đưa log kỹ thuật ra file hoặc cấu hình riêng để không làm nhiễu output.

Với non-interactive mode, kiểm tra message, stdout, stderr và exit code cùng nhau. Với interactive mode, kiểm tra prompt, bảng, trạng thái và cách terminal render nội dung. Khi tách đúng các kênh, command vừa dễ dùng với con người vừa đáng tin cậy trong script và CI.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Writing to the Console](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1.6 Reference: Exception Handling and Exit Codes](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1.6 Reference: Logging](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: CommandContext](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandContext.html)
- [Spring Shell 3.1 API: CommandHandlingResult](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandHandlingResult.html)
- [Spring Shell 3.1 API: CommandExceptionResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandExceptionResolver.html)
- [Spring Shell 3.1 API: DefaultResultHandler](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/result/DefaultResultHandler.html)
- [Spring Shell 3.1 API: ResultHandler](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/ResultHandler.html)

