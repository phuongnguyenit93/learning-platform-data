# Đọc đầu vào bổ sung bằng API của terminal

## 1. Khi nào command cần hỏi thêm dữ liệu?

Thông thường, Spring Shell nhận dữ liệu đầu vào ngay trên dòng lệnh thông qua option và argument. Ví dụ:

~~~text
project create --name demo --profile prod
~~~

Đây là cách phù hợp khi người dùng đã biết các giá trị cần truyền, khi command được chạy trong script hoặc khi muốn lưu lại câu lệnh để thực thi lần sau.

Một số thao tác cần hỏi thêm thông tin sau khi command bắt đầu, chẳng hạn:

- Hỏi người dùng có thật sự muốn xóa một project hay không.
- Yêu cầu nhập lý do trước khi khóa tài khoản.
- Hỏi tên môi trường đích sau khi đã chọn một project.
- Yêu cầu nhập một dòng ghi chú hoặc xác nhận cuối cùng.
- Nhận một phím điều khiển trong một giao diện terminal tùy chỉnh.

Spring Shell 3.4 cung cấp `CommandContext.getTerminal()` để command truy cập terminal đang được shell sử dụng. Từ `Terminal`, ứng dụng có thể dùng JLine `LineReader` để đọc cả dòng có prompt và line editing, hoặc dùng `Terminal.reader()` khi cần đọc ký tự ở mức thấp.

Hãy chỉ hỏi thêm dữ liệu khi command đang chạy trong một phiên tương tác. Với script hoặc CI, những giá trị bắt buộc nên được truyền qua option, argument hoặc cấu hình để tiến trình không dừng lại chờ người dùng.

## 2. Lấy Terminal từ command context

Trong Spring Shell 3.4, `CommandContext` có phương thức `getTerminal()` trả về `org.jline.terminal.Terminal`. Command dùng annotation model mới hoặc programmatic registration có thể nhận `CommandContext` để truy cập terminal của lần gọi hiện tại.

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.command.annotation.Command;

@Command(command = "project prompt")
public String promptProject(CommandContext context) {
    Terminal terminal = context.getTerminal();
    terminal.writer().println("Đang chuẩn bị hỏi thông tin bổ sung");
    terminal.writer().flush();
    return "Terminal đã sẵn sàng";
}
~~~

`CommandContext` là ngữ cảnh của lần thực thi command. Ngoài terminal, nó còn cho phép đọc giá trị option đã parse và thông tin registration. Không nên tạo một `Terminal` mới bằng `TerminalBuilder` bên trong command nếu ứng dụng đã có terminal do Spring Shell quản lý; tạo terminal thứ hai có thể đọc một input stream khác hoặc cạnh tranh với shell hiện tại.

### Với legacy `@ShellMethod`

Nếu ứng dụng vẫn dùng legacy annotation model của Spring Shell 3.x, có thể inject bean `Terminal` do JLine auto-configuration cung cấp:

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands {

    private final Terminal terminal;

    public ProjectCommands(Terminal terminal) {
        this.terminal = terminal;
    }

    @ShellMethod(key = "project terminal-info")
    public String terminalInfo() {
        return "Terminal type: " + terminal.getType();
    }
}
~~~

Hai cách lấy terminal phục vụ hai mô hình command khác nhau. Nếu dùng `@Command` hoặc target function, lấy terminal từ `CommandContext`; nếu dùng `@ShellMethod`, inject `Terminal` vào bean. Cả hai đều dùng terminal được Spring quản lý.

## 3. Dùng JLine LineReader để hỏi một dòng

`Terminal.reader()` là reader mức thấp. Nếu cần hỏi một dòng văn bản có prompt, xử lý phím sửa dòng và nhận kết quả sau khi người dùng nhấn Enter, hãy dùng `LineReader` của JLine.

Tạo `LineReader` gắn với terminal hiện tại:

~~~java
import org.jline.reader.LineReader;
import org.jline.reader.LineReaderBuilder;
import org.jline.terminal.Terminal;

LineReader lineReader = LineReaderBuilder.builder()
        .terminal(terminal)
        .build();

String owner = lineReader.readLine("Tên chủ sở hữu: ");
~~~

`LineReader` cung cấp trải nghiệm nhập dòng tốt hơn việc tự đọc từng ký tự: người dùng có thể nhập, xóa, di chuyển con trỏ và hoàn tất bằng Enter. Phương thức `readLine(prompt)` trả về chuỗi không chứa ký tự xuống dòng cuối cùng.

Ví dụ command hỏi lý do triển khai:

~~~java
import org.jline.reader.EndOfFileException;
import org.jline.reader.LineReader;
import org.jline.reader.LineReaderBuilder;
import org.jline.reader.UserInterruptException;
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.command.annotation.Command;

@Command(command = "project deploy-confirm")
public String confirmDeploy(CommandContext context) {
    LineReader reader = LineReaderBuilder.builder()
            .terminal(context.getTerminal())
            .build();

    try {
        String reason = reader.readLine("Lý do triển khai: ").trim();
        if (reason.isEmpty()) {
            return "Cần nhập lý do triển khai";
        }

        deploymentService.deploy(reason);
        return "Đã gửi yêu cầu triển khai";
    }
    catch (UserInterruptException ex) {
        return "Người dùng đã hủy thao tác";
    }
    catch (EndOfFileException ex) {
        return "Đầu vào đã kết thúc; không thực hiện triển khai";
    }
}
~~~

`deploymentService` là service nghiệp vụ được inject vào command. Ví dụ kiểm tra chuỗi rỗng trước khi gọi service và xử lý riêng hai tình huống thường gặp: người dùng ngắt bằng Ctrl+C và đầu vào kết thúc bằng EOF, thường là Ctrl+D trên Unix-like terminal.

`UserInterruptException` và `EndOfFileException` thuộc `org.jline.reader`. Hãy quyết định rõ hành vi khi người dùng hủy hoặc input kết thúc; không coi các trường hợp này là một chuỗi rỗng hợp lệ.

## 4. Đọc thêm nhiều giá trị trong cùng một command

Có thể dùng cùng một `LineReader` để hỏi nhiều câu liên tiếp. Điều này hữu ích khi một thao tác có một vài thông tin tùy chọn chưa được truyền qua command line.

~~~java
import org.jline.reader.EndOfFileException;
import org.jline.reader.LineReader;
import org.jline.reader.LineReaderBuilder;
import org.jline.reader.UserInterruptException;
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.command.annotation.Command;

@Command(command = "workspace configure")
public String configureWorkspace(CommandContext context) {
    LineReader reader = LineReaderBuilder.builder()
            .terminal(context.getTerminal())
            .build();

    try {
        String name = reader.readLine("Tên workspace: ").trim();
        String region = reader.readLine("Region [ap-southeast-1]: ").trim();

        if (region.isEmpty()) {
            region = "ap-southeast-1";
        }
        if (name.isEmpty()) {
            return "Tên workspace không được để trống";
        }

        workspaceService.configure(name, region);
        return "Đã cấu hình workspace " + name;
    }
    catch (UserInterruptException ex) {
        return "Đã hủy cấu hình workspace";
    }
    catch (EndOfFileException ex) {
        return "Không đủ dữ liệu; chưa lưu cấu hình";
    }
}
~~~

Ví dụ giả định `workspaceService` đã được inject. Cả hai giá trị được thu thập trước khi gọi service. Nếu một bước bị hủy hoặc EOF xảy ra, command thoát mà chưa lưu cấu hình một phần.

Khi có nhiều trường, hãy kiểm tra toàn bộ dữ liệu trong bộ nhớ trước khi ghi. Nếu cần một wizard có lựa chọn, validation và điều hướng giữa các bước, các component như `StringInput`, `ConfirmationInput` hoặc `ComponentFlow` thường phù hợp hơn việc tự tạo nhiều prompt tuần tự.

## 5. Nhập giá trị có che ký tự

JLine `LineReader` hỗ trợ overload `readLine(prompt, mask)`. Nếu `mask` là ký tự như `'*'`, JLine hiển thị ký tự che thay cho nội dung người dùng gõ:

~~~java
String accessCode = reader.readLine("Mã truy cập: ", '*');
~~~

Nếu truyền `null`, ký tự được hiển thị bình thường. Nếu truyền ký tự NUL (`'\0'`), nội dung không được echo ra terminal.

Che ký tự chỉ thay đổi cách hiển thị. Giá trị trả về vẫn là `String`; ứng dụng vẫn phải bảo vệ nó khỏi log, command history, exception message và output. Không ghi giá trị bí mật vào log hoặc trả nó về màn hình.

Với dữ liệu nhạy cảm có yêu cầu bảo vệ cao, ưu tiên lấy secret từ secret manager hoặc biến môi trường được bảo vệ thay vì yêu cầu người dùng gõ trực tiếp. API `InputReader.readPassword()` trả về `char[]` được giới thiệu trong Spring Shell 4.0; không nhầm API đó với `CommandContext.getTerminal()` của Spring Shell 3.4.

## 6. Dùng Terminal.reader() để đọc ký tự trực tiếp

Khi cần nhận một phím đơn, ví dụ menu tối giản hoặc xác nhận bằng `y`/`n`, có thể truy cập `NonBlockingReader` từ `terminal.reader()`.

~~~java
import java.io.IOException;

import org.jline.terminal.Terminal;
import org.jline.utils.NonBlockingReader;

private int readCharacter(Terminal terminal) throws IOException {
    NonBlockingReader reader = terminal.reader();
    return reader.read();
}
~~~

`NonBlockingReader` là reader do terminal sở hữu. `read()` trả về mã ký tự hoặc `-1` khi gặp EOF; API cũng có các thao tác đọc có timeout. Tên lớp là non-blocking reader nhưng lời gọi `read()` thông thường vẫn có thể chờ input. Nếu cần trải nghiệm nhập dòng, không dùng API này để tự xây lại line editor; hãy dùng `LineReader`.

Ví dụ xác nhận bằng một phím:

~~~java
private boolean confirmWithLine(Terminal terminal) {
    LineReader reader = LineReaderBuilder.builder()
            .terminal(terminal)
            .build();
    String answer = reader.readLine("Tiếp tục? [y/N] ").trim();
    return answer.equalsIgnoreCase("y");
}
~~~

Với xác nhận yes/no thông thường, dùng `LineReader` để nhận trọn dòng; nếu đọc trực tiếp một ký tự trong canonical mode, phần còn lại của dòng (bao gồm Enter) có thể vẫn nằm trong input stream và ảnh hưởng lần đọc kế tiếp. Nếu muốn phản hồi ngay khi nhấn một phím mà không cần Enter, cần chuyển terminal sang raw mode và khôi phục thuộc tính sau khi đọc.

## 7. Khi cần phím đơn ngay lập tức: raw mode

Trong canonical mode, terminal xử lý input theo dòng. Trong raw mode, input có thể được nhận theo từng ký tự; terminal cũng thay đổi cách xử lý echo và signal. JLine cung cấp `Terminal.enterRawMode()` để chuyển chế độ và trả lại `Attributes` ban đầu.

~~~java
import java.io.IOException;

import org.jline.terminal.Attributes;
import org.jline.terminal.Terminal;

private int readSingleKey(Terminal terminal) throws IOException {
    Attributes original = terminal.enterRawMode();
    try {
        terminal.writer().print("Nhấn một phím để tiếp tục: ");
        terminal.writer().flush();
        return terminal.reader().read();
    }
    finally {
        terminal.setAttributes(original);
        terminal.writer().println();
        terminal.writer().flush();
    }
}
~~~

Khôi phục attributes trong `finally` là bắt buộc. Nếu command phát sinh exception hoặc bị hủy mà không khôi phục terminal, echo, line editing hoặc xử lý Ctrl+C có thể bị sai trong những command tiếp theo.

Raw mode tắt một số xử lý đặc biệt của terminal. Vì vậy, Ctrl+C có thể được đọc như dữ liệu thay vì được chuyển thành signal; ứng dụng phải quyết định cách xử lý nếu cần. Không dùng raw mode chỉ để hỏi một dòng văn bản. `LineReader` đã quản lý line editing và terminal mode phù hợp cho tác vụ nhập dòng.

## 8. Không đóng Terminal hoặc reader do Spring quản lý

`Terminal` được Spring Shell/JLine tạo và quản lý theo vòng đời của application context. `terminal.reader()` và `terminal.writer()` là các stream thuộc quyền sở hữu của terminal.

Không gọi:

~~~java
terminal.close();
terminal.reader().close();
terminal.writer().close();
~~~

trong một command thông thường. Đóng chúng có thể làm shell mất khả năng nhận input hoặc ghi output cho những command sau. Hãy chỉ đóng terminal tại nơi sở hữu vòng đời của nó, thường là khi application context kết thúc.

Tương tự, không tạo nhiều reader độc lập cùng đọc một terminal tại cùng thời điểm. Hai reader cùng đọc một input stream có thể lấy mất dữ liệu của nhau. Khi command đang đọc input bổ sung, hãy bảo đảm chỉ có một luồng điều khiển thực hiện thao tác đọc terminal.

## 9. Phân biệt đầu vào bổ sung với option và argument

Không phải mọi dữ liệu đều nên được hỏi bằng prompt. Chọn cách nhận input dựa trên cách command được sử dụng:

| Nhu cầu | Cách phù hợp |
|---|---|
| Giá trị bắt buộc khi chạy script | Option hoặc argument. |
| Giá trị có thể mặc định | Option với default value. |
| Một câu xác nhận trong phiên tương tác | `LineReader.readLine(...)` hoặc `ConfirmationInput`. |
| Một vài trường nhập bổ sung | `LineReader` hoặc `ComponentFlow`. |
| Chọn từ danh sách | `SingleItemSelector` hoặc component tương ứng. |
| Nhập một phím điều khiển | `Terminal.reader()`; raw mode nếu cần phản hồi ngay. |
| Secret có yêu cầu quản lý an toàn | Secret manager hoặc nguồn secret được bảo vệ; không log giá trị. |

Nếu command luôn cần một giá trị, hãy ưu tiên khai báo option bắt buộc. Prompt chỉ nên là bước bổ sung khi người dùng thực sự đang tương tác với terminal.

## 10. Tránh treo script ở prompt tương tác

Một command có thể hoạt động tốt trong REPL nhưng bị treo trong pipeline vì nó chờ `readLine()` trong khi không có người dùng nhập liệu. Đây là lý do cần tách rõ interactive và non-interactive use case.

Ví dụ command có thể nhận option `--reason`; nếu option vắng mặt, chỉ hỏi thêm khi ứng dụng đang cho phép tương tác:

~~~java
import org.jline.reader.LineReader;
import org.jline.reader.LineReaderBuilder;
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "project deploy")
public String deploy(
        @Option(longNames = "reason") String reason,
        CommandContext context) {

    String finalReason = reason;
    if (finalReason == null || finalReason.isBlank()) {
        if (!promptingEnabled) {
            return "Thiếu --reason; hãy truyền giá trị khi chạy non-interactive";
        }

        LineReader reader = LineReaderBuilder.builder()
                .terminal(context.getTerminal())
                .build();
        finalReason = reader.readLine("Lý do triển khai: ").trim();
    }

    if (finalReason.isBlank()) {
        return "Lý do triển khai không được để trống";
    }

    deploymentService.deploy(finalReason);
    return "Đã gửi yêu cầu triển khai";
}
~~~

`promptingEnabled` là cấu hình boolean của ứng dụng và `deploymentService` là service được inject. Không nên suy luận rằng có thể prompt chỉ vì một đối tượng `Terminal` tồn tại; terminal có thể được gắn với input đã redirect hoặc không có người dùng tương tác. Hãy quyết định rõ theo runner mode hoặc cấu hình ứng dụng.

Với automation, command nên trả lỗi rõ ràng khi thiếu option bắt buộc thay vì chờ vô hạn. Nếu cần xác nhận trong script, hãy cung cấp option tường minh như `--yes` và định nghĩa rõ tác động của nó.

## 11. Xử lý hủy, EOF và lỗi đọc input

Khi đọc bổ sung, cần phân biệt các tình huống:

- Người dùng nhập chuỗi hợp lệ và nhấn Enter.
- Người dùng nhấn Ctrl+C để hủy thao tác hiện tại.
- Input kết thúc, ví dụ Ctrl+D hoặc pipe đóng.
- Reader phát sinh lỗi I/O.
- Dữ liệu được nhập nhưng không vượt qua validation.

Với `LineReader`, xử lý `UserInterruptException` và `EndOfFileException` riêng. Với `NonBlockingReader`, kiểm tra `-1` cho EOF và xử lý `IOException`. Không nuốt exception rồi tiếp tục gọi service với giá trị rỗng.

Nếu thao tác đã bắt đầu thay đổi dữ liệu trước khi hỏi bổ sung, cần xem xét transaction hoặc thiết kế lại để hoàn tất việc thu thập và xác nhận trước khi áp dụng mutation. Hủy prompt không nên để lại trạng thái một phần ngoài dự kiến.

## 12. Kiểm thử command có đọc input bổ sung

Kiểm thử cần xác nhận cả kết quả lẫn hành vi khi hủy:

1. Input bổ sung hợp lệ được truyền đúng vào service.
2. Input rỗng hoặc sai định dạng bị từ chối trước khi gọi service.
3. Ctrl+C kết thúc thao tác theo quy ước và không gọi service.
4. EOF không bị hiểu thành chuỗi rỗng hợp lệ.
5. Prompt không xuất hiện trong chế độ non-interactive.
6. Terminal attributes được khôi phục sau khi đọc raw mode, kể cả khi có exception.
7. Command tiếp theo vẫn đọc và ghi terminal bình thường.
8. Nhiều command liên tiếp không bị mất ký tự do có nhiều reader cùng đọc một terminal.
9. Giá trị nhạy cảm không xuất hiện trong log, output hoặc lịch sử command.

Với `ShellTestClient`, kiểm thử command trong shell test context và cung cấp input qua session interactive phù hợp với test harness của phiên bản Spring Shell đang dùng. Với phần đọc phím raw mode, nên bổ sung kiểm thử bằng pseudo-terminal hoặc terminal emulator thật vì unit test thông thường không mô phỏng đầy đủ terminal attributes và signal.

## 13. Những lỗi thường gặp

**Dùng `Scanner(System.in)` trong command:** scanner có thể cạnh tranh với JLine vì cả hai cùng đọc input stream. Dùng `Terminal` hiện tại và JLine `LineReader`.

**Dùng `Terminal.reader()` để nhập một câu dài:** reader mức thấp không cung cấp line editing. Dùng `LineReader.readLine(prompt)`.

**Quên flush prompt:** người dùng có thể không thấy câu hỏi trước khi ứng dụng chờ input. Gọi `terminal.writer().flush()` khi tự in prompt bằng writer; `LineReader` tự quản lý prompt của nó.

**Không xử lý Ctrl+C hoặc EOF:** command có thể bị kết thúc bất ngờ hoặc dùng dữ liệu chưa đầy đủ. Bắt các exception JLine tương ứng và dừng trước mutation.

**Đóng reader hoặc terminal:** làm hỏng input/output cho các command sau. Để Spring Shell quản lý vòng đời terminal.

**Không khôi phục raw mode:** terminal có thể tiếp tục không echo hoặc không xử lý Enter như bình thường. Luôn khôi phục `Attributes` trong `finally`.

**Prompt trong script:** command có thể chờ vô hạn. Dùng option/argument hoặc cấu hình non-interactive rõ ràng.

**Cho rằng masked input là secret an toàn:** ký tự chỉ bị che trên màn hình; giá trị vẫn là `String`. Không log, lưu history hoặc hiển thị lại secret.

## 14. Quy trình lựa chọn API

1. Kiểm tra xem giá trị có thể được nhận qua option hoặc argument không.
2. Nếu cần prompt một dòng, lấy `Terminal` từ `CommandContext` hoặc inject terminal cho legacy `@ShellMethod`.
3. Tạo `LineReader` bằng `LineReaderBuilder` gắn với terminal hiện tại.
4. Gọi `readLine(prompt)` và xử lý `UserInterruptException`, `EndOfFileException`.
5. Validate input trước khi gọi service hoặc ghi dữ liệu.
6. Nếu cần một phím đơn, dùng `terminal.reader()`; chỉ bật raw mode khi thật sự cần phản hồi tức thì.
7. Nếu đã thay đổi terminal attributes, khôi phục trong `finally`.
8. Không đóng terminal hoặc reader do Spring Shell quản lý.
9. Không prompt khi chạy non-interactive; yêu cầu caller truyền dữ liệu qua command line.
10. Kiểm thử trên pseudo-terminal và môi trường script thực tế.

## Kết luận

Trong Spring Shell 3.4, command có thể lấy terminal qua `CommandContext.getTerminal()` hoặc inject `Terminal` khi dùng legacy `@ShellMethod`. Để hỏi thêm một dòng, dùng JLine `LineReaderBuilder` và `LineReader.readLine(...)`; để nhận ký tự trực tiếp, dùng `Terminal.reader()` với `NonBlockingReader`. Chỉ chuyển sang raw mode khi cần xử lý phím tức thì và luôn khôi phục `Attributes` trong `finally`. Không đóng terminal do Spring quản lý, không để nhiều reader cùng đọc một terminal và không prompt trong luồng automation. Với dữ liệu nhạy cảm, che ký tự không thay thế việc quản lý secret an toàn.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 – Command Context](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/commandcontext.html)
- [Spring Shell 3.4.3 API – CommandContext](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandContext.html)
- [Spring Shell 3.4.3 – Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html)
- [JLine 3 – Line Reader](https://jline.org/versions/3.x/docs/line-reader/)
- [JLine 3 – Terminal](https://jline.org/versions/3.x/docs/terminal/)
- [JLine 3 – Terminal Attributes](https://jline.org/versions/3.x/docs/advanced/terminal-attributes/)
- [JLine 3 – Non-blocking Input](https://jline.org/versions/3.x/docs/advanced/non-blocking-input/)
- [Spring Shell 4.0 API – InputReader](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InputReader.html)
