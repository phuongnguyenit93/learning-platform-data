# Khôi phục trạng thái terminal khi lỗi hoặc bị ngắt

## 1. Vì sao terminal có thể bị giữ ở trạng thái không mong muốn?

Một CLI tương tác có thể thay đổi cách terminal nhận phím và hiển thị nội dung. Ví dụ, khi hiển thị giao diện toàn màn hình, đọc một phím đơn, nhập mật khẩu hoặc bật theo dõi chuột, ứng dụng có thể thay đổi thuộc tính terminal hoặc gửi các chuỗi điều khiển ANSI.

Nếu command kết thúc bình thường, người dùng thường không nhận ra vấn đề. Nhưng nếu exception xảy ra, người dùng nhấn Ctrl+C, luồng bị interrupt hoặc ứng dụng đóng đột ngột trước khi khôi phục các thay đổi, terminal có thể giữ trạng thái cũ:

- Ký tự gõ vào không còn hiển thị vì chế độ echo vẫn tắt.
- Phím chỉ được gửi sau khi nhấn Enter vì terminal vẫn ở chế độ canonical hoặc ngược lại.
- Ctrl+C không còn hoạt động như mong đợi vì xử lý signal đã bị thay đổi.
- Con trỏ bị ẩn, màu chữ chưa được reset hoặc màn hình vẫn ở alternate screen.
- Chế độ theo dõi chuột hoặc một chế độ bàn phím đặc biệt vẫn còn bật.

Nguyên tắc quan trọng là mọi thay đổi trạng thái terminal phải có đường khôi phục tương ứng. Đặt phần khôi phục trong `finally` để nó chạy cả khi thao tác thành công lẫn khi có exception hoặc cancellation.

## 2. Có nhiều lớp trạng thái cần khôi phục

Không phải mọi trạng thái hiển thị đều được lưu trong cùng một nơi. Khi chẩn đoán lỗi, hãy phân biệt ba lớp:

| Lớp | Ví dụ | Cách khôi phục |
|---|---|---|
| Thuộc tính terminal của hệ điều hành | Echo, canonical mode, xử lý signal và control character | Lưu `Attributes`, sau đó gọi `Terminal.setAttributes(...)`. |
| Trạng thái hiển thị của terminal emulator | Màu chữ, con trỏ, alternate screen, mouse tracking | Gửi chuỗi điều khiển thoát tương ứng hoặc dùng lifecycle của JLine/TerminalUI. |
| Tài nguyên và vòng đời ứng dụng | Terminal, LineReader, event loop, listener, background task | Đóng hoặc dispose tài nguyên do ứng dụng sở hữu; để Spring quản lý bean của framework. |

Khôi phục `Attributes` không tự động reset mọi chế độ ANSI mà ứng dụng đã bật. Ngược lại, gửi mã reset màu không khôi phục echo hoặc canonical mode của hệ điều hành. Cần biết command đã thay đổi lớp nào để khôi phục đúng lớp đó.

## 3. Dùng `try/finally` khi thay đổi terminal attributes

JLine cung cấp `Terminal` và `Attributes` để đọc, thay đổi và khôi phục các thuộc tính terminal. Trước khi thay đổi, lấy một bản sao trạng thái hiện tại. Sau khi hoàn tất, áp dụng lại bản sao đó trong `finally`.

Ví dụ dưới đây tạm thời chuyển terminal sang raw mode để đọc một phím:

~~~java
import java.io.IOException;

import org.jline.terminal.Attributes;
import org.jline.terminal.Terminal;
import org.springframework.stereotype.Component;

@Component
public class KeyReader {

    private final Terminal terminal;

    public KeyReader(Terminal terminal) {
        this.terminal = terminal;
    }

    public int readOneKey() throws IOException {
        // enterRawMode thay đổi attributes và trả về trạng thái ban đầu.
        Attributes original = terminal.enterRawMode();

        try {
            terminal.writer().println("Nhấn một phím bất kỳ...");
            terminal.flush();

            return terminal.reader().read();
        }
        finally {
            // Khôi phục cả khi read() ném IOException hoặc luồng bị hủy.
            terminal.setAttributes(original);
            terminal.flush();
        }
    }
}
~~~

`Terminal.enterRawMode()` trả về `Attributes` ban đầu trước khi chuyển sang raw mode. Raw mode cho phép đọc từng ký tự, đồng thời thay đổi cách terminal xử lý echo, line buffering và signal. Gọi `setAttributes(original)` trong `finally` để khôi phục đúng trạng thái trước đó.

Nếu chỉ cần tạm tắt echo khi nhập dữ liệu nhạy cảm, JLine cũng cung cấp `terminal.echo(false)`. Phương thức này trả về trạng thái echo trước đó; hãy lưu và khôi phục chính giá trị đó:

~~~java
boolean previousEcho = terminal.echo(false);
try {
    // Đọc dữ liệu nhạy cảm bằng input reader phù hợp.
}
finally {
    terminal.echo(previousEcho);
}
~~~

Không mặc định echo ban đầu luôn bật. Khôi phục giá trị thực tế đã lưu để không ghi đè trạng thái do thành phần khác thiết lập trước đó.

## 4. Không đóng Terminal do Spring Shell quản lý bên trong command

Trong ứng dụng Spring Shell 4.x có JLine integration, `JLineShellAutoConfiguration` tạo bean `org.jline.terminal.Terminal` và dùng nó để xây dựng `LineReader`, `JLineInputProvider` và `JLineShellRunner`. Auto-configuration xử lý việc đóng terminal khi application context nhận sự kiện đóng.

Spring Shell 4.0.4 cũng có bản sửa cho lỗi `IllegalStateException: Terminal has been closed` khi thoát ứng dụng shell từ IDE (issue #1363). Nếu gặp lỗi này, hãy xác nhận phiên bản thực tế trên runtime và kiểm tra xem code ứng dụng có đang đóng terminal dùng chung trước khi context kết thúc hay không.

Vì terminal là tài nguyên dùng chung của shell, command chỉ nên thay đổi thuộc tính tạm thời rồi khôi phục. Không gọi `terminal.close()` trong một command đang chạy. Nếu command đóng terminal dùng chung, các command tiếp theo có thể gặp lỗi như `IllegalStateException: Terminal has been closed`.

Hãy phân biệt quyền sở hữu tài nguyên:

- **Terminal được inject từ Spring:** không tự đóng trong command; chỉ khôi phục các thuộc tính mà command đã thay đổi.
- **Terminal do code tự tạo bằng `TerminalBuilder`:** code tạo terminal chịu trách nhiệm đóng nó, tốt nhất bằng try-with-resources.
- **Terminal của Spring Shell:** để lifecycle của application context và auto-configuration quản lý.

Ví dụ terminal do một chương trình độc lập tự tạo:

~~~java
import org.jline.terminal.Terminal;
import org.jline.terminal.TerminalBuilder;

public class StandaloneTerminalTask {

    public void run() throws Exception {
        try (Terminal terminal = TerminalBuilder.builder().build()) {
            terminal.writer().println("Đang chạy tác vụ terminal riêng");
            terminal.flush();
        }
        // close() được gọi tự động khi rời khỏi khối try.
    }
}
~~~

Ví dụ này dành cho tài nguyên do code tự tạo. Không áp dụng try-with-resources lên bean `Terminal` được Spring Shell chia sẻ.

## 5. Khôi phục khi command ném exception

Khi một command thay đổi trạng thái terminal rồi phát sinh exception, phần `finally` vẫn phải chạy trước khi exception được chuyển lên shell. Hãy giữ phần thao tác terminal càng ngắn càng tốt và không đặt logic khôi phục sau một lệnh `return` ở nhánh thành công.

~~~java
public String showInteractivePanel() throws IOException {
    Attributes original = terminal.enterRawMode();

    try {
        return renderAndReadSelection();
    }
    finally {
        terminal.setAttributes(original);
        terminal.flush();
    }
}
~~~

Nếu phần khôi phục cũng có thể phát sinh exception, hãy ghi nhận lỗi đó mà không làm mất nguyên nhân ban đầu. Với tài nguyên có nhiều bước cleanup, có thể dùng các helper method riêng và xử lý từng bước độc lập để một lỗi cleanup không ngăn các bước còn lại.

Không dùng `System.exit(...)` bên trong command để thoát khi có lỗi. Cách đó kết thúc JVM ngay tại vị trí gọi và bỏ qua các bước cleanup thông thường của command, Spring và JLine. Hãy ném exception phù hợp hoặc trả trạng thái lỗi để shell và application lifecycle xử lý.

## 6. Xử lý Ctrl+C và terminal signals

JLine biểu diễn các tín hiệu terminal bằng `Terminal.Signal`. Một số tín hiệu thường gặp:

| Signal | Thao tác thường gặp | Ý nghĩa |
|---|---|---|
| `INT` | Ctrl+C | Ngắt thao tác hiện tại hoặc yêu cầu kết thúc. |
| `TSTP` | Ctrl+Z trên hệ thống hỗ trợ | Tạm dừng tiến trình. |
| `CONT` | Tiếp tục tiến trình sau khi được resume | Tiến trình hoạt động trở lại. |
| `WINCH` | Thay đổi kích thước terminal | Cần cập nhật layout hoặc vẽ lại giao diện. |

JLine có thể đăng ký handler bằng `terminal.handle(signal, handler)`. Phương thức này trả về handler trước đó. Handler nên ngắn và không thực hiện thao tác blocking; tài liệu JLine khuyến nghị tránh các công việc có thể gây deadlock trong signal handler.

Signal và cách terminal chuyển phím điều khiển thành signal có thể khác nhau giữa hệ điều hành, terminal emulator và kiểu kết nối. Hãy kiểm tra trên các môi trường mà CLI hỗ trợ; không giả định Ctrl+Z hoặc mọi signal POSIX đều hoạt động giống nhau trên Windows.

Nếu ứng dụng thật sự cần tạm thay handler cho `INT`, hãy giữ handler trước đó và khôi phục trong `finally`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.jline.terminal.Terminal;
import org.jline.terminal.Terminal.Signal;
import org.jline.terminal.Terminal.SignalHandler;

public void runCancelableOperation(Terminal terminal) {
    AtomicBoolean cancelRequested = new AtomicBoolean(false);

    SignalHandler previous = terminal.handle(
            Signal.INT,
            signal -> cancelRequested.set(true));

    try {
        while (!operationFinished()) {
            if (cancelRequested.get()) {
                throw new OperationCancelledException("Thao tác bị người dùng ngắt");
            }

            performOneStep();
        }
    }
    finally {
        // Trả handler INT về đúng handler đã được đăng ký trước đó.
        terminal.handle(Signal.INT, previous);
    }
}
~~~

`operationFinished()`, `performOneStep()` và `OperationCancelledException` là thành phần minh họa của ứng dụng. Chỉ cài handler riêng khi command có yêu cầu xử lý Ctrl+C đặc biệt. Nếu thay handler toàn cục mà không khôi phục, hành vi Ctrl+C của JLine hoặc shell có thể bị thay đổi cho những lần nhập lệnh sau.

Handler trong ví dụ chỉ đặt cờ cancellation. Vòng xử lý chính nhận ra cờ và thực hiện cleanup trong `finally`. Không nên in nhiều dòng, chờ thread khác hoặc đóng terminal ngay bên trong signal handler.

## 7. Phân biệt signal với Java thread interruption

Ctrl+C có thể được JLine biểu diễn thành `Terminal.Signal.INT`. Java thread interruption là cơ chế riêng của JVM, thường xảy ra khi một thread đang chờ bị gọi `interrupt()`.

Nếu một phương thức blocking ném `InterruptedException`, hãy khôi phục trạng thái interrupt sau khi đã xử lý cleanup:

~~~java
public Result executeTask() {
    try {
        return longRunningService.execute();
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new TaskInterruptedException("Tác vụ bị ngắt", ex);
    }
    finally {
        releaseTemporaryResources();
    }
}
~~~

Ví dụ giả định `longRunningService.execute()` có thể ném `InterruptedException`. Khôi phục cờ interrupt giúp các lớp gọi phía trên biết thread đã bị ngắt. Không bắt `InterruptedException` rồi bỏ qua, vì như vậy có thể làm mất tín hiệu dừng của ứng dụng.

Khi command dùng cả signal handler và thread cancellation, hãy xác định một cơ chế cancellation rõ ràng để chuyển yêu cầu dừng đến công việc đang chạy. Phần cleanup vẫn phải nằm trong luồng điều khiển có thể thực thi `finally`.

## 8. Khôi phục các chế độ hiển thị ANSI và giao diện toàn màn hình

JLine terminal attributes quản lý hành vi nhập liệu ở cấp terminal. Một số chế độ hiển thị lại do terminal emulator quản lý, ví dụ:

- Màu và thuộc tính chữ (bold, underline, inverse).
- Ẩn hoặc hiện con trỏ.
- Alternate screen buffer.
- Mouse tracking.
- Chế độ bàn phím đặc biệt.

Nếu code tự bật một chế độ hiển thị, hãy gửi chuỗi thoát tương ứng khi rời khỏi chế độ đó, kể cả khi có exception. Có thể dùng các capability mà terminal cung cấp qua JLine thay vì giả định mọi terminal hỗ trợ cùng một chuỗi ANSI.

Ví dụ, khi tự thay đổi màu hoặc thuộc tính chữ, hãy reset style sau khi in:

~~~java
try {
    terminal.puts(InfoCmp.Capability.enter_bold_mode);
    terminal.writer().println("Đang xử lý...");
}
finally {
    terminal.puts(InfoCmp.Capability.exit_attribute_mode);
    terminal.flush();
}
~~~

Đoạn mã cần import `org.jline.utils.InfoCmp`. Capability cụ thể phụ thuộc terminfo và loại terminal; hãy kiểm tra capability có được hỗ trợ trước khi phụ thuộc vào nó. Nếu dùng Spring Shell `TerminalUI` hoặc các component TUI của framework, ưu tiên lifecycle của component để kết thúc event loop và dọn trạng thái giao diện thay vì tự phát nhiều chuỗi điều khiển rời rạc.

Với giao diện toàn màn hình, JLine có capability `enter_ca_mode` và `exit_ca_mode` để vào/ra alternate screen. Với con trỏ, có `cursor_invisible` và `cursor_normal`. Hãy ghép mỗi thao tác bật với thao tác thoát tương ứng trong cùng một `try/finally`; nếu ứng dụng dùng `TerminalUI`, để thành phần UI quản lý các chế độ mà nó sở hữu.

Không giả định reset màu cũng khôi phục con trỏ, alternate screen và mouse tracking. Mỗi chế độ cần có thao tác thoát tương ứng hoặc phải được thành phần UI sở hữu nó quản lý.

## 9. Đóng shell và đóng ApplicationContext

Trong Spring Shell 4.x, command built-in `quit` (có alias `exit`) kết thúc vòng lặp interactive shell. Khi application context đóng, các thành phần JLine của Spring Shell có cơ hội thực hiện cleanup và đóng terminal.

Nếu cần yêu cầu Spring application context đóng sau khi shell hoàn tất phần thực thi, có thể cấu hình:

~~~properties
spring.shell.context.close=true
~~~

Property này không bật mặc định. Tài liệu Spring Shell mô tả nó đăng ký listener để yêu cầu đóng context sau khi shell hoàn thành logic thực thi. Điều này hữu ích với ứng dụng có thread nền hoặc tài nguyên khiến context vẫn còn sống sau khi runner kết thúc.

`quit` kết thúc vòng lặp shell; `spring.shell.context.close=true` điều khiển việc đóng application context sau khi shell hoàn tất. Khi context đóng, JLine auto-configuration thực hiện cleanup terminal theo lifecycle của nó. Không cần tự gọi `close()` trên terminal dùng chung từ command `quit` hoặc command nghiệp vụ.

## 10. Điều gì xảy ra khi ứng dụng bị kết thúc đột ngột?

`finally`, `AutoCloseable.close()` và shutdown hook giúp cleanup trong các đường kết thúc có thể kiểm soát. Nhưng không có cơ chế Java nào bảo đảm cleanup luôn chạy khi tiến trình bị kết thúc cưỡng bức.

| Tình huống | Khả năng cleanup |
|---|---|
| Command hoàn tất bình thường | `finally` chạy. |
| Command ném exception | `finally` chạy khi stack unwinding diễn ra. |
| Thread bị interrupt | Cleanup chạy nếu code xử lý interruption và thoát qua `finally`. |
| Người dùng gọi `quit`/`exit` | Shell thoát theo luồng đóng bình thường; Spring/JLine thực hiện cleanup theo lifecycle. |
| JVM nhận tín hiệu shutdown có thể xử lý | Shutdown hook có thể chạy, nhưng không thay thế cleanup ở `finally`. |
| Tiến trình bị kill cưỡng bức, JVM crash hoặc máy mất điện | Không thể bảo đảm cleanup được thực thi. |

Không dựa vào shutdown hook như cơ chế duy nhất để khôi phục terminal. Hãy khôi phục ngay sau mỗi vùng code thay đổi trạng thái bằng `finally`; shutdown hook chỉ là lớp bảo vệ bổ sung cho tài nguyên thuộc quyền sở hữu của ứng dụng.

## 11. Khôi phục terminal thủ công khi màn hình đã bị lỗi

Nếu một chương trình bị dừng cưỡng bức sau khi tắt echo hoặc chuyển terminal sang raw mode, terminal hiện tại có thể không còn nhận lệnh như bình thường.

Trên terminal POSIX, nếu vẫn nhập được command, có thể thử:

~~~bash
stty sane
~~~

Lệnh này yêu cầu terminal line discipline trở về thiết lập thông thường, thường khôi phục echo và chế độ nhập theo dòng. Nếu màn hình vẫn còn màu, con trỏ hoặc layout bất thường, có thể chạy thêm:

~~~bash
reset
~~~

Trên Windows Terminal, PowerShell hoặc terminal tích hợp IDE, cách đơn giản nhất có thể là mở một terminal session mới hoặc dùng chức năng reset terminal của ứng dụng. Cách phục hồi cụ thể phụ thuộc terminal emulator và hệ điều hành.

Đây là biện pháp khôi phục sau sự cố. Ứng dụng vẫn phải tự dọn trạng thái trong luồng thực thi bình thường để không buộc người dùng sửa terminal thủ công.

## 12. Kiểm thử đường cleanup

Đừng chỉ kiểm tra command chạy thành công. Hãy chủ động tạo exception và interruption trong khi terminal đang ở trạng thái tạm thời.

Các ca kiểm thử cần có:

1. Raw mode được bật rồi command kết thúc bình thường; `ECHO` và `ICANON` trở về giá trị ban đầu.
2. Đọc input ném `IOException`; attributes vẫn được khôi phục.
3. Command ném runtime exception; shell tiếp tục nhận command và terminal vẫn nhập được.
4. Thread bị interrupt trong tác vụ blocking; cleanup chạy và interrupt flag được giữ lại.
5. Ctrl+C trong thao tác có handler tùy chỉnh; handler trước đó được khôi phục sau khi command kết thúc.
6. TUI kết thúc bình thường và do lỗi; event loop, cursor, alternate screen và mouse mode được dọn.
7. Gọi `quit` hoặc đóng application context; terminal được đóng theo lifecycle.
8. Chạy kiểm thử trên các terminal emulator và hệ điều hành mà ứng dụng hỗ trợ.

Với JLine, nên kiểm thử tích hợp bằng pseudo-terminal (PTY) để quan sát trạng thái terminal trước và sau khi command kết thúc. Kiểm tra object `Attributes` trong unit test là hữu ích, nhưng chưa đủ để xác nhận terminal emulator đã thoát alternate screen hoặc hiện lại con trỏ.

## 13. Quy trình thiết kế cleanup an toàn

1. Xác định terminal attributes hoặc chế độ hiển thị mà code cần thay đổi.
2. Lưu trạng thái ban đầu trước khi thay đổi.
3. Đặt thao tác thay đổi trong một vùng `try/finally` ngắn.
4. Khôi phục đúng trạng thái ban đầu trong `finally`.
5. Nếu đăng ký signal handler, lưu và khôi phục handler trước đó.
6. Nếu nhận `InterruptedException`, dọn tài nguyên và giữ lại interrupt flag.
7. Chỉ đóng `Terminal` do chính code tạo; để Spring quản lý terminal dùng chung.
8. Dùng lifecycle của Spring Shell/JLine khi đóng REPL hoặc application context.
9. Kiểm thử cả lỗi, Ctrl+C, thread interruption và đóng ứng dụng.

## Kết luận

Khôi phục terminal là một phần của quản lý tài nguyên. Trong Spring Shell 4.x dùng JLine, hãy lưu `Attributes` trước khi vào raw mode, khôi phục bằng `setAttributes()` trong `finally`, và trả signal handler về trạng thái trước đó nếu đã thay đổi. Terminal do Spring Shell quản lý cần được đóng theo lifecycle của application context; command chỉ nên khôi phục trạng thái tạm thời mà nó tự thay đổi. Với màu, con trỏ, alternate screen và mouse tracking, hãy thoát từng chế độ tương ứng. Cleanup trong `finally` là tuyến bảo vệ chính; shutdown hook và thao tác reset thủ công chỉ hỗ trợ những trường hợp tiến trình bị dừng ngoài luồng kiểm soát.

## Tài liệu tham khảo

- [Spring Shell – Context Close](https://docs.spring.io/spring-shell/reference/customization/contextclose.html)
- [Spring Shell 4.0.4 – Quit and Exit](https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html)
- [Spring Shell API – JLineShellAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [Spring Shell API – InteractiveShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InteractiveShellRunner.html)
- [JLine 3 – Terminal Attributes](https://jline.org/versions/3.x/docs/advanced/terminal-attributes/)
- [JLine 3 – Terminal and Signal Handling](https://jline.org/versions/3.x/docs/terminal/)
- [Spring Shell 4.0.4 – Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)
