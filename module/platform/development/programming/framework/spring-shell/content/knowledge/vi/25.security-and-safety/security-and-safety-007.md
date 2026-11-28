# Không ghép dữ liệu người dùng thành lệnh shell hệ điều hành

Một command Spring Shell có thể nhận tên file, từ khóa tìm kiếm hoặc tên repository do người dùng nhập. Nếu command dùng dữ liệu đó để gọi chương trình bên ngoài, việc nối chuỗi trực tiếp thành lệnh shell có thể cho phép người dùng thay đổi câu lệnh mà ứng dụng định chạy. Đây là dạng lỗ hổng **OS command injection**.

Ví dụ, ứng dụng định chạy **grep** để tìm một từ khóa nhưng lại ghép từ khóa vào chuỗi **sh -c**. Nếu giá trị chứa dấu phân cách lệnh hoặc cú pháp shell, shell có thể thực thi thêm một lệnh khác. Kết quả có thể là đọc file ngoài phạm vi, sửa hoặc xóa dữ liệu, tải chương trình khác hay chạy thao tác dưới quyền của tài khoản đang chạy ứng dụng.

Nguyên tắc quan trọng là **không biến dữ liệu người dùng thành cú pháp lệnh**. Nếu có thể, dùng API Java để xử lý file hoặc dữ liệu. Khi thật sự cần chạy chương trình ngoài, dùng **ProcessBuilder** với từng đối số tách biệt, giới hạn chương trình và tham số được phép, kiểm tra đường dẫn, đặt timeout và quản lý vòng đời process.

## 1. Phân biệt command Spring Shell và lệnh shell hệ điều hành

Spring Shell cung cấp parser và command registry để người dùng gọi các lệnh của ứng dụng, ví dụ:

~~~text
repo status --path=./projects/demo
log search --text="connection failed"
~~~

Các chuỗi trên là cú pháp của ứng dụng Spring Shell. Bản thân việc người dùng nhập dấu chấm phẩy, dấu pipe hoặc dấu nháy trong một argument không có nghĩa Spring Shell tự chạy chúng như cú pháp của Bash hoặc PowerShell.

Rủi ro xuất hiện khi code của command chuyển input sang một chương trình hệ điều hành, chẳng hạn:

- **sh -c** hoặc **bash -c** trên Unix-like.
- **cmd.exe /c** trên Windows.
- **powershell -Command** hoặc **pwsh -Command**.
- Một script hoặc executable khác có thể diễn giải đối số thành lệnh, biểu thức hoặc tùy chọn.

Ví dụ, command Spring Shell gọi một service, service lại chạy **bash -c** với chuỗi được ghép từ input. Lúc đó input đã đi qua hai lớp parser: parser của Spring Shell và parser của shell hệ điều hành. Cần bảo vệ tại ranh giới gọi process, nơi dữ liệu được chuyển thành đối số thực tế.

## 2. Vì sao nối chuỗi thành lệnh rất nguy hiểm?

Đoạn code sau có lỗ hổng:

~~~java
new ProcessBuilder(
        "sh",
        "-c",
        "grep " + searchText + " " + fileName
).start();
~~~

Ứng dụng mong đợi **searchText** chỉ là từ khóa và **fileName** chỉ là tên file. Nhưng dữ liệu nhập có thể chứa dấu nháy, dấu chấm phẩy, pipe, command substitution hoặc cú pháp khác của shell. Khi chuỗi được chuyển cho shell phân tích, ký tự trong dữ liệu có thể trở thành cú pháp điều khiển.

Một ví dụ payload vô hại để minh họa việc thay đổi luồng thực thi là:

~~~text
error; echo injected
~~~

Nếu được ghép trực tiếp vào vị trí lệnh trong chuỗi **sh -c**, shell có thể hiểu **echo injected** là một lệnh thứ hai. Trong ứng dụng thật, lệnh thứ hai có thể thực hiện hành động vượt ngoài chức năng tìm kiếm.

Các dạng cú pháp thường bị khai thác gồm:

| Ký tự hoặc cú pháp | Ý nghĩa thường gặp trong shell |
|---|---|
| **;** | Kết thúc một lệnh và bắt đầu lệnh tiếp theo |
| **&&** và **||** | Chạy lệnh tiếp theo theo kết quả lệnh trước |
| **\|** | Nối output của tiến trình trước vào input của tiến trình sau |
| **$()** và backtick | Thực thi command substitution |
| **>** và **>>** | Chuyển hướng output vào file |
| **&** | Chạy tiến trình nền trong nhiều shell |
| **\***, **?**, **[]** | Mở rộng pattern tên file trong shell |
| Dấu nháy | Thay đổi cách shell phân tích các token |

Không nên cố loại bỏ một vài ký tự nguy hiểm rồi tiếp tục ghép chuỗi. Shell có nhiều quy tắc quoting, escaping, expansion và khác biệt giữa các nền tảng. Một bộ lọc thủ công rất dễ bỏ sót cú pháp hoặc xử lý sai dữ liệu hợp lệ.

## 3. Ưu tiên API Java thay cho chương trình ngoài

Nếu mục tiêu là đọc file, tìm chuỗi, đổi tên file, xóa file hoặc tạo thư mục, Java đã có API tương ứng. Không cần gọi **grep**, **find**, **mkdir**, **copy** hoặc **del** chỉ để thực hiện thao tác file thông thường.

Ví dụ tìm một chuỗi trong file:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class LogSearchService {

    public List<String> search(Path file, String text) throws IOException {
        try (Stream<String> lines =
                     Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .filter(line -> line.contains(text))
                    .toList();
        }
    }
}
~~~

**Files.lines()** trả về một stream gắn với file. Khối **try-with-resources** bảo đảm stream được đóng kể cả khi việc xử lý phát sinh exception. Cách này không phụ thuộc shell, không cần escape chuỗi lệnh và dễ kiểm thử hơn.

Một số API Java thay thế thao tác shell:

| Nhu cầu | API Java nên cân nhắc |
|---|---|
| Đọc hoặc ghi file | **Files.readString()**, **Files.writeString()** |
| Duyệt thư mục | **Files.list()**, **Files.walk()** |
| Tạo thư mục | **Files.createDirectories()** |
| Sao chép file | **Files.copy()** |
| Di chuyển hoặc đổi tên | **Files.move()** |
| Xóa file | **Files.delete()** hoặc **Files.deleteIfExists()** |
| Tìm chuỗi trong văn bản | **String.contains()**, regex Java hoặc stream dòng |
| Nén và giải nén ZIP | **ZipInputStream**, **ZipOutputStream** |
| Tải nội dung HTTP | **HttpClient** |
| Đọc biến môi trường | **System.getenv()** |

API Java không tự động làm cho mọi thao tác an toàn. Vẫn cần kiểm tra đường dẫn, giới hạn phạm vi thư mục, xác thực quyền và tránh path traversal. Nhưng nó loại bỏ một lớp diễn giải lệnh shell không cần thiết.

## 4. Dùng ProcessBuilder với danh sách đối số

Khi cần gọi chương trình ngoài, hãy truyền executable và từng đối số riêng:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        "/usr/bin/git",
        "-C",
        repository.toString(),
        "status",
        "--short"
);
~~~

Mỗi phần tử trong danh sách là một đối số riêng. **ProcessBuilder** khởi chạy chương trình trực tiếp; nó không tự gọi Bash, PowerShell hay **cmd.exe** để phân tích chuỗi. Dấu cách, dấu chấm phẩy hoặc dấu pipe nằm trong một phần tử sẽ được truyền như dữ liệu của đối số đó.

ProcessBuilder cũng không tự mở rộng wildcard như **\***, biến môi trường như **$HOME**, pipe hoặc redirect như **>**. Nếu cần nối hai process, Java có **ProcessBuilder.startPipeline()**; nếu cần đọc file hoặc chuyển hướng output, hãy dùng API Java hay cấu hình redirect tường minh.

Không thêm dấu nháy shell quanh từng phần tử. Ví dụ, đối số có nội dung **"my file.txt"** đã là một đối số duy nhất. **ProcessBuilder** không cần shell quoting; nếu thêm dấu nháy vào chuỗi, các dấu đó sẽ được truyền như dữ liệu.

Ví dụ tìm file bằng **grep** với đối số tách biệt:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        "/usr/bin/grep",
        "--",
        searchText,
        file.toString()
);
~~~

**--** là quy ước kết thúc danh sách option được nhiều chương trình Unix hỗ trợ. Nó giúp chương trình hiểu đối số tiếp theo là toán hạng ngay cả khi chuỗi bắt đầu bằng dấu **-**. Tuy nhiên, không phải executable nào cũng hỗ trợ **--**; cần đọc tài liệu của chương trình đích và kiểm tra riêng từng đối số.

**ProcessBuilder loại bỏ việc shell phân tích dữ liệu, nhưng không loại bỏ mọi dạng argument injection.** Chương trình con vẫn có parser riêng và có thể diễn giải một đối số thành option, tên subcommand, biểu thức hoặc đường dẫn đặc biệt.

## 5. Phân biệt shell injection và argument injection

Hai vấn đề này có liên quan nhưng không giống nhau:

| Loại | Cách xảy ra | Biện pháp chính |
|---|---|---|
| Shell injection | Dữ liệu được ghép vào chuỗi cho shell như **sh -c** | Không gọi shell bằng chuỗi có dữ liệu; dùng ProcessBuilder list |
| Argument injection | Chương trình đích diễn giải dữ liệu như option hoặc lệnh riêng | Allowlist, kiểm tra kiểu/giá trị, delimiter **--** nếu được hỗ trợ |
| Path traversal | Đường dẫn thoát khỏi thư mục được phép qua **..** hoặc symlink | Chuẩn hóa, resolve real path và kiểm tra root |
| Executable hijacking | Tên chương trình bị phân giải qua PATH không đáng tin | Dùng đường dẫn executable đáng tin cậy và môi trường được kiểm soát |

Ví dụ, gọi **ProcessBuilder("grep", userInput, file)** không chạy shell. Nhưng nếu **userInput** là một option đặc biệt, **grep** có thể thay đổi hành vi. Hãy dùng **--** trước pattern nếu chương trình hỗ trợ, và chỉ cho phép những kiểu input mà nghiệp vụ cần.

Nếu người dùng được phép chọn một chế độ chạy, không truyền tên tùy ý vào command. Hãy ánh xạ lựa chọn từ một allowlist:

~~~java
import java.util.List;
import java.util.Map;

Map<String, List<String>> modes = Map.of(
        "short", List.of("--short"),
        "verbose", List.of("--verbose")
);

List<String> modeArguments = modes.get(mode);
if (modeArguments == null) {
    throw new IllegalArgumentException("Chế độ không được hỗ trợ.");
}
~~~

Sau đó thêm các đối số được ánh xạ vào **ProcessBuilder**. Người dùng chỉ chọn một giá trị nghiệp vụ đã biết; họ không thể cung cấp một option bất kỳ cho chương trình.

## 6. Không gọi shell bằng chuỗi có input

Các mẫu sau cần tránh:

~~~java
// Không an toàn: dữ liệu được ghép vào lệnh shell
new ProcessBuilder("sh", "-c", "grep " + query + " " + file).start();

// Không an toàn: PowerShell phân tích chuỗi command
new ProcessBuilder("powershell", "-Command",
        "Get-Content " + file + " | Select-String " + query).start();

// Không an toàn: cmd.exe phân tích chuỗi command
new ProcessBuilder("cmd.exe", "/c", "type " + file).start();
~~~

Không khắc phục bằng cách thêm dấu nháy quanh input hoặc thay một số ký tự bằng backslash. Cách escape phụ thuộc shell, vị trí dữ liệu và ngữ cảnh cú pháp. Chuỗi an toàn trong một ngữ cảnh có thể không an toàn ở ngữ cảnh khác.

**Runtime.exec(String)** cũng không phải giải pháp tốt. Overload nhận một chuỗi không tự động chạy shell trên mọi nền tảng; nó tách chuỗi thành token theo quy tắc riêng của Java, dễ làm sai ranh giới đối số và vẫn có thể gây argument injection. Hãy dùng **ProcessBuilder** với danh sách đối số để biểu diễn ý định rõ ràng.

### 6.1. Nếu thật sự cần shell script

Tốt nhất hãy thay shell bằng API Java hoặc gọi executable trực tiếp. Nếu một môi trường bắt buộc phải chạy script, script phải là nội dung cố định do ứng dụng kiểm soát; dữ liệu người dùng phải được truyền thành positional argument riêng và được trích dẫn đúng theo shell đó.

Ví dụ Bash dưới đây chỉ minh họa nguyên tắc truyền tham số, không phải lựa chọn mặc định cho ứng dụng đa nền tảng:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        "/bin/bash",
        "-c",
        "exec grep -- \"$1\" \"$2\"",
        "grep-wrapper",
        searchText,
        file.toString()
);
~~~

Chuỗi script là hằng số. Bash nhận **searchText** và đường dẫn dưới dạng **$1**, **$2**; dấu nháy kép giữ mỗi biến thành một đối số khi gọi **grep**. **--** ngăn pattern hoặc tên file bắt đầu bằng dấu **-** bị hiểu nhầm là option của **grep**.

Mẫu này vẫn phụ thuộc Bash và cú pháp của **grep**; cần kiểm thử trên đúng nền tảng. Không tạo chuỗi script từ input, không dùng **eval**, không bỏ dấu nháy quanh biến và không giả định cú pháp Bash có thể chạy nguyên trạng trong PowerShell hoặc **cmd.exe**.

## 7. Kiểm tra đường dẫn trước khi truyền cho chương trình ngoài

Đường dẫn do người dùng nhập có thể chứa **..**, đường dẫn tuyệt đối hoặc symlink dẫn ra ngoài thư mục được phép. Dù không có shell injection, chương trình vẫn có thể đọc hoặc sửa file ngoài phạm vi.

Ví dụ kiểm tra repository nằm trong một thư mục gốc được cho phép:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class RepositoryPathPolicy {

    private final Path allowedRoot;

    public RepositoryPathPolicy(Path allowedRoot) throws IOException {
        this.allowedRoot = allowedRoot.toRealPath();
    }

    public Path resolveExistingRepository(String userInput) throws IOException {
        Path requested = Path.of(userInput);
        Path candidate = requested.isAbsolute()
                ? requested
                : allowedRoot.resolve(requested);
        Path realPath = candidate.toRealPath();

        if (!realPath.startsWith(allowedRoot)) {
            throw new SecurityException("Đường dẫn nằm ngoài vùng được phép.");
        }

        if (!Files.isDirectory(realPath)) {
            throw new IllegalArgumentException("Đường dẫn không phải thư mục.");
        }

        return realPath;
    }
}
~~~

**toRealPath()** giải quyết đường dẫn thành đường dẫn thực và xử lý symlink cho đối tượng tồn tại. So sánh với root đã chuẩn hóa giúp phát hiện đường dẫn thoát khỏi vùng cho phép. Không chỉ kiểm tra chuỗi có bắt đầu bằng tên thư mục hay không; phép so sánh chuỗi có thể nhầm **projects-safe** với **projects**.

Nếu thao tác tạo file mới, file đích có thể chưa tồn tại nên không gọi **toRealPath()** trực tiếp trên file đó. Hãy chuẩn hóa thư mục cha, kiểm tra thư mục cha thực nằm trong root được phép, rồi tạo file trong thư mục đó. Cần cân nhắc symlink và race condition nếu thư mục có thể bị tiến trình khác thay đổi giữa lúc kiểm tra và sử dụng.

## 8. Chỉ cho phép executable và hành động đã định nghĩa

Không để người dùng tự nhập executable hoặc subcommand tùy ý:

~~~java
// Không nên: người dùng kiểm soát executable
new ProcessBuilder(executableFromUser, argument).start();
~~~

Thay vào đó, cấu hình executable đáng tin cậy trong ứng dụng hoặc môi trường triển khai, rồi chọn hành động từ allowlist:

~~~java
import java.util.List;

enum RepositoryAction {
    STATUS,
    DIFF
}

List<String> argumentsFor(RepositoryAction action) {
    return switch (action) {
        case STATUS -> List.of("status", "--short");
        case DIFF -> List.of("diff", "--stat");
    };
}
~~~

Không cho phép user truyền raw flags như **--upload**, **--delete**, **--config** hoặc đường dẫn output nếu nghiệp vụ không yêu cầu. Kiểm tra option của chương trình con theo allowlist có thể đọc và hiểu được; không cố xây một bộ lọc tổng quát cho mọi executable.

Chương trình ngoài chạy với quyền của tiến trình Spring Shell. Hãy chạy ứng dụng bằng tài khoản có quyền tối thiểu cần thiết; không chạy shell CLI với quyền administrator/root chỉ để tránh lỗi permission.

## 9. Quản lý working directory và environment

**ProcessBuilder** cho phép cấu hình thư mục làm việc và biến môi trường của tiến trình con:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        configuredGitExecutable.toString(),
        "-C",
        repository.toString(),
        "status",
        "--short"
);

processBuilder.directory(repository.toFile());
processBuilder.environment().put("GIT_TERMINAL_PROMPT", "0");
~~~

Các quyết định này ảnh hưởng đến chương trình con:

- **Executable:** dùng đường dẫn đáng tin cậy, tránh phân giải một tên chương trình từ PATH không kiểm soát.
- **Working directory:** đặt thư mục cụ thể; không dựa vào thư mục hiện tại tình cờ của tiến trình cha.
- **Environment:** không chuyển secret hoặc biến điều khiển không cần thiết; tránh cho input người dùng ghi đè **PATH**, **HOME**, **JAVA_TOOL_OPTIONS** hoặc biến cấu hình của chương trình.
- **Locale:** nếu cần output ổn định cho parser, cấu hình locale phù hợp theo nền tảng thay vì parse văn bản phụ thuộc ngôn ngữ.

**ProcessBuilder.environment()** bắt đầu từ môi trường được kế thừa của tiến trình cha. Chỉ thay đổi biến cần thiết; nếu xóa toàn bộ environment, một số chương trình trên Windows có thể không khởi chạy được vì thiếu biến hệ thống. Chính sách environment cần được kiểm thử trên nền tảng mục tiêu.

## 10. Quản lý timeout, exit code và vòng đời process

Không nên gọi **waitFor()** vô thời hạn cho một chương trình có thể bị treo. Đặt timeout và xử lý cả trường hợp bị ngắt:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class GitStatusRunner {

    public void runStatus(
            Path gitExecutable,
            Path repository) throws IOException {

        ProcessBuilder builder = new ProcessBuilder(
                gitExecutable.toString(),
                "-C",
                repository.toString(),
                "status",
                "--short"
        );
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.DISCARD);

        Process process = builder.start();
        try {
            boolean finished = process.waitFor(15, TimeUnit.SECONDS);
            if (!finished) {
                process.destroy();
                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor();
                }
                throw new IllegalStateException("Lệnh git vượt quá thời gian cho phép.");
            }

            if (process.exitValue() != 0) {
                throw new IllegalStateException(
                        "Lệnh git thất bại với exit code " + process.exitValue()
                );
            }
        }
        catch (InterruptedException ex) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Đã ngắt khi chờ lệnh git.", ex);
        }
    }
}
~~~

Ví dụ này bỏ output vì command chỉ cần biết tiến trình thành công hay thất bại. Nếu cần hiển thị output, hãy đọc stdout và stderr một cách có kiểm soát. Khi dùng pipe, phải tiêu thụ stream trong lúc process chạy; nếu chờ process kết thúc rồi mới đọc, buffer đầy có thể làm tiến trình con bị block và gây deadlock.

Không đọc toàn bộ output không giới hạn vào bộ nhớ. Giới hạn số byte hoặc số dòng, lọc thông tin nhạy cảm và không hiển thị nguyên văn output nếu chương trình con có thể in control character hoặc dữ liệu không tin cậy.

**destroyForcibly()** tác động lên process được tạo. Nếu chương trình đó sinh process con, cần có chiến lược quản lý process tree hoặc cơ chế containment của hệ điều hành; không giả định hủy process cha luôn hủy mọi hậu duệ.

## 11. Tích hợp an toàn trong command Spring Shell

Command chỉ nên nhận dữ liệu, kiểm tra sơ bộ và gọi một service chuyên trách. Service xác thực đường dẫn, chọn executable cố định và xây dựng danh sách đối số.

Ví dụ command Spring Shell 4:

~~~java
import java.nio.file.Path;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class RepositoryCommands {

    private final RepositoryStatusService statusService;

    public RepositoryCommands(RepositoryStatusService statusService) {
        this.statusService = statusService;
    }

    @Command(
            name = {"repo", "status"},
            description = "Hiển thị trạng thái repository."
    )
    public String status(
            @Option(longName = "path", required = true) Path path) {
        return statusService.status(path);
    }
}
~~~

Service không ghép **path** vào một chuỗi shell. Nó kiểm tra root, gọi một executable đã cấu hình và truyền path thành một phần tử riêng trong danh sách đối số. Tách service như vậy giúp kiểm thử policy và process runner mà không cần khởi chạy toàn bộ shell.

Không đặt **@Transactional** quanh command chỉ để chạy process. Một tiến trình ngoài không tham gia transaction JDBC của Spring; rollback database không thể hoàn tác file hoặc side effect do executable tạo ra. Nếu một nghiệp vụ phối hợp database và process, cần thiết kế trạng thái, retry và bù trừ rõ ràng.

## 12. Kiểm soát output của chương trình ngoài

Output từ executable cũng là dữ liệu không tin cậy. Nó có thể chứa:

- Thông tin nhạy cảm như đường dẫn nội bộ, username hoặc token.
- ANSI escape sequence có thể đổi màu, di chuyển con trỏ hoặc làm terminal hiển thị nội dung giả.
- Chuỗi rất dài làm đầy bộ nhớ hoặc làm giao diện không sử dụng được.
- Văn bản phụ thuộc locale, phiên bản chương trình hoặc hệ điều hành.

Nếu command chỉ cần mã thoát, bỏ output hoặc chuyển hướng vào một nơi được kiểm soát. Nếu cần hiển thị, lọc thông tin nhạy cảm, giới hạn kích thước, loại bỏ control character không được phép và phân biệt stdout với stderr.

Không dùng output của chương trình ngoài để tạo lệnh shell tiếp theo. Nếu cần chạy bước tiếp theo, hãy dùng exit code và dữ liệu đã parse theo định dạng có cấu trúc, rồi ánh xạ sang một hành động allowlist.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Input có dấu **;** làm chạy thêm lệnh | Nối input vào **sh -c** hoặc **cmd /c** | Không ghép chuỗi shell; dùng ProcessBuilder list |
| Đối số có dấu cách bị tách | Dùng Runtime.exec(String) hoặc tự tokenize | Truyền mỗi đối số thành một phần tử |
| Pattern bắt đầu bằng **-** làm đổi hành vi | Argument injection vào chương trình con | Dùng **--** nếu được hỗ trợ và kiểm tra input |
| Đường dẫn đọc file ngoài root | Không chuẩn hóa path hoặc không xử lý symlink | Resolve real path và kiểm tra thư mục gốc |
| Chạy nhầm executable | Dựa vào PATH không đáng tin | Cấu hình executable path đáng tin cậy |
| Process treo vô thời hạn | Không có timeout | Dùng waitFor(timeout, unit) và hủy khi quá hạn |
| Process không kết thúc sau khi hủy cha | Process sinh child process | Quản lý process tree hoặc OS containment |
| Process bị deadlock khi ghi output | Không đọc pipe trong lúc process chạy | Drain stdout/stderr đồng thời hoặc redirect |
| Log lộ dữ liệu | In toàn bộ command, argument hoặc output | Redact secret và chỉ log metadata cần thiết |
| Windows chạy khác Linux | Cú pháp shell và parser đối số khác nhau | Tránh shell; kiểm thử executable trên từng nền tảng |
| Tin rằng ProcessBuilder loại bỏ mọi injection | Quên parser riêng của executable đích | Kết hợp argument list với allowlist và validation |

## 14. Kiểm thử bảo mật cho lệnh ngoài

Kiểm thử nên xác nhận cấu trúc đối số và giới hạn hành vi:

| Ca kiểm thử | Kết quả cần xác nhận |
|---|---|
| Input chứa dấu cách | Vẫn được truyền thành một đối số |
| Input chứa **;**, **\|**, **$()** hoặc dấu nháy | Không tạo lệnh thứ hai |
| Input bắt đầu bằng **-** | Không bị hiểu thành option ngoài dự kiến |
| Path chứa **..** | Bị từ chối nếu thoát khỏi root được phép |
| Path dùng symlink ra ngoài root | Bị từ chối |
| Executable không nằm trong allowlist | Không được khởi chạy |
| Option không được hỗ trợ | Bị từ chối trước khi tạo process |
| Process vượt timeout | Bị hủy và command trả lỗi rõ ràng |
| Thread bị interrupt | Process bị hủy và interrupt status được giữ |
| Exit code khác 0 | Command không báo thành công |
| Output rất lớn | Không làm đầy heap hoặc treo terminal |
| Output chứa ANSI/control character | Được lọc hoặc hiển thị an toàn |
| Chạy trên Windows và Linux | Đối số và đường dẫn hoạt động theo nền tảng mục tiêu |

Không cần gọi một shell thật trong unit test để chứng minh chuỗi đã an toàn. Có thể inject một process launcher abstraction và kiểm tra executable cùng danh sách đối số được tạo ra. Integration test chỉ nên chạy một executable giả lập hoặc một lệnh đọc an toàn, với thư mục tạm và dữ liệu test.

## 15. Checklist trước khi gọi chương trình hệ điều hành

- [ ] Đã xem xét API Java thay cho chương trình ngoài.
- [ ] Không nối dữ liệu người dùng vào chuỗi **sh -c**, **bash -c**, **cmd /c** hoặc **powershell -Command**.
- [ ] Dùng **ProcessBuilder** với executable và từng đối số tách biệt.
- [ ] Executable được cấu hình đáng tin cậy và nằm trong allowlist.
- [ ] Subcommand và option do ứng dụng kiểm soát.
- [ ] Dùng **--** khi chương trình hỗ trợ để kết thúc option parsing.
- [ ] Kiểm tra kiểu, độ dài, định dạng và giá trị đầu vào.
- [ ] Chuẩn hóa đường dẫn, kiểm tra real path và giới hạn root.
- [ ] Cấu hình working directory và environment có chủ đích.
- [ ] Đặt timeout, xử lý exit code và interruption.
- [ ] Quản lý stdout/stderr để tránh deadlock và giới hạn output.
- [ ] Không log secret hoặc dữ liệu nhạy cảm.
- [ ] Chạy ứng dụng với quyền hệ điều hành tối thiểu.
- [ ] Có test cho shell metacharacter, option injection, path traversal và timeout.
- [ ] Kiểm thử trên các hệ điều hành thực sự được hỗ trợ.

Spring Shell giúp tổ chức command cho người vận hành, nhưng khi command gọi chương trình ngoài, ranh giới bảo mật nằm ở cách ứng dụng tạo process. Hãy giữ dữ liệu ở dạng đối số, giới hạn executable và hành động được phép, xác minh đường dẫn, rồi quản lý timeout và tài nguyên process. Nếu Java có API làm được công việc đó, dùng API Java sẽ loại bỏ hẳn nhu cầu phân tích cú pháp shell.

## Tài liệu tham khảo

- [Java SE — ProcessBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html) — tạo process, truyền command và đối số riêng, cấu hình working directory, environment và redirect stream.
- [Java SE — Process](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html) — waitFor có timeout, exitValue, destroy, destroyForcibly và quản lý stream.
- [Java SE — ProcessHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html) — thông tin process và quan hệ process cha/con.
- [OWASP — OS Command Injection Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html) — tránh gọi OS command khi có API thay thế, parameterization và allowlist.
- [OWASP — OS Command Injection](https://owasp.org/www-community/attacks/OS_Command_Injection) — mô tả lỗ hổng khi dữ liệu không tin cậy thay đổi cú pháp lệnh hệ điều hành.
- [CWE-78 — Improper Neutralization of Special Elements used in an OS Command](https://cwe.mitre.org/data/definitions/78.html) — phân loại lỗi command injection.
- [CWE-88 — Improper Neutralization of Argument Delimiters in a Command](https://cwe.mitre.org/data/definitions/88.html) — lỗi dữ liệu làm thay đổi cách chương trình nhận diện đối số.
- [Spring Shell 4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — đăng ký command trong Spring-managed bean.
- [Spring Shell 4 API — Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) — khai báo option và chuyển dữ liệu đầu vào cho command.
