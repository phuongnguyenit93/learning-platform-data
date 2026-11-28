# Tạo tiến trình bằng ProcessBuilder và xác định chủ sở hữu

Java tạo tiến trình hệ điều hành bằng **ProcessBuilder**. Lệnh và tham số được cấu hình trước, sau đó gọi **start()** để khởi chạy tiến trình con và nhận về một đối tượng **Process**. Từ đối tượng này, ứng dụng có thể đọc/ghi luồng chuẩn, chờ kết thúc, lấy exit code và chuyển sang **ProcessHandle** để quan sát hoặc yêu cầu dừng tiến trình.

Điểm quan trọng của quản lý vòng đời là xác định thành phần nào trong ứng dụng chịu trách nhiệm với tiến trình đã khởi chạy. ProcessBuilder chỉ cấu hình và khởi chạy; nó không tự quản lý vòng đời thay cho ứng dụng. Thành phần gọi start() cần lưu Process/ProcessHandle, xác định chính sách timeout, thu thập output và dọn dẹp tiến trình khi công việc kết thúc hoặc bị hủy.

Các API ProcessBuilder, Process và ProcessHandle đã ổn định từ Java 9. Trong JDK 26, chúng không phải preview hay incubator API; không cần bật --enable-preview hoặc thêm module thử nghiệm.

## 1. Vai trò của ProcessBuilder, Process và ProcessHandle

| API | Vai trò | Dùng khi |
|---|---|---|
| ProcessBuilder | Cấu hình executable, tham số, thư mục làm việc, environment và redirect stream; gọi start() để chạy | Chuẩn bị lệnh và tạo process |
| Process | Đại diện cho tiến trình do ứng dụng khởi chạy; cung cấp stdin/stdout/stderr, waitFor(), exitValue(), destroy() và onExit() | Điều phối tiến trình trực tiếp đã tạo |
| ProcessHandle | Đại diện cho một tiến trình hệ điều hành; cung cấp PID, thông tin, parent/children/descendants, trạng thái và thao tác destroy | Quan sát process tree và quản lý process theo handle |

Mỗi lần gọi ProcessBuilder.start() sẽ tạo một tiến trình mới và trả về Process tương ứng. Có thể gọi start() nhiều lần trên cùng một ProcessBuilder để tạo nhiều tiến trình với cấu hình tương tự; mỗi lần gọi trả về Process riêng. Thay đổi ProcessBuilder sau khi start() không thay đổi tiến trình đã chạy.

Process.toHandle() trả về ProcessHandle của tiến trình đó. Nên lưu handle ngay sau khi start() nếu ứng dụng cần ghi log PID, quan sát tiến trình hoặc quản lý các tiến trình con.

## 2. Cấu hình lệnh và môi trường trước khi start()

ProcessBuilder nhận một danh sách các chuỗi: phần tử đầu tiên là chương trình cần chạy, các phần tử tiếp theo là đối số. Mỗi đối số nên là một phần tử riêng trong danh sách.

    Path workingDirectory = Path.of("C:/workspace/my-app");

    ProcessBuilder builder = new ProcessBuilder(
            "git",
            "status",
            "--short"
    );

    builder.directory(workingDirectory.toFile());
    builder.redirectErrorStream(true);

    Process process = builder.start();

Các thuộc tính thường cấu hình:

- **command()**: executable và các đối số.
- **directory(File)**: thư mục làm việc của tiến trình con. Nếu không đặt, tiến trình thường kế thừa working directory của tiến trình Java hiện tại.
- **environment()**: bản đồ biến môi trường. Mặc định là bản sao môi trường của tiến trình hiện tại; có thể thêm, sửa hoặc xóa biến trước khi start().
- **redirectInput(...)**, **redirectOutput(...)**, **redirectError(...)**: chuyển hướng stdin, stdout và stderr đến file, pipe hoặc stream kế thừa.
- **redirectErrorStream(true)**: gộp stderr vào stdout để đọc hoặc chuyển hướng chung.
- **inheritIO()**: cho tiến trình con dùng các stream chuẩn của tiến trình Java hiện tại.

ProcessBuilder không tự phân tích một chuỗi lệnh như terminal shell. Ví dụ, truyền "git", "status", "--short" tạo ra executable và hai đối số riêng. Cách này giúp tránh lỗi quoting và giảm nguy cơ command injection. Nếu chủ động gọi shell như cmd.exe /c hoặc sh -c, ứng dụng phải tự xử lý quoting và dữ liệu đầu vào không tin cậy.

Nên dùng đường dẫn executable đáng tin cậy hoặc xác định rõ executable cần dùng. Nếu chỉ truyền tên lệnh, hệ điều hành sẽ tìm executable theo cơ chế tìm kiếm của môi trường, thường liên quan PATH. Đừng giả định PATH trong tiến trình con luôn giống PATH khi bạn mở terminal tương tác.

## 3. Xác định tiến trình do ứng dụng khởi chạy

Sau khi start(), giữ lại cả Process và ProcessHandle:

    Process process = builder.start();
    ProcessHandle child = process.toHandle();

    System.out.println("Child PID: " + child.pid());
    System.out.println("Alive: " + child.isAlive());

Process là đối tượng thuận tiện để điều khiển tiến trình mà chính lời gọi start() đã tạo. ProcessHandle bổ sung khả năng quan sát process theo PID và quan hệ cha-con của hệ điều hành.

Có thể lấy PID trực tiếp từ Process.pid() hoặc ProcessHandle.pid(). PID hữu ích cho log, giám sát và đối chiếu với công cụ hệ điều hành. Không nên chỉ lưu PID rồi dùng nó như định danh lâu dài: sau khi tiến trình kết thúc, hệ điều hành có thể tái sử dụng PID cho một tiến trình khác. Trong ứng dụng Java, ưu tiên giữ ProcessHandle trả về từ process.toHandle() cho đúng tiến trình đã tạo.

### ProcessBuilder không phải chủ sở hữu vòng đời

Có hai khái niệm cần tách biệt:

- **Quan hệ cha-con của hệ điều hành:** khi JVM gọi start(), tiến trình mới thường được tạo như một child process của tiến trình Java tại thời điểm đó. ProcessHandle.parent() cho biết parent hiện có nếu hệ điều hành cung cấp thông tin.
- **Chủ sở hữu ở cấp ứng dụng:** thành phần trong mã Java đã yêu cầu chạy tiến trình và chịu trách nhiệm quản lý nó, ví dụ một service, job runner hoặc component thực thi lệnh.

ProcessBuilder không giữ một danh sách tiến trình đã tạo và không tự động đóng chúng khi đối tượng builder hết phạm vi. Vì vậy, component gọi start() cần lưu Process/ProcessHandle và chuyển trách nhiệm rõ ràng cho một component quản lý vòng đời nếu process cần tồn tại lâu hơn request hiện tại.

Việc parent JVM kết thúc không phải là một hợp đồng portable rằng mọi child process hoặc descendant đều sẽ bị kết thúc theo. Hệ điều hành có thể re-parent child process hoặc để nó tiếp tục chạy. Nếu ứng dụng cần dừng tiến trình ngoài khi shutdown, phải chủ động thiết kế và kiểm thử chính sách cleanup.

## 4. Quan sát parent, children và descendants

ProcessHandle cung cấp các API để xem quan hệ tiến trình:

    ProcessHandle current = ProcessHandle.current();

    System.out.println("Current PID: " + current.pid());

    current.parent().ifPresent(parent ->
            System.out.println("Parent PID: " + parent.pid())
    );

    current.children().forEach(child ->
            System.out.println("Child PID: " + child.pid())
    );

    current.descendants().forEach(descendant ->
            System.out.println("Descendant PID: " + descendant.pid())
    );

Ý nghĩa:

- **current()** trả về handle của JVM hiện tại.
- **parent()** trả về Optional chứa parent process nếu thông tin có sẵn.
- **children()** trả về stream các tiến trình con trực tiếp.
- **descendants()** trả về stream các tiến trình con và hậu duệ ở các cấp sâu hơn.

Các stream children() và descendants() phản ánh một snapshot của process tree tại thời điểm truy vấn. Process có thể kết thúc hoặc tạo thêm child trong lúc ứng dụng đang duyệt. Vì vậy, danh sách này không phải một giao dịch nguyên tử khóa toàn bộ process tree.

Parent cũng có thể không còn tồn tại hoặc không thể xác định tại thời điểm truy vấn. Hệ điều hành có thể thay đổi quan hệ parent sau khi tiến trình cha kết thúc. Không dùng parent() như một bằng chứng bảo mật hoặc bằng chứng sở hữu.

Nếu cần quản lý một tiến trình cụ thể do ứng dụng tạo, dùng ProcessHandle từ Process.toHandle(). Nếu cần quản lý cả process tree, hãy xây dựng chính sách riêng: theo dõi các child mà ứng dụng khởi chạy, ghi nhận descendant cần quản lý, và xử lý race khi process tree thay đổi. Không gọi destroy() trên mọi descendant của JVM chỉ vì chúng xuất hiện trong snapshot; một tiến trình có thể thuộc một component khác hoặc không còn liên quan đến công việc đang dừng.

## 5. Đọc thông tin tiến trình qua ProcessHandle.Info

ProcessHandle.info() cung cấp thông tin tùy thuộc khả năng của hệ điều hành và quyền truy cập:

    ProcessHandle.Info info = child.info();

    info.command().ifPresent(command ->
            System.out.println("Command: " + command)
    );

    info.commandLine().ifPresent(commandLine ->
            System.out.println("Command line: " + commandLine)
    );

    info.arguments().ifPresent(arguments ->
            System.out.println("Arguments: " + String.join(" ", arguments))
    );

    info.startInstant().ifPresent(start ->
            System.out.println("Started: " + start)
    );

    info.totalCpuDuration().ifPresent(cpu ->
            System.out.println("CPU time: " + cpu)
    );

    info.user().ifPresent(user ->
            System.out.println("User: " + user)
    );

Các thuộc tính command, commandLine, arguments, startInstant, totalCpuDuration và user được biểu diễn bằng Optional vì hệ điều hành có thể không cung cấp hoặc không cho phép đọc thông tin đó. Không giả định mọi Optional đều có giá trị.

Thông tin command line có thể chứa token, mật khẩu hoặc tham số nhạy cảm nếu ứng dụng truyền chúng trực tiếp trên dòng lệnh. Tránh ghi toàn bộ commandLine/arguments vào log production. Dùng biến môi trường hoặc secret manager cũng cần cân nhắc quyền đọc environment của các tiến trình khác trên hệ điều hành; không có phương thức truyền bí mật nào tự động an toàn trong mọi môi trường.

## 6. Quản lý stdin, stdout và stderr để tránh deadlock

Mặc định, ProcessBuilder tạo pipe cho stdin, stdout và stderr của tiến trình con. Java có thể truy cập chúng qua:

- **getOutputStream()**: dữ liệu Java ghi vào đây đi đến stdin của tiến trình con.
- **getInputStream()**: Java đọc stdout của tiến trình con.
- **getErrorStream()**: Java đọc stderr của tiến trình con.

Một lỗi thường gặp là gọi waitFor() trong khi tiến trình con đang ghi nhiều dữ liệu ra stdout hoặc stderr mà ứng dụng không đọc. Pipe có dung lượng hữu hạn; khi đầy, tiến trình con bị block khi ghi, còn Java bị block khi chờ tiến trình kết thúc. Hai phía chờ nhau và tạo deadlock.

Có ba cách xử lý phổ biến:

1. Chuyển hướng stdout/stderr đến file bằng redirectOutput và redirectError.
2. Dùng redirectErrorStream(true) rồi đọc một stream chung.
3. Nếu cần đọc stdout và stderr riêng, tiêu thụ hai stream đồng thời bằng hai task riêng hoặc cơ chế I/O bất đồng bộ.

Ví dụ chuyển hướng output vào file:

    ProcessBuilder builder = new ProcessBuilder("java", "-version");
    builder.redirectErrorStream(true);
    builder.redirectOutput(Path.of("child-output.log").toFile());

    Process process = builder.start();
    process.getOutputStream().close(); // Báo EOF cho stdin nếu không gửi input.

    int exitCode = process.waitFor();

Lệnh java -version thường ghi thông tin phiên bản vào stderr; redirectErrorStream(true) gộp stream đó vào stdout và file nhận được toàn bộ output. Đóng getOutputStream() khi không có dữ liệu đầu vào giúp child nhận EOF thay vì chờ input mãi.

Nếu cần đọc trực tiếp, hãy bắt đầu task tiêu thụ stdout và stderr trước hoặc đồng thời với việc chờ tiến trình. Không đọc tuần tự stdout đến EOF rồi mới đọc stderr nếu child có thể ghi đầy stderr trong lúc Java đang chờ stdout.

## 7. Chờ tiến trình kết thúc và đọc exit code

Process.waitFor() chờ tiến trình kết thúc và trả về exit code. Phương thức này có thể ném InterruptedException nếu luồng Java đang chờ bị interrupt.

Process.waitFor(timeout, unit) chờ trong khoảng thời gian giới hạn và trả về boolean:

- true: tiến trình đã kết thúc trong thời hạn.
- false: hết thời gian chờ nhưng tiến trình vẫn chưa kết thúc.

Chỉ gọi exitValue() sau khi xác nhận tiến trình đã kết thúc. Nếu process còn chạy, exitValue() ném IllegalThreadStateException.

    boolean finished = process.waitFor(10, TimeUnit.SECONDS);

    if (finished) {
        System.out.println("Exit code: " + process.exitValue());
    } else {
        System.out.println("Process vẫn đang chạy sau timeout");
    }

Quy ước exit code 0 thường biểu thị thành công, còn giá trị khác 0 thường biểu thị lỗi theo hợp đồng của chương trình con. Tuy nhiên, ý nghĩa cụ thể của exit code phụ thuộc executable được gọi; ứng dụng cần đọc tài liệu hoặc quy ước của lệnh đó.

### Chờ bất đồng bộ với onExit()

Nếu không muốn block luồng hiện tại, dùng Process.onExit():

    process.onExit().thenAccept(exited -> {
        System.out.println("Child ended with code "
                + exited.exitValue());
    });

onExit() trả về CompletableFuture<Process>, hoàn tất khi tiến trình kết thúc. Có thể kết hợp với các thao tác CompletableFuture khác để điều phối công việc. Tuy nhiên, onExit() không tự đọc stdout/stderr; vẫn phải xử lý stream hoặc redirect để tránh child bị block do pipe đầy.

## 8. Dừng tiến trình có timeout và xác nhận đã kết thúc

Process.destroy() yêu cầu dừng tiến trình. Cách hệ điều hành thực hiện có thể khác nhau; không giả định mọi nền tảng đều gửi cùng một loại tín hiệu hoặc đảm bảo shutdown graceful. Process.destroyForcibly() yêu cầu kết thúc cưỡng bức, nhưng cũng không có nghĩa tiến trình đã biến mất ngay tại thời điểm phương thức trả về.

Sau khi yêu cầu dừng, cần chờ và xác nhận bằng waitFor() hoặc isAlive():

    process.destroy();

    if (!process.waitFor(2, TimeUnit.SECONDS)) {
        process.destroyForcibly();

        if (!process.waitFor(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Process chưa kết thúc sau yêu cầu forcible termination"
            );
        }
    }

ProcessHandle có các phương thức tương ứng destroy(), destroyForcibly() và supportsNormalTermination(). supportsNormalTermination() cho biết destroy() có yêu cầu kết thúc bình thường theo khả năng implementation hay không. Nó không đảm bảo ứng dụng con sẽ hoàn tất cleanup trong một thời gian cụ thể.

Đừng gọi destroyForcibly() ngay khi hết timeout nếu ứng dụng con có thể hoàn tất cleanup trong một khoảng ngắn. Một chính sách thường dùng là yêu cầu dừng trước, chờ grace period, rồi mới yêu cầu kết thúc cưỡng bức. Sau đó vẫn phải chờ và kiểm tra tiến trình đã kết thúc hay chưa.

## 9. Xử lý interruption khi luồng Java đang chờ

waitFor() là thao tác interruptible. Nếu thread owner bị interrupt trong lúc chờ, waitFor() ném InterruptedException và xóa interrupt status khi ném exception. Ứng dụng cần quyết định việc đó có nghĩa là hủy công việc hay chỉ truyền tín hiệu lên tầng cao hơn.

Nếu thread bị interrupt, component quản lý process thường nên yêu cầu child dừng, chờ trong khoảng grace period, chuyển sang destroyForcibly() nếu cần, sau đó khôi phục interrupt status và truyền exception lên:

    static void stopProcess(Process process) {
        process.destroy();

        try {
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    System.err.println("Child vẫn còn hoạt động");
                }
            }
        } catch (InterruptedException e) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
        }
    }

    static int waitForProcess(Process process) throws InterruptedException {
        try {
            if (!process.waitFor(30, TimeUnit.SECONDS)) {
                stopProcess(process);
                throw new IllegalStateException("Process timed out");
            }
            return process.exitValue();
        } catch (InterruptedException e) {
            stopProcess(process);
            Thread.currentThread().interrupt();
            throw e;
        }
    }

Trong mã thực tế, tránh để nhiều component cùng tranh quyền dừng một Process. Hãy chỉ định một lifecycle owner chịu trách nhiệm timeout, interrupt và cleanup. Nếu có nhiều caller, họ nên gửi yêu cầu hủy đến owner thay vì mỗi caller tự gọi destroy().

## 10. Ví dụ hoàn chỉnh: start, ghi nhận owner, redirect và timeout

Ví dụ sau khởi chạy Java executable của cùng JDK đang chạy chương trình. Nó chuyển hướng stdout/stderr vào log file, lưu ProcessHandle, chờ tối đa 10 giây và thực hiện dừng theo hai giai đoạn nếu cần.

    import java.io.IOException;
    import java.nio.file.Path;
    import java.util.concurrent.TimeUnit;

    public class ManagedChildProcess {

        private static boolean stop(Process process) {
            process.destroy();

            try {
                if (process.waitFor(2, TimeUnit.SECONDS)) {
                    return true;
                }

                process.destroyForcibly();
                return process.waitFor(2, TimeUnit.SECONDS);

            } catch (InterruptedException e) {
                process.destroyForcibly();
                Thread.currentThread().interrupt();
                return false;
            }
        }

        public static void main(String[] args)
                throws IOException, InterruptedException {

            String executable = Path.of(
                    System.getProperty("java.home"),
                    "bin",
                    System.getProperty("os.name").startsWith("Windows")
                            ? "java.exe"
                            : "java"
            ).toString();

            Path output = Path.of("child-process.log")
                    .toAbsolutePath();

            ProcessBuilder builder = new ProcessBuilder(
                    executable,
                    "-version"
            );

            builder.directory(Path.of(".").toAbsolutePath().toFile());
            builder.redirectErrorStream(true);
            builder.redirectOutput(output.toFile());

            Process process = builder.start();
            ProcessHandle handle = process.toHandle();

            // Không gửi input: đóng stdin để child nhận EOF.
            process.getOutputStream().close();

            System.out.println("Owner PID: "
                    + ProcessHandle.current().pid());
            System.out.println("Child PID: " + handle.pid());
            System.out.println("Command: "
                    + handle.info().command().orElse("unavailable"));

            try {
                boolean finished = process.waitFor(
                        10,
                        TimeUnit.SECONDS
                );

                if (!finished) {
                    if (!stop(process)) {
                        throw new IllegalStateException(
                                "Không xác nhận được child đã dừng"
                        );
                    }
                    System.out.println("Child đã bị dừng do timeout");
                }

                System.out.println("Exit code: " + process.exitValue());
                System.out.println("Output file: " + output);

            } catch (InterruptedException e) {
                stop(process);
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }

Biên dịch và chạy bằng JDK 26:

    javac --release 26 -encoding UTF-8 -d out src/ManagedChildProcess.java
    java -cp out ManagedChildProcess

Ví dụ này dùng API đã ổn định nên không cần --enable-preview. File child-process.log chứa thông tin phiên bản Java mà child ghi ra. PID của JVM hiện tại và child được ghi riêng để thấy quan hệ process ở thời điểm khởi chạy.

## 11. Quản lý process tree và tiến trình con do child tạo

Một tiến trình con có thể tự tạo thêm tiến trình khác. Khi đó, Process đại diện cho child trực tiếp không tự cung cấp Process object cho mọi descendant. Có thể dùng ProcessHandle.descendants() để quan sát cây con tại một thời điểm:

    ProcessHandle root = process.toHandle();

    List<ProcessHandle> snapshot = root.descendants().toList();

    for (ProcessHandle descendant : snapshot) {
        System.out.println(
                descendant.pid() + " "
                        + descendant.info().command().orElse("unknown")
        );
    }

Snapshot có thể trở nên cũ ngay sau khi lấy: tiến trình có thể kết thúc, sinh thêm child hoặc bị hệ điều hành re-parent. Không có thao tác portable duy nhất bảo đảm dừng nguyên tử toàn bộ process tree đang thay đổi.

Nếu ứng dụng có yêu cầu dừng cả cây, nên thiết kế từ đầu để mỗi tiến trình do ứng dụng khởi chạy đều được ghi nhận và có lifecycle owner. Khi cần cleanup, lấy snapshot descendant, yêu cầu dừng các tiến trình cần quản lý, chờ trong grace period, sau đó mới dừng root. Cần lặp lại việc quan sát nếu workload có thể tạo descendant mới trong lúc cleanup; vẫn phải chấp nhận race và kiểm thử trên hệ điều hành triển khai.

Không dùng ProcessHandle.allProcesses() để suy ra tiến trình nào thuộc ứng dụng. API đó liệt kê các process có thể quan sát trên hệ thống, không xác định ownership nghiệp vụ. Tương tự, ProcessHandle.of(pid) chỉ tìm handle cho PID hiện tại nếu có; biết PID không có nghĩa ứng dụng có quyền hoặc trách nhiệm dừng process đó.

## 12. Các vấn đề bảo mật và độ tin cậy

- **Command injection:** không nối input không tin cậy vào một chuỗi shell. Dùng executable cố định và từng argument riêng; xác thực giá trị đối số theo nghiệp vụ.
- **Executable search path:** không tin PATH hoặc working directory do người dùng kiểm soát khi chạy lệnh nhạy cảm. Dùng đường dẫn executable đáng tin cậy.
- **Environment:** chỉ truyền biến môi trường cần thiết; tránh đưa secret vào command line hoặc log. Process con có thể thừa hưởng environment từ JVM.
- **Output:** log của child có thể chứa token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Đặt quyền file log và chính sách lưu trữ phù hợp.
- **Resource exhaustion:** giới hạn thời gian chạy, output size, số process đồng thời và số lần retry. Redirect ra file cũng cần kiểm soát dung lượng file.
- **Process ownership:** chỉ dừng những process mà component của bạn thực sự quản lý. Không giết process theo PID chỉ vì nó có quan hệ descendant trong một snapshot cũ.
- **Cleanup:** dừng child trong lifecycle kết thúc bình thường và khi cancellation; shutdown hook chỉ là biện pháp dự phòng, không thay thế cleanup tường minh.

Nếu cần truyền dữ liệu lớn giữa Java và child process, dùng stream có kiểm soát và tiêu thụ đồng thời. Nếu chỉ cần gọi một công cụ tạo file, redirect output đến file và giới hạn thời gian thường đơn giản hơn.

## 13. Checklist triển khai

1. Dùng ProcessBuilder để cấu hình executable và arguments thành từng phần tử.
2. Xác định working directory, environment và redirect policy trước start().
3. Ngay sau start(), giữ Process và ProcessHandle của child.
4. Xác định component nào là lifecycle owner và ai chịu trách nhiệm dừng process.
5. Đọc stdout/stderr đồng thời hoặc redirect để tránh pipe deadlock.
6. Đóng stdin nếu child không cần input.
7. Dùng waitFor(timeout, unit) hoặc onExit() thay cho chờ vô hạn không kiểm soát.
8. Chỉ đọc exitValue() sau khi process đã kết thúc.
9. Khi timeout/interruption, yêu cầu dừng, chờ grace period, rồi mới dùng destroyForcibly().
10. Xác nhận isAlive() hoặc waitFor() sau khi yêu cầu dừng.
11. Nếu quản lý descendants, hiểu rằng children()/descendants() là snapshot có thể thay đổi.
12. Không suy ra quyền sở hữu từ PID hoặc parent() đơn thuần.
13. Chạy thử trên đúng OS, quyền người dùng và container/runtime production.
14. Dùng API stable của JDK 26; không bật preview hoặc phụ thuộc API nội bộ.

## Tài liệu chính thức

- [Java SE 26 API — ProcessBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): cấu hình command, directory, environment, redirect và start().
- [Java SE 26 API — Process](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): stream, waitFor, timeout, exitValue, destroy, onExit và toHandle.
- [Java SE 26 API — ProcessHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html): PID, parent, children, descendants, info, onExit và thao tác điều khiển.
- [Java SE 26 API — ProcessHandle.Info](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.Info.html): command, arguments, start time, CPU duration và user.
- [Java SE 26 API — ProcessBuilder.Redirect](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.Redirect.html): redirect stream đến file, pipe, DISCARD hoặc stream kế thừa.
- [Oracle Java Tutorials — Process API](https://docs.oracle.com/javase/tutorial/essential/environment/process.html): mô hình khởi chạy và giao tiếp với process.
- [Java SE 26 API — CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): phối hợp kết quả bất đồng bộ từ Process.onExit().

ProcessBuilder và ProcessHandle là API Java ổn định, dùng được trên JDK 26 mà không cần preview flag. Điều cần thiết kế cẩn thận là quyền sở hữu vòng đời, luồng I/O, timeout, interruption và việc dừng descendant. JVM không tự thay ứng dụng quyết định khi nào một tiến trình ngoài cần kết thúc.
