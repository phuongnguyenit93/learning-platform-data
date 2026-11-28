# CommandContext và thông tin một lần thực thi

Khi một command bắt đầu chạy, Spring Shell cung cấp **CommandContext** để method command truy cập thông tin của lần gọi hiện tại. Context gom dữ liệu đã phân tích, registry command, luồng ghi output và bộ đọc input vào cùng một đối tượng. Nhờ đó, command có thể xem lại option/argument, hỏi thêm thông tin, hiển thị kết quả và tương tác với tập command đang được đăng ký.

Trong Spring Shell 4.x, **CommandContext** là một record thuộc package **org.springframework.shell.core.command**. Nó có bốn thành phần: **ParsedInput**, **CommandRegistry**, **PrintWriter** và **InputReader**. Các accessor tương ứng là **parsedInput()**, **commandRegistry()**, **outputWriter()** và **inputReader()**.

Context mô tả môi trường của một lần gọi command. Nó không phải nơi lưu trạng thái nghiệp vụ dài hạn. Dữ liệu cần dùng giữa nhiều lần gọi nên được quản lý bởi service hoặc component có vòng đời phù hợp.

## 1. CommandContext nằm ở đâu trong luồng thực thi?

Runner nhận dòng lệnh, parser phân tích thành cấu trúc **ParsedInput**, registry tìm command cần chạy rồi executor gọi command với một **CommandContext**. Method command nhận các tham số đã được ánh xạ hoặc đọc thêm thông tin qua context.

~~~mermaid
flowchart TD
    A["Runner nhận dòng lệnh"] --> B["CommandParser"]
    B --> C["ParsedInput"]
    C --> D["CommandRegistry tìm command"]
    D --> E["Executor gọi command"]
    E --> F["CommandContext"]
    F --> G["Method command"]
    G --> H["Application service"]
    F --> I["InputReader đọc thêm dữ liệu"]
    F --> J["PrintWriter ghi output"]
    F --> K["CommandRegistry tra cứu command"]
~~~

**CommandContext** chứa thông tin cần cho lần thực thi, còn **CommandRegistry** là tập command mà ứng dụng shell đang quản lý. Hai thành phần này có phạm vi khác nhau: context được truyền vào lần gọi hiện tại; registry tồn tại trong ứng dụng và có thể được nhiều command truy cập.

## 2. Bốn thành phần của CommandContext

| Thành phần | Kiểu dữ liệu | Vai trò |
|---|---|---|
| **parsedInput()** | ParsedInput | Kết quả parser: tên command, subcommand, option và argument |
| **commandRegistry()** | CommandRegistry | Tra cứu các command đang được đăng ký |
| **outputWriter()** | PrintWriter | Ghi nội dung vào output do shell quản lý |
| **inputReader()** | InputReader | Đọc dòng nhập hoặc mật khẩu từ shell |

Các accessor là thành phần của record, nên được gọi bằng cú pháp phương thức:

~~~java
import java.io.PrintWriter;
import org.springframework.shell.core.InputReader;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.shell.core.command.ParsedInput;

ParsedInput parsedInput = context.parsedInput();
CommandRegistry registry = context.commandRegistry();
PrintWriter output = context.outputWriter();
InputReader input = context.inputReader();
~~~

Không cần tự tạo context trong một command annotation thông thường. Spring Shell truyền context vào method khi tham số có kiểu **CommandContext**. Với command được xây dựng bằng programmatic API, callback thực thi cũng nhận context tương ứng.

## 3. Đọc dữ liệu đã được phân tích

### 3.1. ParsedInput mô tả dòng lệnh

**ParsedInput** là record chứa bốn phần:

- **commandName()**: tên command đã được nhận diện.
- **subCommands()**: danh sách subcommand.
- **options()**: danh sách option đã phân tích.
- **arguments()**: danh sách positional argument đã phân tích.

Ví dụ người dùng nhập:

~~~text
artifact-inspect report.csv --format=json
~~~

ParsedInput lưu tên command, các subcommand và những option/argument tương ứng. Đây là dữ liệu ở mức parser, hữu ích khi command cần kiểm tra cấu trúc đầu vào hoặc xử lý metadata động.

~~~java
import java.util.List;
import org.springframework.shell.core.command.CommandArgument;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.ParsedInput;

ParsedInput parsed = context.parsedInput();

String commandName = parsed.commandName();
List<String> subCommands = parsed.subCommands();
List<CommandOption> options = parsed.options();
List<CommandArgument> arguments = parsed.arguments();
~~~

### 3.2. Lấy option theo tên

**CommandContext** cung cấp ba phương thức truy xuất option:

| Phương thức | Cách dùng |
|---|---|
| **getOptionByLongName(String)** | Tìm theo tên dài, ví dụ format |
| **getOptionByShortName(char)** | Tìm theo tên ngắn, ví dụ 'f' |
| **getOptionByName(String)** | Tìm theo tên dài hoặc tên ngắn |

Tên truyền vào không bao gồm dấu gạch ngang. Ví dụ dùng "format" thay vì "--format".

Các phương thức này trả về **CommandOption** hoặc null nếu không tìm thấy. **CommandOption** chứa metadata và giá trị runtime như short name, long name, description, required, defaultValue, value và type.

~~~java
CommandOption format = context.getOptionByLongName("format");

if (format != null) {
    String rawValue = format.value();
    if (rawValue != null) {
        context.outputWriter().println("Format đã parse: " + rawValue);
    }
}
~~~

### 3.3. Lấy positional argument theo index

**getArgumentByIndex(int)** truy xuất argument theo index bắt đầu từ 0. Phương thức trả về **CommandArgument** hoặc null nếu không có argument tương ứng.

~~~java
CommandArgument source = context.getArgumentByIndex(0);

if (source != null) {
    String value = source.value();
    if (value != null) {
        context.outputWriter().println("File đầu vào: " + value);
    }
}
~~~

**CommandArgument** chứa index, description, defaultValue, value, type và thông tin argument có variadic hay không. value() là giá trị dạng chuỗi được lưu trong cấu trúc parse; type() cho biết kiểu được khai báo.

Các accessor value() được đánh dấu có thể null trong API. Vì vậy, kiểm tra cả đối tượng metadata lẫn giá trị của nó trước khi sử dụng; việc tìm thấy option hoặc argument không đảm bảo giá trị runtime luôn có mặt.

### 3.4. Khi nào nên đọc ParsedInput trực tiếp?

Nếu method command đã khai báo tham số có kiểu, hãy ưu tiên dùng chính tham số đó:

~~~java
@Command(name = "artifact-inspect")
public String inspect(
        @Option(longName = "format", defaultValue = "text") String format,
        @Argument(index = 0) String file) {

    return "File: " + file + ", format: " + format;
}
~~~

Tham số method được Spring Shell ánh xạ và chuyển đổi theo khai báo. Không cần truy cập **CommandContext** chỉ để đọc lại cùng một giá trị.

Truy xuất qua context hữu ích khi:

- Một command cần duyệt danh sách option hoặc argument theo cấu trúc động.
- Logic phụ thuộc vào metadata như tên option, kiểu khai báo hoặc index.
- Một command programmatic xử lý đầu vào dựa trên metadata của command.
- Cần kiểm tra thông tin parser phục vụ chẩn đoán hoặc thông báo lỗi.

Ví dụ sau kết hợp tham số có kiểu với dữ liệu parse để hiển thị thông tin lần gọi:

~~~java
import java.io.PrintWriter;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.ParsedInput;
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ArtifactInspectionCommands {

    @Command(name = "artifact-inspect")
    public void inspect(
            @Option(longName = "format", required = true) String format,
            @Argument(index = 0) String file,
            CommandContext context) {

        ParsedInput parsed = context.parsedInput();
        CommandOption parsedFormat = context.getOptionByLongName("format");
        String parsedFormatValue =
                parsedFormat == null ? null : parsedFormat.value();

        PrintWriter out = context.outputWriter();
        out.println("Command: " + parsed.commandName());
        out.println("Format đã bind: " + format);
        out.println("Format trong parser: "
                + (parsedFormatValue == null ? "(không có)" : parsedFormatValue));
        out.println("File: " + file);
        out.println("Số positional argument: " + parsed.arguments().size());
        out.flush();
    }
}
~~~

Trong ứng dụng thực tế, không nên ghi toàn bộ **ParsedInput**, **CommandOption.value()** hoặc **CommandArgument.value()** vào log một cách vô điều kiện. Các giá trị có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm mà người dùng truyền trên dòng lệnh. Chỉ ghi metadata cần thiết và che các giá trị bí mật.

## 4. CommandRegistry trong context

**commandRegistry()** trả về registry mà shell đang dùng. Command có thể tra cứu một lệnh khác theo tên hoặc xem các command hiện có:

~~~java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class CommandLookupCommands {

    @Command(name = "describe-command")
    public void describeCommand(CommandContext context) {
        var statusCommand =
                context.commandRegistry().getCommandByName("status");

        if (statusCommand != null) {
            context.outputWriter().println(statusCommand.getDescription());
        }
        else {
            context.outputWriter().println("Command status chưa được đăng ký.");
        }
    }
}
~~~

Registry hữu ích khi command cần khám phá tính năng đã đăng ký, chẳng hạn hiển thị thông tin về command hỗ trợ. Tuy nhiên, registry không phải kho lưu trạng thái nghiệp vụ. Không lưu phiên đăng nhập, tiến trình đang chạy hoặc dữ liệu người dùng trong registry.

Việc đăng ký và hủy đăng ký command động nên được quản lý bởi thành phần chuyên trách về module hoặc plugin. Một command chỉ nên sửa registry khi đó là hành vi được thiết kế rõ ràng; không dùng registry thay cho dependency injection hoặc service nghiệp vụ.

## 5. Đọc input bổ sung bằng InputReader

Một command đôi khi cần hỏi thêm dữ liệu sau khi đã nhận option và argument. **InputReader** cung cấp các phương thức:

| Phương thức | Kết quả |
|---|---|
| **readInput()** | Đọc một dòng input và trả về String |
| **readInput(String prompt)** | Hiển thị prompt rồi đọc một dòng |
| **readPassword()** | Đọc mật khẩu và trả về char[] |
| **readPassword(String prompt)** | Hiển thị prompt rồi đọc mật khẩu |

Các phương thức đọc input có thể ném Exception, vì vậy method command thường khai báo throws Exception hoặc xử lý lỗi phù hợp.

Ví dụ hỏi xác nhận trước khi xóa:

~~~java
import java.io.PrintWriter;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ArtifactCommands {

    private final ArtifactService artifactService;

    ArtifactCommands(ArtifactService artifactService) {
        this.artifactService = artifactService;
    }

    @Command(name = "artifact-delete", description = "Xóa một artifact.")
    public void delete(
            @Option(longName = "id", required = true) String id,
            @Option(longName = "yes", defaultValue = "false") boolean yes,
            CommandContext context) throws Exception {

        PrintWriter out = context.outputWriter();

        if (!yes) {
            String answer = context.inputReader()
                    .readInput("Xóa artifact " + id + "? [y/N] ");

            if (!"y".equalsIgnoreCase(answer.strip())) {
                out.println("Đã hủy thao tác.");
                out.flush();
                return;
            }
        }

        artifactService.delete(id);
        out.println("Đã xóa artifact " + id);
        out.flush();
    }
}
~~~

Prompt nên có lựa chọn mặc định an toàn và giải thích rõ hành động sẽ thực hiện. Ví dụ trên chỉ tiếp tục khi người dùng nhập y; các giá trị khác đều hủy thao tác.

### 5.1. Đọc mật khẩu

Khi cần đọc bí mật, dùng **readPassword()** thay cho **readInput()**. API trả về char[], cho phép xóa nội dung mảng sau khi xác thực:

~~~java
import java.util.Arrays;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class LoginCommands {

    private final AuthenticationService authenticationService;

    LoginCommands(AuthenticationService authenticationService) {
        this.authenticationService = authenticationService;
    }

    @Command(name = "login")
    public void login(
            @Option(longName = "username", required = true) String username,
            CommandContext context) throws Exception {

        char[] password = context.inputReader().readPassword("Mật khẩu: ");
        try {
            authenticationService.authenticate(username, password);
        }
        finally {
            Arrays.fill(password, (char) 0);
        }
    }
}
~~~

Không in mật khẩu, không đưa nó vào log và tránh chuyển nó thành String nếu không cần thiết. Chuỗi Java là immutable nên không thể chủ động ghi đè nội dung của đối tượng String sau khi tạo.

### 5.2. Input tương tác và chạy script

**InputReader** là lớp trừu tượng để command đọc từ shell. Trong terminal tương tác, prompt có thể hỏi người dùng ngay trong lúc command chạy. Với script hoặc chế độ non-interactive, không nên giả định luôn có người trả lời prompt.

Nếu command cần chạy tự động, hãy ưu tiên truyền đầy đủ dữ liệu qua option và argument:

~~~text
artifact-delete --id=artifact-42 --yes
~~~

Khi cần xác nhận tương tác, command có thể yêu cầu prompt; khi chạy tự động, cờ xác nhận rõ ràng như --yes giúp script thể hiện ý định. Cần định nghĩa hành vi khi không có input: từ chối thao tác, trả lỗi hoặc yêu cầu người gọi cung cấp option xác nhận. Không để command chờ vô hạn vì một script không có người dùng.

## 6. Ghi output bằng PrintWriter

**outputWriter()** trả về **PrintWriter** để ghi nội dung vào luồng output do Spring Shell quản lý. Đây là cách được khuyến nghị trong command thay cho ghi trực tiếp bằng **System.out**.

~~~java
import java.io.PrintWriter;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class StatusCommands {

    @Command(name = "show-status")
    public void showStatus(CommandContext context) {
        PrintWriter out = context.outputWriter();
        out.println("Application: running");
        out.println("Database: connected");
        out.flush();
    }
}
~~~

Gọi **flush()** khi cần đẩy nội dung đã ghi ra ngay, chẳng hạn sau thông báo tiến độ trước khi thực hiện một tác vụ lâu. Nếu chỉ ghi một kết quả cuối cùng, có thể để cơ chế output xử lý theo vòng đời bình thường.

### 6.1. Khi nào dùng giá trị trả về, khi nào dùng outputWriter?

Với command method trả về một giá trị, Spring Shell xử lý kết quả đó theo cơ chế result handling của shell. Ví dụ method trả về **String** có thể dùng để hiển thị một dòng kết quả.

Dùng **outputWriter()** khi cần:

- In nhiều dòng theo thứ tự do command kiểm soát.
- Hiển thị tiến độ trong khi công việc đang chạy.
- Ghi nội dung theo từng phần thay vì đợi method hoàn tất.
- Tạo output tương tác như prompt hoặc thông báo xác nhận.

Hãy chọn một cách trình bày nhất quán cho mỗi command. Nếu vừa ghi toàn bộ kết quả qua writer vừa trả lại cùng nội dung, người dùng có thể thấy kết quả bị lặp.

Không dùng **System.out.println()** cho output thông thường của command. Ghi qua writer của context giúp output đi theo luồng shell đã cấu hình và dễ kiểm thử hơn.

## 7. Ví dụ kết hợp dữ liệu, input và output

Ví dụ sau nhận mã artifact, hỏi xác nhận và ghi tiến độ:

~~~java
import java.io.PrintWriter;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ArchiveCommands {

    private final ArchiveService archiveService;

    ArchiveCommands(ArchiveService archiveService) {
        this.archiveService = archiveService;
    }

    @Command(name = "archive-create", description = "Tạo bản lưu trữ.")
    public void create(
            @Option(longName = "name", required = true) String name,
            CommandContext context) throws Exception {

        PrintWriter out = context.outputWriter();

        out.println("Chuẩn bị tạo archive: " + name);
        out.flush();

        String answer = context.inputReader()
                .readInput("Tiếp tục? [y/N] ");

        if (!"y".equalsIgnoreCase(answer.strip())) {
            out.println("Đã hủy.");
            out.flush();
            return;
        }

        out.println("Đang tạo archive...");
        out.flush();

        ArchiveResult result = archiveService.create(name);

        out.println("Đã tạo: " + result.location());
        out.println("Dung lượng: " + result.sizeInBytes() + " bytes");
        out.flush();
    }
}
~~~

Command dùng tham số **name** cho dữ liệu đã khai báo, dùng **InputReader** cho bước xác nhận phát sinh trong lúc chạy và dùng **PrintWriter** để hiển thị tiến độ. **ArchiveService** chịu trách nhiệm tạo archive; context chỉ cung cấp khả năng tương tác với shell.

Trong một command không cần prompt, có thể bỏ **InputReader** và chỉ dùng tham số method cùng service. Không cần đưa **CommandContext** vào mọi method chỉ vì framework hỗ trợ nó.

## 8. Phạm vi và vòng đời của context

**CommandContext** được tạo cho một lần thực thi command. Vì vậy:

- Không lưu context vào field của một Spring singleton để dùng ở lần gọi sau.
- Không giữ **InputReader** hoặc **PrintWriter** để sử dụng sau khi command kết thúc.
- Không chuyển context vào tác vụ nền chạy lâu sau khi method đã trả về, trừ khi ứng dụng tự quản lý rõ vòng đời của các tài nguyên I/O.
- Không dùng **ParsedInput** làm mô hình nghiệp vụ lâu dài.
- Chỉ trích xuất những giá trị cần thiết rồi truyền chúng vào application service.

Ví dụ, thay vì truyền cả context cho service:

~~~java
// Không nên để service nghiệp vụ phụ thuộc vào shell context.
archiveService.create(context);
~~~

hãy truyền dữ liệu nghiệp vụ:

~~~java
ArchiveResult result = archiveService.create(name);
~~~

Service có thể được tái sử dụng từ REST API, job nền hoặc một giao diện khác mà không cần Spring Shell.

## 9. CommandContext khác với các tham số command như thế nào?

| Nhu cầu | Cách phù hợp |
|---|---|
| Nhận một chuỗi, số hoặc enum đã khai báo | Tham số method với **@Option** hoặc **@Argument** |
| Đọc danh sách option/argument đã parse | **context.parsedInput()** |
| Tìm một option theo tên | **getOptionByLongName()**, **getOptionByShortName()** hoặc **getOptionByName()** |
| Tìm positional argument theo index | **getArgumentByIndex()** |
| Đọc thêm một dòng từ người dùng | **context.inputReader().readInput()** |
| Đọc mật khẩu | **context.inputReader().readPassword()** |
| In thông báo hoặc tiến độ | **context.outputWriter()** |
| Tra cứu command đang đăng ký | **context.commandRegistry()** |
| Lưu dữ liệu nghiệp vụ giữa các lần gọi | Application service hoặc repository phù hợp |

Các tham số method thể hiện hợp đồng đầu vào tĩnh của command. Context cung cấp quyền truy cập đến thông tin runtime và tài nguyên tương tác. Khi dùng đúng vai trò, method command vẫn dễ đọc và service không phụ thuộc vào shell.

## 10. Khác biệt API giữa Spring Shell 3.x và 4.x

Spring Shell 4 thay đổi mô hình command và API context. Trong 4.x, **CommandContext** là record thuộc **org.springframework.shell.core.command**, với các accessor:

- **parsedInput()**
- **commandRegistry()**
- **inputReader()**
- **outputWriter()**
- **getOptionByName()**
- **getOptionByLongName()**
- **getOptionByShortName()**
- **getArgumentByIndex()**

Một số ví dụ cũ của dòng 3.x sử dụng các tên như **getRawArgs()**, **getOptionValue()**, **getParserResults()** hoặc **getTerminal()**. Không chép nguyên các lời gọi đó vào mã 4.x. Hãy kiểm tra package và API của đúng phiên bản Spring Shell mà dự án đang sử dụng.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| NullPointerException khi đọc option | getOptionByLongName() không tìm thấy và trả về null | Kiểm tra null trước khi đọc value() |
| Đọc nhầm positional argument | Dùng index sai hoặc giả định index bắt đầu từ 1 | Dùng index bắt đầu từ 0 |
| Output không xuất hiện ngay | Đã ghi nhưng chưa flush trong lúc cần hiển thị tiến độ | Gọi outputWriter().flush() tại điểm cần đẩy output |
| Output xuất hiện hai lần | Vừa ghi writer vừa trả về cùng nội dung | Chọn một cơ chế trình bày cho kết quả |
| Script bị treo ở prompt | Command đợi input tương tác trong môi trường không có người trả lời | Cung cấp option xác nhận và định nghĩa hành vi non-interactive |
| Mật khẩu xuất hiện trong log | Ghi toàn bộ ParsedInput hoặc option value | Che dữ liệu nhạy cảm và dùng readPassword() |
| Service phụ thuộc Spring Shell | Truyền cả context vào tầng nghiệp vụ | Trích xuất dữ liệu rồi gọi service bằng kiểu nghiệp vụ |
| Tác vụ nền ghi vào terminal đã đóng | Giữ writer/context sau khi command kết thúc | Quản lý riêng kênh thông báo và vòng đời tác vụ |
| Dùng API context cũ không biên dịch | Sao chép ví dụ 3.x vào 4.x | Dùng record accessor và phương thức truy xuất của API 4.x |

## 12. Kiểm thử command sử dụng context

Kiểm thử cần xác minh dữ liệu và tương tác của lần gọi command:

1. **ParsedInput:** command name, subcommand, option và argument được parse đúng.
2. **Option lookup:** tìm thấy option bằng tên dài/ngắn; trường hợp không tồn tại được xử lý an toàn.
3. **Argument lookup:** index 0 ánh xạ đúng giá trị đầu tiên; trường hợp thiếu argument không gây lỗi ngoài dự kiến.
4. **InputReader:** câu trả lời xác nhận đúng thì tiếp tục; câu trả lời khác thì hủy; lỗi đọc input được xử lý rõ ràng.
5. **Password:** dùng đường đọc mật khẩu, không ghi giá trị ra output/log và xóa mảng sau khi sử dụng.
6. **OutputWriter:** thông báo xuất hiện đúng thứ tự và được flush tại điểm cần thiết.
7. **CommandRegistry:** tra cứu command có tồn tại và xử lý trường hợp không tìm thấy.
8. **Non-interactive:** command chạy trong script không bị chặn bởi prompt ngoài dự kiến.
9. **Ranh giới service:** service chỉ nhận dữ liệu nghiệp vụ, không phụ thuộc **CommandContext**.

Có thể kiểm thử service độc lập với shell, sau đó kiểm thử tích hợp command qua bộ công cụ kiểm thử Spring Shell để xác nhận parser, context và output phối hợp đúng. Với các command có prompt, cần cung cấp input giả lập trong test thay vì để test chờ thao tác bàn phím thật.

## 13. Tài liệu tham khảo

- [Spring Shell 4.0.4 API — CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html) — record chứa thông tin runtime của lần gọi command.
- [Spring Shell 4.0.4 API — ParsedInput](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ParsedInput.html) — tên command, subcommand, option và argument đã parse.
- [Spring Shell 4.0.4 API — CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html) — metadata và giá trị runtime của option.
- [Spring Shell 4.0.4 API — CommandArgument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandArgument.html) — metadata và giá trị runtime của positional argument.
- [Spring Shell 4.0.3 — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html) — cách truy cập context trong command.
- [Spring Shell 4.0.3 — Reading Input](https://docs.spring.io/spring-shell/reference/commands/reading.html) — đọc dòng input và mật khẩu bằng InputReader.
- [Spring Shell 4.0.3 — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html) — ghi output qua PrintWriter của context.
- [Spring Shell 4.0.4 API — InputReader](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InputReader.html) — hợp đồng đọc input và password.
- [Spring Shell 4.0.4 API — CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html) — tra cứu và quản lý tập command.
