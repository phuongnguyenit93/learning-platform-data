# Kiểm thử đường thành công, lỗi và thu hồi tài nguyên

Kiểm thử code khởi chạy tiến trình hệ điều hành cần xác nhận cả kết quả nghiệp vụ lẫn vòng đời tài nguyên. Một test chỉ kiểm tra output đúng chưa đủ nếu tiến trình con vẫn chạy sau khi test kết thúc, stream còn mở hoặc pipe bị đầy làm test treo. Ngược lại, một test chỉ xác nhận `Process.close()` đã được gọi cũng chưa chứng minh chương trình con trả đúng exit code hay thông báo lỗi.

Java 26 cho phép dùng `Process` trực tiếp trong `try-with-resources` vì `Process` triển khai `Closeable` và `AutoCloseable`. Bài này xây dựng bộ test cho các nhánh khởi chạy thành công, tiến trình trả exit code khác 0, không thể khởi chạy, timeout và test kết thúc đột ngột. Một chương trình Java nhỏ đóng vai tiến trình con giúp các test có kết quả xác định trên Windows, macOS và Linux mà không phụ thuộc shell hoặc tiện ích cài sẵn của hệ điều hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi không khởi chạy được process, lỗi I/O và process kết thúc với exit code khác 0.
- Tạo process fixture bằng chính JDK đang chạy test để kiểm thử độc lập với shell.
- Kiểm tra stdout, stderr, exit code và thời gian hoàn tất trên đường thành công.
- Kiểm tra `try-with-resources` đóng process kể cả khi thân test ném exception.
- Dùng `waitFor(Duration)`, `destroy()` và `destroyForcibly()` để kiểm thử timeout.
- Dùng `Process.onExit()` để xác nhận process con đã kết thúc và `@TempDir` để cô lập file test.
- Tránh deadlock, test phụ thuộc thời gian và rò rỉ process/stream sau khi test kết thúc.

## 1. Xác định các nhánh cần kiểm thử

Một lời gọi `ProcessBuilder.start()` và một lần chạy process có nhiều kết quả khác nhau. Hãy tách chúng thành các trường hợp kiểm thử riêng:

| Trường hợp | Điều kiện | Kết quả cần xác nhận |
|---|---|---|
| Khởi chạy và hoàn tất thành công | Executable tồn tại, process chạy và kết thúc bình thường | Output đúng, exit code `0`, process không còn sống |
| Process trả lỗi | Process khởi chạy được nhưng kết thúc với exit code khác `0` | Output/error được thu thập, exit code được đọc chính xác; Java không tự ném exception chỉ vì exit code khác 0 |
| Không khởi chạy được | Executable không tồn tại, không có quyền chạy hoặc hệ điều hành từ chối | `start()` ném `IOException`; chưa có `Process` để gọi `close()` |
| Lỗi khi đọc/ghi stream | Stream bị đóng, I/O bị lỗi hoặc dữ liệu không đúng giao thức | Exception I/O được quan sát và các resource đã mở vẫn được đóng |
| Hết thời gian | Process chạy lâu hơn deadline | `waitFor(Duration)` trả `false`; test yêu cầu chấm dứt và chờ process kết thúc |
| Test thất bại giữa chừng | Assertion hoặc code trong thân `try` ném exception | `Process.close()` vẫn chạy; process con kết thúc và exception ban đầu được giữ lại |
| Thread bị interrupt | Owner bị interrupt khi chờ process | `InterruptedException` được xử lý đúng; process được cleanup theo chính sách đã chọn |

Đừng gộp tất cả trường hợp vào một test lớn. Khi một test thất bại, tên test cần cho biết đó là lỗi khởi chạy, exit status, timeout hay cleanup để việc chẩn đoán nhanh hơn.

## 2. Dùng một chương trình Java làm process fixture

Không nên viết test gọi `sh -c`, `cmd /c`, `grep`, `sleep` hoặc một tiện ích có thể không được cài trên máy CI. Cú pháp shell, quoting, đường dẫn và hành vi của các tiện ích này khác nhau giữa hệ điều hành. Thay vào đó, tạo một class Java nhỏ trong source set test và chạy nó bằng executable Java của chính runtime hiện tại.

Đặt file sau trong `src/test/java/example/process/ProcessFixture.java`:

```java
package example.process;

import java.io.OutputStream;
import java.time.Duration;

public final class ProcessFixture {
    private ProcessFixture() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Expected one fixture mode");
            System.exit(64);
        }

        switch (args[0]) {
            case "success" -> {
                System.out.println("stdout-success");
                System.err.println("stderr-diagnostic");
            }
            case "nonzero" -> {
                System.out.println("output-before-failure");
                System.err.println("fixture-failed");
                System.out.flush();
                System.err.flush();
                System.exit(7);
            }
            case "wait-for-eof" ->
                    System.in.transferTo(OutputStream.nullOutputStream());
            case "sleep" -> {
                System.out.println("started");
                System.out.flush();
                Thread.sleep(Duration.ofMinutes(1));
            }
            case "large-output" -> {
                for (int i = 0; i < 20_000; i++) {
                    System.out.println("out-" + i);
                    System.err.println("err-" + i);
                }
            }
            default -> {
                System.err.println("Unknown fixture mode: " + args[0]);
                System.exit(64);
            }
        }
    }
}
```

Các chế độ được thiết kế cho từng mục tiêu:

- `success`: ghi một dòng ra stdout và một dòng ra stderr rồi kết thúc với mã `0`.
- `nonzero`: ghi output và kết thúc với mã `7`, mô phỏng lỗi nghiệp vụ của chương trình con.
- `wait-for-eof`: đọc stdin đến EOF rồi kết thúc. Chế độ này kiểm tra việc đóng input stream khi `Process.close()` chạy.
- `sleep`: thông báo đã khởi động rồi chờ lâu, dùng để kiểm thử timeout và hủy.
- `large-output`: ghi nhiều dữ liệu ra cả stdout lẫn stderr để kiểm tra cách drain pipe.

Fixture không gọi mạng, không đọc file cấu hình của máy và không phụ thuộc chương trình ngoài JDK. Các test chỉ truyền tên chế độ qua đối số, vì vậy kết quả dễ lặp lại.

## 3. Khởi chạy fixture bằng JDK đang chạy test

Đặt test trong `src/test/java/example/process/ProcessLifecycleTest.java`. Helper sau tìm Java launcher cạnh runtime hiện tại và truyền classpath test vào process con:

```java
package example.process;

import java.nio.file.Path;
import java.util.List;

final class ProcessCommands {
    private ProcessCommands() {}

    static List<String> fixtureCommand(String mode) {
        boolean windows = System.getProperty("os.name")
                .startsWith("Windows");

        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java");

        return List.of(
                java.toString(),
                "-cp",
                System.getProperty("java.class.path"),
                ProcessFixture.class.getName(),
                mode);
    }
}
```

Mỗi đối số là một phần tử riêng của `List<String>`. Không nối thành một chuỗi lệnh shell; như vậy đường dẫn có khoảng trắng vẫn được truyền đúng và test không phải xử lý quy tắc quoting riêng của Windows hoặc POSIX.

Helper này phù hợp với test runner đưa test class vào classpath. Nếu build tool chạy test bằng module path hoặc classpath riêng của worker, cấu hình test runtime để process con nhìn thấy `ProcessFixture`; không mặc định rằng mọi test runner đều đặt cùng một giá trị `java.class.path`.

## 4. Kiểm thử đường thành công: output và exit code

Với process kết thúc nhanh và output nhỏ, có thể đọc riêng stdout và stderr. Dùng `Charset` rõ ràng để kết quả không phụ thuộc encoding mặc định của máy:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class ProcessSuccessTest {
    @Test
    @Timeout(value = 5, unit = java.util.concurrent.TimeUnit.SECONDS)
    void capturesOutputAndZeroExitCode() throws Exception {
        try (Process process = new ProcessBuilder(
                ProcessCommands.fixtureCommand("success")).start();
             var stdout = process.inputReader(StandardCharsets.UTF_8);
             var stderr = process.errorReader(StandardCharsets.UTF_8)) {

            assertEquals("stdout-success", stdout.readLine());
            assertEquals("stderr-diagnostic", stderr.readLine());

            assertTrue(process.waitFor(Duration.ofSeconds(2)));
            assertEquals(0, process.exitValue());
        }
    }
}
```

Thứ tự resource được khai báo là `Process`, stdout reader, stderr reader; khi thoát block, Java đóng theo thứ tự ngược: stderr, stdout, rồi process. Vì đã đọc dữ liệu cần dùng và process đã kết thúc, `Process.close()` hoàn tất nhanh.

`@Timeout` giới hạn thời gian toàn test. Nó bảo vệ suite trước fixture lỗi hoặc process bị treo; timeout của JUnit không thay thế timeout của process trong code production. Trong ứng dụng thật, vẫn phải đặt `waitFor(Duration)` và chính sách destroy riêng.

## 5. Kiểm thử process kết thúc với exit code khác 0

Một process khởi chạy thành công nhưng trả mã `7` không làm `Process.waitFor()` tự ném exception. Phương thức trả về mã kết thúc; ứng dụng phải diễn giải mã đó theo hợp đồng của chương trình con.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;

class ProcessExitFailureTest {
    @Test
    void capturesNonZeroExitAndMergedOutput() throws Exception {
        ProcessBuilder builder = new ProcessBuilder(
                ProcessCommands.fixtureCommand("nonzero"));
        builder.redirectErrorStream(true);

        try (Process process = builder.start();
             var output = process.inputReader(StandardCharsets.UTF_8)) {

            List<String> lines = output.lines().toList();

            assertTrue(process.waitFor(Duration.ofSeconds(2)));
            assertEquals(7, process.exitValue());
            assertTrue(lines.contains("output-before-failure"));
            assertTrue(lines.contains("fixture-failed"));
        }
    }
}
```

Test gộp stderr vào stdout nên chỉ cần một reader. Không khẳng định thứ tự tương đối giữa các dòng stdout/stderr đã merge; thứ tự quan sát có thể phụ thuộc thời điểm ghi và cách hệ điều hành chuyển dữ liệu. Test chỉ xác nhận cả hai thông điệp đều có mặt và exit code là `7`.

Trong code nghiệp vụ, nên chuyển mã khác `0` thành exception hoặc kết quả lỗi có cấu trúc:

```java
int exitCode = process.waitFor();
if (exitCode != 0) {
    throw new ExternalCommandException(command, exitCode);
}
```

Không coi việc stderr có dữ liệu là bằng chứng chắc chắn process thất bại. Một công cụ có thể ghi warning ra stderr rồi kết thúc với mã `0`; ngược lại, process có thể trả mã khác `0` mà không ghi thông báo nào.

## 6. Kiểm thử lỗi không khởi chạy được

Lỗi khi gọi `start()` khác với process đã chạy rồi trả mã khác `0`. Nếu executable không tồn tại hoặc hệ điều hành từ chối tạo process, `ProcessBuilder.start()` ném `IOException` và không trả về một đối tượng `Process` để đóng.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ProcessStartFailureTest {
    @TempDir
    Path tempDir;

    @Test
    void missingExecutableFailsAtStart() {
        Path missing = tempDir.resolve("no-such-program.exe");
        ProcessBuilder builder = new ProcessBuilder(List.of(missing.toString()));

        assertThrows(IOException.class, builder::start);
    }
}
```

Đường dẫn tuyệt đối tới một file không tồn tại trong thư mục test riêng giúp test không phụ thuộc `PATH` của máy. Không dùng tên command chung như `fake-command` vì máy developer hoặc CI có thể vô tình cài một chương trình cùng tên.

Khi `start()` thất bại, không có process handle để gọi `close()`. Những resource được tạo trước đó trong phương thức gọi vẫn phải được đóng bằng `try-with-resources` như bình thường.

## 7. Kiểm thử cleanup khi thân test ném exception

Đây là một test quan trọng của Java 26. Fixture `wait-for-eof` chờ tới khi stdin đóng. Khi `Process.close()` chạy, nó đóng các reader/writer của process; child nhận EOF, kết thúc và `close()` chờ cho đến khi process thật sự dừng.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CompletableFuture;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class ProcessCleanupTest {
    @Test
    @Timeout(value = 5, unit = java.util.concurrent.TimeUnit.SECONDS)
    void closesProcessWhenTestBodyThrows() throws Exception {
        Process process = new ProcessBuilder(
                ProcessCommands.fixtureCommand("wait-for-eof")).start();
        CompletableFuture<Process> exited = process.onExit();

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> {
                    try (process) {
                        assertTrue(process.isAlive());
                        throw new IllegalStateException("simulated test failure");
                    }
                });

        assertEquals("simulated test failure", failure.getMessage());
        assertEquals(process, exited.get(2, java.util.concurrent.TimeUnit.SECONDS));
        assertFalse(process.isAlive());
        assertEquals(0, process.exitValue());
    }
}
```

Test cố ý ném exception trong thân `try`. Dù vậy, `Process.close()` vẫn được gọi. Vì child đọc stdin tới EOF, việc đóng stream khiến child thoát; `close()` chờ child kết thúc trước khi trả quyền điều khiển cho test. Sau đó `onExit()` đã hoàn tất và `isAlive()` trả `false`.

Đây là bằng chứng tốt hơn việc chỉ kiểm tra biến `Process` không còn được tham chiếu. JVM không tự giết process khi không còn reference tới đối tượng Java; process có thể tiếp tục chạy bất đồng bộ. Test cần xác nhận trạng thái của process hệ điều hành.

## 8. Kiểm thử timeout và hủy process

Timeout phải được kiểm tra bằng `waitFor(Duration)`, không dùng `Process.close()` như một bộ đếm thời gian. Fixture `sleep` in một dòng xác nhận đã khởi động rồi chờ lâu hơn thời hạn test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class ProcessTimeoutTest {
    @Test
    @Timeout(value = 5, unit = java.util.concurrent.TimeUnit.SECONDS)
    void destroysProcessAfterDeadline() throws Exception {
        try (Process process = new ProcessBuilder(
                ProcessCommands.fixtureCommand("sleep")).start();
             var output = process.inputReader(StandardCharsets.UTF_8)) {

            assertEquals("started", output.readLine());
            assertFalse(process.waitFor(Duration.ofMillis(100)));

            process.destroy();
            if (!process.waitFor(Duration.ofSeconds(1))) {
                process.destroyForcibly();
            }

            assertTrue(process.waitFor(Duration.ofSeconds(2)));
            assertFalse(process.isAlive());
            process.exitValue(); // Exit status is available; its exact value is OS-dependent.
        }
    }
}
```

Test đọc dòng `started` để biết child đã đi vào chế độ chờ trước khi bắt đầu đo timeout. Nếu chỉ gọi `waitFor(Duration.ofMillis(100))` ngay sau `start()`, thời gian khởi động JVM con có thể chiếm phần lớn khoảng đo và làm kết quả không phản ánh hành vi đang muốn kiểm thử.

`destroy()` có hành vi phụ thuộc nền tảng. Nếu process chưa kết thúc sau grace period, `destroyForcibly()` yêu cầu kết thúc cưỡng bức; vẫn phải `waitFor()` để xác nhận nó đã dừng. `destroyForcibly()` không có nghĩa process biến mất tức thời.

## 9. Kiểm thử output redirect và file cleanup bằng @TempDir

Khi process ghi nhiều dữ liệu, redirect stdout/stderr ra file thường dễ kiểm soát hơn việc giữ toàn bộ output trong bộ nhớ. JUnit Jupiter `@TempDir` tạo thư mục riêng cho test và mặc định xóa đệ quy khi scope test kết thúc.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ProcessRedirectTest {
    @TempDir
    Path tempDir;

    @Test
    void redirectsOutputAndErrorToTemporaryFiles() throws Exception {
        Path stdoutFile = tempDir.resolve("stdout.txt");
        Path stderrFile = tempDir.resolve("stderr.txt");

        ProcessBuilder builder = new ProcessBuilder(
                ProcessCommands.fixtureCommand("success"));
        builder.redirectOutput(stdoutFile.toFile());
        builder.redirectError(stderrFile.toFile());

        try (Process process = builder.start()) {
            process.getOutputStream().close();
            assertTrue(process.waitFor(Duration.ofSeconds(2)));
            assertEquals(0, process.exitValue());
        }

        assertEquals("stdout-success" + System.lineSeparator(),
                Files.readString(stdoutFile, StandardCharsets.UTF_8));
        assertEquals("stderr-diagnostic" + System.lineSeparator(),
                Files.readString(stderrFile, StandardCharsets.UTF_8));
    }
}
```

Process được chờ kết thúc trước khi test đọc file. `@TempDir` cô lập output giữa các test và tự dọn thư mục sau khi test/class kết thúc. Nếu process vẫn giữ file handle hoặc còn chạy, việc dọn file có thể thất bại trên một số hệ điều hành; đó là dấu hiệu cần điều tra cleanup chứ không nên bỏ qua bằng cách chuyển sang thư mục chung.

Không dùng đường dẫn output cố định trong thư mục dự án. Dữ liệu test có thể ghi đè file của developer, khiến các test chạy song song tranh chấp hoặc để lại rác sau khi thất bại.

## 10. Kiểm tra pipe và tránh deadlock trong test

Pipe của stdout và stderr có dung lượng hữu hạn. Nếu fixture ghi nhiều dữ liệu vào cả hai pipe nhưng test chỉ đọc stdout, child có thể bị block khi stderr đầy. Test sau đó chờ stdout EOF hoặc `waitFor()` trong khi child đang chờ parent đọc stderr; hai bên deadlock.

Với fixture `large-output`, chọn một trong hai chiến lược:

**Chiến lược A: gộp stderr vào stdout**

```java
ProcessBuilder builder = new ProcessBuilder(
        ProcessCommands.fixtureCommand("large-output"));
builder.redirectErrorStream(true);

try (Process process = builder.start();
     var output = process.inputReader(StandardCharsets.UTF_8)) {
    long lines = output.lines().count();
    assertTrue(process.waitFor(Duration.ofSeconds(5)));
    assertEquals(40_000, lines);
}
```

**Chiến lược B: redirect mỗi stream ra file riêng**

```java
ProcessBuilder builder = new ProcessBuilder(
        ProcessCommands.fixtureCommand("large-output"));
builder.redirectOutput(stdoutFile.toFile());
builder.redirectError(stderrFile.toFile());
```

Chiến lược B tránh pipe phía parent và không cần giữ toàn bộ output trong heap. Nếu cần phân biệt stdout và stderr nhưng vẫn phải đọc trực tiếp từ pipe, tổ chức hai reader chạy đồng thời và đợi cả hai hoàn tất trước khi đóng process.

Không đọc `process.getInputStream()` và `process.inputReader()` đồng thời trên cùng process. Reader có buffer riêng và sẽ tiêu thụ byte từ cùng một stream; hai cách đọc sẽ cạnh tranh dữ liệu. Quy tắc tương tự áp dụng cho stderr stream và `errorReader()`.

## 11. Kiểm thử interruption và phân biệt với lỗi process

`Process.waitFor()` có thể ném `InterruptedException` khi thread owner bị interrupt trong lúc chờ. Việc thread bị interrupt không tự động có nghĩa process con đã thất bại; đó là tín hiệu hủy từ phía thread cha. Ứng dụng cần quyết định có destroy process hay chuyển interruption lên tầng gọi.

Khi `Process.close()` đang chờ process kết thúc mà thread bị interrupt, API Java 26 quy định process bị `destroyForcibly()`, `close()` tiếp tục chờ cho đến khi process kết thúc và khôi phục interrupted status trước khi trả về hoặc ném `IOException`.

Khi viết test cho interruption:

- Dùng latch hoặc tín hiệu xác nhận để biết worker đã bắt đầu chờ; tránh `Thread.sleep()` ngẫu nhiên để tạo race.
- Interrupt đúng thread đang chờ, rồi xác nhận nó nhận `InterruptedException` nếu đang gọi `waitFor()`.
- Xác định rõ ai chịu trách nhiệm chấm dứt process sau khi owner bị interrupt.
- Trong `finally` hoặc `try-with-resources`, đảm bảo process không còn sống trước khi test trả về.
- Nếu bắt `InterruptedException` mà không ném tiếp, khôi phục trạng thái bằng `Thread.currentThread().interrupt()` khi phù hợp với hợp đồng của phương thức.

Không bắt `InterruptedException` rồi bỏ qua để tiếp tục chờ process vô thời hạn. Cũng không khẳng định process đã bị kill chỉ vì thread chờ bị interrupt; `waitFor()` và `close()` có hành vi khác nhau.

## 12. Kiểm tra suppressed exception và cleanup nhiều resource

`try-with-resources` đóng tài nguyên theo thứ tự ngược với thứ tự khai báo. Nếu thân `try` ném exception và `close()` cũng ném exception, exception của thân `try` tiếp tục là exception chính; lỗi khi đóng được gắn vào `getSuppressed()`.

Ví dụ cấu trúc resource:

```java
try (Process process = builder.start();
     var stdout = process.inputReader(StandardCharsets.UTF_8);
     var stderr = process.errorReader(StandardCharsets.UTF_8)) {

    // Đọc output cần thiết, waitFor và kiểm tra exit code.
}
```

Thứ tự đóng là stderr reader, stdout reader, rồi process. `Process.close()` tiếp tục đóng các reader/writer gắn với process và chờ process kết thúc. Việc khai báo reader riêng giúp test kiểm soát encoding và vòng đời của từng stream; process resource ở ngoài cùng đảm bảo cleanup khi code trong thân test ném exception.

Khi một test thất bại, hãy in cả exception chính và suppressed exceptions trong báo cáo test. Không chỉ log `getMessage()` vì thông tin lỗi đóng stream có thể chỉ nằm trong suppressed exceptions. Không cố tạo lỗi đóng giả tạo bằng cách đóng stream nhiều lần; hành vi đóng lại phụ thuộc stream và thường không tạo lỗi có thể dự đoán.

## 13. Checklist về tính ổn định của test

- [ ] Fixture là chương trình Java nhỏ nằm trong test source set, không phụ thuộc shell hoặc tool cài ngoài.
- [ ] Java executable lấy từ `java.home` của runtime đang chạy test.
- [ ] Command và argument được truyền thành các phần tử riêng.
- [ ] Encoding của stdout/stderr được chỉ định rõ.
- [ ] Đường thành công kiểm tra output, exit code `0` và process đã kết thúc.
- [ ] Đường non-zero kiểm tra exit code và output; không nhầm stderr với trạng thái thất bại.
- [ ] Lỗi `start()` được kiểm tra riêng; không tìm cách gọi close trên process chưa được tạo.
- [ ] Mọi process đã start đều nằm trong `try-with-resources` hoặc có cleanup `finally` tương đương.
- [ ] Test cleanup có thể chứng minh child kết thúc sau khi resource được đóng.
- [ ] Timeout có grace period, force destroy và `waitFor()` xác nhận process dừng.
- [ ] stdout/stderr được drain đồng thời, gộp hoặc redirect; không để pipe đầy.
- [ ] File output nằm trong `@TempDir`; process kết thúc trước khi JUnit xóa thư mục.
- [ ] Test có deadline để lỗi fixture không treo toàn bộ test suite.
- [ ] Interruption được phân biệt với lỗi từ chương trình con.
- [ ] CI chạy trên đúng JDK mục tiêu, đặc biệt khi test `Process.close()` cần Java 26 trở lên.

## 14. Bài tập thực hành

Tạo một tiện ích `ExternalToolRunner` chạy chương trình ngoài bằng `ProcessBuilder`. Tiện ích nhận command, timeout và thư mục log; trả về exit code cùng nội dung stdout/stderr hoặc ném exception nghiệp vụ khi process không thể khởi chạy, quá thời gian hay kết thúc với mã lỗi.

**Yêu cầu:**

1. Tạo `ProcessFixture` với các chế độ `success`, `nonzero`, `wait-for-eof`, `sleep` và `large-output`.
2. Viết test đường thành công, xác nhận output và exit code bằng `waitFor()`.
3. Viết test process kết thúc với mã khác `0`, xác nhận Java không tự ném exception do exit code.
4. Viết test executable không tồn tại, xác nhận `ProcessBuilder.start()` ném `IOException`.
5. Viết test thân `try` ném exception nhưng process con vẫn kết thúc do `Process.close()` đóng stdin.
6. Viết test timeout bằng `waitFor(Duration)`, `destroy()` và `destroyForcibly()`.
7. Redirect output lớn ra file trong `@TempDir` và xác nhận không deadlock.
8. Viết test interruption có latch, phân biệt interruption của owner với exit failure của process.
9. Chạy test bằng JDK 26 và xác nhận không cần `--enable-preview` cho `Process.close()`.

**Kết quả mong đợi:**

- Test phân biệt được launch failure, non-zero exit, I/O failure, timeout và interruption.
- Mọi process đã khởi chạy đều kết thúc trước khi test hoàn tất.
- `Process.close()` được gọi cả khi test body ném exception.
- Exit code chỉ được đọc sau khi process kết thúc; dữ liệu output được đọc trước khi close.
- Test output lớn không phụ thuộc pipe buffer và không giữ dữ liệu vô hạn trong bộ nhớ.
- Thư mục tạm được dọn sau test, không để file log hoặc process tồn dư trong workspace.

## Tài liệu tham khảo

- [Process — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): `close()`, `waitFor(Duration)`, exit value, I/O streams và hành vi khi interrupted.
- [ProcessBuilder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): `start()`, lỗi khởi chạy, command arguments và chuyển hướng I/O.
- [ProcessHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html): `onExit()` và quan sát vòng đời process.
- [JUnit Jupiter User Guide](https://docs.junit.org/current/user-guide/): test lifecycle, assertion và giới hạn thời gian test.
- [TempDir — JUnit Jupiter API](https://docs.junit.org/current/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html): tạo và dọn thư mục tạm theo scope của test.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html): thay đổi `Process` triển khai `Closeable` và `AutoCloseable` từ Java 26.
