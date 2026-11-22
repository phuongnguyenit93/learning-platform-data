# Phân biệt hoàn tất theo dõi với mã thoát thành công

## 1. Tiến trình kết thúc và tiến trình thành công là hai trạng thái khác nhau

Khi Java khởi chạy chương trình bên ngoài bằng `ProcessBuilder`, đối tượng `Process` đại diện cho tiến trình con. Có hai câu hỏi riêng biệt cần trả lời:

1. **Tiến trình đã kết thúc chưa?** Đây là câu hỏi về vòng đời và việc theo dõi tiến trình.
2. **Tiến trình kết thúc với kết quả thành công hay thất bại?** Đây là câu hỏi về mã thoát mà chương trình con trả về.

Một tiến trình có thể kết thúc bình thường về mặt vòng đời nhưng trả mã thoát khác 0 để báo lỗi. Vì vậy, việc một future hoàn tất, `waitFor` trả về hoặc `isAlive()` trở thành false không tự chứng minh tác vụ thành công.

Theo quy ước phổ biến trên hệ điều hành, mã thoát 0 biểu thị thành công và mã khác 0 biểu thị một dạng thất bại. Tuy nhiên, ý nghĩa cụ thể của từng mã do chương trình con và hợp đồng của ứng dụng định nghĩa. Java cung cấp mã thoát; mã gọi phải diễn giải nó theo quy ước mà hai bên thống nhất.

## 2. Process.onExit(): hoàn tất theo dõi khi tiến trình đã kết thúc

Từ Java 9, `Process.onExit()` trả về một `CompletableFuture<Process>`. Future này hoàn tất khi tiến trình con kết thúc. Nó cho phép đăng ký callback hoặc kết hợp với các thao tác bất đồng bộ thay vì phải chặn một thread bằng `waitFor()`.

```java
Process process = new ProcessBuilder(command).start();

CompletableFuture<Process> completion = process.onExit();

completion.thenAccept(terminated -> {
    int exitCode = terminated.exitValue();
    System.out.println("exit code = " + exitCode);
});
```

Điểm quan trọng:

- Future hoàn tất khi tiến trình đã kết thúc, bất kể mã thoát là 0 hay khác 0.
- Future hoàn tất bình thường không đồng nghĩa với tiến trình con thành công.
- Sau khi future hoàn tất, có thể lấy mã thoát bằng `exitValue()`.
- `onExit()` không tự khởi chạy, dừng hoặc hủy tiến trình; nó cung cấp tín hiệu theo dõi vòng đời.

Nếu cần xác định thành công, callback phải đọc mã thoát và áp dụng quy tắc của ứng dụng:

```java
completion.thenAccept(terminated -> {
    int exitCode = terminated.exitValue();

    if (exitCode == 0) {
        handleSuccess();
    } else {
        handleFailure(exitCode);
    }
});
```

Tên callback như `thenAccept` hoặc trạng thái `isDone()` chỉ nói về future. Chúng không thay thế việc kiểm tra mã thoát.

## 3. waitFor(): chờ kết thúc và nhận trực tiếp mã thoát

Phương thức không tham số:

```java
int exitCode = process.waitFor();
```

chặn thread gọi cho đến khi tiến trình kết thúc, rồi trả về mã thoát. Đây là điểm khác biệt quan trọng so với `onExit()`: `waitFor()` không chỉ xác nhận tiến trình kết thúc mà còn trả ngay giá trị mã thoát.

Mã gọi vẫn phải diễn giải mã đó:

```java
int exitCode = process.waitFor();

if (exitCode == 0) {
    System.out.println("Process succeeded");
} else {
    System.out.println("Process failed with code " + exitCode);
}
```

Nếu mã thoát là 7, `waitFor()` vẫn trả về 7 bình thường. Việc phương thức hoàn tất và không ném ngoại lệ không có nghĩa chương trình con thành công.

### waitFor(timeout, unit) trả về boolean

Overload có timeout:

```java
boolean terminated = process.waitFor(10, TimeUnit.SECONDS);
```

có ý nghĩa:

- `true`: tiến trình đã kết thúc trong khoảng thời gian chờ.
- `false`: hết thời gian chờ mà tiến trình vẫn chưa kết thúc.

Giá trị boolean này không phải mã thoát và cũng không phải kết quả thành công/thất bại. Nếu trả về `true`, gọi `exitValue()` hoặc `waitFor()` để lấy mã thoát. Nếu trả về `false`, tiến trình vẫn có thể tiếp tục chạy.

Timeout chỉ kết thúc lần chờ. Nó không tự động gửi tín hiệu dừng tiến trình. Nếu ứng dụng quyết định hủy tiến trình, có thể gọi `destroy()` hoặc `destroyForcibly()`, rồi tiếp tục chờ xác nhận tiến trình thực sự kết thúc.

## 4. isAlive() và exitValue()

Hai phương thức này trả lời hai câu hỏi khác nhau:

- `process.isAlive()` trả về `true` nếu tiến trình chưa kết thúc và `false` nếu tiến trình đã kết thúc.
- `process.exitValue()` trả về mã thoát nếu tiến trình đã kết thúc. Nếu tiến trình vẫn đang chạy, phương thức ném `IllegalThreadStateException`.

Ví dụ:

```java
if (!process.isAlive()) {
    int exitCode = process.exitValue();
}
```

Kiểm tra `isAlive()` chỉ xác định trạng thái vòng đời. Một tiến trình đã kết thúc với mã 1 vẫn có `isAlive() == false). Để đánh giá thành công, phải kiểm tra mã thoát theo hợp đồng ứng dụng.

Không nên dùng `exitValue()` như cách thăm dò liên tục khi tiến trình đang chạy. Nếu cần chờ, dùng `waitFor()`, overload có timeout hoặc `onExit()`.

## 5. Phân biệt các kết quả thường gặp

| Quan sát | Ý nghĩa | Có chứng minh thành công không? |
|---|---|---|
| `onExit()` future hoàn tất | Tiến trình đã kết thúc | Không |
| `waitFor()` trả về | Tiến trình đã kết thúc và có mã thoát | Chỉ khi mã thoát đáp ứng quy ước thành công |
| `waitFor(timeout, unit)` trả `true` | Tiến trình kết thúc trong thời gian chờ | Không |
| `waitFor(timeout, unit)` trả `false` | Tiến trình chưa kết thúc trước timeout | Không |
| `isAlive() == false` | Tiến trình không còn chạy | Không |
| `exitValue() == 0` | Mã thoát bằng 0 | Thường là có, nếu chương trình con dùng quy ước 0 = thành công |
| `exitValue() != 0` | Mã thoát khác 0 | Thường biểu thị lỗi theo quy ước chương trình con |

Một ngoại lệ khác cần tách riêng là lỗi khởi chạy: `ProcessBuilder.start()` có thể ném `IOException` nếu không thể tạo tiến trình, chẳng hạn executable không tồn tại hoặc không thể khởi chạy. Khi đó chưa có một tiến trình con hợp lệ để theo dõi mã thoát. Lỗi khởi chạy khác với một tiến trình đã chạy rồi tự kết thúc bằng mã khác 0.

## 6. Ví dụ Java chạy được: future hoàn tất nhưng exit code khác nhau

Chương trình sau tự khởi chạy hai tiến trình con bằng chính Java runtime hiện tại. Một tiến trình thoát với mã 0, tiến trình còn lại thoát với mã 7. Cả hai future từ `onExit()` đều hoàn tất; chỉ mã thoát cho biết kết quả thành công hay thất bại.

Ví dụ cũng kiểm tra `waitFor(timeout, unit)`: tiến trình con chờ 250 ms nên lần chờ 1 ms đầu tiên hết hạn, nhưng tiến trình vẫn chạy và sau đó kết thúc với mã 0.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ProcessOutcomeDemo {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].startsWith("child-")) {
            runChildMode(args[0]);
            return;
        }

        inspectExit("success");
        inspectExit("failure");
        inspectTimeout();
    }

    private static void runChildMode(String mode) throws InterruptedException {
        if (mode.equals("child-slow")) {
            Thread.sleep(250);
            return;
        }
        System.out.println("child completed: " + mode);
        if (mode.equals("child-failure")) {
            System.exit(7);
        }
    }

    private static Process startChild(String mode) throws Exception {
        String executable = Path.of(
                System.getProperty("java.home"), "bin",
                isWindows() ? "java.exe" : "java").toString();
        return new ProcessBuilder(
                executable, "-cp", System.getProperty("java.class.path"),
                ProcessOutcomeDemo.class.getName(), "child-" + mode)
                .redirectErrorStream(true)
                .start();
    }

    private static void inspectExit(String mode) throws Exception {
        Process process = startChild(mode);
        CompletableFuture<Process> completion = process.onExit();
        Process terminated;
        try {
            terminated = completion.get(10, TimeUnit.SECONDS);
        } catch (TimeoutException ex) {
            process.destroyForcibly();
            throw ex;
        }

        String output = new String(
                terminated.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).trim();
        int exitCode = terminated.exitValue();
        System.out.println("mode = " + mode);
        System.out.println("onExit completed = " + completion.isDone());
        System.out.println("process alive = " + terminated.isAlive());
        System.out.println("exit code = " + exitCode);
        System.out.println("success = " + (exitCode == 0));
        System.out.println("child output = " + output);
    }

    private static void inspectTimeout() throws Exception {
        Process process = startChild("slow");
        boolean terminatedQuickly = process.waitFor(1, TimeUnit.MILLISECONDS);
        System.out.println("terminated within 1 ms = " + terminatedQuickly);
        Process terminated = process.onExit().get(10, TimeUnit.SECONDS);
        System.out.println("later exit code = " + terminated.exitValue());
    }

    private static boolean isWindows() {
        return System.getProperty("os.name").toLowerCase().contains("win");
    }
}
```

Lưu mã nguồn trong `ProcessOutcomeDemo.java`, sau đó biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all ProcessOutcomeDemo.java
java ProcessOutcomeDemo
```

Kết quả:

```text
mode = success
onExit completed = true
process alive = false
exit code = 0
success = true
child output = child completed: child-success
mode = failure
onExit completed = true
process alive = false
exit code = 7
success = false
child output = child completed: child-failure
terminated within 1 ms = false
later exit code = 0
```

Hai lần `onExit()` đều hoàn tất và `isAlive()` đều là false. Tuy nhiên, tiến trình thứ nhất trả mã 0 còn tiến trình thứ hai trả mã 7. Dòng timeout cũng cho thấy `false` chỉ nói rằng lần chờ 1 ms không đủ; tiến trình vẫn tiếp tục và sau đó kết thúc với mã 0.

Ví dụ đã được biên dịch với `javac --release 17 -Xlint:all` và chạy thành công. Nó dùng đường dẫn Java từ `java.home`, nên không phụ thuộc tên executable `java` có sẵn trong PATH; tên file được chọn theo hệ điều hành.

## 7. Timeout, hủy tiến trình và xác nhận kết thúc

Khi timeout xảy ra, ứng dụng cần quyết định có tiếp tục chờ hay hủy tiến trình. Một quy trình thường dùng:

```java
if (!process.waitFor(5, TimeUnit.SECONDS)) {
    process.destroy();

    if (!process.waitFor(2, TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor();
    }
}

int exitCode = process.exitValue();
```

`destroy()` yêu cầu tiến trình kết thúc theo cơ chế của nền tảng. Tiến trình có thể không dừng ngay hoặc có thể không phản hồi yêu cầu đó. `destroyForcibly()` yêu cầu dừng mạnh hơn, nhưng vẫn cần chờ để xác nhận vòng đời đã kết thúc.

Sau khi tiến trình bị hủy, mã thoát thường không bằng 0; ứng dụng nên phân biệt trạng thái timeout/cancellation với lỗi nghiệp vụ do chương trình con báo. Nếu cần giữ lý do hủy, lưu trạng thái đó riêng thay vì chỉ dựa vào mã thoát.

Lưu ý: `waitFor()` và `CompletableFuture.get()` có thể bị ngắt hoặc hết timeout. `InterruptedException` biểu thị thread đang chờ bị ngắt; nó không chứng minh tiến trình con đã kết thúc. Nếu bắt và không ném tiếp ngoại lệ, thường cần khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()`.

## 8. Đọc stdout và stderr mà không gây deadlock

Một tiến trình con có thể ghi dữ liệu vào stdout hoặc stderr. Nếu bộ đệm pipe đầy mà tiến trình cha chỉ chờ `waitFor()` hoặc `onExit()` trước khi đọc output, tiến trình con có thể bị chặn khi ghi và không bao giờ kết thúc. Khi đó tiến trình cha cũng chờ mãi.

Ví dụ ở trên chỉ ghi một dòng ngắn nên dữ liệu không làm đầy pipe. Trong ứng dụng thực tế, nếu output có thể lớn, hãy chọn một cách xử lý phù hợp:

- Dùng `redirectOutput(...)` và `redirectError(...)` để ghi ra file.
- Dùng `inheritIO()` nếu muốn tiến trình con dùng trực tiếp các luồng I/O của tiến trình cha.
- Đọc stdout và stderr đồng thời trong các tác vụ riêng khi cần xử lý output trong bộ nhớ.
- Dùng `redirectErrorStream(true)` nếu có thể gộp stderr vào stdout.

Theo dõi vòng đời và tiêu thụ output là hai trách nhiệm riêng. Hoàn tất future không giúp giải phóng một pipe đang đầy nếu tiến trình con bị chặn trước khi thoát.

## 9. ProcessHandle và tiến trình ngoài

Java 9 bổ sung `ProcessHandle` để truy vấn và quản lý tiến trình ở cấp hệ điều hành. `Process.toHandle()` cung cấp handle của tiến trình con; `ProcessHandle.onExit()` cũng trả về `CompletableFuture<ProcessHandle>` hoàn tất khi tiến trình tương ứng kết thúc.

`ProcessHandle` hữu ích khi cần PID, thông tin tiến trình, cây tiến trình hoặc theo dõi tiến trình không được tạo trực tiếp bởi đối tượng `Process`. Tuy nhiên, `ProcessHandle.onExit()` cũng chỉ xác nhận tiến trình kết thúc. Muốn biết mã thoát của một tiến trình được khởi chạy bằng `Process`, hãy lấy mã từ đối tượng `Process` sau khi nó kết thúc.

Không phải mọi tiến trình hệ điều hành đều có mã thoát mà ứng dụng có thể đọc thông qua cùng một API. Với tiến trình con do `ProcessBuilder` tạo, dùng `Process.exitValue()` hoặc `waitFor()` để nhận exit status.

## 10. Checklist khi review mã nguồn

1. Mã đang cần biết tiến trình đã kết thúc hay cần biết tác vụ thành công?
2. Nếu dùng `onExit()`, callback có đọc và kiểm tra `exitValue()` không?
3. Nếu dùng `waitFor(timeout, unit)`, mã có hiểu `false` là hết thời gian chờ chứ không phải exit code không?
4. Có gọi `exitValue()` trước khi tiến trình kết thúc không?
5. Khi exit code khác 0, ứng dụng có xử lý lỗi theo hợp đồng của chương trình con không?
6. Khi timeout, chính sách tiếp tục chờ, `destroy()` hay `destroyForcibly()` đã rõ chưa?
7. stdout/stderr có được tiêu thụ để tránh pipe deadlock không?
8. Lỗi khởi chạy, lỗi chờ bị interrupt, timeout và mã thoát khác 0 có được phân biệt không?

`onExit()`, `waitFor()` và `isAlive()` mô tả vòng đời tiến trình. Mã thoát mô tả kết quả mà chương trình con báo lại. Chỉ kết luận thành công sau khi đã có mã thoát và kiểm tra nó theo hợp đồng của ứng dụng.