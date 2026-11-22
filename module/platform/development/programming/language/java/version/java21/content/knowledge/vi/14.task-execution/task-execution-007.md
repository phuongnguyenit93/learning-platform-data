# Hủy task bằng Future.cancel và giới hạn của interruption

`Future.cancel()` cho phép yêu cầu hủy một tác vụ đã được gửi tới executor. Khi gọi `cancel(true)`, Future có thể interrupt thread đang thực thi tác vụ nếu tác vụ đã bắt đầu. Tuy nhiên, interruption là cơ chế hợp tác: nó gửi tín hiệu để mã đang chạy có cơ hội dừng, không cưỡng bức kết thúc thread hay hoàn tác những thay đổi đã thực hiện.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần phân biệt trạng thái hủy của `Future` với việc mã tác vụ đã thực sự kết thúc. `Future` có thể báo đã hủy trong khi tác vụ vẫn đang chạy nếu tác vụ không phản hồi interruption. Điều này đặc biệt quan trọng với tác vụ CPU-bound, lời gọi I/O không hỗ trợ interruption và các tác vụ có bước giải phóng tài nguyên.

## Future là handle để theo dõi và yêu cầu hủy task

Khi gửi một tác vụ bằng `ExecutorService.submit()`, chương trình nhận lại một `Future`. Đối tượng này cho phép kiểm tra trạng thái, lấy kết quả và yêu cầu hủy:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
    Future<String> future = executor.submit(() -> {
        performWork();
        return "completed";
    });

    // Có thể kiểm tra trạng thái hoặc yêu cầu hủy qua future.
    boolean cancelled = future.cancel(true);
}
```

`Future` là handle của tác vụ được submit, không phải thread thực thi. Với executor, thread thực hiện công việc có thể do executor quản lý và không cần được gọi trực tiếp từ mã gửi tác vụ. Khi cần hủy, hãy dùng `Future.cancel()` hoặc cơ chế quản lý task tương ứng thay vì tìm thread bên trong executor.

## cancel(true) và cancel(false) khác nhau thế nào?

Phương thức có chữ ký `cancel(boolean mayInterruptIfRunning)`. Tham số quyết định có cho phép interrupt thread thực thi tác vụ đang chạy hay không:

| Lệnh | Tác vụ chưa bắt đầu | Tác vụ đang chạy |
| --- | --- | --- |
| `cancel(true)` | Ngăn tác vụ bắt đầu nếu việc hủy thành công | Yêu cầu interrupt thread đang chạy tác vụ |
| `cancel(false)` | Ngăn tác vụ bắt đầu nếu việc hủy thành công | Đánh dấu Future đã hủy nhưng không yêu cầu interrupt; mã tác vụ có thể tiếp tục chạy |

Nếu tác vụ đã hoàn tất hoặc đã bị hủy, lần gọi tiếp theo thường trả về `false`. Nếu hủy thành công, `cancel()` trả về `true` và Future chuyển sang trạng thái cancelled. Với tác vụ đang chạy, `cancel(true)` chỉ yêu cầu interrupt; kết quả cuối cùng phụ thuộc vào cách mã tác vụ và API mà nó gọi phản hồi tín hiệu đó.

Một điểm dễ nhầm: `future.isDone()` trả về `true` khi tác vụ hoàn tất bình thường, hoàn tất do lỗi hoặc đã bị hủy. Vì vậy, `isDone()` cùng với `isCancelled()` mô tả trạng thái của Future; chúng không chứng minh mã tác vụ đã chạy xong phần cleanup.

## Ví dụ hủy một tác vụ đang chạy

Ví dụ sau dùng `CountDownLatch` để biết tác vụ đã bắt đầu trước khi gửi yêu cầu hủy. Tác vụ kiểm tra interrupt status trong vòng lặp và xử lý `InterruptedException` khi đang ngủ:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CancellationExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    while (!Thread.currentThread().isInterrupted()) {
                        doOneUnitOfWork();
                        Thread.sleep(100);
                    }
                } catch (InterruptedException e) {
                    // Khôi phục trạng thái vì InterruptedException đã xóa cờ.
                    Thread.currentThread().interrupt();
                } finally {
                    releaseResources();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);
            System.out.println("Cancellation accepted: " + accepted);

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("Future is cancelled");
            }
        }
    }

    private static void doOneUnitOfWork() {
        // Thực hiện một phần công việc hữu hạn.
    }

    private static void releaseResources() {
        // Đóng hoặc giải phóng tài nguyên do task sở hữu.
    }
}
```

`cancel(true)` yêu cầu interrupt thread thực thi tác vụ. Nếu thread đang ở `Thread.sleep()`, thao tác này ném `InterruptedException`; khối `finally` vẫn chạy để giải phóng tài nguyên. Nếu interrupt đến trước khi tác vụ vào `sleep()`, vòng lặp cũng kiểm tra cờ interrupt và dừng.

`future.get()` ném `CancellationException` vì Future đã chuyển sang trạng thái cancelled. Exception này không phải bằng chứng rằng cleanup đã hoàn tất tại đúng thời điểm `get()` ném lỗi. Trong ví dụ, `ExecutorService.close()` được gọi khi rời try-with-resources; nó thực hiện shutdown có trật tự và chờ các tác vụ đang chạy kết thúc. Vì tác vụ phản hồi interruption, nó có thể kết thúc và giải phóng tài nguyên.

Các hàm `doOneUnitOfWork()` và `releaseResources()` đại diện cho logic của ứng dụng. Trong mã thực tế, cleanup nên nằm trong `finally` hoặc dùng try-with-resources cho các tài nguyên có hỗ trợ `AutoCloseable`.

## Interruption là tín hiệu hợp tác, không phải lệnh kill

`Thread.interrupt()` thay đổi trạng thái interrupt của thread hoặc đánh thức thread khỏi một số thao tác blocking có thể bị interrupt. Nó không buộc JVM dừng thread ngay lập tức. Mã đang chạy cần kiểm tra tín hiệu hoặc gọi API có hỗ trợ interruption để có thể phản hồi.

Hành vi thường gặp trong Java:

- Nếu thread đang ngủ trong `Thread.sleep()`, chờ bằng `Object.wait()` hoặc `Thread.join()`, interrupt làm thao tác ném `InterruptedException` và xóa interrupt status.
- Nếu thread không nằm trong một thao tác blocking có hành vi ném exception như trên, interrupt status thường được đặt thành `true`.
- Các API interruptible khác có quy tắc riêng. Ví dụ, thao tác trên interruptible channel có thể đóng channel và ném `ClosedByInterruptException`.
- Một đoạn code tính toán hoặc thư viện không kiểm tra/không phản hồi interruption có thể tiếp tục chạy.

Do đó, `cancel(true)` có thể rất hiệu quả với tác vụ dùng `sleep`, `wait`, `join`, các API interruptible hoặc vòng lặp có kiểm tra cờ. Nó không đảm bảo dừng ngay một lời gọi native, một thư viện bỏ qua interruption hoặc một vòng lặp CPU vô hạn không kiểm tra trạng thái.

## Kiểm tra interrupt status đúng cách

Java cung cấp hai cách kiểm tra thường gặp:

- `Thread.currentThread().isInterrupted()` đọc trạng thái interrupt của thread hiện tại nhưng không xóa cờ.
- `Thread.interrupted()` là phương thức static đọc trạng thái interrupt của thread hiện tại và đồng thời xóa cờ.

Trong vòng lặp xử lý tác vụ, `isInterrupted()` thường phù hợp hơn khi chỉ cần kiểm tra có nên dừng hay không:

```java
while (!Thread.currentThread().isInterrupted()) {
    processNextChunk();
}
```

Không gọi `Thread.interrupted()` chỉ để kiểm tra nếu chương trình cần giữ nguyên tín hiệu cho lớp gọi. Vì phương thức này xóa cờ, việc gọi nó có thể khiến đoạn mã phía sau không còn nhìn thấy yêu cầu hủy.

Nếu thao tác blocking ném `InterruptedException`, cờ interrupt thường đã được xóa. Nếu phương thức hiện tại có thể truyền `InterruptedException` lên, hãy khai báo `throws InterruptedException` và để tầng gọi quyết định. Nếu không thể truyền exception, thường cần khôi phục trạng thái rồi kết thúc hoặc chuyển sang đường xử lý hủy:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Không nên bắt `InterruptedException` rồi bỏ qua và tiếp tục như thể không có yêu cầu hủy. Cách đó làm mất tín hiệu và có thể khiến `Future.cancel(true)` không đạt mục tiêu.

## Tác vụ CPU-bound phải tự kiểm tra tín hiệu

Một vòng lặp tính toán không gọi API blocking có thể không nhận `InterruptedException`. Nó cần chủ động kiểm tra interrupt status tại những điểm an toàn:

```java
static void calculate() {
    while (!Thread.currentThread().isInterrupted()) {
        calculateOneBatch();
    }
}
```

`calculateOneBatch()` nên là phần công việc hữu hạn để chương trình có cơ hội kiểm tra lại cờ giữa các batch. Nếu một batch kéo dài nhiều phút và không thể ngắt, cancellation vẫn có thể bị trì hoãn trong toàn bộ thời gian đó.

Không cần kiểm tra interrupt ở từng phép toán nhỏ nếu điều đó làm mã phức tạp hoặc tốn chi phí không cần thiết. Hãy chọn điểm kiểm tra phù hợp với yêu cầu về độ trễ hủy và tính nhất quán của dữ liệu.

## Giới hạn khi tác vụ đang chờ I/O hoặc gọi thư viện bên ngoài

Không phải mọi API I/O đều phản hồi interruption theo cùng một cách. Một số API blocking có hỗ trợ interrupt; một số lời gọi native hoặc thư viện bên thứ ba có thể tiếp tục chặn thread cho đến khi thao tác hoàn tất hoặc timeout. Khi đó, `cancel(true)` không đảm bảo giải phóng thread ngay.

Với I/O và tài nguyên bên ngoài, nên kết hợp nhiều cơ chế:

- Đặt connect timeout, read timeout hoặc deadline cho request.
- Dùng API có hỗ trợ interruption/cancellation nếu thư viện cung cấp.
- Đóng socket, channel hoặc tài nguyên do task sở hữu khi cần hủy, theo đúng hợp đồng của API.
- Dùng cancellation token hoặc cờ dừng riêng nếu thư viện nghiệp vụ cần một cơ chế hợp tác ngoài interrupt.
- Thiết kế retry và cleanup sao cho không lặp lại side effect khi tác vụ đã thực hiện một phần công việc.

Interrupt không tự động đóng mọi tài nguyên, rollback transaction hoặc hủy một yêu cầu đã gửi tới hệ thống từ xa. Ứng dụng phải định nghĩa rõ tác động của việc dừng giữa chừng.

Interrupt cũng không tự động hủy các thread con mà task đã tự tạo. Nếu một task khởi chạy thêm công việc bất đồng bộ hoặc gửi yêu cầu tới dịch vụ từ xa, ứng dụng phải quản lý và truyền yêu cầu hủy tới các công việc đó theo API tương ứng.

## Hủy Future khác với interrupt thread đang chờ Future.get()

Có hai thread và hai trạng thái khác nhau trong tình huống này:

1. Thread A gửi task và nhận `Future`.
2. Thread A gọi `future.get()` để chờ kết quả.
3. Thread B đang thực thi task.

Nếu Thread A bị interrupt trong lúc `get()` đang chờ, `get()` ném `InterruptedException`. Điều này chỉ báo rằng thread đang chờ bị interrupt; nó không tự động gọi `future.cancel()` và không có nghĩa Thread B đã dừng.

Muốn hủy task, phải gọi `future.cancel(true)` hoặc một cơ chế hủy task tương ứng. Ví dụ xử lý interruption ở thread gọi:

```java
try {
    return future.get();
} catch (InterruptedException e) {
    future.cancel(true); // Chủ động yêu cầu hủy task.
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Thread chờ bị interrupt", e);
}
```

Ví dụ trên chọn chính sách hủy task khi thread chờ bị interrupt. Ứng dụng có thể chọn chính sách khác, nhưng phải thể hiện rõ trong mã. Khôi phục interrupt status giúp tầng gọi cao hơn vẫn nhận biết thread đã bị interrupt.

Ngoài `InterruptedException`, `Future.get()` có thể ném `ExecutionException` nếu task kết thúc do lỗi, hoặc `CancellationException` nếu Future đã bị hủy. Ba trường hợp này có ý nghĩa khác nhau và không nên gộp thành một lỗi chung mà không phân biệt.

## cancel(false) có thể để task tiếp tục chạy

`cancel(false)` không gửi interrupt tới thread đang thực thi task. Nếu task chưa bắt đầu, Future có thể được hủy trước khi executor chạy nó. Nếu task đã bắt đầu, Future chuyển sang trạng thái cancelled nhưng mã đang chạy có thể tiếp tục đến khi tự kết thúc.

Điều này có nghĩa:

- `future.isCancelled()` có thể là `true` trong khi task vẫn đang thực hiện side effect.
- `future.get()` sẽ ném `CancellationException`, không trả kết quả cuối của task.
- Executor vẫn phải chờ task thực sự kết thúc trước khi hoàn tất shutdown có trật tự.

Chỉ chọn `cancel(false)` khi không cần interrupt task đang chạy và chấp nhận rằng công việc có thể tiếp tục. Nếu mục tiêu là yêu cầu tác vụ đang chạy dừng sớm, `cancel(true)` thường phù hợp hơn, với điều kiện task có thiết kế phản hồi interruption.

## Shutdown executor không cưỡng bức kết thúc task

`ExecutorService` có hai thao tác shutdown chính:

| Phương thức | Hành vi |
| --- | --- |
| `shutdown()` | Ngừng nhận task mới, cho phép task đã submit tiếp tục hoàn tất |
| `shutdownNow()` | Cố gắng dừng task đang chạy bằng cách interrupt thread thực thi và trả về danh sách task chưa bắt đầu; không bảo đảm task đang chạy sẽ kết thúc |

`shutdownNow()` cũng dựa vào khả năng phản hồi interruption của task. Nếu task bỏ qua interrupt, executor có thể không kết thúc ngay. Nếu cần đợi executor chấm dứt, dùng `awaitTermination()` với thời hạn phù hợp và xử lý trường hợp hết thời gian chờ.

Trong Java 21, `ExecutorService` hỗ trợ `AutoCloseable`, nên có thể dùng try-with-resources. Khi đóng, executor thực hiện shutdown có trật tự và chờ các task đã submit kết thúc. Nếu task không phản hồi interruption hoặc không bao giờ kết thúc, việc đóng executor vẫn có thể chờ lâu. Try-with-resources quản lý vòng đời executor; nó không biến cancellation thành cơ chế kill.

## Áp dụng với virtual thread

Virtual thread vẫn tuân theo mô hình interruption. Nếu `Future` đại diện cho tác vụ chạy trên virtual thread, `cancel(true)` yêu cầu interrupt virtual thread thực thi tác vụ đó. Với thao tác blocking được JDK hỗ trợ, virtual thread thường có thể được đánh thức và unmount khỏi carrier; mã tác vụ vẫn phải xử lý exception, dừng công việc và cleanup.

Ví dụ dùng executor tạo virtual thread cho từng task:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> {
        try {
            callRemoteService();
            return "done";
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "cancelled";
        }
    });

    // Khi không còn cần kết quả:
    future.cancel(true);
}
```

`callRemoteService()` ở đây đại diện cho một API có thể ném `InterruptedException`; trong ứng dụng thật cần dùng client và timeout phù hợp. Việc chạy trên virtual thread không thay đổi bản chất hợp tác của interruption và không làm cho mọi thư viện I/O tự động có khả năng hủy.
Trong ví dụ này, `return "cancelled"` chỉ là đường thoát của mã tác vụ; sau khi `cancel(true)` thành công, bên gọi vẫn nhận `CancellationException` từ Future thay vì đọc được chuỗi đó.

## Quy trình thiết kế cancellation đáng tin cậy

1. **Giữ Future của task.** Dùng handle này để lấy kết quả, kiểm tra trạng thái và yêu cầu hủy.
2. **Chọn chính sách interrupt.** Dùng `cancel(true)` khi muốn yêu cầu task đang chạy phản hồi; chỉ dùng `cancel(false)` khi chấp nhận task có thể tiếp tục.
3. **Thiết kế task hợp tác.** Kiểm tra `isInterrupted()` trong vòng lặp CPU-bound và dùng API blocking có hỗ trợ interruption hoặc timeout.
4. **Không nuốt InterruptedException.** Truyền exception lên nếu có thể; nếu không, khôi phục interrupt status và kết thúc hoặc chuyển sang đường hủy rõ ràng.
5. **Giải phóng tài nguyên.** Đặt cleanup trong `finally` hoặc try-with-resources; xác định cách xử lý side effect đã thực hiện một phần.
6. **Phân biệt trạng thái Future với kết thúc thực tế.** `isCancelled()` và `isDone()` không thay thế việc chờ task/executor hoàn tất cleanup.
7. **Quản lý executor có thời hạn.** Chọn `shutdown()` hay `shutdownNow()` theo chính sách và dùng `awaitTermination()` nếu cần xác nhận executor đã kết thúc.
8. **Kiểm thử các tình huống hủy.** Kiểm tra task chưa chạy, đang blocking, đang tính toán, đang I/O và đang cleanup; xác nhận thời gian phản hồi cùng trạng thái tài nguyên.

`Future.cancel()` thay đổi trạng thái của Future và, với `cancel(true)`, gửi tín hiệu interrupt tới thread thực thi task đang chạy. Việc task có thực sự dừng hay không phụ thuộc vào khả năng hợp tác của mã và các API nó sử dụng. Thiết kế cancellation tốt cần có điểm kiểm tra, timeout, xử lý interruption và cleanup rõ ràng thay vì dựa vào việc thread sẽ tự kết thúc ngay lập tức.
