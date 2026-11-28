# Hành vi khi không có terminal hoặc đầu vào đã kết thúc

Một ứng dụng Spring Shell có thể được chạy từ terminal thật, cửa sổ Run của IDE, pipeline CI, cron, Docker, SSH hoặc một lệnh có stdin/stdout được chuyển hướng. Trong những môi trường đó, ứng dụng không phải lúc nào cũng có terminal để hiển thị prompt và nhận phím. Tuy nhiên, không có terminal không đồng nghĩa với không có dữ liệu đầu vào: stdin vẫn có thể nhận nội dung từ pipe hoặc file. Ngược lại, một terminal đang mở vẫn có thể gửi EOF khi người dùng kết thúc luồng nhập.

Muốn command không treo hoặc xử lý nhầm dữ liệu, cần phân biệt bốn trạng thái: chế độ interactive của Spring Shell, khả năng PTY của terminal, dữ liệu hiện có trên stdin và trạng thái EOF. Khi không thể hỏi người dùng, command phải nhận đủ tham số qua option/config/script hoặc kết thúc với thông báo rõ ràng. Khi luồng dữ liệu kết thúc, command cần dừng đọc đúng lúc và xử lý phần dữ liệu đã nhận theo hợp đồng nghiệp vụ.

## Phân biệt terminal, PTY, stdin và EOF

Các khái niệm này liên quan nhưng không thay thế cho nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Terminal | Thiết bị/giao diện cung cấp nhập phím và hiển thị văn bản | Windows Terminal, macOS Terminal, GNOME Terminal |
| TTY/PTY | Giao diện terminal của hệ điều hành; PTY là pseudo-terminal do chương trình khác tạo | Terminal SSH, terminal giả lập trong test hoặc container `-t` |
| stdin | Luồng byte mà process đọc làm đầu vào chuẩn | Bàn phím, file được redirect hoặc pipe từ process khác |
| stdout | Luồng đầu ra chuẩn | Terminal hoặc file nhận kết quả command |
| stderr | Luồng lỗi chuẩn | Terminal hoặc file nhận thông báo chẩn đoán |
| EOF | Tín hiệu cho biết luồng đầu vào đã kết thúc, không còn byte để đọc | Người dùng gửi EOF, file đã đọc hết hoặc process ghi vào pipe đóng luồng |
| Interactive mode | Chế độ runner của Spring Shell giữ phiên shell để người dùng tiếp tục nhập command | REPL có prompt và history |
| Non-interactive mode | Runner thực thi command từ đối số khởi chạy rồi kết thúc | `java -jar app.jar customer-list` |

Một số trường hợp thường gặp:

| Môi trường | Có PTY? | stdin có thể có dữ liệu? | Có thể hỏi prompt? |
|---|---:|---:|---:|
| Terminal hệ điều hành mở trực tiếp | Thường có | Có, từ bàn phím | Có |
| IDE Run console | Tùy IDE, thường không đủ terminal capability | Có thể nhận text | Không nên giả định |
| `cat file.csv | java -jar ...` | Không | Có, từ pipe | Không |
| `java -jar ... < input.txt` | Không | Có, từ file | Không |
| CI job không cấp terminal | Không | Có thể có pipe/file hoặc rỗng | Không |
| `docker run -it ...` | Có PTY được cấp | Có | Có thể |
| `docker run ...` không có `-t` | Không | Có thể có nếu dùng pipe/redirect | Không |
| Script file đã đọc hết | Không cần PTY | Script provider đã tới cuối file | Không cần hỏi |

Điểm cần nhớ: `hasPty() == false` cho biết không có terminal tương tác phù hợp; nó không chứng minh stdin rỗng. Một pipe có thể chứa hàng triệu byte dù process không có PTY.

## Phân biệt InteractionMode và khả năng PTY trong Spring Shell 3.x

Spring Shell 3.x cung cấp `ShellContext` để command biết shell đang chạy ở chế độ nào và terminal có PTY hay không:

| API | Giá trị | Ý nghĩa |
|---|---|---|
| `getInteractionMode()` | `INTERACTIVE` | Shell đang chạy phiên tương tác và dự kiến tiếp tục sống để nhận command |
| `getInteractionMode()` | `NONINTERACTIVE` | Shell thực thi command rồi kết thúc |
| `hasPty()` | `true` | Terminal có PTY và các khả năng tương tác phù hợp |
| `hasPty()` | `false` | Không có PTY; ví dụ output bị pipe vào file hoặc chạy trong CI không có người dùng |

Hai thông tin này độc lập. Có thể runner đang được cấu hình interactive nhưng môi trường khởi chạy không cung cấp PTY. Ngược lại, một process có PTY nhưng command được yêu cầu chạy một lần rồi kết thúc vẫn có thể đi theo luồng non-interactive.

Lấy `ShellContext` từ `CommandContext`:

```java
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.context.ShellContext;

boolean canPrompt(CommandContext commandContext) {
    ShellContext shellContext = commandContext.getShellContext();
    return shellContext.getInteractionMode() == InteractionMode.INTERACTIVE
            && shellContext.hasPty();
}
```

Chỉ gọi `ComponentFlow`, `StringInput`, selector hoặc prompt nhập password khi `canPrompt(...)` trả `true`. Nếu không, nhận giá trị từ option/config/secret provider hoặc báo lỗi hướng dẫn. Không dùng riêng `getInteractionMode()` để quyết định có thể đọc phím.

`ShellContext.hasPty()` được mô tả trong API Spring Shell 3.x; kiểm tra Javadoc của minor version đang dùng nếu ứng dụng còn ở dòng cũ hơn. Không suy diễn khả năng terminal từ việc process có `System.in` hay không.

## Chọn ShellRunner phù hợp

Spring Shell 3.x có ba runner chính:

| Runner | Nhiệm vụ | Khi dùng |
|---|---|---|
| `InteractiveShellRunner` | Mở REPL và lấy command từ input tương tác | Người dùng thao tác trong terminal |
| `NonInteractiveShellRunner` | Thực thi command từ process arguments mà không mở REPL | Script, CI, cron và command chạy một lần |
| `ScriptShellRunner` | Đọc tên file script bắt đầu bằng `@`, thực thi các command trong file rồi kết thúc | Batch gồm nhiều command |

Từ Spring Shell 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Muốn bật interactive hoặc startup script, cấu hình rõ:

```yaml
spring:
  shell:
    noninteractive:
      enabled: true
    interactive:
      enabled: true
    script:
      enabled: true
```

Các phiên bản đến 3.2.x có mặc định runner khác: cả ba runner được bật mặc định. Vì vậy, khi nâng từ 3.2 lên 3.3, hãy kiểm tra cấu hình runner thay vì giả định REPL hoặc `@script` vẫn tự chạy.

### Chạy một command không cần terminal

Với non-interactive runner, command được truyền ngay khi khởi chạy:

```bash
java -jar customer-cli.jar customer-list --status ACTIVE --limit 20
```

Process thực thi command và kết thúc. Không có prompt để hỏi thêm option còn thiếu. Command phải validate tham số và trả lỗi có hướng dẫn nếu dữ liệu bắt buộc chưa được cung cấp.

### Chạy script file

`ScriptShellRunner` nhận đối số bắt đầu bằng `@` và coi phần còn lại là đường dẫn file script:

```bash
java -jar customer-cli.jar @release-check.shell
```

Ví dụ nội dung `release-check.shell`:

```text
version
health-check --target staging
customer-count --status ACTIVE
```

Script file là nguồn command lines; stdin vẫn là một luồng riêng. Khi script tới cuối file, runner kết thúc quá trình đọc script. Không đặt prompt cần bàn phím vào giữa script nếu mục tiêu là chạy tự động.

Lưu ý: built-in `script` command trong một phiên REPL và `ScriptShellRunner` xử lý đối số `@file` là hai cách gọi khác nhau. Runner `@file` phải được bật bằng `spring.shell.script.enabled=true` trong Spring Shell 3.3.x.

## Không có terminal nhưng stdin vẫn có dữ liệu

Một command import có thể nhận dữ liệu CSV qua pipe. Khi đó command line chứa cú pháp command và option, còn stdin chứa nội dung file:

```bash
cat customers.csv | java -jar customer-cli.jar customer-import --stdin
```

Hoặc redirect từ file:

```bash
java -jar customer-cli.jar customer-import --stdin < customers.csv
```

Để cách này hoạt động ổn định:

- Chạy command bằng non-interactive runner; không để JLine REPL đọc cùng stdin trước command.
- Định nghĩa rõ option như `--stdin` để command biết nó sở hữu luồng stdin.
- Không hiển thị prompt hoặc chờ Enter khi đang đọc pipe.
- Tách kết quả command khỏi dữ liệu máy đọc; tránh in banner hoặc bảng vào stdout nếu caller cần CSV/JSON.
- Xác định encoding, giới hạn kích thước, xử lý dòng lỗi và chính sách khi input rỗng.

Ví dụ đọc stdin theo từng dòng trong một command dành cho non-interactive mode:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class CustomerImportCommands {

    private final CustomerImportService importService;

    CustomerImportCommands(CustomerImportService importService) {
        this.importService = importService;
    }

    @ShellMethod(key = "customer-import")
    public String importCustomers(
            @ShellOption(value = "stdin", defaultValue = "false") boolean fromStdin)
            throws IOException {

        if (!fromStdin) {
            throw new IllegalArgumentException(
                    "Hãy cung cấp --stdin hoặc dùng option --file.");
        }

        int imported = 0;
        try {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                importService.importLine(line);
                imported++;
            }
        } catch (IOException ex) {
            throw new IOException("Không thể đọc dữ liệu từ stdin.", ex);
        }

        if (imported == 0) {
            throw new IllegalArgumentException("stdin đã kết thúc nhưng không có bản ghi.");
        }
        return "Đã nhập " + imported + " bản ghi.";
    }
}
```

Ví dụ này minh họa cách đọc dữ liệu theo dòng, không phải một parser CSV đầy đủ. `System.in` được dùng trực tiếp vì command được thiết kế cho process non-interactive; không dùng cùng cách này trong REPL đang lấy command từ chính stdin. Code không đóng `System.in` để tránh đóng luồng do process sở hữu trước khi ứng dụng kết thúc. Với dữ liệu lớn, service nên xử lý theo batch và có giới hạn bộ nhớ.

## Khi stdin đã kết thúc: hiểu đúng EOF

EOF (End Of File/End Of Stream) là trạng thái luồng không còn dữ liệu để đọc. Nó không phải một dòng trống.

| Tình huống | Kết quả |
|---|---|
| Người dùng nhấn Enter trên dòng trống | Nhận một dòng có độ dài 0; stream vẫn mở |
| File có một dòng trống ở cuối | Reader nhận dòng trống, sau đó có thể tiếp tục đọc |
| File đã đọc hết | Lần đọc tiếp theo trả EOF |
| Process ghi vào pipe đóng output | Reader phía nhận thấy EOF sau khi buffer đã được đọc hết |
| Người dùng gửi ký tự EOF của terminal | Terminal/reader báo kết thúc input theo cấu hình terminal |
| `Ctrl+C` | Tín hiệu ngắt/cancel; không phải EOF |

Không dùng `line.isBlank()` để phát hiện EOF. Dùng giá trị trả về hoặc exception theo API đang đọc.

### BufferedReader: EOF trả về null

Với `BufferedReader.readLine()`, kết quả `null` nghĩa là hết luồng. Chuỗi `""` là một dòng trống hợp lệ:

```java
String line;
while ((line = reader.readLine()) != null) {
    if (line.isBlank()) {
        // Chính sách cho dòng trống, không phải EOF.
        continue;
    }
    process(line);
}
// Đến đây reader đã hết dữ liệu.
```

Sau khi nhận `null`, không lặp lại lệnh đọc trong vòng `while (true)` mà không có điều kiện thoát. Nếu làm vậy, command có thể quay vòng liên tục mà không nhận thêm dữ liệu.

### JLine LineReader: EOF ném EndOfFileException

JLine 3 `LineReader.readLine(...)` có thể ném `EndOfFileException` khi input kết thúc; tài liệu dùng Ctrl+D làm ví dụ. `UserInterruptException` biểu thị người dùng nhấn Ctrl+C. Xử lý riêng hai trường hợp:

```java
import org.jline.reader.EndOfFileException;
import org.jline.reader.LineReader;
import org.jline.reader.UserInterruptException;

void runPrompt(LineReader reader) {
    while (true) {
        try {
            String line = reader.readLine("customer> ");
            processCommand(line);
        } catch (EndOfFileException eof) {
            // EOF: kết thúc REPL một cách bình thường.
            return;
        } catch (UserInterruptException interrupted) {
            // Ctrl+C: hủy thao tác hiện tại hoặc quay về prompt theo policy.
            cancelCurrentOperation();
        }
    }
}
```

Đoạn mã trên minh họa cách xử lý khi tự quản lý `LineReader`; ứng dụng Spring Shell dùng runner có thể đã xử lý vòng đọc và EOF ở tầng framework. Không tự tạo thêm một vòng đọc JLine bên trong command nếu không có lý do rõ ràng.

Phím gửi EOF phụ thuộc terminal, shell và cấu hình control character. Trên nhiều terminal POSIX, Ctrl+D thường là VEOF; một số Windows console dùng Ctrl+Z rồi Enter cho input được redirect. Với JLine, key binding và provider đang dùng có thể thay đổi hành vi. Tài liệu vận hành nên nêu đúng tổ hợp phím đã kiểm thử trên môi trường mục tiêu thay vì coi một phím là chuẩn chung.

## Phân biệt EOF, Ctrl+C và lỗi I/O

| Trạng thái | Ý nghĩa | Hành động phù hợp |
|---|---|---|
| EOF | Không còn dữ liệu đầu vào | Dừng vòng đọc; hoàn tất hoặc báo input không đủ theo hợp đồng |
| Ctrl+C / interrupt | Người dùng muốn hủy thao tác | Hủy an toàn, giải phóng tài nguyên và trả prompt/exit theo policy |
| IOException | Lỗi đọc luồng, thiết bị hoặc pipe | Dừng thao tác, báo lỗi kỹ thuật và giữ nguyên dữ liệu đã xử lý theo transaction policy |
| Dòng trống | Một record/dòng không có nội dung | Bỏ qua, chấp nhận hoặc báo validation theo định dạng dữ liệu |
| Timeout | Không có dữ liệu trong khoảng thời gian quy định | Áp dụng timeout/cancel riêng; không tự coi là EOF nếu stream còn mở |

Không bắt `Exception` rồi trả về thành công cho mọi trường hợp. EOF bình thường có thể là kết thúc hợp lệ của file; EOF trước khi nhận đủ header hoặc record bắt buộc có thể là input không hoàn chỉnh. Quyết định này thuộc hợp đồng command.

## Xử lý prompt khi không có PTY

Command hỗ trợ cả terminal và CI nên có đường fallback rõ ràng. Ví dụ command cho phép người dùng chọn file trong interactive mode nhưng yêu cầu `--file` khi chạy tự động:

```java
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.context.ShellContext;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class ImportCommands {

    private final ImportPromptService promptService;

    ImportCommands(ImportPromptService promptService) {
        this.promptService = promptService;
    }

    @ShellMethod(key = "customer-import-file")
    public String importFile(
            @ShellOption(value = "file", defaultValue = ShellOption.NULL)
            String file,
            CommandContext commandContext) {

        ShellContext shellContext = commandContext.getShellContext();
        boolean canPrompt =
                shellContext.getInteractionMode() == InteractionMode.INTERACTIVE
                && shellContext.hasPty();

        if (file == null && !canPrompt) {
            throw new IllegalArgumentException(
                    "Thiếu --file. Ví dụ: customer-import-file --file customers.csv");
        }

        if (file == null) {
            file = promptService.askForFile();
        }

        validateReadableFile(file);
        importFromFile(file);
        return "Đã nhập dữ liệu từ " + file;
    }

    private void validateReadableFile(String file) {
        // Kiểm tra đường dẫn, quyền đọc và định dạng.
    }

    private void importFromFile(String file) {
        // Gọi service nghiệp vụ.
    }
}
```

Ví dụ dùng `ShellOption.NULL` để option có thể vắng mặt, giúp method được gọi và tự quyết định có thể hỏi hay không. Nếu parser bắt buộc option trước khi gọi method, command không có cơ hội mở prompt. Dùng cú pháp optional phù hợp với annotation model/version của ứng dụng.

Không tự chọn một giá trị mặc định nguy hiểm khi không có PTY. Với thao tác xóa, triển khai production hoặc ghi đè dữ liệu, yêu cầu option xác nhận tường minh như `--yes` và vẫn kiểm tra authorization/precondition.

## JLine khi stdin/stdout được chuyển hướng

JLine tạo system terminal dựa trên terminal mà JVM dùng khi khởi chạy. Khi process được chạy với stdin/stdout là pipe hoặc file, JLine có thể không nhận diện được TTY và fallback sang dumb terminal. Trong trường hợp đó, line editing, completion, terminal size và điều khiển cursor có thể không hoạt động như trong terminal thật.

Trên POSIX, JLine có thể được cấu hình dùng `/dev/tty` để truy cập controlling terminal dù stdin/stdout đang được redirect:

```bash
java -Dorg.jline.terminal.devtty=true -jar customer-cli.jar
```

Chỉ bật fallback này khi ứng dụng thực sự cần hỏi người dùng qua controlling terminal trong khi stdin/stdout đang dành cho dữ liệu khác. Nó không tạo ra terminal cho một CI runner không có controlling terminal, không giải quyết EOF của pipe và không nên được dùng để ép prompt trong batch job.

Nếu mục tiêu là chạy tự động, hãy chọn `NonInteractiveShellRunner` và dùng arguments/file/pipe. Nếu mục tiêu là có REPL, hãy khởi chạy từ terminal có PTY. Không cố chữa mọi lỗi no-TTY bằng cách ép `TERM=xterm` hoặc bật `/dev/tty`; khai báo terminal type sai có thể khiến ứng dụng gửi control sequence không được hỗ trợ.

## Kiểm tra môi trường chạy

Trên Linux/macOS, có thể kiểm tra stdin và stdout có phải terminal không:

```bash
if [ -t 0 ]; then
  echo "stdin is a terminal"
else
  echo "stdin is redirected or piped"
fi

if [ -t 1 ]; then
  echo "stdout is a terminal"
else
  echo "stdout is redirected or piped"
fi

tty
```

`test -t 0` và `test -t 1` kiểm tra hai file descriptor riêng. stdin có thể là pipe trong khi stdout vẫn là terminal, hoặc ngược lại. Đây là lý do không nên dùng một phép kiểm tra duy nhất để suy ra toàn bộ môi trường.

Trong Java, `System.console() == null` là một dấu hiệu JVM không có console được gắn trực tiếp, nhưng không mô tả đầy đủ trạng thái của mọi pipe/PTY. Với Spring Shell 3.x, ưu tiên dùng `ShellContext.hasPty()` cho quyết định về khả năng prompt; dùng kiểm tra stream riêng khi command cần đọc dữ liệu.

Ví dụ kiểm tra hai điều kiện ở command:

```java
ShellContext shellContext = commandContext.getShellContext();
boolean interactiveMode =
        shellContext.getInteractionMode() == InteractionMode.INTERACTIVE;
boolean terminalAvailable = shellContext.hasPty();

if (interactiveMode && terminalAvailable) {
    // Có thể dùng prompt, history, completion và component tương tác.
} else {
    // Yêu cầu input qua option, file hoặc pipe; không chờ bàn phím.
}
```

## Kiểm thử các trường hợp không có terminal và EOF

Kiểm thử phải bao phủ cả trạng thái không có PTY nhưng stdin có dữ liệu, và trường hợp stdin kết thúc ngay từ đầu. Không gộp hai trường hợp này thành một test “non-interactive”.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Interactive + PTY | Prompt xuất hiện và command nhận được input |
| Interactive mode nhưng không PTY | Command không gọi prompt; thiếu option thì báo hướng dẫn |
| Non-interactive + stdin có pipe data | Command đọc hết dữ liệu và xử lý đúng số record |
| Non-interactive + stdin rỗng | Command báo input rỗng hoặc hoàn tất 0 record theo hợp đồng |
| File có dòng trống | Dòng trống được xử lý theo policy; không bị coi là EOF |
| EOF sau một số record hợp lệ | Dừng đọc và giữ kết quả đã commit theo transaction policy |
| EOF giữa record/header bắt buộc | Báo dữ liệu không hoàn chỉnh, không giả vờ thành công |
| Ctrl+C trong khi đọc | Hủy thao tác, giải phóng tài nguyên và không nhầm với EOF |
| Pipe producer lỗi | Lỗi I/O được báo, không bị đổi thành thành công |
| Script `@file` hết dòng | Runner kết thúc đọc script và process kết thúc đúng |
| Script có command lỗi | Exit/status tuân theo policy tiếp tục hay dừng của ứng dụng |
| Output redirect | Không in prompt/ANSI vào dữ liệu máy đọc |
| Docker có `-it` và không có `-t` | Hành vi interactive/non-interactive đúng mục đích |
| Terminal raw mode | Attributes được khôi phục sau EOF, interrupt và exception |

Với test unit, dùng `StringReader("")` hoặc `ByteArrayInputStream(new byte[0])` để mô phỏng EOF ngay lập tức; dùng một stream có dữ liệu rồi kết thúc để mô phỏng pipe. Với test Spring Shell, dùng non-interactive session để xác nhận command không chờ input bàn phím và dùng interactive session cho luồng prompt. Chọn API test theo minor version Spring Shell đang dùng.

Ví dụ kiểm thử một reader thuần Java:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.StringReader;

import org.junit.jupiter.api.Test;

class InputReaderTests {

    @Test
    void emptyInputIsEofNotAnEmptyLine() throws Exception {
        BufferedReader reader = new BufferedReader(new StringReader(""));
        assertThat(reader.readLine()).isNull();
    }

    @Test
    void blankLineIsDataBeforeEof() throws Exception {
        BufferedReader reader = new BufferedReader(new StringReader("\n"));
        assertThat(reader.readLine()).isEmpty();
        assertThat(reader.readLine()).isNull();
    }
}
```

## Khôi phục terminal và giải phóng tài nguyên

Nếu ứng dụng tự thay đổi terminal attributes, chuyển sang raw mode hoặc tắt echo, phải khôi phục trạng thái ban đầu trong `finally`. Nếu process kết thúc khi terminal còn raw mode, người dùng có thể không thấy ký tự mình gõ, con trỏ biến mất hoặc Ctrl+C không hoạt động như mong đợi.

Ví dụ với JLine:

```java
import org.jline.terminal.Attributes;
import org.jline.terminal.Terminal;

void readRawInput(Terminal terminal) {
    Attributes original = terminal.getAttributes();
    try {
        Attributes raw = new Attributes(original);
        raw.setLocalFlag(Attributes.LocalFlag.ICANON, false);
        raw.setLocalFlag(Attributes.LocalFlag.ECHO, false);
        raw.setLocalFlag(Attributes.LocalFlag.ISIG, false);
        terminal.setAttributes(raw);
        // Đọc input ở chế độ raw.
    } finally {
        terminal.setAttributes(original);
    }
}
```

Đây là minh họa cho code tự điều khiển terminal; nếu dùng JLine `LineReader` hoặc Spring Shell runner, để thư viện quản lý mode của nó. Không gọi `enterRawMode()` chỉ để đọc một dòng thông thường.

Khi nhận EOF, Ctrl+C hoặc lỗi I/O, đóng file, socket, stream do ứng dụng sở hữu và giải phóng lock/transaction phù hợp. Không đóng `System.in` trong một command của REPL nếu shell còn cần dùng nó cho command tiếp theo.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Command treo trong CI | Vẫn gọi prompt hoặc interactive component khi không có PTY | Kiểm tra `InteractionMode` và `hasPty()`; yêu cầu option/config |
| `hasPty()` false nhưng pipe có dữ liệu | Nhầm không có PTY với stdin rỗng | Đọc stdin theo hợp đồng non-interactive |
| Command coi dòng trống là EOF | Dùng `isBlank()` thay vì kiểm tra `null`/EOF exception | Phân biệt empty line và end-of-stream |
| Vòng đọc chạy mãi sau EOF | Không thoát khi `readLine()` trả `null` hoặc không bắt `EndOfFileException` | Kết thúc vòng đọc đúng lúc |
| Ctrl+C bị xử lý như EOF | Gộp interrupt và end-of-stream vào cùng catch | Xử lý `UserInterruptException` riêng |
| REPL không mở sau khi nâng lên 3.3.x | `InteractiveShellRunner` không còn bật mặc định | Bật `spring.shell.interactive.enabled=true` |
| `@script` không chạy | `ScriptShellRunner` chưa bật | Bật `spring.shell.script.enabled=true` |
| JLine chỉ hiển thị dumb terminal | stdin/stdout bị redirect hoặc thiếu terminal provider | Chạy trong terminal có PTY hoặc chọn non-interactive mode |
| `/dev/tty` fallback không hoạt động trong CI | Không có controlling terminal để mở | Dùng command arguments, script file hoặc pipe |
| Prompt ăn mất dữ liệu pipe | REPL và command cùng đọc stdin | Chọn một owner cho stdin; dùng non-interactive runner khi command đọc payload |
| Output CSV chứa prompt/banner | Command ghi thông báo vào stdout cùng dữ liệu | Tách output máy đọc và thông báo chẩn đoán |
| Terminal không gõ được sau exception | Raw mode/attributes chưa được khôi phục | Lưu attributes và restore trong `finally` |
| EOF giữa file import vẫn báo thành công | Không kiểm tra record/header bắt buộc | Validate completeness trước khi commit hoặc báo partial result |

## Quy trình xử lý no-terminal và EOF

1. Xác định runner cần dùng: interactive REPL, non-interactive command hay script runner.
2. Kiểm tra `InteractionMode` và `ShellContext.hasPty()` trước khi mở prompt.
3. Xác định command đọc dữ liệu từ option, file, pipe hay terminal; không dùng chung stdin cho hai mục đích.
4. Khi đọc `BufferedReader`, coi `null` là EOF; khi dùng JLine, xử lý `EndOfFileException`.
5. Xử lý Ctrl+C/interrupt riêng với EOF và lỗi I/O.
6. Quy định rõ input rỗng, dòng trống và EOF giữa record được xử lý ra sao.
7. Không chờ prompt trong CI; thiếu dữ liệu bắt buộc thì trả lỗi có ví dụ cách gọi.
8. Chỉ bật `/dev/tty` fallback khi có lý do tương tác cụ thể trên POSIX.
9. Khôi phục terminal attributes và giải phóng tài nguyên ở mọi đường thoát.
10. Kiểm thử terminal thật, pipe có dữ liệu, pipe rỗng, script hết file, interrupt và output redirect.

Không có terminal chỉ có nghĩa là không thể dựa vào giao diện nhập phím thông thường. Dữ liệu vẫn có thể đến qua stdin, file hoặc process arguments. EOF mới là tín hiệu luồng đã kết thúc. Khi tách bạch hai khái niệm này và chọn đúng ShellRunner, command Spring Shell có thể chạy ổn định trong terminal, script và CI mà không treo hoặc xử lý nhầm dữ liệu.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): `InteractiveShellRunner`, `NonInteractiveShellRunner`, `ScriptShellRunner` và thay đổi mặc định từ 3.3.x.
- [Spring Shell 3.3.0 API — ShellContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/context/ShellContext.html): `getInteractionMode()` và `hasPty()`.
- [Spring Shell 3.3.0 API — CommandContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandContext.html): lấy `ShellContext` qua `getShellContext()`.
- [Spring Shell 3.4.2 API — NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/NonInteractiveShellRunner.html): thực thi command mà không vào interactive shell.
- [Spring Shell 3.4.3 API — ScriptShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html): nhận đối số `@file` để chạy script rồi kết thúc.
- [Spring Shell 3.4.3 API — FileInputProvider](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/FileInputProvider.html): `readInput()` trả `null` khi hết dữ liệu và yêu cầu shell thoát.
- [JLine 3.x — Line Reading](https://jline.org/versions/3.x/docs/line-reader/): `LineReader.readLine()`, `EndOfFileException`, `UserInterruptException` và vòng đọc REPL.
- [JLine 3.x — Terminal](https://jline.org/versions/3.x/docs/terminal/): system terminal, terminal capabilities, pipe redirection và `/dev/tty` fallback.
- [JLine 3.x — Terminal Attributes](https://jline.org/versions/3.x/docs/advanced/terminal-attributes/): VEOF, VINTR, canonical/raw mode và khôi phục attributes.
- [JLine 3.x — Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/): giới hạn terminal non-interactive, terminal size và các vấn đề terminal provider.
