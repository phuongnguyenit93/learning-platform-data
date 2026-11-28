# Ngoại lệ khi đóng luồng và suppressed exceptions

*Tình trạng API được đối chiếu với Java 26 tại ngày 27/11/2026.*

Khi quản lý tiến trình hệ điều hành bằng `ProcessBuilder`, ứng dụng Java đồng thời quản lý ba kênh I/O: stdin của tiến trình con, stdout và stderr. Những kênh này được biểu diễn bằng các stream hoặc reader/writer ở phía Java. Nếu thao tác đọc, ghi hoặc đóng một kênh phát sinh lỗi, ứng dụng cần giữ được nguyên nhân ban đầu và cả lỗi xảy ra trong quá trình dọn dẹp.

Java 26 bổ sung `Process.close()` và làm cho `Process` triển khai `AutoCloseable`/`Closeable`. Phương thức này đóng các stream I/O của tiến trình rồi chờ tiến trình kết thúc. Khi đóng nhiều stream có lỗi, `Process.close()` ném `IOException` đầu tiên và gắn các lỗi đóng stream tiếp theo vào nó bằng `Throwable.addSuppressed()`. Nếu thân khối try cũng ném lỗi, try-with-resources tiếp tục giữ lỗi thân khối làm lỗi chính và gắn lỗi từ `Process.close()` vào danh sách suppressed.

Bài học này tập trung vào cách đọc cây ngoại lệ, đóng đúng các kênh I/O, tránh deadlock và bảo toàn thông tin lỗi khi tiến trình con kết thúc.

## 1. Ba kênh I/O của Process

Khi chạy:

```java
Process process = new ProcessBuilder("some-command").start();
```

Java nhận một đối tượng `Process` để giao tiếp với tiến trình con. Ba phương thức stream có hướng nhìn từ tiến trình Java cha:

| API | Kênh của tiến trình con | Hướng dữ liệu |
|---|---|---|
| `getOutputStream()` | stdin | Java ghi dữ liệu để tiến trình con đọc |
| `getInputStream()` | stdout | Java đọc dữ liệu tiến trình con ghi |
| `getErrorStream()` | stderr | Java đọc dữ liệu lỗi tiến trình con ghi |

Các API reader/writer tương ứng:

- `outputWriter(Charset)` ghi ký tự vào stdin.
- `inputReader(Charset)` đọc ký tự từ stdout.
- `errorReader(Charset)` đọc ký tự từ stderr.

Chọn một cách đọc cho mỗi kênh. Không dùng đồng thời `getInputStream()` và `inputReader()` trên cùng process, vì reader có buffer riêng và có thể đã đọc trước những byte mà stream thô chưa nhìn thấy. Quy tắc tương tự áp dụng cho `getErrorStream()` và `errorReader()`.

Nếu stdout được redirect bằng `ProcessBuilder.redirectOutput()`, `getInputStream()` trả về null input stream. Nếu stderr được redirect hoặc gộp bằng `redirectErrorStream(true)`, `getErrorStream()` trả về null input stream. Đây là stream rỗng, không phải Java reference `null`.

## 2. Đóng stream có ý nghĩa gì đối với tiến trình con?

Đóng từng kênh có tác động khác nhau:

- Đóng stream Java trả về bởi `getOutputStream()` hoặc writer tương ứng sẽ đóng stdin phía tiến trình con. Nhiều chương trình đọc đến EOF rồi mới xử lý xong, nên đóng stdin là tín hiệu rằng Java không gửi thêm dữ liệu.
- Đóng stdout reader hoặc stream phía Java dừng việc nhận output qua kênh đó. Nó không trực tiếp gọi `destroy()` trên tiến trình con.
- Đóng stderr reader hoặc stream phía Java dừng việc nhận thông báo lỗi qua kênh đó. Nếu còn dữ liệu chưa đọc, dữ liệu có thể bị mất.

Đầu còn lại của pipe thuộc tiến trình con. Đóng một stream phía Java kết thúc kênh giao tiếp; hành vi tiếp theo của chương trình con phụ thuộc cách nó xử lý EOF hoặc lỗi ghi. Đóng stream không phải là một lệnh đảm bảo tiến trình con bị kill.

Một tiến trình con có thể chờ thêm input, tiếp tục chạy nền hoặc ghi rất nhiều dữ liệu ra stdout/stderr. Nếu ứng dụng không đọc các pipe kịp thời, buffer hữu hạn của hệ điều hành có thể đầy và làm tiến trình con bị block. Nếu Java đang chờ tiến trình con thoát trong khi tiến trình con đang chờ Java đọc pipe, hai bên có thể deadlock.

Vì vậy, đóng tài nguyên đúng lúc phải đi cùng với việc đọc/ghi đúng trình tự.

## 3. Process.close() trong Java 26

Từ Java 26, `Process` triển khai `AutoCloseable` và có phương thức:

```java
public void close() throws IOException
```

Hợp đồng của phương thức:

1. Đóng tất cả reader và writer stream của process.
2. Chờ tiến trình kết thúc.
3. Nếu việc đóng stream phát sinh `IOException`, ném lỗi đó sau khi tiến trình đã kết thúc.
4. Nếu nhiều stream đóng lỗi, lỗi đầu tiên được ném; những lỗi đóng stream tiếp theo được thêm vào lỗi đầu tiên bằng `addSuppressed()`.
5. Nếu thread bị interrupt trong khi `close()` chờ tiến trình, process bị hủy cưỡng bức; `close()` tiếp tục chờ đến khi process kết thúc và khôi phục interrupt status trước khi trả về hoặc ném `IOException`.

Phương thức `close()` có tính idempotent: gọi lại sau khi process đã đóng không làm lặp lại quá trình đóng. Tuy nhiên, đừng suy rộng tính chất này cho mọi lớp triển khai `AutoCloseable`; interface `AutoCloseable` không yêu cầu mọi `close()` phải idempotent.

Điểm quan trọng: `Process.close()` không trả về exit code. Nếu cần mã thoát, phải gọi `waitFor()` hoặc kiểm tra `exitValue()` sau khi process kết thúc trước khi đóng process.

## 4. try-with-resources giữ ngoại lệ chính như thế nào?

Try-with-resources tự động đóng resource khi rời khỏi khối `try`, kể cả khi thân khối ném exception. Nếu cả thân khối và `close()` đều lỗi:

- Exception từ thân khối là **primary exception** được ném ra ngoài.
- Exception phát sinh khi đóng resource được gắn vào primary exception bằng `getSuppressed()`.
- Nếu đóng nhiều resource và nhiều lần đóng đều lỗi, mỗi lỗi đóng được thêm vào danh sách suppressed theo thứ tự đóng.

Ví dụ:

```java
static final class FailingResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("Close failed");
    }
}

static void runTask() throws IOException {
    try (var resource = new FailingResource()) {
        throw new IOException("Task failed");
    }
}
```

Nếu `FailingResource.close()` cũng ném `IOException`, caller nhận `IOException("Task failed")`. Lỗi đóng resource không thay thế lỗi gốc; nó xuất hiện trong:

```java
catch (IOException e) {
    System.err.println("Primary: " + e);

    for (Throwable suppressed : e.getSuppressed()) {
        System.err.println("Suppressed: " + suppressed);
    }
}
```

Đây là khác biệt quan trọng so với tự đóng trong `finally`. Nếu `finally` ném exception mới, exception đó có thể che mất exception từ thân khối. Try-with-resources được thiết kế để bảo toàn lỗi chính và giữ lỗi cleanup như suppressed.

## 5. Thứ tự đóng nhiều resource

Các resource khai báo trong header của try-with-resources được đóng theo thứ tự ngược với thứ tự khai báo.

```java
try (var first = openFirst();
     var second = openSecond();
     var third = openThird()) {
    doWork();
}
```

Thứ tự đóng là:

1. `third.close()`
2. `second.close()`
3. `first.close()`

Nếu thân khối ném exception, exception đó vẫn là primary; mọi lỗi từ ba lần đóng được thêm vào danh sách suppressed theo thứ tự đóng. Nếu thân khối thành công nhưng cả ba lần đóng đều lỗi, lỗi từ `third.close()` là lỗi được ném ra ngoài; lỗi từ `second.close()` và `first.close()` là suppressed.

Điều này hữu ích khi resource có quan hệ phụ thuộc: khai báo resource cấp thấp trước, resource bao ngoài sau, để resource bao ngoài được đóng trước. Với process, cần quyết định rõ ai sở hữu stream và process để tránh đóng lặp hoặc đóng process trước khi đọc xong dữ liệu.

## 6. Hai tầng suppressed exception khi đóng Process

Có thể xuất hiện hai tầng suppressed độc lập:

**Tầng bên trong – Process.close():** process đóng nhiều reader/writer. Nếu nhiều thao tác đóng stream ném `IOException`, lỗi stream đầu tiên là lỗi được ném từ `Process.close()`; các lỗi stream còn lại được thêm vào nó.

**Tầng bên ngoài – try-with-resources:** nếu thân khối đang xử lý process đã ném exception, rồi `Process.close()` cũng ném `IOException`, lỗi từ `Process.close()` được thêm vào exception của thân khối.

Cây lỗi có thể có dạng:

```text
Primary exception: IOException("Parsing process output failed")
└── Suppressed: IOException("Process stream close failed")
    ├── Suppressed: IOException("stdout close failed")
    └── Suppressed: IOException("stderr close failed")
```

Đây là mô hình minh họa cấu trúc lỗi. Không nên giả định mọi lần đóng process đều phát sinh lỗi; các lỗi I/O khi close thường phụ thuộc implementation và trạng thái stream.

Khi điều tra sự cố, chỉ in `e.getMessage()` sẽ làm mất thông tin. Hãy giữ exception object, cause và toàn bộ suppressed exceptions. `Throwable.printStackTrace()` thường hiển thị suppressed exception, nhưng hệ thống logging cần được cấu hình để không chỉ ghi message.

## 7. Ví dụ chạy process và giữ lỗi đóng tài nguyên

Ví dụ sau chạy một lệnh, gộp stdout và stderr, gửi EOF cho stdin, đọc toàn bộ output và kiểm tra exit code. `Process` là resource ngoài cùng; reader được đóng trước khi `Process.close()` chạy.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

record ProcessResult(int exitCode, String output) {}

public class ProcessRunner {
    static ProcessResult run(List<String> command)
            throws IOException, InterruptedException {

        ProcessBuilder builder = new ProcessBuilder(command)
                .redirectErrorStream(true);

        try (Process process = builder.start()) {
            // Không gửi input; đóng stdin để tiến trình con nhận EOF.
            process.getOutputStream().close();

            String output;
            try (BufferedReader reader =
                         process.inputReader(StandardCharsets.UTF_8)) {
                output = reader.lines()
                        .collect(java.util.stream.Collectors.joining(
                                System.lineSeparator()
                        ));
            }

            int exitCode;
            try {
                exitCode = process.waitFor();
            } catch (InterruptedException e) {
                // waitFor() đã clear interrupt status. Khôi phục trước khi
                // thoát scope để Process.close() nhìn thấy tín hiệu interrupt.
                Thread.currentThread().interrupt();
                throw e;
            }

            if (exitCode != 0) {
                throw new IOException(
                        "Command failed with exit code " + exitCode
                                + "; output: " + output
                );
            }

            return new ProcessResult(exitCode, output);
        }
    }

    public static void main(String[] args) {
        try {
            ProcessResult result = run(List.of("java", "-version"));
            System.out.println(result.output());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.err.println("Waiting for child process was interrupted");
        } catch (IOException e) {
            System.err.println("Process operation failed: " + e);
            for (Throwable suppressed : e.getSuppressed()) {
                System.err.println("Cleanup failure: " + suppressed);
            }
        }
    }
}
```

Các điểm cần hiểu:

- `redirectErrorStream(true)` gộp stderr vào stdout để chỉ cần đọc một pipe. Nếu cần giữ riêng hai kênh, phải đọc cả hai đồng thời.
- Đóng stdin trước khi chờ output để chương trình con biết rằng không còn dữ liệu đầu vào.
- Đọc output đến EOF trước khi gọi `waitFor()` để tránh pipe đầy làm tiến trình con bị block.
- `waitFor()` lấy exit code; `Process.close()` ở cuối khối sẽ đóng các stream còn lại và bảo đảm process đã kết thúc.
- Reader đã được đóng bởi khối try bên trong. `Process.close()` tiếp tục quản lý các stream của process; việc đóng lại stream đã đóng thường không gây tác động, nhưng hành vi cụ thể của từng stream phụ thuộc implementation.
- Nếu kiểm tra exit code thất bại và thân khối ném `IOException`, lỗi đó vẫn là primary. Lỗi phát sinh từ `Process.close()` sẽ được thêm vào suppressed.

Trong production, không nên đưa toàn bộ output của tiến trình vào exception nếu output có thể chứa token, password hoặc dữ liệu nhạy cảm. Có thể lưu output vào file bảo vệ quyền truy cập, giới hạn số byte giữ trong bộ nhớ hoặc chỉ ghi phần cuối cần thiết để chẩn đoán.

## 8. Khi stdout và stderr tách riêng

Nếu không dùng `redirectErrorStream(true)`, tiến trình có hai pipe độc lập. Cần đọc chúng đồng thời để tránh một pipe đầy trong khi Java đang chờ pipe còn lại.

Mô hình an toàn:

```text
Java parent
  ├── reader task A: continuously drains child stdout
  ├── reader task B: continuously drains child stderr
  └── coordinator: writes stdin, closes it, waits for process,
                   then joins both reader tasks
```

Có thể dùng virtual threads hoặc executor phù hợp để chạy hai reader task. Mỗi reader chỉ đọc một kênh. Không dùng chung một reader cho cả stdout và stderr, và không đọc tuần tự một pipe đến EOF nếu tiến trình con có thể ghi nhiều dữ liệu lên pipe còn lại.

Nếu reader task thất bại, coordinator cần giữ exception đó, đóng hoặc hủy các kênh liên quan theo chính sách, kết thúc process nếu cần và vẫn đợi process kết thúc. Khi nhiều công việc cleanup lỗi, ghi nhận tất cả exception thay vì chỉ giữ lỗi cuối cùng.

## 9. Process.close() không thay thế destroy() và waitFor()

Ba API có mục đích khác nhau:

| API | Mục đích | Có bảo đảm trả exit code? |
|---|---|---|
| `waitFor()` | Đợi process kết thúc | Có, trả về exit code |
| `destroy()` | Yêu cầu hệ điều hành kết thúc process | Không |
| `destroyForcibly()` | Yêu cầu kết thúc cưỡng bức process | Không |
| `close()` | Đóng reader/writer stream và đợi process kết thúc | Không |

`close()` không phải timeout API. Nếu tiến trình con không kết thúc sau khi các stream bị đóng, `close()` có thể chờ lâu. Nếu ứng dụng cần giới hạn thời gian, hãy dùng `waitFor(timeout, unit)` để quan sát process; khi hết thời hạn, quyết định có gọi `destroy()` rồi `destroyForcibly()` hay không, sau đó đợi process kết thúc trước khi rời khỏi scope.

Ví dụ chính sách timeout:

```java
boolean finished = process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS);

if (!finished) {
    process.destroy();

    if (!process.waitFor(2, java.util.concurrent.TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor();
    }
}
```

Đây là chính sách điều khiển tiến trình, không phải hành vi tự động của `close()`. Khi `waitFor()` ném `InterruptedException`, exception làm clear interrupt status. Nếu process đang nằm trong try-with-resources, hãy khôi phục interrupt status **trước khi rời khỏi scope** nếu muốn `Process.close()` nhận biết interruption và áp dụng hành vi destroy cưỡng bức theo hợp đồng Java 26. Nếu chỉ khôi phục trong catch bên ngoài scope, việc đóng resource đã diễn ra trước đó và có thể chờ process vô thời hạn.

Ví dụ xử lý trong phạm vi sở hữu:

```java
try (Process process = builder.start()) {
    try {
        if (!process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)) {
            process.destroy();
            if (!process.waitFor(2, java.util.concurrent.TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor();
            }
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw e; // Process.close() chạy khi unwind và thấy interrupt status
    }
}
```

Nếu thread bị interrupt khi chính `Process.close()` đang chờ, hợp đồng Java 26 yêu cầu process bị destroyForcibly và `close()` tiếp tục đợi cho đến khi kết thúc, sau đó re-assert interrupt status. Đừng bắt `InterruptedException` rồi bỏ qua tín hiệu interrupt.

## 10. Đọc exit code và output trước khi đóng

Nếu exit code có ý nghĩa, gọi `waitFor()` trước `close()`. Nếu output có ý nghĩa, đọc stdout/stderr đến EOF trước khi `close()`. Java 26 API nói rõ dữ liệu từ process input/error streams chưa đọc đến EOF sẽ bị bỏ qua khi `close()` chạy.

Một trình tự thường dùng:

1. Khởi chạy process.
2. Bắt đầu đọc stdout và stderr.
3. Gửi input nếu cần.
4. Đóng stdin khi đã gửi xong để phát EOF.
5. Đọc output đến EOF.
6. Gọi `waitFor()` để lấy exit code.
7. Đánh giá kết quả.
8. Rời khối try để `Process.close()` đóng các kênh còn lại và xác nhận process đã kết thúc.

Nếu tiến trình con không đóng stdout/stderr vì child process khác còn giữ pipe mở, việc đọc đến EOF có thể chờ lâu. Trong trường hợp có process tree, cần cân nhắc quản lý descendant qua `ProcessHandle.descendants()` và chính sách kết thúc tiến trình con phù hợp; không giả định `Process.close()` tự động quản lý mọi descendant.

## 11. Đọc suppressed exceptions theo cách đệ quy

Suppressed exception có thể lồng nhau. Ví dụ exception chính của thân khối chứa lỗi `Process.close()`, còn lỗi `Process.close()` lại chứa lỗi đóng stdout/stderr. Duyệt đệ quy giúp không bỏ sót lỗi sâu bên trong:

```java
static void printExceptionTree(Throwable error, String indent) {
    System.err.println(indent + error.getClass().getName()
            + ": " + error.getMessage());

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println(indent + "Suppressed:");
        printExceptionTree(suppressed, indent + "  ");
    }

    Throwable cause = error.getCause();
    if (cause != null) {
        System.err.println(indent + "Caused by:");
        printExceptionTree(cause, indent + "  ");
    }
}
```

Cần tránh vòng lặp khi một exception có quan hệ cause/suppressed bất thường do code tự tạo. Với exception thông thường từ try-with-resources, cấu trúc là cây và cách duyệt trên phù hợp. Trong hệ thống logging thực tế, nên dùng logger có hỗ trợ Throwable để giữ stack trace đầy đủ, đồng thời lọc dữ liệu nhạy cảm.

Không chỉ gọi `getSuppressed()` trên exception cuối cùng rồi bỏ qua cause. Nếu một API bọc lỗi gốc trong exception khác, suppressed có thể nằm ở exception chính hoặc ở một node trong chuỗi cause.

## 12. Vì sao không nên tự đóng trong finally?

Mẫu dễ gây mất lỗi:

```java
Process process = builder.start();

try {
    doWork(process);
} finally {
    process.close();
}
```

Nếu `doWork()` ném `IOException A` và `process.close()` ném `IOException B`, lỗi B từ `finally` có thể thay thế lỗi A. Khi đó log chỉ còn lỗi cleanup, làm mất nguyên nhân thao tác chính thất bại.

Mẫu nên dùng:

```java
try (Process process = builder.start()) {
    doWork(process);
}
```

Try-with-resources giữ lỗi từ `doWork()` làm primary và thêm lỗi từ `close()` vào suppressed. Nếu không có lỗi trong thân khối, lỗi close trở thành lỗi chính và được ném ra ngoài.

Không cần tự gọi `process.close()` ở cuối khối try nếu process đã được khai báo là resource. Gọi đóng thủ công trong thân khối rồi để try-with-resources đóng lần nữa có thể làm code khó đọc; dù `Process.close()` idempotent, nên để một nơi chịu trách nhiệm rõ ràng.

## 13. Lưu ý về AutoCloseable và lỗi InterruptedException

`AutoCloseable.close()` khai báo có thể ném `Exception`. Tài liệu API khuyến nghị implementation cụ thể khai báo loại exception hẹp hơn, và tránh ném `InterruptedException` từ `close()` vì exception này tương tác với interrupt status. Nếu `InterruptedException` bị suppressed, trạng thái interrupt có thể bị xử lý sai.

`Process.close()` của Java 26 khai báo `IOException`, không khai báo `InterruptedException`. Khi thread bị interrupt trong lúc close chờ process, implementation thực hiện destroy cưỡng bức, tiếp tục đợi và khôi phục interrupt status. Đây là hành vi đặc thù của `Process.close()`, không phải hợp đồng chung của mọi `AutoCloseable`.

Khi tự viết resource wrapper quanh process hoặc stream:

- Ưu tiên `close()` idempotent.
- Giải phóng tài nguyên trước khi ném lỗi close nếu có thể.
- Không ném `InterruptedException` từ close.
- Nếu cần báo interrupt, thiết kế API điều khiển riêng và giữ interrupt status theo đúng hợp đồng.
- Không che mất exception chính bằng exception cleanup.

## 14. Checklist xử lý lỗi khi đóng Process

- [ ] Đã xác định rõ stdin, stdout và stderr của process.
- [ ] Mỗi kênh chỉ dùng một API đọc/ghi: stream hoặc reader/writer tương ứng.
- [ ] Đã đọc stdout và stderr đồng thời nếu chúng là hai pipe riêng.
- [ ] Đã đóng stdin sau khi gửi hết input để tiến trình con nhận EOF.
- [ ] Đã đọc dữ liệu output cần thiết trước khi gọi `Process.close()`.
- [ ] Đã gọi `waitFor()` nếu cần exit code.
- [ ] Đã hiểu rằng `Process.close()` chờ process kết thúc và không phải timeout API.
- [ ] Đã dùng try-with-resources để giữ lỗi thân khối làm primary.
- [ ] Đã kiểm tra `getSuppressed()` và `getCause()` khi xử lý lỗi.
- [ ] Đã có chính sách timeout, destroy và destroyForcibly nếu tiến trình có thể treo.
- [ ] Đã khôi phục interrupt status khi bắt `InterruptedException`.
- [ ] Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm từ stdout/stderr vào log.

## Tài liệu tham chiếu

1. [Oracle Java SE 26 API – Process](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html)
2. [Oracle Java SE 26 API – AutoCloseable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html)
3. [Oracle Java SE 26 API – Throwable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html)
4. [Oracle Java Tutorials – The try-with-resources Statement and Suppressed Exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
5. [Oracle Java SE 26 Core Libraries Developer Guide – Process API Classes and Interfaces](https://docs.oracle.com/en/java/javase/26/core/java-core-libraries-developer-guide.pdf)

