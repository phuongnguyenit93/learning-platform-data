# cancel, isCancelled và isDone

## 1. “Không cần kết quả nữa” khác “mã đã ngừng chạy”

Người dùng hủy một báo cáo đang tạo. Chương trình gọi `future.cancel(true)`, thấy `isDone() == true` và lập tức xóa thư mục mà tác vụ đang ghi. Nếu tác vụ chưa đáp ứng tín hiệu ngắt, nó vẫn có thể tiếp tục dùng thư mục đó.

Vấn đề nằm ở hai lớp trạng thái:

- **Trạng thái Future:** còn chờ kết quả, thành công, thất bại hoặc bị hủy.
- **Việc thực thi thực tế:** mã tác vụ đã thoát chưa, đã dọn tài nguyên chưa, tác dụng phụ nào đã xảy ra.

Ba phương thức trong bài giúp yêu cầu hủy và quan sát trạng thái Future. Chúng không tự giải quyết toàn bộ vòng đời của mã đang chạy.

Các ví dụ dùng Java 17+. Thí nghiệm về tác vụ đang chạy sử dụng bộ thực thi chuẩn dựa trên `FutureTask`; phần cuối lưu ý những khác biệt của lớp triển khai khác.

## 2. Hai câu hỏi trạng thái

| Tình huống của Future | isDone() | isCancelled() | Khi gọi get() |
| --- | --- | --- | --- |
| Chưa có kết quả cuối cùng | `false` | `false` | Có thể phải chờ |
| Hoàn thành thành công | `true` | `false` | Trả kết quả |
| Hoàn thành bằng lỗi | `true` | `false` | Ném `ExecutionException` |
| Đã bị hủy | `true` | `true` | Ném `CancellationException` |

`isDone()` là câu hỏi “Future đã có trạng thái kết thúc chưa?”, không phải “kết quả có đúng không?”. Hủy cũng là một cách kết thúc Future.

`isCancelled()` cho biết Future đã bị hủy. Nó không chứng minh phần mã đang thực thi đã thoát khỏi mọi câu lệnh hoặc hoàn thành khối `finally`. [Tài liệu Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

Một Future đã có kết quả cuối cùng không được đặt lại để chạy lại bằng các thao tác thông thường trong bài. Muốn thực hiện lại công việc, cần tạo/gửi tác vụ mới theo chính sách riêng.

## 3. Hợp đồng của cancel

Chữ ký:

```java
boolean cancel(boolean mayInterruptIfRunning);
```

Tên tham số thể hiện đúng câu hỏi: **có được yêu cầu ngắt luồng đang chạy hay không?**

| Tình huống | cancel(false) | cancel(true) |
| --- | --- | --- |
| Tác vụ chưa bắt đầu, hủy được chấp nhận | Công việc không được chạy | Công việc không được chạy |
| Tác vụ đã bắt đầu và lớp triển khai cho phép hủy | Không yêu cầu ngắt; mã đang chạy có thể tiếp tục | Yêu cầu ngắt nếu lớp triển khai biết luồng thực hiện |
| Future đã hoàn thành hoặc đã bị hủy | Không thay đổi kết quả cuối cùng | Không thay đổi kết quả cuối cùng |

`false` không có nghĩa “chỉ hủy khi chưa chạy”. Với `FutureTask`, `cancel(false)` có thể chuyển Future đang chạy sang trạng thái hủy mà không ngắt mã tác vụ.

Giá trị trả về của `cancel` báo kết quả của lần cố hủy đó. Để quan sát Future hiện có bị hủy hay không, dùng `isCancelled()`. Khi nhiều luồng cùng hủy, một lời gọi trả `false` không có nghĩa Future chắc chắn chưa bị hủy bởi lời gọi khác. Cả `true` cũng không phải giấy xác nhận mã đã dừng thực tế. [Hợp đồng Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean))

Không dùng chuỗi `cancel(false)` rồi `cancel(true)` như cách tăng mức dừng: nếu lần đầu đã hủy Future, lần sau không thay đổi trạng thái và không bảo đảm gửi thêm tín hiệu ngắt cho mã còn chạy. Hãy chọn chính sách hủy từ đầu hoặc thiết kế cơ chế dừng tác vụ riêng khi cần.

## 4. Thí nghiệm các trạng thái cuối cùng

`FutureTask` vừa là `Runnable` vừa là `Future`. Trong ví dụ này, gọi trực tiếp `run()` để tạo các kết quả xác định; nó chạy trên luồng gọi, không tự tạo luồng mới.

Tệp **FutureStatusDemo.java**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureStatusDemo {
    private static void printStatus(String label, Future<?> future) {
        System.out.println(label + ": done=" + future.isDone()
                + ", cancelled=" + future.isCancelled());
    }

    public static void main(String[] args) throws Exception {
        FutureTask<Integer> pending = new FutureTask<>(() -> 1);
        FutureTask<Integer> success = new FutureTask<>(() -> 42);
        FutureTask<Integer> failed = new FutureTask<>(() -> {
            throw new IllegalArgumentException("bad input");
        });

        AtomicBoolean cancelledBodyRan = new AtomicBoolean();
        FutureTask<Integer> cancelled = new FutureTask<>(() -> {
            cancelledBodyRan.set(true);
            return 99;
        });

        success.run();
        failed.run();
        cancelled.cancel(false);
        cancelled.run();

        printStatus("pending", pending);
        printStatus("success", success);
        printStatus("failed", failed);
        printStatus("cancelled", cancelled);

        System.out.println("success.get=" + success.get());
        try {
            failed.get();
        } catch (ExecutionException ex) {
            System.out.println("failed.get=ExecutionException");
        }

        try {
            cancelled.get();
        } catch (CancellationException ex) {
            System.out.println("cancelled.get=CancellationException");
        }

        System.out.println("cancelledBodyRan=" + cancelledBodyRan.get());
        System.out.println("cancelAfterSuccess=" + success.cancel(true));

        pending.cancel(false);
    }
}
```

Chạy:

```shell
javac --release 17 FutureStatusDemo.java
java FutureStatusDemo
```

Stdout:

```text
pending: done=false, cancelled=false
success: done=true, cancelled=false
failed: done=true, cancelled=false
cancelled: done=true, cancelled=true
success.get=42
failed.get=ExecutionException
cancelled.get=CancellationException
cancelledBodyRan=false
cancelAfterSuccess=false
```

Tác vụ bị hủy trước khi chạy không thực hiện phần thân, kể cả khi sau đó gọi `run()` của FutureTask. Kết quả thành công đã có cũng không bị lệnh hủy đến muộn đổi thành hủy. [Tài liệu FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html)

Ví dụ đồng thời cho thấy chỉ nhìn `isDone()` không phân biệt được ba kết quả cuối cùng. Cần dùng trạng thái hủy và thao tác lấy kết quả/lỗi phù hợp.

## 5. cancel(false) khi tác vụ đang chạy

Thí nghiệm sau bảo đảm tác vụ đã bắt đầu rồi giữ nó ở một chốt. Sau khi hủy Future mà không ngắt, mã vẫn chưa thoát. Mở chốt cho phép nó thực hiện tác dụng phụ, dù Future đã bị hủy.

Tệp **CancelWithoutInterruptDemo.java**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelWithoutInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch bodyExited = new CountDownLatch(1);
        AtomicBoolean sideEffect = new AtomicBoolean();

        try {
            Future<Integer> future = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    sideEffect.set(true);
                    return 7;
                } finally {
                    bodyExited.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            System.out.println("cancelReturned=" + future.cancel(false));
            System.out.println("cancelled=" + future.isCancelled());
            System.out.println("done=" + future.isDone());
            System.out.println("bodyExitedBeforeRelease="
                    + (bodyExited.getCount() == 0));

            release.countDown();
            if (!bodyExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not exit");
            }

            System.out.println("sideEffectAfterCancellation=" + sideEffect.get());

            try {
                future.get();
            } catch (CancellationException ex) {
                System.out.println("get=CancellationException");
            }
        } finally {
            release.countDown();
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
javac --release 17 CancelWithoutInterruptDemo.java
java CancelWithoutInterruptDemo
```

Stdout:

```text
cancelReturned=true
cancelled=true
done=true
bodyExitedBeforeRelease=false
sideEffectAfterCancellation=true
get=CancellationException
```

Đây là bằng chứng trực tiếp rằng Future bị hủy và `isDone() == true` trong lúc phần thân vẫn chưa thoát. Tác vụ còn có thể thực hiện câu lệnh sau đó.

Giá trị `7` mà phần thân trả về không trở thành kết quả lấy được từ Future đã hủy. Bên đọc vẫn nhận `CancellationException`. Hủy việc cung cấp kết quả không hoàn tác tác dụng phụ đã hoặc sẽ xảy ra trong mã còn chạy.

## 6. cancel(true): gửi tín hiệu rồi quan sát sự hợp tác

Với tác vụ chuẩn của bộ thực thi trong ví dụ, `cancel(true)` yêu cầu ngắt luồng thực hiện. Tác vụ đang chờ bằng API đáp ứng ngắt sẽ nhận `InterruptedException` và có thể rời phần xử lý.

Tệp **CooperativeCancelDemo.java**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocked = new CountDownLatch(1);
        CountDownLatch bodyExited = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    blocked.await();
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    bodyExited.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            System.out.println("cancelReturned=" + future.cancel(true));
            System.out.println("cancelled=" + future.isCancelled());
            System.out.println("done=" + future.isDone());

            if (!bodyExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not exit");
            }
            System.out.println("taskObservedInterrupt=" + sawInterrupt.get());
            System.out.println("bodyExited=true");

            try {
                future.get();
            } catch (CancellationException ex) {
                System.out.println("get=CancellationException");
            }
        } finally {
            blocked.countDown();
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
javac --release 17 CooperativeCancelDemo.java
java CooperativeCancelDemo
```

Stdout:

```text
cancelReturned=true
cancelled=true
done=true
taskObservedInterrupt=true
bodyExited=true
get=CancellationException
```

Lưu ý mốc quan sát: chương trình chờ `bodyExited` trước khi báo tác vụ đã đi qua điểm dọn dẹp được xác định. Nó không dùng `isDone()` thay cho bằng chứng đó. Ở ví dụ này, `countDown()` là thao tác cuối trong khối `finally`; xác nhận cả bộ thực thi kết thúc vẫn thuộc `awaitTermination`.

Với vòng lặp tính toán dài, tác vụ cần kiểm tra cờ ngắt tại ranh giới các đơn vị công việc. Với thao tác I/O không đáp ứng ngắt theo cách mong muốn, cần timeout hoặc cơ chế đóng tài nguyên cụ thể. Bắt `InterruptedException` rồi tiếp tục lặp như chưa có gì xảy ra có thể khiến yêu cầu hủy không đạt mục đích. [Tài liệu Thread.interrupt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupt())

## 7. Không suy luận từ hai lần đọc thành một ảnh chụp nguyên tử

Đoạn suy luận “`isDone()` vừa trả false, vậy chắc chắn còn hủy được” có khoảng trống cạnh tranh. Tác vụ có thể hoàn thành giữa lần đọc trạng thái và lời gọi `cancel`.

Tương tự, khi nhiều luồng cùng gọi `cancel`, một luồng có thể thấy `false` vì luồng khác đã hủy trước. Hãy diễn đạt riêng:

- Kết quả của lần yêu cầu hủy.
- Trạng thái Future quan sát được sau đó.
- Bằng chứng phần mã thực thi đã thoát, nếu nghiệp vụ cần biết.

Không quay vòng liên tục gọi `isDone()` để chờ kết quả. Nếu cần kết quả, dùng `get` với chính sách thời hạn/ngắt phù hợp; nếu cần cập nhật giao diện, dùng cơ chế thông báo hoặc kiểm tra theo chu kỳ hợp lý.

Cũng không dùng Future bị hủy như hàng rào duy nhất để đọc dữ liệu có thể thay đổi của tác vụ. Các thí nghiệm dùng `AtomicBoolean` và chốt đồng bộ để quan sát tác dụng phụ/điểm thoát một cách rõ ràng.

## 8. Timeout, hủy một tác vụ và đóng bộ thực thi là ba việc

| Thao tác | Phạm vi |
| --- | --- |
| `future.get(timeout, unit)` | Giới hạn thời gian bên gọi chờ |
| `future.cancel(...)` | Cố hủy một Future/tác vụ |
| `executor.shutdown()` | Ngừng tiếp nhận trên cả bộ thực thi |
| `executor.awaitTermination(...)` | Chờ bộ thực thi kết thúc |

Hết thời gian chờ không tự hủy tác vụ. Nếu chính sách yêu cầu hủy khi hết hạn, phải yêu cầu hủy tường minh và xử lý tình huống tác vụ đã hoàn thành ngay trước đó.

Hủy một Future cũng không đóng bộ thực thi dùng chung. Các công việc khác vẫn có thể tiếp tục. Không gọi `shutdownNow()` lên một bộ thực thi dùng chung chỉ để hủy một báo cáo mà không có quyền quản lý vòng đời của nó.

## 9. Hủy không nhất thiết lấy phần tử khỏi hàng đợi ngay

Một FutureTask đã hủy có thể vẫn còn dưới dạng phần tử bao trong hàng đợi của bộ thực thi cho tới khi được lấy ra hoặc có cơ chế dọn. Do đó, không suy luận `isCancelled() == true` thành “vị trí hàng đợi và mọi tham chiếu đã được giải phóng ngay”.

`ThreadPoolExecutor` có cơ chế như `purge()` để hỗ trợ dọn tác vụ đã hủy trong hàng đợi; đây là vấn đề quản lý tài nguyên của lớp triển khai, khác với trạng thái kết quả của Future. Không thao tác hàng đợi nội bộ tùy tiện từ mã nghiệp vụ. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#purge())

Nếu hủy xảy ra thường xuyên với lượng công việc lớn, cần đo hàng đợi và bộ nhớ, đồng thời chọn chính sách dọn phù hợp với loại bộ thực thi.

## 10. Đọc hợp đồng của đúng lớp triển khai

Các ví dụ chạy tác vụ dùng mô hình `FutureTask` của bộ thực thi chuẩn. Không áp dụng mọi chi tiết ngắt cho tất cả đối tượng có kiểu `Future`.

Ví dụ, `CompletableFuture.cancel(true)` không dùng tham số `mayInterruptIfRunning` để ngắt phép tính đang thực hiện. Việc hủy ở đây được biểu diễn như một kiểu hoàn thành ngoại lệ; nó không kiểm soát trực tiếp mọi công việc tạo ra kết quả. [Tài liệu CompletableFuture.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html#cancel(boolean))

Vì vậy, trước khi xây dựng yêu cầu “nhấn Hủy phải dừng trong hai giây”, cần biết Future thuộc loại nào, công việc có đáp ứng tín hiệu không, tài nguyên chặn có timeout không và mốc nào được dùng để xác nhận đã dừng.

## 11. Tự kiểm tra một yêu cầu hủy báo cáo

Khi người dùng nhấn Hủy:

1. Yêu cầu `cancel` với chính sách ngắt đã định.
2. Quan sát `isCancelled()` và xử lý kết quả/lỗi nếu tác vụ đã kết thúc trước yêu cầu hủy.
3. Nếu cần biết công việc thực sự dừng, theo dõi một mốc hoàn tất/dọn dẹp riêng.
4. Xác định tác dụng phụ đã xảy ra và tài nguyên nào có thể được thu hồi.
5. Phản hồi đúng trạng thái: đã yêu cầu hủy, Future đã hủy hay công việc đã dừng thực tế.

Cách phân biệt này tránh lời hứa “đã dừng” trong lúc mã còn chạy. `cancel` là thao tác yêu cầu thay đổi, `isCancelled` và `isDone` là quan sát trạng thái Future; sự kết thúc thực tế cần được kiểm chứng theo hợp đồng của công việc.
