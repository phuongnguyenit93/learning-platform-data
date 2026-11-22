# ProcessHandle và mã tiến trình pid trong Java

## 1. ProcessHandle là gì?

ProcessHandle là API của Java 9 dùng để nhận diện, quan sát và gửi yêu cầu điều khiển tới một tiến trình của hệ điều hành. Mỗi ProcessHandle đại diện cho một tiến trình và cung cấp mã tiến trình (PID), trạng thái sống, thông tin tiến trình, quan hệ cha/con và các thao tác kết thúc tiến trình.

Các API chính nằm trong java.lang nên không cần import:

- ProcessHandle.current(): lấy handle của tiến trình Java hiện tại.
- ProcessHandle.of(pid): tìm handle theo PID và trả về Optional.
- ProcessHandle.allProcesses(): lấy Stream các tiến trình mà ứng dụng hiện tại nhìn thấy.
- handle.pid(): lấy PID kiểu long.
- handle.info(): lấy thông tin mô tả tiến trình.
- handle.parent(), children(), descendants(): truy cập quan hệ tiến trình.
- handle.onExit(): nhận thông báo bất đồng bộ khi tiến trình kết thúc.
- handle.destroy() và destroyForcibly(): gửi yêu cầu kết thúc tiến trình.

ProcessHandle hữu ích khi ứng dụng cần theo dõi tiến trình con, hiển thị PID, kiểm tra tiến trình còn chạy, giám sát cây tiến trình hoặc chờ tiến trình kết thúc mà không phải chặn luồng bằng vòng lặp kiểm tra liên tục.

## 2. PID là gì và lấy PID hiện tại

PID (process identifier) là mã số do hệ điều hành gán cho một tiến trình. Trong Java, PID có kiểu long, vì vậy không nên ép về int nếu không có lý do cụ thể.

Lấy PID của tiến trình JVM hiện tại:

~~~java
long pid = ProcessHandle.current().pid();

System.out.println("Current PID: " + pid);
~~~

current() luôn trả về ProcessHandle của tiến trình đang chạy đoạn mã. pid() trả về mã tiến trình tương ứng trên hệ điều hành.

PID hữu ích để:

- Hiển thị tiến trình trong log hoặc màn hình giám sát.
- Đối chiếu ứng dụng với công cụ quản lý tiến trình của hệ điều hành.
- Tìm một tiến trình đã biết PID.
- Ghi nhận tiến trình con được ứng dụng khởi chạy.

PID không phải mã định danh bền vững cho toàn bộ vòng đời hệ thống. Sau khi tiến trình kết thúc, hệ điều hành có thể tái sử dụng cùng PID cho tiến trình khác. Không nên lưu PID lâu dài rồi giả định rằng một lần tra cứu sau đó vẫn trỏ đến đúng tiến trình ban đầu.

## 3. Tìm ProcessHandle theo PID

ProcessHandle.of(long pid) trả về Optional<ProcessHandle>. Optional có giá trị khi tiến trình tương ứng tồn tại và có thể được nhìn thấy; nếu không tìm thấy hoặc không truy cập được, kết quả có thể rỗng.

~~~java
long pid = 12345L;

ProcessHandle.of(pid).ifPresentOrElse(
    handle -> System.out.println("Process is alive: " + handle.isAlive()),
    () -> System.out.println("Process not found or not visible")
);
~~~

Nếu muốn xử lý tường minh:

~~~java
Optional<ProcessHandle> optionalHandle = ProcessHandle.of(pid);

if (optionalHandle.isPresent()) {
    ProcessHandle handle = optionalHandle.orElseThrow();
    System.out.println("PID: " + handle.pid());
    System.out.println("Alive: " + handle.isAlive());
}
~~~

Không nên gọi get() trực tiếp khi chưa kiểm tra Optional. Dùng ifPresent, ifPresentOrElse hoặc orElseThrow để thể hiện rõ trường hợp PID không có handle.

Một PID có thể đã kết thúc hoặc được tái sử dụng giữa lúc tra cứu và lúc thao tác. Việc lấy được handle không bảo đảm tiến trình vẫn còn sống ở mọi thời điểm tiếp theo; hãy kiểm tra isAlive() ngay trước thao tác cần thiết và xử lý trường hợp tiến trình đã kết thúc.

## 4. Phân biệt Process và ProcessHandle

Hai kiểu này liên quan nhưng phục vụ hai mục đích khác nhau.

| Kiểu | Vai trò |
|---|---|
| Process | Đại diện cho tiến trình được ứng dụng khởi chạy, cung cấp luồng vào/ra/lỗi, waitFor(), exitValue() và các thao tác chờ hoặc kết thúc |
| ProcessHandle | Đại diện cho tiến trình hệ điều hành, cung cấp PID, thông tin, quan hệ tiến trình, trạng thái và thao tác điều khiển |

Khi khởi chạy tiến trình bằng ProcessBuilder, có thể chuyển từ Process sang ProcessHandle:

~~~java
Process process = new ProcessBuilder("java", "-version").start();

long pid = process.pid();
ProcessHandle handle = process.toHandle();

System.out.println("PID: " + pid);
System.out.println("Same PID: " + (pid == handle.pid()));
~~~

Process.pid() và Process.toHandle() có từ Java 9. ProcessHandle không cung cấp các luồng stdin, stdout, stderr; nếu cần đọc output hoặc ghi input của tiến trình con, hãy tiếp tục dùng đối tượng Process.

ProcessHandle.current() lấy tiến trình JVM hiện tại. Process.toHandle() lấy handle của một tiến trình mà ứng dụng đã khởi chạy. Chọn API theo việc cần quản lý luồng I/O hay cần quan sát và điều khiển tiến trình ở cấp hệ điều hành.

## 5. Đọc thông tin bằng ProcessHandle.Info

handle.info() trả về ProcessHandle.Info, chứa các thông tin có thể lấy được về tiến trình. Các phương thức trả về Optional vì hệ điều hành hoặc quyền truy cập có thể không cung cấp mọi trường.

Một số trường thông tin:

| Phương thức | Ý nghĩa |
|---|---|
| command() | Đường dẫn hoặc tên chương trình thực thi |
| commandLine() | Dòng lệnh khởi chạy tiến trình |
| arguments() | Mảng đối số của tiến trình |
| startInstant() | Thời điểm bắt đầu |
| totalCpuDuration() | Tổng thời gian CPU đã sử dụng |
| user() | Người dùng sở hữu tiến trình |

Ví dụ:

~~~java
ProcessHandle handle = ProcessHandle.current();
ProcessHandle.Info info = handle.info();

info.command().ifPresent(command ->
    System.out.println("Command: " + command)
);

info.startInstant().ifPresent(start ->
    System.out.println("Started: " + start)
);

info.totalCpuDuration().ifPresent(cpu ->
    System.out.println("CPU time: " + cpu)
);
~~~

Không giả định command(), arguments() hoặc user() luôn có giá trị. Hãy kiểm tra Optional trước khi sử dụng. Thông tin Info là ảnh chụp tại thời điểm lấy; nếu cần trạng thái mới hơn, hãy gọi info() lại.

commandLine() và arguments() có thể chứa đường dẫn, tên tài khoản, token hoặc dữ liệu nhạy cảm do ứng dụng truyền trên command line. Tránh ghi toàn bộ các trường này vào log dùng chung hoặc hiển thị cho người không có quyền xem.

## 6. Quan hệ cha, con và cây tiến trình

ProcessHandle hỗ trợ truy cập quan hệ tiến trình:

- parent(): Optional chứa tiến trình cha nếu có và nhìn thấy được.
- children(): Stream các tiến trình con trực tiếp.
- descendants(): Stream các tiến trình con và hậu duệ trong cây tiến trình.

Lấy PID của tiến trình cha:

~~~java
ProcessHandle.current().parent()
    .ifPresent(parent -> System.out.println("Parent PID: " + parent.pid()));
~~~

Liệt kê các tiến trình con trực tiếp:

~~~java
ProcessHandle.current().children()
    .forEach(child -> System.out.println("Child PID: " + child.pid()));
~~~

Liệt kê các tiến trình hậu duệ:

~~~java
ProcessHandle.current().descendants()
    .forEach(descendant ->
        System.out.println("Descendant PID: " + descendant.pid())
    );
~~~

children() chỉ bao gồm con trực tiếp. descendants() đi qua toàn bộ cây bên dưới tiến trình hiện tại. Nếu cần xử lý cả cây, hãy xác định rõ thứ tự và chính sách khi một tiến trình kết thúc trong lúc đang duyệt.

Các Stream tiến trình phản ánh trạng thái quan sát được tại thời điểm tạo và không phải ảnh chụp nguyên tử của toàn bộ hệ thống. Tiến trình có thể kết thúc hoặc cây tiến trình có thể thay đổi trong lúc xử lý. Luôn kiểm tra isAlive() trước hành động quan trọng và xử lý trường hợp handle đã không còn hoạt động.

## 7. Liệt kê tiến trình với allProcesses()

ProcessHandle.allProcesses() trả về Stream các ProcessHandle mà tiến trình hiện tại có thể nhìn thấy:

~~~java
ProcessHandle.allProcesses()
    .limit(20)
    .forEach(handle ->
        System.out.println(
            handle.pid() + " " + handle.info().command().orElse("unknown")
        )
    );
~~~

Ví dụ giới hạn 20 phần tử để tránh in toàn bộ danh sách tiến trình. Nếu cần đếm số tiến trình nhìn thấy:

~~~java
long count = ProcessHandle.allProcesses().count();
System.out.println("Visible process count: " + count);
~~~

Danh sách phụ thuộc hệ điều hành và quyền truy cập. Không phải mọi tiến trình của máy đều nhất thiết xuất hiện. Số lượng và trạng thái tiến trình có thể thay đổi ngay trong khi duyệt; không dùng danh sách này như một bản chụp nhất quán để ra quyết định quan trọng.

Việc liệt kê và đọc thông tin tiến trình có thể bị giới hạn bởi nền tảng hoặc môi trường thực thi. Hãy xử lý UnsupportedOperationException khi triển khai trên môi trường không hỗ trợ đầy đủ và không giả định mọi trường metadata đều có sẵn.

## 8. Theo dõi tiến trình kết thúc bằng onExit()

onExit() trả về CompletableFuture<ProcessHandle>. Future hoàn thành khi tiến trình kết thúc. Đây là cách chờ bất đồng bộ, giúp ứng dụng tiếp tục xử lý công việc khác trong lúc tiến trình con chạy.

~~~java
Process process = new ProcessBuilder("java", "-version").start();
ProcessHandle handle = process.toHandle();

handle.onExit().thenAccept(exited -> {
    System.out.println("Exited PID: " + exited.pid());
    System.out.println("Still alive: " + exited.isAlive());
});
~~~

Nếu cần chờ ngay tại luồng hiện tại:

~~~java
ProcessHandle exited = handle.onExit().join();
System.out.println("Process ended: " + !exited.isAlive());
~~~

join() chặn luồng gọi cho đến khi Future hoàn thành. Trong ứng dụng giao diện hoặc server, nên dùng thenAccept, thenApply hoặc một cơ chế bất đồng bộ phù hợp thay vì chặn luồng xử lý chính.

Process cũng có onExit() trả về CompletableFuture<Process>. Dùng Process.onExit() nếu cần tiếp tục làm việc với đối tượng Process, chẳng hạn đọc exitValue(). Dùng ProcessHandle.onExit() nếu cần kết quả là handle của tiến trình đã kết thúc.

onExit() cũng hữu ích khi tiến trình có thể kết thúc trước lúc đăng ký callback: Future sẽ hoàn thành theo trạng thái tiến trình, nên không cần tự viết vòng lặp polling bằng isAlive().

## 9. Gửi yêu cầu kết thúc tiến trình

ProcessHandle cung cấp hai thao tác:

- destroy(): gửi yêu cầu kết thúc tiến trình. Khả năng kết thúc bình thường phụ thuộc implementation và hệ điều hành.
- destroyForcibly(): gửi yêu cầu kết thúc cưỡng bức.

supportsNormalTermination() cho biết destroy() có khả năng kết thúc tiến trình theo cách bình thường hay không. Nếu trả về false, destroy() có thể có hiệu lực tương đương destroyForcibly() trên implementation đó.

~~~java
ProcessHandle handle = ProcessHandle.of(pid).orElseThrow();

if (handle.isAlive()) {
    boolean normalSupported = handle.supportsNormalTermination();
    System.out.println("Normal termination supported: " + normalSupported);

    boolean requestAccepted = handle.destroy();
    System.out.println("Termination request accepted: " + requestAccepted);
}
~~~

Nếu cần yêu cầu kết thúc cưỡng bức:

~~~java
if (handle.isAlive()) {
    boolean requestAccepted = handle.destroyForcibly();
    System.out.println("Force request accepted: " + requestAccepted);
}
~~~

Giá trị boolean cho biết yêu cầu có được gửi thành công theo implementation hay không; nó không khẳng định tiến trình đã biến mất ngay tại thời điểm phương thức trả về. Hãy dùng onExit() để chờ hoàn tất hoặc kiểm tra isAlive() sau đó.

Chỉ gửi yêu cầu kết thúc đối với tiến trình mà ứng dụng có quyền quản lý. Không nên kết thúc một PID chỉ vì nó xuất hiện trong danh sách; PID có thể đã được tái sử dụng và tiến trình hiện tại có thể không còn là tiến trình mà ứng dụng dự định xử lý.

## 10. Ví dụ hoàn chỉnh: lấy PID và chờ tiến trình con

Ví dụ tạo một tiến trình Java con bằng ProcessBuilder, lấy ProcessHandle của nó, đăng ký onExit() và đọc mã thoát sau khi tiến trình kết thúc. Chương trình dùng đường dẫn Java trong java.home để chạy được trên Windows, Linux và macOS.

**Tệp ProcessHandleDemo.java:**

~~~java
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

public class ProcessHandleDemo {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--child")) {
            return;
        }

        ProcessHandle current = ProcessHandle.current();
        long currentPid = current.pid();

        System.out.println("current pid positive: " + (currentPid > 0));
        System.out.println("lookup current pid: "
                + ProcessHandle.of(currentPid).isPresent());
        System.out.println("current alive: " + current.isAlive());

        String osName = System.getProperty("os.name").toLowerCase(Locale.ROOT);
        String javaName = osName.contains("win") ? "java.exe" : "java";
        String javaExecutable = Path.of(
                System.getProperty("java.home"), "bin", javaName).toString();

        Process child = new ProcessBuilder(
                javaExecutable,
                "-cp",
                System.getProperty("java.class.path"),
                ProcessHandleDemo.class.getName(),
                "--child")
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start();

        try {
            ProcessHandle childHandle = child.toHandle();
            System.out.println("child pid positive: " + (childHandle.pid() > 0));

            CompletableFuture<ProcessHandle> exit = childHandle.onExit();
            ProcessHandle exited = exit.join();

            System.out.println("child exited: " + !exited.isAlive());
            System.out.println("child exit code: " + child.exitValue());
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                child.waitFor();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all ProcessHandleDemo.java
java ProcessHandleDemo
~~~

Output:

~~~text
current pid positive: true
lookup current pid: true
current alive: true
child pid positive: true
child exited: true
child exit code: 0
~~~

Các dòng PID chỉ kiểm tra PID có giá trị dương, không in con số cụ thể vì PID thay đổi theo lần chạy. Tiến trình con thoát bình thường nên exit code là 0. finally bảo đảm gửi yêu cầu dừng cưỡng bức và chờ nếu tiến trình con vẫn còn chạy do một lỗi trong quá trình xử lý.

Process không triển khai AutoCloseable, vì vậy không dùng Process trực tiếp trong try-with-resources. Cần quản lý vòng đời tiến trình bằng waitFor(), onExit(), destroy() hoặc destroyForcibly() và xử lý các luồng I/O theo nhu cầu.

## 11. Giới hạn và lỗi thường gặp

- **Ép PID từ long sang int:** có thể mất dữ liệu. Giữ kiểu long khi lưu và truyền PID.
- **Coi PID là định danh vĩnh viễn:** hệ điều hành có thể tái sử dụng PID sau khi tiến trình kết thúc. Không dùng PID cũ để kết thúc tiến trình sau một khoảng thời gian mà không xác minh.
- **Giả định ProcessHandle.of luôn có giá trị:** PID có thể không tồn tại hoặc tiến trình không nhìn thấy được. Xử lý Optional.empty().
- **Giả định Info luôn đầy đủ:** command, arguments, user và thời gian có thể không được cung cấp. Kiểm tra Optional.
- **Nhầm children với descendants:** children chỉ là con trực tiếp; descendants bao gồm cả các thế hệ phía dưới.
- **Cho rằng destroy() luôn kết thúc bình thường:** hành vi phụ thuộc hệ điều hành. Kiểm tra supportsNormalTermination() và theo dõi onExit().
- **Cho rằng destroyForcibly() hoàn tất ngay:** đây vẫn là yêu cầu kết thúc. Chờ onExit() hoặc kiểm tra isAlive().
- **Polling liên tục bằng isAlive():** gây lãng phí CPU và khó kiểm soát. Ưu tiên onExit() khi cần biết thời điểm kết thúc.
- **Giả định allProcesses là danh sách toàn hệ thống bất biến:** kết quả chỉ gồm tiến trình nhìn thấy được và có thể thay đổi trong lúc duyệt.
- **Ghi commandLine hoặc arguments vào log:** các trường này có thể chứa thông tin nhạy cảm. Chỉ thu thập và hiển thị khi có lý do và quyền phù hợp.
- **Nhầm Process với ProcessHandle:** Process quản lý I/O và exit code của tiến trình đã khởi chạy; ProcessHandle cung cấp PID, metadata và điều khiển tiến trình.

## 12. Chọn API theo nhu cầu

| Nhu cầu | API |
|---|---|
| Lấy PID của JVM hiện tại | ProcessHandle.current().pid() |
| Tìm tiến trình theo PID | ProcessHandle.of(pid) |
| Kiểm tra tiến trình còn chạy | isAlive() |
| Đọc metadata | info() |
| Lấy tiến trình cha | parent() |
| Lấy tiến trình con trực tiếp | children() |
| Lấy toàn bộ hậu duệ | descendants() |
| Liệt kê tiến trình nhìn thấy được | allProcesses() |
| Chờ tiến trình kết thúc bất đồng bộ | onExit() |
| Gửi yêu cầu kết thúc | destroy() |
| Gửi yêu cầu kết thúc cưỡng bức | destroyForcibly() |
| Chuyển từ Process sang ProcessHandle | Process.toHandle() |
| Lấy PID từ Process | Process.pid() |

## 13. Ghi nhớ

ProcessHandle là API Java 9 để làm việc với tiến trình hệ điều hành. Dùng pid() để lấy PID, current() để lấy tiến trình JVM hiện tại, of() để tìm tiến trình theo PID và info() để đọc metadata dạng Optional. parent(), children() và descendants() giúp theo dõi cây tiến trình; onExit() cho phép chờ bất đồng bộ. destroy() và destroyForcibly() chỉ gửi yêu cầu kết thúc, vì vậy hãy kiểm tra trạng thái và chờ tiến trình thực sự thoát. PID có thể được tái sử dụng, metadata có thể thiếu và danh sách tiến trình phụ thuộc nền tảng/quyền truy cập.
