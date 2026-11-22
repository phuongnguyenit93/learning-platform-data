# Khôi phục interrupt flag khi không thể tiếp tục lan truyền trong Java

> **Chủ đề:** Java Core → Exception → Ngắt và hủy. Bài học giải thích cách giữ tín hiệu hủy hợp tác khi một phương thức Java bắt `InterruptedException` nhưng **không thể khai báo hoặc tiếp tục ném** ngoại lệ đó, chẳng hạn khi triển khai `Runnable.run()`. Trọng tâm là sự khác biệt giữa **ngoại lệ báo ngắt** và **cờ interrupt** gắn với luồng, cách khôi phục cờ chính xác, và cách thiết kế đường thoát để không tiếp tục công việc trái ý muốn.

## 1. Interrupt trong Java là gì?

`Thread.interrupt()` là cơ chế **báo hiệu hợp tác** tới một thread. Nó không cưỡng bức dừng luồng tại một dòng mã tùy ý, không tự rollback trạng thái và không mặc nhiên ném `InterruptedException` vào stack của thread khác. Tác vụ phải phản ứng với tín hiệu theo hợp đồng của API đang chạy.

Một thread có **interrupt status** (thường gọi là *interrupt flag*). Khi thread A gọi `worker.interrupt()`, tín hiệu được đặt cho `worker`; một số thao tác chặn ở worker sẽ phản ứng bằng cách ném `InterruptedException`. Với các thao tác chặn chuẩn như `Thread.sleep`, `Object.wait` hoặc `Thread.join`, nếu bị interrupt và ném `InterruptedException`, **trạng thái interrupt được xóa khi exception được ném**. Điều này khiến mã đã bắt exception cần chủ động quyết định có truyền tín hiệu lên hay không.

~~~text
Thread A                                 Thread B (worker)
--------                                 -----------------
worker.interrupt()
     |                                   đang Thread.sleep(...)
     |                                   -> InterruptedException
     |                                   -> interrupt status được xóa
     |                                   -> catch (InterruptedException e)
     |                                      ├─ truyền exception tiếp
     |                                      └─ không truyền được:
     |                                           interrupt() để đặt lại flag
     |                                           thoát/ủy quyền xử lý hủy
~~~

Từ khóa quan trọng là **hợp tác**: việc đặt cờ cho phép những lớp phía ngoài nhận ra yêu cầu dừng, nhưng chỉ có tác dụng nếu các lớp đó kiểm tra và tôn trọng tín hiệu.

## 2. Vì sao bắt InterruptedException có thể làm mất tín hiệu?

Ví dụ một đoạn mã trong worker:

~~~java
// Đoạn minh họa nằm bên trong một phương thức.
try {
    Thread.sleep(10_000);
} catch (InterruptedException ex) {
    System.out.println("Interrupted");
}
continueProcessing();
~~~

Với `Thread.sleep`, khi exception được ném do interrupt, interrupt status được xóa. Sau khối `catch` trên, `continueProcessing()` vẫn chạy và tầng ngoài kiểm tra `Thread.currentThread().isInterrupted()` có thể thấy `false`. Ứng dụng đã *nuốt tín hiệu* hủy.

Điều này có thể dẫn tới:

- Tác vụ vẫn lấy message mới hoặc tiếp tục lặp dù hệ thống yêu cầu dừng.
- Shutdown của `ExecutorService` kéo dài vì worker không hợp tác.
- Caller tưởng yêu cầu cancellation đã được tôn trọng, trong khi một phần side effect còn tiếp tục.
- Các đoạn mã phía ngoài không nhìn thấy interrupt status để dừng hợp tác hoặc khôi phục tài nguyên.

**Nguyên tắc:** nếu không thể truyền `InterruptedException` lên theo đúng hợp đồng phương thức, thường phải **khôi phục trạng thái interrupt bằng `Thread.currentThread().interrupt()`** rồi **kết thúc công việc hiện tại hoặc đi tới đường thoát phù hợp**.

Việc chỉ đặt lại flag nhưng tiếp tục xử lý vô hạn chưa giải quyết vấn đề hủy.

## 3. Hai cách chuẩn khi gặp InterruptedException

### Cách A — truyền exception lên nếu chữ ký cho phép

Nếu phương thức có thể khai báo `throws InterruptedException`, cách đơn giản nhất là để ngoại lệ truyền lên:

~~~java
// Ví dụ phương thức có thể khai báo checked exception.
static String receive(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

Nếu cần dọn dẹp trước khi truyền, bắt rồi `throw ex`:

~~~java
static String receiveWithCleanup(
        java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    try {
        return queue.take();
    } catch (InterruptedException ex) {
        logCancellation();
        throw ex;
    }
}
~~~

`logCancellation()` ở trên là hàm minh họa do ứng dụng cung cấp; đoạn này không phải chương trình Java độc lập. Khi truyền chính `InterruptedException` lên, tầng gọi nhận tín hiệu qua **đường exception**; thông thường **không cần đặt lại interrupt flag chỉ để rethrow cùng ngoại lệ**. Caller sẽ quyết định hủy/khôi phục nếu nó không thể truyền tiếp.

### Cách B — không truyền được thì khôi phục flag

Một `Runnable.run()` không khai báo `throws InterruptedException`. Khi code trong `run()` gọi thao tác chặn có thể ném checked exception, thường cần:

~~~java
@Override
public void run() {
    try {
        blockingOperation();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt(); // Đặt lại flag đã bị xóa.
        return; // Thoát công việc theo chính sách hủy.
    }
}
~~~

`blockingOperation()` ở đây là hàm minh họa được định nghĩa trong lớp thật, có `throws InterruptedException`.

Dòng `Thread.currentThread().interrupt()` không ngắt một thread xa lạ: nó báo lại tín hiệu cho **chính luồng đang chạy catch**, để mã bao ngoài/đơn vị quản lý tác vụ có thể quan sát. `return` ngăn worker tiếp tục xử lý như chưa có yêu cầu dừng.

**Không viết `throw new InterruptedException()` trong `Runnable.run()`**, vì chữ ký override không cho khai báo một checked exception mới. Nếu hợp đồng đòi một lỗi unchecked, có thể bọc nguyên nhân bằng `RuntimeException` thích hợp và khôi phục flag trước khi ném, nhưng cần tài liệu hóa hành vi này; không phải mọi ngắt hợp tác đều nên trở thành một lỗi ứng dụng.

## 4. Chương trình Java 17 chạy được: quan sát flag bị xóa rồi được phục hồi

Ví dụ sử dụng interrupt do chính thread đặt trước lời gọi `Thread.sleep` để tạo tình huống **xác định, không phụ thuộc thời gian scheduler**. Trong ứng dụng thực, tín hiệu thường được gửi từ thread khác qua `interrupt()` hoặc `Future.cancel(true)`.

Lưu toàn bộ mã trong **`InterruptFlagRestoreDemo.java`**:

~~~java
public class InterruptFlagRestoreDemo {
    static final class Worker implements Runnable {
        @Override
        public void run() {
            // Mô phỏng thread đã được yêu cầu hủy trước khi chờ.
            Thread.currentThread().interrupt();

            try {
                Thread.sleep(1_000);
                System.out.println("unexpected success");
            } catch (InterruptedException ex) {
                System.out.println("after InterruptedException: "
                        + Thread.currentThread().isInterrupted());

                // Không thể throws InterruptedException qua Runnable.run().
                Thread.currentThread().interrupt();

                System.out.println("after restore: "
                        + Thread.currentThread().isInterrupted());
                return;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(new Worker(), "worker");
        worker.start();
        worker.join();

        // Interrupt status là trạng thái theo từng thread.
        System.out.println("main interrupted: "
                + Thread.currentThread().isInterrupted());
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac InterruptFlagRestoreDemo.java
java InterruptFlagRestoreDemo
~~~

**Stdout chính xác:**

~~~text
after InterruptedException: false
after restore: true
main interrupted: false
~~~

Giải thích:

1. Worker đặt cờ của chính nó bằng `Thread.currentThread().interrupt()`.
2. `Thread.sleep(1_000)` nhận thấy tình trạng đã bị interrupt, ném `InterruptedException` và xóa interrupt status. Vì vậy dòng đầu là `false`; lệnh sau `sleep` không chạy.
3. Khối `catch` gọi `Thread.currentThread().interrupt()` để phục hồi trạng thái, nên dòng thứ hai là `true`.
4. Worker dừng bằng `return`. Main gọi `join()` rồi kiểm tra **cờ của main**, không phải cờ của worker, nên in `false`. Một luồng bị interrupt không tự biến mọi luồng khác thành interrupted.

Dấu hiệu quan trọng là **trạng thái sau khi thao tác chặn ném lỗi**; không nên diễn giải rằng mọi API ném exception bất kỳ đều tự xóa interrupt flag.

## 5. Mã ứng dụng thực tế: nhận việc từ BlockingQueue

Một vòng lặp tiêu thụ tác vụ có thể chờ trên `BlockingQueue.take()`; đây là phương thức có thể ném `InterruptedException`. Ví dụ sau là **đoạn minh họa trong một worker**, giả sử `queue` chứa công việc, `process` xử lý công việc và các API khác đã được khai báo:

~~~java
@Override
public void run() {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Work work = queue.take();
            process(work);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            break;
        }
    }
    // Thực hiện cleanup phù hợp trước khi run() kết thúc.
}
~~~

Ở đây:

- Vòng `while` kiểm tra tín hiệu giữa các lần xử lý; `queue.take()` phản ứng với interrupt khi chờ.
- Nếu `take()` bị ngắt, khối `catch` khôi phục cờ vì `run()` không thể tiếp tục ném checked exception.
- `break` thoát vòng lặp để tiến tới cleanup. Nếu chỉ reinterrupt rồi vòng lại `queue.take()`, tác vụ có thể bị ngắt ngay lần nữa và lặp không hiệu quả.
- Nếu `process(work)` có thể ném `InterruptedException`, cùng nhánh xử lý cần bảo đảm tác vụ đang làm có trạng thái kết thúc rõ ràng. Nếu `process` gây side effect, không thể giả định interrupt tự rollback.

**Lưu ý concurrency:** nếu dùng `ExecutorService`, callback có thể chạy trên một thread dùng chung lâu dài. Thực hành tốt là tôn trọng chính sách hủy của executor/framework và thoát đúng ranh giới task. Đừng tự ý quyết định cả thread pool phải chết chỉ vì một task nhận yêu cầu interrupt.

## 6. Cách kiểm tra interrupt flag: isInterrupted và interrupted

Java có hai phương thức dễ bị nhầm:

| API | Đối tượng được kiểm tra | Có xóa interrupt status? | Dùng khi nào? |
|---|---|---|---|
| `Thread.currentThread().isInterrupted()` | Thread hiện tại, gọi qua object | **Không** | Điều kiện dừng ở vòng lặp, quan sát trạng thái trước khi thoát |
| `someThread.isInterrupted()` | Thread object được chỉ định | **Không** | Giám sát một thread khác khi thích hợp |
| `Thread.interrupted()` | **Luồng hiện tại** (static) | **Có**: đọc rồi xóa flag | Chỉ khi chủ đích tiêu thụ tín hiệu ngắt |
| `Thread.currentThread().interrupt()` | Thread hiện tại | **Đặt** cờ (hoặc kích hoạt ngữ nghĩa interrupt tương ứng) | Khôi phục sau khi đã bắt `InterruptedException` và không truyền tiếp |

Ví dụ dễ sai:

~~~java
// Không phù hợp nếu muốn giữ tín hiệu cho tầng ngoài.
while (!Thread.interrupted()) {
    doNonBlockingWork();
}
~~~

Khi gặp cờ interrupt, `Thread.interrupted()` trả về `true` **đồng thời xóa cờ**. Vòng lặp có thể dừng, nhưng tầng ngoài không còn thấy yêu cầu hủy qua interrupt status. Nếu hợp đồng yêu cầu bảo toàn flag, dùng `Thread.currentThread().isInterrupted()` hoặc đặt lại cờ khi đã tiêu thụ tín hiệu.

Ví dụ chủ ý xóa flag có thể phù hợp khi một tầng đã **nhận và xử lý hoàn toàn** tín hiệu rồi quyết định tiếp tục theo hợp đồng riêng. Điều này cần được thực hiện có chủ đích, không vô tình bởi tên phương thức tương tự nhau.

## 7. Nếu chỉ ghi log mà không reinterrupt thì sao?

Mẫu thường gây lỗi:

~~~java
// Sai khi ứng dụng cần bảo toàn yêu cầu hủy.
try {
    Thread.sleep(5_000);
} catch (InterruptedException ex) {
    logger.warn("interrupted", ex);
}
doMoreWork();
~~~

Tại đây, logger được giả định là đối tượng ghi log đã được định nghĩa ở bên ngoài đoạn mã. `Thread.sleep` đã xóa cờ khi ném exception; code chỉ log rồi chạy tiếp, nên caller không nhận được tín hiệu hủy. Đó là hành vi **swallow interruption**.

Một sửa đổi phù hợp trong tác vụ không thể `throws InterruptedException`:

~~~java
try {
    Thread.sleep(5_000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    logger.warn("operation cancelled by interrupt", ex);
    return;
}
doMoreWork();
~~~

Đây vẫn là **trích đoạn trong phương thức có kiểu trả về `void`**. Dòng `return` ngăn công việc sau thao tác chặn tiếp tục. Nếu việc ghi log tự ném ngoại lệ, cờ đã được khôi phục trước lời gọi logging; tuy nhiên code ứng dụng vẫn cần cân nhắc trách nhiệm cleanup và kênh báo lỗi.

**Quy tắc không nên áp dụng máy móc:** không phải *mọi* khối `catch` đều phải gọi `interrupt()`. Hãy xác định chính xác exception được bắt và ngữ nghĩa của API sinh lỗi. `IOException` do socket timeout, ví dụ, không tự đồng nghĩa với yêu cầu interrupt của thread.

## 8. Khôi phục flag rồi ném unchecked exception: khi nào phù hợp?

Đôi khi interface không cho phép checked exception nhưng caller/framework muốn nhận một thất bại thay vì chỉ thấy tác vụ trả về bình thường. Có thể chuyển đổi lỗi có chủ đích:

~~~java
@Override
public void run() {
    try {
        blockingOperation();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("background task interrupted", ex);
    }
}
~~~

Hai hành động ở đây phục vụ **hai kênh khác nhau**:

- `Thread.currentThread().interrupt()` bảo toàn tín hiệu hủy ở trạng thái thread.
- `throw new IllegalStateException(..., ex)` truyền thông tin thất bại theo kênh exception mà framework có thể ghi nhận, ví dụ executor có `Future`.

Việc bọc lỗi không có nghĩa trạng thái chia sẻ đã rollback. Nếu hệ thống kỳ vọng cancellation là kết quả bình thường, trả về hoặc đưa trạng thái `CANCELLED` có thể rõ hơn biến interrupt thành một lỗi nghiệp vụ. Hãy thống nhất với hợp đồng API: một framework có thể sử dụng interrupt để hủy thay vì muốn nhận `IllegalStateException`.

Ngoài ra, một task chỉ có thể báo cho caller về việc bị ngắt **nếu kết quả hoặc kênh lỗi thật sự được người cần xử lý quan sát**. Ví dụ `ExecutorService.submit` lưu lỗi trong `Future`; bỏ qua Future có thể đồng nghĩa bỏ luôn thông tin thất bại ở cấp ứng dụng.

## 9. Cẩn thận khi gọi thao tác chặn khác sau khi reinterrupt

Nếu khôi phục interrupt flag rồi tiếp tục chạy:

~~~java
// Trích đoạn cảnh báo trong một phương thức.
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    Thread.sleep(1_000); // Không hợp lệ nếu không xử lý throws; có thể ném ngay.
}
~~~

Một số lệnh chặn sẽ nhận thấy flag đang bật và phản ứng bằng một `InterruptedException` mới; nếu mỗi lần bắt lại khôi phục rồi lặp, chương trình có thể tạo **vòng lặp chờ/interrupt** không có tiến triển. Đừng dùng interrupt như một thông báo để *bỏ qua một bước rồi tiếp tục làm mọi việc bình thường*.

Sau reinterrupt, nên:

1. Ra khỏi vòng xử lý hoặc trả về tầng quản lý.
2. Hoàn tất cleanup ngắn, có khả năng thành công trong trạng thái đã bị interrupt.
3. Nếu cleanup cần chờ, xác định rõ chiến lược xử lý riêng và tránh mất tín hiệu hủy.
4. Ghi nhận phần trạng thái đã thay đổi trước khi lỗi, không nhầm “thread sắp dừng” với “transaction đã rollback”.

Một số thao tác cleanup không chặn vẫn có thể thực hiện an toàn sau khi cờ được khôi phục, nhưng không nên phát sinh hoạt động dài hoặc gửi thêm tác vụ mà caller đã yêu cầu hủy.

## 10. InterruptedException trong các API thường gặp

| Thao tác | Khi bị interrupt trong lúc chờ | Gợi ý xử lý |
|---|---|---|
| `Thread.sleep(...)` | Ném `InterruptedException`, xóa interrupt status | Propagate hoặc restore+exit |
| `Object.wait(...)` | Ném `InterruptedException`, xóa interrupt status; thread lấy lại monitor thích hợp trước khi trở về | Bảo vệ invariant trạng thái được chờ, propagate hoặc restore+exit |
| `Thread.join(...)` | Thread **đang join** nhận `InterruptedException` nếu bị ngắt; đây không phải lỗi của thread được chờ | Caller quyết định có chờ tiếp hay hủy; giữ tín hiệu nếu không truyền tiếp |
| `BlockingQueue.take()` / `put()` | Có thể ném `InterruptedException` theo hợp đồng | Worker loop nên hợp tác kết thúc |
| `CountDownLatch.await()` | Ném `InterruptedException` theo hợp đồng | Propagate hoặc restore tại boundary |
| `Future.get()` | Luồng đang chờ có thể nhận `InterruptedException` | Phân biệt với `ExecutionException` do task lỗi |
| `Lock.lockInterruptibly()` | Có thể ném `InterruptedException` khi chờ lock | Bảo đảm không gọi `unlock()` nếu chưa lấy được lock |
| `ExecutorService.awaitTermination(...)` | Có thể ném `InterruptedException` trong lúc chờ shutdown | Yêu cầu hủy theo chính sách, restore flag |

Với các API như `CompletableFuture.join()`, lời gọi **không khai báo `InterruptedException`**, nên cách chờ/ngắt khác với `Future.get()`. Không áp dụng quy tắc “cứ catch rồi reinterrupt” ở nơi không có checked exception đó. Hãy đọc hợp đồng của chính API đang dùng.

Một số API I/O liên quan interrupt bằng những lớp exception khác, như `ClosedByInterruptException` của các channel có thể ngắt, hoặc `InterruptedIOException`. Trạng thái cờ và side effect phụ thuộc từng API. Đừng suy diễn rằng mọi exception có chữ “interrupted” đều đã xóa flag giống `Thread.sleep`; đọc Javadoc khi thiết kế chuyển đổi.

## 11. Shutdown ExecutorService: mẫu phục hồi interrupt đúng ngữ cảnh

Ví dụ chính sách shutdown một executor: ngừng nhận công việc mới, chờ công việc đang chạy, yêu cầu hủy nếu quá hạn; nếu thread điều phối bị interrupt thì yêu cầu hủy và **khôi phục interrupt flag**.

~~~java
// Trích đoạn dùng ExecutorService pool đã được khởi tạo.
// TimeUnit được dùng với tên đầy đủ.
pool.shutdown();
try {
    if (!pool.awaitTermination(30, java.util.concurrent.TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
} catch (InterruptedException ex) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là một đoạn mã minh họa từ cách xử lý được tài liệu hóa cho executor. Vì đoạn code ở ranh giới shutdown không chọn `throws InterruptedException`, nó bảo toàn tín hiệu với `Thread.currentThread().interrupt()`.

**Không đánh đồng các thao tác:**

- `shutdown()` ngừng chấp nhận công việc mới, nhưng không yêu cầu mọi task đang chạy dừng tức thì.
- `shutdownNow()` cố gắng dừng các task đang chạy, thường thông qua interrupt và trả về danh sách tác vụ chờ chưa được chạy; không bảo đảm mọi task tuân theo yêu cầu.
- `awaitTermination()` chờ và có thể bị interrupt ở **thread điều phối**, khác với exception của một task đang chạy.
- `Thread.currentThread().interrupt()` trong `catch` trả lại tín hiệu cho người gọi đoạn shutdown này. Nó không tự hủy những task chưa hoàn tất nếu không có chính sách như `shutdownNow()`.

Nếu code cần cleanup thêm, nên định nghĩa rõ giới hạn chờ, các trường hợp không thể hoàn tất và khả năng đặt interrupt flag lại sau khi một đoạn cleanup khác đã tiêu thụ nó.

## 12. Giữ tính toàn vẹn trạng thái khi bị ngắt

Khôi phục interrupt status không bảo đảm **bất biến dữ liệu**. Giả sử worker đã trừ tồn kho rồi mới đi vào một thao tác chặn. Nếu thao tác chặn ném `InterruptedException`, việc reinterrupt chỉ giữ yêu cầu hủy; hàng tồn đã giảm vẫn có thể tồn tại.

~~~java
// Minh họa tình huống cần thiết kế commit/rollback.
synchronized (lock) {
    inventory.decrement(item);
    queue.put(event); // Có thể bị interrupt hoặc chờ.
}
~~~

Đoạn trên là **mã minh họa** có `lock`, `inventory`, `queue`, `item`, `event` được định nghĩa trong ứng dụng. Nếu `put` thất bại vì interrupt, monitor được nhả khi rời khối `synchronized` (nếu exception thoát), nhưng `decrement` không tự bị hoàn tác.

Muốn giữ dữ liệu nhất quán cần thêm:

- Validate và chuẩn bị trạng thái mới trước tác dụng phụ.
- Quy định rõ điểm commit; khi có nhiều tài nguyên, dùng transaction/compensation/outbox nếu phù hợp.
- Dùng cùng cơ chế đồng bộ cho các đường đọc/ghi liên quan, tránh TOCTOU.
- Quyết định task đang bị hủy có thể bỏ dở phần việc nào và cần cleanup gì.
- Giữ nguyên `cause`, thông tin tiến độ và trạng thái đã commit trong kết quả nếu caller cần phục hồi.

Việc cố “rollback” trong `catch` cũng có thể thất bại hoặc không thể đảo ngược email/HTTP request đã gửi. Tách riêng **bảo toàn tín hiệu interrupt** và **bảo toàn dữ liệu nghiệp vụ**.

## 13. Những điều không nên làm

1. **Nuốt interrupt:** `catch (InterruptedException ex) { }` rồi làm tiếp.
2. **Chỉ log rồi tiếp tục:** sau `sleep`, cờ đã bị xóa; tầng khác không thấy cancellation.
3. **Luôn reinterrupt rồi vòng lặp lại thao tác chặn:** có thể tạo vòng lỗi lặp mãi mà không tiến triển.
4. **Dùng `Thread.interrupted()` để chỉ “kiểm tra” trong khi cần bảo toàn flag:** phương thức này đồng thời xóa flag.
5. **Ném unchecked wrapper mà quên cause:** làm mất nguồn gốc lỗi và thông tin ngắt.
6. **Coi `interrupt()` như `Thread.stop()`:** interrupt là tín hiệu hợp tác, không phải dừng cưỡng bức.
7. **Ném hoặc bắt `InterruptedException` cho mọi lỗi I/O:** interrupt không đồng nghĩa mọi timeout/mất kết nối.
8. **Bắt `Exception` quá rộng rồi xử lý như lỗi thường:** có thể giấu mất `InterruptedException` và phá chính sách shutdown.
9. **Reinterrupt ở tầng đã truyền `InterruptedException` nguyên vẹn mà không có lý do:** làm trùng kênh thông báo và có thể gây tác động ngoài hợp đồng.
10. **Cho rằng shutdownNow/cancel(true) chắc chắn dừng task:** tác vụ phải hỗ trợ hủy; side effect đã thực hiện vẫn có thể tồn tại.

## 14. Kiểm thử đúng hành vi của interrupt flag

Kiểm thử nên tạo tình huống interrupt một cách có kiểm soát thay vì đoán thời điểm scheduler:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Đặt flag trước `Thread.sleep` | `InterruptedException` xảy ra và flag được xóa trước khi catch xử lý |
| Catch rồi reinterrupt | `Thread.currentThread().isInterrupted()` trả `true` |
| Caller khác thread | Interrupt status của caller không tự bị thay đổi |
| Propagate `InterruptedException` | Lỗi đến đúng tầng nhận; không bị wrap/nuốt ngoài ý muốn |
| `Runnable.run()` nhận interrupt khi chặn | Worker thoát, không tiếp tục xử lý các bước không nên chạy |
| Vòng lặp dùng `Thread.interrupted()` | Chứng minh cờ bị xóa; quyết định có đặt lại hay đổi sang `isInterrupted()` |
| `Future.cancel(true)` | Task hợp tác dừng; không giả định tức thì, kiểm tra thời gian/cleanup |
| Shutdown manager bị interrupt trong `awaitTermination` | Chính sách shutdown và restored interrupt status đúng |
| Task có side effect rồi bị interrupt | Bất biến và trạng thái commit được kiểm tra độc lập |

Đối với kiểm thử trong một thread khác, có thể dùng `CountDownLatch` để đánh dấu tác vụ đã vào điểm chờ, rồi gọi `interrupt()` và `join()`; cần timeout để tránh test treo. Không dùng một lần `Thread.sleep(100)` như bằng chứng chắc chắn rằng worker đã đến đúng vị trí chờ.

Ngoài kiểm thử, nên đọc kỹ hợp đồng của API có thể ném `InterruptedException`: chính API xác định điều kiện ném, thao tác với interrupt status và trạng thái tài nguyên trước/sau ngắt.

## 15. Quy trình xử lý khi viết code thật

Khi nhìn thấy một `catch (InterruptedException ex)`, hãy trả lời các câu hỏi theo thứ tự:

1. **Luồng nào bị interrupt?** Đó là current thread đang thực thi thao tác chặn; không nhầm với một worker mà ta đang chờ.
2. **API đang dùng làm gì với flag?** Với `sleep`/`wait`/`join` và nhiều phương thức blocking chuẩn, flag được xóa khi exception được ném; API khác có thể có quy tắc riêng.
3. **Phương thức có thể khai báo `throws InterruptedException` không?** Nếu được và hợp đồng cho phép, truyền tiếp thường là cách rõ ràng.
4. **Nếu không truyền được, có khôi phục flag không?** Dùng `Thread.currentThread().interrupt()` tại ranh giới bắt lỗi.
5. **Sau đó có thoát đúng cách không?** `return`/`break`/chuyển trạng thái cancel thay vì tiếp tục công việc bình thường.
6. **Có cleanup hoặc thông báo kết quả không?** Giữ nguyên nhân lỗi và trạng thái công việc cần thiết, tránh chặn vô hạn sau reinterrupt.
7. **Dữ liệu có thể đã đổi trước ngắt chưa?** Xác nhận invariant, transaction và khả năng idempotency/compensation.
8. **Đã test flag và hành vi hủy chưa?** Đo cả đường exception lẫn điều kiện dừng, tránh chỉ assert có exception.

## 16. Ghi nhớ

**`InterruptedException` và interrupt flag là hai cách biểu diễn tín hiệu ngắt hợp tác.** Nhiều thao tác chặn chuẩn xóa flag khi ném `InterruptedException`. Nếu có thể truyền checked exception lên theo hợp đồng, hãy truyền; nếu **không thể truyền tiếp**, thường phải gọi **`Thread.currentThread().interrupt()`** để khôi phục tín hiệu, rồi thoát hoặc bàn giao cho cơ chế hủy phù hợp.

Khôi phục cờ **không tự dừng luồng**, không khiến exception lan sang thread khác và không tự rollback dữ liệu. Nó có ý nghĩa khi những tầng liên quan thực sự tôn trọng giao thức interrupt và tác vụ ngừng thực hiện công việc không còn được yêu cầu.

### Tham khảo

- [Java SE 17 — Thread.interrupt, interrupted, isInterrupted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java SE 17 — InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html)
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html)
