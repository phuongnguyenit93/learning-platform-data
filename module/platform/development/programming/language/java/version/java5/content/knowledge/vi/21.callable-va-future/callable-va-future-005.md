# InterruptedException và xử lý tín hiệu ngắt

## 1. Tín hiệu ngắt là lời yêu cầu hợp tác

Một tác vụ chạy lâu cần có cách phản hồi khi ứng dụng không còn muốn chờ hoặc đang dừng. Trong Java, **ngắt luồng (interruption)** là một cơ chế để truyền yêu cầu đó.

Gọi:

```java
worker.interrupt();
```

không có nghĩa ép luồng `worker` kết thúc ngay. Nó tác động tới trạng thái ngắt của luồng đích và có thể đánh thức một số thao tác chặn hỗ trợ ngắt. Mã đang chạy phải phản hồi bằng cách thoát, truyền tín hiệu lên tầng chịu trách nhiệm hoặc xử lý theo một chính sách rõ ràng.

Trong ngữ cảnh `Callable` và `Future`, cần tách hai luồng:

- **Luồng thực hiện công việc**: chạy thân `Callable.call()`.
- **Luồng chờ kết quả**: gọi `Future.get()`.

Luồng chờ bị ngắt không tự đồng nghĩa công việc đang tính toán cũng đã bị hủy. Đây là điểm đầu tiên phải xác định trước khi quyết định xử lý ngoại lệ.

## 2. InterruptedException xuất hiện khi nào?

`InterruptedException` là một ngoại lệ được kiểm tra lúc biên dịch, thuộc `java.lang`. Nó biểu diễn việc một thao tác có hỗ trợ ngắt phải phản hồi tín hiệu ngắt.

Những thao tác thường gặp:

| Thao tác | Luồng nào đang chờ? |
|---|---|
| `Thread.sleep(...)` | Luồng gọi sleep |
| `Object.wait(...)` | Luồng chờ trên monitor của đối tượng |
| `Thread.join(...)` | Luồng đang chờ một luồng khác kết thúc |
| `BlockingQueue.take()` | Luồng đợi có phần tử |
| `CountDownLatch.await()` | Luồng đợi chốt mở |
| `Future.get()` | Luồng đang chờ kết quả của Future |
| `Lock.lockInterruptibly()` | Luồng đang xin khóa theo cơ chế hỗ trợ ngắt |

Ngắt có thể đến **trước khi bắt đầu chờ** hoặc **trong khi đang chờ**. Không được giả định rằng phải đợi luồng vào đúng một trạng thái nhất định mới gửi tín hiệu được.

Không phải mọi lời gọi chặn đều ném `InterruptedException`. Cần đọc hợp đồng của API cụ thể. Khái niệm ngoại lệ được mô tả trong [InterruptedException API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/InterruptedException.html).

## 3. Cờ ngắt và ba phương thức dễ nhầm

Mỗi luồng có trạng thái ngắt; có thể hiểu nó như một cờ, không phải hàng đợi đếm số lần gửi yêu cầu.

| Phương thức | Tác động |
|---|---|
| `thread.interrupt()` | Gửi yêu cầu ngắt tới luồng được chỉ định |
| `thread.isInterrupted()` | Đọc trạng thái ngắt của luồng đó, không xóa cờ |
| `Thread.interrupted()` | Đọc rồi xóa trạng thái ngắt của **luồng hiện tại** |

`Thread.interrupted()` là phương thức static. Dùng cách gọi `Thread.interrupted()` để nhấn mạnh nó làm việc với luồng hiện tại; không gọi qua một biến luồng rồi hiểu nhầm nó đọc luồng ấy.

Ví dụ minh họa trong một luồng:

```java
Thread.currentThread().interrupt();

boolean first = Thread.currentThread().isInterrupted(); // true
boolean second = Thread.interrupted();                 // true, clears
boolean third = Thread.currentThread().isInterrupted(); // false
```

Ví dụ này cho thấy việc **quan sát** bằng `Thread.interrupted()` cũng làm thay đổi trạng thái. Không chèn phương thức ấy vào log chẩn đoán rồi cho rằng nó vô hại.

### Khi ném InterruptedException, cờ có thể đã được xóa

Các thao tác tiêu chuẩn như `sleep`, `wait` hoặc `join` xóa trạng thái ngắt khi báo `InterruptedException`. Trong những đường chờ tiêu chuẩn khác, cần tuân theo hợp đồng tương ứng.

Vì vậy, vào khối `catch` không có nghĩa `isInterrupted()` vẫn phải là `true`. Chính ngoại lệ đang là tín hiệu để tầng gọi biết có yêu cầu ngắt.

Việc **tạo một đối tượng** `new InterruptedException()` không tự xóa cờ; hành vi xóa nằm trong thao tác phản hồi ngắt của API hoặc mã thực thi, không phải hiệu ứng kỳ diệu của lớp ngoại lệ.

Các phương thức trạng thái được quy định trong [Thread API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

## 4. Cách thứ nhất: truyền InterruptedException lên nơi chịu trách nhiệm

Nếu phương thức được phép khai báo ngoại lệ này, cách rõ ràng thường là truyền tiếp:

```java
static String waitForMessage(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

Đây là phương thức minh họa, cần import `BlockingQueue` từ `java.util.concurrent`.

Phương thức không quyết định toàn bộ chính sách dừng của ứng dụng. Nó giữ nguyên khả năng để tầng gọi quyết định khi việc chờ bị ngắt.

Với `Callable`, có thể để ngoại lệ truyền ra khỏi `call()`:

```java
Callable<String> task = () -> queue.take();
```

Đoạn trên giả sử `queue` là một `BlockingQueue<String>` đã có sẵn. `Callable.call()` cho phép ném checked exception.

Khi đang truyền chính `InterruptedException` lên trên, thông thường không cần vừa phục hồi cờ vừa ném lại một cách máy móc. Tín hiệu đã được giữ trong đường truyền ngoại lệ; chính sách cuối cùng nằm ở nơi nhận nó.

Nếu cần dọn tài nguyên, dùng `finally` hoặc try-with-resources để dọn rồi vẫn cho ngoại lệ đi tiếp.

## 5. Cách thứ hai: phục hồi cờ khi không truyền tiếp được

`Runnable.run()` không khai báo checked exception. Nếu nó gọi một thao tác có thể bị ngắt, phải bắt ngoại lệ bên trong hoặc thay đổi cấu trúc xử lý.

Ví dụ một tác vụ xử lý hàng đợi:

```java
Runnable worker = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String message = queue.take();
            process(message);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        closeWorkerResources();
    }
};
```

Đây là mã minh họa: `queue`, `process` và `closeWorkerResources` thuộc ứng dụng. Các thao tác dọn dẹp cần được thiết kế an toàn với trạng thái ngắt và lỗi riêng của chúng.

Ở đây, khối `catch` nằm **ngoài vòng lặp**. Sau khi bắt ngắt và phục hồi cờ, tác vụ đi qua `finally` rồi kết thúc; nó không tiếp tục nhận việc như cũ.

`Thread.currentThread().interrupt()` không ném lại cùng ngoại lệ. Nó đặt lại trạng thái ngắt trên luồng hiện tại để mã ở tầng ngoài còn nhận biết yêu cầu.

### Vì sao chỉ in log là chưa đủ?

Mẫu sau dễ làm mất yêu cầu dừng:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    System.out.println("interrupted");
}
// Tiep tuc xu ly nhu chua co yeu cau dung.
```

Nếu ngoại lệ đã làm cờ bị xóa và mã chỉ tiếp tục, tầng ngoài có thể không biết phải dừng. Hậu quả là ứng dụng khó đóng hoặc tác vụ tiếp tục sau khi người gọi không còn cần.

Tại một ranh giới sở hữu luồng được thiết kế rõ, mã có thể chủ động tiêu thụ tín hiệu để hoàn tất quy trình dừng. Nhưng đó phải là quyết định có chủ đích; không dùng “bắt rồi bỏ qua” làm mặc định trong thư viện hoặc phương thức trợ giúp.

### Phục hồi rồi tiếp tục vòng lặp cũng có thể sai

Nếu khối `catch` phục hồi cờ rồi lập tức thử lại cùng một thao tác chặn hỗ trợ ngắt, thao tác ấy có thể lại ném ngay. Vòng lặp có thể quay nhanh, ghi log liên tục mà không làm được việc hữu ích.

Giữ tín hiệu phải đi cùng thay đổi luồng điều khiển: trả về, thoát vòng lặp, truyền ngoại lệ hoặc chuyển sang bước dừng đã thiết kế.

## 6. Vòng lặp tính toán cần điểm kiểm tra

Nếu tác vụ không dùng lời gọi chặn có hỗ trợ ngắt, Java không tự chèn ngoại lệ vào vòng lặp tính toán.

Mã minh họa:

```java
static long compute(int limit) throws InterruptedException {
    long total = 0;
    for (int i = 0; i < limit; i++) {
        if (Thread.interrupted()) {
            throw new InterruptedException("Computation interrupted");
        }
        total += i;
    }
    return total;
}
```

Ở đây, phương thức chủ động kiểm tra, xóa cờ rồi truyền tín hiệu bằng ngoại lệ. Nếu chỉ cần kiểm tra để thoát mà muốn giữ cờ, dùng `isInterrupted()` và xử lý kết thúc phù hợp.

Trong công việc lớn, có thể kiểm tra ở ranh giới những đơn vị xử lý thay vì mọi phép toán nhỏ; phải cân bằng chi phí kiểm tra và độ nhanh phản hồi. Một đơn vị xử lý không nên kéo dài vô hạn mà không có cơ hội dừng.

Không dùng cờ ngắt như nơi lưu dữ liệu nghiệp vụ. Nó là tín hiệu điều phối của luồng, không mang theo thông điệp hay số lần yêu cầu.

## 7. Đọc đúng InterruptedException từ Future.get

Ba tình huống khác nhau:

| Hiện tượng | Ai gặp tín hiệu? | Nơi gọi get() quan sát gì? |
|---|---|---|
| Luồng đang chờ `get` bị ngắt | Luồng gọi get | `InterruptedException` trực tiếp |
| Thân `Callable` ném `InterruptedException`, Future không bị hủy | Luồng chạy công việc | `ExecutionException` có nguyên nhân là `InterruptedException` |
| Future bị hủy thành công | Trạng thái tác vụ được đánh dấu hủy | `CancellationException` |

Không bắt `ExecutionException` rồi cứ thấy nguyên nhân là `InterruptedException` thì đặt cờ ngắt trên luồng đang nhận kết quả một cách máy móc. Nguyên nhân ấy xảy ra ở **luồng công việc**; nó không tự chứng minh luồng hiện tại đã nhận yêu cầu ngắt.

Nếu một thành phần sở hữu công việc và quyết định rằng nơi chờ bị ngắt thì không còn cần tác vụ, nó có thể yêu cầu `future.cancel(true)`. Đây là quyết định về quyền sở hữu và hủy công việc, không phải hiệu ứng tự động của `get()`.

Nếu Future được nhiều nơi chia sẻ, hủy từ một nơi chờ có thể ảnh hưởng các nơi khác. Phải xác định rõ ai có quyền quyết định vòng đời công việc.

Hợp đồng chờ và hủy nằm trong [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

## 8. Chương trình hoàn chỉnh: ngắt nơi chờ không hủy phép tính

Lưu thành **`InterruptedFutureDemo.java`**, chạy trên Java 17+:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InterruptedFutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch taskStarted = new CountDownLatch(1);
        CountDownLatch releaseTask = new CountDownLatch(1);
        CountDownLatch waiterReady = new CountDownLatch(1);

        try {
            Future<Integer> result = pool.submit(() -> {
                taskStarted.countDown();
                releaseTask.await();
                return 42;
            });

            taskStarted.await();

            Thread waiter = new Thread(() -> {
                waiterReady.countDown();
                try {
                    result.get();
                    throw new AssertionError("Expected interruption");
                } catch (InterruptedException e) {
                    System.out.println(
                            "caught flag: "
                            + Thread.currentThread().isInterrupted());

                    Thread.currentThread().interrupt();

                    System.out.println(
                            "restored flag: "
                            + Thread.currentThread().isInterrupted());
                } catch (ExecutionException e) {
                    throw new IllegalStateException(e.getCause());
                }
            }, "result-waiter");

            waiter.start();
            waiterReady.await();
            waiter.interrupt();
            waiter.join();

            System.out.println("task cancelled: " + result.isCancelled());

            releaseTask.countDown();
            System.out.println(
                    "task result: " + result.get(5, TimeUnit.SECONDS));
        } finally {
            releaseTask.countDown();
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 InterruptedFutureDemo.java
java InterruptedFutureDemo
```

Stdout chính xác:

```text
caught flag: false
restored flag: true
task cancelled: false
task result: 42
```

### Vì sao đầu ra này đáng tin?

Chốt `releaseTask` giữ phép tính chưa hoàn tất trong lúc thử ngắt. Luồng `waiter` đã thông báo chuẩn bị chờ trước khi `main` gọi `interrupt()`.

Tín hiệu có thể tới ngay trước hoặc trong lời gọi `get()`; vì kết quả vẫn chưa sẵn sàng, đường chờ tiêu chuẩn phản hồi bằng `InterruptedException` và xóa trạng thái ngắt. Vì thế dòng đầu in `false`; sau khi phục hồi cờ, dòng sau in `true`.

`main` dùng `join()` để chờ `waiter` kết thúc rồi mới in các dòng còn lại. Không dựa vào một khoảng `sleep` để đoán thứ tự.

Không có lệnh hủy Future hoặc ngắt luồng của executor. Vì vậy công việc vẫn tồn tại; sau khi mở chốt, nó trả `42` bình thường. Ví dụ chứng minh yêu cầu ngắt nơi chờ và yêu cầu dừng công việc là hai việc riêng.

`main` khai báo `throws Exception` để ví dụ tập trung vào cơ chế; ứng dụng thực cần cách phản hồi lỗi và thời hạn chờ phù hợp.

## 9. Không phải mọi thao tác chặn đều giống nhau

### Chờ monitor bằng synchronized

Một luồng đang chờ để **đi vào** khối `synchronized` không thoát việc xin monitor chỉ vì nhận `interrupt()`. Cờ ngắt có thể được đặt nhưng lời xin khóa vẫn phải đợi.

Điều này khác với `Object.wait()`, là một thao tác chờ hỗ trợ ngắt bên trong cơ chế monitor. Không gộp hai tình huống chỉ vì đều liên quan đến `synchronized`.

### Xin khóa có hỗ trợ ngắt

Khi cần khả năng dừng lúc đang đợi khóa, xem xét `lockInterruptibly()` của `Lock` và hợp đồng triển khai cụ thể. Nếu đã lấy được khóa, vẫn phải giải phóng bằng `finally`.

Khả năng xin khóa và ngắt được mô tả trong [Lock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).

### I/O có hợp đồng riêng

Không tuyên bố mọi I/O đều ném `InterruptedException`. Ví dụ, khi đang chặn trên một `InterruptibleChannel`, ngắt có thể làm đóng channel và báo `ClosedByInterruptException`, đồng thời giữ trạng thái ngắt.

Vì vậy, sau ngắt cũng không được giả định tài nguyên I/O còn nguyên trạng để dùng lại. Xem [InterruptibleChannel API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/InterruptibleChannel.html).

Với các thư viện mạng, cơ sở dữ liệu hoặc client khác, cần dùng cơ chế timeout/hủy được thư viện hỗ trợ và kiểm tra giới hạn của nó.

## 10. Dọn dẹp tài nguyên và ý nghĩa nghiệp vụ

Phản hồi ngắt cần đưa công việc về trạng thái có thể quản lý:

- Giải phóng khóa hoặc permit đã lấy thành công.
- Đóng tài nguyên mà công việc sở hữu.
- Dừng nhận thêm đơn vị xử lý khi không còn cần.
- Báo kết quả chưa hoàn tất theo hợp đồng ứng dụng.

Không giải phóng một permit chưa lấy được chỉ vì `acquire()` bị ngắt. Không gọi `unlock()` nếu việc xin khóa đã thất bại trước khi sở hữu khóa.

Cờ ngắt không tự hoàn tác phần việc đã làm. Nếu tác vụ đã ghi một phần tệp, gửi một yêu cầu hoặc commit dữ liệu, cần chính sách nghiệp vụ riêng cho phần tác động ấy.

Việc dọn dẹp cũng có thể bị chặn hoặc thất bại. Nên thiết kế nó có giới hạn và tránh biến quy trình dừng thành một lời chờ vô hạn khác.

## 11. Chọn cách xử lý theo vị trí

| Vị trí của mã | Hướng xử lý thường phù hợp |
|---|---|
| Phương thức trợ giúp được phép khai báo ngoại lệ | Truyền `InterruptedException` lên trên |
| `Callable` không sở hữu chính sách dừng | Cho phép ngoại lệ truyền khỏi `call()` |
| `Runnable` không thể khai báo checked exception | Bắt, giữ tín hiệu khi phù hợp, rồi kết thúc công việc |
| Nơi gọi `Future.get()` sở hữu tác vụ | Phản hồi ngắt và quyết định có hủy công việc hay không |
| Mã thư viện không biết chính sách của ứng dụng | Không âm thầm tiêu thụ yêu cầu ngắt |
| Vòng lặp tính toán dài | Bố trí điểm kiểm tra và đường thoát rõ ràng |

Đây là hướng lựa chọn theo trách nhiệm, không phải công thức bắt mọi `Exception` rồi đặt cờ ngắt. Chỉ xử lý tín hiệu ngắt khi thật sự có nó hoặc khi hợp đồng của thành phần yêu cầu.

## 12. Tự kiểm tra

1. `thread.interrupt()` có bảo đảm luồng đích kết thúc trước khi phương thức trả về không?
2. `isInterrupted()` khác `Thread.interrupted()` ở điểm nào?
3. Vì sao cờ có thể là `false` ngay khi vào `catch (InterruptedException)`?
4. Ngắt một luồng gọi `Future.get()` có tự gọi `future.cancel(true)` không?
5. Vì sao phục hồi cờ rồi thử lại vô hạn cùng thao tác chặn có thể tạo vòng lặp quay nhanh?
6. `ExecutionException` chứa `InterruptedException` có chứng minh luồng đang nhận kết quả đã bị ngắt không?

**Gợi ý:** (1) Không. (2) Phương thức static đọc và xóa cờ của luồng hiện tại; phương thức còn lại chỉ đọc cờ của luồng được chỉ định. (3) API chờ có thể đã xóa cờ và truyền tín hiệu bằng ngoại lệ. (4) Không. (5) Cờ vẫn đặt khiến thao tác phản hồi ngắt ngay. (6) Không; lỗi có thể phát sinh trên luồng thực hiện công việc.

Xử lý ngắt đúng cần xác định **luồng nào nhận yêu cầu, ai sở hữu chính sách dừng, và tín hiệu được truyền tiếp hay được giữ lại bằng cách nào**.
