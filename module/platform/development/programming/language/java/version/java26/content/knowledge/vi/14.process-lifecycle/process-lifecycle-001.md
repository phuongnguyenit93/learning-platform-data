# Process triển khai AutoCloseable và Closeable từ Java 26

Khi Java khởi chạy một chương trình bên ngoài bằng `ProcessBuilder.start()`, ứng dụng nhận về một đối tượng `Process` để gửi dữ liệu vào stdin, đọc stdout/stderr, chờ kết thúc và lấy exit code. Trước Java 26, `Process` không thể được đặt trực tiếp trong phần resource của `try-with-resources`; lập trình viên phải tự đóng các stream và quản lý vòng đời tiến trình. Từ Java 26, `Process` triển khai `Closeable` và do đó cũng là `AutoCloseable`.

Điểm mới này giúp việc giải phóng tài nguyên của tiến trình con rõ ràng hơn. Khi `try` kết thúc, `Process.close()` đóng các reader/writer của tiến trình và chờ tiến trình kết thúc. Tuy nhiên, `close()` không phải một lệnh timeout và không đồng nghĩa với `destroy()`: nếu chương trình con không thoát sau khi các stream bị đóng, lời gọi có thể tiếp tục chờ. Muốn kiểm soát thời gian chạy, ứng dụng vẫn cần `waitFor(Duration)`, `destroy()` và `destroyForcibly()` theo chính sách riêng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích thay đổi của `Process` trong Java 26 và mối quan hệ giữa `Closeable` với `AutoCloseable`.
- Quản lý tiến trình con bằng `try-with-resources` và hiểu chính xác hành vi của `Process.close()`.
- Đọc stdout/stderr, gửi stdin, đóng input để báo EOF và lấy exit code đúng thứ tự.
- Tránh deadlock do pipe buffer khi chương trình con ghi nhiều dữ liệu.
- Kết hợp `waitFor(Duration)`, `destroy()` và `destroyForcibly()` để đặt timeout.
- Phân biệt đóng stream, đóng đối tượng `Process` và yêu cầu hệ điều hành chấm dứt process.
- Đánh giá tương thích khi biên dịch cho JDK trước Java 26.

## 1. Process quản lý một tiến trình hệ điều hành và các kênh I/O

`ProcessBuilder` mô tả lệnh, đối số, working directory, environment và cách chuyển hướng standard I/O. Gọi `start()` tạo tiến trình hệ điều hành và trả về một `Process` đại diện cho tiến trình đó.

Theo mặc định, Java kết nối ba kênh chuẩn của tiến trình con với các pipe mà tiến trình cha có thể truy cập:

| Phía tiến trình con | API phía Java | Hướng dữ liệu |
|---|---|---|
| stdin | `getOutputStream()` hoặc `outputWriter()` | Java ghi vào; chương trình con đọc |
| stdout | `getInputStream()` hoặc `inputReader()` | Chương trình con ghi; Java đọc |
| stderr | `getErrorStream()` hoặc `errorReader()` | Chương trình con ghi; Java đọc |

Tên API nhìn từ phía tiến trình cha. Vì vậy `Process.getOutputStream()` là stream Java ghi dữ liệu để chương trình con nhận qua stdin; `Process.getInputStream()` là stream Java đọc stdout của chương trình con.

Ví dụ khởi chạy một lệnh:

```java
import java.io.IOException;
import java.util.List;

public class StartProcess {
    public static void main(String[] args) throws IOException {
        List<String> command = List.of("java", "--version");
        ProcessBuilder builder = new ProcessBuilder(command);

        Process process = builder.start();
        System.out.println("PID: " + process.pid());
    }
}
```

Ví dụ này chỉ minh họa việc tạo tiến trình. Khi ứng dụng không còn cần tiến trình hoặc các kênh I/O, phải quản lý vòng đời và đóng tài nguyên. Không được giả định rằng bỏ tham chiếu tới `Process` sẽ tự động giết tiến trình; tiến trình con có thể tiếp tục chạy độc lập.

Nên truyền executable và từng đối số thành các phần tử riêng của `List<String>` hoặc varargs cho `ProcessBuilder`. Tránh ghép toàn bộ lệnh thành một chuỗi shell rồi nối dữ liệu không tin cậy vào đó. `ProcessBuilder.start()` là cách được khuyến nghị để tạo process; `Runtime.exec` vẫn tồn tại nhưng không cần dùng cho ví dụ mới.

## 2. Thay đổi trong Java 26: Process là Closeable và AutoCloseable

Từ Java 26, khai báo API của `Process` triển khai `Closeable`. `Closeable` kế thừa `AutoCloseable`, nên một `Process` có thể được quản lý trực tiếp trong `try-with-resources`:

```java
try (Process process = new ProcessBuilder("java", "--version").start()) {
    // Đọc output, chờ process và kiểm tra exit code.
}
```

Các điểm chính của `Process.close()` trong Java 26:

- Đóng tất cả reader và writer gắn với standard input, output và error của process.
- Chờ tiến trình hệ điều hành kết thúc.
- Có tính idempotent: gọi `close()` lần nữa sau khi process đã đóng không có tác dụng.
- Ném `IOException` nếu việc đóng một hoặc nhiều stream gặp lỗi; các lỗi đóng bổ sung được gắn dưới dạng suppressed exception.
- Nếu thread gọi `close()` bị interrupt trong lúc chờ process kết thúc, implementation sẽ gọi `destroyForcibly()`, tiếp tục chờ process kết thúc rồi khôi phục trạng thái interrupted trước khi trả về hoặc ném `IOException`.
- Nếu dữ liệu stdout hoặc stderr còn cần dùng, phải đọc trước khi gọi `close()`. Dữ liệu chưa đọc hết sẽ bị bỏ đi.
- Nếu cần exit code, phải gọi `waitFor()` trước `close()`; `close()` không trả về exit code.

Phương thức `close()` được bổ sung từ Java 26. Nó là API chính thức, không phải preview hoặc incubator, không cần `--enable-preview`.

## 3. close() không phải destroy()

Ba thao tác thường bị nhầm lẫn:

| Thao tác | Ý nghĩa | Kết quả mong đợi |
|---|---|---|
| Đóng một stream, ví dụ `process.getOutputStream().close()` | Kết thúc một kênh giao tiếp | Đầu bên kia nhận EOF/đóng kênh; tiến trình con có thể thoát nếu nó xử lý EOF |
| `process.close()` | Đóng các reader/writer của process rồi chờ process kết thúc | Giải phóng tài nguyên I/O và đợi process thoát; không có timeout riêng |
| `process.destroy()` / `destroyForcibly()` | Yêu cầu hệ điều hành chấm dứt tiến trình | `destroy()` phụ thuộc nền tảng; `destroyForcibly()` yêu cầu kết thúc cưỡng bức |

Đóng stream ở một đầu không trực tiếp gửi lệnh kill cho tiến trình ở đầu kia. Thông thường, chương trình con nhận EOF trên stdin rồi tự kết thúc. Nếu chương trình bỏ qua EOF, đợi thêm dữ liệu hoặc đang chạy công việc không liên quan tới stdin, `Process.close()` có thể chờ rất lâu.

Vì vậy, không dùng `close()` làm cơ chế timeout cho một tiến trình không đáng tin cậy hoặc có thể treo. Hãy đặt thời hạn bằng `waitFor(Duration)`; khi hết hạn, yêu cầu chấm dứt và chờ process thật sự kết thúc trước khi rời phạm vi quản lý.

## 4. Ví dụ đọc output và lấy exit code với try-with-resources

Khi chương trình con được biết là tạo output hữu hạn rồi kết thúc, có thể gộp stdout và stderr để chỉ cần đọc một pipe. Sau khi đọc hết dữ liệu, gọi `waitFor()` để lấy exit code, rồi để `try-with-resources` đóng reader và process:

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

        // Không gửi dữ liệu stdin; đóng để chương trình con nhận EOF.
        process.getOutputStream().close();

        // Chỉ phù hợp với lệnh có output hữu hạn và sẽ kết thúc.
        List<String> output = reader.lines().toList();

        // Phải lấy exit code trước khi Process.close() được gọi.
        int exitCode = process.waitFor();
        return new ProcessResult(exitCode, output);
    }
}
```

Khi thoát khỏi block, tài nguyên được đóng theo thứ tự ngược với thứ tự khai báo: `reader` trước, `process` sau. Reader đã đọc đến EOF nên không còn dữ liệu cần giữ. `Process.close()` đóng các stream còn lại và `waitFor()` trở về ngay vì process đã kết thúc.

Trong ví dụ, `redirectErrorStream(true)` gộp stderr vào stdout. Nếu cần phân biệt hai loại output, không nên đọc hết stdout rồi mới đọc stderr trong khi process đang chạy; hãy đọc đồng thời cả hai stream hoặc chuyển hướng chúng tới file riêng. Nếu không, pipe của stream chưa được đọc có thể đầy và làm chương trình con bị block.

Không dùng `reader.lines().toList()` cho output không giới hạn hoặc quá lớn vì toàn bộ kết quả sẽ được giữ trong bộ nhớ. Với log lớn, đọc từng dòng và ghi ra file/consumer hoặc dùng `ProcessBuilder.redirectOutput(...)`.

## 5. Gửi dữ liệu vào stdin và báo EOF

Khi tiến trình con đọc stdin cho đến EOF, phải đóng writer sau khi gửi xong dữ liệu. `flush()` chỉ đẩy dữ liệu đang buffer; nó không báo rằng đầu vào đã kết thúc.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.util.List;

static int sendText(List<String> command, String text)
        throws Exception {

    ProcessBuilder builder = new ProcessBuilder(command)
            .redirectErrorStream(true);

    try (Process process = builder.start();
         BufferedWriter writer = process.outputWriter(StandardCharsets.UTF_8);
         BufferedReader reader = process.inputReader(StandardCharsets.UTF_8)) {

        writer.write(text);
        writer.newLine();
        writer.close(); // Gửi EOF cho stdin của chương trình con.

        reader.lines().forEach(System.out::println);
        return process.waitFor();
    }
}
```

Ví dụ này minh họa quy trình gửi dữ liệu rồi đọc phản hồi. Lệnh thực tế phải được chọn sao cho đọc stdin và trả lời theo giao thức đã biết. Khi dùng các resource trong cùng một `try`, writer và reader được đóng trước process. `Process.close()` đóng các stream một lần nữa; việc đóng process là idempotent và việc đóng stream đã đóng thường không có tác dụng.

Nếu chương trình con vừa đọc stdin vừa ghi lượng lớn stdout, hãy bảo đảm output được drain trong lúc input được gửi. Chỉ ghi toàn bộ input trước rồi mới đọc output có thể deadlock nếu buffer stdout đầy trong khi chương trình con đang chờ Java đọc.

## 6. Tránh deadlock do stdout và stderr

Standard I/O của process thường được nối bằng pipe có dung lượng hữu hạn. Nếu chương trình con ghi đầy pipe stdout hoặc stderr, thao tác ghi của nó sẽ block cho đến khi tiến trình cha đọc dữ liệu. Nếu Java đang chờ process kết thúc mà không đọc pipe, hai bên có thể chờ nhau vô hạn.

Các cách xử lý phù hợp:

- Dùng `redirectErrorStream(true)` khi không cần phân biệt stdout và stderr; đọc một pipe duy nhất.
- Dùng `redirectOutput(file)` và `redirectError(file)` hoặc `Redirect.appendTo(file)` để OS ghi ra file thay vì pipe trong bộ nhớ.
- Nếu phải đọc hai stream riêng, chạy hai tác vụ đọc đồng thời; chỉ gọi `waitFor()` sau khi việc drain đã được tổ chức đúng.
- Không giữ output vô hạn trong `List<String>` hoặc `StringBuilder`; giới hạn dung lượng hoặc stream thẳng ra nơi lưu trữ.
- Nếu tiến trình cần input, gửi dữ liệu và đóng stdin đúng thời điểm; không để chương trình con chờ EOF trong khi Java lại chờ stdout.

Ví dụ chuyển hướng output và error ra file:

```java
import java.io.File;
import java.util.List;

ProcessBuilder builder = new ProcessBuilder(List.of("tool", "--run"));
builder.redirectOutput(new File("tool-output.log"));
builder.redirectError(new File("tool-error.log"));

try (Process process = builder.start()) {
    process.getOutputStream().close(); // Không có input từ Java.
    int exitCode = process.waitFor();
    System.out.println("Exit code: " + exitCode);
}
```

Khi stdout/stderr được redirect, `getInputStream()` hoặc `getErrorStream()` tương ứng trả về null input stream; đọc nó sẽ nhận EOF ngay. Không cố đọc cùng một kênh qua cả `getInputStream()` và `inputReader()` trên cùng process, vì reader có buffer riêng và hai cách đọc sẽ cạnh tranh dữ liệu.

## 7. Đặt timeout và chấm dứt tiến trình có kiểm soát

`Process.waitFor(Duration)` có từ Java 24 và tiếp tục dùng được trong Java 26. Phương thức trả `true` nếu process đã kết thúc trong thời hạn, `false` nếu hết thời gian. Đây là công cụ để quyết định khi nào cần yêu cầu chấm dứt; `Process.close()` tự nó không nhận timeout.

Ví dụ dưới đây redirect output ra file để tránh pipe đầy, đóng stdin vì không cần gửi dữ liệu, chờ trong thời hạn, sau đó thử chấm dứt bình thường trước khi dùng cưỡng bức:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

static int runWithTimeout(List<String> command, Path logFile)
        throws IOException, InterruptedException {

    ProcessBuilder builder = new ProcessBuilder(command)
            .redirectErrorStream(true)
            .redirectOutput(logFile.toFile());

    try (Process process = builder.start()) {
        process.getOutputStream().close();

        if (!process.waitFor(Duration.ofSeconds(30))) {
            process.destroy();

            if (!process.waitFor(Duration.ofSeconds(2))) {
                process.destroyForcibly();
                process.waitFor();
            }

            throw new IOException("Process timed out: " + process.pid());
        }

        return process.exitValue();
    }
}
```

Quy trình này có các bước:

1. Đợi tối đa 30 giây.
2. Nếu process còn sống, gọi `destroy()` để yêu cầu hệ điều hành kết thúc theo cách bình thường nếu nền tảng hỗ trợ.
3. Đợi thêm 2 giây.
4. Nếu vẫn còn sống, gọi `destroyForcibly()` và chờ process kết thúc.
5. Khi thoát block, `Process.close()` đóng stream và xác nhận process đã kết thúc.

`destroy()` có hành vi phụ thuộc nền tảng; kiểm tra `supportsNormalTermination()` nếu logic cần biết implementation có hỗ trợ kết thúc bình thường hay không. `destroyForcibly()` cũng không bảo đảm process biến mất ngay lập tức; nếu cần exit status, phải đợi `waitFor()` rồi mới gọi `exitValue()`.

Đoạn code trên dùng `IOException` để báo timeout cho ngắn gọn. Trong ứng dụng, có thể định nghĩa `ProcessTimeoutException` riêng để phân biệt timeout với lỗi đọc/ghi. Nếu thread bị interrupt trong lúc `waitFor`, truyền tiếp `InterruptedException` hoặc xử lý theo chính sách của ứng dụng. Khi block thoát do exception, `Process.close()` vẫn được gọi; nếu close đang chờ mà thread bị interrupt, nó sẽ force-destroy process, tiếp tục đợi rồi khôi phục interrupt status.

## 8. Thứ tự đóng resource và suppressed exception

`try-with-resources` đóng resource theo thứ tự ngược với thứ tự khai báo. Ví dụ:

```java
try (Process process = builder.start();
     BufferedReader output = process.inputReader(StandardCharsets.UTF_8);
     BufferedReader error = process.errorReader(StandardCharsets.UTF_8)) {
    // Dùng các resource.
}
```

Thứ tự đóng là `error`, `output`, rồi `process`. Khi `Process.close()` chạy, nó đóng tất cả reader/writer còn gắn với process và chờ tiến trình kết thúc. Nếu một reader đã được đóng, process không cần dùng nó nữa. Khi có exception trong thân `try` và việc đóng resource cũng ném exception, exception lúc đóng được giữ dưới dạng suppressed exception trên exception chính.

`Process.close()` ném `IOException`, vì vậy phương thức gọi cần khai báo hoặc xử lý ngoại lệ. Không bỏ qua lỗi close nếu ứng dụng cần bảo đảm tiến trình và các handle hệ điều hành đã được giải phóng.

Nếu cần exit code, gọi `waitFor()` trước khi đóng process. Nếu gọi `close()` trước, dữ liệu chưa đọc có thể bị bỏ và `close()` không trả lại exit code. Sau khi process đã kết thúc, có thể gọi `exitValue()`; nếu gọi khi process còn chạy, phương thức ném `IllegalThreadStateException`.

## 9. Process.close() không tự quản lý cả cây process

`Process` đại diện cho một tiến trình. Chương trình con có thể tạo thêm process con hoặc process cháu. Đóng đối tượng `Process` không nên được hiểu là tự động thu gom mọi descendant trong mọi nền tảng.

Nếu ứng dụng cần quản lý cây process:

- Dùng `process.toHandle()` để lấy `ProcessHandle`.
- Dùng `children()` hoặc `descendants()` để lấy snapshot các tiến trình con/tiến trình hậu duệ.
- Áp dụng chính sách chấm dứt phù hợp cho các handle cần quản lý, rồi chờ chúng kết thúc.
- Xem xét đặc điểm nền tảng, quyền của user và khả năng process tạo thêm descendant trong lúc đang thu thập snapshot.

`ProcessHandle.descendants()` trả về snapshot, không phải một nhóm process có vòng đời được ràng buộc như structured concurrency. Nếu chương trình con tạo descendant sau thời điểm snapshot, descendant mới có thể không nằm trong danh sách đã lấy. Ứng dụng chạy tool lâu dài cần có chính sách process-tree riêng hoặc dùng cơ chế quản lý tiến trình của hệ điều hành/container.

## 10. So sánh với JDK trước Java 26

| Khả năng | JDK 25 trở xuống | Java 26 trở lên |
|---|---|---|
| `ProcessBuilder.start()` | Có | Có |
| `waitFor()` và `waitFor(Duration)` | Có; `Duration` có từ JDK 24 | Có |
| `inputReader`, `errorReader`, `outputWriter` | Có từ JDK 17 | Có |
| `Process` triển khai `Closeable`/`AutoCloseable` | Không | Có từ JDK 26 |
| Dùng `try (Process p = builder.start())` | Không biên dịch vì `Process` chưa là `AutoCloseable` | Biên dịch được |
| `Process.close()` | Không có | Có từ JDK 26; đóng stream và chờ process kết thúc |

Nếu ứng dụng vẫn cần biên dịch với `--release 25` hoặc chạy trên JDK 25, không thể dùng `Process` làm resource trực tiếp. Khi đó phải đóng stdin/stdout/stderr một cách tường minh, chờ process và có nhánh timeout/chấm dứt riêng. `ProcessBuilder`, `waitFor`, `destroy` và các API I/O vẫn sử dụng được; phần mới của Java 26 chủ yếu đơn giản hóa việc gom trách nhiệm đóng vào `try-with-resources`.

Không bật `--enable-preview` cho tính năng này. Nếu compiler báo không tìm thấy `close()` hoặc không cho dùng `Process` trong try-with-resources, hãy kiểm tra `javac --version`, `--release` và JDK thực sự dùng để biên dịch.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `try (Process p = ...)` không biên dịch | Đang biên dịch bằng JDK trước 26 hoặc `--release` thấp hơn 26 | Biên dịch bằng JDK 26+ hoặc dùng cách quản lý thủ công nếu cần target cũ |
| Ứng dụng treo khi đọc output | Process không kết thúc hoặc chương trình con chờ thêm input | Đóng stdin khi đã gửi xong; dùng timeout và kiểm tra giao thức con |
| Process treo dù Java đã gọi `waitFor()` | stdout/stderr pipe đầy vì Java chưa đọc | Drain cả hai stream đồng thời hoặc redirect ra file |
| `close()` không trả về | Process chưa kết thúc sau khi các stream bị đóng | Dùng `waitFor(Duration)` trước đó; nếu timeout thì destroy và chờ kết thúc |
| Output bị thiếu sau khi gọi `close()` | Có dữ liệu chưa được đọc hết | Đọc stdout/stderr đến EOF trước khi close |
| Không lấy được exit code | Gọi `exitValue()` khi process còn chạy hoặc gọi close trước khi wait | Gọi `waitFor()` trước, sau đó lấy exit code |
| Chỉ stdout có dữ liệu, stderr mất | Chỉ đọc một stream hoặc redirect đã thay đổi stream còn lại | Kiểm tra `redirectErrorStream`, đọc hai stream đồng thời hoặc chuyển hướng riêng |
| Process con thoát nhưng process cháu còn chạy | Chỉ quản lý process trực tiếp | Kiểm tra `ProcessHandle.descendants()` và quản lý process tree riêng |

## 12. Checklist khi quản lý Process

- [ ] Dùng `ProcessBuilder` và truyền command/arguments tách biệt.
- [ ] Xác định rõ stdin có cần dữ liệu không; đóng writer để báo EOF khi đã gửi xong.
- [ ] Chọn cách xử lý stdout/stderr: gộp, drain đồng thời hoặc redirect ra file.
- [ ] Không để pipe buffer đầy trong khi Java đang chờ process kết thúc.
- [ ] Đọc hết dữ liệu cần giữ trước khi gọi `Process.close()`.
- [ ] Gọi `waitFor()` hoặc `waitFor(Duration)` trước khi cần exit code.
- [ ] Có timeout và chính sách `destroy()`/`destroyForcibly()` cho tiến trình có thể treo.
- [ ] Dùng `try-with-resources` trên Java 26+ để process và stream được đóng.
- [ ] Không giả định process bị kill chỉ vì Java mất reference tới đối tượng `Process`.
- [ ] Quản lý descendants riêng nếu công cụ con có thể tạo process khác.

## 13. Bài tập thực hành

Viết một tiện ích Java chạy chương trình ngoài, gửi một dòng đầu vào, thu thập output và trả về exit code. Sau đó mở rộng để hỗ trợ timeout.

**Yêu cầu:**

1. Tạo `ProcessBuilder` từ danh sách command và arguments.
2. Dùng `try-with-resources` để quản lý `Process` trên JDK 26.
3. Gửi input qua `outputWriter(StandardCharsets.UTF_8)` và đóng writer để báo EOF.
4. Dùng `redirectErrorStream(true)` hoặc thiết kế hai reader chạy đồng thời.
5. Đọc output trước khi đóng process; kiểm tra exit code bằng `waitFor()`.
6. Thêm `waitFor(Duration)` để giới hạn thời gian thực thi.
7. Khi hết hạn, gọi `destroy()`, chờ một khoảng grace period, rồi dùng `destroyForcibly()` nếu cần.
8. Tạo một process con tạo nhiều output để kiểm tra cách tránh deadlock.
9. Thử biên dịch cùng source với `--release 25` và `--release 26`; giải thích khác biệt khi `Process` tham gia try-with-resources.

**Kết quả mong đợi:**

- Java đóng stream và process tự động khi ra khỏi block `try`.
- Ứng dụng đọc được dữ liệu trước khi `close()` có thể bỏ dữ liệu chưa đọc.
- Exit code được lấy trước khi đóng process.
- Timeout không phụ thuộc vào `close()`; ứng dụng chủ động destroy và chờ process kết thúc.
- Người học giải thích được vì sao cần drain stdout/stderr và vì sao mất reference không làm process tự kết thúc.
- Mã nguồn dùng `Process` như resource cần JDK 26 trở lên và không cần preview flag.

## Tài liệu tham khảo

- [Process — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): hợp đồng `Process.close()`, I/O streams, wait, destroy và vòng đời tài nguyên.
- [ProcessBuilder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): tạo process, environment, working directory và redirect standard I/O.
- [JDK 26 Release Notes — Process Implements AutoCloseable and Closeable](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận `Process.close()` được bổ sung từ JDK 26.
- [Closeable — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Closeable.html): quan hệ kế thừa với `AutoCloseable` và hợp đồng đóng tài nguyên.
- [AutoCloseable — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): cách `try-with-resources` gọi `close()` và xử lý ngoại lệ.
- [ProcessHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html): giám sát process, children và descendants.
