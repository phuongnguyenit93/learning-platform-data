# Theo dõi tiến trình con với thời hạn và xử lý đầu ra trong Java 9+

**Chủ đề:** Thực hành tổng hợp Java 9. Bài học xây dựng cơ chế gọi một chương trình con, theo dõi trạng thái, thu thập stdout/stderr, giới hạn thời gian chạy, xử lý lỗi và thu hồi tài nguyên đúng cách. Sử dụng `ProcessBuilder`, `Process`, `ProcessHandle`/`onExit()` và API vẫn được hỗ trợ trên các JDK hiện hành. Ví dụ chính **biên dịch với Java 17** và chạy được trên Windows, Linux, macOS khi có JDK phù hợp.

> **Nguyên tắc:** Một tiến trình con có thể chặn vĩnh viễn nếu bạn **chỉ chờ `waitFor()` mà không đọc stdout/stderr**: pipe hệ điều hành có bộ đệm hữu hạn. Ngược lại, chỉ đọc `readAllBytes()` trên luồng gọi có thể bị kẹt vì tiến trình không bao giờ đóng output. Giải pháp thực tế: **khởi động bộ đọc output song song, đặt timeout cho tiến trình, hủy tiến trình khi quá hạn, chờ hủy hoàn tất và giới hạn dữ liệu giữ trong RAM**.

## 1. Khi nào cần quản lý subprocess?

Ứng dụng Java đôi khi cần thực thi tool bên ngoài như trình biên dịch, chương trình xử lý ảnh, trình chuyển đổi dữ liệu, trình kiểm thử CLI hoặc một Java worker khác. Lúc này hệ điều hành tạo một **tiến trình riêng**, có PID, bộ nhớ, environment, working directory và các luồng I/O riêng. Java không thể điều khiển nó như một method bình thường.

Các yêu cầu thường đi cùng nhau:

1. **Chạy đúng chương trình/đối số:** không ghép input người dùng thành shell command tùy tiện.
2. **Giám sát kết thúc:** biết tiến trình còn chạy hay đã thoát; lấy exit code sau khi kết thúc.
3. **Có thời hạn:** không để job treo vô hạn; phân biệt timeout với exit code khác 0.
4. **Thu stdout/stderr:** tránh pipe bị đầy, nhưng không đọc toàn bộ output vô hạn vào RAM.
5. **Dọn tài nguyên:** đóng stdin, đóng stream, dừng tác vụ đọc, chờ tiến trình bị hủy và cân nhắc các tiến trình con/cháu.
6. **Chẩn đoán:** giữ log output với kích thước và chính sách bảo mật hợp lý.

**Giới hạn quan trọng:** Một timeout chỉ áp dụng cho `waitFor(timeout, unit)` **không phải** tự động là thời hạn end-to-end cho khởi động, thu output, cleanup và cả những tiến trình cháu. Ứng dụng có SLA cứng cần áp dụng cùng một **deadline tổng thể** cho tất cả pha.

## 2. Mô hình tiến trình và ba luồng chuẩn

Từ góc nhìn Java parent:

```text
Java parent                    OS child process
    |                               |
    | ProcessBuilder.start()        |
    +------------------------------>|
    |                               |
    | process.getOutputStream() ----> stdin  (input đi VÀO child)
    | process.getInputStream() <----- stdout (output TỪ child)
    | process.getErrorStream() <----- stderr (diagnostics TỪ child)
    |                               |
    | waitFor(timeout)              | chạy, in log, có thể treo
    | onExit()                       |
    | destroy()/destroyForcibly() -->|
    |                               X
```

Tên accessor có thể gây nhầm:

- `Process.getOutputStream()` **ghi vào stdin** của child.
- `Process.getInputStream()` **đọc stdout** của child.
- `Process.getErrorStream()` **đọc stderr** của child.

Theo mặc định, `ProcessBuilder` nối cả ba luồng qua pipe. Nếu chương trình không cần nhập dữ liệu, hãy **đóng stdin** sớm bằng `process.getOutputStream().close()`, để child nhận EOF thay vì chờ input mãi.

**Không giả định các luồng là vô hạn.** Nếu child ghi nhiều dữ liệu trong khi parent chưa đọc, stdout hoặc stderr có thể đầy. Khi đó child bị chặn trên thao tác `write`, không bao giờ đạt đến `exit`; `waitFor()` phía parent cũng có thể kẹt.

## 3. Các API còn áp dụng trong Java hiện đại

| API | Nhiệm vụ | Lưu ý |
| --- | --- | --- |
| `new ProcessBuilder(program, arg1, ...)` | Cấu hình chương trình và danh sách đối số | Truyền mỗi argument riêng; không dùng shell nếu không cần. |
| `ProcessBuilder.start()` | Khởi chạy child, trả `Process` | Có thể ném `IOException` nếu program không tồn tại/không có quyền chạy. |
| `ProcessBuilder.redirectErrorStream(true)` | **Gộp stderr vào stdout** | Chỉ cần đọc một pipe; mất khả năng phân biệt hai loại output sau khi gộp. |
| `ProcessBuilder.redirectOutput(...)`, `redirectError(...)` | Chuyển output vào file/inherit | Có thể tránh tự tạo reader; đọc lưu ý khi gộp hai luồng. |
| `Process.waitFor(long, TimeUnit)` | Chờ kết thúc trong thời hạn | Trả `true` nếu đã kết thúc, `false` nếu hết thời gian; **không tự kill**. |
| `Process.exitValue()` | Đọc exit code | Gọi khi tiến trình đã kết thúc; nếu còn chạy ném `IllegalThreadStateException`. |
| `Process.isAlive()` | Quan sát trạng thái | Mang tính thời điểm; có race với việc tiến trình kết thúc. |
| `Process.destroy()` | Đề nghị kết thúc tiến trình | “Bình thường” hay “mạnh tay” phụ thuộc OS/implementation. |
| `Process.destroyForcibly()` | Yêu cầu buộc kết thúc | Không đảm bảo chết **ngay lập tức**; chờ lại sau khi gọi. |
| `Process.onExit()` | `CompletableFuture<Process>` hoàn tất khi child thoát | Hữu ích cho callback/async từ Java 9; kết thúc không đồng nghĩa exit code bằng 0. |
| `Process.pid()`/`toHandle()` | PID và `ProcessHandle` | PID có thể được hệ điều hành tái sử dụng về sau. |
| `ProcessHandle.Info` | Snapshot metadata process | `command()`, `arguments()`, `startInstant()`... có thể không có. |
| `ProcessHandle.children()`/`descendants()` | Snapshot các child/descendant handles | Không phải quản lý process tree nguyên tử. |

`ProcessBuilder.startPipeline(...)` cũng có từ Java 9, dùng cho chuỗi process kiểu pipeline; khi vận hành phải theo dõi từng `Process` và stderr của chúng. Bài này tập trung một child để quan sát chính xác timeout/output trước khi mở rộng.

## 4. Chiến lược thực thi an toàn

```text
[Chuẩn bị program + args]
           |
           v
[Start child] ---- lỗi ----> [Ghi nhận IOException]
           |
           v
[Đóng stdin không dùng; chạy collector stdout/stderr ngay]
           |
           v
[waitFor(timeout)]
      |             |
   true           false
      |             |
      v             v
[Đọc exit code]  [Đánh dấu TIMEOUT]
      |             |
      |          destroy()
      |             |
      |          waitFor(grace)
      |             |
      |          nếu còn sống: destroyForcibly() + waitFor(...)
      |             |
      +------+------+
             |
             v
[Chờ collector có giới hạn; thu output có giới hạn RAM]
             |
             v
[Đóng tài nguyên, ghi kết quả có trạng thái rõ ràng]
```

Kết quả cần phân biệt **ít nhất** ba trạng thái:

- **SUCCESS:** tiến trình kết thúc trong hạn **và** exit code là 0 **và** output phù hợp yêu cầu.
- **NON_ZERO_EXIT:** kết thúc trong hạn nhưng exit code khác 0; đây không phải timeout.
- **TIMEOUT:** hết hạn chờ, sau đó mới tiến hành dừng; exit code phát sinh do bị kill thường **phụ thuộc OS** và không được xem là exit code nghiệp vụ.

Ngoài ra còn có **START_FAILED**, **OUTPUT_FAILED**, **INTERRUPTED** hoặc **CLEANUP_FAILED**. Một chương trình con có thể trả 0 nhưng output không hợp lệ; khi dùng trong sản phẩm nên kiểm tra cả nội dung, không chỉ exit code.

## 5. Lab độc lập: parent Java theo dõi một child Java

Ví dụ tự chạy lại chính `ProcessMonitorDemo` ở chế độ child, vì vậy không cần lệnh `sleep`, `ping`, `cmd.exe` hay `sh` phụ thuộc hệ điều hành. Chương trình kiểm chứng hai tình huống:

- Child bình thường: in stdout và stderr rồi thoát trước thời hạn.
- Child chậm: đã in thông tin ban đầu rồi ngủ lâu hơn timeout; parent đánh dấu timeout, hủy và chờ kết thúc.

Các kỹ thuật trong ví dụ:

1. Chọn `java` đang chạy theo `java.home/bin`, tránh vô tình dùng JDK khác trong PATH.
2. Dùng `ProcessBuilder` với **danh sách đối số**.
3. Gộp stdout/stderr để chỉ cần **một** reader.
4. Reader chạy riêng bằng `ExecutorService`, **đọc cho đến EOF** nhưng chỉ giữ **4.096 byte đầu**, hạn chế RAM dù child tạo output dài.
5. Dùng `waitFor(timeout)` rồi `destroy`, nếu còn sống thì `destroyForcibly` và chờ lại.
6. Dùng `Future.get(timeout)` để không chờ vô hạn việc thu output.
7. Xử lý `InterruptedException` bằng cách yêu cầu dừng child, khôi phục trạng thái interrupt và truyền lỗi ra ngoài.

Tạo file `ProcessMonitorDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ProcessMonitorDemo {
    record Result(boolean finished, int exitCode, String output) {}

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("--child")) {
            System.out.println("OUT: started");
            System.err.println("ERR: diagnostic");
            System.out.flush();
            System.err.flush();
            Thread.sleep(Long.parseLong(args[1]));
            System.out.println("OUT: finished");
            return;
        }

        Result normal = runChild(0, 5000);
        Result slow = runChild(5000, 300);

        System.out.println("normal: " +
                (normal.finished() && normal.exitCode() == 0 ? "EXIT_0" : "FAILED"));
        System.out.println("normal-output-ok: " +
                (normal.output().contains("OUT: started")
                        && normal.output().contains("ERR: diagnostic")
                        && normal.output().contains("OUT: finished")));
        System.out.println("slow: " + (!slow.finished() ? "TIMEOUT" : "UNEXPECTED_EXIT"));
        System.out.println("slow-output-ok: " +
                (slow.output().contains("OUT: started")
                        && slow.output().contains("ERR: diagnostic")));
    }

    static Result runChild(long childSleepMillis, long timeoutMillis) throws Exception {
        String java = Path.of(System.getProperty("java.home"), "bin",
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java").toString();

        Process process = new ProcessBuilder(
                java, "-cp", System.getProperty("java.class.path"),
                ProcessMonitorDemo.class.getName(), "--child",
                Long.toString(childSleepMillis))
                .redirectErrorStream(true)
                .start();

        process.getOutputStream().close(); // Child không đọc stdin.
        ExecutorService readers = Executors.newSingleThreadExecutor();
        Future<String> output = readers.submit(
                () -> readBounded(process.getInputStream(), 4096));

        try {
            boolean finished = process.waitFor(timeoutMillis, TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroy();
                if (!process.waitFor(500, TimeUnit.MILLISECONDS)) {
                    process.destroyForcibly();
                    if (!process.waitFor(2, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Child still alive");
                    }
                }
            }
            String text = output.get(2, TimeUnit.SECONDS);
            return new Result(finished, process.exitValue(), text);
        } catch (InterruptedException ex) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw ex;
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
            }
            readers.shutdownNow();
        }
    }

    static String readBounded(InputStream input, int limit) throws IOException {
        try (InputStream in = input) {
            ByteArrayOutputStream kept = new ByteArrayOutputStream();
            byte[] buffer = new byte[1024];
            int count;
            while ((count = in.read(buffer)) != -1) {
                int allowed = Math.min(count, limit - kept.size());
                if (allowed > 0) {
                    kept.write(buffer, 0, allowed);
                }
            }
            return kept.toString(StandardCharsets.UTF_8);
        }
    }
}
```

Biên dịch và chạy từ thư mục có `ProcessMonitorDemo.java`:

```bash
javac --release 17 ProcessMonitorDemo.java
java ProcessMonitorDemo
```

**Stdout thực tế trên OpenJDK 24 (Windows), đã kiểm tra:**

```text
normal: EXIT_0
normal-output-ok: true
slow: TIMEOUT
slow-output-ok: true
```

Trong môi trường có tải CPU cực cao, quá trình khởi động JVM mới có thể cần hơn 300 ms; lúc đó child chậm có thể bị timeout **trước khi kịp in**, khiến `slow-output-ok` là `false`. Đây là **tính chất của deadline** chứ không phải lỗi syntax. Khi chạy CI trên máy chậm, điều chỉnh timeout cho phù hợp: ví dụ `normal` 15 giây, `slow` 1 giây và child ngủ 10 giây. Trong chương trình sản xuất phải thiết kế dựa trên latency/đảm bảo SLA thực tế, không dùng các ngưỡng lab để xử lý công việc quan trọng.

### Đọc kết quả và phạm vi đảm bảo của code

- `normal.finished() == true` nghĩa là child đã kết thúc trong thời gian `waitFor` cho phép; `exitCode() == 0` là điều kiện thành công theo quy ước của ví dụ.
- `slow.finished() == false` nghĩa là thời hạn chờ ban đầu đã hết; **sau đó** code vẫn cần dừng tiến trình và chờ dừng xong trước khi đọc `exitValue()`.
- `redirectErrorStream(true)` khiến `"ERR: diagnostic"` đi vào stream được đọc bởi `getInputStream()`. Không còn stream stderr độc lập để đọc.
- `readBounded(...)` **tiếp tục tiêu thụ hết pipe** ngay cả khi `kept` đã đầy 4.096 byte. Nó không lưu toàn bộ vào RAM, tránh làm child kẹt trên pipe đầy do bỏ đọc.
- Collector dùng `Future<String>` nên có thể gặp `ExecutionException`/`TimeoutException`; để đơn giản, demo truyền exception ra `main`. Code production nên giữ trạng thái `OUTPUT_FAILED` và log nguyên nhân phù hợp.
- Bản demo giữ **4.096 byte đầu** nhưng không trả cờ `truncated`; trong hệ thống thực nên thêm `bytesSeen`/`truncated` để người vận hành biết output đã bị cắt. Cắt theo số **byte** có thể chia giữa ký tự UTF-8 nhiều byte; nếu output có Unicode cần decoder streaming hoặc chính sách cắt tại ranh giới code point.
- `runChild` dừng mỗi **tiến trình được tạo trực tiếp**. Nếu child tự spawn tiến trình cháu, demo này **không** cam kết dừng cả nhóm; xem mục quản lý process tree.

**Các ngoại lệ cần xử lý thêm khi dùng production:** `IOException` lúc start/read; `InterruptedException` lúc wait; `ExecutionException` hoặc `TimeoutException` lúc nhận kết quả reader; tiến trình bị terminate cưỡng bức nhưng chưa rời OS ngay, hoặc output stream không đóng do process cháu kế thừa handle.

## 6. Vì sao không được đọc output sau khi `waitFor()` một cách tuần tự?

Mẫu dễ gây kẹt:

```java
// PHẢN VÍ DỤ: chỉ minh họa kiểu dùng có thể deadlock.
Process p = new ProcessBuilder("some-tool").start();
int exit = p.waitFor();           // Có thể chờ mãi vì stdout/stderr đầy.
byte[] out = p.getInputStream().readAllBytes();
```

Khi parent chờ child thoát mà không thu output, child có thể bị block trên write. Nếu tool vừa ghi stdout vừa ghi stderr, việc chỉ đọc **một** pipe cũng có thể kẹt ở pipe còn lại.

### Phương án A — gộp stdout và stderr

```java
Process p = new ProcessBuilder("tool", "--option")
        .redirectErrorStream(true)
        .start();
```

Sau đó đọc `p.getInputStream()` liên tục trên reader thread. Ưu điểm: đơn giản, tránh cần hai collector; nhược điểm: mất phân loại stdout/stderr và thứ tự xen kẽ giữa hai nguồn có thể không phản ánh chính xác thứ tự gọi `print` của child vì buffering.

**Chú ý:** khi `redirectErrorStream(true)`, `Process.getErrorStream()` là **null input stream** theo hợp đồng API, đọc sẽ trả EOF; đồng thời `redirectError(...)` cấu hình riêng sẽ bị bỏ qua khi tạo child.

### Phương án B — hai reader chạy đồng thời

Nếu cần phân biệt stdout và stderr, giữ mặc định `redirectErrorStream(false)`, dùng **hai** tác vụ đọc:

```java
// Đoạn minh họa bên trong method, process đã được khởi chạy.
ExecutorService io = Executors.newFixedThreadPool(2);
Future<String> stdout = io.submit(
        () -> readBounded(process.getInputStream(), 4096));
Future<String> stderr = io.submit(
        () -> readBounded(process.getErrorStream(), 4096));
```

`readBounded` ở đây là method đã định nghĩa trong `ProcessMonitorDemo`. Sau khi theo dõi/kết thúc process, lấy kết quả **có timeout**, xử lý exception và `shutdown` pool. Hai task phải được chạy đồng thời; dùng thread pool có **chỉ một worker** rồi đọc stdout xong mới đọc stderr là thiết kế có nguy cơ deadlock khi stderr đầy.

### Phương án C — redirect vào file

```java
// Đoạn minh họa, file paths cần được kiểm soát trước.
ProcessBuilder pb = new ProcessBuilder("tool", "--option");
pb.redirectOutput(ProcessBuilder.Redirect.to(
        java.nio.file.Path.of("child.stdout.log").toFile()));
pb.redirectError(ProcessBuilder.Redirect.to(
        java.nio.file.Path.of("child.stderr.log").toFile()));
Process p = pb.start();
```

Hữu ích khi output lớn và không muốn giữ trong RAM. `Redirect.to(file)` có thể ghi đè file; `Redirect.appendTo(file)` ghi nối. Lưu ý quyền ghi, quota đĩa, log rotation, file path không tin cậy và yêu cầu xóa dữ liệu nhạy cảm. Khi redirect khỏi pipe, `getInputStream()`/`getErrorStream()` không còn là nguồn dữ liệu thực để thu bằng reader.

**`inheritIO()`** là lựa chọn đơn giản cho CLI tương tác: stdin/stdout/stderr của child dùng cùng nguồn/đích với parent. Dễ dùng, nhưng không phù hợp khi cần capture độc lập hoặc kiểm soát kích thước log.

## 7. `ProcessHandle`: theo dõi không chặn từ Java 9

`ProcessHandle` và `Process.onExit()`/`ProcessHandle.onExit()` giúp truy cập thông tin tiến trình và theo dõi bất đồng bộ:

```java
// Đoạn minh họa, process là java.lang.Process còn sống.
ProcessHandle handle = process.toHandle();
long pid = handle.pid();

handle.info().command().ifPresent(cmd ->
        System.out.println("Executable: " + cmd));

java.util.concurrent.CompletableFuture<Process> done = process.onExit();
done.thenAccept(ended ->
        System.out.println("Exit code: " + ended.exitValue()));
```

Giải thích:

- `process.onExit()` trả `CompletableFuture<Process>` được hoàn tất **khi process kết thúc**, kể cả **exit code khác 0**. Đây không phải `CompletableFuture` hoàn tất đặc biệt khi process thất bại theo exit code; ứng dụng phải tự kiểm tra.
- `handle.onExit()` trả `CompletableFuture<ProcessHandle>`; `ProcessHandle` không trực tiếp cung cấp exit code. Khi bạn **đang giữ `Process`** do `ProcessBuilder.start()` trả về và cần exit code, `Process.onExit()` thường tiện hơn.
- `thenAccept` có thể chạy khi future hoàn tất; nếu muốn tách luồng thực thi callback khỏi các task khác, dùng biến thể async với executor rõ ràng.
- **Hủy future không hủy child:** `done.cancel(true)`, `future.orTimeout(...)`, hoặc timeout của `future.get(...)` **không tự động gọi** `destroy()` lên process. Khi quá hạn, logic quản lý phải quyết định kết thúc thực tế.
- Future hoàn tất khi **tiến trình thoát**, nhưng luồng stdout/stderr có thể vẫn còn dữ liệu buffered cần đọc. **`onExit()` không thay việc drain output**.
- Có thể thấy `process.isAlive() == false` **trước** khi callback `onExit` thực thi; đừng viết logic phụ thuộc các sự kiện này luôn xảy ra chính xác cùng thời điểm.

### Quan sát snapshot metadata

```java
// Minh họa bên trong một method có Process p.
ProcessHandle handle = p.toHandle();
ProcessHandle.Info info = handle.info();
info.command().ifPresent(System.out::println);
info.startInstant().ifPresent(System.out::println);
info.totalCpuDuration().ifPresent(System.out::println);
```

Những thuộc tính này là **snapshot**, trả bằng `Optional` vì hệ điều hành/permission có thể không cung cấp. Không dùng command line/arguments làm nguồn tin cậy tuyệt đối cho bảo mật; chúng có thể thiếu hoặc chứa secrets, cần lọc khi log.

### `children()` và `descendants()` không phải job control hoàn chỉnh

```java
// Minh họa: lấy snapshot process descendants khi parent còn sống.
java.util.List<ProcessHandle> descendants;
try (java.util.stream.Stream<ProcessHandle> children =
        process.toHandle().descendants()) {
    descendants = children.toList();
}
```

`descendants()` chỉ là **ảnh chụp tại một thời điểm**. Process có thể sinh thêm con hoặc kết thúc ngay sau đó; PID có thể được tái sử dụng. `process.destroyForcibly()` nhắm vào **tiến trình đó**, không phải bảo đảm tự động hủy tất cả descendants.

Với công cụ có thể tạo nhiều process độc lập (build tools, shell scripts, browser drivers), muốn timeout thực sự cho **cả job** phải sử dụng cơ chế quản lý process group/session, Windows Job Object, container/cgroup hoặc supervisor phù hợp OS. Một vòng lặp kill danh sách `descendants()` không thay thế cơ chế job control nguyên tử.

## 8. Timeout phải được hiểu như một ngân sách thời gian

`waitFor(5, TimeUnit.SECONDS)` tối đa là 5 giây **cho lần chờ đó**; thời gian khởi động process, lấy output, shutdown reader và dừng cưỡng bức có thể khiến toàn bộ request dài hơn.

Với job có deadline tổng thể, hãy đo thời gian bằng **đồng hồ đơn điệu**:

```java
// Minh họa khi bắt đầu toàn bộ job.
long startedAt = System.nanoTime();
long timeoutNanos = TimeUnit.SECONDS.toNanos(10);

// Trước mỗi pha có thể block:
long elapsed = System.nanoTime() - startedAt;
long remaining = Math.max(0L, timeoutNanos - elapsed);
if (remaining == 0L) {
    // Hết ngân sách: chuyển sang quy trình hủy/dọn tài nguyên.
}
```

Đây là đoạn minh họa, **chưa phải scheduler hoàn chỉnh**: nếu muốn cleanup có phần ngân sách riêng, xác định rõ nó có tính vào SLA hay không. `System.nanoTime()` phù hợp đo **khoảng thời gian**; không dùng `System.currentTimeMillis()` làm deadline tương đối, vì đồng hồ hệ thống có thể bị chỉnh.

Một timeout hợp lệ cần ít nhất:

- Giới hạn thời gian **chạy**; biết khi nào bắt đầu đo (trước start hay sau start).
- Giới hạn thời gian **graceful termination** sau khi quá hạn.
- Giới hạn thời gian **forced termination/reaping** và xử lý trường hợp vẫn còn sống.
- Giới hạn thời gian **đợi output collector** và chính sách xử lý output bị kẹt/thiếu.
- Nếu child có thể fork, giới hạn vòng đời của **cả nhóm process** qua cơ chế OS thích hợp.

**Không tạo một tác vụ `onExit().get()` vô hạn rồi kỳ vọng gọi `cancel(true)` sẽ tự giải phóng mọi tài nguyên.** Future và process là hai tài nguyên khác nhau.

## 9. Lỗi, interrupt và cleanup

### Phân biệt các lỗi

| Tình huống | Tín hiệu | Cách xử lý |
| --- | --- | --- |
| File thực thi không tồn tại/không cho phép chạy | `ProcessBuilder.start()` ném `IOException` | Kiểm tra đường dẫn, quyền, workdir; không retry bừa. |
| Child trả status khác 0 | `waitFor(...) == true`, `exitValue() != 0` | Báo `NON_ZERO_EXIT`; giữ phần stderr hữu ích. |
| Child chạy quá lâu | `waitFor(...) == false` | Đánh dấu `TIMEOUT`, `destroy`, grace, force, wait lại. |
| Thread chờ bị cancel/interrupted | `InterruptedException` | Dừng child, khôi phục interrupt, cleanup rõ. |
| Bộ thu output bị lỗi | `Future.get()` ném `ExecutionException` | Xem nguyên nhân `IOException`/charset/file permission; không coi là thành công. |
| Thu output vượt hạn | `TimeoutException` từ `Future.get(timeout, unit)` | Đánh dấu `OUTPUT_FAILED`, đóng/dừng tài nguyên và xem liệu có process cháu giữ pipe. |
| Buffer output đầy | Child có thể bị block khi write | Bắt đầu collector ngay; tiếp tục drain dù đã giới hạn số byte giữ. |
| Child tiếp tục chạy sau `destroyForcibly()` | `isAlive()` có thể vẫn đúng thoáng qua | Chờ lại và báo nếu không dừng được. |

Một số chi tiết cần giữ đúng khi viết code production:

- **Không nuốt `InterruptedException`** rồi coi job thành công. Khi bắt lỗi, yêu cầu cleanup và thường khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` trước khi truyền hoặc thoát.
- `destroy()` có thể mang nghĩa khác nhau trên Windows và Unix. Có thể xem `supportsNormalTermination()` nếu cần, nhưng vẫn phải thiết kế timeout và force-path.
- `exitValue()` chỉ dùng sau khi xác nhận process đã kết thúc; sau timeout nếu chưa kết thúc thì không đọc ngay.
- `readBounded` chỉ ngăn **giữ** output quá nhiều trong RAM, không ngăn child thực sự tạo lượng output khổng lồ làm tốn CPU/I/O. Có thể cần quota log, throttling hoặc giết child nếu vượt giới hạn output.
- Nếu process dừng mà reader vẫn chưa thấy EOF, có thể một process cháu đã thừa kế file descriptor/handle stdout/stderr. Khi đó chỉ dừng parent chưa chắc đủ.
- `shutdownNow()` **yêu cầu** ngắt thread; I/O native blocking không phải lúc nào cũng đáp ứng interrupt ngay. Cần quy trình đóng stream/kill process group nếu muốn bảo đảm thu hồi triệt để.
- Không đóng stdout/stderr từ thread khác trong lúc reader còn đang sử dụng trừ khi đang thực hiện một trình tự cleanup được thiết kế rõ.

## 10. Bảo mật khi gọi lệnh ngoài

`ProcessBuilder` giúp bạn truyền chương trình và đối số theo cấu trúc, nhưng **không tự giải quyết tất cả vấn đề security**.

### Đừng biến input không tin cậy thành shell command

```java
// ĐÚNG VỀ CẤU TRÚC ĐỐI SỐ: fileName là một argument.
new ProcessBuilder("tool", "--input", fileName).start();
```

Ngay cả khi dùng arguments riêng, vẫn cần **kiểm tra ngữ nghĩa giá trị**: đường dẫn có được phép đọc không, đối số có bắt đầu bằng `-` và bị tool hiểu nhầm thành option không, có được phép truy cập file/host đó không. Khi tool hỗ trợ `--` để kết thúc options, hãy dùng theo tài liệu tool.

```java
// DỄ RỦI RO: nếu userInput tham gia tạo chuỗi shell.
new ProcessBuilder("sh", "-c", "tool --input " + userInput).start();
```

Ở ví dụ thứ hai, shell phân tích lại toàn bộ chuỗi và có thể tạo lỗ hổng command injection. `ProcessBuilder` không tự escape an toàn cho chuỗi được giao qua `sh -c`/`cmd /c`. Trừ khi thực sự cần khả năng của shell và có escaping/validation theo nền tảng, hãy gọi binary trực tiếp.

### Những điểm phải kiểm soát thêm

- **Đường dẫn executable:** dùng đường dẫn tuyệt đối/được cấu hình tin cậy, tránh thực thi nhầm tool trong `PATH` bị sửa.
- **Working directory:** đặt `ProcessBuilder.directory(...)` khi cần; validate không cho thoát vùng dữ liệu được phép.
- **Environment:** `pb.environment()` mặc định nhận bản sao environment của parent. Giảm biến không cần thiết/không tin cậy; secrets đi qua environment có thể bị lộ theo quyền OS hoặc log.
- **Stdin/stdout/stderr:** không log token, mật khẩu, certificate, private key, PII hoặc toàn bộ output vô kiểm soát.
- **Resource quotas:** giới hạn CPU/memory/file descriptors/process count ở mức OS/container khi tool không đáng tin; Java timeout chỉ là một phần.
- **Concurrency:** giới hạn số subprocess chạy đồng thời bằng semaphore/queue/executor; quá nhiều process và reader threads có thể làm hệ thống cạn tài nguyên.

## 11. Cách kiểm thử và quan sát trong ứng dụng thật

Nên có các test độc lập cho:

1. **Thành công:** child thoát `0`, stdout/stderr được thu đầy đủ trong ngưỡng log.
2. **Lỗi exit:** child thoát mã khác `0`; không nhầm thành timeout.
3. **Hết thời hạn:** child chạy lâu, đánh dấu `TIMEOUT`, kiểm tra child không còn sống sau quy trình dừng.
4. **Nhiều output:** child ghi nhiều hơn pipe capacity **và** hơn giới hạn capture; không bị deadlock, memory capture vẫn bounded, có flag truncated.
5. **Hai luồng riêng:** child ghi nhiều vào **cả stdout và stderr**; hai collectors chạy song song.
6. **Interrupted:** thread chờ bị interrupt; child được dọn và trạng thái interrupt được giữ theo thiết kế.
7. **Child spawn descendant:** kiểm tra timeout của cả job, không để process cháu mồ côi.
8. **Lỗi khởi động:** binary sai/thiếu permission; không bắt đầu collector nếu start không thành công.
9. **Log Unicode:** output có ký tự UTF-8 dài, kiểm tra charset/giới hạn byte không gây giải mã sai.
10. **Resource leaks:** chạy nhiều job liên tục, kiểm tra không tăng vô hạn số thread, file handle hoặc child process.

### Thu thập metadata khi điều tra

Các trường hữu ích: job ID nội bộ, executable đã được sanitize, PID, thời điểm start/end, duration, exit code (nếu có), `timedOut`, bytes stdout/stderr, `truncated`, lý do cleanup và nơi lưu log. Dữ liệu `ProcessHandle.Info` không phải lúc nào cũng có; không coi trường thiếu là lỗi bảo mật hay trạng thái process bất thường.

**Không ghi tùy tiện toàn bộ command-line**: argument có thể chứa access token/password. Tạo allowlist các trường được phép log; che secrets theo chính sách.

### Bài tập

1. Sửa child trong lab để `System.exit(7)`. Điều gì phân biệt `NON_ZERO_EXIT` và `TIMEOUT`?
2. Cho child ghi 1 MB vào stdout. Tại sao `readBounded(..., 4096)` vẫn tránh deadlock? Thêm cờ `truncated` như thế nào?
3. Bỏ `redirectErrorStream(true)`, cho child ghi dữ liệu lớn vào cả stdout/stderr. Làm thế nào dùng hai reader thread độc lập?
4. Đổi `waitFor(300, MILLISECONDS)` thành `process.onExit().get(300, MILLISECONDS)`. Nếu `get` ném `TimeoutException`, phải làm gì **ngoài** xử lý future?
5. Một child tạo tiến trình cháu rồi thoát. Vì sao `ProcessHandle.descendants()` không cho phép bạn giả định đã kiểm soát toàn bộ job?
6. Vì sao log `exitValue` ngay sau `destroyForcibly()` có thể lỗi? Cần chờ sự kiện nào?
7. Nếu request API của bạn có deadline 2 giây, một lệnh `waitFor(2s)` cộng 500 ms graceful cleanup đã bảo đảm deadline end-to-end chưa?

**Định hướng:** Exit code khác 0 chỉ có nghĩa child đã thoát thất bại; timeout là vượt ngân sách. `readBounded` **tiếp tục đọc** sau khi bộ nhớ capture đầy. Timeout của `CompletableFuture` không giết process. Theo dõi cả process tree cần hỗ trợ OS; mỗi pha của job phải nằm trong ngân sách thời gian phù hợp.

## 12. Tài liệu chính thống còn áp dụng

- [Oracle Java SE 26 — `ProcessBuilder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): cấu hình program/args, stdin/stdout/stderr, redirect và pipeline.
- [Oracle Java SE 26 — `Process`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): `waitFor`, `onExit`, `destroy`, `destroyForcibly`, exit code và stream handling.
- [Oracle Java SE 26 — `ProcessHandle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html): PID, trạng thái, `Info`, `onExit`, children/descendants.
- [Oracle Java SE 17 — `Process`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): baseline tương thích cho ví dụ thực hành.
- [Oracle Java SE 17 — `ProcessBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): chạy child và xử lý output bằng API ổn định.
- [Oracle Java SE 26 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): xử lý bất đồng bộ; timeout/cancel future là cơ chế riêng với lifecycle tiến trình.

**Ghi nhớ:** Khi gọi subprocess, cần kiểm soát **cả tiến trình và các pipe**. Bắt đầu drain output trước khi chờ, phân biệt exit code với timeout, đừng để dữ liệu log chiếm hết RAM, và xem `onExit` là thông báo kết thúc — không phải bộ hẹn giờ tự kill. Với tool có process tree, bổ sung quản lý job ở mức hệ điều hành.
