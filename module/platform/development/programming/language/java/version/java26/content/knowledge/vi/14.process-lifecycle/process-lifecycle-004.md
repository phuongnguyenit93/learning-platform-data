# Process.close đóng luồng và chờ tiến trình kết thúc

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò mới của `Process.close()` trong JDK 26.
- Phân biệt đóng process streams, chờ tiến trình kết thúc và yêu cầu hệ điều hành hủy tiến trình.
- Dùng `Process` với try-with-resources để giải phóng stream và tài nguyên native.
- Đọc stdout/stderr trước khi đóng để không làm mất dữ liệu cần thiết.
- Tránh deadlock do pipe đầy hoặc tiến trình con đang chờ stdin.
- Lựa chọn giữa `close()`, `waitFor()`, `destroy()` và `destroyForcibly()`.
- Xử lý timeout, interruption và lỗi I/O trong vòng đời process.

## 1. Process.close() trong JDK 26

Java tạo tiến trình hệ điều hành bằng `ProcessBuilder.start()`. Phương thức trả về một đối tượng `Process` để ứng dụng giao tiếp với tiến trình con, đọc kết quả, gửi dữ liệu, chờ kết thúc hoặc yêu cầu hủy.

Từ JDK 26, `Process` có phương thức:

~~~java
public void close() throws IOException
~~~

`Process.close()` đóng các reader và writer streams liên quan đến process, sau đó chờ tiến trình kết thúc. Phương thức có tính idempotent: gọi lại trên một `Process` đã đóng không thực hiện thêm hành động.

Đây là API Java SE được bổ sung từ JDK 26, không phải preview hay incubator. Không cần `--enable-preview` để sử dụng.

Điểm quan trọng là `close()` không trả về exit code và không tương đương với `destroy()`. Việc đóng các pipe có thể khiến chương trình con nhận EOF hoặc lỗi ghi và tự kết thúc, nhưng `close()` không gửi yêu cầu hủy bình thường như `destroy()`. Nếu tiến trình vẫn chạy sau khi các stream đóng, `close()` tiếp tục chờ. Nếu luồng gọi bị interrupt trong lúc chờ, phương thức sẽ forcibly destroy process rồi tiếp tục chờ đến khi process kết thúc.

## 2. Process quản lý những luồng nào?

Các stream của `Process` được đặt tên theo góc nhìn của tiến trình Java cha:

| API | Hướng dữ liệu | Ý nghĩa |
|---|---|---|
| `getOutputStream()` / `outputWriter()` | Java cha → stdin của tiến trình con | Gửi dữ liệu hoặc lệnh cho chương trình con |
| `getInputStream()` / `inputReader()` | stdout của tiến trình con → Java cha | Đọc kết quả thông thường |
| `getErrorStream()` / `errorReader()` | stderr của tiến trình con → Java cha | Đọc thông báo lỗi và chẩn đoán |

Tên `getOutputStream()` dễ gây nhầm: đây là luồng mà Java cha ghi vào, nhưng dữ liệu đi vào standard input của tiến trình con.

Các phương thức reader/writer tiện dụng như `inputReader()`, `errorReader()` và `outputWriter()` có từ JDK 17. Có thể chọn charset tường minh bằng overload nhận `Charset`.

Không nên trộn `getInputStream()` với `inputReader()` trên cùng một process. Reader có thể đọc trước và buffer byte; nếu cùng lúc đọc raw stream, dữ liệu sẽ bị chia sẻ không xác định giữa hai consumer. Hãy chọn một cách đọc cho mỗi luồng.

## 3. close() thực hiện theo thứ tự nào?

Hợp đồng API JDK 26 quy định quy trình:

1. Đóng các reader và writer streams của process.
2. Chờ process kết thúc.
3. Nếu đóng stream phát sinh `IOException`, vẫn chờ process kết thúc rồi mới ném lỗi.
4. Nếu nhiều stream cùng ném `IOException`, các lỗi tiếp theo được thêm vào lỗi đầu tiên dưới dạng suppressed exceptions.

Nếu thread đang chờ bị interrupt, `close()` forcibly destroys process và vẫn tiếp tục chờ đến khi process kết thúc. Trước khi trả về hoặc ném `IOException`, phương thức khôi phục interrupt status của thread.

Điều này giúp try-with-resources có thể giải phóng các stream và đợi process trong cả đường chạy bình thường lẫn đường thoát do exception.

Tuy nhiên, `close()` không có tham số timeout. Nếu process không kết thúc sau khi các stream đóng, lời gọi có thể chờ lâu hoặc vô hạn. Với tiến trình cần giới hạn thời gian, hãy thiết kế timeout và chính sách hủy riêng bằng `waitFor(Duration)` cùng `destroyForcibly()`.

## 4. Dùng try-with-resources để tự động đóng Process

Ví dụ chạy một chương trình ngắn, đọc toàn bộ output rồi kiểm tra exit code:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

public final class ProcessCapture {
    static List<String> captureVersion() throws IOException, InterruptedException {
        ProcessBuilder builder = new ProcessBuilder("java", "-version")
            .redirectErrorStream(true);

        try (Process process = builder.start()) {
            List<String> lines;

            try (BufferedReader output =
                     process.inputReader(StandardCharsets.UTF_8)) {
                lines = output.readAllLines();
            }

            int exitCode = process.waitFor();

            if (exitCode != 0) {
                throw new IOException("java -version exited with " + exitCode);
            }

            return lines;
        }
    }
}
~~~

Trong ví dụ:

- `redirectErrorStream(true)` gộp stderr vào stdout để chỉ cần đọc một pipe.
- `readAllLines()` đọc đến EOF. Ví dụ giả định chương trình kết thúc sau khi in phiên bản.
- `waitFor()` lấy exit status trước khi đóng process.
- Khi rời khối try, `Process.close()` đóng các stream còn lại và chờ process kết thúc. Process đã kết thúc nên bước chờ thường trả về ngay.

Ví dụ dùng UTF-8 vì giả định chương trình con xuất dữ liệu theo UTF-8. Với chương trình sử dụng encoding khác, chọn đúng charset hoặc dùng raw byte stream.

`readAllLines()` giữ toàn bộ output trong bộ nhớ. Với output lớn, hãy đọc từng dòng hoặc từng khối và xử lý dần thay vì nạp toàn bộ vào một collection.

## 5. Đọc output trước khi gọi close()

Nếu dữ liệu stdout hoặc stderr còn cần dùng, phải đọc trước khi gọi `close()`. Nội dung của stream chưa được đọc đến EOF sẽ bị discard hoặc bỏ qua khi `close()` đóng stream.

Ví dụ không nên làm:

~~~java
try (Process process = new ProcessBuilder(command).start()) {
    // Không đọc stdout hoặc stderr.
}
// close() đóng các stream; dữ liệu chưa đọc có thể mất.
~~~

Nếu ứng dụng cần output để xác định kết quả, hãy đọc nó trước khi đóng. Nếu không cần output, chuyển hướng stream ngay từ `ProcessBuilder` để tránh tạo pipe mà ứng dụng không tiêu thụ:

~~~java
ProcessBuilder builder = new ProcessBuilder(command)
    .redirectOutput(ProcessBuilder.Redirect.DISCARD)
    .redirectError(ProcessBuilder.Redirect.DISCARD);

try (Process process = builder.start()) {
    int exitCode = process.waitFor();
    // Kiểm tra exitCode trước khi rời khối.
}
~~~

Có thể dùng `Redirect.to(file)` để lưu output vào file hoặc `Redirect.INHERIT` để cho tiến trình con dùng luồng tương ứng của tiến trình cha. Chọn cách chuyển hướng theo yêu cầu vận hành và bảo mật.

## 6. Tránh deadlock khi stdout và stderr cùng được sử dụng

Pipe giữa hai process có bộ đệm giới hạn. Nếu chương trình con ghi nhiều dữ liệu vào stdout hoặc stderr mà Java cha không đọc kịp, bộ đệm có thể đầy. Khi đó, chương trình con bị block lúc ghi.

Một deadlock phổ biến:

~~~text
Java cha                           Process con
--------                           ------------
Gọi waitFor()                      Ghi stdout
Không đọc stdout                   Pipe stdout đầy
                                   Chờ Java cha đọc
Java cha chờ process thoát         Process chờ Java cha đọc
~~~

Nếu process ghi cả stdout và stderr, chỉ đọc một trong hai cũng có thể để pipe còn lại đầy. Khi cần giữ hai luồng riêng, hãy đọc đồng thời cả hai, chẳng hạn bằng hai task trên executor hoặc virtual threads. Nếu không cần tách luồng, `redirectErrorStream(true)` gộp chúng thành một pipe.

Đối với output lớn, không nên dùng `readAllBytes()` hoặc `readAllLines()` một cách thiếu giới hạn. Có thể ghi thẳng ra file, xử lý streaming hoặc giới hạn lượng dữ liệu lưu trong bộ nhớ.

`Process.close()` đóng các stream khi được gọi, nhưng không thay thế việc đọc output trong lúc process đang chạy. Nếu tiến trình con bị block vì pipe đầy trước khi Java cha gọi `close()`, việc chỉ chờ bằng `waitFor()` cũng không giải quyết được deadlock.

## 7. Gửi EOF cho stdin để chương trình con có thể kết thúc

Một số chương trình đọc stdin đến EOF trước khi xử lý hoặc thoát. Nếu Java cha mở `getOutputStream()` hoặc `outputWriter()` nhưng không đóng sau khi gửi dữ liệu, chương trình con có thể tiếp tục chờ input.

~~~java
try (Process process = new ProcessBuilder(command).start()) {
    try (var writer = process.outputWriter(StandardCharsets.UTF_8)) {
        writer.write("request-data");
        writer.newLine();
        // Đóng writer gửi EOF tới stdin của process con.
    }

    // Chỉ chờ sau khi đã gửi EOF nếu chương trình con cần EOF để kết thúc.
    int exitCode = process.waitFor();
}
~~~

Đóng writer kết thúc luồng input từ phía Java cha. Nó không đóng stdout/stderr của chương trình con. Khi rời khối ngoài, `Process.close()` đóng các stream còn lại và chờ process.

Nếu chương trình con là một service đọc stdin liên tục và không được thiết kế để kết thúc khi nhận EOF, việc đóng stdin không đảm bảo nó thoát. Khi đó, dùng giao thức shutdown của ứng dụng con hoặc yêu cầu terminate bằng API phù hợp.

## 8. Phân biệt close(), waitFor() và destroy()

Ba thao tác có mục đích khác nhau:

| Phương thức | Đóng stream? | Chờ process? | Yêu cầu hủy process? | Kết quả |
|---|---:|---:|---:|---|
| `close()` | Có, tất cả reader/writer | Có | Không theo đường bình thường; forcibly destroy nếu bị interrupt khi chờ | `void`, có thể ném `IOException` |
| `waitFor()` | Không | Có | Không | Exit code |
| `waitFor(Duration)` | Không | Có giới hạn | Không | `true` nếu đã kết thúc, `false` nếu hết thời gian |
| `destroy()` | Không trực tiếp | Không | Có, kiểu terminate phụ thuộc nền tảng | `void` |
| `destroyForcibly()` | Không trực tiếp | Không | Có, yêu cầu terminate cưỡng bức | Trả về `Process` |

Nếu cần exit code, gọi `waitFor()` trước `close()`. Nếu chỉ cần giải phóng stream và chờ process hoàn tất, `close()` phù hợp. Nếu cần timeout, dùng `waitFor(Duration)`; nếu hết thời gian, quyết định có yêu cầu terminate hay không.

`destroy()` không đảm bảo luôn là graceful termination. Dùng `supportsNormalTermination()` để biết implementation có hỗ trợ terminate bình thường hay không. `destroyForcibly()` yêu cầu kết thúc cưỡng bức; process có thể vẫn ở trạng thái alive trong một khoảng ngắn sau lời gọi, vì vậy cần chờ thêm nếu muốn xác nhận nó đã kết thúc.

## 9. Chờ có timeout rồi mới đóng

`Process.close()` không nhận timeout. Nếu ứng dụng cần giới hạn thời gian chờ, dùng `waitFor(Duration)` trước. Ví dụ sau chuyển hướng output vì ứng dụng không cần capture:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

static int runWithTimeout(List<String> command, Duration timeout)
        throws IOException, InterruptedException, TimeoutException {

    ProcessBuilder builder = new ProcessBuilder(command)
        .redirectOutput(ProcessBuilder.Redirect.DISCARD)
        .redirectError(ProcessBuilder.Redirect.DISCARD);

    try (Process process = builder.start()) {
        if (!process.waitFor(timeout)) {
            process.destroyForcibly();
            process.waitFor();
            throw new TimeoutException("Process exceeded " + timeout);
        }

        return process.exitValue();
    }
}
~~~

Nếu hết thời gian, ví dụ yêu cầu hủy cưỡng bức, sau đó chờ process thực sự kết thúc rồi mới rời khối try. `close()` được gọi tự động ở cuối và giải phóng stream.

Trong code production, cần xử lý cả trường hợp thread bị interrupt khi đang chờ. Nếu `waitFor(Duration)` ném `InterruptedException`, trạng thái interrupt bị clear theo quy tắc của exception. Hãy quyết định rõ có terminate process trong catch hay không, khôi phục interrupt status sau khi cleanup và tránh để `close()` vô tình chờ một process còn chạy vô hạn.

Một chính sách phổ biến là: khi bị interrupt, yêu cầu `destroyForcibly()`, chờ process kết thúc, khôi phục interrupt status rồi truyền exception lên caller. `Process.close()` tự nó cũng có quy tắc xử lý interruption khi thread đang chờ bên trong close: forcibly destroy process, tiếp tục chờ và re-assert interrupt status.

## 10. close() có thể chờ vô hạn trong trường hợp nào?

Vì `close()` đóng các stream rồi chờ process, nó có thể chờ lâu nếu chương trình con không thoát khi mất các stream. Ví dụ:

- Process chạy như daemon/service và không dùng EOF để kết thúc.
- Process đã nhận EOF nhưng vẫn tiếp tục làm việc nền.
- Process đang chờ một dependency hoặc một lock bên ngoài.
- Process tạo tiến trình con và bản thân process cha vẫn chờ chúng.
- Chương trình con không xử lý lỗi ghi stdout/stderr và tiếp tục chạy.

Đóng một đối tượng `Process` không có nghĩa là tự động kết thúc toàn bộ process tree. `close()` chờ process được đại diện bởi đối tượng đó. Nếu ứng dụng tạo tiến trình con hoặc descendants, cần quản lý chúng riêng bằng `ProcessHandle.children()`, `descendants()` và chính sách terminate phù hợp.

Không dựa vào việc garbage collector thu hồi đối tượng `Process` để kết thúc tiến trình. Nếu không còn tham chiếu tới đối tượng `Process`, tiến trình hệ điều hành vẫn có thể tiếp tục chạy bất đồng bộ. Hãy đóng stream và quản lý vòng đời process một cách tường minh.

## 11. Xử lý IOException khi đóng

`close()` khai báo `throws IOException`. Nếu một stream gặp lỗi trong lúc đóng, phương thức vẫn chờ process kết thúc rồi mới ném exception. Nếu nhiều stream gặp lỗi, exception đầu tiên được ném và các exception còn lại được thêm dưới dạng suppressed exceptions.

Với try-with-resources, Java tự động gắn exception phát sinh khi đóng tài nguyên vào exception chính theo quy tắc suppressed exception. Có thể kiểm tra bằng `getSuppressed()` khi cần chẩn đoán.

Không bỏ qua `IOException` nếu ứng dụng cần bảo đảm dữ liệu output đã được xử lý hoặc tài nguyên đã được đóng. Nếu chỉ cleanup và không thể phục hồi, hãy ghi log phù hợp nhưng không log dữ liệu bí mật từ stdin/stdout/stderr.

## 12. Checklist quản lý Process an toàn

- [ ] Dùng `ProcessBuilder.start()` để tạo tiến trình.
- [ ] Đóng Process bằng try-with-resources hoặc gọi `close()` tường minh.
- [ ] Đọc stdout/stderr cần thiết trước khi gọi `close()`.
- [ ] Đóng stdin sau khi gửi đủ dữ liệu để child nhận EOF.
- [ ] Đọc stdout và stderr đồng thời nếu giữ hai pipe riêng.
- [ ] Dùng redirect file, inherit hoặc discard nếu không cần capture output.
- [ ] Không dùng `waitFor()` trước khi giải quyết khả năng pipe đầy.
- [ ] Gọi `waitFor()` trước `close()` nếu cần exit code.
- [ ] Dùng `waitFor(Duration)` và chính sách terminate khi cần timeout.
- [ ] Phân biệt `close()` với `destroy()` và `destroyForcibly()`.
- [ ] Xử lý interruption và khôi phục interrupt status.
- [ ] Quản lý descendants nếu process có tạo process tree.
- [ ] Xử lý `IOException` và suppressed exceptions khi cleanup.

## 13. Trạng thái API và tương thích JDK

`Process.close()` có từ **Java 26**. Nó thuộc `java.base` trong Java SE, không phải preview API và không yêu cầu cờ incubator.

Các ứng dụng compile với JDK 26 nhưng chạy trên JDK cũ hơn 26 không thể giả định method này tồn tại. Nếu dự án phải hỗ trợ nhiều JDK, hãy đặt baseline phù hợp hoặc dùng adapter theo phiên bản runtime. Với runtime trước Java 26, cách tương thích là tự đóng các process streams và gọi `waitFor()` theo đúng thứ tự; cần tự xử lý timeout, interruption và cleanup.

`waitFor(Duration)` có từ JDK 24. Các API reader/writer tiện dụng của Process có từ JDK 17. Phân biệt rõ phiên bản của từng method để không gán nhầm toàn bộ Process API cho Java 26.

## Kết luận

Từ JDK 26, `Process.close()` cung cấp cách quản lý vòng đời process bằng try-with-resources: đóng các reader/writer streams rồi chờ tiến trình kết thúc. Nó không trả exit code và không phải yêu cầu terminate thông thường; nếu cần exit status hãy gọi `waitFor()` trước, còn nếu cần timeout hãy dùng `waitFor(Duration)` cùng chính sách hủy riêng. Đọc dữ liệu cần thiết trước khi đóng, xử lý stdout/stderr để tránh pipe deadlock và nhớ rằng close có thể chờ vô hạn nếu process không tự kết thúc. Khi thread bị interrupt trong lúc close đang chờ, JDK forcibly destroys process, tiếp tục chờ và khôi phục interrupt status.

## Tài liệu tham khảo

- [Java SE 26 API – Process](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html)
- [Java SE 26 API – ProcessBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java SE 26 API – ProcessHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html)
- [Java SE 26 Core Libraries Guide – Process API](https://docs.oracle.com/en/java/javase/26/core/java-core-libraries-developer-guide.pdf)
- [Java SE 26 API – AutoCloseable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html)
