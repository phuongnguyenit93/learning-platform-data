# Theo dõi kết thúc qua onExit và CompletableFuture

Khi tạo tiến trình con bằng `ProcessBuilder`, chương trình thường cần biết tiến trình đã kết thúc hay chưa, lấy mã thoát, cập nhật trạng thái công việc hoặc khởi chạy bước tiếp theo. `Process.waitFor()` thực hiện việc chờ theo kiểu blocking; từ Java 9, `Process.onExit()` cung cấp một cách theo dõi bất đồng bộ bằng cách trả về `CompletableFuture<Process>`.

Khi tiến trình kết thúc, future hoàn tất với chính đối tượng `Process`. Có thể nối các hành động bằng `thenApply()`, `thenAccept()`, `whenComplete()` hoặc các phương thức composition khác mà không cần tự tạo một vòng lặp polling.

## Mục tiêu

- Hiểu hợp đồng và thời điểm hoàn tất của `Process.onExit()`.
- Kết hợp kết quả kết thúc tiến trình với `CompletableFuture`.
- Lấy mã thoát an toàn sau khi tiến trình đã kết thúc.
- Chọn giữa callback bất đồng bộ và chờ đồng bộ bằng `get()` hoặc `join()`.
- Xử lý lỗi, timeout, hủy future và dừng tiến trình đúng cách.
- Quản lý stdout/stderr để tránh pipe bị đầy và tiến trình bị treo.
- Phân biệt `Process.onExit()` với `ProcessHandle.onExit()`.

## 1. Chờ tiến trình kết thúc: waitFor và onExit

`Process` đại diện cho một tiến trình do ứng dụng tạo ra. Sau khi gọi `ProcessBuilder.start()`, tiến trình có thể đang chạy trong khi luồng Java tiếp tục làm công việc khác.

### 1.1. `waitFor()` là cách chờ blocking

`waitFor()` không tham số chặn luồng gọi cho đến khi tiến trình kết thúc, sau đó trả về mã thoát:

~~~java
Process process = new ProcessBuilder("some-command").start();
int exitCode = process.waitFor();
~~~

Đây là cách đơn giản khi luồng hiện tại có thể chờ. Overload `waitFor(timeout, unit)` cho phép chờ trong thời hạn; nó trả `false` nếu hết thời gian mà tiến trình chưa kết thúc. Hết thời gian chờ không tự động dừng tiến trình.

### 1.2. `onExit()` cung cấp future

Java 9 bổ sung:

~~~java
CompletableFuture<Process> exitFuture = process.onExit();
~~~

`onExit()` trả về một `CompletableFuture<Process>`. Future hoàn tất khi tiến trình kết thúc và cung cấp đối tượng `Process` tương ứng. Có thể đăng ký hành động tiếp theo ngay sau khi tạo future:

~~~java
process.onExit().thenAccept(exited ->
    System.out.println("exit code: " + exited.exitValue())
);
~~~

Đăng ký callback không yêu cầu luồng gọi phải chờ tại chỗ. Khi tiến trình kết thúc, hành động phụ thuộc được thực thi theo cơ chế của `CompletableFuture`.

### 1.3. `exitValue()` chỉ an toàn sau khi kết thúc

`Process.exitValue()` trả mã thoát của tiến trình. Nếu tiến trình vẫn đang chạy, phương thức ném `IllegalThreadStateException`. Khi nhận `Process` từ future đã hoàn tất, tiến trình đã kết thúc nên có thể lấy mã thoát:

~~~java
CompletableFuture<Integer> exitCode = process.onExit()
    .thenApply(Process::exitValue);
~~~

Đoạn mã này biến `CompletableFuture<Process>` thành `CompletableFuture<Integer>`. Kết quả có thể được chuyển tiếp tới các bước xử lý sau.

## 2. Kết hợp onExit với CompletableFuture

`CompletableFuture` biểu diễn một kết quả có thể có trong tương lai. Các phương thức stage cho phép nối công việc khi future hoàn tất.

| Phương thức | Công dụng |
| --- | --- |
| `thenApply(fn)` | Chuyển đổi kết quả và tạo future mới |
| `thenAccept(action)` | Thực hiện hành động nhận kết quả, không tạo giá trị kết quả mới |
| `thenRun(action)` | Thực hiện hành động không cần nhận kết quả trước đó |
| `thenCompose(fn)` | Nối một bước bất đồng bộ khác và làm phẳng future lồng nhau |
| `whenComplete(action)` | Quan sát kết quả hoặc lỗi khi hoàn tất, giữ nguyên kết quả của stage |
| `handle(fn)` | Xử lý cả kết quả thành công lẫn lỗi và tạo kết quả mới |
| `exceptionally(fn)` | Phục hồi hoặc chuyển đổi lỗi thành kết quả thay thế |

### 2.1. Lấy mã thoát rồi xử lý

~~~java
CompletableFuture<Integer> exitCode = process.onExit()
    .thenApply(Process::exitValue);

CompletableFuture<Void> report = exitCode.thenAccept(code -> {
    if (code == 0) {
        System.out.println("process completed successfully");
    } else {
        System.out.println("process failed with code " + code);
    }
});
~~~

`exitCode` đại diện cho mã thoát trong tương lai. `report` đại diện cho bước báo cáo sau khi có mã thoát. Có thể nối thêm các stage mà không phải gọi `waitFor()` trong từng bước.

### 2.2. Nối một thao tác bất đồng bộ khác

Nếu bước sau cũng trả về `CompletableFuture`, dùng `thenCompose()` để tránh tạo cấu trúc `CompletableFuture<CompletableFuture<T>>`:

~~~java
CompletableFuture<String> summary = process.onExit()
    .thenCompose(exited -> loadSummaryAsync(exited.exitValue()));
~~~

Trong ví dụ này, `loadSummaryAsync()` là phương thức của ứng dụng trả về `CompletableFuture<String>`. `thenCompose()` nối trực tiếp kết quả của future bên trong vào pipeline ngoài.

### 2.3. Quan sát thành công và lỗi

`whenComplete()` hữu ích khi cần ghi log hoặc cập nhật trạng thái dù tiến trình hoàn tất bình thường hay future thất bại:

~~~java
CompletableFuture<Process> exitFuture = process.onExit();

exitFuture.whenComplete((exited, error) -> {
    if (error != null) {
        logFailure(error);
    } else {
        recordExitCode(exited.exitValue());
    }
});
~~~

`whenComplete()` là bước quan sát; nếu cần biến lỗi thành kết quả phục hồi, dùng `exceptionally()` hoặc `handle()` theo chính sách ứng dụng.

## 3. Không blocking và blocking ở đâu?

`onExit()` cho phép đăng ký callback rồi trả quyền điều khiển về cho luồng gọi. Tuy nhiên, các phương thức chờ kết quả của future vẫn có thể blocking:

- `future.get()` chờ hoàn tất và khai báo `InterruptedException`, `ExecutionException`.
- `future.join()` chờ hoàn tất và ném `CompletionException` nếu stage thất bại.
- `thenApply()` và `thenAccept()` đăng ký công việc phụ thuộc; chúng không tự chặn luồng gọi để chờ tiến trình.

Ví dụ, `join()` phù hợp ở điểm chương trình thực sự cần kết quả:

~~~java
CompletableFuture<Integer> exitCode = process.onExit()
    .thenApply(Process::exitValue);

int code = exitCode.join();
System.out.println(code);
~~~

Đoạn mã vẫn chờ, vì `join()` là thao tác blocking. Lợi ích của future là có thể kết hợp công việc và chỉ chờ ở ranh giới thật sự cần kết quả.

### 3.1. Khi nào dùng callback async?

Các biến thể như `thenApplyAsync()` và `thenAcceptAsync()` thực thi hành động phụ thuộc qua executor thay vì mặc định chạy theo thread hoàn tất stage. Chọn executor phù hợp nếu callback tốn CPU hoặc có thao tác blocking:

~~~java
exitCode.thenAcceptAsync(code -> updateLargeReport(code), executor);
~~~

Các callback không có hậu tố `Async` có thể chạy trên thread hoàn tất future hoặc thread đăng ký callback nếu future đã hoàn tất. Vì vậy, tránh đặt công việc blocking dài trong callback không async, đặc biệt khi không kiểm soát executor.

## 4. Xử lý lỗi và mã thoát

Cần phân biệt hai loại kết quả:

- **Mã thoát khác 0:** tiến trình đã kết thúc bình thường theo cơ chế hệ điều hành, nhưng ứng dụng con báo trạng thái thất bại hoặc một kết quả nghiệp vụ khác.
- **Future hoàn tất exceptional:** lỗi xảy ra trong quá trình quản lý hoặc xử lý future, ví dụ một stage ném exception. Đây không đồng nghĩa với mã thoát khác 0.

`Process.onExit()` thông thường hoàn tất với `Process` khi tiến trình kết thúc; sau đó ứng dụng kiểm tra `exitValue()` để quyết định thành công hay thất bại theo quy ước của lệnh con.

### 4.1. Xử lý exception của stage

~~~java
CompletableFuture<Integer> exitCode = process.onExit()
    .thenApply(Process::exitValue);

CompletableFuture<Integer> safeCode = exitCode.exceptionally(error -> {
    logFailure(error);
    return -1;
});
~~~

Giá trị `-1` ở đây chỉ là quy ước phục hồi của ví dụ; ứng dụng cần chọn cách biểu diễn lỗi phù hợp. Không gộp lỗi khởi chạy, lỗi đọc output và mã thoát của tiến trình thành một trạng thái duy nhất nếu hệ thống cần phân biệt chúng.

### 4.2. Giữ trạng thái interrupted

Nếu dùng `get()` và thread bị interrupt, hãy xử lý `InterruptedException` theo chính sách của ứng dụng. Với tác vụ không thể tiếp tục, thường nên khôi phục cờ interrupt trước khi truyền lỗi lên:

~~~java
try {
    int code = exitCode.get();
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting for process was interrupted", exception);
}
~~~

Không nuốt `InterruptedException` rồi tiếp tục chờ như thể không có yêu cầu dừng.

## 5. Timeout, cancel và dừng tiến trình

Timeout của future và việc dừng tiến trình là hai hành động khác nhau.

### 5.1. Timeout không tự kill tiến trình

`CompletableFuture.orTimeout(timeout, unit)` (có từ Java 9) làm future hoàn tất exceptional bằng `TimeoutException` nếu thời hạn hết trước khi có kết quả. Nó không gửi tín hiệu dừng tới tiến trình hệ điều hành.

Tương tự, `get(timeout, unit)` chỉ giới hạn thời gian thread gọi chờ. Nếu hết thời gian, tiến trình vẫn có thể tiếp tục chạy.

### 5.2. Chủ động yêu cầu dừng

Nếu quá thời gian mà tiến trình cần được dừng, ứng dụng phải gọi `destroy()` hoặc `destroyForcibly()` theo chính sách đã chọn, rồi tiếp tục theo dõi cho đến khi tiến trình thực sự kết thúc:

~~~java
if (!process.waitFor(5, TimeUnit.SECONDS)) {
    process.destroy();
    if (!process.waitFor(2, TimeUnit.SECONDS)) {
        process.destroyForcibly();
    }
}

Process exited = process.onExit().join();
~~~

Ví dụ này dùng `waitFor(timeout, unit)` để thể hiện trình tự đồng bộ. Nếu hệ thống cần hoàn toàn bất đồng bộ, có thể dùng scheduler để phát lệnh `destroy()` khi timeout và vẫn dùng `onExit()` để xác nhận kết thúc.

`destroy()` là yêu cầu dừng nhẹ theo khả năng của nền tảng; `destroyForcibly()` yêu cầu chấm dứt mạnh hơn. Không nên mặc định rằng yêu cầu dừng đã thành công ngay lập tức; hãy xác nhận bằng `onExit()` hoặc `waitFor()`.

### 5.3. Hủy CompletableFuture không đồng nghĩa dừng process

Gọi `cancel()` trên future không phải là cơ chế portable để kết thúc tiến trình hệ điều hành. Nếu cần dừng process, hãy gọi API trên `Process` một cách tường minh và sau đó theo dõi completion. Future chỉ đại diện cho trạng thái kết quả bất đồng bộ.

## 6. Quản lý stdout và stderr

Đây là một nguyên nhân phổ biến khiến chương trình chờ `onExit()` mãi không hoàn tất.

Mặc định, `ProcessBuilder` tạo các pipe cho stdout, stderr và stdin của tiến trình con. Nếu tiến trình con ghi nhiều dữ liệu nhưng chương trình cha không đọc stdout/stderr, pipe có thể đầy. Khi pipe đầy, tiến trình con bị block lúc ghi và không thể kết thúc; future từ `onExit()` vì thế cũng chưa hoàn tất.

Các cách xử lý:

- Đọc stdout và stderr đồng thời trong khi tiến trình chạy.
- Dùng `redirectErrorStream(true)` để gộp stderr vào stdout, nhưng vẫn phải đọc hoặc redirect pipe kết quả.
- Dùng `redirectOutput()` và `redirectError()` để ghi ra file hoặc kế thừa luồng console khi phù hợp.
- Đóng stdin của tiến trình con nếu chương trình con chờ input nhưng ứng dụng cha không có dữ liệu cần gửi.

Ví dụ này kế thừa output của tiến trình con để không để pipe stdout/stderr bị bỏ mặc:

~~~java
Process process = new ProcessBuilder(command)
    .redirectErrorStream(true)
    .redirectOutput(ProcessBuilder.Redirect.INHERIT)
    .start();

process.onExit().thenAccept(exited ->
    System.out.println("exit code: " + exited.exitValue())
);
~~~

Nếu cần lưu output để phân tích, hãy đọc stream trong tác vụ riêng và bảo đảm tác vụ đọc được chạy đồng thời với tiến trình. Không chờ process kết thúc rồi mới bắt đầu đọc một pipe có thể đã đầy.

## 7. ProcessHandle.onExit()

Java 9 cũng bổ sung `ProcessHandle`, một abstraction đại diện cho tiến trình của hệ điều hành. `Process.toHandle()` trả handle của process tương ứng; `ProcessHandle.of(pid)` cho phép tìm handle theo PID và trả về `Optional<ProcessHandle>`.

`ProcessHandle.onExit()` trả về `CompletableFuture<ProcessHandle>` hoàn tất khi tiến trình tương ứng kết thúc. Nó gần với `Process.onExit()`, nhưng kết quả là `ProcessHandle`, không phải `Process`.

| API | Kiểu future | Khi phù hợp |
| --- | --- | --- |
| `Process.onExit()` | `CompletableFuture<Process>` | Đang quản lý một đối tượng `Process` tạo bởi `ProcessBuilder` và cần lấy exit value hoặc thao tác trên Process |
| `ProcessHandle.onExit()` | `CompletableFuture<ProcessHandle>` | Theo dõi một process handle, cần thông tin định danh hoặc thao tác qua ProcessHandle |

`ProcessHandle` còn cung cấp thông tin như PID, trạng thái sống và quan hệ tiến trình. Không dùng PID làm định danh lâu dài: PID có thể được hệ điều hành tái sử dụng sau khi tiến trình kết thúc.

## 8. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ này khởi chạy chính chương trình Java hiện tại ở chế độ child. Tiến trình cha đăng ký `onExit()`, chuyển `Process` thành mã thoát bằng `thenApply()`, rồi báo kết quả bằng `thenAccept()`. Output của child được kế thừa để tránh pipe bị đầy.

**Tệp:** `ProcessExitDemo.java`

~~~java
import java.nio.file.Paths;
import java.util.concurrent.CompletableFuture;

public class ProcessExitDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "child".equals(args[0])) {
            System.out.println("child work complete");
            return;
        }

        String executable = Paths.get(
            System.getProperty("java.home"),
            "bin",
            isWindows() ? "java.exe" : "java"
        ).toString();

        Process process = new ProcessBuilder(
            executable,
            "-cp",
            System.getProperty("java.class.path"),
            ProcessExitDemo.class.getName(),
            "child"
        )
            .redirectErrorStream(true)
            .redirectOutput(ProcessBuilder.Redirect.INHERIT)
            .start();

        CompletableFuture<Integer> exitCode = process.onExit()
            .thenApply(Process::exitValue);

        CompletableFuture<Void> report = exitCode.thenAccept(code ->
            System.out.println("child exit code: " + code)
        );

        report.join();
        System.out.println("process alive: " + process.isAlive());
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
            .toLowerCase(java.util.Locale.ROOT).contains("win");
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 ProcessExitDemo.java
java ProcessExitDemo
~~~

Output:

~~~text
child work complete
child exit code: 0
process alive: false
~~~

Trong lần chạy này:

1. Nhánh `child` in thông báo rồi kết thúc với mã thoát `0`.
2. Nhánh cha tạo `CompletableFuture<Process>` bằng `process.onExit()`.
3. `thenApply(Process::exitValue)` chuyển kết quả thành `CompletableFuture<Integer>`.
4. `thenAccept()` in mã thoát sau khi future trước hoàn tất.
5. `report.join()` chờ cả callback báo cáo kết thúc; sau đó `isAlive()` trả `false`.

Ví dụ sử dụng `java.home` và tên executable theo hệ điều hành để tìm Java runtime hiện tại. Nó dùng classpath đang chạy để child tìm thấy cùng class. Trong ứng dụng thực tế, cần xác định classpath/module path và tham số tiến trình theo cách triển khai của ứng dụng.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `exitValue()` khi process còn chạy | Chưa có mã thoát | Dùng giá trị `Process` sau khi `onExit()` hoàn tất hoặc chờ bằng `waitFor()` |
| Nghĩ `onExit()` tự chờ ngay tại chỗ | Nhầm future với thao tác blocking | Đăng ký callback hoặc chủ động dùng `get()`/`join()` ở ranh giới cần chờ |
| Nghĩ `collect`/callback tự đóng stream process | Completion notification không thay thế quản lý stdout/stderr/stdin | Đọc, redirect và đóng stream theo ownership rõ ràng |
| Không đọc stdout/stderr | Pipe đầy làm tiến trình con bị block | Drain đồng thời hoặc redirect output |
| Dùng `orTimeout()` rồi cho rằng process đã dừng | Timeout chỉ hoàn tất future exceptional | Gọi `destroy()`/`destroyForcibly()` và xác nhận bằng `onExit()` |
| Hủy future để kill process | Future và tiến trình OS là hai đối tượng khác nhau | Gọi API dừng trên `Process` một cách tường minh |
| Blocking callback trong `thenAccept()` | Callback có thể chạy trên thread hoàn tất future | Dùng stage `Async` với executor phù hợp cho công việc nặng |
| Không phân biệt exit code với exception | Process có thể kết thúc mã khác 0 mà future vẫn hoàn tất bình thường | Kiểm tra `exitValue()` và xử lý exception của future riêng biệt |
| Dùng PID làm ID bền vững | Hệ điều hành có thể tái sử dụng PID | Dùng handle trong phạm vi vòng đời cần thiết và không lưu PID như ID vĩnh viễn |

## 10. Quy tắc thực hành

1. Dùng `Process.onExit()` khi muốn theo dõi kết thúc tiến trình theo kiểu bất đồng bộ.
2. Dùng `thenApply()` để lấy exit code và `thenAccept()`/`whenComplete()` để cập nhật trạng thái hoặc báo cáo.
3. Chỉ gọi `exitValue()` sau khi process đã kết thúc.
4. Dùng `get()` hoặc `join()` khi thực sự cần chờ; nhớ rằng cả hai đều blocking.
5. Dùng stage `Async` và executor phù hợp cho callback tốn CPU hoặc có thao tác blocking.
6. Phân biệt mã thoát khác 0 với exceptional completion của future.
7. Không coi timeout hoặc cancel của future là lệnh dừng process; gọi `destroy()`/`destroyForcibly()` khi cần.
8. Đọc hoặc redirect stdout/stderr trong khi process chạy để tránh pipe đầy.
9. Dùng try/finally hoặc cấu trúc quản lý tài nguyên phù hợp cho các stream mà ứng dụng mở quanh process.
10. Dùng `ProcessHandle.onExit()` khi đang làm việc với ProcessHandle; chọn đúng kiểu future trả về.

## 11. Tự kiểm tra

- `Process.onExit()` trả về kiểu gì? `CompletableFuture<Process>`.
- Khi nào future từ `onExit()` hoàn tất? Khi tiến trình tương ứng kết thúc.
- Vì sao `thenApply(Process::exitValue)` an toàn sau `onExit()`? Vì Process được đưa vào stage sau khi tiến trình đã kết thúc.
- `thenAccept()` khác `thenApply()` thế nào? `thenAccept()` chỉ thực hiện hành động và tạo `CompletableFuture<Void>`; `thenApply()` chuyển đổi kết quả sang giá trị mới.
- `join()` có blocking không? Có, nó chờ future hoàn tất.
- `orTimeout()` có tự dừng process không? Không, nó chỉ hoàn tất future exceptional khi timeout.
- Vì sao không đọc stdout/stderr có thể làm `onExit()` không hoàn tất? Pipe có thể đầy khiến tiến trình con bị block khi ghi.
- `ProcessHandle.onExit()` trả future kiểu gì? `CompletableFuture<ProcessHandle>`.
- Mã thoát khác 0 có làm future `onExit()` exceptional không? Không nhất thiết; future có thể hoàn tất bình thường với Process, còn mã thoát được kiểm tra riêng.

Điểm cốt lõi: **`Process.onExit()` báo thời điểm tiến trình kết thúc dưới dạng `CompletableFuture<Process>`.** Dùng các stage của CompletableFuture để nối xử lý kết quả, kiểm tra mã thoát riêng với lỗi future, và quản lý output/timeout/dừng tiến trình một cách tường minh.