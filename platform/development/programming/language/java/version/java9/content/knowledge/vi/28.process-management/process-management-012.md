# Quản lý thời hạn chờ cùng vòng đời tiến trình con

Khi ứng dụng Java khởi chạy một tiến trình con bằng `ProcessBuilder`, tiến trình đó có vòng đời độc lập với luồng Java đang quản lý nó. Tiến trình có thể chạy lâu hơn dự kiến, chờ input, bị treo khi ghi output hoặc tiếp tục tồn tại sau khi ứng dụng cha đã hết kiên nhẫn chờ.

Quản lý tiến trình an toàn cần phối hợp ba việc: **đặt thời hạn chờ**, **quyết định cách yêu cầu dừng**, và **xác nhận tiến trình thực sự kết thúc**. Java cung cấp `Process.waitFor(timeout, unit)`, `destroy()`, `destroyForcibly()`, `isAlive()` và từ Java 9 có `Process.onExit()` cùng `ProcessHandle` để thực hiện các bước đó.

Timeout chỉ cho biết thời gian chờ đã hết. Nó không tự động dừng tiến trình. Sau khi hết hạn, ứng dụng phải quyết định có tiếp tục chờ, yêu cầu dừng nhẹ, dừng cưỡng bức hay để tiến trình chạy nền theo chính sách của hệ thống.

## Mục tiêu

- Hiểu các trạng thái chính trong vòng đời một tiến trình con.
- Dùng `waitFor(timeout, unit)` để giới hạn thời gian chờ.
- Kết hợp `Process.onExit()` với `CompletableFuture` để nhận thông báo kết thúc bất đồng bộ.
- Phân biệt timeout của thao tác chờ với việc chấm dứt tiến trình.
- Thực hiện quy trình dừng nhẹ, chờ grace period và dừng cưỡng bức khi cần.
- Quản lý stdout, stderr, stdin và tài nguyên liên quan để tránh deadlock.
- Xử lý tiến trình con cháu bằng `ProcessHandle` khi ứng dụng tạo process tree.
- Bảo đảm cleanup khi có lỗi hoặc luồng quản lý bị interrupt.

## 1. Vòng đời cơ bản của Process

`ProcessBuilder.start()` tạo tiến trình hệ điều hành và trả về một đối tượng `Process`. Từ thời điểm đó, tiến trình có thể đang chạy độc lập với luồng gọi.

| Trạng thái | Ý nghĩa | API hữu ích |
| --- | --- | --- |
| Đã khởi chạy | `start()` thành công và hệ điều hành đã tạo tiến trình | `ProcessBuilder.start()` |
| Đang chạy | Tiến trình chưa kết thúc | `isAlive()` trả `true` |
| Đã được yêu cầu dừng | Ứng dụng gọi `destroy()` hoặc `destroyForcibly()` | Kiểm tra tiếp bằng `isAlive()` hoặc `waitFor()` |
| Đã kết thúc | Tiến trình không còn chạy; mã thoát có thể được đọc | `waitFor()`, `exitValue()`, `onExit()` |

`Process` là handle để điều khiển và quan sát tiến trình. Đóng một stream của `Process` không đồng nghĩa với việc chấm dứt tiến trình; ngược lại, tiến trình kết thúc cũng không thay thế trách nhiệm đóng các stream mà ứng dụng đang giữ.

### 1.1. Mã thoát chỉ có sau khi kết thúc

`exitValue()` trả mã thoát của tiến trình. Nếu tiến trình vẫn đang chạy, phương thức ném `IllegalThreadStateException`.

~~~java
if (!process.isAlive()) {
    int code = process.exitValue();
    System.out.println("exit code: " + code);
}
~~~

Mã `0` thường được quy ước là thành công và mã khác `0` là trạng thái khác hoặc lỗi, nhưng ý nghĩa chính xác phụ thuộc vào chương trình con. Không nên gán ý nghĩa nghiệp vụ chung cho mọi mã thoát nếu lệnh con có quy ước riêng.

## 2. Đặt giới hạn thời gian với waitFor

`Process.waitFor()` không tham số chặn luồng gọi cho đến khi tiến trình kết thúc. Overload có timeout cho phép giới hạn thời gian chờ:

~~~java
boolean finished = process.waitFor(5, TimeUnit.SECONDS);
if (finished) {
    System.out.println("exit code: " + process.exitValue());
} else {
    System.out.println("deadline reached");
}
~~~

Kết quả:

- `true`: tiến trình đã kết thúc trước khi thời hạn chờ hết.
- `false`: thời hạn chờ hết mà tiến trình vẫn chưa kết thúc.

**Khi trả về `false`, tiến trình vẫn đang chạy.** `waitFor(timeout, unit)` chỉ dừng việc chờ của luồng gọi; nó không gọi `destroy()` và không gửi tín hiệu chấm dứt tới hệ điều hành.

### 2.1. Timeout cho một thao tác và deadline cho toàn bộ công việc

Nếu một quy trình có nhiều bước, đặt timeout đầy đủ cho từng bước có thể khiến tổng thời gian vượt xa giới hạn mong muốn. Ví dụ, ba bước mỗi bước chờ tối đa 10 giây có thể tiêu tốn gần 30 giây.

Để giữ một ngân sách thời gian chung, có thể tính deadline bằng `System.nanoTime()` và truyền thời gian còn lại cho từng thao tác:

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);

long remaining = deadline - System.nanoTime();
if (remaining > 0) {
    boolean finished = process.waitFor(remaining, TimeUnit.NANOSECONDS);
    // Xử lý finished theo chính sách của ứng dụng.
}
~~~

`System.nanoTime()` phù hợp để đo khoảng thời gian vì không phụ thuộc đồng hồ ngày giờ của hệ thống. Khi có nhiều bước chờ, hãy tính lại thời gian còn lại thay vì đặt lại toàn bộ timeout ở mỗi bước.

### 2.2. Chọn đơn vị thời gian rõ ràng

`TimeUnit` giúp biểu đạt ý định mà không phải tự đổi mili giây hoặc nano giây:

- `TimeUnit.MILLISECONDS` cho timeout ngắn ở mức mili giây.
- `TimeUnit.SECONDS` hoặc `MINUTES` cho giới hạn dễ đọc.
- `TimeUnit.NANOSECONDS` khi dùng deadline được tính bằng `System.nanoTime()`.

Tránh nhân/chia số nguyên tùy tiện khi đổi đơn vị vì phép tính có thể tràn hoặc mất độ chính xác.

## 3. Theo dõi bất đồng bộ với Process.onExit

Java 9 bổ sung `Process.onExit()`, trả về `CompletableFuture<Process>`. Future hoàn tất khi tiến trình kết thúc và cung cấp đối tượng `Process` tương ứng.

~~~java
CompletableFuture<Process> exited = process.onExit();

exited.thenAccept(finished ->
    System.out.println("exit code: " + finished.exitValue())
);
~~~

Việc gọi `onExit()` không bắt buộc luồng hiện tại phải chờ tại chỗ. Ứng dụng có thể đăng ký callback để cập nhật trạng thái, giải phóng slot chạy hoặc lên lịch bước tiếp theo khi tiến trình hoàn tất.

### 3.1. Chuyển future thành mã thoát

`thenApply()` biến kết quả `Process` thành mã thoát:

~~~java
CompletableFuture<Integer> exitCode = process.onExit()
    .thenApply(Process::exitValue);

exitCode.thenAccept(code -> recordExitCode(code));
~~~

Vì stage được thực thi sau khi `onExit()` hoàn tất, `exitValue()` được gọi khi tiến trình đã kết thúc.

### 3.2. Nối các bước xử lý

Các phương thức của `CompletableFuture` cho phép tạo pipeline xử lý kết quả:

| Phương thức | Vai trò |
| --- | --- |
| `thenApply()` | Chuyển đổi giá trị kết quả |
| `thenAccept()` | Thực hiện hành động với kết quả |
| `thenRun()` | Thực hiện hành động không cần giá trị kết quả |
| `thenCompose()` | Nối một thao tác bất đồng bộ khác trả về future |
| `whenComplete()` | Quan sát kết quả hoặc lỗi khi hoàn tất |
| `handle()` | Xử lý cả kết quả thành công lẫn lỗi |
| `exceptionally()` | Phục hồi hoặc ánh xạ lỗi thành kết quả khác |

Nếu callback tốn thời gian hoặc thực hiện I/O blocking, cân nhắc dùng biến thể `thenAcceptAsync()`/`thenApplyAsync()` với executor phù hợp. Callback không có hậu tố `Async` có thể chạy trên thread hoàn tất stage hoặc thread đăng ký callback nếu future đã hoàn tất.

## 4. Timeout của CompletableFuture không dừng tiến trình

Java 9 bổ sung `CompletableFuture.orTimeout(timeout, unit)` và `completeOnTimeout(value, timeout, unit)`. Đây là các API hữu ích để giới hạn thời gian chờ kết quả future, nhưng chúng **không gửi lệnh dừng tới tiến trình hệ điều hành**.

### 4.1. orTimeout

`orTimeout()` làm future được gọi hoàn tất exceptional bằng `TimeoutException` nếu future chưa hoàn tất trong thời hạn. Phương thức trả về chính future đó.

~~~java
CompletableFuture<Process> observation = process.onExit()
    .thenApply(exited -> exited)
    .orTimeout(5, TimeUnit.SECONDS);

observation.whenComplete((exited, error) -> {
    if (error != null) {
        System.out.println("exit was not observed within five seconds");
    } else {
        System.out.println("process exited: " + exited.exitValue());
    }
});
~~~

Ở đây, `thenApply(exited -> exited)` tạo một future phụ thuộc riêng trước khi áp dụng `orTimeout()`. Future gốc từ `process.onExit()` vẫn có thể hoàn tất sau đó. Nếu gọi `orTimeout()` trực tiếp trên future gốc, chính future đó sẽ bị hoàn tất exceptional khi timeout.

### 4.2. completeOnTimeout

`completeOnTimeout(value, timeout, unit)` hoàn tất future bình thường bằng giá trị dự phòng nếu thời hạn hết trước khi có kết quả. Nó cũng không dừng tiến trình.

Giá trị dự phòng cần được thiết kế rõ ràng để không nhầm với kết quả thật. Ví dụ, nếu dùng `null`, caller phải phân biệt được `null` do timeout với một kết quả nghiệp vụ hợp lệ.

### 4.3. Phân biệt ba loại thời hạn

| Cơ chế | Điều gì hết hạn? | Tiến trình có tự dừng không? |
| --- | --- | --- |
| `process.waitFor(timeout, unit)` | Thời gian luồng hiện tại chờ | Không |
| `future.get(timeout, unit)` | Thời gian caller chờ future | Không |
| `future.orTimeout(timeout, unit)` | Thời gian future được phép chờ trước khi hoàn tất exceptional | Không |

Muốn dừng process khi hết deadline, ứng dụng phải chủ động gọi `destroy()` hoặc `destroyForcibly()` theo chính sách đã chọn, rồi xác nhận process kết thúc.

## 5. Quy trình dừng nhẹ và dừng cưỡng bức

Một chính sách phổ biến gồm ba giai đoạn:

1. Chờ công việc hoàn tất trong deadline.
2. Khi hết hạn, gọi `destroy()` để yêu cầu tiến trình dừng và dành một khoảng grace period để nó kết thúc.
3. Nếu vẫn chạy, gọi `destroyForcibly()` rồi tiếp tục chờ xác nhận kết thúc trong một giới hạn thời gian.

~~~java
if (!process.waitFor(5, TimeUnit.SECONDS)) {
    process.destroy();

    if (!process.waitFor(2, TimeUnit.SECONDS)) {
        process.destroyForcibly();

        if (!process.waitFor(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Process did not terminate");
        }
    }
}

Process exited = process.onExit().join();
~~~

`destroy()` yêu cầu tiến trình kết thúc. Cách hệ điều hành thực hiện việc này có thể khác nhau; không giả định nó luôn là một shutdown nhẹ có thể chạy cleanup hook, hoặc luôn kết thúc ngay.

`destroyForcibly()` yêu cầu chấm dứt cưỡng bức. Ngay cả khi API trả về thành công, tiến trình có thể cần thêm thời gian mới thực sự kết thúc. Vì vậy, vẫn cần kiểm tra bằng `waitFor()` hoặc `onExit()`.

### 5.1. Exit code sau khi bị dừng

Mã thoát của tiến trình bị dừng phụ thuộc nền tảng và cách chương trình bị chấm dứt. Không dùng một con số cố định làm điều kiện portable cho mọi hệ điều hành. Nếu ứng dụng cần phân biệt timeout với lỗi nghiệp vụ, hãy lưu trạng thái timeout riêng bên cạnh mã thoát.

### 5.2. Cleanup trong finally

Nếu lỗi xảy ra sau khi process đã được khởi chạy, ứng dụng vẫn cần quyết định cách cleanup. Một khối `finally` có thể kiểm tra `isAlive()`, yêu cầu dừng và chờ có giới hạn:

~~~java
try {
    runAndObserve(process);
} finally {
    if (process.isAlive()) {
        process.destroyForcibly();
        if (!process.waitFor(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Cleanup timed out");
        }
    }
}
~~~

Trong hệ thống thực tế, hãy cân nhắc cách báo lỗi cleanup mà không làm mất exception gốc từ công việc chính. Có thể ghi nhận lỗi dừng như suppressed exception hoặc kết hợp chúng trong kết quả vận hành.

## 6. Tiến trình con cháu và ProcessHandle

Một process có thể tạo thêm process khác. Dừng process cha không phải lúc nào cũng bảo đảm mọi tiến trình con cháu đều dừng theo.

Java 9 cung cấp `ProcessHandle` để quan sát và điều khiển tiến trình theo PID:

- `process.toHandle()` lấy handle tương ứng với `Process`.
- `handle.pid()` trả PID.
- `handle.isAlive()` kiểm tra trạng thái.
- `handle.children()` liệt kê các tiến trình con trực tiếp.
- `handle.descendants()` trả stream các tiến trình con và hậu duệ.
- `handle.destroy()` và `handle.destroyForcibly()` yêu cầu dừng tiến trình.
- `handle.onExit()` trả `CompletableFuture<ProcessHandle>` khi tiến trình kết thúc.

Ví dụ lấy danh sách hậu duệ hiện được quan sát rồi yêu cầu dừng:

~~~java
List<ProcessHandle> descendants = process.toHandle()
    .descendants()
    .collect(Collectors.toList());

for (ProcessHandle descendant : descendants) {
    if (descendant.isAlive()) {
        descendant.destroy();
    }
}

process.destroy();
~~~

`descendants()` cung cấp một góc nhìn tại thời điểm truy vấn, không phải khóa đồng bộ toàn bộ process tree. Tiến trình có thể tạo thêm con sau khi snapshot được lấy hoặc kết thúc trong lúc ứng dụng đang duyệt danh sách. Nếu cần dừng cây tiến trình đáng tin cậy, cần phối hợp với cơ chế quản lý process group, job object, container hoặc API đặc thù nền tảng.

Không coi PID là định danh bền vững: hệ điều hành có thể tái sử dụng PID sau khi tiến trình kết thúc. Giữ `ProcessHandle` trong phạm vi vòng đời cần quản lý và kiểm tra `isAlive()` trước khi thao tác.

## 7. Quản lý stdin, stdout và stderr

Quản lý stream là một phần của vòng đời tiến trình. Theo mặc định, `ProcessBuilder` có thể tạo pipe để kết nối stdin, stdout và stderr của tiến trình con với ứng dụng Java.

### 7.1. Pipe đầy có thể làm process không kết thúc

Nếu tiến trình con ghi nhiều dữ liệu vào stdout hoặc stderr mà ứng dụng cha không đọc, pipe có thể đầy. Khi đó, tiến trình con bị block trong thao tác ghi và không thể đi đến điểm kết thúc. `waitFor()` hoặc `onExit()` vì vậy có thể chờ rất lâu dù logic của chương trình con đã gần hoàn tất.

Các lựa chọn:

- Đọc stdout và stderr đồng thời trong khi tiến trình chạy.
- Dùng `redirectErrorStream(true)` để gộp stderr vào stdout rồi đọc một pipe.
- Redirect output/error ra file nếu cần lưu log.
- Dùng `ProcessBuilder.Redirect.INHERIT` nếu muốn output đi thẳng tới console hoặc nơi kế thừa phù hợp.

Không nên đọc hết stdout rồi mới đọc stderr nếu cả hai pipe có thể cùng đầy. Hãy drain đồng thời hoặc redirect để tránh deadlock.

### 7.2. Đóng stdin khi không gửi dữ liệu

Nếu tiến trình con chờ input nhưng ứng dụng cha không định gửi dữ liệu, đóng `process.getOutputStream()` để gửi EOF. Nếu không, chương trình con có thể tiếp tục chờ dữ liệu và không bao giờ kết thúc.

### 7.3. Đóng stream phía cha

Dùng try-with-resources cho reader/writer mà ứng dụng mở. Khi process đã kết thúc, đọc output đến EOF nếu cần thu thập đầy đủ kết quả rồi đóng stream. Đóng stream không thay thế việc dừng process; dừng process cũng không thay thế việc đóng stream.

## 8. Xử lý interruption

`waitFor()` và `waitFor(timeout, unit)` có thể ném `InterruptedException`. Đây là tín hiệu cho biết luồng quản lý bị yêu cầu dừng chờ.

Nếu ứng dụng không thể tiếp tục chờ, hãy khôi phục interrupt flag trước khi truyền lỗi lên hoặc thực hiện cleanup:

~~~java
try {
    boolean finished = process.waitFor(5, TimeUnit.SECONDS);
} catch (InterruptedException exception) {
    process.destroy();
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting for child process was interrupted", exception);
}
~~~

Đoạn mã minh họa chính sách dừng process khi luồng quản lý bị interrupt. Tùy ứng dụng, có thể cần chờ grace period hoặc dừng cưỡng bức trước khi khôi phục interrupt flag. Không nuốt `InterruptedException` rồi tiếp tục chờ như thể không có yêu cầu dừng.

Với `CompletableFuture.join()`, lỗi của stage được bọc trong `CompletionException`; nếu dùng `get()`, caller cần xử lý `InterruptedException` và `ExecutionException` riêng.

## 9. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ này chạy chính class Java hiện tại ở chế độ child. Child in thông báo sẵn sàng rồi ngủ 10 giây. Parent chỉ chờ 300 mili giây; khi deadline hết, parent yêu cầu dừng nhẹ, có fallback dừng cưỡng bức, sau đó dùng `Process.onExit()` và `CompletableFuture` để lấy mã thoát.

**Tệp:** `ProcessDeadlineDemo.java`

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class ProcessDeadlineDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "child".equals(args[0])) {
            System.out.println("child ready");
            System.out.flush();
            Thread.sleep(10_000L);
            System.out.println("child finished normally");
            return;
        }

        String javaExecutable = Paths.get(
            System.getProperty("java.home"),
            "bin",
            isWindows() ? "java.exe" : "java"
        ).toString();

        Process process = new ProcessBuilder(
            javaExecutable,
            "-cp",
            System.getProperty("java.class.path"),
            ProcessDeadlineDemo.class.getName(),
            "child"
        ).redirectErrorStream(true).start();

        try (BufferedReader output = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            System.out.println("child says: " + output.readLine());

            CompletableFuture<Integer> exitCode = process.onExit()
                .thenApply(Process::exitValue);

            boolean finishedInTime = process.waitFor(300, TimeUnit.MILLISECONDS);
            if (finishedInTime) {
                System.out.println("completed before deadline");
            } else {
                System.out.println("deadline reached; requesting stop");
                process.destroy();
                if (!process.waitFor(1, TimeUnit.SECONDS)) {
                    System.out.println("grace period expired; forcing stop");
                    process.destroyForcibly();
                    if (!process.waitFor(2, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Process did not terminate");
                    }
                }
            }

            int code = exitCode.join();
            System.out.println("exit code category: " + (code == 0 ? "zero" : "non-zero"));
            System.out.println("child alive: " + process.isAlive());
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Process cleanup timed out");
                }
            }
        }
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
            .toLowerCase(Locale.ROOT).contains("win");
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 ProcessDeadlineDemo.java
java ProcessDeadlineDemo
~~~

Output trên runtime dùng để kiểm thử ví dụ:

~~~text
child says: child ready
deadline reached; requesting stop
exit code category: non-zero
child alive: false
~~~

Tiến trình bị dừng trước khi hoàn thành `Thread.sleep(10_000L)`, nên mã thoát được phân loại là khác `0` trên runtime kiểm thử. Mã thoát số cụ thể và hành vi của `destroy()` có thể khác giữa các nền tảng; chương trình chỉ in nhóm mã thoát để tránh phụ thuộc vào một con số.

Nhánh `grace period expired; forcing stop` là fallback nếu process chưa kết thúc sau một giây. Nó không xuất hiện trong lần chạy kiểm thử này vì process kết thúc sau yêu cầu `destroy()`.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hết timeout nhưng process vẫn chạy | Timeout chỉ giới hạn việc chờ | Gọi `destroy()` hoặc chính sách dừng khác rồi xác nhận kết thúc |
| Gọi `exitValue()` khi process còn sống | Mã thoát chưa sẵn sàng | Chờ `waitFor()` hoặc `onExit()` hoàn tất |
| Nghĩ `orTimeout()` tự kill process | Future timeout không điều khiển process OS | Dùng timeout để phát hiện quá hạn, sau đó gọi API dừng process |
| Dùng `orTimeout()` trực tiếp trên future gốc rồi mong nó hoàn tất sau | Future gốc đã bị hoàn tất exceptional | Dùng future phụ thuộc riêng nếu cần deadline view và vẫn giữ future kết thúc thật |
| Chỉ gọi `destroy()` rồi giả định process đã dừng | Yêu cầu dừng không đồng nghĩa đã kết thúc | Chờ grace period, kiểm tra và dùng `destroyForcibly()` khi cần |
| Không kiểm tra tiến trình con cháu | Process cha có thể tạo process khác còn sống | Dùng `ProcessHandle.descendants()` và cơ chế process group phù hợp |
| Không đọc stdout/stderr | Pipe đầy khiến child block khi ghi | Drain đồng thời hoặc redirect output/error |
| Để stdin mở dù child chờ EOF | Child tiếp tục chờ input | Đóng `process.getOutputStream()` khi không gửi dữ liệu |
| Hủy CompletableFuture để dừng process | Future và process là hai đối tượng riêng | Gọi `destroy()`/`destroyForcibly()` trên Process hoặc ProcessHandle |
| Nuốt `InterruptedException` | Mất tín hiệu dừng từ luồng quản lý | Cleanup theo chính sách và khôi phục interrupt flag |

## 11. Quy tắc thực hành

1. Đặt deadline rõ ràng cho tiến trình và cho toàn bộ quy trình quản lý nó.
2. Dùng `waitFor(timeout, unit)` khi luồng hiện tại có thể chờ trong một khoảng giới hạn.
3. Dùng `Process.onExit()` khi cần nhận thông báo kết thúc bất đồng bộ và nối các bước bằng `CompletableFuture`.
4. Phân biệt timeout của thao tác chờ với việc process thực sự bị dừng.
5. Khi hết hạn, thực hiện chính sách dừng nhẹ, grace period, rồi dừng cưỡng bức nếu cần.
6. Xác nhận kết thúc bằng `waitFor()`, `isAlive()` hoặc `onExit()`; không suy luận từ việc đã gọi `destroy()`.
7. Giữ future gốc từ `onExit()` nếu cần quan sát kết thúc thật; áp dụng timeout trên stage phụ thuộc riêng khi cần timeout cho một góc nhìn.
8. Drain hoặc redirect stdout/stderr và đóng stdin khi child không cần input.
9. Quản lý process descendants nếu ứng dụng tạo process tree; hiểu giới hạn snapshot và race condition.
10. Xử lý interruption và cleanup trong mọi đường thoát sau khi process đã khởi chạy.

## 12. Tự kiểm tra

- `waitFor(5, SECONDS)` trả `false` nghĩa là gì? Hết thời gian chờ nhưng tiến trình vẫn chưa kết thúc.
- Khi `waitFor(timeout)` trả `false`, process có tự dừng không? Không.
- `Process.onExit()` trả kiểu gì? `CompletableFuture<Process>`.
- `orTimeout()` có gửi tín hiệu dừng tới process không? Không; nó chỉ hoàn tất future exceptional khi timeout.
- Vì sao nên dùng `destroy()` trước `destroyForcibly()`? Để cho tiến trình một khoảng thời gian kết thúc theo chính sách dừng nhẹ trước khi cưỡng bức.
- Vì sao cần xác nhận sau `destroyForcibly()`? Vì yêu cầu dừng không đồng nghĩa process đã kết thúc ngay lập tức.
- Vì sao `onExit()` có thể chờ mãi nếu stdout không được đọc? Pipe có thể đầy làm tiến trình con bị block khi ghi.
- `ProcessHandle.descendants()` có phải snapshot bất biến của toàn bộ process tree không? Không; process tree có thể thay đổi đồng thời khi truy vấn.
- Khi luồng quản lý bị interrupt trong `waitFor()`, cần làm gì? Cleanup theo chính sách và khôi phục interrupt flag nếu truyền lỗi lên.

Điểm cốt lõi: **deadline xác định thời gian chờ; destroy xác định yêu cầu dừng; onExit/waitFor xác nhận tiến trình đã kết thúc.** Quản lý cả ba phần cùng với stream và process descendants để tránh tiến trình con bị treo hoặc sống ngoài vòng đời mà ứng dụng dự kiến.