# `waitFor`, `exitValue` và xử lý mã kết thúc

Khi Java khởi chạy một chương trình bên ngoài bằng `ProcessBuilder.start()`, JVM nhận về một đối tượng `Process` để theo dõi và điều khiển tiến trình con. `waitFor()` chờ tiến trình kết thúc và trả về mã kết thúc; `exitValue()` chỉ đọc mã kết thúc hiện có và ném `IllegalThreadStateException` nếu tiến trình vẫn đang chạy. Hai phương thức phục vụ hai mục đích khác nhau: chờ kết thúc và truy vấn trạng thái đã kết thúc.

Trong Java 26, `Process` còn triển khai `Closeable`/`AutoCloseable`. `Process.close()` đóng các stream giao tiếp rồi chờ tiến trình kết thúc; nếu thread bị interrupt trong lúc `close()` chờ, tiến trình bị hủy cưỡng bức và `close()` tiếp tục chờ nó dừng. Đây là thay đổi quan trọng khi dùng `try-with-resources` để quản lý vòng đời process. `waitFor(Duration)` đã có từ Java 24 và tiếp tục là API hiện hành trong Java 26. Các API này thuộc Java SE ổn định, không phải preview hay incubator. [Java 26 `Process`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html) · [Java 26 `ProcessBuilder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html).

## 1. Vòng đời cơ bản của một Process

`ProcessBuilder` mô tả chương trình cần chạy, các tham số, thư mục làm việc, môi trường và cách nối stdin/stdout/stderr. Gọi `start()` để tạo tiến trình hệ điều hành và nhận về `Process`:

```java
List<String> command = List.of("java", "-version");
ProcessBuilder builder = new ProcessBuilder(command);
Process process = builder.start();
```

Vòng đời điển hình:

```text
Java application
      |
      | ProcessBuilder.start()
      v
 OS process được tạo
      |
      +---- stdin  <---- Process.getOutputStream()/outputWriter()
      |
      +---- stdout ----> Process.getInputStream()/inputReader()
      |
      +---- stderr ----> Process.getErrorStream()/errorReader()
      |
      v
 Process đang chạy
      |
      +---- waitFor() --------------------> chờ tới khi kết thúc
      |                                         |
      +---- waitFor(Duration) ------------> chờ có giới hạn
      |                                         |
      +---- onExit() ----------------------> nhận tín hiệu bất đồng bộ
      |                                         |
      v                                         v
 Process đã kết thúc <------------------- exit code có sẵn
      |
      +---- exitValue() ----> đọc mã kết thúc
      |
      +---- close() --------> đóng stream và chờ kết thúc (Java 26+)
```

Một `Process` không phải thread Java. Nó đại diện cho tiến trình do hệ điều hành quản lý; vòng đời của nó không tự kết thúc chỉ vì biến `Process` không còn được tham chiếu. Nếu ứng dụng bỏ tham chiếu mà không đóng stream hoặc không quản lý process, tiến trình con vẫn có thể tiếp tục chạy.

Từ Java 5, `ProcessBuilder.start()` là cách được ưu tiên để tạo process. `ProcessBuilder` nhận danh sách command và argument, giúp tránh việc ghép một chuỗi shell rồi phụ thuộc vào cách shell phân tích dấu cách, dấu nháy hoặc ký tự đặc biệt. Hãy truyền từng argument thành một phần tử riêng trong `List<String>`.

## 2. `waitFor()` chờ và trả về exit code

Chữ ký:

```java
public abstract int waitFor() throws InterruptedException
```

`waitFor()` chặn thread gọi cho đến khi process kết thúc. Nếu process đã kết thúc trước khi gọi, phương thức trả về ngay. Giá trị trả về là exit code của chương trình con.

```java
try (Process process = new ProcessBuilder("java", "-version").start()) {
    int exitCode = process.waitFor();

    if (exitCode == 0) {
        System.out.println("Process completed successfully");
    } else {
        System.err.println("Process failed with exit code: " + exitCode);
    }
}
```

Theo quy ước phổ biến, `0` biểu thị kết thúc bình thường; giá trị khác `0` thường biểu thị lỗi hoặc một trạng thái đặc biệt do chương trình con định nghĩa. Java không quy định ý nghĩa thống nhất cho từng mã khác `0`. Ý nghĩa của các giá trị đó thuộc hợp đồng của executable được gọi và có thể phụ thuộc hệ điều hành.

`waitFor()` không tự đọc stdout hoặc stderr. Nó chỉ chờ tiến trình kết thúc. Nếu chương trình con đang ghi dữ liệu vào pipe và pipe bị đầy vì Java không đọc, tiến trình con có thể bị chặn khi ghi; lúc đó `waitFor()` cũng chờ mãi. Phải quản lý các stream song song với việc chờ process, hoặc redirect output sang file/đích khác.

### `InterruptedException`

Nếu thread đang chờ bị interrupt, `waitFor()` kết thúc việc chờ và ném `InterruptedException`. Việc interrupt thread Java không tự động hủy process hệ điều hành. Ứng dụng phải quyết định có tiếp tục chờ, gửi tín hiệu kết thúc hay hủy cưỡng bức process.

Nếu phương thức hiện tại có thể khai báo `throws InterruptedException`, hãy truyền exception lên caller để caller quyết định chính sách hủy. Nếu bắt exception để kết thúc tác vụ, khôi phục interrupt status khi không tiếp tục ném exception:

```java
try (Process process = new ProcessBuilder(command).start()) {
    try {
        int exitCode = process.waitFor();
        handleExitCode(exitCode);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw interrupted;
    }
}
```

Trong Java 26, khi exception thoát khỏi block, `Process.close()` được gọi tự động. Vì interrupt status đã được khôi phục, thao tác chờ bên trong `close()` bị interrupt; theo hợp đồng Java 26, close hủy cưỡng bức process, đợi process kết thúc rồi khôi phục interrupt status. Nếu không dùng `Process.close()` hoặc runtime mục tiêu thấp hơn Java 26, hãy tự gọi `destroyForcibly()` và chờ process kết thúc trước khi trả quyền điều khiển.

## 3. `exitValue()` chỉ đọc trạng thái đã kết thúc

Chữ ký:

```java
public abstract int exitValue()
```

`exitValue()` không chờ process. Nó trả về exit code nếu process đã kết thúc. Nếu process vẫn còn sống, phương thức ném `IllegalThreadStateException`.

```java
if (process.isAlive()) {
    System.out.println("Process is still running");
} else {
    int exitCode = process.exitValue();
    System.out.println("Exit code: " + exitCode);
}
```

Không dùng `exitValue()` như một cách chờ. Cũng không cần gọi `exitValue()` ngay sau `waitFor()` nếu chỉ muốn lấy mã kết thúc, vì `waitFor()` đã trả chính mã đó:

```java
int exitCode = process.waitFor(); // Đã có exit code
```

`isAlive()` hữu ích để quan sát trạng thái, nhưng nếu mục tiêu là lấy exit code sau khi hoàn tất, hãy gọi `waitFor()` hoặc `waitFor(Duration)` trước. Đừng dựa vào chuỗi `isAlive()` rồi `exitValue()` để đồng bộ nhiều thread; process có thể đổi trạng thái giữa hai lần gọi.

| Trạng thái process | `waitFor()` | `exitValue()` |
|---|---|---|
| Đã kết thúc trước khi gọi | Trả về ngay exit code. | Trả về exit code. |
| Đang chạy | Chặn thread đến khi kết thúc. | Ném `IllegalThreadStateException`. |
| Thread chờ bị interrupt | Ném `InterruptedException`; process vẫn có thể tiếp tục chạy. | Không có thao tác chờ nên không ném `InterruptedException`; nếu process còn sống thì ném `IllegalThreadStateException`. |

## 4. Chờ có thời hạn với `waitFor(Duration)`

Java 24 bổ sung overload nhận `Duration`, tiếp tục có trong Java 26:

```java
public boolean waitFor(Duration duration) throws InterruptedException
```

Phương thức trả về:

- `true`: process đã kết thúc trong hoặc trước thời hạn chờ.
- `false`: thời hạn đã hết nhưng process vẫn chưa kết thúc.

Timeout không tự hủy process. Nếu trả về `false`, process vẫn có thể chạy và vẫn cần được quản lý. Nếu `Duration` không dương, phương thức trả về ngay `false` khi process còn sống; nếu process đã kết thúc thì trả về `true`.

```java
import java.time.Duration;

boolean finished = process.waitFor(Duration.ofSeconds(5));

if (finished) {
    int exitCode = process.exitValue();
    System.out.println("Exited with: " + exitCode);
} else {
    System.out.println("Still running after five seconds");
    // Process vẫn sống. Cần quyết định chờ tiếp hoặc hủy.
}
```

Overload cũ hơn `waitFor(long timeout, TimeUnit unit)` vẫn là API hiện hành và có thể dùng khi codebase đang nhận timeout theo `TimeUnit`:

```java
boolean finished = process.waitFor(5, TimeUnit.SECONDS);
```

Khi viết code mới trong Java 26, `Duration` thường dễ đọc và kết hợp tự nhiên với các API thời gian khác. Không nhầm `waitFor(Duration)` với `ProcessHandle.onExit()`: một phương thức chờ đồng bộ có thời hạn, phương thức còn lại cung cấp tín hiệu hoàn tất bất đồng bộ.

### Timeout phải đi cùng chính sách hủy

Ví dụ sau chờ tối đa 5 giây, yêu cầu kết thúc bình thường, cho thêm 1 giây để process tự dừng, rồi mới hủy cưỡng bức:

```java
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

static int runWithTimeout(List<String> command)
        throws IOException, InterruptedException, TimeoutException {

    ProcessBuilder builder = new ProcessBuilder(command)
            .redirectOutput(ProcessBuilder.Redirect.DISCARD)
            .redirectError(ProcessBuilder.Redirect.DISCARD);

    try (Process process = builder.start()) {
        if (!process.waitFor(Duration.ofSeconds(5))) {
            process.destroy();

            if (!process.waitFor(Duration.ofSeconds(1))) {
                process.destroyForcibly();
                process.waitFor(); // Chờ xác nhận process đã kết thúc
            }

            throw new TimeoutException("Process exceeded five seconds");
        }

        return process.exitValue();
    }
}
```

`destroy()` yêu cầu kết thúc process theo cách bình thường nếu nền tảng hỗ trợ; cách thực hiện phụ thuộc implementation và hệ điều hành. `supportsNormalTermination()` cho biết implementation có hỗ trợ kiểu kết thúc bình thường hay không. Nếu process không dừng trong khoảng grace period, `destroyForcibly()` yêu cầu hủy cưỡng bức. Sau lệnh này, process vẫn có thể còn sống trong một khoảng ngắn; gọi `waitFor()` để chờ kết thúc thực sự.

Trong ví dụ, stdout và stderr được redirect sang `DISCARD` vì chương trình không cần đọc output. Điều này tránh để pipe đầy khi đang chờ. Nếu cần lưu output, redirect sang file hoặc đọc các stream đúng cách.

## 5. Đọc stdout và stderr để tránh deadlock

Mặc định, `ProcessBuilder` nối ba stream của process con với Java process bằng pipe:

- `Process.getOutputStream()` là đầu ghi vào stdin của process con.
- `Process.getInputStream()` là đầu đọc stdout của process con.
- `Process.getErrorStream()` là đầu đọc stderr của process con.

Dung lượng buffer pipe có giới hạn. Nếu process con ghi nhiều dữ liệu ra stdout hoặc stderr trong khi Java chỉ gọi `waitFor()`, buffer có thể đầy. Process con bị chặn khi ghi, không thể hoàn tất; Java tiếp tục chờ process kết thúc. Đây là một dạng deadlock thường gặp.

### Gộp stderr vào stdout

Nếu không cần phân biệt output thường và thông báo lỗi, dùng `redirectErrorStream(true)` để gộp hai stream. Đọc output tới EOF rồi lấy exit code:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

record ProcessResult(int exitCode, List<String> output) {}

static ProcessResult capture(List<String> command)
        throws IOException, InterruptedException {

    ProcessBuilder builder = new ProcessBuilder(command)
            .redirectErrorStream(true);

    try (Process process = builder.start();
         BufferedReader reader = process.inputReader(StandardCharsets.UTF_8)) {

        // Chương trình mẫu không cần stdin; đóng để gửi EOF cho process con.
        process.getOutputStream().close();

        List<String> lines = reader.lines().toList();
        int exitCode = process.waitFor();

        return new ProcessResult(exitCode, List.copyOf(lines));
    }
}
```

Khi `redirectErrorStream(true)` được bật, stderr được gửi vào cùng destination với stdout; `getErrorStream()` trả về null input stream. Ví dụ dùng UTF-8 rõ ràng để đọc output. Nếu executable dùng encoding khác, hãy chọn `Charset` tương ứng.

`reader.lines().toList()` giữ toàn bộ output trong bộ nhớ. Chỉ dùng khi output có kích thước kiểm soát được. Với output lớn hoặc không giới hạn, đọc từng dòng và xử lý ngay, hoặc redirect trực tiếp ra file:

```java
ProcessBuilder builder = new ProcessBuilder(command)
        .redirectErrorStream(true)
        .redirectOutput(ProcessBuilder.Redirect.appendTo(logFile.toFile()));
```

Khi output đã được redirect ra file, `process.getInputStream()` không còn là pipe chứa output; nó là null input stream. Java có thể chờ process mà không cần drain stdout.

### Khi cần giữ stdout và stderr riêng biệt

Nếu cần phân biệt dữ liệu và lỗi, phải đọc cả hai stream đồng thời. Có thể dùng hai task đọc độc lập, mỗi task tiêu thụ một stream trong lúc thread điều phối chờ process. Không đọc hết stdout rồi mới đọc stderr nếu process có thể ghi đầy stderr trước khi đóng stdout; tình huống ngược lại cũng vậy.

Một lựa chọn đơn giản hơn là redirect một hoặc cả hai stream ra file riêng. Chọn cách phù hợp với dung lượng output, yêu cầu thứ tự log và khả năng xử lý lỗi đọc file.

### Gửi input cho process con

Nếu process con cần dữ liệu từ stdin, ghi bằng `outputWriter(Charset)` hoặc `getOutputStream()`. Đóng writer khi đã gửi xong để process con nhận EOF:

```java
try (var writer = process.outputWriter(StandardCharsets.UTF_8)) {
    writer.write("input line 1\n");
    writer.write("input line 2\n");
} // close() gửi EOF tới stdin của process con
```

Không giữ stdin mở nếu chương trình con cần EOF để kết thúc đọc dữ liệu. Đồng thời, nếu ghi lượng dữ liệu lớn, cần bảo đảm process con đang đọc stdin; nếu không, pipe stdin cũng có thể đầy và thao tác ghi ở Java bị chặn.

## 6. `Process.close()` trong Java 26

Java 26 bổ sung `Process.close()` và làm `Process` triển khai `Closeable`/`AutoCloseable`. Điều này cho phép quản lý vòng đời process bằng `try-with-resources`:

```java
try (Process process = new ProcessBuilder(command).start()) {
    // Giao tiếp với process, đọc output và chờ kết thúc.
    int exitCode = process.waitFor();
    handleExitCode(exitCode);
}
```

Hợp đồng của `close()`:

1. Đóng tất cả reader và writer stream của process.
2. Chờ process kết thúc.
3. Nếu thread bị interrupt trong lúc `close()` chờ, process bị hủy cưỡng bức; `close()` tiếp tục chờ process kết thúc.
4. Khôi phục interrupt status trước khi trả về hoặc ném `IOException`.
5. Nếu đóng stream phát sinh `IOException`, exception được ném sau khi process đã kết thúc; các lỗi đóng stream tiếp theo được thêm dưới dạng suppressed exceptions.
6. Gọi `close()` nhiều lần là an toàn; sau khi đã đóng, các lần tiếp theo không làm gì.

`close()` không phải API timeout. Nếu đóng các stream không khiến process kết thúc, `close()` có thể chờ lâu hoặc vô thời hạn. Nếu cần giới hạn thời gian, gọi `waitFor(Duration)` trước, rồi áp dụng `destroy()`/`destroyForcibly()` theo chính sách đã định.

Nếu cần dữ liệu stdout/stderr hoặc exit code, hãy đọc stream và chờ process trước khi gọi `close()`. Tài liệu Java 26 nêu rõ nội dung stream chưa đọc sẽ bị bỏ khi đóng; nếu exit code quan trọng, phải chờ process kết thúc trước khi close. Trong `try-with-resources`, quá trình đóng tự động diễn ra khi rời block.

### Xử lý interruption khi dùng try-with-resources

`waitFor()` ném `InterruptedException` và thông thường xóa interrupt status khi ném. Nếu exception được truyền ra khỏi block, `Process.close()` sẽ được gọi sau đó. Muốn `close()` nhận biết interrupt để hủy process nếu cần, khôi phục interrupt status trước khi thoát block:

```java
try (Process process = new ProcessBuilder(command).start()) {
    try {
        int exitCode = process.waitFor();
        handleExitCode(exitCode);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw interrupted;
    }
}
```

Khi `close()` chạy với interrupt status đã được đặt, thao tác chờ bên trong close bị interrupt; theo hợp đồng Java 26, close hủy cưỡng bức process, đợi process dừng và đặt lại interrupt status. Nếu không dùng `Process.close()` hoặc runtime mục tiêu thấp hơn Java 26, hãy tự quản lý việc hủy process và đóng stream trong `finally`.

Không dùng `close()` như cách lấy exit code: phương thức không trả về mã kết thúc. Hãy gọi `waitFor()` trước nếu cần mã kết thúc.

## 7. `onExit()` cho luồng xử lý bất đồng bộ

Nếu không muốn block thread hiện tại, dùng `Process.onExit()`. Phương thức trả về `CompletableFuture<Process>` hoàn tất khi process kết thúc, bất kể exit code là `0` hay khác `0`.

```java
Process process = new ProcessBuilder(command).start();

CompletableFuture<Integer> exitCodeFuture = process.onExit()
        .thenApply(Process::exitValue);

exitCodeFuture.thenAccept(code -> {
    if (code == 0) {
        System.out.println("Process succeeded");
    } else {
        System.err.println("Process failed: " + code);
    }
});
```

`onExit()` chỉ báo process đã kết thúc. Future không coi exit code khác `0` là lỗi tự động; ứng dụng phải kiểm tra `exitValue()` trong callback. Nếu cần lấy kết quả đồng bộ ở một thời điểm sau, có thể chờ future, nhưng khi đó thread gọi `get()` hoặc `join()` vẫn có thể bị block.

Khi có nhiều process chạy song song, `onExit()` cho phép gắn callback và tiếp tục làm việc khác. Tuy nhiên, vẫn phải quản lý stdout/stderr, đóng stream và giải phóng tài nguyên. Đừng coi future hoàn tất là thay thế cho việc đọc dữ liệu process.

## 8. Mã kết thúc và quy tắc xử lý ở tầng ứng dụng

Exit code là một số nguyên do chương trình con trả về cho hệ điều hành. Java chuyển giá trị đó cho ứng dụng thông qua `waitFor()` hoặc `exitValue()`; Java không diễn giải mã này theo một bảng chung cho mọi executable.

Một quy ước phổ biến:

| Exit code | Cách hiểu thường gặp |
|---|---|
| `0` | Hoàn tất thành công. |
| Khác `0` | Có lỗi hoặc một trạng thái không thành công theo hợp đồng của chương trình. |

Với công cụ do chính nhóm phát triển, hãy định nghĩa rõ các mã kết thúc trong tài liệu CLI, ví dụ `2` cho input không hợp lệ, `3` cho cấu hình sai, `4` cho lỗi nghiệp vụ. Không áp đặt những mã đó cho công cụ của bên thứ ba nếu tài liệu của công cụ không quy định.

Không giả định rằng các mã lỗi có ý nghĩa giống nhau giữa Windows, Linux và macOS. Cũng không suy luận rằng mọi mã khác `0` đều có cùng mức độ nghiêm trọng. Hãy ánh xạ mã kết thúc sang exception hoặc kết quả nghiệp vụ của ứng dụng theo hợp đồng executable:

```java
static void checkExitCode(int exitCode) throws IOException {
    switch (exitCode) {
        case 0 -> { /* thành công */ }
        case 2 -> throw new IOException("Input arguments are invalid");
        case 3 -> throw new IOException("Configuration is invalid");
        default -> throw new IOException(
                "External command failed with exit code " + exitCode
        );
    }
}
```

Các mã `2` và `3` trong ví dụ chỉ là hợp đồng minh họa của một executable do ứng dụng kiểm soát. Với chương trình khác, hãy đọc tài liệu chính thức của chương trình đó.

## 9. Các ngoại lệ và tình huống cần phân biệt

| Tình huống | API/ngoại lệ | Ý nghĩa và cách xử lý |
|---|---|---|
| Không tạo được process | `ProcessBuilder.start()` ném `IOException` | Executable không tồn tại, không đủ quyền, lỗi I/O hoặc lỗi hệ điều hành. Kiểm tra executable, đường dẫn, quyền và working directory. |
| Lệnh rỗng hoặc phần tử command null | `IndexOutOfBoundsException` hoặc `NullPointerException` | Kiểm tra danh sách command trước khi gọi `start()`. |
| Gọi `exitValue()` khi process còn chạy | `IllegalThreadStateException` | Dùng `waitFor()` hoặc kiểm tra trạng thái trước khi đọc. |
| Thread đang `waitFor()` bị interrupt | `InterruptedException` | Chờ kết thúc bị dừng; process không tự động bị hủy. Quyết định chính sách hủy và khôi phục interrupt status khi phù hợp. |
| Timeout của `waitFor(Duration)` | Trả về `false` | Process vẫn chạy; timeout không tự hủy. Gửi `destroy()` hoặc `destroyForcibly()` nếu chính sách yêu cầu. |
| Đọc/ghi stream lỗi | `IOException` | Xử lý I/O riêng; đóng stream và bảo đảm process được thu dọn. |
| `Process.close()` bị interrupt khi chờ | Không ném `InterruptedException`; hủy process cưỡng bức, đợi kết thúc rồi khôi phục interrupt status. | Đây là hành vi riêng của `close()` trong Java 26. |
| Process kết thúc với exit code khác `0` | Không tự ném exception | Kiểm tra mã và ánh xạ theo hợp đồng chương trình con. |

## 10. Các lỗi thiết kế thường gặp

| Cách làm dễ lỗi | Vì sao lỗi | Cách làm đúng |
|---|---|---|
| Gọi `waitFor()` trước khi đọc stdout/stderr | Pipe có buffer giới hạn; process con có thể bị block khi ghi. | Drain stream đồng thời, gộp stderr/stdout hoặc redirect ra file. |
| Gọi `exitValue()` để chờ | Phương thức không block; process còn chạy thì ném `IllegalThreadStateException`. | Dùng `waitFor()`. |
| Coi timeout `false` là process đã bị hủy | `waitFor(Duration)` chỉ kết thúc việc chờ, process tiếp tục chạy. | Chủ động destroy, chờ grace period rồi destroy forcibly nếu cần. |
| Coi interrupt của thread Java là hủy process | `InterruptedException` chỉ kết thúc thao tác chờ. | Áp dụng chính sách hủy process rõ ràng và chờ process dừng. |
| Không đóng stdin sau khi gửi input | Process con có thể đợi EOF mãi. | Đóng `OutputStream`/`BufferedWriter` sau khi gửi xong. |
| Chỉ đọc stdout mà bỏ stderr | stderr có thể đầy pipe và làm process con bị block. | Đọc hai stream đồng thời hoặc dùng `redirectErrorStream(true)`. |
| Dùng `Process.close()` như timeout | `close()` chờ process kết thúc và không có tham số thời hạn. | Dùng `waitFor(Duration)` và chính sách destroy trước khi close. |
| Cho rằng process biến mất khi mất reference | Process hệ điều hành có thể tiếp tục chạy sau khi Java không còn giữ `Process`. | Giữ handle, theo dõi completion và đóng stream/process đúng vòng đời. |
| Ghép command thành một chuỗi shell | Dấu cách và ký tự đặc biệt có thể bị phân tích sai; có thể tạo command injection. | Dùng `ProcessBuilder(List<String>)` và truyền từng argument riêng. |

## 11. Bài thực hành tổng hợp

Viết một hàm chạy công cụ kiểm tra với thời hạn 10 giây, lưu output vào file và trả về exit code. Mẫu dưới đây redirect stdout và stderr vào cùng file nên Java không cần đọc pipe:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

static int runTool(List<String> command, Path logFile)
        throws IOException, InterruptedException, TimeoutException {

    ProcessBuilder builder = new ProcessBuilder(command)
            .redirectErrorStream(true)
            .redirectOutput(ProcessBuilder.Redirect.to(logFile.toFile()));

    try (Process process = builder.start()) {
        if (!process.waitFor(Duration.ofSeconds(10))) {
            process.destroy();

            if (!process.waitFor(Duration.ofSeconds(2))) {
                process.destroyForcibly();
                process.waitFor();
            }

            throw new TimeoutException("Tool did not finish within 10 seconds");
        }

        int exitCode = process.exitValue();
        if (exitCode != 0) {
            System.err.println("Tool failed. See log: " + logFile);
        }
        return exitCode;
    }
}
```

Hàm này thể hiện các quyết định quan trọng:

1. Command là danh sách argument, không phải chuỗi shell.
2. stdout và stderr được gộp và ghi thẳng vào file.
3. `waitFor(Duration)` giới hạn thời gian chờ.
4. Khi timeout, hàm yêu cầu process kết thúc bình thường trước; nếu không được thì hủy cưỡng bức và chờ kết thúc.
5. Exit code chỉ được đọc sau khi đã xác nhận process kết thúc.
6. `try-with-resources` gọi `Process.close()` để đóng stream và bảo đảm vòng đời process được thu dọn trong Java 26.

Trong môi trường thật, hãy kiểm tra quyền ghi và dung lượng log file, giới hạn output, xác định executable theo cấu hình tin cậy, và tránh đưa secret vào command arguments vì danh sách tiến trình của hệ điều hành có thể hiển thị command line.

## 12. Tương thích Java và trạng thái API

Các API trong bài là Java SE API ổn định:

| API | Có từ | Trạng thái trong Java 26 |
|---|---:|---|
| `Process.waitFor()` | Java 1.0 | API ổn định. |
| `Process.exitValue()` | Java 1.0 | API ổn định. |
| `ProcessBuilder.start()` | Java 1.5 | Cách được ưu tiên để tạo process. |
| `waitFor(long, TimeUnit)` | Java 1.8 | Vẫn được hỗ trợ. |
| `Process.onExit()` | Java 9 | API bất đồng bộ ổn định. |
| `Process.inputReader()` / `outputWriter()` | Java 17 | API đọc/ghi text theo charset, vẫn hiện hành. |
| `waitFor(Duration)` | Java 24 | API timeout theo `Duration`, vẫn hiện hành. |
| `Process.close()` | Java 26 | Mới trong Java 26; `Process` triển khai `Closeable`/`AutoCloseable`. |

Không cần `--enable-preview` hoặc `--add-modules` để dùng `Process`, `ProcessBuilder`, `Duration` hay `ProcessHandle`; tất cả thuộc Java SE và module `java.base`. Khi biên dịch với JDK mới nhưng cần chạy trên Java 26, có thể giới hạn API bằng `javac --release 26`.

Lưu ý khi hỗ trợ runtime cũ hơn Java 26: `Process.close()` chưa tồn tại trước Java 26, vì vậy không thể gọi method này nếu ứng dụng phải chạy trên JDK 25 trở xuống. Các phương thức `waitFor`, `exitValue`, `waitFor(Duration)` và `onExit` có mốc phát hành riêng trong bảng trên. Hãy chọn API theo baseline runtime thực tế.

## 13. Checklist trước khi triển khai

- [ ] Đã dùng `ProcessBuilder` và truyền command/argument thành các phần tử riêng.
- [ ] Đã xử lý `IOException` nếu không tạo được process.
- [ ] Đã dùng `waitFor()` để lấy exit code hoặc `waitFor(Duration)` để giới hạn thời gian.
- [ ] Không gọi `exitValue()` khi chưa xác nhận process đã kết thúc.
- [ ] Đã hiểu `waitFor(Duration)` trả `false` không tự hủy process.
- [ ] Đã định nghĩa ý nghĩa exit code theo hợp đồng executable; chỉ xem `0` là thành công theo quy ước chung.
- [ ] Đã đọc stdout và stderr, gộp chúng hoặc redirect để tránh pipe đầy và deadlock.
- [ ] Đã đóng stdin khi process con cần EOF.
- [ ] Đã có chính sách destroy/grace period/destroy forcibly khi timeout hoặc cancellation.
- [ ] Đã xử lý `InterruptedException` và interrupt status đúng cách.
- [ ] Đã dùng `Process.close()` trong Java 26 để quản lý stream và vòng đời process; không nhầm close với timeout.
- [ ] Đã kiểm tra giới hạn output, quyền file log và không truyền secret qua command line.
- [ ] Đã xác nhận baseline JDK và không bật preview/incubator không cần thiết.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Process`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html)
- [Java SE 26 — `ProcessBuilder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java SE 26 — `ProcessHandle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html)
- [Java SE 26 — `ProcessBuilder.Redirect`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.Redirect.html)
- [Java SE 26 — `Duration`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [Java SE 26 Core Libraries Guide — Process API Classes and Interfaces](https://docs.oracle.com/en/java/javase/26/core/java-core-libraries-developer-guide.pdf)

*Cập nhật nội dung: 27-11-2026. `waitFor`, `exitValue`, `waitFor(Duration)` và `Process.close()` là API Java SE ổn định trong JDK 26; kiểm tra hợp đồng exit code và cách quản lý stream của executable cụ thể trước khi triển khai.*
