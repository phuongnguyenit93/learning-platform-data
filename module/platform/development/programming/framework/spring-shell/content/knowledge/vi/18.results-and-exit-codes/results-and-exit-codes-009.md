# Phân biệt lỗi không tìm thấy lệnh với lỗi trong phương thức xử lý

Khi chạy một ứng dụng Spring Shell, cùng một dòng nhập sai có thể thất bại ở những giai đoạn khác nhau. Người dùng gõ sai tên command thì shell không tìm thấy command để gọi. Người dùng gõ đúng tên nhưng phương thức xử lý gặp lỗi thì command đã được tìm thấy và method đã bắt đầu chạy. Hai trường hợp có nguyên nhân, cơ chế xử lý và cách chẩn đoán khác nhau.

Trong mô hình annotation legacy của Spring Shell 3.x, lỗi không tìm thấy command được biểu diễn bằng `CommandNotFound` và xử lý bởi `CommandNotFoundResultHandler`. Exception phát sinh trong command method đi qua cơ chế exception resolving và result handling. Hiểu rõ ranh giới này giúp chọn đúng nơi tùy biến thông báo, ánh xạ mã thoát và viết kiểm thử.

Bài học thuộc phạm vi SPRING_SHELL: xây dựng CLI với command, tham số, validation, trợ giúp, tự hoàn thành, kết quả và mã thoát. Nội dung tập trung vào Spring Shell 3.1.x, đồng thời nêu những thay đổi quan trọng trong Spring Shell 4.x để tránh trộn API giữa hai thế hệ.

## 1. Vòng đời xử lý một command

Trước khi phân loại lỗi, cần hiểu command đi qua những bước nào:

~~~mermaid
flowchart TD
    A["Người dùng nhập dòng lệnh"] --> B["Parser phân tích token và option"]
    B --> C["Tìm CommandRegistration"]
    C --> D{"Có command phù hợp?"}
    D -- "Không" --> E["CommandNotFound"]
    E --> F["CommandNotFoundResultHandler"]
    D -- "Có" --> G{"Command khả dụng?"}
    G -- "Không" --> H["CommandNotCurrentlyAvailable"]
    G -- "Có" --> I["Resolve và convert tham số"]
    I --> J{"Tham số hợp lệ?"}
    J -- "Không" --> K["Parser / conversion / validation error"]
    J -- "Có" --> L["Gọi command method"]
    L --> M{"Method thành công?"}
    M -- "Không" --> N["ExceptionResolver / ThrowableResultHandler"]
    M -- "Có" --> O["ResultHandler xử lý kết quả"]
~~~

Có thể chia thành bốn nhóm lỗi chính:

1. **Không tìm thấy command:** shell không tìm được command registration tương ứng với tên người dùng nhập.
2. **Không thể chuẩn bị tham số:** command tồn tại nhưng option, argument, kiểu dữ liệu hoặc validation không hợp lệ; method có thể chưa được gọi.
3. **Command không khả dụng:** command tồn tại nhưng điều kiện trạng thái chưa cho phép thực thi.
4. **Lỗi trong phương thức xử lý:** command đã được tìm thấy, tham số đã được chuẩn bị và method ném exception khi chạy nghiệp vụ.

Đề bài tập trung vào nhóm 1 và nhóm 4. Hai nhóm còn lại được trình bày để người đọc không nhầm chúng với hai trường hợp đó.

## 2. Lỗi không tìm thấy command là gì?

Lỗi không tìm thấy command xảy ra khi Spring Shell không thể ánh xạ dòng nhập thành một command đã đăng ký. Command method không được gọi vì shell chưa tìm được target để thực thi.

Ví dụ ứng dụng có command:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(value = "List projects.", key = "project list")
    public String list() {
        return "Project list";
    }
}
~~~

Người dùng nhập sai tên:

~~~text
shell:> projcet list
No command found for 'projcet list'
~~~

Tên `projcet list` không khớp command `project list`, vì vậy Spring Shell xử lý tình huống này như command không tồn tại.

### 2.1. CommandNotFound trong Spring Shell 3.x

Trong API Spring Shell 3.1.x, `org.springframework.shell.CommandNotFound` là một `RuntimeException` được tạo khi không có command nào ánh xạ được với input.

Exception này lưu một số thông tin hữu ích:

| Thông tin | Phương thức |
|---|---|
| Các từ đã phân tích | `getWords()` |
| Danh sách registration đã biết tại thời điểm tạo lỗi | `getRegistrations()` |
| Dòng nhập thô của người dùng | `getText()` |
| Thông báo lỗi | `getMessage()` |

Dù `CommandNotFound` kế thừa `RuntimeException`, không nên xem nó là exception do command method ném ra. Nó là tín hiệu của framework cho biết bước tìm command thất bại.

### 2.2. Result handler mặc định

Spring Shell 3.x đăng ký `CommandNotFoundResultHandler` để xử lý kết quả kiểu `CommandNotFound`. Thông báo mặc định có dạng:

~~~text
shell:>missing
No command found for 'missing'
~~~

`CommandNotFoundResultHandler` là một `ResultHandler<CommandNotFound>`. Nó sử dụng `CommandNotFoundMessageProvider` để tạo thông báo hiển thị.

Cơ chế này tách việc tìm command khỏi việc định dạng thông báo. Vì vậy, khi muốn đổi câu thông báo “không tìm thấy command”, hãy tùy biến message provider tương ứng. Không dùng `@ExceptionResolver` của command method cho trường hợp này.

## 3. Lỗi trong phương thức xử lý là gì?

Lỗi trong phương thức xử lý xảy ra sau khi Spring Shell đã tìm thấy command và bắt đầu gọi method được đăng ký.

Ví dụ:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(value = "Show a project.", key = "project show")
    public String show(@ShellOption("--id") long id) {
        if (id == 404) {
            throw new IllegalStateException("Project service is unavailable");
        }

        return "Project " + id;
    }
}
~~~

Người dùng nhập:

~~~text
shell:> project show --id 404
~~~

Tên command hợp lệ, option `--id` cũng có thể chuyển thành `long`. Spring Shell gọi `show(404)`, sau đó method ném `IllegalStateException`.

Đây là lỗi trong quá trình thực thi command. Nó không phải `CommandNotFound`, bởi command `project show` đã được tìm thấy.

Các nguyên nhân thường gặp:

- Không tìm thấy bản ghi trong repository.
- Dịch vụ bên ngoài không phản hồi.
- Không thể đọc hoặc ghi file.
- Dữ liệu nghiệp vụ vi phạm điều kiện.
- Lỗi lập trình như `NullPointerException` hoặc `IllegalStateException`.
- Một exception từ tầng service được ném lên hoặc bọc trong exception khác.

## 4. Phân biệt hai loại lỗi

| Tiêu chí | Không tìm thấy command | Exception trong command method |
|---|---|---|
| Giai đoạn xảy ra | Tìm command registration | Sau khi gọi method |
| Command có tồn tại không? | Không có registration khớp input | Có command registration |
| Method xử lý có chạy không? | Không | Có |
| Tín hiệu trong Spring Shell 3.x | `CommandNotFound` | Exception do method hoặc tầng nghiệp vụ ném ra |
| Bộ xử lý mặc định | `CommandNotFoundResultHandler` | Exception resolver và `ThrowableResultHandler` |
| Nơi tùy biến thông báo | `CommandNotFoundMessageProvider` | `@ExceptionResolver` hoặc `CommandExceptionResolver` |
| Hướng điều tra | Tên command, alias, registration, component scan | Stack trace, cause, service, dữ liệu và nghiệp vụ |

Ví dụ đối chiếu:

~~~text
shell:> project sho
No command found for 'project sho'

shell:> project show --id 404
Project 404 was not found
~~~

Dòng đầu không khớp command đã đăng ký. Dòng thứ hai gọi được command và nhận thông báo lỗi nghiệp vụ do exception resolver xử lý.

## 5. Những trường hợp gần giống nhưng không phải hai lỗi trên

Khi chẩn đoán, cần phân biệt thêm command unavailable và lỗi tham số.

### 5.1. Command tồn tại nhưng chưa khả dụng

Spring Shell có thể đăng ký command nhưng tạm thời không cho phép gọi do trạng thái ứng dụng.

Ví dụ command `download` chỉ hoạt động sau khi kết nối:

~~~java
@ShellComponent
public class RemoteCommands {

    private boolean connected;

    @ShellMethod("Connect to the server.")
    public String connect() {
        connected = true;
        return "Connected";
    }

    @ShellMethod("Download data.")
    public String download() {
        return "Download completed";
    }

    public Availability downloadAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Trước khi kết nối:

~~~text
shell:> download
Command 'download' exists but is not currently available because you are not connected.
~~~

Command `download` vẫn tồn tại và được đăng ký. Nó chỉ chưa khả dụng. Spring Shell 3.x biểu diễn trường hợp này bằng `CommandNotCurrentlyAvailable`.

Không xử lý trường hợp này như command không tìm thấy hoặc lỗi nghiệp vụ trong method. Cần kiểm tra `Availability` và trạng thái ứng dụng.

### 5.2. Command tồn tại nhưng option hoặc argument không hợp lệ

Ví dụ:

~~~text
shell:> project show --id abc
~~~

Nếu tham số `id` có kiểu `long`, chuỗi `abc` không thể chuyển đổi thành số. Lỗi xảy ra trong quá trình parse hoặc resolve tham số, trước khi method được gọi.

Tương tự, các tình huống sau không phải lỗi không tìm thấy command:

- Thiếu option bắt buộc.
- Dùng option không được khai báo.
- Không chuyển đổi được chuỗi sang kiểu Java.
- Validation của tham số thất bại.
- Số lượng argument không đúng arity.

Spring Shell 3.x có resolver và result handler dành cho các lỗi parsing, conversion và validation. Không bắt những lỗi này bằng một `catch` trong command method vì method có thể chưa được gọi.

Với lỗi Bean Validation của tham số, Spring Shell 3.x có `ParameterValidationExceptionResultHandler` để hiển thị lỗi validation trên terminal. Đây vẫn là lỗi ở bước chuẩn bị tham số, trước khi command method thực thi.

### 5.3. Lỗi khi khởi động ứng dụng

Nếu Spring không tạo được bean chứa `@ShellComponent`, command có thể không được đăng ký. Người dùng nhập command đó sau khi ứng dụng khởi động có thể nhận lỗi không tìm thấy command.

Trong trường hợp này, nguyên nhân gốc nằm ở startup hoặc component scanning. Cần kiểm tra log khởi động, package scan, điều kiện auto-configuration và trạng thái bean.

## 6. Tùy biến thông báo command không tìm thấy

Trong Spring Shell 3.x, có thể đăng ký một bean `CommandNotFoundMessageProvider` để thay đổi thông báo mặc định.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.result.CommandNotFoundMessageProvider;

@Configuration
public class ShellErrorConfiguration {

    @Bean
    CommandNotFoundMessageProvider commandNotFoundMessageProvider() {
        return context -> {
            String input = context.text();

            return "Unknown command '" + input
                    + "'. Run 'help' to see available commands.";
        };
    }
}
~~~

Khi người dùng nhập một command không tồn tại, message provider nhận `ProviderContext` chứa thông tin về input và các command registration đã biết.

Các thông tin có thể dùng trong context gồm:

- `commands()`: các từ command đã phân tích.
- `error()`: lỗi tương ứng, thường là `CommandNotFound`.
- `registrations()`: các registration được biết tại thời điểm xử lý.
- `text()`: dòng nhập thô.

Chỉ nên đưa thông tin hữu ích cho người dùng vào thông báo. Không cần in toàn bộ danh sách registration hoặc stack trace khi người dùng chỉ gõ sai tên command.

Việc tùy biến `CommandNotFoundMessageProvider` chỉ đổi thông báo của lỗi không tìm thấy command. Nó không bắt exception do command method ném ra và không thay thế `CommandExceptionResolver`.

## 7. Xử lý exception từ command method bằng @ExceptionResolver

Với command được khai báo bằng `@ShellComponent` và `@ShellMethod`, Spring Shell 3.x cho phép khai báo method xử lý exception bằng `@ExceptionResolver`.

Ví dụ một exception nghiệp vụ:

~~~java
public class ProjectNotFoundException extends RuntimeException {

    private final long projectId;

    public ProjectNotFoundException(long projectId) {
        super("Project " + projectId + " was not found");
        this.projectId = projectId;
    }

    public long getProjectId() {
        return projectId;
    }
}
~~~

Command ném exception khi không tìm thấy dự án:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod(value = "Show a project.", key = "project show")
    public String show(@ShellOption("--id") long id) {
        return projectService.findById(id)
                .map(Project::toString)
                .orElseThrow(() -> new ProjectNotFoundException(id));
    }
}
~~~

Thêm exception resolver trong cùng `@ShellComponent`:

~~~java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
public CommandHandlingResult handleProjectNotFound(
        ProjectNotFoundException exception) {

    return CommandHandlingResult.of(
            "Project " + exception.getProjectId() + " was not found",
            4);
}
~~~

Khi `show()` ném `ProjectNotFoundException`, resolver phù hợp có thể chuyển exception thành thông báo thân thiện và mã thoát `4` cho chế độ non-interactive.

Điểm quan trọng:

- Method resolver không phải command; không đánh dấu nó bằng `@ShellMethod`.
- Tham số exception nên khai báo đúng kiểu cần xử lý.
- `@ExceptionResolver` được dùng cho các method trong command component.
- Nếu exception được bọc trong một exception khác, Spring Shell có thể dò theo cause chain.
- Khi có nhiều resolver phù hợp, exception ở cấp gốc thường được ưu tiên hơn exception chỉ xuất hiện trong cause.

Không nên dùng một resolver bắt mọi `Throwable` rồi trả về thông báo chung cho tất cả lỗi. Làm như vậy dễ che khuất lỗi lập trình và làm mất thông tin chẩn đoán.

## 8. Chọn kết quả và mã thoát trong @ExceptionResolver

Trong Spring Shell 3.x, `@ExceptionResolver` hỗ trợ một số kiểu trả về:

| Kiểu trả về | Ý nghĩa |
|---|---|
| `String` | Chuỗi được hiển thị trên shell; mặc định mã thoát là `1` |
| `CommandHandlingResult` | Cho phép trả thông báo và mã thoát cụ thể |
| `void` | Resolver được xem là đã xử lý exception; mặc định mã thoát là `0` |

Ví dụ trả về chuỗi với mã thoát riêng:

~~~java
import org.springframework.shell.command.annotation.ExitCode;
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
@ExitCode(code = 4)
public String handleProjectNotFound(ProjectNotFoundException exception) {
    return "Project " + exception.getProjectId() + " was not found";
}
~~~

Hoặc trả về `CommandHandlingResult`:

~~~java
@ExceptionResolver
public CommandHandlingResult handleProjectNotFound(
        ProjectNotFoundException exception) {

    return CommandHandlingResult.of(
            "Project " + exception.getProjectId() + " was not found",
            4);
}
~~~

Cần đặc biệt chú ý trường hợp resolver trả về `void`: Spring Shell xem exception đã được xử lý và mặc định mã thoát là `0`. Nếu đây vẫn là một lỗi cần báo cho CI hoặc script, hãy chỉ định `@ExitCode` hoặc dùng `CommandHandlingResult` có mã thoát khác `0`.

`CommandHandlingResult.exitCode()` chỉ có ý nghĩa trong non-interactive mode. Trong REPL tương tác, shell tiếp tục hoạt động và người dùng có thể chạy command tiếp theo.

## 9. Dùng CommandExceptionResolver ở phạm vi ứng dụng hoặc command registration

Ngoài `@ExceptionResolver`, Spring Shell 3.x có interface `CommandExceptionResolver` để xử lý exception trong quá trình command processing.

Resolver có thể được đăng ký:

- Toàn cục như một Spring bean.
- Riêng cho một `CommandRegistration`.

Ví dụ resolver toàn cục:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

@Configuration
public class CommandErrorConfiguration {

    @Bean
    CommandExceptionResolver projectExceptionResolver() {
        return exception -> {
            if (exception instanceof ProjectNotFoundException notFound) {
                return CommandHandlingResult.of(
                        "Project " + notFound.getProjectId() + " was not found",
                        4);
            }

            // Trả null để resolver tiếp theo hoặc xử lý mặc định tiếp tục.
            return null;
        };
    }
}
~~~

Khi chỉ một command cần resolver riêng, có thể gắn resolver vào `CommandRegistration`:

~~~java
CommandExceptionResolver projectExceptionResolver = exception -> {
    if (exception instanceof ProjectNotFoundException notFound) {
        return CommandHandlingResult.of(
                "Project " + notFound.getProjectId() + " was not found",
                4);
    }
    return null;
};

CommandRegistration.builder()
        .command("project show")
        .withErrorHandling()
            .resolver(projectExceptionResolver)
            .and()
        .build();
~~~

Resolver được khai báo cho command được xử lý trước resolver toàn cục. Cách này phù hợp khi quy tắc lỗi chỉ liên quan đến một command hoặc một nhóm command.

Không đăng ký đồng thời nhiều resolver có cùng phạm vi và cùng xử lý một exception nếu không cần thiết. Hãy xác định thứ tự ưu tiên rõ ràng để tránh một resolver tổng quát che mất resolver chuyên biệt.

## 10. Exception không được xử lý và ThrowableResultHandler

Nếu exception không được resolver xử lý, nó tiếp tục đi qua `ResultHandlerService` và được một `ResultHandler` phù hợp hiển thị.

Spring Shell 3.x có `ThrowableResultHandler` để xử lý đối tượng `Throwable`.

Theo Javadoc:

- Thông báo exception được hiển thị bằng màu đỏ.
- Handler lưu exception gần nhất đã xử lý.
- Trong interactive mode, người dùng có thể dùng command `stacktrace` để xem chi tiết.
- Trong non-interactive mode, stack trace được in ra vì không còn phiên shell để chạy command xem chi tiết.

Ví dụ:

~~~text
shell:> project show --id 404
Project service is unavailable

shell:> stacktrace
java.lang.IllegalStateException: Project service is unavailable
    at com.example.ProjectService.findById(ProjectService.java:42)
    ...
~~~

`stacktrace` là command tích hợp trong mô hình Spring Shell 3.x. Nó hiển thị stack trace của lỗi gần nhất, hữu ích khi thông báo ngắn chưa đủ để xác định nguyên nhân.

Trong môi trường production, cần cân nhắc thông tin nào được phép hiển thị cho người dùng. Stack trace có thể chứa tên class, đường dẫn, thông tin kết nối hoặc chi tiết nội bộ. Có thể giữ thông báo ngắn cho người dùng và ghi chi tiết vào log được bảo vệ.

## 11. Mã thoát mặc định trong Spring Shell 3.x

Mã thoát có ý nghĩa rõ nhất khi command chạy ở non-interactive mode, vì tiến trình kết thúc và trả mã cho shell hệ điều hành hoặc CI runner.

Theo tài liệu Spring Shell 3.1.6, mặc định:

| Kết quả | Mã thoát |
|---|---:|
| Lỗi khi parse option của command | `2` |
| Lỗi tổng quát | `1` |
| Không có lỗi | `0` |

Tài liệu cũng cho phép cấu hình ánh xạ exception sang mã thoát cho từng `CommandRegistration`.

Cần phân biệt:

- Lỗi option parsing là lỗi trước khi method chạy.
- Exception trong method là lỗi thực thi.
- Command không tìm thấy được xử lý qua result handler chuyên biệt.
- `CommandHandlingResult` cho phép resolver trả mã thoát cụ thể trong non-interactive mode.

Tài liệu mô tả rõ mã mặc định cho lỗi option parsing, lỗi tổng quát và thành công; không nên tự suy đoán một mã riêng cho `CommandNotFound` chỉ dựa vào nội dung thông báo. Hãy xác minh mã thoát của phiên bản và runner thực tế bằng process-level test.

### 11.1. Ánh xạ exception của command registration

Với command được đăng ký bằng builder, Spring Shell 3.x hỗ trợ ánh xạ exception sang mã thoát:

~~~java
CommandRegistration.builder()
        .command("project show")
        .withExitCode()
            .map(ProjectNotFoundException.class, 4)
            .and()
        .build();
~~~

Có thể dùng mapping function để đọc mã từ exception hoặc xử lý nhiều kiểu exception. Tài liệu 3.1.6 ghi rõ cấu hình exit code theo cách này không được khai báo trực tiếp bằng annotation command.

Với command annotation, có thể dùng `@ExceptionResolver`, `@ExitCode` hoặc `CommandHandlingResult` để điều khiển cách xử lý exception.

### 11.2. Kiểm tra mã thoát ở hệ điều hành

Không chỉ kiểm tra thông báo trên terminal. Trong CI, hãy kiểm tra mã thoát thực tế của process.

Bash:

~~~bash
java -jar customer-cli.jar project show --id 404
echo $?
~~~

PowerShell:

~~~powershell
java -jar customer-cli.jar project show --id 404
$LASTEXITCODE
~~~

Nếu test chỉ xác nhận màn hình có chuỗi “Project not found”, test đó chưa chứng minh process đã trả mã thoát như mong đợi.

## 12. Không dùng exception để thay thế kết quả nghiệp vụ bình thường

Không phải mọi kết quả “không có dữ liệu” đều cần ném exception.

Ví dụ:

- Người dùng tìm một project không tồn tại: có thể là lỗi nghiệp vụ cần xử lý rõ.
- Người dùng chạy `project list` nhưng chưa có project nào: có thể là kết quả hợp lệ, trả danh sách rỗng.
- Người dùng nhập tên command sai: là lỗi resolve command của framework.
- Người dùng truyền option không hợp lệ: là lỗi parse hoặc validation.

Hãy quyết định dựa trên ý nghĩa nghiệp vụ. Exception nên đại diện cho tình huống không thể tiếp tục theo luồng bình thường hoặc một điều kiện lỗi mà caller cần xử lý.

Ví dụ kết quả rỗng hợp lệ:

~~~java
@ShellMethod("List projects.")
public String list() {
    List<Project> projects = projectService.findAll();

    if (projects.isEmpty()) {
        return "No projects found";
    }

    return projects.stream()
            .map(Project::getName)
            .collect(Collectors.joining("\n"));
}
~~~

Nếu method trả chuỗi thông báo như trên, Spring Shell xem đó là kết quả command bình thường. Nó không tự tạo mã lỗi chỉ vì chuỗi có nội dung “No projects found”.

Nếu muốn CI coi một trường hợp là thất bại, hãy dùng exception hoặc cơ chế kết quả/mã thoát có chủ đích.

## 13. Thiết kế exception để dễ chẩn đoán

Exception trong command method nên chứa đủ thông tin để xác định vấn đề, nhưng không tiết lộ dữ liệu nhạy cảm.

Một exception nghiệp vụ có thể có:

- Kiểu exception riêng, ví dụ `ProjectNotFoundException`.
- Mã hoặc định danh tài nguyên liên quan.
- Thông báo ngắn, rõ ràng.
- `cause` gốc nếu exception được bọc từ tầng thấp hơn.

Ví dụ:

~~~java
public class ProjectImportException extends RuntimeException {

    public ProjectImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Khi bọc exception:

~~~java
try {
    importService.importFile(file);
}
catch (IOException exception) {
    throw new ProjectImportException(
            "Unable to import project file",
            exception);
}
~~~

Giữ `cause` để stack trace vẫn cho biết lỗi gốc. Không tạo exception mới chỉ với thông báo mà bỏ mất cause nếu cần điều tra sự cố.

Tránh:

- Bắt `Exception` rồi bỏ qua.
- Bắt `Throwable` để che mọi lỗi.
- Trả chuỗi lỗi như kết quả thành công mà không thiết lập exit status.
- Ghi log cùng một exception ở nhiều tầng gây trùng stack trace.
- Đưa mật khẩu, token hoặc thông tin cá nhân vào message.
- Dùng `System.exit()` bên trong command method để ép tiến trình dừng.

## 14. Quy trình chẩn đoán theo triệu chứng

Khi người dùng báo một command không chạy, hãy đi theo thứ tự sau.

### Bước 1: Kiểm tra tên command

Xác minh tên và alias đã đăng ký. Dùng `help` để xem danh sách command:

~~~text
shell:> help
~~~

Nếu shell trả `No command found`, kiểm tra tên command, alias và việc component có được scan hay không.

### Bước 2: Kiểm tra trạng thái khả dụng

Nếu command xuất hiện trong help nhưng không chạy, kiểm tra method availability hoặc trạng thái ứng dụng. Command unavailable có thể trả reason thay vì báo command không tồn tại.

### Bước 3: Kiểm tra option và argument

Xác minh tên option, giá trị bắt buộc, kiểu dữ liệu và validation. Nếu method không được gọi, có thể lỗi xảy ra trong parser hoặc parameter resolver.

### Bước 4: Kiểm tra method có được gọi không

Đặt breakpoint hoặc log ở đầu method. Nếu method đã chạy rồi mới lỗi, điều tra service, repository, file, mạng hoặc logic nghiệp vụ.

### Bước 5: Xem exception và cause

Trong REPL, dùng `stacktrace` để xem lỗi gần nhất. Trong non-interactive mode, kiểm tra stack trace và log được ghi ra.

### Bước 6: Kiểm tra resolver

Xác minh exception có khớp với `@ExceptionResolver` hoặc `CommandExceptionResolver` hay không. Nếu resolver trả `null`, exception tiếp tục qua chuỗi xử lý.

### Bước 7: Kiểm tra exit code

Chạy command trong non-interactive mode và đọc `$?` hoặc `$LASTEXITCODE`. Xác minh mã thoát phù hợp với chính sách ứng dụng.

## 15. Kiểm thử lỗi không tìm thấy và lỗi trong method

Nên kiểm thử hai tình huống riêng biệt. Spring Shell 3.1.x cung cấp `spring-shell-test`, `@ShellTest` và `ShellTestClient` để mô phỏng shell.

Ví dụ kiểm thử interactive:

~~~java
@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ProjectCommandErrorTests {

    @Autowired
    ShellTestClient client;

    @Test
    void reportsUnknownCommand() {
        InteractiveShellSession session = client
                .interactive()
                .run();

        session.write(
                session.writeSequence()
                        .text("project sho")
                        .carriageReturn()
                        .build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("No command found"));
    }

    @Test
    void reportsExceptionFromCommandMethod() {
        InteractiveShellSession session = client
                .interactive()
                .run();

        session.write(
                session.writeSequence()
                        .text("project show --id 404")
                        .carriageReturn()
                        .build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Project 404 was not found"));
    }
}
~~~

Trong test thứ nhất, command không tồn tại và method không được gọi. Trong test thứ hai, command đã được resolve và exception resolver chuyển exception nghiệp vụ thành thông báo.

Nên bổ sung các test khác:

| Kịch bản | Điều cần xác minh |
|---|---|
| Command typo | Hiển thị thông báo command không tìm thấy |
| Alias hợp lệ | Alias được resolve như command |
| Command unavailable | Hiển thị reason từ availability |
| Option không hợp lệ | Method chưa chạy và parser báo lỗi |
| Validation thất bại | Hiển thị thông tin validation |
| Method ném exception | Throwable handler hoặc exception resolver xử lý |
| Exception được resolver bắt | Thông báo và mã thoát đúng |
| Exception không được resolver bắt | Stack trace hoặc thông báo mặc định đúng |
| Non-interactive command lỗi | Process trả exit code đúng |
| Interactive command lỗi | Shell vẫn có thể nhận command tiếp theo |

Test terminal mô phỏng kiểm tra nội dung hiển thị. Để xác minh exit code của JVM, cần chạy tiến trình non-interactive và đọc mã thoát từ hệ điều hành hoặc viết process-level integration test.

## 16. Khác biệt trong Spring Shell 4.x

Spring Shell 4.x thay đổi API exception handling cùng với command programming model.

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| `CommandNotFound` trong mô hình legacy | `CommandNotFoundException` trong `CommandExecutor` của command model mới |
| `CommandExceptionResolver` | `ExitStatusExceptionMapper` |
| `CommandHandlingResult` | `ExitStatus` |
| `@ExceptionResolver` cho component method | `@Command(exitStatusExceptionMapper = "...")` hoặc cấu hình trên builder |
| `CommandNotFoundMessageProvider` | Hook tùy biến này đã bị loại bỏ trong redesign 4.0 |

Trong API command mới của Spring Shell 4.0.x, `CommandExecutor.execute()` có thể ném:

- `CommandNotFoundException` nếu command không tìm thấy.
- `CommandExecutionException` nếu có lỗi trong quá trình thực thi command.

`CommandExecutionException` có constructor nhận message, cause và từ 4.0.2 có thể nhận exit code trực tiếp.

Spring Shell 4.x dùng `ExitStatusExceptionMapper` để ánh xạ exception thành `ExitStatus`. `ExitStatus` mô tả mã và trạng thái của command; nó không tự động đồng nghĩa với mã thoát của JVM process.

Đặc biệt, migration guide ghi nhận `CommandNotFoundMessageProvider` và `CommandNotFoundResultHandler` của mô hình 3.x đã bị loại bỏ trong redesign 4.0. Vì vậy, không sao chép cấu hình custom message provider của 3.x sang 4.x.

Ví dụ khai báo mapper cho command annotation mới:

~~~java
@Command(
        name = "project show",
        exitStatusExceptionMapper = "projectExitStatusMapper")
public void show(@Option(longName = "id") long id) {
    projectService.findById(id)
            .orElseThrow(() -> new ProjectNotFoundException(id));
}

@Bean
ExitStatusExceptionMapper projectExitStatusMapper() {
    return exception -> {
        if (exception instanceof ProjectNotFoundException) {
            return new ExitStatus(4, "Project was not found");
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
~~~

Đây là API của mô hình annotation mới trong Spring Shell 4.x. Không dùng nguyên ví dụ này cho ứng dụng 3.x đang dùng `@ShellComponent` và `@ShellMethod`.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tên command sai nhưng resolver nghiệp vụ không chạy | `CommandNotFound` xảy ra trước khi method được gọi | Dùng `CommandNotFoundMessageProvider` trong 3.x |
| Command tồn tại nhưng method không được gọi | Lỗi option parsing, conversion hoặc validation | Kiểm tra parser và parameter resolver |
| Command không chạy vì trạng thái | Availability trả unavailable | Kiểm tra method availability và state |
| Method ném exception nhưng thông báo quá chung | Chưa có resolver chuyên biệt | Tạo exception type và `@ExceptionResolver` |
| Resolver không bắt được exception | Kiểu exception không khớp hoặc exception nằm trong cause | Kiểm tra root/cause và kiểu tham số resolver |
| Resolver trả `null` | Resolver chủ động nhường xử lý cho resolver tiếp theo | Kiểm tra thứ tự resolver và xử lý mặc định |
| Exception được xử lý nhưng exit code bằng 0 | Resolver trả `void` hoặc không chỉ định mã thoát | Trả `CommandHandlingResult` hoặc dùng `@ExitCode` |
| CI nhận mã thoát không như mong đợi | Chỉ kiểm tra nội dung terminal, chưa kiểm tra process status | Chạy non-interactive process-level test |
| Dùng `@ExceptionResolver` cho command not found | Sai giai đoạn xử lý | Tùy biến result handler/provider riêng |
| Dùng API 3.x trong Spring Shell 4 | API exception handling đã thay đổi | Dùng `ExitStatusExceptionMapper` và API mới |

## 18. Bài thực hành: phân loại và xử lý lỗi project

Tạo ứng dụng Spring Shell có command:

~~~text
project list
project show --id <id>
~~~

Yêu cầu:

1. Đăng ký hai command bằng `@ShellMethod`.
2. Nhập sai tên command và quan sát `CommandNotFound`.
3. Tạo `ProjectNotFoundException` khi ID không tồn tại.
4. Tạo `@ExceptionResolver` xử lý `ProjectNotFoundException`.
5. Trả thông báo thân thiện cùng mã thoát `4`.
6. Thử nhập ID không phải số để quan sát lỗi chuyển đổi trước khi method chạy.
7. Tạo một command unavailable bằng `Availability`.
8. Viết test riêng cho command not found, method exception, parse error và unavailable.
9. Chạy non-interactive command và kiểm tra exit code.
10. Chạy interactive REPL, gây lỗi một lần rồi dùng `stacktrace`.

Kịch bản mong đợi:

~~~text
shell:> project sho
No command found for 'project sho'

shell:> project show --id abc
Invalid value for option --id

shell:> project show --id 404
Project 404 was not found

shell:> stacktrace
...
~~~

Sau bài tập, giải thích tại sao ba dòng đầu thuộc ba giai đoạn khác nhau và tại sao không nên dùng một exception resolver duy nhất để xử lý tất cả.

## 19. Checklist triển khai

- [ ] Xác định command có registration hay không.
- [ ] Phân biệt `CommandNotFound` với exception do command method ném ra.
- [ ] Kiểm tra command unavailable trước khi điều tra logic method.
- [ ] Kiểm tra parse, conversion và validation riêng với lỗi thực thi.
- [ ] Dùng `CommandNotFoundMessageProvider` cho thông báo command không tìm thấy trong 3.x.
- [ ] Dùng `@ExceptionResolver` hoặc `CommandExceptionResolver` cho exception từ command processing.
- [ ] Giữ exception type riêng cho lỗi nghiệp vụ có thể dự đoán.
- [ ] Giữ cause khi bọc exception.
- [ ] Không bắt và nuốt lỗi lập trình.
- [ ] Chỉ trả mã thoát khác 0 khi command thực sự thất bại.
- [ ] Không để resolver `void` mặc định biến lỗi thành mã thoát 0 ngoài ý muốn.
- [ ] Kiểm thử riêng command not found và method exception.
- [ ] Kiểm tra exit code ở process-level trong non-interactive mode.
- [ ] Dùng đúng API exception handling theo phiên bản Spring Shell.

## 20. Kết luận

Lỗi không tìm thấy command xảy ra khi Spring Shell không ánh xạ được input tới một command registration. Trong Spring Shell 3.x, framework tạo `CommandNotFound` và dùng `CommandNotFoundResultHandler` để hiển thị thông báo. Command method chưa được gọi trong tình huống này.

Exception trong phương thức xử lý xảy ra sau khi command đã được tìm thấy và method bắt đầu chạy. Exception đi qua cơ chế `CommandExceptionResolver`, `@ExceptionResolver` và `ResultHandler`; nếu không được xử lý, `ThrowableResultHandler` hiển thị thông báo lỗi và cung cấp stack trace.

Hãy xác định đúng giai đoạn xảy ra lỗi trước khi chọn cách xử lý. Việc tách riêng command not found, command unavailable, lỗi tham số và exception nghiệp vụ giúp thông báo chính xác, mã thoát đáng tin cậy và kiểm thử dễ hiểu hơn.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Exception Handling](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1.6 Reference: Command Not Found](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: `CommandNotFound`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/CommandNotFound.html)
- [Spring Shell 3.1 API: `CommandNotFoundMessageProvider`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/result/CommandNotFoundMessageProvider.html)
- [Spring Shell 3.1 API: `CommandNotFoundResultHandler`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/result/CommandNotFoundResultHandler.html)
- [Spring Shell 3.1 API: `ThrowableResultHandler`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/result/ThrowableResultHandler.html)
- [Spring Shell 3.1 API: `CommandExceptionResolver`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandExceptionResolver.html)
- [Spring Shell 3.1 API: `CommandHandlingResult`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandHandlingResult.html)
- [Spring Shell 3.1 API: `@ExceptionResolver`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/annotation/ExceptionResolver.html)
- [Spring Shell 3.1 API: `@ExitCode`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/annotation/ExitCode.html)
- [Spring Shell 3.1 API: `CommandNotCurrentlyAvailable`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/CommandNotCurrentlyAvailable.html)
- [Spring Shell v4 Migration Guide: Command exception handling changes](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 4.0.3 API: `CommandExecutor`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutor.html)
- [Spring Shell 4.0.3 API: `CommandExecutionException`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html)
- [Spring Shell 4.0.4 Reference: Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)

