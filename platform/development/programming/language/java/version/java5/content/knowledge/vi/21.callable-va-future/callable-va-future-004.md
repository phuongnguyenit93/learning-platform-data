# ExecutionException và truy nguyên lỗi gốc

## 1. Một lỗi, hai nơi quan sát

Khi gọi một hàm thông thường, ngoại lệ thường đi trực tiếp về bên gọi trên cùng luồng. Với `Callable` gửi qua bộ thực thi, có hai thời điểm khác nhau:

1. Bên gửi gọi `submit` và nhận `Future`.
2. Tác vụ chạy, có thể thất bại; sau đó bên đọc gọi `Future.get()` để lấy kết quả.

`ExecutionException` báo rằng **phép tính bất đồng bộ đã kết thúc bằng lỗi** khi bên đọc cố lấy kết quả. Nó là lớp bao; nguyên nhân tác vụ ném ra được truy cập qua `getCause()`. [Tài liệu ExecutionException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutionException.html)

Có thể hình dung:

```text
Luồng gửi/chờ                         Luồng thực hiện tác vụ
submit(callable) -------------------> callable.call()
nhận Future                             |
                                        +-- ném IOException
                                        |
Future.get() <----------------------- lưu trạng thái thất bại
    |
    +-- ném ExecutionException
            |
            +-- cause: IOException
```

`submit` trả về không chứng minh tác vụ thành công. `get()` ném `ExecutionException` cũng không có nghĩa chính thao tác chờ làm hỏng dữ liệu: cần kiểm tra lỗi mà tác vụ đã ghi nhận.

Bài dùng Java 17+ và các hợp đồng vẫn áp dụng trên Java hiện đại.

## 2. Phân loại đúng trước khi truy nguyên

| Ngoại lệ quan sát | Thường xuất hiện ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `RejectedExecutionException` | Lúc gửi việc vào bộ thực thi theo chính sách từ chối | Tác vụ không được tiếp nhận để thực thi theo yêu cầu |
| `ExecutionException` | `Future.get()` | Tác vụ kết thúc bằng lỗi |
| `InterruptedException` | Luồng đang gọi `get()` bị ngắt | Việc chờ bị gián đoạn |
| `TimeoutException` | `get(timeout, unit)` | Hết thời gian chờ kết quả |
| `CancellationException` | `get()` trên tác vụ bị hủy | Kết quả không được trả theo đường thành công |

Đừng gom tất cả thành “tác vụ lỗi”. Ví dụ, timeout của bên chờ không tự chứng minh tác vụ đã thất bại hoặc dừng. Ngắt bên chờ cũng không tự hủy công việc. [Tài liệu Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Ngược lại, nếu **chính tác vụ** ném `InterruptedException` ra khỏi `call()`, lỗi đó có thể được quan sát dưới dạng `ExecutionException` có cause là `InterruptedException`. Luồng bị ngắt ở đâu là thông tin quyết định cách xử lý.

## 3. Ví dụ đầy đủ: nguyên nhân có thể có nhiều lớp

Tác vụ tạo báo cáo có thể chuyển lỗi nguồn dữ liệu thành lỗi nghiệp vụ rồi thất bại. Bên đọc nhìn thấy chuỗi:

```text
ExecutionException
    -> ReportFailure
        -> IOException
```

Tệp **ExecutionCauseDemo.java**:

```java
import java.io.IOException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutionCauseDemo {
    static final class ReportFailure extends Exception {
        ReportFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        AtomicInteger attempts = new AtomicInteger();

        try {
            Future<String> future = pool.submit(() -> {
                attempts.incrementAndGet();
                throw new ReportFailure(
                        "Cannot create report R7",
                        new IOException("Source unavailable"));
            });

            try {
                future.get();
            } catch (ExecutionException ex) {
                Throwable taskFailure = ex.getCause();
                Throwable origin = taskFailure.getCause();

                System.out.println("wrapper=" + ex.getClass().getSimpleName());
                System.out.println("taskFailure="
                        + taskFailure.getClass().getSimpleName());
                System.out.println("taskMessage=" + taskFailure.getMessage());
                System.out.println("origin=" + origin.getClass().getSimpleName());
                System.out.println("originMessage=" + origin.getMessage());
            }

            System.out.println("done=" + future.isDone());
            System.out.println("cancelled=" + future.isCancelled());

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("secondGet=failedAgain");
            }
            System.out.println("attempts=" + attempts.get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 ExecutionCauseDemo.java
java ExecutionCauseDemo
```

Stdout:

```text
wrapper=ExecutionException
taskFailure=ReportFailure
taskMessage=Cannot create report R7
origin=IOException
originMessage=Source unavailable
done=true
cancelled=false
secondGet=failedAgain
attempts=1
```

Điểm cần đọc đúng:

- Cause trực tiếp là `ReportFailure`, không phải ngay lập tức là `IOException`.
- Lớp nghiệp vụ bổ sung báo cáo nào thất bại; lớp trong bổ sung loại lỗi nguồn dữ liệu.
- `isDone() == true` không đồng nghĩa thành công.
- Đọc lại cùng `Future` không chạy lại tác vụ. Lỗi vẫn được báo, còn `attempts` vẫn bằng 1.
- Lỗi không đồng nghĩa hủy: ví dụ này `isCancelled()` vẫn bằng `false`.

Trong chương trình, hai lần `getCause()` là có chủ đích vì chính ta tạo chuỗi ba lớp đã biết. Với lỗi lấy từ thư viện hoặc hệ thống ngoài, không được giả định độ sâu đó.

## 4. Đọc stack trace theo các tầng

Khi có lỗi thực tế, chỉ ghi `ex.getMessage()` thường chưa đủ. Thông điệp có thể thiếu, trùng lặp hoặc chỉ mô tả lớp bao.

Một stack trace đầy đủ giúp phân biệt:

1. Nơi bên đọc gọi `get()` và nhận `ExecutionException`.
2. Nơi mã nghiệp vụ tạo ngoại lệ của tác vụ.
3. Các lớp `Caused by` ở dưới, mô tả nguyên nhân sâu hơn.
4. Các lỗi `Suppressed`, nếu có, chẳng hạn lỗi dọn tài nguyên phát sinh khi đang xử lý một lỗi khác.

Một mẫu thường gặp, chỉ minh họa cấu trúc, không phải stdout của chương trình:

```text
ExecutionException
    tại mã chờ kết quả
Caused by: ReportFailure
    tại mã tạo báo cáo
Caused by: IOException
    tại mã đọc nguồn dữ liệu
```

Không xác định vị trí hỏng chỉ từ dòng trên cùng. Dòng đầu có thể chỉ nói nơi tác vụ được quan sát là thất bại. Hãy nối bối cảnh của bên gọi với ngăn xếp của tác vụ.

`Throwable` hỗ trợ cả nguyên nhân (`cause`) và các ngoại lệ bị giữ kèm (`suppressed`). Chuỗi cause không phải toàn bộ cấu trúc lỗi; chỉ đi tới phần tử sâu nhất có thể bỏ qua lỗi dọn dẹp và ngữ cảnh trung gian. [Tài liệu Throwable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html)

### Nguyên nhân sâu nhất chưa phải toàn bộ lời giải thích

`IOException` cho biết một thao tác I/O thất bại, nhưng `ReportFailure("Cannot create report R7")` cho biết thao tác nghiệp vụ nào bị ảnh hưởng. Cả hai đều có giá trị.

Không phân loại lỗi bằng cách so sánh thông điệp văn bản như `message.contains("timeout")`. Thông điệp có thể thay đổi theo thư viện hoặc ngôn ngữ. Ưu tiên kiểu ngoại lệ, mã lỗi có hợp đồng và ngữ cảnh thao tác.

Cũng không khẳng định tác động nghiệp vụ chỉ từ kiểu ngoại lệ sâu nhất. Muốn quyết định có thể thử lại hay không, còn cần biết tác vụ đã làm gì trước lúc lỗi.

## 5. Duyệt chuỗi cause để chẩn đoán

Đoạn sau là **phương thức tiện ích**, đặt trong một lớp sau khi nhập các lớp collection tương ứng:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

static List<String> causeTypes(Throwable failure) {
    Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
    List<String> types = new ArrayList<>();

    for (Throwable current = failure;
         current != null && seen.add(current);
         current = current.getCause()) {
        types.add(current.getClass().getSimpleName());
    }
    return types;
}
```

Với ngoại lệ ở ví dụ trước, danh sách kiểu là:

```text
[ExecutionException, ReportFailure, IOException]
```

Tập `seen` dùng danh tính đối tượng, tránh vòng lặp vô hạn nếu gặp chuỗi nguyên nhân có vòng. Đoạn tiện ích chỉ phục vụ quan sát chuỗi cause; nó không thay stack trace đầy đủ và không thu thập cây suppressed exceptions.

Không viết vòng `while (error.getCause() != null)` rồi tự động ném lỗi sâu nhất trong mọi tình huống. Việc bỏ lớp bao phải dựa trên hợp đồng của API và mục đích của tầng đang xử lý.

## 6. Chuyển lỗi sang tầng nghiệp vụ mà không làm mất bằng chứng

Khi một hàm nghiệp vụ không muốn lộ `ExecutionException` trong API, có thể chuyển thành ngoại lệ của tầng đó và **giữ cause**.

Ví dụ dưới đây là các khai báo trong một lớp; cần nhập `ExecutionException` và `Future`:

```java
static final class ReportUnavailableException extends RuntimeException {
    ReportUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

static String awaitReport(Future<String> future, String reportId)
        throws InterruptedException {
    try {
        return future.get();
    } catch (ExecutionException ex) {
        Throwable taskFailure = ex.getCause();

        if (taskFailure instanceof Error error) {
            throw error;
        }

        throw new ReportUnavailableException(
                "Report " + reportId + " could not be generated", ex);
    }
}
```

Đoạn này:

- Thêm ngữ cảnh báo cáo tại tầng nghiệp vụ.
- Giữ `ExecutionException` làm cause để còn mốc quan sát bất đồng bộ và toàn bộ nguyên nhân tác vụ bên trong.
- Truyền `InterruptedException` cho tầng gọi; không biến yêu cầu ngắt thành lỗi báo cáo thông thường.
- Không chuyển `Error` trực tiếp của tác vụ thành lỗi nghiệp vụ có vẻ dễ phục hồi.

Nhánh `Error` là chính sách thể hiện tường minh trong ví dụ, không phải khuôn xử lý bắt buộc cho mọi hệ thống. Cần phân loại những lỗi dự kiến theo hợp đồng cụ thể; tránh bắt mọi `Throwable` rồi trả dữ liệu mặc định.

Có thể chọn giữ trực tiếp `taskFailure` làm cause trong một API khác, nếu đã chủ động quyết định loại bỏ lớp bao và vẫn giữ đủ thông tin cần thiết. Điều quan trọng là không làm mất nguyên nhân bằng cách chỉ chuyển chuỗi message.

Hai cách làm mất bằng chứng thường gặp:

```text
ném ngoại lệ mới chỉ có ex.getMessage()
bắt lỗi, ghi "failed" rồi trả kết quả mặc định như thành công
```

Nếu nghiệp vụ có kết quả dự phòng hợp lệ, hãy biểu diễn nó rõ là kết quả dự phòng và giữ khả năng quan sát lỗi; không làm người gọi tưởng dữ liệu chính đã được tạo thành công.

## 7. Ngắt bên chờ khác ngắt bên thực hiện

Tệp **InterruptLocationDemo.java** minh họa hai trường hợp độc lập:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class InterruptLocationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<String> taskFailure = pool.submit(() -> {
                throw new InterruptedException("Task could not continue");
            });

            try {
                taskFailure.get();
            } catch (ExecutionException ex) {
                System.out.println("taskFailureCause="
                        + ex.getCause().getClass().getSimpleName());
                System.out.println("mainInterrupted="
                        + Thread.currentThread().isInterrupted());
            }

            FutureTask<String> pending = new FutureTask<>(() -> "unused");

            Thread waiter = new Thread(() -> {
                Thread.currentThread().interrupt();
                try {
                    pending.get();
                } catch (InterruptedException ex) {
                    System.out.println("waitingGet=InterruptedException");
                    Thread.currentThread().interrupt();
                    System.out.println("waiterRestoredInterrupt="
                            + Thread.currentThread().isInterrupted());
                } catch (ExecutionException ex) {
                    throw new AssertionError("Unexpected task failure", ex);
                }
            });

            waiter.start();
            waiter.join();

            System.out.println("pendingDoneAfterWaiterExit=" + pending.isDone());
            pending.cancel(false);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 InterruptLocationDemo.java
java InterruptLocationDemo
```

Stdout:

```text
taskFailureCause=InterruptedException
mainInterrupted=false
waitingGet=InterruptedException
waiterRestoredInterrupt=true
pendingDoneAfterWaiterExit=false
```

Trong phần đầu, tác vụ **chủ động ném** `InterruptedException` để tạo trạng thái lỗi cho thí nghiệm. Luồng `main` nhận lớp bao, nhưng bản thân nó không bị ngắt.

Trong phần sau, `FutureTask` được tạo mà chưa được chạy, bảo đảm chưa có kết quả. Luồng chờ tự đặt cờ ngắt trước khi gọi `get()`; việc chờ bị gián đoạn. Nó khôi phục cờ ngắt rồi kết thúc. Việc chờ kết thúc không làm `pending` tự hoàn thành hay tự hủy, nên chương trình hủy nó riêng ở cuối.

Không đặt cờ ngắt cho luồng đang chờ chỉ vì thấy cause của `ExecutionException` là `InterruptedException`: tín hiệu đó có thể thuộc luồng tác vụ. Chỉ truyền hoặc khôi phục tín hiệu ngắt theo đúng luồng và đúng hợp đồng đang xử lý.

## 8. Lỗi được lưu trong Future cần người quan sát

Với tác vụ được bao bằng `FutureTask`, lỗi của phép tính được ghi nhận để `get()` báo lại. Tác vụ kết thúc lỗi không làm việc đọc lại cùng Future khởi chạy phép tính lần nữa. [Tài liệu FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html)

Nếu dùng `submit` rồi bỏ luôn Future, lỗi có thể không tới nơi xử lý nghiệp vụ. Một `UncaughtExceptionHandler` của luồng làm việc không thay thế việc quan sát lỗi đã được lớp bao giữ lại.

Cần xác định rõ thành phần nào:

- Thu thập kết quả của mỗi tác vụ.
- Gắn lỗi với mã tác vụ hoặc thao tác.
- Quyết định tiếp tục các tác vụ độc lập hay hủy phần còn lại.
- Báo thành công, thất bại hoặc kết quả một phần cho người gọi.

Ghi nhật ký ở nơi đủ ngữ cảnh rồi chuyển tiếp lỗi nếu cần; tránh nhiều tầng ghi cùng một stack trace mà không bổ sung thông tin. Khi log, truyền đối tượng ngoại lệ cho API logger phù hợp để giữ stack trace và nguyên nhân, thay vì chỉ ghép `getMessage()` vào chuỗi.

## 9. Thử lại phải là một quyết định riêng

Sau `ExecutionException`, gọi `future.get()` thêm lần nữa không phải thử lại công việc. Muốn chạy lại phải tạo/gửi một tác vụ mới theo chính sách.

Trước khi thử lại, cần hỏi:

1. Lỗi có khả năng tạm thời không?
2. Tác vụ đã tạo tác dụng phụ nào?
3. Gửi lại có làm trùng thao tác không?
4. Còn ngân sách thời gian và số lượt thử không?
5. Người gọi có đang yêu cầu hủy hoặc dừng không?

Ví dụ, tác vụ gửi yêu cầu thanh toán rồi lỗi khi đọc phản hồi không thể được coi chắc chắn là “chưa thanh toán”. Nguyên nhân I/O không đủ chứng minh thao tác bên kia chưa xảy ra. Hợp đồng định danh yêu cầu và khả năng chạy lại an toàn mới quyết định cách xử lý.

## 10. Tự truy nguyên một chuỗi lỗi

Một luồng đọc kết quả thấy:

```text
ExecutionException
    -> ExportFailedException
        -> IOException
```

Đừng dừng ở câu “Future bị lỗi”. Hãy xác định thao tác xuất nào, lớp mã nào thêm ngữ cảnh, I/O nào thất bại, có lỗi suppressed không và phần công việc nào đã thực hiện.

Khi đã phân biệt **lỗi được quan sát ở đâu**, **tác vụ ném gì** và **nguyên nhân nào được giữ lại**, bạn mới có cơ sở chọn báo lỗi, trả kết quả một phần, hủy các việc liên quan hoặc thử lại.
