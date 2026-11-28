# Phím ngắt lệnh, hủy chờ đầu vào và thoát tiến trình

Khi làm việc với CLI, người dùng cần biết cách dừng một thao tác đang chạy, hủy một dòng lệnh nhập nhầm, thoát khỏi lúc chương trình đang chờ dữ liệu và đóng ứng dụng khi hoàn tất. Các hành động này có vẻ giống nhau vì đều dùng phím điều khiển hoặc làm prompt biến mất, nhưng chúng tác động tới những phần khác nhau của ứng dụng.

Trong Spring Shell, terminal tương tác được đọc qua JLine. JLine phân biệt thao tác ngắt dòng đang nhập với tín hiệu kết thúc đầu vào; Spring Shell cũng có command `quit` và alias `exit` để yêu cầu shell đóng application context một cách có trật tự. Khi một command Java đang chạy, việc nhấn Ctrl+C lại phụ thuộc vào cách terminal và hệ điều hành chuyển tín hiệu tới tiến trình. Không nên mặc định mọi lần nhấn Ctrl+C đều tự động hủy được logic của command.

Bài này phân biệt năm tình huống: hủy dòng đang nhập, ngắt thao tác đang chạy, kết thúc luồng đầu vào, thoát shell có trật tự và kết thúc tiến trình ở cấp hệ điều hành. Bạn sẽ biết phím nào phù hợp, điều gì xảy ra với command và tài nguyên, cũng như cách thiết kế command chạy lâu để có thể dừng an toàn.

Sau bài này, bạn có thể:

- Phân biệt Ctrl+C khi đang nhập lệnh với Ctrl+C khi command đang thực thi.
- Hiểu `UserInterruptException` và `EndOfFileException` trong JLine.
- Dùng `quit` hoặc `exit` để đóng phiên Spring Shell có trật tự.
- Phân biệt EOF, suspend và terminate trên các terminal khác nhau.
- Thiết kế tác vụ dài có cơ chế hủy hợp tác bằng interruption hoặc cancellation token.
- Xử lý `InterruptedException` mà không làm mất trạng thái interrupt.
- Kiểm tra hành vi trên terminal tương tác, IDE, container và chế độ non-interactive.

> Các mô tả API trong bài dựa trên Spring Shell 3.3.x và JLine 3. Phím điều khiển thực tế phụ thuộc hệ điều hành, terminal emulator, keymap và cách ứng dụng khởi tạo terminal.

## 1. Năm hành động cần phân biệt

| Hành động | Tác động chính | Ví dụ |
|---|---|---|
| Hủy dòng đang nhập | Xóa đầu vào chưa gửi, quay lại prompt | Nhấn Ctrl+C khi đang gõ command trong JLine |
| Ngắt command đang chạy | Gửi tín hiệu ngắt tới tiến trình hoặc kích hoạt cơ chế hủy của ứng dụng | Ctrl+C khi command đang xử lý |
| Kết thúc đầu vào (EOF) | Báo cho chương trình rằng không còn dữ liệu đầu vào | Ctrl+D ở terminal Unix khi dòng nhập trống |
| Thoát shell có trật tự | Yêu cầu Spring Shell đóng application context | Gõ `quit` hoặc `exit` |
| Kết thúc tiến trình | Hệ điều hành dừng JVM | Tín hiệu terminate hoặc lệnh kết thúc tiến trình từ bên ngoài |

Một phím có thể có ý nghĩa khác nhau tùy trạng thái. Ví dụ, Ctrl+C khi JLine đang đọc dòng thường hủy dòng hiện tại; khi command đang chạy, terminal có thể gửi SIGINT tới tiến trình. Ctrl+D thường biểu thị EOF trên terminal Unix, không phải lệnh hủy command đang thực thi.

~~~mermaid
flowchart TD
    A[Người dùng tương tác với Spring Shell] --> B{Ứng dụng đang ở trạng thái nào?}
    B -->|Đang nhập command| C[Ctrl+C]
    C --> D[Hủy buffer nhập / UserInterruptException]
    B -->|Command đang chạy| E[Ctrl+C hoặc tín hiệu hệ điều hành]
    E --> F{Ứng dụng có cơ chế hủy?}
    F -->|Có| G[Hủy hợp tác và dọn dẹp]
    F -->|Không| H[Command có thể tiếp tục hoặc tiến trình bị kết thúc]
    B -->|Đang chờ input| I[EOF hoặc hủy theo API nhập]
    I --> J[EndOfFileException hoặc UserInterruptException]
    B -->|Muốn đóng shell| K[quit / exit]
    K --> L[Đóng Spring application context]
~~~

## 2. Ctrl+C khi đang nhập command

Trong phiên tương tác dùng JLine, người dùng có thể đang gõ một command nhưng chưa nhấn Enter. Khi nhấn Ctrl+C, JLine báo thao tác ngắt dòng nhập bằng `UserInterruptException`. Một vòng lặp REPL thường bắt exception này, bỏ phần buffer chưa hoàn chỉnh rồi hiển thị prompt để người dùng nhập lại.

Ví dụ:

~~~text
shell:>customer update --id 42 --status
^C
shell:>
~~~

Command chưa được gửi tới Spring Shell nên phương thức xử lý command chưa được gọi. Dữ liệu đã gõ trong dòng đó bị hủy; những command trước đó vẫn đã thực thi như bình thường.

JLine minh họa cách xử lý trong một vòng lặp đọc dòng:

~~~java
import org.jline.reader.EndOfFileException;
import org.jline.reader.LineReader;
import org.jline.reader.UserInterruptException;

public void readCommands(LineReader reader) {
    while (true) {
        try {
            String line = reader.readLine("shell:> ");
            process(line);
        } catch (UserInterruptException ex) {
            // Hủy dòng đang nhập và tiếp tục hiển thị prompt.
        } catch (EndOfFileException ex) {
            // Kết thúc vòng lặp khi đầu vào đã hết.
            return;
        }
    }
}
~~~

Đây là ví dụ vòng lặp JLine độc lập để minh họa hai loại exception. Ứng dụng Spring Shell đã có vòng lặp và tích hợp JLine riêng; thông thường không cần tự tạo `LineReader` hoặc tự viết REPL chỉ để hủy một dòng nhập.

### Hủy một dòng chưa hoàn chỉnh khác với hủy command

Giả sử người dùng gõ `invoice delete --id 42` nhưng chưa nhấn Enter. Ctrl+C hủy dòng này và command không chạy. Nếu người dùng đã nhấn Enter và command bắt đầu xóa dữ liệu, Ctrl+C không thể hoàn tác thao tác đã hoàn tất. Muốn có khả năng hoàn tác cần thiết kế transaction, xác nhận trước thao tác hoặc command bù trừ theo yêu cầu nghiệp vụ.

## 3. Ctrl+C khi command đang chạy

Khi command đã được gửi và phương thức Java đang thực thi, JLine không còn ở bước đọc dòng để nhận `UserInterruptException` theo cách trên. Terminal có thể gửi tín hiệu ngắt tới tiến trình foreground. Hành vi phụ thuộc hệ điều hành, terminal provider và signal handler được cài đặt.

Trên terminal POSIX, Ctrl+C thường tạo tín hiệu SIGINT cho foreground process group. Trên Windows, tài liệu JLine cảnh báo Ctrl+C mặc định có thể kết thúc ứng dụng nếu terminal không cài signal handler phù hợp. IDE console, SSH, container và terminal emulator cũng có thể xử lý tín hiệu khác nhau.

Điều quan trọng: **Ctrl+C không tự động biến mọi command Java thành một tác vụ có thể hủy an toàn.** Một vòng lặp tính toán, lời gọi thư viện không kiểm tra interrupt hoặc thao tác I/O đang chặn có thể không dừng ngay. Nếu tín hiệu được xử lý theo hành vi mặc định của hệ điều hành/JVM, cả tiến trình có thể kết thúc thay vì chỉ command hiện tại bị hủy.

Vì vậy, hãy phân biệt:

- **Signal handling:** terminal và hệ điều hành chuyển tín hiệu ngắt tới tiến trình.
- **Thread interruption:** một thread nhận trạng thái interrupt trong Java.
- **Cancellation:** logic ứng dụng nhận biết yêu cầu hủy, dừng công việc và giải phóng tài nguyên phù hợp.

Ba cơ chế này có liên quan nhưng không tự động đồng nhất. Muốn Ctrl+C dừng một command đang chạy mà vẫn giữ shell hoạt động, ứng dụng phải kết nối tín hiệu hoặc thao tác hủy với cơ chế cancellation của command và phải xử lý tình huống dọn dẹp.

## 4. Thiết kế command chạy lâu có thể hủy hợp tác

Một command chạy lâu nên chia công việc thành các bước có thể kiểm tra yêu cầu hủy. Với tác vụ chạy trên thread riêng, có thể dùng interruption hoặc cancellation token. Với tác vụ chạy trực tiếp trên thread xử lý command, cần đặc biệt cẩn thận vì việc chặn thread shell có thể làm prompt không phản hồi.

Ví dụ một service kiểm tra trạng thái interrupt giữa các batch:

~~~java
import java.util.List;

public class ImportService {

    public int importRows(List<String> rows) throws InterruptedException {
        int imported = 0;

        for (String row : rows) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("Yêu cầu dừng tác vụ import.");
            }

            importOne(row);
            imported++;
        }

        return imported;
    }

    private void importOne(String row) {
        // Kiểm tra, chuyển đổi và lưu một bản ghi.
    }
}
~~~

`isInterrupted()` đọc trạng thái interrupt mà không xóa cờ. Khi phát hiện yêu cầu hủy, service dừng ở ranh giới an toàn và báo lại cho caller. Nếu một thao tác bên trong ném `InterruptedException`, caller cũng cần xử lý đúng trạng thái đó.

### Không nuốt InterruptedException

Một lỗi thường gặp là bắt `InterruptedException` rồi bỏ qua:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ex) {
    // Không làm gì.
}
~~~

`InterruptedException` thường xóa trạng thái interrupt khi được ném. Nếu tầng hiện tại không thể truyền exception lên, hãy khôi phục cờ interrupt:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Nếu phương thức có thể khai báo `throws InterruptedException`, thường nên truyền exception lên để tầng gọi quyết định cách kết thúc. Không tiếp tục xử lý như thể tác vụ vẫn hoàn tất bình thường sau khi đã nhận yêu cầu interrupt.

### Hủy tác vụ chạy nền bằng Future

Nếu command khởi chạy công việc trên executor và giữ `Future`, bộ điều phối hủy có thể gọi `cancel(true)` để yêu cầu thread thực thi nhận interrupt:

~~~java
Future<Integer> future = executor.submit(() -> importService.importRows(rows));

// Tại điểm điều khiển hủy của ứng dụng:
future.cancel(true);
~~~

`cancel(true)` chỉ yêu cầu ngắt thread đang chạy. Tác vụ vẫn cần hợp tác bằng cách kiểm tra interrupt hoặc gọi API có thể bị ngắt. Nó không đảm bảo rollback các thay đổi đã ghi, cũng không thể cưỡng bức dừng an toàn một đoạn code không phản hồi interruption.

Ví dụ này chỉ minh họa cơ chế Java. Spring Shell không tự động nối Ctrl+C với `Future.cancel(true)` của ứng dụng. Muốn hỗ trợ thao tác hủy từ terminal, cần xây dựng và kiểm thử riêng đường truyền yêu cầu hủy, đồng thời bảo đảm terminal và signal handler do Spring Shell/JLine quản lý không bị ghi đè tùy tiện.

## 5. Hủy khi command đang chờ đầu vào

Một command có thể hỏi thêm thông tin sau khi đã bắt đầu, chẳng hạn yêu cầu người dùng xác nhận hoặc nhập mã OTP. Lúc này cần phân biệt việc hủy câu trả lời đang gõ với việc báo hết dữ liệu đầu vào.

Với JLine `LineReader`, hai tình huống được biểu diễn bằng:

| Exception | Ý nghĩa |
|---|---|
| `UserInterruptException` | Người dùng nhấn Ctrl+C trong lúc JLine đọc dòng |
| `EndOfFileException` | Đầu vào kết thúc; trên terminal Unix thường do Ctrl+D |

Ví dụ xử lý input bằng JLine:

~~~java
String confirmation;
try {
    confirmation = reader.readLine("Xác nhận triển khai (yes/no): ");
} catch (UserInterruptException ex) {
    return "Đã hủy bước xác nhận.";
} catch (EndOfFileException ex) {
    return "Đầu vào đã kết thúc; không tiếp tục triển khai.";
}
~~~

Ví dụ trên dành cho code sở hữu `LineReader`. Trong Spring Shell, hãy dùng cơ chế tương tác được hỗ trợ bởi ứng dụng và phiên bản đang chạy; không tự lấy `System.in` hoặc tạo một terminal thứ hai nếu framework đã quản lý luồng nhập.

Nếu command đang chờ input từ pipe hoặc file, Ctrl+D có thể được nhìn như EOF thay vì tín hiệu hủy. Nếu command đang chờ một lời gọi mạng hoặc database, Ctrl+C ở terminal không nhất thiết làm lời gọi đó dừng ngay. Hãy cấu hình timeout và cancellation riêng cho tài nguyên bên ngoài.

## 6. Ctrl+D, EOF và Ctrl+Z

EOF (end of file) báo rằng luồng đầu vào không còn dữ liệu. Nó không có nghĩa là hủy một command đang chạy.

### Ctrl+D trên terminal Unix-like

Trong terminal POSIX ở chế độ canonical, Ctrl+D thường là ký tự VEOF. Khi dòng nhập trống, nó làm thao tác đọc nhận EOF. Trong JLine, EOF được biểu diễn bằng `EndOfFileException`; một vòng lặp REPL thường kết thúc khi nhận exception này.

Nếu đang nhập một dòng có nội dung, hành vi VEOF có thể khác với lúc buffer trống vì terminal line discipline xử lý dữ liệu đã gõ. Không nên dùng Ctrl+D để xóa một dòng command chưa hoàn chỉnh; dùng phím hủy dòng phù hợp.

### Ctrl+Z trên POSIX

Trong nhiều terminal POSIX, Ctrl+Z là ký tự VSUSP và gửi SIGTSTP, làm tiến trình foreground tạm dừng. Đây là suspend, không phải thoát shell. Người dùng thường có thể đưa tiến trình trở lại foreground bằng `fg` trong shell hệ điều hành.

Không dùng Ctrl+Z như một cách thoát ứng dụng Spring Shell. Một tiến trình bị suspend vẫn còn tồn tại và giữ tài nguyên.

### Windows và các terminal khác

Windows Console, Windows Terminal, PowerShell, Git Bash, WSL và terminal trong IDE có thể ánh xạ phím điều khiển khác nhau. JLine có thể dùng native terminal provider để đọc control character; Ctrl+C trên Windows có thể kết thúc ứng dụng theo hành vi mặc định nếu không có signal handler. Ctrl+Z cũng không có cùng ý nghĩa suspend như terminal POSIX.

Khi cần nhận EOF trên Windows, kiểm tra tài liệu terminal/console đang sử dụng và thử với ứng dụng nhỏ trước khi đưa vào quy trình vận hành. Không giả định Ctrl+D hay Ctrl+Z hoạt động giống nhau trên mọi môi trường.

## 7. Thoát Spring Shell bằng quit hoặc exit

Spring Shell cung cấp built-in command `quit` và alias `exit`. Lệnh này yêu cầu shell thoát và đóng Spring application context một cách có trật tự:

~~~text
shell:>quit
~~~

Hoặc:

~~~text
shell:>exit
~~~

Đóng application context cho phép các bean thực hiện callback vòng đời, chẳng hạn `@PreDestroy`, `DisposableBean` hoặc hook đóng tài nguyên đã đăng ký. JLine history cũng có thể lưu lịch sử khi shell kết thúc theo cấu hình.

Đây là cách thoát bình thường được khuyến nghị trong phiên interactive. Nó khác với việc kill JVM từ bên ngoài hoặc gọi `Runtime.getRuntime().halt(...)`, vốn có thể bỏ qua phần lớn quy trình shutdown.

### Không gọi System.exit() trong command nghiệp vụ

Không nên dùng `System.exit(0)` bên trong command thông thường chỉ để thoát shell. Lệnh đó kết thúc JVM và ảnh hưởng toàn bộ ứng dụng, làm các command khác không thể chạy tiếp. Nó cũng khiến việc kiểm thử command trở nên khó khăn.

Nếu người dùng cần kết thúc shell, dùng built-in `quit` hoặc `exit`. Nếu ứng dụng cần yêu cầu shell đóng từ code, hãy dùng cơ chế shutdown/exit được Spring Shell cung cấp trong đúng phiên bản thay vì tự kết thúc JVM.

## 8. Shell thoát và tiến trình kết thúc có phải một việc?

Trong ứng dụng Spring Boot thông thường, Spring Shell chạy bên trong cùng JVM. Khi `quit` hoặc `exit` đóng application context, Spring Boot và các runner hoàn tất vòng đời ứng dụng. Nếu ứng dụng còn thread non-daemon hoặc tài nguyên do code tự tạo chưa được đóng, JVM có thể vẫn còn sống sau khi shell đã dừng.

| Tình huống | Kết quả |
|---|---|
| `quit` / `exit` trong interactive shell | Yêu cầu đóng shell và application context |
| Command non-interactive hoàn tất | Runner trả kết quả; ứng dụng kết thúc theo vòng đời khởi chạy |
| Ctrl+C với signal handler xử lý graceful shutdown | Ứng dụng có cơ hội chạy shutdown hook và đóng context |
| Ctrl+C theo hành vi terminate mặc định | JVM có thể bắt đầu shutdown hoặc bị kết thúc tùy môi trường |
| Kill cưỡng bức tiến trình | Có thể bỏ qua callback dọn dẹp của ứng dụng |
| Thread non-daemon vẫn chạy sau khi context đóng | JVM có thể chưa kết thúc |

Nếu command tạo `ExecutorService`, thread riêng, socket hoặc watcher, cần đóng chúng khi tác vụ hoàn tất hoặc khi context shutdown. Có thể dùng bean lifecycle, `@PreDestroy` hoặc quản lý tài nguyên bằng try-with-resources.

## 9. Interactive và non-interactive mode

Trong interactive mode, Spring Shell giữ phiên REPL để người dùng nhập nhiều command và thoát bằng `quit` hoặc `exit`. Các phím điều khiển của JLine chỉ có ý nghĩa khi ứng dụng đang đọc input tương tác từ terminal hỗ trợ.

Trong non-interactive mode, ứng dụng thường nhận một command từ tham số khởi chạy hoặc một nguồn input, thực thi rồi kết thúc theo runner. Built-in `quit` không có ý nghĩa tương tự vì không có REPL đang chờ để thoát. Exit code thường quan trọng ở chế độ này vì script hoặc hệ điều hành cần biết command thành công hay thất bại.

Ví dụ:

~~~powershell
java -jar app.jar customer list --status ACTIVE
~~~

Lệnh trên chạy một command và kết thúc tiến trình theo runner. Không thể nhấn Up hoặc gõ `exit` sau khi command đã hoàn tất vì shell không còn ở trạng thái tương tác.

Trong Spring Shell 3.3, cấu hình `spring.shell.interactive.enabled` điều khiển chế độ interactive. Khi thiết kế command, hãy xác định command có phù hợp với cả hai chế độ hay chỉ dành cho interactive; annotation legacy `@ShellMethod` có thuộc tính `interactionMode` để mô tả điều kiện khả dụng.

## 10. Xử lý tài nguyên khi hủy hoặc thoát

Khi command bị hủy, ứng dụng cần xác định tài nguyên nào phải được giải phóng và dữ liệu nào có thể đã được ghi:

- Dùng try-with-resources cho stream, reader, writer và file handle do command mở.
- Đóng transaction hoặc rollback khi nghiệp vụ cho phép và transaction chưa commit.
- Không xóa dữ liệu đã commit chỉ vì người dùng nhấn Ctrl+C sau đó.
- Hủy request mạng hoặc truy vấn database bằng API cancellation/timeout tương ứng.
- Đóng executor và thread do ứng dụng sở hữu khi context shutdown.
- Ghi trạng thái tác vụ dở dang nếu cần cho phép resume hoặc retry.
- Không đóng terminal hoặc `System.in`/`System.out` dùng chung do framework sở hữu.

Ví dụ:

~~~java
public void copyFile(Path source, Path target) throws IOException {
    try (InputStream input = Files.newInputStream(source);
         OutputStream output = Files.newOutputStream(target)) {
        input.transferTo(output);
    }
}
~~~

Try-with-resources bảo đảm stream được đóng khi phương thức kết thúc bình thường hoặc ném exception. Tuy nhiên, nó không tự xóa file đích đã tạo một phần. Nếu yêu cầu không để lại file dang dở, hãy ghi vào file tạm rồi đổi tên nguyên tử khi hoàn tất, đồng thời xử lý việc dọn file tạm khi bị hủy.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ctrl+C khi đang gõ làm mất dòng | JLine phát hiện user interrupt | Đây là hành vi hủy buffer nhập; gõ lại command nếu cần |
| Ctrl+C khi command chạy làm tắt cả app | Terminal chuyển SIGINT tới tiến trình và không có handler phù hợp | Kiểm tra terminal provider, signal handling và thiết kế cancellation |
| Ctrl+C không dừng vòng lặp Java | Code không kiểm tra interrupt hoặc đang ở API không thể ngắt | Thêm điểm kiểm tra cancellation, timeout hoặc API có hỗ trợ interrupt |
| Bắt InterruptedException rồi tác vụ vẫn chạy | Code nuốt exception và làm mất trạng thái interrupt | Truyền exception lên hoặc khôi phục cờ bằng `Thread.currentThread().interrupt()` |
| Ctrl+D không thoát shell | Terminal không ánh xạ phím thành EOF hoặc input không ở chế độ tương tác | Kiểm tra terminal, JLine và loại input đang dùng |
| Ctrl+Z làm ứng dụng đứng | Trên POSIX, tiến trình bị suspend thay vì thoát | Dùng `fg` để tiếp tục hoặc `quit` để thoát shell |
| `exit` không có tác dụng sau command một lần | Ứng dụng đã chạy non-interactive và không còn REPL | Để runner kết thúc hoặc xử lý exit code của command |
| Shell đã thoát nhưng JVM còn chạy | Thread non-daemon hoặc tài nguyên riêng chưa đóng | Quản lý executor, watcher và bean lifecycle |
| Dữ liệu bị ghi dở khi hủy | Tác vụ đã ghi một phần trước khi nhận yêu cầu dừng | Dùng transaction, file tạm, checkpoint hoặc cơ chế resume |
| IDE xử lý Ctrl+C khác terminal | Console của IDE có quy tắc signal riêng | Kiểm thử trên terminal mục tiêu và không suy rộng từ một môi trường |

## 12. Checklist thiết kế hành vi ngắt và thoát

- Xác định Ctrl+C đang được dùng để hủy dòng nhập hay ngắt command đang chạy.
- Phân biệt `UserInterruptException` với `EndOfFileException`.
- Không xem EOF là cancellation của tác vụ.
- Cung cấp `quit` hoặc `exit` để người dùng thoát interactive shell có trật tự.
- Không gọi `System.exit()` từ command nghiệp vụ.
- Thiết kế tác vụ dài có điểm kiểm tra cancellation.
- Không nuốt `InterruptedException`; truyền tiếp hoặc khôi phục interrupt flag.
- Cấu hình timeout và cancellation cho I/O, database và HTTP request.
- Dọn tài nguyên và xử lý dữ liệu dở dang khi hủy.
- Kiểm tra hành vi trên Windows, POSIX, IDE, SSH và container có/không có TTY.
- Phân biệt interactive runner với non-interactive runner và exit code.

## 13. Bài tập thực hành

Tạo command `data import --file <path>` có thể xử lý một file lớn:

1. Chạy command và nhập sai một option nhưng chưa nhấn Enter; nhấn Ctrl+C để xác nhận chỉ buffer nhập bị hủy.
2. Chạy lại command và cho service xử lý theo từng batch 100 bản ghi.
3. Thêm kiểm tra `Thread.currentThread().isInterrupted()` giữa các batch và dừng có kiểm soát khi nhận yêu cầu hủy.
4. Viết một tác vụ chạy trên `ExecutorService`, giữ `Future` và thử `cancel(true)` từ một cơ chế điều khiển riêng.
5. Bắt `InterruptedException` ở một tầng và xác nhận cờ interrupt được khôi phục nếu tầng đó không truyền exception lên.
6. Thử Ctrl+D tại prompt trên terminal Unix hoặc terminal hỗ trợ EOF; so sánh với Ctrl+C.
7. Dùng `quit` và `exit`, sau đó kiểm tra callback `@PreDestroy` của một bean được gọi.
8. Chạy cùng ứng dụng ở non-interactive mode và giải thích vì sao không có prompt để nhập `quit`.
9. Thử trong terminal Windows và POSIX nếu có; ghi lại sự khác nhau của Ctrl+C, Ctrl+D và Ctrl+Z.
10. Nếu tác vụ ghi file, thêm file tạm và chỉ đổi tên sang file đích khi hoàn tất để tránh để lại output dở dang.

Khi hoàn thành, hãy mô tả cơ chế nào hủy dòng nhập, cơ chế nào yêu cầu dừng command và cơ chế nào đóng cả ứng dụng.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): interactive và non-interactive mode, shell runner và phạm vi sử dụng của command `exit`.
- [Spring Shell 3.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): built-in command `quit` và `exit`.
- [Spring Shell 3.3 – Quit API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/Quit.html): command thoát shell.
- [JLine 3 – Line Reader](https://jline.org/versions/3.x/docs/line-reader/): `UserInterruptException`, `EndOfFileException` và vòng lặp đọc input.
- [JLine 3 – Terminal](https://jline.org/versions/3.x/docs/terminal/): terminal signal, handler và control character.
- [JLine 3 – Terminal Attributes](https://jline.org/versions/3.x/docs/advanced/terminal-attributes/): `VINTR`, `VEOF`, `VSUSP` và các ký tự điều khiển.
- [JLine 3 – Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/): khác biệt xử lý Ctrl+C trên Windows và vấn đề terminal.
- [Java SE 21 – Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): interrupt flag, `isInterrupted()` và `InterruptedException`.
- [Java SE 21 – Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): hủy tác vụ bằng `cancel(boolean)`.
