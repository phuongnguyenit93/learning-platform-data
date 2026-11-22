# Giới hạn quyền và khác biệt hệ điều hành khi quản lý tiến trình Java

Java cung cấp `ProcessBuilder`, `Process` và `ProcessHandle` để tạo, theo dõi và yêu cầu kết thúc tiến trình. Các API này tạo một lớp giao tiếp tương đối thống nhất, nhưng chúng không xóa bỏ quyền truy cập và quy tắc thực thi của hệ điều hành. Một chương trình Java chỉ có thể khởi chạy executable mà tài khoản đang chạy JVM được phép thực thi; khả năng xem thông tin hoặc điều khiển một tiến trình khác cũng phụ thuộc vào quyền của hệ điều hành.

Khi viết mã chạy trên nhiều hệ điều hành, cần tách phần logic Java khỏi giả định về shell, đường dẫn, biến môi trường, quyền file, tín hiệu và cách tiến trình kết thúc. Không có API Java chuẩn nào tự nâng quyền lên administrator/root hoặc làm cho mọi hành vi quản lý tiến trình giống hệt nhau giữa Windows và các hệ POSIX.

## 1. Ranh giới quyền giữa JVM và hệ điều hành

`ProcessBuilder.start()` yêu cầu hệ điều hành tạo tiến trình mới. Tiến trình con thường chạy dưới cùng danh tính và security context với tiến trình Java cha. Các quyền đọc file, ghi file, truy cập mạng, chạy chương trình hoặc truy cập tài nguyên khác được hệ điều hành đánh giá theo tài khoản và chính sách áp dụng.

Java không tự cấp quyền cao hơn cho tiến trình con. Nếu ứng dụng cần chạy một tác vụ có quyền quản trị, hãy thiết kế một thành phần được triển khai và cấp quyền riêng theo chính sách của hệ điều hành, giới hạn chức năng của thành phần đó và xác thực dữ liệu đầu vào. Không nên chạy toàn bộ ứng dụng Java với quyền cao nhất chỉ để một tác vụ nhỏ có thể thực hiện.

Khi khởi chạy executable, `ProcessBuilder.start()` có thể thất bại bằng `IOException` nếu file không tồn tại, không thể thực thi, định dạng không được hỗ trợ hoặc hệ điều hành từ chối tạo tiến trình. Nội dung thông báo lỗi và mã lỗi nền tảng có thể khác nhau giữa Windows, Linux và macOS. Vì vậy, không nên phân tích chuỗi thông báo lỗi theo một định dạng cố định để quyết định logic nghiệp vụ.

## 2. Quyền thực thi trên POSIX và Windows

Trên Linux và macOS, quyền thực thi thường chịu ảnh hưởng của:

- Bit quyền `execute` trên file và quyền đi qua (`search`/`execute`) trên các thư mục cha của đường dẫn.
- Quyền sở hữu, nhóm, ACL và danh tính người dùng/nhóm hiệu lực của JVM.
- Chính sách hệ thống như mount option `noexec`, sandbox hoặc cơ chế kiểm soát truy cập bổ sung.
- Với script, interpreter được chỉ định trong shebang và quyền thực thi của chính interpreter.

Trên Windows, khả năng tạo tiến trình phụ thuộc vào access token của tài khoản, ACL trên file/thư mục và các chính sách kiểm soát ứng dụng của máy. Đường dẫn executable, định dạng chương trình và cách hệ thống phân giải tên file cũng có quy tắc riêng. Một script `.bat` hoặc `.cmd` thường cần được chạy thông qua command interpreter phù hợp.

Do đó, một lệnh chạy được trên máy phát triển có thể thất bại trong service, container hoặc tài khoản triển khai vì danh tính chạy khác, thư mục làm việc khác, quyền file khác hoặc chính sách máy chủ khác. Hãy kiểm tra quyền tại đúng môi trường chạy và ghi nhận lỗi gốc từ `IOException`.

## 3. Không giả định có cùng shell hoặc cú pháp lệnh

`ProcessBuilder` không tự chạy lệnh thông qua shell. Mỗi phần tử trong danh sách command là một token riêng: phần tử đầu là chương trình cần chạy, các phần tử tiếp theo là đối số của nó.

```java
List<String> command = new ArrayList<>();
command.add("git");
command.add("status");
command.add("--short");
Process process = new ProcessBuilder(command).start();
```

Cách truyền đối số theo từng phần tử giúp giữ nguyên một đối số có dấu cách mà không phải tự ghép dấu nháy. `ProcessBuilder` không diễn giải `|`, `>`, `&&`, `*`, `$VAR` hoặc cú pháp shell như một shell thông thường.

Các lệnh như `dir`, `copy`, `ls`, `grep` hoặc `cat` không phải lúc nào cũng là executable độc lập. Một số là lệnh built-in của shell; tên lệnh, tùy chọn và cú pháp có thể khác nhau theo hệ điều hành.

Nếu thật sự cần shell, phải chỉ định interpreter một cách tường minh. Ví dụ trên POSIX có thể gọi `/bin/sh` với `-c`; trên Windows thường dùng `cmd.exe` với `/c`. Hai môi trường có cú pháp quoting, biến môi trường, chuyển hướng và escape khác nhau. Tránh tạo chuỗi shell bằng cách nối dữ liệu người dùng; hãy truyền đối số riêng và xác thực giá trị trước khi thực thi để giảm nguy cơ command injection.

Đối với executable quan trọng, nên cấu hình hoặc xác định đường dẫn tuyệt đối thay vì phụ thuộc hoàn toàn vào `PATH`. Cách tìm executable theo `PATH`, phần mở rộng được xét và cách xử lý script có khác biệt nền tảng. Khi dùng `ProcessBuilder`, đừng tự thêm dấu nháy vào từng token chỉ vì đường dẫn có dấu cách; token là một đối số, còn việc biểu diễn lệnh ở tầng hệ điều hành do runtime đảm nhiệm.

## 4. Đường dẫn, thư mục làm việc và biến môi trường

Đường dẫn file có thể khác nhau giữa các hệ điều hành: ký tự phân cách, ổ đĩa, UNC path, symbolic link và quy tắc phân biệt chữ hoa/chữ thường không đồng nhất. Dùng `Path`, `Paths.get()` và `Path.resolve()` để tạo đường dẫn theo filesystem đang chạy, thay vì nối chuỗi với `/` hoặc `\`.

`ProcessBuilder.directory(File)` đặt thư mục làm việc của tiến trình con. Nếu không đặt, tiến trình con thường kế thừa thư mục làm việc hiện tại của JVM. Đường dẫn tương đối mà chương trình con sử dụng được phân giải theo thư mục làm việc của chính tiến trình con; nó không nhất thiết là thư mục chứa file JAR.

Môi trường của tiến trình con mặc định được khởi tạo từ môi trường của tiến trình Java. Có thể đọc hoặc sửa bản sao môi trường qua `ProcessBuilder.environment()` trước khi gọi `start()`. Tên biến môi trường trên Windows thường không phân biệt hoa/thường, trong khi trên POSIX chúng phân biệt hoa/thường. Không nên giả định `PATH`, `Path` hoặc các biến cấu hình khác luôn tương đương trên mọi nền tảng.

Chỉ truyền những biến môi trường mà tiến trình con cần. Tránh đưa token, mật khẩu hoặc khóa bí mật vào command line hay môi trường nếu có cơ chế truyền an toàn hơn; thông tin command line và environment có thể bị lộ qua công cụ giám sát hoặc quyền xem tiến trình của hệ thống.

## 5. Giới hạn khi quan sát tiến trình bằng `ProcessHandle`

`ProcessHandle` được bổ sung trong Java 9 để đại diện cho một tiến trình đang chạy. Có thể lấy handle của tiến trình hiện tại, tra cứu theo PID hoặc duyệt các tiến trình con:

```java
ProcessHandle current = ProcessHandle.current();
long pid = current.pid();

ProcessHandle.of(pid).ifPresent(handle ->
        System.out.println("Process is alive: " + handle.isAlive())
);
```

`ProcessHandle.of(pid)` trả về `Optional<ProcessHandle>`; nếu PID không còn tương ứng với một tiến trình đang tồn tại tại thời điểm tra cứu, kết quả có thể rỗng. Tiến trình cũng có thể kết thúc ngay sau khi tra cứu, vì vậy phải kiểm tra trạng thái và xử lý race condition thay vì coi PID là định danh tồn tại vĩnh viễn. Hệ điều hành có thể tái sử dụng PID sau khi tiến trình kết thúc.

`ProcessHandle.Info` cung cấp một số metadata như command, command line, arguments, thời điểm bắt đầu và thời lượng CPU. Các trường này được trả về dưới dạng `Optional` vì thông tin có thể không được hệ điều hành cung cấp hoặc không thể truy cập trong ngữ cảnh hiện tại. Không được giả định `commandLine()` hay `arguments()` luôn có dữ liệu.

Khả năng liệt kê, xem chi tiết hoặc điều khiển tiến trình khác còn phụ thuộc quyền của tài khoản và chính sách hệ điều hành. Một chương trình không thể dùng `ProcessHandle` để vượt qua ACL hoặc đọc mọi thông tin riêng tư của tiến trình khác. Nếu thông tin không có, hãy thiết kế luồng xử lý chấp nhận trạng thái thiếu thay vì suy ra rằng tiến trình không tồn tại.

Thông tin command line có thể chứa đường dẫn, tên tài khoản hoặc tham số nhạy cảm. Tránh ghi toàn bộ `ProcessHandle.Info` vào log công khai hoặc trả dữ liệu đó cho người dùng không có quyền.

## 6. Khác biệt khi yêu cầu tiến trình kết thúc

`Process.destroy()` và `ProcessHandle.destroy()` gửi yêu cầu kết thúc tiến trình theo khả năng của nền tảng. Cách hệ điều hành diễn giải yêu cầu kết thúc bình thường không giống nhau ở mọi nơi. `Process.supportsNormalTermination()` cho biết implementation của `Process` có hỗ trợ kiểu kết thúc bình thường hay không.

`destroyForcibly()` yêu cầu kết thúc cưỡng bức. Đây vẫn là một yêu cầu ở mức hệ điều hành; tiến trình có thể chưa biến mất ngay khi phương thức trả về. Nếu cần xác nhận đã kết thúc, hãy chờ bằng `waitFor()` hoặc theo dõi `isAlive()`/`onExit()` với timeout và chính sách xử lý phù hợp.

Java không cung cấp một API tín hiệu POSIX thống nhất như `SIGTERM`/`SIGKILL` có cùng ý nghĩa trên Windows. Không nên dựa vào tín hiệu hay tên lệnh hệ điều hành nếu mục tiêu là ứng dụng đa nền tảng. Với chương trình con do mình kiểm soát, cách đáng tin cậy hơn để yêu cầu dừng mềm là thiết kế giao thức riêng, chẳng hạn gửi lệnh qua stdin, socket hoặc endpoint quản trị; sau thời hạn chờ mới cân nhắc kết thúc cưỡng bức.

Không giả định `destroy()` luôn cho chương trình con cơ hội lưu dữ liệu hoặc giải phóng tài nguyên. Hành vi graceful shutdown phụ thuộc vào chính chương trình con và nền tảng. Nếu tiến trình con tạo thêm tiến trình con khác, việc kết thúc tiến trình cha cũng không đảm bảo toàn bộ cây tiến trình tự kết thúc theo cùng một cách.

## 7. Theo dõi tiến trình con và cây tiến trình

`ProcessHandle.children()` và `ProcessHandle.descendants()` hỗ trợ duyệt tiến trình con trực tiếp và các hậu duệ. Kết quả duyệt là ảnh chụp tại thời điểm truy vấn, không phải khóa đồng bộ cho toàn bộ cây tiến trình. Trong lúc duyệt, tiến trình có thể kết thúc hoặc tạo thêm tiến trình mới.

Vì vậy, không nên xem việc duyệt rồi gọi `destroyForcibly()` trên từng handle là một thao tác nguyên tử. Nếu cần quản lý vòng đời cả nhóm tiến trình, hãy lưu handle của các tiến trình do ứng dụng tự khởi chạy, thiết kế quy trình shutdown có thứ tự và xử lý các tiến trình đã kết thúc hoặc không còn quyền điều khiển.

## 8. Ví dụ hoàn chỉnh: khởi chạy tiến trình con theo cách ít phụ thuộc nền tảng

Ví dụ sau dùng `java.home` để tìm executable Java hiện tại, tạo danh sách đối số riêng biệt và khởi chạy lại chính class đang chạy. Chương trình không gọi shell. Đường dẫn executable được chọn theo hệ điều hành, còn các phần tử command vẫn được truyền tách biệt.

Tạo tệp `ProcessPermissionsDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ProcessPermissionsDemo {
    private static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        String executable = windows ? "java.exe" : "java";
        return Paths.get(System.getProperty("java.home"), "bin", executable).toString();
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        if (args.length == 2 && "child".equals(args[0])) {
            System.out.println("child argument: " + args[1]);
            return;
        }

        System.out.println("Current process PID is positive: "
                + (ProcessHandle.current().pid() > 0));

        List<String> command = new ArrayList<>();
        command.add(javaExecutable());
        command.add("-cp");
        command.add(System.getProperty("java.class.path"));
        command.add(ProcessPermissionsDemo.class.getName());
        command.add("child");
        command.add("argument with spaces");

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();
        byte[] output = process.getInputStream().readAllBytes();
        int exitCode = process.waitFor();
        String childOutput = new String(output, StandardCharsets.UTF_8);

        System.out.println("Child exit code: " + exitCode);
        System.out.println("Argument preserved: "
                + childOutput.contains("child argument: argument with spaces"));
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all ProcessPermissionsDemo.java
java ProcessPermissionsDemo
```

Kết quả stdout:

```text
Current process PID is positive: true
Child exit code: 0
Argument preserved: true
```

Ví dụ chứng minh đối số có dấu cách được giữ thành một đối số duy nhất và chương trình con được chạy trực tiếp. Nó vẫn cần quyền thực thi đối với Java executable, quyền đọc classpath và quyền tạo tiến trình trong môi trường triển khai. Nếu một trong các quyền này bị từ chối, `start()` có thể ném `IOException`; việc dùng `ProcessBuilder` không bỏ qua hạn chế của hệ điều hành.

## 9. Checklist triển khai đa nền tảng

1. Chạy ứng dụng bằng tài khoản có quyền tối thiểu cần thiết; không mặc định dùng administrator/root.
2. Kiểm tra executable tồn tại, có quyền thực thi và đúng định dạng trong môi trường triển khai.
3. Dùng `ProcessBuilder` với từng đối số riêng; chỉ gọi shell khi thật sự cần và xử lý đầu vào như dữ liệu không tin cậy.
4. Dùng `Path`/`Paths` để tạo đường dẫn; đặt working directory rõ ràng nếu chương trình con cần đường dẫn tương đối.
5. Kiểm soát môi trường kế thừa và tránh truyền bí mật qua command line hoặc log.
6. Xử lý `IOException`, mã thoát khác 0, stdout và stderr; không giả định thông báo lỗi giống nhau giữa các hệ điều hành.
7. Chấp nhận `Optional` rỗng từ `ProcessHandle.Info`; metadata có thể bị giới hạn bởi hệ điều hành hoặc quyền truy cập.
8. Xem `destroy()` là yêu cầu có tính nền tảng; dùng giao thức shutdown của ứng dụng nếu cần kết thúc mềm và xác nhận trạng thái bằng `waitFor()`/`onExit()`.
9. Không giả định kết thúc tiến trình cha sẽ tự động dọn toàn bộ hậu duệ; quản lý các process do ứng dụng tạo ra.

Quản lý tiến trình Java chỉ thống nhất ở mức API. Quyền thực thi, khả năng quan sát, đường dẫn, môi trường và cách kết thúc vẫn do hệ điều hành quyết định. Thiết kế tốt là xác định rõ executable và đối số, chạy với quyền tối thiểu, xử lý dữ liệu metadata có thể thiếu và xây dựng quy trình dừng tiến trình phù hợp với nền tảng.