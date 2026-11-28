# Thời gian chờ, interruption và chính sách dừng tiến trình

Khi Java khởi chạy một chương trình hệ điều hành, vòng đời của tiến trình con độc lập với vòng đời của thread đang chờ nó. `waitFor()` chỉ chờ tiến trình kết thúc; timeout không tự dừng tiến trình; interruption cũng không tự gửi tín hiệu kết thúc tới tiến trình con. Ứng dụng cần chọn rõ chính sách khi hết thời gian hoặc khi thread bị interrupt: tiếp tục chờ, yêu cầu dừng bình thường, dừng cưỡng bức, hay chủ động để tiến trình chạy nền.

Với mã Java hiện hành, hãy dùng `ProcessBuilder` để tạo tiến trình, `Process` để quản lý tiến trình do ứng dụng khởi chạy và `ProcessHandle` để quan sát/điều khiển tiến trình ở cấp hệ điều hành. `Process.waitFor(Duration)` có từ JDK 24; `Process` triển khai `AutoCloseable` từ JDK 26, cho phép quản lý tài nguyên bằng try-with-resources. Các API này tiếp tục có trong JDK 27 và không phải preview hay incubator.

## 1. Tạo tiến trình và chờ kết thúc

`ProcessBuilder.start()` là cách hiện hành để tạo một tiến trình. Mỗi đối số command nên là một phần tử riêng; tránh ghép toàn bộ lệnh thành một chuỗi shell tùy tiện.

```java
import java.io.IOException;

Process process = new ProcessBuilder("java", "-version").start();
int exitCode = process.waitFor();

if (exitCode == 0) {
    System.out.println("Process completed successfully");
} else {
    System.err.println("Process exited with code " + exitCode);
}
```

Các method chờ thường dùng:

| API | Kết quả | Khi dùng |
| --- | --- | --- |
| `waitFor()` | Trả exit code sau khi tiến trình kết thúc | Cần chờ vô thời hạn |
| `waitFor(long, TimeUnit)` | `true` nếu tiến trình kết thúc trong thời hạn; `false` nếu hết giờ | Dự án cần tương thích JDK 8+ |
| `waitFor(Duration)` | `true` nếu tiến trình kết thúc trong thời hạn; `false` nếu hết giờ | Cách viết gọn trên JDK 24+ |
| `onExit()` | `CompletableFuture<Process>` hoàn tất khi tiến trình kết thúc | Cần callback hoặc pipeline bất đồng bộ |
| `exitValue()` | Exit code hiện tại | Chỉ gọi sau khi tiến trình đã kết thúc |

Theo quy ước phổ biến, exit code `0` biểu thị thành công và giá trị khác `0` biểu thị lỗi. Đây là quy ước của chương trình con; ý nghĩa cụ thể của từng mã phụ thuộc chương trình được khởi chạy.

`exitValue()` ném `IllegalThreadStateException` nếu tiến trình vẫn đang chạy. Nếu cần chờ có giới hạn, hãy dùng `waitFor(Duration)` rồi chỉ đọc exit code khi method trả `true`.

## 2. Timeout chỉ kết thúc việc chờ

Ví dụ:

```java
boolean finished = process.waitFor(Duration.ofSeconds(10));

if (finished) {
    System.out.println("Exit code: " + process.exitValue());
} else {
    System.out.println("Deadline elapsed; process is still running");
}
```

Nếu trả về `false`, thread gọi được giải phóng nhưng tiến trình con vẫn tiếp tục chạy. `waitFor(Duration)` không tự gọi `destroy()` hoặc `destroyForcibly()`.

Điều này quan trọng khi timeout được dùng làm deadline nghiệp vụ. Sau khi hết thời gian, ứng dụng phải tự quyết định:

- Tiếp tục theo dõi tiến trình nếu công việc vẫn có giá trị.
- Gửi yêu cầu dừng bình thường và chờ thêm một khoảng grace period.
- Dừng cưỡng bức nếu tiến trình không thoát trong grace period.
- Chuyển quyền quản lý tiến trình cho một service manager nếu nó được thiết kế để chạy độc lập.

Không dùng `isAlive()` làm cơ chế chờ bận trong vòng lặp. `waitFor(Duration)` hoặc `onExit()` diễn đạt mục đích rõ hơn và tránh polling do ứng dụng tự viết.

## 3. Interruption không tự dừng tiến trình con

`waitFor()` và các overload timeout ném `InterruptedException` khi thread đang chờ bị interrupt. Exception kết thúc thao tác chờ; bản thân tiến trình con không bị dừng bởi sự kiện đó.

Ví dụ:

```java
try {
    int exitCode = process.waitFor();
    System.out.println("Exit code: " + exitCode);
} catch (InterruptedException e) {
    // Thread ngừng chờ; process vẫn có thể đang chạy.
    throw e;
}
```

Khi `InterruptedException` được ném, trạng thái interrupt của thread bị xóa. Nếu tầng hiện tại có thể truyền exception lên, thường nên truyền tiếp để caller quyết định cách xử lý. Nếu bắt exception và không truyền tiếp, hãy khôi phục trạng thái bằng `Thread.currentThread().interrupt()`.

Trước khi rời method, cần có chính sách rõ ràng cho tiến trình con. Nếu tiến trình phải dừng cùng công việc của thread cha, hãy gửi yêu cầu dừng hoặc hủy tiến trình trong nhánh xử lý interruption. Nếu cố ý để tiến trình chạy tiếp, hãy giữ một thành phần khác chịu trách nhiệm giám sát và thu hồi nó.

## 4. `destroy()` và `destroyForcibly()` khác nhau thế nào?

`Process.destroy()` yêu cầu hệ điều hành kết thúc tiến trình. Hành vi có bình thường/graceful hay không phụ thuộc implementation và nền tảng. Trên một số nền tảng, thao tác này có thể kết thúc tiến trình ngay.

`supportsNormalTermination()` cho biết implementation của `destroy()` có hỗ trợ kết thúc bình thường hay không:

```java
if (process.supportsNormalTermination()) {
    process.destroy(); // Yêu cầu dừng bình thường trên implementation hỗ trợ
} else {
    process.destroyForcibly(); // Implementation không có normal termination
}
```

`destroyForcibly()` yêu cầu dừng cưỡng bức. Với tiến trình do `ProcessBuilder.start()` tạo, implementation phải thực hiện việc kết thúc cưỡng bức. Tuy nhiên, tiến trình có thể vẫn được quan sát là còn sống trong một khoảng ngắn sau lời gọi; cần chờ bằng `waitFor()` hoặc `onExit()` để xác nhận.

| Method | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `destroy()` | Yêu cầu kết thúc tiến trình | Mức độ graceful phụ thuộc OS/implementation |
| `destroyForcibly()` | Yêu cầu kết thúc cưỡng bức | Không bảo đảm tiến trình biến mất tức thì |
| `supportsNormalTermination()` | Kiểm tra khả năng normal termination của `destroy()` | Có thể khác giữa Windows, Linux, macOS và implementation |
| `waitFor()` | Chờ tiến trình thực sự kết thúc | Dùng sau destroy để xác nhận |

Đừng giả định `destroy()` luôn tương đương SIGTERM hoặc luôn chạy shutdown hook của chương trình con. Java API để implementation và hệ điều hành quyết định cách gửi yêu cầu kết thúc.

## 5. Chính sách ba bước: deadline, graceful stop, force stop

Một chính sách thường dùng cho tiến trình ngắn hạn là:

1. Chờ tiến trình hoàn tất trong thời hạn nghiệp vụ.
2. Nếu hết thời gian, gọi `destroy()` và chờ thêm grace period.
3. Nếu vẫn chưa kết thúc, gọi `destroyForcibly()` rồi chờ kết thúc.

Ví dụ hoàn chỉnh trên JDK 26+:

```java
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.Objects;

record ProcessResult(boolean timedOut, int exitCode) {}

static ProcessResult runWithPolicy(
        List<String> command,
        Duration timeout,
        Duration gracePeriod
) throws IOException, InterruptedException {

    Objects.requireNonNull(command);
    Objects.requireNonNull(timeout);
    Objects.requireNonNull(gracePeriod);

    if (timeout.isNegative() || gracePeriod.isNegative()) {
        throw new IllegalArgumentException("Durations must not be negative");
    }

    ProcessBuilder builder = new ProcessBuilder(command)
            .redirectOutput(ProcessBuilder.Redirect.DISCARD)
            .redirectError(ProcessBuilder.Redirect.DISCARD);

    try (Process process = builder.start()) {
        try {
            if (process.waitFor(timeout)) {
                return new ProcessResult(false, process.exitValue());
            }

            // Hết deadline: yêu cầu kết thúc bình thường nếu nền tảng hỗ trợ.
            process.destroy();

            if (!process.waitFor(gracePeriod)) {
                // Hết grace period: yêu cầu dừng cưỡng bức rồi xác nhận.
                process.destroyForcibly();
                process.waitFor();
            }

            return new ProcessResult(true, process.exitValue());
        } catch (InterruptedException e) {
            // Chính sách ở đây: interruption hủy tiến trình con.
            process.destroyForcibly();
            throw e;
        }
    }
}
```

`ProcessResult.timedOut` cho biết deadline ban đầu đã hết, kể cả khi tiến trình sau đó thoát bình thường trong grace period. `exitCode` cho biết mã thoát cuối cùng.

Ví dụ dùng `Redirect.DISCARD` để không tạo pipe stdout/stderr mà chương trình cha không đọc. Nếu cần lưu log, thay bằng `redirectOutput(File)` và `redirectError(File)`. Nếu cần capture output trong Java, phải đọc stdout và stderr đồng thời hoặc gộp stderr vào stdout bằng `redirectErrorStream(true)`; không chờ tiến trình trước khi tiêu thụ pipe có thể làm đầy buffer và gây deadlock.

Trong nhánh interruption, code gọi `destroyForcibly()` rồi truyền tiếp exception. `try-with-resources` gọi `Process.close()` để đóng stream và chờ tiến trình kết thúc. Trên JDK 26+, nếu chính `close()` bị interrupt trong lúc chờ, nó tiếp tục dừng cưỡng bức và chờ process exit, sau đó khôi phục trạng thái interrupt.

## 6. `Process.close()` và try-with-resources từ JDK 26

Từ JDK 26, `Process` triển khai `AutoCloseable`. Khi `close()` được gọi, Java:

1. Đóng các reader/writer và stream của tiến trình.
2. Chờ tiến trình kết thúc.
3. Nếu thread bị interrupt trong lúc chờ, tiến trình bị dừng cưỡng bức; `close()` tiếp tục chờ đến khi tiến trình kết thúc rồi khôi phục trạng thái interrupt.

Ví dụ:

```java
try (Process process = new ProcessBuilder("my-command", "--version")
        .redirectErrorStream(true)
        .start()) {

    try (var reader = process.inputReader()) {
        reader.lines().forEach(System.out::println);
    }

    int exitCode = process.waitFor();
    if (exitCode != 0) {
        throw new IllegalStateException("Command failed: " + exitCode);
    }
}
```

`close()` giúp thu hồi stream và chờ process; nó không thay thế deadline/grace-period policy. Nếu tiến trình không thoát khi stdin bị đóng, `close()` có thể tiếp tục chờ. Hãy gọi `destroy()`/`destroyForcibly()` theo chính sách của ứng dụng trước khi đóng nếu cần bảo đảm có yêu cầu dừng.

Nếu exit code hoặc output quan trọng, hãy đọc output và chờ tiến trình trước khi `close()`. `close()` bỏ phần nội dung của stdout/stderr chưa được đọc. Dữ liệu output cần được tiêu thụ trước khi đóng resource.

## 7. `onExit()` cho xử lý bất đồng bộ

`Process.onExit()` trả về `CompletableFuture<Process>`. Có thể đăng ký callback để xử lý khi tiến trình kết thúc mà không block thread hiện tại:

```java
Process process = new ProcessBuilder("my-command", "--version").start();

process.onExit().thenAcceptAsync(exited -> {
    int exitCode = exited.exitValue();
    System.out.println("PID " + exited.pid() + " exited with " + exitCode);
}, callbackExecutor);
```

Future hoàn tất khi process kết thúc, bất kể exit code là `0` hay khác `0`. Nếu cần biết thành công hay thất bại, kiểm tra `exitValue()` trong callback.

Hủy future không hủy tiến trình:

```java
var exitFuture = process.onExit();
exitFuture.cancel(true); // Chỉ hủy việc theo dõi qua future
// Process vẫn có thể đang chạy.
```

Nếu cần dừng process, phải gọi `destroy()` hoặc `destroyForcibly()` trên `Process`/`ProcessHandle`. Tương tự, `exitFuture.get(timeout, unit)` chỉ giới hạn thời gian chờ future; hết giờ không tự dừng tiến trình.

## 8. Process và ProcessHandle: quản lý một tiến trình hay cả cây tiến trình

`Process` đại diện tiến trình được tạo bởi `ProcessBuilder.start()` hoặc `Runtime.exec(...)`, đồng thời cung cấp stream để giao tiếp với tiến trình đó. `ProcessHandle` đại diện một tiến trình hệ điều hành, cho phép xem PID, trạng thái, thông tin và yêu cầu kết thúc.

```java
Process process = new ProcessBuilder("my-command").start();
ProcessHandle handle = process.toHandle();

System.out.println("PID: " + handle.pid());
System.out.println("Alive: " + handle.isAlive());
System.out.println("Command: " + handle.info().command().orElse("unknown"));
```

`ProcessHandle` cũng có thể lấy từ PID bằng `ProcessHandle.of(pid)`, nhưng PID có thể được hệ điều hành tái sử dụng. Không nên lưu PID rồi mặc định rằng nó luôn đại diện cùng một process trong tương lai. `ProcessHandle` là value-based; không dùng instance làm monitor đồng bộ bằng `synchronized`.

Một process có thể tạo child process hoặc grandchild process. `process.destroy()` điều khiển process đại diện bởi `Process`; không nên mặc định rằng toàn bộ descendants cũng bị dừng. Có thể lấy snapshot cây con bằng:

```java
var descendants = process.descendants().toList();

// Yêu cầu các tiến trình con trong snapshot dừng trước.
descendants.forEach(ProcessHandle::destroy);
process.destroy();
```

Nếu hết grace period, có thể gửi yêu cầu force stop tới snapshot đó:

```java
descendants.forEach(ProcessHandle::destroyForcibly);
process.destroyForcibly();
```

`children()` và `descendants()` trả về snapshot tại thời điểm truy vấn. Tiến trình có thể sinh thêm child hoặc kết thúc ngay sau khi snapshot được tạo; vì vậy, đoạn code trên là best-effort, không phải giao dịch nguyên tử bảo đảm dừng mọi hậu duệ. Nếu cần kiểm soát cây tiến trình nghiêm ngặt, hãy dùng cơ chế của hệ điều hành như process group/session trên Unix hoặc Job Object trên Windows, hay giao cho container/service manager quản lý.

## 9. Tránh deadlock khi đọc stdout và stderr

Mặc định, stdout và stderr của child process được nối với hai pipe. Hệ điều hành chỉ cung cấp buffer hữu hạn. Nếu chương trình con ghi nhiều dữ liệu vào một pipe nhưng Java không đọc, buffer có thể đầy và child bị block khi ghi. Nếu Java đồng thời đang `waitFor()`, cả hai phía có thể chờ nhau vô thời hạn.

Các cách xử lý:

- Dùng `redirectOutput()`/`redirectError()` để ghi trực tiếp ra file.
- Dùng `Redirect.DISCARD` nếu không cần nội dung.
- Dùng `redirectErrorStream(true)` để gộp stderr vào stdout rồi đọc một stream.
- Nếu phải giữ stdout và stderr riêng, đọc cả hai đồng thời bằng hai task/virtual thread và quản lý vòng đời reader.

Không gọi cả `getInputStream()` và `inputReader()` cho cùng stdout; reader đã buffer dữ liệu từ stream và hai cách đọc sẽ cạnh tranh, làm dữ liệu khó dự đoán. Quy tắc tương tự áp dụng cho `getErrorStream()` và `errorReader()`.

## 10. Shutdown hook của JVM không thay thế quản lý process

`Runtime.addShutdownHook()` đăng ký công việc chạy khi chính JVM bắt đầu shutdown sequence, ví dụ do `System.exit()` hoặc tín hiệu bên ngoài. Shutdown hooks chạy đồng thời và thứ tự không được bảo đảm. Hook nên ngắn, thread-safe và không chờ vô hạn.

Một ứng dụng có thể đăng ký hook để yêu cầu child process dừng khi JVM thoát, nhưng hook vẫn cần timeout và force-stop policy. Nếu hook treo, JVM có thể không hoàn tất shutdown sequence. `Runtime.halt()` kết thúc JVM mà không chạy shutdown hooks; khi JVM bị dừng cưỡng bức, `finally` và try-with-resources cũng không được bảo đảm chạy.

Do đó, quản lý child process ngay trong component sở hữu nó vẫn là cách chính. Shutdown hook chỉ là lớp bảo vệ bổ sung cho trường hợp JVM shutdown bình thường.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `waitFor(Duration)` trả `false` nhưng process vẫn chạy | Timeout chỉ kết thúc việc chờ | Gọi `destroy()` rồi chờ grace period; sau đó `destroyForcibly()` nếu cần |
| Thread bị interrupt nhưng child vẫn chạy | `InterruptedException` không tự dừng process | Chọn chính sách hủy child trong catch hoặc chuyển quyền quản lý rõ ràng |
| `exitValue()` ném `IllegalThreadStateException` | Đọc exit code khi process chưa kết thúc | Chờ `waitFor()`/`onExit()` hoàn tất trước |
| `onExit().cancel(true)` nhưng child vẫn chạy | Cancel chỉ tác động future theo dõi | Gọi `destroy()`/`destroyForcibly()` trên process |
| Ứng dụng treo khi đọc output | Pipe stdout/stderr đầy hoặc chỉ một stream được đọc | Redirect, gộp stream hoặc đọc đồng thời |
| `destroy()` không kết thúc process theo cách mong đợi | Hành vi phụ thuộc OS/implementation | Kiểm tra `supportsNormalTermination()` và dùng force stop sau grace period |
| Child process còn sống sau khi parent thoát | Chỉ dừng process gốc, descendants có lifecycle riêng | Dùng `ProcessHandle.descendants()` như best-effort hoặc quản lý process group/job object |
| JVM treo khi shutdown | Shutdown hook chờ vô hạn hoặc child không thoát | Giữ hook ngắn, có deadline và force-stop policy |

## 12. Chọn chính sách theo loại công việc

| Loại tiến trình | Chính sách phù hợp |
| --- | --- |
| Lệnh ngắn, kết quả cần ngay | `waitFor(Duration)` với deadline; đọc exit code sau khi hoàn tất |
| Lệnh có thể treo hoặc phụ thuộc bên ngoài | Deadline → `destroy()` → grace period → `destroyForcibly()` |
| Tiến trình chạy dài, giám sát bất đồng bộ | `onExit()` để nhận callback; giữ component quản lý process và stream |
| Tiến trình tạo child process | Theo dõi `ProcessHandle.descendants()` và dùng OS-level process group/job object khi cần bảo đảm cây tiến trình |
| Tương tác qua stdin/stdout | Đóng stdin khi gửi xong, đọc stdout/stderr đồng thời, sau đó chờ exit |
| Service child phải dừng cùng JVM | Quản lý lifecycle ngay trong service; shutdown hook chỉ hỗ trợ cleanup có deadline |

## Ghi nhớ

- Dùng `ProcessBuilder` để tạo process; tránh `Runtime.exec(String)` đã deprecated vì dễ phân tách lệnh sai.
- `waitFor(Duration)` có từ JDK 24 và chỉ trả `false` khi hết thời gian chờ; nó không tự dừng process.
- `InterruptedException` dừng việc chờ, không tự dừng child process.
- `destroy()` phụ thuộc nền tảng; `destroyForcibly()` cũng có thể cần thời gian để process thực sự kết thúc.
- Chính sách phổ biến: deadline → graceful request → grace period → force stop → xác nhận exit.
- `Process.close()` triển khai `AutoCloseable` từ JDK 26; đóng stream và chờ process, nếu close bị interrupt khi chờ thì force stop và tiếp tục chờ.
- `onExit()` hoàn tất bất kể exit code; cancel future không dừng process.
- Pipe stdout/stderr có buffer hữu hạn; phải redirect hoặc đọc stream đồng thời.
- `ProcessHandle.descendants()` là snapshot, không bảo đảm quản lý nguyên tử toàn bộ process tree.
- Shutdown hook là cleanup bổ sung cho JVM shutdown bình thường, không thay thế quản lý child process.

## Tài liệu tham khảo

- [Process, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html) — `waitFor(Duration)`, `onExit`, `destroy`, `destroyForcibly` và `close()` từ JDK 26.
- [Process, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Process.html) — xác nhận API và hành vi process lifecycle trên JDK 27.
- [ProcessBuilder, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html) — tạo process, command arguments và redirect I/O.
- [ProcessHandle, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html) — PID, children, descendants, onExit và điều khiển process.
- [Handling Processes When They Terminate with the onExit Method](https://docs.oracle.com/en/java/javase/26/core/managing-processes-asynchronously-onexit-method.html) — xử lý process completion bằng `CompletableFuture`.
- [Runtime, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html) — shutdown sequence, shutdown hooks, `exit` và `halt`.
