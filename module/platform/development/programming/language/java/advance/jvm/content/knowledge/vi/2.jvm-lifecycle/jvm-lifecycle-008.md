# Khác biệt giữa kết thúc bình thường, ngoại lệ không được bắt và JVM bị dừng cưỡng bức

## 1. Phân biệt thread, JVM và tiến trình

Khi nói “ứng dụng Java kết thúc”, phải xác định chính xác đối tượng đang dừng:

- **Thread kết thúc:** phương thức run() hoàn thành hoặc Throwable không được bắt thoát khỏi thread. Những thread khác vẫn có thể chạy.
- **JVM bắt đầu shutdown có trật tự:** không còn non-daemon thread hoặc mã gọi System.exit(status), hoặc môi trường đưa JVM vào luồng shutdown được hỗ trợ. JVM khởi chạy các shutdown hook đã đăng ký theo quy tắc của nó rồi kết thúc.
- **Tiến trình bị chấm dứt cưỡng bức:** Runtime.halt(status), SIGKILL, một số trường hợp native crash hoặc OS ép dừng có thể kết thúc mọi thread mà không chạy shutdown hook Java.

**Exit code** là kết quả của *tiến trình*, không phải đặc tính của từng thread. Theo quy ước, 0 thường chỉ thành công và khác 0 thường chỉ lỗi, nhưng code không đủ nói cơ chế dừng: System.exit(7) có thể chạy shutdown hook; Runtime.halt(7) thì không. Ngoại lệ không được bắt ở worker cũng không nhất thiết làm tiến trình có exit code khác 0.

~~~text
Một thread kết thúc
    |
    +-- Còn non-daemon thread? -- Có --> JVM tiếp tục chạy
    |                        |
    |                        +-- Không --> JVM bắt đầu shutdown
    |
    +-- System.exit(status) được gọi --> JVM bắt đầu shutdown
    |
Tiến trình bị Runtime.halt()/SIGKILL/crash nghiêm trọng
    |
    +-- Chấm dứt đột ngột; không trông đợi Java shutdown hook
~~~

Các đường này độc lập: SIGKILL từ hệ điều hành không cần chờ thread Java nào kết thúc.

## 2. Bảng so sánh ba tình huống

| Khía cạnh | Hoàn thành bình thường | Ngoại lệ không được bắt | Dừng cưỡng bức |
| --- | --- | --- | --- |
| Ví dụ | main() trả về và các non-daemon thread hết; hoặc System.exit(status) yêu cầu shutdown | IllegalStateException đi ra khỏi main()/run() | Runtime.halt(), SIGKILL, OS/container ép kill, một số native crash |
| Đối tượng kết thúc trước | Thread hoàn thành hoặc JVM nhận lệnh shutdown | **Thread mang exception** chết trước; JVM có thể vẫn hoạt động | Thường **toàn bộ tiến trình** bị dừng |
| finally | Chạy khi rời scope bình thường; riêng System.exit() **không unwind stack** để thực hiện finally | Chạy khi stack unwinding đi qua khối finally, trừ khi có đường dừng abrupt khác | Không được bảo đảm; halt/SIGKILL không tháo stack Java |
| Shutdown hook | Được chạy khi JVM thực sự shutdown có trật tự | Chỉ chạy **nếu JVM sau đó shutdown** | Không chạy với Runtime.halt()/SIGKILL; với crash cũng không thể tin cậy |
| Exit status | main hoàn tất tự nhiên thường là 0; System.exit(status) dùng status đã yêu cầu | Main uncaught exception thường tạo code khác 0 trên Java launcher; worker lỗi riêng chưa tạo process exit | Runtime.halt(status) dùng status; tín hiệu OS do nền tảng quyết định |
| Cleanup | Có thể dùng scope/try-with-resources; hook hỗ trợ shutdown | finally của thread lỗi có thể chạy; thread khác vẫn chịu trách nhiệm cleanup riêng | Phải giả định Java cleanup có thể chưa chạy |

Kết thúc **tự nhiên** và shutdown **có chủ đích** qua System.exit() đều có thể có hook nhưng không có cùng đường control flow: System.exit() không quay về bình thường, nên finally của stack gọi exit không được thực hiện chỉ vì shutdown đã bắt đầu.

## 3. Kết thúc tự nhiên: main return chưa chắc JVM exit

JVM thường bắt đầu shutdown tự nhiên khi **mọi non-daemon thread đã khởi chạy đều kết thúc**. Thread main do launcher tạo thường là non-daemon, nhưng nó không nhất thiết là non-daemon cuối cùng.

- main() return mà còn một worker non-daemon: tiến trình tiếp tục.
- main() return và không còn non-daemon thread: JVM bắt đầu shutdown.
- Daemon thread không giữ JVM sống; một daemon đang làm việc có thể không hoàn thành khi JVM shutdown.
- Thread mới thường kế thừa trạng thái daemon từ thread tạo ra nó (trừ khi factory/công cụ quy định khác). Không nên suy ra mọi thread do mọi thư viện tạo đều non-daemon.

Tạo tệp **MainReturns.java**:

~~~java
public class MainReturns {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(200);
                System.out.println("WORKER_DONE");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("WORKER_INTERRUPTED");
            }
        }, "worker");

        worker.start();
        System.out.println("MAIN_RETURN");
    }
}
~~~

~~~bash
javac --release 17 MainReturns.java
java MainReturns
~~~

Đường chạy không bị interrupt cho đầu ra:

~~~text
MAIN_RETURN
WORKER_DONE
~~~

main() đã return trước, nhưng worker non-daemon vẫn giữ JVM sống. Thời gian sleep chỉ minh họa thứ tự; trong ứng dụng thực dùng join(), Future, structured concurrency phù hợp hoặc vòng đời ExecutorService có quản lý. Nếu một non-daemon thread pool không đóng, ứng dụng có thể “không chịu thoát” dù main() đã kết thúc.

### System.exit() là yêu cầu shutdown, không phải return

System.exit(status) gọi cơ chế Runtime.exit(status), yêu cầu kết thúc JVM với mã trạng thái tương ứng, kể cả khi vẫn có những thread không daemon khác đang chạy. JVM vào shutdown sequence và chạy hook đã đăng ký. Lời gọi **không trả về bình thường**, không chủ động unwind toàn bộ stack của thread hiện tại; nếu cần đóng tài nguyên trong một khối try, thực hiện cleanup **trước khi gọi exit**.

## 4. Ngoại lệ không được bắt: chỉ thread gây lỗi kết thúc trước

Khi Throwable không được catch và thoát khỏi phương thức gốc của một thread, thread đó chết. JVM có thể chuyển Throwable cho một UncaughtExceptionHandler để báo lỗi. Handler ghi nhận sự cố, **không tiếp tục chạy** đoạn code đã ném exception.

Với thread main:

1. Khi ngoại lệ lan truyền qua các scope, finally và try-with-resources tương ứng có cơ hội thực hiện cleanup trong quá trình tháo stack.
2. Nếu ngoại lệ thoát khỏi main(), thread main chấm dứt. Handler mặc định của Java launcher thường in stack trace lên **stderr**.
3. Nếu còn non-daemon thread, JVM vẫn có thể chạy. Nếu không còn, JVM bắt đầu shutdown và các hook được khởi chạy.
4. Với Java launcher thông dụng, uncaught exception ở main thường cho exit status khác 0, nhưng đặc tả JVM không yêu cầu mọi lỗi ở mọi thread phải tạo một exit code cố định.

Với worker thread, những thread khác có thể hoạt động bình thường. Trong ExecutorService, hành vi phụ thuộc cách submit task: lỗi ở Future thường được lưu để Future.get() đưa ra ExecutionException; không nhất thiết đi qua uncaught handler mặc định. Không được đồng nhất “task throw” với “VM chết”.

UncaughtExceptionHandler là đường **quan sát thất bại**, không phải catch có khả năng cho thread tiếp tục. Nếu handler tự lỗi, handler đó cũng không giúp phục hồi thread.

## 5. JVM shutdown có trật tự và shutdown hook

Đăng ký trước khi shutdown bắt đầu:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> System.out.println("cleanup"), "cleanup-hook"));
~~~

Khi JVM shutdown có trật tự, nó khởi chạy những hook đã đăng ký và chờ chúng hoàn thành. Những điểm cần hiểu chính xác:

- Nhiều hook chạy theo thứ tự **không xác định** và có thể **đồng thời**. Không thiết kế hook A phải hoàn thành rồi hook B mới chạy.
- Không được thêm/xóa hook khi shutdown đã khởi động; thao tác có thể ném IllegalStateException.
- Hook phải nhanh, có khả năng xử lý lỗi và tránh chờ vô hạn. Nếu hook tự deadlock, tiến trình có thể treo trong giai đoạn shutdown.
- Các thread ứng dụng khác có thể vẫn còn chạy trong shutdown sequence; không giả định chúng đã được join hoặc resource của chúng còn ở trạng thái sẵn sàng.
- Gọi System.exit() từ hook đang chạy có thể block vô thời hạn; không dùng nó để “exit lại”.
- Hook không bảo đảm chạy khi Runtime.halt(), SIGKILL hoặc crash/OS kill đột ngột; hook cũng có thể bị cắt ngang nếu orchestrator hết grace period.

Hook phù hợp cho cleanup cuối cùng có giới hạn và logging cuối; không phải nơi duy nhất chứa transaction commit, phát message quan trọng hay flush toàn bộ dữ liệu chưa bền vững.

## 6. Dừng cưỡng bức: Runtime.halt, SIGKILL, tín hiệu và crash

**Runtime.getRuntime().halt(status)** chấm dứt JVM ngay, **không khởi chạy shutdown hook** và không thực hiện Java stack unwinding cho finally còn chờ. Nó là cơ chế đặc biệt, không phải API chuẩn để kết thúc nghiệp vụ bình thường.

Một số đường dừng cấp tiến trình:

- **SIGKILL / kill -9** trên Unix/Linux không thể được tiến trình bắt hoặc trì hoãn; Java hook không có cơ hội chạy.
- **Container/OS ép kill:** hệ thống quản lý có thể gửi tín hiệu dừng và cho một grace period, sau đó giết tiến trình nếu nó chưa thoát.
- **Native/JVM crash:** có thể abort quá trình; một số JVM như HotSpot có thể sinh hs_err_pid*.log hoặc core dump nếu điều kiện cho phép, nhưng không cam kết có file cho mọi trường hợp.
- **Mất điện/OS chết:** dữ liệu chỉ nằm trong RAM, buffer hoặc chưa đồng bộ ổ lưu trữ có thể mất.

Phải phân biệt **SIGTERM** với **SIGKILL**. SIGTERM thường là yêu cầu dừng *có thể xử lý*: HotSpot trên nhiều môi trường Linux/Unix thường chuyển nó thành shutdown có hook, nhưng hành vi phụ thuộc JVM implementation, native signal handler và cấu hình/host. **SIGKILL** luôn là ép kill không thể catch. Ctrl+C, SIGINT, ProcessHandle.destroy() và thao tác stop service cũng có chi tiết phụ thuộc nền tảng. Không hứa tất cả hệ điều hành đều chạy hook khi nhận một “lệnh dừng”.

## 7. Thí nghiệm kiểm chứng trên Java 17+

Tạo tệp **JvmExitCases.java**. Mỗi lần chạy lệnh java là **một tiến trình riêng**, để exit/halt không ảnh hưởng thí nghiệm khác:

~~~java
public final class JvmExitCases {
    private static void log(String message) {
        System.out.println(message);
        System.out.flush();
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Choose normal, uncaught, worker, exit, or halt");
        }

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> log("HOOK"), "cleanup-hook"));

        String mode = args[0];
        if ("worker".equals(mode)) {
            Thread worker = new Thread(() -> {
                throw new IllegalStateException("worker-boom");
            }, "worker");

            worker.setUncaughtExceptionHandler((thread, error) ->
                    log("HANDLER: " + thread.getName() + ": "
                            + error.getClass().getSimpleName()));

            worker.start();
            worker.join();
            log("MAIN_CONTINUES");
            return;
        }

        try {
            log("BODY");
            switch (mode) {
                case "normal" -> { }
                case "uncaught" -> throw new IllegalStateException("boom");
                case "exit" -> System.exit(7);
                case "halt" -> Runtime.getRuntime().halt(9);
                default -> throw new IllegalArgumentException(
                        "Unknown mode: " + mode);
            }
        } finally {
            log("FINALLY");
        }
    }
}
~~~

Biên dịch và chạy riêng từng mode:

~~~bash
javac --release 17 JvmExitCases.java
java JvmExitCases normal
java JvmExitCases uncaught
java JvmExitCases worker
java JvmExitCases exit
java JvmExitCases halt
~~~

Để xem mã kết thúc **ngay sau lệnh cần kiểm tra**:

~~~bash
# Bash trên Linux/macOS
java JvmExitCases exit
echo $?

# PowerShell trên Windows
java JvmExitCases exit
echo $LASTEXITCODE
~~~

### 7.1. normal

Stdout:

~~~text
BODY
FINALLY
HOOK
~~~

Main kết thúc, finally chạy; khi hết non-daemon thread, JVM vào shutdown và chạy hook. Exit code thông thường là **0**.

### 7.2. uncaught

Các dòng **stdout**:

~~~text
BODY
FINALLY
HOOK
~~~

Ngoài ra mặc định còn có stack trace IllegalStateException với thông điệp boom ở **stderr**. Khi gộp hai stream, thứ tự xuất hiện giữa stack trace và dòng HOOK có thể khác nhau. Trên Java launcher thông dụng mã kết thúc là khác 0 (OpenJDK thường là 1); không dùng giá trị 1 làm bảo đảm từ đặc tả JVM. Khác normal ở đây là **main chết do exception**, dù hook vẫn chạy khi JVM shutdown.

### 7.3. worker

Stdout:

~~~text
HANDLER: worker: IllegalStateException
MAIN_CONTINUES
HOOK
~~~

Worker chết; handler riêng ghi lỗi; main join() thấy thread đã hoàn tất rồi tiếp tục. JVM chỉ shutdown khi main return và không còn non-daemon thread. Mã kết thúc thông thường là **0**. Vì đã cài handler riêng không in stack trace, ví dụ không có stack trace mặc định của worker.

### 7.4. exit

Stdout:

~~~text
BODY
HOOK
~~~

Không có FINALLY. System.exit(7) yêu cầu shutdown có hook nhưng **không** thoát qua finally trên stack hiện thời; mã kết thúc là **7**.

### 7.5. halt

Stdout đã chủ động flush trước khi halt:

~~~text
BODY
~~~

Không có FINALLY và không có HOOK; mã kết thúc là **9**. Flush ở ví dụ giúp dòng BODY được quan sát, nhưng halt có thể làm mất dữ liệu ở buffer khác. Không dùng đường halt cho logic xử lý ứng dụng bình thường.

**Kiểm chứng chạy thực tế:** mã này đã được biên dịch bằng JDK 21 với --release 17 và chạy cả năm mode. Kết quả stdout và status tương ứng 0, 1, 0, 7, 9 trên môi trường kiểm chứng; dòng exception của main nằm trên stderr và cách các stream được công cụ log ghép không cố định.

## 8. finally, try-with-resources và shutdown hook khác nhau

| Cơ chế | Khi nào dùng | Giới hạn |
| --- | --- | --- |
| try-with-resources | Đóng AutoCloseable lúc rời scope, kể cả khi exception đi qua scope | Halt/kill trước khi rời scope có thể bỏ dở cleanup |
| finally | Xử lý khi thoát khỏi khối try theo control flow hay stack unwinding của exception | System.exit không tự chạy finally đang nằm trên stack; halt/kill cũng không |
| Shutdown hook | Dọn dẹp khi JVM thực sự bắt đầu shutdown có trật tự | Không chạy trên mọi đường dừng; thứ tự nhiều hook không xác định |

Ví dụ đóng writer theo scope, không chờ shutdown hook:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ScopedResource {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("sample.txt");
        try (var writer = Files.newBufferedWriter(path)) {
            writer.write("important data");
        }
        System.out.println("FILE_CLOSED");
    }
}
~~~

Trong đường thành công, writer được đóng trước khi in FILE_CLOSED; nếu write() ném IOException, try-with-resources vẫn cố đóng writer. Dù vậy **close/flush tại Java layer không đồng nghĩa dữ liệu đã được fsync/bền vững trước mất điện**. Bảo toàn dữ liệu đòi hỏi thiết kế theo hệ lưu trữ, transaction, retry và phục hồi phù hợp.

Không đợi shutdown mới commit mọi message, transaction hoặc trạng thái nghiệp vụ. Việc ghi nhận tiến độ theo từng đơn vị công việc và cơ chế chạy lại an toàn giúp ứng dụng chịu được những lần bị SIGKILL hoặc crash.

## 9. Khi chương trình “không chịu thoát” hoặc chết bất ngờ, điều tra thế nào?

1. **Xác nhận JVM/process còn sống hay đã chết.** Nếu main kết thúc mà process không exit, kiểm tra non-daemon thread, thread pool, network service và thread dump.
2. **Xem exit status, stack trace, stderr và log vòng đời.** Exception không bắt của worker không chứng minh tiến trình chết; mã exit khác 0 không chứng minh SIGKILL.
3. **Xem nguồn yêu cầu dừng:** System.exit, signal, service manager, container orchestrator, OOM killer, timeout, crash native. Với container, kiểm tra cả nguyên nhân restart và grace period.
4. **Xem hook đã bắt đầu/kết thúc chưa:** hook có thể treo vì lock, join, network call hoặc phụ thuộc một thread đã ngừng. Thiếu dòng HOOK không tự chứng minh SIGKILL vì log cũng có thể bị mất.
5. **Kiểm chứng tài nguyên phía ngoài:** database commit, message ack, file flush/sync, lease timeout và khả năng replay. Chỉ nhìn thấy log cleanup không bảo đảm dữ liệu đã bền vững.
6. **Sửa tại vòng đời đúng:** đóng executor/server theo giao thức, chặn nhận công việc mới, đợi bounded timeout rồi hoàn tất có kiểm soát; giữ hook gọn và có giới hạn.

Các nhầm lẫn thường gặp:

- “main() return là process thoát”: sai nếu còn non-daemon thread.
- “Một exception không bắt luôn giết JVM”: sai, trước tiên nó chỉ kết thúc thread bị lỗi.
- “System.exit chạy mọi finally”: sai; nó dùng shutdown hook chứ không unwind mọi stack.
- “System.exit(7) giống Runtime.halt(7)”: sai, cùng status nhưng khác cleanup.
- “SIGTERM giống SIGKILL”: sai, SIGTERM có thể được xử lý, SIGKILL thì không.
- “Hook chạy theo thứ tự đăng ký”: sai, thứ tự không xác định và có thể song song.
- “Có shutdown hook là bảo đảm dữ liệu an toàn khi mất điện”: sai.

## 10. Câu hỏi tự kiểm tra

1. main ném RuntimeException không bắt, nhưng một non-daemon worker còn sống: JVM phải exit tức khắc không? **Không.**
2. Tại sao worker mode có handler in lỗi nhưng exit code bình thường vẫn là 0? **Worker chết, main tiếp tục hoàn thành và không yêu cầu status lỗi của process.**
3. System.exit(0) có thực thi finally bao quanh chính lời gọi đó không? **Không; nó bắt đầu shutdown chứ không trả khỏi scope theo control flow bình thường.**
4. Runtime.halt(0) có gọi shutdown hook không? **Không.**
5. Daemon thread có giữ JVM sống sau khi mọi non-daemon thread kết thúc không? **Không.**
6. Nhìn thấy HOOK có chứng minh mọi dữ liệu đã được ghi bền vững không? **Không; cần xác nhận commit/ack/fsync tương ứng.**

**Kết luận kỹ thuật:** hoàn thành tự nhiên và System.exit() có thể tạo shutdown có trật tự; ngoại lệ không bắt làm chết **thread mang lỗi** trước; Runtime.halt(), SIGKILL và kill cưỡng bức có thể dừng **toàn bộ tiến trình** mà không có shutdown hook. Thiết kế cleanup theo phạm vi tài nguyên, quản lý non-daemon thread, quan sát lỗi tại ranh giới tác vụ và xây dựng cơ chế khôi phục cho mọi công việc quan trọng.
