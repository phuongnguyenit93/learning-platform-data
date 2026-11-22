# Yêu cầu kết thúc bằng destroy hoặc destroyForcibly

Khi Java khởi chạy tiến trình con bằng `ProcessBuilder`, ứng dụng nhận được một đối tượng `Process` để theo dõi và điều khiển tiến trình đó. Khi không cần tiến trình chạy tiếp, có thể yêu cầu kết thúc bằng `destroy()` hoặc yêu cầu chấm dứt cưỡng bức bằng `destroyForcibly()`.

Hai phương thức có mục đích khác nhau, nhưng đều cần được kết hợp với việc chờ tiến trình thực sự kết thúc. Lời gọi yêu cầu dừng không đồng nghĩa tiến trình đã kết thúc ngay tại thời điểm phương thức trả về.

## 1. Hai phương thức kết thúc tiến trình

API trên `Process` có hai phương thức chính:

~~~java
void destroy()
Process destroyForcibly()
~~~

**`destroy()`**

Yêu cầu kết thúc tiến trình con. Cách hệ điều hành và implementation thực hiện yêu cầu này có thể khác nhau; không nên giả định nó luôn tương đương với một tín hiệu kết thúc nhẹ nhàng hoặc luôn cho phép tiến trình hoàn tất mọi công việc dọn dẹp.

**`destroyForcibly()`**

Yêu cầu chấm dứt tiến trình một cách cưỡng bức. Phương thức trả về đối tượng `Process` để thuận tiện nối tiếp thao tác. Tuy vậy, tiến trình có thể chưa biến mất ngay khi lời gọi trả về.

Vì việc kết thúc có thể diễn ra bất đồng bộ, hãy kiểm tra bằng `isAlive()` hoặc chờ bằng `waitFor()` trước khi giả định tiến trình đã dừng.

## 2. Chờ tiến trình kết thúc

Các phương thức thường được dùng cùng với hai cách yêu cầu kết thúc:

~~~java
boolean isAlive()
int waitFor() throws InterruptedException
boolean waitFor(long timeout, TimeUnit unit)
        throws InterruptedException
int exitValue()
~~~

- `isAlive()` cho biết tiến trình còn đang chạy hay không.
- `waitFor()` chờ vô thời hạn đến khi tiến trình kết thúc, rồi trả về exit code.
- `waitFor(timeout, unit)` chờ tối đa khoảng thời gian chỉ định; trả về `true` nếu tiến trình đã kết thúc, `false` nếu hết thời gian mà tiến trình vẫn chạy.
- `exitValue()` lấy exit code, nhưng ném `IllegalThreadStateException` nếu tiến trình chưa kết thúc.

Ví dụ:

~~~java
process.destroy();

if (!process.waitFor(3, TimeUnit.SECONDS)) {
    process.destroyForcibly();
    process.waitFor();
}

int exitCode = process.exitValue();
~~~

Cách làm này dành một khoảng thời gian cho yêu cầu kết thúc đầu tiên. Nếu tiến trình vẫn chạy sau timeout, ứng dụng gửi yêu cầu cưỡng bức rồi chờ đến khi nó kết thúc.

Không gọi `waitFor()` vô thời hạn ngay sau `destroy()` nếu ứng dụng cần bảo đảm thời gian chờ có giới hạn. Nếu implementation hoặc tiến trình không kết thúc, luồng gọi có thể chờ rất lâu.

## 3. Quy trình kết thúc có timeout

Một quy trình thực tế thường gồm các bước:

1. Ngừng gửi thêm công việc cho tiến trình con.
2. Nếu giao thức của tiến trình dùng EOF trên stdin để báo hết dữ liệu, đóng `process.getOutputStream()` sau khi gửi xong đầu vào.
3. Gọi `destroy()` để yêu cầu kết thúc.
4. Chờ một khoảng thời gian hữu hạn bằng `waitFor(timeout, unit)`.
5. Nếu tiến trình vẫn còn sống, gọi `destroyForcibly()`.
6. Chờ xác nhận kết thúc và lấy exit code nếu cần.
7. Đóng các stream mà ứng dụng sở hữu và hoàn tất xử lý tài nguyên.

Không phải chương trình con nào cũng dùng EOF trên stdin làm tín hiệu dừng. Chỉ đóng stream đầu vào khi điều đó phù hợp với giao thức của tiến trình.

Ví dụ một helper:

~~~java
static int terminate(Process process, long timeout, TimeUnit unit)
        throws InterruptedException {

    process.destroy();

    if (!process.waitFor(timeout, unit)) {
        process.destroyForcibly();
        process.waitFor();
    }

    return process.exitValue();
}
~~~

Sau khi helper trả về, tiến trình đã kết thúc và exit code có thể được đọc. Timeout chỉ giới hạn giai đoạn chờ sau `destroy()`; thời gian chấm dứt cưỡng bức còn phụ thuộc hệ điều hành và implementation.

## 4. destroyForcibly không đồng nghĩa đã dừng ngay

`destroyForcibly()` là yêu cầu chấm dứt cưỡng bức. API không bảo đảm tiến trình đã chết ngay tại thời điểm phương thức trả về.

Vì vậy, đoạn code sau chưa đủ nếu bước tiếp theo phụ thuộc vào việc tiến trình đã dừng:

~~~java
process.destroyForcibly();
// Không giả định tiến trình chắc chắn đã kết thúc ở đây.
~~~

Hãy chờ hoặc kiểm tra trạng thái:

~~~java
process.destroyForcibly();
process.waitFor();
System.out.println(process.isAlive()); // false sau khi waitFor hoàn tất bình thường
~~~

Nếu không muốn chờ vô hạn, có thể dùng `waitFor(timeout, unit)` và xử lý trường hợp vẫn còn sống. Không nên lặp vô hạn chỉ để chờ `isAlive()` chuyển thành false vì cách đó có thể tiêu tốn CPU.

## 5. Exit code và lỗi khi đọc quá sớm

Exit code cho biết kết quả kết thúc theo quy ước của chương trình con hoặc hệ điều hành. Thông thường, 0 được dùng để biểu thị thành công, nhưng ý nghĩa cụ thể do chương trình con định nghĩa.

Chỉ đọc exit code sau khi tiến trình đã kết thúc:

~~~java
if (!process.waitFor(5, TimeUnit.SECONDS)) {
    process.destroyForcibly();
    process.waitFor();
}

int code = process.exitValue();
~~~

Nếu gọi `exitValue()` khi tiến trình còn chạy, Java ném `IllegalThreadStateException`. Không dùng exit code để suy luận tiến trình đã kết thúc thành công nếu chưa biết hợp đồng mã thoát của chương trình con.

## 6. destroy không tự động kết thúc mọi tiến trình con cháu

Một đối tượng `Process` đại diện cho một tiến trình cụ thể. Yêu cầu `destroy()` hoặc `destroyForcibly()` trên đối tượng đó không nên được xem là cam kết toàn bộ cây tiến trình do nó tạo ra sẽ tự động kết thúc.

Từ Java 9, `ProcessHandle` cung cấp API để quan sát và điều khiển tiến trình theo handle, gồm:

~~~java
ProcessHandle handle = process.toHandle();
handle.descendants();
handle.destroy();
handle.destroyForcibly();
~~~

`descendants()` trả về các tiến trình con cháu có thể quan sát được tại thời điểm truy vấn. Nếu ứng dụng cần dọn dẹp cả cây tiến trình, phải xác định rõ phạm vi tiến trình cần kết thúc và xử lý từng handle phù hợp. Danh sách tiến trình có thể thay đổi trong lúc ứng dụng đang xử lý, nên cần thiết kế cho trường hợp tiến trình mới được tạo hoặc đã tự kết thúc.

Không kết thúc mọi tiến trình hệ thống theo tên chương trình hoặc theo một PID không được xác minh. Chỉ điều khiển tiến trình mà ứng dụng có quyền sở hữu hoặc được phép quản lý.

## 7. Quản lý stdin, stdout và stderr

Một tiến trình có thể bị treo dù ứng dụng đã gọi `waitFor()` nếu hai bên không xử lý luồng dữ liệu đúng cách.

- `process.getOutputStream()` là luồng ghi từ tiến trình cha vào stdin của tiến trình con.
- `process.getInputStream()` là luồng đọc stdout của tiến trình con.
- `process.getErrorStream()` là luồng đọc stderr của tiến trình con.

Nếu tiến trình con ghi nhiều dữ liệu vào stdout hoặc stderr nhưng tiến trình cha không đọc, pipe có thể đầy và tiến trình con bị chặn khi ghi. Khi đó, tiến trình cha chờ kết thúc trong khi tiến trình con chờ được đọc dữ liệu.

Giải pháp tùy nhu cầu:

- Đọc stdout và stderr đồng thời trong các tác vụ phù hợp.
- Gộp stderr vào stdout bằng `redirectErrorStream(true)` nếu không cần phân biệt hai luồng.
- Chuyển output sang file hoặc một đích phù hợp bằng `ProcessBuilder.Redirect`.
- Nếu không cần dữ liệu đầu ra, cấu hình redirect phù hợp thay vì để pipe không được tiêu thụ.

Đóng stream của tiến trình không thay thế `destroy()`. Tương tự, gọi `destroy()` không thay thế việc thu thập output nếu ứng dụng cần nội dung đó.

## 8. Xử lý InterruptedException và dọn dẹp

`waitFor()` và `waitFor(timeout, unit)` có thể ném `InterruptedException`. Khi luồng đang chờ bị interrupt, ứng dụng cần có chính sách dọn dẹp và giữ lại trạng thái interrupt nếu không xử lý tiếp exception ở tầng trên.

Ví dụ:

~~~java
try {
    if (!process.waitFor(3, TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor();
    }
} catch (InterruptedException exception) {
    process.destroyForcibly();
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Interrupted while waiting for child process",
            exception
    );
}
~~~

Trong code sản phẩm, nên cân nhắc chờ có giới hạn cả sau yêu cầu cưỡng bức, ghi log PID/exit code phù hợp và đóng các stream. Nếu cần bảo đảm dọn dẹp trong mọi nhánh, đặt logic kết thúc trong `finally` hoặc một abstraction quản lý vòng đời tiến trình.

Không nuốt `InterruptedException` rồi tiếp tục chờ như không có gì xảy ra. Việc đó làm mất tín hiệu hủy tác vụ của ứng dụng.

## 9. Ví dụ chạy được với Java 17+

Tạo file **ProcessTerminationDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class ProcessTerminationDemo {
    private static Process startChild() throws IOException {
        String executable = Path.of(
                System.getProperty("java.home"),
                "bin",
                isWindows() ? "java.exe" : "java"
        ).toString();

        return new ProcessBuilder(
                executable,
                "-cp",
                System.getProperty("java.class.path"),
                ProcessTerminationDemo.class.getName(),
                "child"
        ).start();
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
                .toLowerCase()
                .contains("win");
    }

    private static void stopWithFallback(Process process)
            throws InterruptedException {

        process.destroy();

        if (!process.waitFor(3, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("child")) {
            while (true) {
                Thread.sleep(1_000);
            }
        }

        Process requested = startChild();
        stopWithFallback(requested);
        System.out.println("destroy(): child exited");

        Process forced = startChild();
        forced.destroyForcibly();
        forced.waitFor();
        System.out.println("destroyForcibly(): child exited");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ProcessTerminationDemo.java
java ProcessTerminationDemo
~~~

Kết quả stdout:

~~~text
destroy(): child exited
destroyForcibly(): child exited
~~~

Ví dụ tạo hai tiến trình con chạy liên tục. Với tiến trình đầu, chương trình yêu cầu kết thúc bằng `destroy()`, chờ tối đa ba giây rồi mới dùng `destroyForcibly()` nếu cần. Với tiến trình thứ hai, chương trình yêu cầu chấm dứt cưỡng bức ngay và vẫn gọi `waitFor()` để xác nhận tiến trình đã kết thúc.

Output không in exit code vì mã thoát của tiến trình bị dừng có thể khác nhau theo hệ điều hành và cách implementation thực hiện yêu cầu kết thúc.

## 10. Lỗi thường gặp

**Cho rằng destroy luôn là kết thúc nhẹ nhàng**

Cách yêu cầu được hệ điều hành thực hiện phụ thuộc implementation. Không dựa vào `destroy()` như một cam kết tiến trình sẽ hoàn tất mọi bước cleanup.

**Cho rằng destroyForcibly kết thúc ngay lập tức**

Phương thức có thể trả về trước khi tiến trình thực sự kết thúc. Dùng `waitFor()` hoặc kiểm tra trạng thái sau đó.

**Gọi exitValue khi tiến trình còn sống**

Lệnh này ném `IllegalThreadStateException`. Chờ tiến trình kết thúc trước khi đọc exit code.

**Chờ vô thời hạn mà không có chính sách timeout**

Nếu tiến trình không phản hồi yêu cầu kết thúc, ứng dụng có thể bị treo. Dùng `waitFor(timeout, unit)` rồi quyết định có cần chấm dứt cưỡng bức hay không.

**Giả định destroy dừng cả cây tiến trình**

Process đại diện cho một tiến trình cụ thể. Nếu cần quản lý tiến trình con cháu, dùng `ProcessHandle` và xác định rõ phạm vi cần dọn dẹp.

**Không đọc stdout hoặc stderr**

Pipe đầy có thể khiến tiến trình con bị chặn. Thu thập output hoặc redirect theo nhu cầu trước khi chờ tiến trình.

**Bỏ qua InterruptedException**

Hãy dọn dẹp tiến trình theo chính sách của ứng dụng và khôi phục interrupt flag hoặc truyền exception lên tầng gọi.

## 11. Checklist kết thúc tiến trình

- Xác định tiến trình nào thuộc quyền quản lý của ứng dụng.
- Ngừng gửi công việc mới và hoàn tất giao thức stdin nếu cần.
- Gọi `destroy()` để yêu cầu kết thúc.
- Dùng `waitFor(timeout, unit)` để giới hạn thời gian chờ.
- Nếu vẫn chạy, gọi `destroyForcibly()` rồi chờ xác nhận kết thúc.
- Chỉ đọc `exitValue()` sau khi tiến trình đã dừng.
- Xử lý stdout/stderr để tránh pipe đầy.
- Dọn dẹp stream và xử lý `InterruptedException`.
- Dùng `ProcessHandle` nếu nghiệp vụ cần quản lý tiến trình con cháu.

`destroy()` và `destroyForcibly()` là hai mức yêu cầu kết thúc tiến trình con. Thiết kế an toàn cần kết hợp yêu cầu dừng, timeout, xác nhận bằng `waitFor()`, xử lý exit code và dọn dẹp tài nguyên theo đúng vòng đời tiến trình.
