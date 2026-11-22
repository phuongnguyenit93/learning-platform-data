# Khi `main` kết thúc: luồng không daemon và điều kiện JVM thoát

Lời gọi `main(String[] args)` là **điểm vào của ứng dụng Java**, nhưng hoàn tất phương thức `main` **không đồng nghĩa** toàn bộ tiến trình JVM đã kết thúc. Sau khi `main` trả về, các luồng khác vẫn có thể chạy hoặc đang đợi; một luồng **non-daemon** còn sống có thể giữ tiến trình tiếp tục tồn tại. Ngược lại, những luồng **daemon** còn sống không tự chúng ngăn JVM bắt đầu quá trình shutdown.

Bài này giải thích quy tắc kết thúc JVM theo Java SE, phân biệt `main` với toàn bộ vòng đời ứng dụng, cách nhìn trạng thái daemon, cách quản lý worker và executor, và những ngoại lệ như `System.exit`, shutdown hooks và virtual threads.

## 1. Mô hình đúng: `main` là phương thức của một luồng, JVM là tiến trình có thể chứa nhiều luồng

Thông thường, Java launcher khởi động JVM, tải/khởi tạo lớp chính rồi gọi `main` trên một **luồng non-daemon**. Trong quá trình chạy, chương trình hoặc thư viện có thể khởi tạo thêm những luồng khác.

Ba sự kiện phải phân biệt:

1. **Phương thức `main` trả về** (hoặc ném exception chưa được xử lý): lời gọi vào `main` kết thúc; trong cách chạy launcher thông thường, luồng chính sau đó cũng kết thúc.
2. **Luồng `main` kết thúc**: JVM kiểm tra điều kiện kết thúc của *toàn bộ* chương trình; những luồng non-daemon đã được khởi động khác có thể vẫn còn sống.
3. **JVM/tiến trình kết thúc**: các luồng không còn tiếp tục thực thi Java code; hệ điều hành nhận lại tài nguyên tiến trình. Shutdown hooks có thể đã được chạy khi JVM kết thúc theo đường shutdown thông thường.

Trong JLS Java SE 17 `12.8, điều kiện kết thúc chương trình thông thường là **tất cả luồng non-daemon đã kết thúc**. Một đường khác là lời gọi `System.exit`/`Runtime.exit` được phép thực hiện. Tài liệu `Runtime` giải thích thêm quá trình shutdown hooks; các đường dừng đột ngột cần được xem riêng.

### Luồng non-daemon có còn sống không?

| Tình huống sau `main` | JVM có thể tự kết thúc ngay khi xét luồng? | Vì sao |
| --- | --- | --- |
| Không còn luồng non-daemon sống; chỉ còn daemon | Có, JVM bắt đầu shutdown | Daemon không giữ JVM tồn tại |
| Còn non-daemon đang thực thi công việc | Chưa | Nó vẫn là luồng sống |
| Còn non-daemon `sleep()`, `wait()`, `join()`, blocked I/O hoặc chờ khóa | Chưa | `WAITING`/`BLOCKED`/`TIMED_WAITING` không đồng nghĩa `TERMINATED` |
| Có đối tượng `Thread` non-daemon nhưng chưa gọi `start()` | Không vì riêng đối tượng đó | Thread chưa bắt đầu thì không phải luồng đang thực thi giữ JVM |
| Có non-daemon trước đó nhưng `run()` đã hoàn tất hoặc thoát vì exception | Không vì riêng luồng đã chết | Luồng đã kết thúc, dù object `Thread` còn được tham chiếu |
| Có non-daemon sống và một luồng gọi `System.exit(0)` | Có thể bắt đầu shutdown ngay | `System.exit` là đường kết thúc chủ động, không đợi mọi worker hoàn tất theo cơ chế đếm non-daemon |

Bảng giả định ứng dụng được chạy bằng Java launcher thông thường, không có non-daemon khác hoặc shutdown hook đang giữ tiến trình. “Có thể kết thúc” không hứa rằng lệnh shutdown mất thời gian bằng 0.

## 2. Daemon là thuộc tính ảnh hưởng đến thời điểm JVM tự shutdown

Một luồng `Thread` có cờ daemon:

- **Non-daemon (user thread):** khi còn sống, nó giữ JVM không tự kết thúc theo điều kiện “không còn non-daemon”.
- **Daemon:** vẫn là luồng Java thực sự và vẫn được lên lịch thực thi khi JVM chạy; nhưng một mình nó **không đủ** để giữ JVM sống.
- Phân loại daemon/non-daemon **không** biểu thị độ ưu tiên, mức CPU, tính an toàn của dữ liệu hoặc công việc quan trọng hay không.
- `Thread.isDaemon()` đọc trạng thái daemon; `Thread.isAlive()` cho biết luồng đã `start()` và chưa kết thúc. Cần kết hợp cả hai để hiểu liệu luồng có thể giữ JVM sống.
- Với **platform threads** truyền thống, `new Thread(runnable)` thường kế thừa cờ daemon của luồng *tạo đối tượng Thread*. Vì `main` trên launcher thường non-daemon, worker tạo từ `main` mặc định non-daemon.
- `setDaemon(boolean)` phải được gọi **trước `start()`**. Gọi sau khi luồng đã sống gây `IllegalThreadStateException`. Không có cách hợp lệ dùng `setDaemon` để biến một luồng đang chạy từ non-daemon thành daemon.
- Việc gán `setDaemon(true)` không “hủy” luồng khi `main` kết thúc; nó cho phép JVM kết thúc dù luồng ấy vẫn đang hoạt động nếu không còn luồng non-daemon khác.

Lưu ý sự khác nhau: **“daemon không giữ JVM tồn tại”** khác với **“daemon dừng ngay khi `main` trả về”**. Nếu một non-daemon khác còn sống, daemon vẫn có thể tiếp tục chạy. Khi JVM thực sự kết thúc, công việc daemon còn dang dở có thể bị chấm dứt mà không đi qua các khối cleanup thông thường.

## 3. Ví dụ A — `main` đã kết thúc nhưng non-daemon vẫn chạy

Tạo file **`MainAndWorker.java`**:

```java
public class MainAndWorker {
    public static void main(String[] args) {
        Thread mainThread = Thread.currentThread();

        Thread worker = new Thread(() -> {
            try {
                // Chỉ in khi luồng main thật sự đã kết thúc.
                mainThread.join();
                System.out.println("worker: main thread terminated");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("worker: interrupted");
            }
        }, "worker");

        // Dòng này minh họa rõ lựa chọn; mặc định vốn đã non-daemon
        // vì worker được tạo trên luồng main thông thường.
        worker.setDaemon(false);
        worker.start();

        System.out.println("main: returning");
    }
}
```

Chạy với **JDK 17+**:

```bash
javac --release 17 MainAndWorker.java
java MainAndWorker
```

**Stdout khi không có can thiệp bên ngoài**:

```text
main: returning
worker: main thread terminated
```

**Vì sao thứ tự output xác định?** `main` in dòng đầu, rồi trả về. `worker` chờ `mainThread.join()`; lệnh đó chỉ trả về bình thường sau khi luồng `main` kết thúc. Sau đó worker mới in dòng thứ hai. JVM không kết thúc giữa hai dòng vì worker là **non-daemon** đang sống. Sau khi worker hoàn thành `run()`, không còn non-daemon nào trong ví dụ này; JVM có thể shutdown.

Ví dụ cố ý dùng `join()` từ worker để chứng minh `main` đã *thật sự* kết thúc trước khi worker tiếp tục; một ví dụ chỉ đặt `sleep(1000)` rồi đoán thứ tự từ màn hình sẽ phụ thuộc lịch chạy của OS.

## 4. Ví dụ B — Daemon có thể bị bỏ lại khi `main` kết thúc

Tạo **`DaemonDoesNotKeepJVM.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class DaemonDoesNotKeepJVM {
    public static void main(String[] args) {
        Thread background = new Thread(() -> {
            try {
                // Một công việc chờ vô hạn vì latch không được mở.
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "background");

        background.setDaemon(true); // trước start()
        background.start();

        System.out.println("main: returning");
    }
}
```

Chạy:

```bash
javac --release 17 DaemonDoesNotKeepJVM.java
java DaemonDoesNotKeepJVM
```

**Stdout**:

```text
main: returning
```

Trong chương trình chạy độc lập này, sau khi `main` kết thúc sẽ không còn non-daemon của ứng dụng; `background` là daemon dù đang đợi latch. JVM có thể đi tới shutdown mà không cần latch về 0.

Ví dụ cố tình đặt công việc daemon ở trạng thái chờ để kết quả không phụ thuộc “máy nhanh hay chậm”. Nếu thay chỗ đợi bằng việc ghi file/chuyển dữ liệu và hy vọng daemon luôn hoàn tất trước khi JVM thoát, đó là một lỗi về quản lý vòng đời. Không dùng daemon làm bảo đảm hoàn thành ghi log, lưu giao dịch, flush buffer hay giải phóng tài nguyên.

## 5. Ví dụ C — Cần kết quả thì `join()` để chờ chủ động

Cho dù công việc chạy trên daemon hay non-daemon, nếu `main` cần bảo đảm hoàn tất trước khi trả về, **đợi kết quả** một cách rõ ràng.

File **`WaitForTask.java`**:

```java
public class WaitForTask {
    public static void main(String[] args) throws InterruptedException {
        Thread background = new Thread(
                () -> System.out.println("task: completed"),
                "background"
        );
        background.setDaemon(true);
        background.start();

        background.join();
        System.out.println("main: completed");
    }
}
```

```bash
javac --release 17 WaitForTask.java
java WaitForTask
```

**Stdout**:

```text
task: completed
main: completed
```

`join()` khiến `main` chỉ in dòng cuối sau khi thread đã hoàn tất. Khi worker là daemon, chính `main` (non-daemon) vẫn còn sống trong lúc đợi, nên JVM không tự thoát sớm. Nếu worker bị kẹt mãi, `join()` không timeout cũng có thể đợi mãi; có thể dùng `join(milliseconds)` rồi kiểm tra `isAlive()` và thực hiện chính sách timeout/cancellation phù hợp. `join()` có thể ném `InterruptedException` và cần xử lý theo contract của chương trình.

### Điều `join()` không bảo đảm

- `join()` chỉ chờ luồng được chỉ định; không tự chờ tất cả luồng con, thread pool hay hoạt động I/O không gắn với luồng đó.
- Nếu luồng kết thúc vì exception, `join()` vẫn hoàn tất; cần kênh riêng để báo thành công/thất bại, chẳng hạn `Future.get()`.
- `Thread.interrupt()` yêu cầu phối hợp/hỗ trợ gián đoạn, **không** phải lệnh cưỡng bức kết thúc.
- Tránh tạo vòng chờ: luồng A `join()` B trong khi B lại `join()` A, sẽ không thể hoàn tất bình thường.

## 6. ExecutorService: một nguyên nhân thực tế khiến ứng dụng “đã in done nhưng chưa thoát”

Ví dụ thường gặp:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
executor.submit(() -> System.out.println("task done"));
System.out.println("main done");
// Thiếu executor.shutdown()
```

Đây chỉ là **đoạn minh họa lỗi**, không phải file độc lập. `Executors.newSingleThreadExecutor()` theo cách dùng mặc định tạo worker **non-daemon** khi cần để chạy task. Ngay cả khi task trả về và `main` kết thúc, executor vẫn có thể duy trì worker đang chờ job kế tiếp. JVM không tự thoát. Việc gọi `Future.get()` để đợi riêng task hoàn tất cũng **không thay thế** `executor.shutdown()`.

Cách đầy đủ cho **Java 17+** — file **`ExecutorLifecycle.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorLifecycle {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> result = executor.submit(() -> 6 * 7);
            System.out.println("result=" + result.get());
        } finally {
            stopExecutor(executor);
        }
    }

    private static void stopExecutor(ExecutorService executor) {
        executor.shutdown(); // không nhận thêm task; xử lý task đã nhận
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow(); // best-effort interrupt
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("executor: still running");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

```bash
javac --release 17 ExecutorLifecycle.java
java ExecutorLifecycle
```

**Stdout bình thường**:

```text
result=42
```

- `result.get()` chờ task trả số, đồng thời chuyển lỗi task thành `ExecutionException`. Nó không tự đóng executor.
- `shutdown()` từ chối task mới, vẫn xử lý những task đã submit; `awaitTermination()` đợi pool kết thúc đến hết timeout.
- `shutdownNow()` chỉ **cố gắng** dừng task đang chạy bằng interrupt và lấy ra các task đang chờ; task không hợp tác có thể tiếp tục sống. Vì vậy code còn kiểm tra lần nữa và ghi cảnh báo nếu không dừng được.
- Khi thread gọi shutdown đang bị interrupt, ví dụ bảo toàn interrupt flag sau yêu cầu hủy; ứng dụng thực tế phải quyết định chính sách riêng nếu timeout kéo dài.
- Với Java 17, không mặc định dùng `try (ExecutorService executor = ...)` theo cú pháp AutoCloseable; `ExecutorService` trong API Java 17 chưa có `close()`. Với release mới hơn, cần đọc API đúng phiên bản khi dùng cơ chế đóng mới.

Nếu một web server/listener được thiết kế để chạy liên tục, non-daemon giữ JVM sống là **hành vi đúng**. Vấn đề chỉ xuất hiện khi bài toán yêu cầu kết thúc mà không có đường dừng server/executor.

## 7. Điều gì thay đổi khi gọi `System.exit`?

Hai đường đi khác nhau:

### A. Kết thúc tự nhiên

`main` kết thúc → các non-daemon còn lại vẫn chạy → khi non-daemon cuối cùng chết, JVM bắt đầu shutdown → chạy các shutdown hook đã đăng ký → sau khi hook kết thúc, JVM kết thúc.

### B. Gọi `System.exit(status)` (hoặc `Runtime.getRuntime().exit(status)`)

JVM **bắt đầu quá trình shutdown** theo yêu cầu, kể cả khi vẫn có non-daemon đang chạy. Các shutdown hooks đã đăng ký được khởi chạy và có thể chạy đồng thời với những luồng khác; sau khi hooks xong, runtime tiến tới kết thúc. `status` là mã trạng thái yêu cầu trả cho môi trường gọi chương trình; `0` thường biểu thị kết thúc thành công theo quy ước hệ điều hành.

Do đó, `System.exit(0)` **không phải** phương án thay cho `join()` hoặc đóng executor. Nó không bảo đảm tất cả task đã hoàn thành, buffer đã được flush, hoặc `finally` của các luồng bị chấm dứt sẽ được chạy. Trong một server, thư viện hoặc test suite, việc tự gọi `System.exit` còn có thể kết thúc toàn bộ JVM ngoài ý muốn.

### Shutdown hooks liên quan thế nào?

Đăng ký một hook khi JVM còn hoạt động:

```java
Runtime.getRuntime().addShutdownHook(new Thread(
        () -> System.out.println("shutdown hook"),
        "shutdown-hook"
));
```

Đây là **đoạn trích minh họa**, không phải chương trình đầy đủ. Hook là một đối tượng `Thread` được đăng ký để JVM khởi chạy ở giai đoạn shutdown. Một hook **chưa start** không phải non-daemon worker giữ chương trình sống trước khi shutdown. Hooks có thể chạy **song song**, thứ tự thực thi không được bảo đảm; hook treo có thể làm quá trình shutdown không hoàn tất. Vì vậy:

- Dùng hook cho thao tác dọn dẹp cần thiết trong phạm vi thời gian hợp lý; tránh chờ vòng tròn hoặc phụ thuộc vào dịch vụ đang tự shutdown.
- Không dùng thứ tự output của hai hook để suy ra trình tự chắc chắn.
- Không kỳ vọng hook luôn chạy khi bị cưỡng bức dừng: `Runtime.halt()` bỏ qua shutdown sequence; lỗi native nghiêm trọng, process bị kill cưỡng bức hoặc mất điện cũng có thể bỏ qua hooks.
- Dù một hook có kết thúc, các luồng thường còn chạy khác không được JVM “join” tự động theo đường `System.exit`.

## 8. Từ Java 21: virtual threads luôn là daemon

**Phần này áp dụng Java 21+**, không thuộc public API Java 17. Trong Javadoc `Thread` Java 21, **virtual threads là daemon threads** và bản thân chúng không ngăn JVM bắt đầu shutdown. Không thể chuyển một virtual thread thành non-daemon bằng `setDaemon(false)`.

Ví dụ độc lập, file **`VirtualThreadLifetime.java`**:

```java
public class VirtualThreadLifetime {
    public static void main(String[] args) throws InterruptedException {
        Thread task = Thread.startVirtualThread(
                () -> System.out.println("virtual: completed")
        );

        task.join();
        System.out.println("main: completed");
    }
}
```

```bash
javac --release 21 VirtualThreadLifetime.java
java VirtualThreadLifetime
```

**Stdout**:

```text
virtual: completed
main: completed
```

`Thread.startVirtualThread` có từ Java 21. Nếu bỏ `task.join()`, chương trình có thể shutdown ngay khi `main` và những non-daemon khác kết thúc, khiến công việc của virtual thread chưa kịp hoàn tất. **Không “sửa” bằng cách đổi virtual thread thành non-daemon:** hãy tổ chức vòng đời tác vụ để đợi kết quả, có timeout và hủy khi cần.

Điều này làm quy tắc non-daemon đặc biệt quan trọng khi chuyển từ mô hình thread pool truyền thống sang virtual threads: API tạo task và cơ chế hoàn thành khác nhau, nhưng **trách nhiệm đợi các tác vụ thiết yếu vẫn thuộc ứng dụng**.

## 9. Kiểm tra khi chương trình không thoát

Khi terminal/CI vẫn chờ sau khi log `main completed`, kiểm tra có hệ thống:

1. **Có `System.exit`/`Runtime.halt` hay shutdown hook nào đã bắt đầu chưa?** Nếu có, đây là nhánh shutdown chủ động/hook, không chỉ câu chuyện `main`.
2. **Có non-daemon sống không?** Nhận diện tên, `Thread.isDaemon()` và `Thread.isAlive()`; thread còn `WAITING`, `TIMED_WAITING`, `BLOCKED` vẫn là luồng còn sống.
3. **Luồng đó đến từ đâu?** `new Thread`, `ExecutorService`/`ScheduledExecutorService`, server socket, I/O listener, scheduler, thư viện HTTP/DB, GUI/event loop hoặc callback tự tạo.
4. **Luồng đợi điều kiện nào?** `Lock`/monitor, `CountDownLatch`, `BlockingQueue.take()`, `Object.wait()`, `Thread.join()`, socket/accept hoặc task queue rỗng.
5. **Có đường dừng hợp lệ?** Dừng nhận tác vụ mới, đóng socket/listener, phát tín hiệu hủy, `shutdown()` executor, `awaitTermination()` hoặc chờ bằng `join()`, với timeout và chính sách xử lý sự cố.

Với một **HotSpot JDK** có các công cụ chẩn đoán tương ứng, có thể lấy thread dump bằng:

```bash
jcmd <PID> Thread.print
```

`<PID>` là ID tiến trình Java cần kiểm tra. Kết quả giúp xem danh sách luồng, tên, stack và trạng thái; tùy JDK/cách hiển thị, thông tin daemon và virtual threads có thể khác nhau. Đừng quyết định chỉ bằng chữ “RUNNABLE”: luồng non-daemon đang `WAITING` cũng đủ để chặn shutdown tự nhiên. Thread dump là ảnh chụp tại một thời điểm, có thể cần quan sát nhiều lần khi điều tra deadlock hoặc pool đang chờ.

**Lưu ý:** trạng thái của một thread là đặc điểm vòng đời của thread ấy, không phải trạng thái toàn JVM. Số thread thay đổi liên tục; không kết luận process đã/chưa exit chỉ từ log của `main`.

## 10. Các lỗi hiểu sai thường gặp

| Ngộ nhận | Sửa lại |
| --- | --- |
| “Cuối hàm `main` là cuối chương trình” | `main` kết thúc chỉ hoàn tất một luồng; những non-daemon khác có thể tiếp tục giữ tiến trình sống |
| “Có tham chiếu `Thread` thì JVM sẽ đợi” | Chỉ luồng **đã khởi chạy và còn sống** mới có ý nghĩa; object chưa start/đã chết không giữ JVM |
| “Luồng `WAITING` thì xem như đã dừng” | `WAITING` vẫn còn sống và non-daemon vẫn ngăn shutdown tự nhiên |
| “`daemon=true` là ưu tiên thấp hoặc auto cleanup” | Daemon chỉ liên quan quyền giữ JVM sống; công việc có thể bị cắt khi JVM kết thúc |
| “`setDaemon(true)` bất cứ lúc nào cũng được” | Với platform thread, phải gọi trước `start()` |
| “`Future.get()` là đóng executor” | `get()` đợi kết quả task; `shutdown()` mới yêu cầu pool chấm dứt |
| “`shutdownNow()` luôn dừng mọi worker” | Interrupt mang tính phối hợp/best effort; worker không hợp tác có thể vẫn chạy |
| “`System.exit(0)` luôn hoàn thành mọi dọn dẹp” | Nó khởi đầu shutdown, chỉ hooks có cơ chế chờ trong đường này; task khác không được đảm bảo |
| “Virtual thread tự giữ JVM sống như platform thread” | Java 21+ virtual threads luôn daemon |
| “Hook chắc chắn được gọi với mọi cách kill process” | Có những trường hợp terminate đột ngột mà hook không chạy |

## 11. Cách thiết kế vòng đời JVM rõ ràng

Một ứng dụng dạng batch/CLI nên có **điều kiện hoàn tất rõ ràng**: nhận công việc → chờ task cần thiết → thu lỗi → đóng executor/tài nguyên → trả về từ `main`. Một ứng dụng server nên có **điều kiện dừng rõ ràng**: yêu cầu shutdown → dừng nhận request → đợi các tác vụ còn lại trong giới hạn → đóng listener/executor → cho các non-daemon hoàn tất.

Sơ đồ quyết định ngắn:

```text
main() trả về
    |
    v
Còn non-daemon đã start và chưa kết thúc?
    | Có                     | Không
    v                        v
JVM tiếp tục sống      Bắt đầu shutdown
    |                        |
    v                        v
Worker xử lý/đợi       Chạy shutdown hooks
    |                        |
    v                        v
Non-daemon cuối chết   Hooks hoàn tất?
    |                        | Có
    +------> shutdown -------+----> JVM kết thúc
```

`System.exit(...)` là một đường riêng đi vào shutdown mà không cần đợi non-daemon cuối cùng chết; `Runtime.halt(...)` và một số sự cố bên ngoài không đi theo đường hook thông thường. Đừng dùng sơ đồ để suy ra rằng mọi hook luôn kết thúc: hook bị treo cũng có thể chặn shutdown.

### Checklist khi đọc hoặc review code

- Worker nào cần chạy đến hết? Có `join()`, `Future.get()`, completion coordination hoặc cách đồng bộ khác để bảo đảm?
- Tạo thread mới trong ngữ cảnh nào, daemon flag có được kiểm tra hoặc chủ động đặt trước `start()`?
- Executor/scheduler có đường `shutdown()` và chờ kết thúc không? Nếu có timeout thì chuyện gì xảy ra tiếp?
- Có thành phần chạy lâu dài như server, listener, event loop, GUI và cơ chế đóng chủ động không?
- Có chỗ nào gọi `System.exit` thay vì quản lý worker/tài nguyên không?
- Dùng JDK 17 hay 21+? Với virtual threads, luồng daemon không giữ JVM sống; đã có cơ chế chờ chưa?
- Shutdown hook có tránh block vô thời hạn, deadlock và phụ thuộc thứ tự hook khác không?

## Nguồn chuẩn để đối chiếu

- [JLS Java SE 17, `12.8 Program Exit](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.8): điều kiện kết thúc chương trình theo non-daemon và `System.exit`.
- [`Thread` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): daemon flag, `start()`, `join()`, trạng thái và kế thừa thuộc tính.
- [`Runtime` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt`, `addShutdownHook` và shutdown sequence.
- [`ExecutorService` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`.
- [`Thread` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): virtual threads luôn daemon; `Thread.startVirtualThread` có từ Java 21.

**Ghi nhớ:** `main` hết chỉ nói rằng công việc của luồng chính đã hết. JVM chỉ tự shutdown theo đường thông thường khi **không còn non-daemon sống**; nếu muốn ứng dụng kết thúc đúng và an toàn, hãy quản lý việc hoàn tất của các tác vụ và việc đóng tài nguyên một cách tường minh.
