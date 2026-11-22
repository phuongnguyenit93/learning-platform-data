# destroy và quản lý vòng đời tiến trình

## 1. Tiến trình đã được tạo phải có một bên chịu trách nhiệm kết thúc

Sau `ProcessBuilder.start()`, tiến trình con chạy độc lập với việc mã Java còn giữ biến tham chiếu hay không.

Các tình huống cần quản lý gồm:

- Công việc hoàn tất bình thường.
- Công việc thoát với mã lỗi.
- Hết thời hạn nhưng tiến trình còn sống.
- Luồng điều phối Java bị ngắt.
- Giao tiếp I/O thất bại.
- Ứng dụng không còn cần công việc đó.

Chỉ tạo tiến trình rồi bỏ tham chiếu không phải một cơ chế dừng. API Process nêu rõ tiến trình không tự bị hủy chỉ vì không còn tham chiếu Java đến đối tượng `Process`. Xem [vòng đời Process](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html).

Một quy trình đầy đủ cần phân biệt:

```text
Đã gửi yêu cầu dừng
        ≠
Đã xác nhận tiến trình kết thúc
        ≠
Công việc nghiệp vụ đã thành công
```

## 2. Những thao tác chính và ý nghĩa thực tế

| API | Ý nghĩa |
| --- | --- |
| `isAlive()` | Quan sát tiến trình còn sống tại thời điểm gọi |
| `waitFor()` | Chờ tiến trình kết thúc và lấy exit code |
| `waitFor(timeout, unit)` | Chờ có thời hạn, trả true nếu đã kết thúc |
| `exitValue()` | Lấy exit code nếu đã kết thúc; nếu còn chạy thì báo lỗi |
| `destroy()` | Yêu cầu kết thúc theo cơ chế triển khai/nền tảng |
| `destroyForcibly()` | Yêu cầu kết thúc cưỡng bức cho Process do ProcessBuilder tạo |
| `onExit()` | Future hoàn tất khi tiến trình kết thúc |

Các quan sát có thể thay đổi giữa hai lời gọi vì tiến trình có thể tự kết thúc bất cứ lúc nào. Đừng coi một lần `isAlive()` là quyền giữ cho tiến trình tồn tại hoặc một giao dịch khóa trạng thái.

Đặc biệt, `waitFor(timeout, unit)` trả `false` chỉ nói rằng tiến trình chưa được quan sát kết thúc trong thời hạn chờ đó. Nó **không tự gọi destroy**.

## 3. destroy() không có cùng bảo đảm “êm” trên mọi hệ điều hành

Một diễn giải quá đơn giản là “destroy luôn dừng nhẹ, destroyForcibly luôn dừng mạnh”. Cần hiểu chính xác hơn.

`Process.destroy()` yêu cầu kết thúc, nhưng việc nó là kết thúc bình thường hay cưỡng bức phụ thuộc triển khai nền tảng. `supportsNormalTermination()` có thể cho biết cách `destroy()` của triển khai xử lý việc này; một triển khai không hỗ trợ API đó có thể ném `UnsupportedOperationException`. Xem [supportsNormalTermination](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html#supportsNormalTermination()).

Do đó không giả định:

- `destroy()` luôn gửi cùng một loại tín hiệu trên mọi hệ điều hành.
- Tiến trình luôn được chạy mọi bước dọn dẹp của ứng dụng.
- Shutdown hook hoặc khối `finally` của tiến trình con luôn chạy.
- Mọi dữ liệu đang đệm chắc chắn được ghi xong.

Nếu cần **dừng hợp tác ở cấp ứng dụng**, ưu tiên giao thức của chính chương trình con khi có:

```text
Gửi lệnh dừng được chương trình hỗ trợ
    ↓
Cho chương trình ngừng nhận việc mới, hoàn tất phần cần thiết
    ↓
Chờ xác nhận hoặc chờ tiến trình thoát
    ↓ nếu không đáp ứng trong thời hạn
Chuyển sang yêu cầu kết thúc ở cấp hệ điều hành
```

Đóng stdin có thể là tín hiệu kết thúc với một công cụ đọc đến EOF, nhưng không có nghĩa tương tự cho mọi chương trình. Phải biết giao thức của chương trình được chạy.

## 4. destroyForcibly() vẫn cần được quan sát kết quả

Với tiến trình do `ProcessBuilder.start()` tạo, `destroyForcibly()` thực hiện yêu cầu kết thúc cưỡng bức. Nó trả về đối tượng Process, không phải một boolean chứng minh tiến trình đã dừng ngay lập tức.

API lưu ý `isAlive()` có thể vẫn trả true trong một khoảng ngắn sau lời gọi. Nếu cần xác nhận, hãy chờ:

```java
// Mã minh họa trong phương thức xử lý InterruptedException.
process.destroyForcibly();
boolean stopped = process.waitFor(3, TimeUnit.SECONDS);
if (!stopped) {
    reportTerminationNotConfirmed();
}
```

Xem [destroyForcibly](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html#destroyForcibly()).

Không dùng vòng lặp quay liên tục gọi `destroyForcibly()` mà không có chính sách thời gian. Nếu không xác nhận được kết thúc, cần trả trạng thái rõ ràng hoặc chuyển tới tầng giám sát; không in “đã dừng” chỉ vì lệnh hủy đã được gọi.

Kết thúc cưỡng bức cũng không hoàn tác tác dụng phụ mà tiến trình đã tạo. Một tệp có thể được ghi một phần, một yêu cầu mạng có thể đã được gửi hoặc một giao dịch bên ngoài đã được chấp nhận.

## 5. Quy trình dừng theo nhiều mức

Một chính sách thường gặp:

```text
Chạy công việc và theo dõi I/O
    ↓
Còn trong thời hạn chạy?
    ├─ Có → tiếp tục theo dõi
    └─ Không
         ↓
Yêu cầu dừng hợp tác nếu chương trình có giao thức phù hợp
         ↓ chờ một khoảng có giới hạn
destroy()
         ↓ chờ một khoảng có giới hạn
destroyForcibly()
         ↓ chờ xác nhận có giới hạn
Ghi nhận kết quả dừng và hoàn tất dọn tài nguyên
```

Không phải mọi hệ thống cần đủ mọi mức. Điều quan trọng là xác định:

- Khi nào chuyển mức.
- Thời gian dành cho từng mức.
- Tình trạng nào được xem là kết thúc đã xác nhận.
- Ai còn giữ trách nhiệm nếu chưa dừng được.
- Dữ liệu đầu ra và tài nguyên được thu hồi thế nào.

Nếu yêu cầu là tổng thời hạn 10 giây, việc chờ 10 giây rồi chờ thêm 5 và 5 giây không còn là tổng 10 giây. Phân biệt ngân sách thực thi với ngân sách dọn dẹp, hoặc tính thời gian còn lại từ một deadline đơn điệu bằng `System.nanoTime()`.

## 6. Ví dụ đầy đủ: nhận biết sẵn sàng rồi dừng và xác nhận

Chương trình tạo một tiến trình Java con có hành vi kiểm soát được:

- Con in một dòng `READY`, rồi chờ một tín hiệu không bao giờ được phát trong ví dụ.
- Cha đọc dòng sẵn sàng bằng một tác vụ riêng có giới hạn chờ.
- Cha kiểm tra rằng con chưa tự kết thúc.
- Hàm `stop` gọi `destroy()`, chờ, rồi tăng mức nếu cần.
- Cha chỉ báo đã dừng sau khi đã quan sát tiến trình kết thúc.

Tệp `ProcessLifecycleDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ProcessLifecycleDemo {
    private static void stop(Process process)
            throws InterruptedException, IOException {
        if (!process.isAlive()) {
            return;
        }

        process.destroy();
        if (process.waitFor(1, TimeUnit.SECONDS)) {
            return;
        }

        process.destroyForcibly();
        if (!process.waitFor(3, TimeUnit.SECONDS)) {
            throw new IOException("Termination was not confirmed");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("child")) {
            System.out.println("READY");
            System.out.flush();
            new CountDownLatch(1).await();
            return;
        }

        Path bin = Path.of(System.getProperty("java.home"), "bin");
        Path java = bin.resolve("java");
        if (!Files.isRegularFile(java)) {
            java = bin.resolve("java.exe");
        }

        ProcessBuilder builder = new ProcessBuilder(
                java.toString(), "-cp", System.getProperty("java.class.path"),
                ProcessLifecycleDemo.class.getName(), "child");
        builder.redirectError(ProcessBuilder.Redirect.DISCARD);
        Process process = builder.start();
        ExecutorService reader = Executors.newSingleThreadExecutor();

        try {
            Future<String> ready = reader.submit(() -> {
                BufferedReader input = new BufferedReader(new InputStreamReader(
                        process.getInputStream(), StandardCharsets.UTF_8));
                return input.readLine();
            });
            process.getOutputStream().close();

            if (!"READY".equals(ready.get(5, TimeUnit.SECONDS))) {
                throw new IOException("Child did not announce readiness");
            }
            System.out.println("ready=true");

            boolean completed = process.waitFor(100, TimeUnit.MILLISECONDS);
            System.out.println("completedBeforeStop=" + completed);

            stop(process);
            System.out.println("stopped=" + !process.isAlive());
        } finally {
            try {
                if (process.isAlive()) {
                    process.destroyForcibly();
                    if (!process.waitFor(3, TimeUnit.SECONDS)) {
                        throw new IOException("Cleanup did not terminate child");
                    }
                }
            } finally {
                reader.shutdownNow();
                process.getInputStream().close();
                process.getErrorStream().close();
                process.getOutputStream().close();
            }
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac ProcessLifecycleDemo.java
java ProcessLifecycleDemo
```

Kết quả khi khởi động và dọn dẹp hoàn tất trong thời hạn:

```text
ready=true
completedBeforeStop=false
stopped=true
```

Các dòng không phụ thuộc exit code cụ thể của một tiến trình bị dừng trên từng hệ điều hành.

### Vì sao có bước READY?

Cha không đoán tiến trình đã khởi tạo bằng một khoảng `sleep`. Nó chờ một dấu hiệu do chính con phát.

Khoảng chờ 100 ms sau READY chỉ để minh họa rằng con vẫn đang chạy khi chưa được yêu cầu dừng. Nó không được dùng để chứng minh khởi tạo đã xong.

### Vì sao ví dụ chỉ đọc một dòng stdout?

Tiến trình con được viết trong ví dụ chỉ xuất đúng một dòng rồi không ghi thêm. Với một công cụ tùy ý có log liên tục, phải tổ chức đọc đến EOF hoặc chuyển hướng đầu ra phù hợp; không sao chép cách đọc một dòng rồi bỏ phần còn lại.

Stderr được bỏ có chủ ý trong ví dụ kiểm soát này. Với chẩn đoán thực tế, có thể cần giữ stderr trong một tệp hoặc bộ đệm có giới hạn thay vì bỏ.

### Phạm vi của hàm stop

Hàm xử lý một tiến trình trực tiếp, không quản lý cây tiến trình. Nó thử mức `destroy()` trước, nhưng không khẳng định mức đó luôn là dừng hợp tác trên mọi nền tảng.

Khối finally vẫn yêu cầu hủy nếu đường chính thoát sớm. Một bộ quản lý sản xuất cần thêm chính sách bảo toàn lỗi gốc khi dọn dẹp cũng lỗi, quản lý tiến trình con cháu và thu thập đầu ra theo giao thức thật.

## 7. Dừng tiến trình và quản lý stream là hai trách nhiệm nối tiếp

Một Process có stdin, stdout và stderr. Quản lý vòng đời phải xét cả ba:

- Nếu không gửi đầu vào nữa và chương trình con cần EOF, đóng stream ghi stdin.
- Khi còn giữ stdout/stderr dưới dạng pipe, bảo đảm có bên tiêu thụ trong lúc con có thể ghi.
- Sau khi con kết thúc, chờ bên đọc hoàn tất theo chính sách đầu ra.
- Đóng các stream và dừng các tác vụ hỗ trợ.
- Nếu lỗi đọc xảy ra, đưa nó về bên quản lý tiến trình.

Không đọc stdout/stderr có thể làm pipe đầy, khiến con không thể kết thúc tự nhiên. Trong tình huống đó, chỉ tăng thời hạn waitFor không sửa nguyên nhân.

Cũng không đóng tùy tiện stream đọc rồi coi công việc đã dừng; điều đó chỉ thay đổi giao tiếp và có thể làm con gặp lỗi ghi trong khi vẫn còn sống.

Đối với tiến trình tương tác, đóng stdin quá sớm có thể cắt dữ liệu cần gửi. Vòng đời I/O phải theo giao thức chứ không chỉ theo việc mã Java vừa ra khỏi một khối lệnh.

## 8. Ngắt luồng Java không tự hủy tiến trình con

Nếu luồng đang `waitFor()` bị ngắt, nó có thể nhận `InterruptedException`. Tiến trình hệ điều hành không tự nhận cùng một lệnh hủy chỉ vì luồng Java đó bị ngắt.

Cần có chính sách rõ:

- Chuyển tiếp ngoại lệ sau khi thực hiện phần dọn dẹp mà phương thức chịu trách nhiệm.
- Hoặc bắt tại ranh giới tác vụ, yêu cầu dừng công việc theo hợp đồng, khôi phục cờ ngắt nếu không chuyển tiếp ngoại lệ.
- Không tiếp tục đường “thành công” sau khi đã bị ngắt và chưa có kết quả.

```java
// Mã minh họa một phần chính sách trong Runnable.
// Quản lý I/O và xác nhận dừng vẫn thuộc tầng điều phối.
try {
    process.waitFor();
} catch (InterruptedException interrupted) {
    process.destroy();
    Thread.currentThread().interrupt();
    return;
}
```

Đoạn trên chỉ minh họa việc không nuốt cờ ngắt; nó chưa phải một quy trình dừng đầy đủ vì chưa xác nhận kết thúc hoặc tăng mức.

Nếu một phương thức giữ nguyên `throws InterruptedException`, không cần tự bắt rồi khôi phục cờ chỉ để ném lại cùng ngoại lệ. Điều cần quyết định là trách nhiệm tài nguyên khi đường chờ bị ngắt.

## 9. onExit hỗ trợ theo dõi, không tự tạo chính sách hủy

Có thể theo dõi bất đồng bộ:

```java
// Mã minh họa; đây là Future của việc kết thúc tiến trình.
CompletableFuture<Process> completion = process.onExit();
completion.thenAccept(ended -> recordExitCode(ended.exitValue()));
```

Future hoàn tất khi tiến trình kết thúc, kể cả exit code khác 0. Nó không tự coi exit code lỗi là một lần hoàn tất ngoại lệ.

Hủy Future trả về bởi `onExit()` không làm Process bị hủy. Tương tự, một timeout ở lớp chờ Future chỉ báo việc chờ đã quá hạn; ứng dụng vẫn cần gọi chính sách dừng tiến trình. Xem [Process.onExit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html#onExit()).

Không đặt công việc dọn dẹp quan trọng chỉ trong một callback mà không quản lý vòng đời và lỗi của callback đó. Cần xác định bên nào chịu trách nhiệm ngay cả khi luồng hoặc bộ thực thi hỗ trợ đang kết thúc.

## 10. Tiến trình trực tiếp không đồng nghĩa toàn bộ cây công việc

Một công cụ có thể tạo thêm tiến trình:

```text
Java cha
    ↓
Process trực tiếp: công cụ điều phối
    ├─ tiến trình làm việc 1
    └─ tiến trình làm việc 2
```

Gọi destroy trên Process trực tiếp không có bảo đảm chung là mọi tiến trình bên dưới đều dừng.

`ProcessHandle` hỗ trợ quan sát `children()`, `descendants()` và điều khiển tiến trình. Nhưng danh sách là ảnh chụp: tiến trình có thể được sinh thêm hoặc kết thúc trong lúc đang kiểm tra. Xem [ProcessHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html).

Cần lưu ý:

- Lấy danh sách sau khi tiến trình cha đã thoát có thể không còn thấy quan hệ cây như trước.
- Một snapshot không đóng băng cây tiến trình.
- Chỉ quản lý những tiến trình thuộc công việc đã khởi chạy và có quyền quản lý.
- PID có thể được hệ điều hành tái sử dụng; không lưu một PID lâu rồi mặc định nó vẫn chỉ cùng một công việc.
- Với yêu cầu dừng cả nhóm đáng tin cậy, có thể cần cơ chế cấp hệ điều hành, container hoặc bộ giám sát phù hợp.

Không gọi lệnh dừng theo một tên tiến trình chung để thay thế việc theo dõi đúng công việc. Việc đó có thể tác động tới các công việc độc lập khác cùng chạy chương trình.

Cũng phân biệt `Process.destroy()` trả về void với `ProcessHandle.destroy()` trả boolean. Không dùng hai hợp đồng như thể chúng giống nhau.

## 11. Ghi nhận kết quả vòng đời tách khỏi exit code

Một kết quả quản lý hữu ích có thể lưu các thông tin song song:

| Thông tin | Ví dụ ý nghĩa |
| --- | --- |
| Khởi động thành công không | Có tạo được Process hay start ném IOException? |
| Nguyên nhân kết thúc theo dõi | Hoàn tất tự nhiên, timeout, yêu cầu người dùng, lỗi I/O, ngắt |
| Có gửi yêu cầu dừng không | Không, destroy, destroyForcibly hoặc giao thức riêng |
| Đã xác nhận kết thúc chưa | waitFor thành công hay còn chưa rõ |
| Exit code | Chỉ đọc khi tiến trình đã kết thúc |
| Tình trạng đầu ra | Đã đọc hết, bị giới hạn, lỗi đọc hoặc chưa hoàn tất |
| Lỗi dọn dẹp | Có còn tài nguyên hoặc tiến trình cần xử lý không? |

Một tiến trình timeout rồi được hủy không biến thành “thành công” chỉ vì sau đó đã có exit code. Ngược lại, một mã khác 0 cần được diễn giải theo quy ước của công cụ; không bịa cùng một ý nghĩa cho mọi chương trình.

Exit code khi bị dừng có thể khác giữa hệ điều hành và chương trình. Đừng đóng đinh một con số duy nhất làm bằng chứng duy nhất rằng cơ chế hủy đã hoạt động.

Nếu start thất bại, chưa có Process để gọi destroy; cần báo lỗi khởi động cùng ngữ cảnh lệnh và đường dẫn thích hợp.

## 12. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề |
| --- | --- |
| Bỏ biến Process rồi chờ GC | Tiến trình không tự bị hủy vì mất tham chiếu |
| waitFor có timeout rồi trả về luôn | Con có thể tiếp tục chạy ngoài ý muốn |
| Gọi destroy rồi lập tức báo đã dừng | Chưa xác nhận kết thúc |
| Chỉ gọi destroyForcibly rồi không đợi | Trạng thái có thể chưa chuyển ngay |
| Hủy Future của onExit | Không tự hủy tiến trình |
| Dừng cha trực tiếp rồi coi mọi tiến trình cháu đã dừng | Không có bảo đảm chung |
| Chỉ quản lý PID, không quản lý I/O | Có thể bỏ sót pipe, luồng đọc và phần log chưa xử lý |
| Bắt lỗi dọn dẹp rồi bỏ qua mọi trạng thái | Không còn biết công việc thật sự đã kết thúc chưa |

Bài tập: bỏ `stop(process)` khỏi ví dụ nhưng vẫn in `stopped=true`. Vì sao thông báo đó sai? Vì chương trình chỉ chờ 100 ms, chưa có hành động dừng hay xác nhận kết thúc nào ở đường đó. Khối finally có thể dọn sau, nhưng nó không làm thông báo trước đó trở nên đúng tại thời điểm được in.

Quản lý vòng đời nghĩa là **có bên chịu trách nhiệm từ lúc khởi động, qua theo dõi và yêu cầu dừng, đến xác nhận kết thúc cùng việc hoàn tất I/O và tài nguyên**.
