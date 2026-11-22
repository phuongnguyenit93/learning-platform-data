# `InterruptedException` là tín hiệu gì trong Java?

`InterruptedException` là **ngoại lệ có kiểm tra (checked exception)** thông báo rằng **luồng đang thực hiện một thao tác chờ có thể ngắt đã nhận yêu cầu interrupt**. Trong Java, interrupt là cơ chế **báo hiệu để luồng hợp tác dừng việc chờ hoặc thay đổi hướng xử lý**. Nó không phải lệnh cưỡng bức giết luồng, không mặc nhiên là lỗi nghiệp vụ, và cũng không tự bảo đảm tác vụ đã hủy xong.

Bài viết thuộc nhóm **Ngắt và hủy** của Java Core Exception, sử dụng Java 17+. Mục tiêu là hiểu tín hiệu interrupt, trạng thái cờ interrupt, xử lý `InterruptedException` đúng cách, sự khác nhau giữa ngắt luồng chờ và ngắt luồng làm việc, cũng như cách dùng trong ứng dụng đồng thời thực tế.

## 1. Hiểu đúng tín hiệu interrupt

Mỗi đối tượng `Thread` có **trạng thái interrupt** (thường gọi là *interrupt status* hoặc *interrupt flag*).

Khi một luồng A gọi:

```java
worker.interrupt();
```

thì về mặt khái niệm A gửi tín hiệu tới `worker`: **“hãy chú ý, có yêu cầu ngắt”**. Tùy thời điểm và thao tác `worker` đang làm, Java sẽ phản ứng khác nhau:

1. Nếu `worker` đang chạy mã tính toán bình thường, `interrupt()` thường đặt cờ interrupt của `worker` thành `true`; luồng vẫn có thể tiếp tục chạy cho đến khi chính mã của nó quan sát cờ và quyết định dừng.
2. Nếu `worker` đang trong một thao tác chờ **có thể ngắt** như `Thread.sleep(...)`, `Object.wait(...)`, `Thread.join(...)`, `BlockingQueue.take()` hoặc `CountDownLatch.await()`, thao tác có thể kết thúc sớm bằng `InterruptedException`.
3. Với các thao tác chờ thông dụng như `sleep`, `wait`, `join`, khi `InterruptedException` được ném, **trạng thái interrupt bị xóa**. Nếu mã bắt ngoại lệ mà không truyền tiếp hoặc khôi phục tín hiệu, tầng gọi cao hơn có thể không còn nhận ra yêu cầu ngắt.
4. Nếu luồng bị kẹt trong thao tác không hỗ trợ interrupt, hoặc cố tình phớt lờ tín hiệu, gọi `interrupt()` **không bảo đảm** luồng dừng. Một số API I/O có quy tắc riêng, nên phải xem hợp đồng của thao tác cụ thể.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| `Thread.interrupt()` | Gửi yêu cầu interrupt đến một luồng; không ép nó chấm dứt |
| `Thread.isInterrupted()` | Kiểm tra trạng thái interrupt của **đối tượng luồng**, không tự xóa cờ |
| `Thread.interrupted()` | Phương thức `static` kiểm tra **luồng hiện tại** và **xóa cờ** interrupt của luồng đó |

`InterruptedException` không tương đương `ThreadDeath`, không tự đồng nghĩa với `CancellationException` và không chứng minh chương trình đang gặp sự cố. Trong nhiều hệ thống, ngắt là tín hiệu điều phối vòng đời: đóng ứng dụng, hủy tác vụ, ngừng consumer, dừng chờ khi request hết hiệu lực.

## 2. Luồng phát tín hiệu và luồng nhận tín hiệu

Giả sử luồng `main` khởi tạo một worker đang chờ dữ liệu:

```text
main                                     worker
----                                     ------
new Thread(...) ──────────────────────►  bắt đầu chạy
start()                                  gọi await()/sleep()/take()
                                           │
worker.interrupt() ─── tín hiệu ───────►  thao tác chờ nhận interrupt
                                           │
                                           ▼
                                       InterruptedException
                                           │
                                       thoát hoặc xử lý tiếp
worker.join() ─── chờ worker kết thúc ──►  kết thúc
```

`InterruptedException` được ném **tại luồng đang gọi thao tác chờ**. Nó không tự động được “ném ngược” sang luồng đã gọi `interrupt()`.

Nếu luồng A gọi `worker.interrupt()` trong khi luồng B đang `worker.join()`, **worker là đối tượng bị yêu cầu ngắt**. Lời gọi `join()` của B chỉ tự ném `InterruptedException` nếu **chính B bị interrupt** trong lúc đợi. Việc worker bị interrupt không mặc nhiên làm B bị interrupt.

Đối với thao tác ngủ:

```java
try {
    Thread.sleep(10_000);
} catch (InterruptedException e) {
    // Chính luồng đang ngủ nhận tín hiệu ngắt.
}
```

Đây là **đoạn minh họa trong thân phương thức**, không phải một tệp Java độc lập. `sleep(...)` dừng chờ sớm khi nhận interrupt; câu lệnh `catch` chạy trong cùng luồng vừa bị ngắt.

## 3. Ví dụ chạy được: bắt tín hiệu và khôi phục cờ interrupt

Tạo tệp `InterruptSignalDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptSignalDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            System.out.println("worker: sẵn sàng");
            ready.countDown();

            try {
                new CountDownLatch(1).await();
                System.out.println("worker: hoàn thành bình thường");
            } catch (InterruptedException e) {
                System.out.println("worker: bắt ngoại lệ, flag="
                        + Thread.currentThread().isInterrupted());

                Thread.currentThread().interrupt();

                System.out.println("worker: khôi phục, flag="
                        + Thread.currentThread().isInterrupted());
            }
        }, "demo-worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("main: worker alive=" + worker.isAlive());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac InterruptSignalDemo.java
java InterruptSignalDemo
```

Kết quả chuẩn:

```text
worker: sẵn sàng
worker: bắt ngoại lệ, flag=false
worker: khôi phục, flag=true
main: worker alive=false
```

**Vì sao kết quả ổn định?**

- `ready.await()` buộc `main` chờ đến lúc worker phát tín hiệu đã sẵn sàng. Worker có thể vào `await()` trước hoặc sau lời gọi `interrupt()` của `main`, nhưng thao tác `await()` sẽ phản ứng với trạng thái interrupt trong cả hai trường hợp.
- Trong `catch`, `flag=false` vì việc ném `InterruptedException` từ `CountDownLatch.await()` đã xóa cờ ngắt. Đây là hành vi của API chờ có thể ngắt đó.
- `Thread.currentThread().interrupt()` trong nhánh `catch` **khôi phục** cờ cho worker. Vì worker sắp kết thúc nên không có vòng lặp tiếp tục tiêu thụ tín hiệu.
- `worker.join()` bảo đảm main chỉ in dòng cuối **sau khi worker đã chấm dứt**. `Thread.isAlive()` do đó là `false`.

Ví dụ này cố tình dùng `CountDownLatch` thay cho việc đoán thứ tự chạy bằng `Thread.sleep(...)`, vì lịch thực thi các luồng không được bảo đảm.

Lưu ý: cờ interrupt được khôi phục là một **trạng thái trên Thread**, không phải bằng chứng worker sẽ chấm dứt. Worker ở đây chấm dứt vì đoạn mã chạy đến cuối.

## 4. Vì sao `InterruptedException` là checked exception?

`InterruptedException` kế thừa `Exception`, không kế thừa `RuntimeException`. Vì vậy các phương thức có thể ném nó thường khai báo `throws InterruptedException`; người gọi phải **bắt** hoặc **khai báo truyền tiếp** ngoại lệ.

Ví dụ dưới đây là một phương thức hoàn chỉnh có thể đặt trong một class Java:

```java
static void pause() throws InterruptedException {
    Thread.sleep(1_000);
}
```

Khi caller cũng có khả năng phản ứng đúng với interrupt, **truyền tiếp** thường là lựa chọn đơn giản và rõ ràng nhất:

```java
static String waitForResult(java.util.concurrent.Future<String> future)
        throws InterruptedException, java.util.concurrent.ExecutionException {
    return future.get();
}
```

Nếu không thể truyền checked exception qua API hiện tại, có thể bắt, **khôi phục cờ**, rồi thoát theo chiến lược của tầng ứng dụng:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Công việc đang chờ bị yêu cầu ngắt", e);
}
```

Đoạn `try/catch` này là **mã minh họa trong thân phương thức**. Trong ứng dụng thực tế, kiểu exception được chuyển đổi phải phù hợp hợp đồng của hàm. Việc `throw` còn giúp tránh chạy tiếp như thể không có tín hiệu ngắt.

Quy tắc ra quyết định:

- **Có thể khai báo `throws InterruptedException`**: thường truyền ngoại lệ lên caller, để caller quyết định hủy hoặc kết thúc. Việc khôi phục cờ trước khi truyền không mặc nhiên cần thiết.
- **Đã bắt ngoại lệ để kết thúc tác vụ tại đây**: thoát vòng lặp hoặc trả về; khôi phục cờ nếu cần báo trạng thái interrupt cho tầng phía trên.
- **Phải đổi sang ngoại lệ khác**: thường gọi `Thread.currentThread().interrupt()` trước khi ném ngoại lệ mới và **giữ cause** là `e`.
- **Chủ đích xử lý và tiếp tục**: chỉ làm nếu hợp đồng ứng dụng thực sự cho phép, và đã quyết định rõ có giữ hay tiêu thụ tín hiệu. Đây là lựa chọn đặc biệt, không phải mặc định.

Một anti-pattern phổ biến:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Bỏ qua: bên yêu cầu ngắt mất tín hiệu mà không biết.
}
```

Nếu sau đó chương trình tiếp tục xử lý dài hoặc chờ vô hạn, tác vụ có thể không đáp ứng yêu cầu dừng. Dòng `ignored` không tự giải quyết ngắt; thông thường cần truyền tiếp, khôi phục cờ và thoát, hoặc có chính sách xử lý riêng được giải thích rõ.

## 5. `isInterrupted()` khác `Thread.interrupted()` thế nào?

`Thread.currentThread().isInterrupted()` đọc cờ của luồng hiện tại mà không xóa. `Thread.interrupted()` là phương thức tĩnh của `Thread`: đọc rồi **xóa cờ của luồng đang chạy lệnh này**.

Ví dụ độc lập `InterruptFlagDemo.java`:

```java
public class InterruptFlagDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread thread = new Thread(() -> {
            Thread.currentThread().interrupt();

            System.out.println("isInterrupted #1: "
                    + Thread.currentThread().isInterrupted());
            System.out.println("Thread.interrupted(): "
                    + Thread.interrupted());
            System.out.println("isInterrupted #2: "
                    + Thread.currentThread().isInterrupted());
        });

        thread.start();
        thread.join();
    }
}
```

Chạy:

```bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
```

Kết quả chính xác:

```text
isInterrupted #1: true
Thread.interrupted(): true
isInterrupted #2: false
```

Giải thích:

1. Worker tự gọi `interrupt()`, nên cờ được đặt `true`.
2. `isInterrupted()` chỉ kiểm tra, nên vẫn là `true`.
3. `Thread.interrupted()` vừa trả `true` vừa **xóa cờ**.
4. Lần `isInterrupted()` cuối vì thế trả `false`.

Đừng viết `otherThread.interrupted()` với ý định kiểm tra trạng thái ngắt của `otherThread`: cú pháp đó gọi **phương thức tĩnh** và kiểm tra **luồng đang chạy**, dù viết qua tên biến đối tượng. Muốn hỏi trạng thái của luồng khác, dùng `otherThread.isInterrupted()`.

Vì `Thread.interrupted()` tiêu thụ tín hiệu, hãy cân nhắc kỹ trước khi dùng trong logging, tiện ích kiểm tra hoặc điều kiện vòng lặp. Nếu chỉ cần quan sát, ưu tiên `isInterrupted()`.

## 6. Những thao tác nào thường ném `InterruptedException`?

| API tiêu biểu | Luồng nào nhận `InterruptedException`? | Điều đang bị ngắt |
|---|---|---|
| `Thread.sleep(...)` | Luồng đang ngủ | Chờ hết thời gian ngủ |
| `Object.wait(...)` | Luồng đang đợi trên monitor | Chờ notify hoặc thời điểm timeout |
| `Thread.join(...)` | Luồng đang **gọi** `join()` | Chờ luồng khác kết thúc |
| `CountDownLatch.await()` | Luồng đang gọi `await()` | Chờ latch về 0 |
| `BlockingQueue.take()` / `put(...)` | Luồng lấy hoặc thêm phần tử | Chờ queue có phần tử hoặc còn chỗ |
| `Future.get()` | Luồng đang lấy kết quả | Chờ tác vụ kết thúc |
| `Lock.lockInterruptibly()` | Luồng đang xin khóa | Chờ lấy khóa |
| `Semaphore.acquire()` | Luồng đang xin permit | Chờ permit |
| `ExecutorService.awaitTermination(...)` | Luồng đang chờ executor đóng | Chờ các tác vụ đã gửi kết thúc |

Điều quan trọng không nằm ở việc có tạo thread hay không, mà nằm ở **thao tác chờ cụ thể**. Một phương thức thuần CPU như tính tổng vòng lặp sẽ không tự sinh `InterruptedException` khi cờ interrupt được đặt. Mã tính toán muốn hỗ trợ hủy hợp tác thường phải tự quan sát cờ hoặc gọi thao tác có khả năng ngắt.

Ví dụ vòng lặp CPU:

```java
static long countUntilInterrupted() {
    long counter = 0;
    while (!Thread.currentThread().isInterrupted()) {
        counter++;
    }
    return counter;
}
```

Đây là **phương thức minh họa**, không phải ví dụ chạy đầy đủ: số vòng đếm tùy thời điểm và môi trường. Nếu vòng lặp chứa thao tác chờ ném `InterruptedException`, cần bổ sung xử lý/truyền ngoại lệ ở vị trí thao tác ấy.

Một số API khác có phản ứng interrupt khác nhau. Chẳng hạn các thao tác I/O kênh có thể đóng channel hoặc ném ngoại lệ chuyên biệt thay vì `InterruptedException`. Vì vậy đừng áp quy tắc “mọi chỗ bị ngắt đều ném `InterruptedException`” cho toàn bộ Java.

## 7. Vòng đời worker: dừng hợp tác với `BlockingQueue.take()`

Giả sử một worker đang đợi công việc từ hàng đợi. Một chính sách shutdown hợp lý là yêu cầu interrupt, worker thoát khỏi `take()`, chạy `finally` để dọn dẹp, rồi kết thúc.

Tạo tệp `QueueInterruptDemo.java`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class QueueInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch ready = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            try {
                System.out.println("consumer: đang chờ");
                ready.countDown();
                String item = queue.take();
                System.out.println("consumer: nhận " + item);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("consumer: đã nhận tín hiệu dừng");
            } finally {
                System.out.println("consumer: dọn dẹp");
            }
        }, "queue-consumer");

        consumer.start();
        ready.await();
        consumer.interrupt();
        consumer.join();

        System.out.println("main: hoàn tất");
    }
}
```

Chạy:

```bash
javac QueueInterruptDemo.java
java QueueInterruptDemo
```

Kết quả:

```text
consumer: đang chờ
consumer: đã nhận tín hiệu dừng
consumer: dọn dẹp
main: hoàn tất
```

`BlockingQueue.take()` chờ đến khi có phần tử hoặc bị ngắt. Hàng đợi trong ví dụ không được thêm phần tử; sau tín hiệu `interrupt()`, worker thoát `take()` bằng `InterruptedException`. `finally` chạy để xử lý tài nguyên. `join()` bảo đảm main chỉ in sau khi worker kết thúc.

Trong dịch vụ thực, `finally` phải dọn đúng tài nguyên mà worker sở hữu: khóa, stream, kết nối, transaction hoặc trạng thái nghiệp vụ tùy trường hợp. Cần thiết kế dọn dẹp **an toàn khi bị yêu cầu hủy**; không giả định mọi tác vụ đang dở đều có thể bỏ mà không cần rollback hoặc xử lý bù.

### Vòng lặp consumer nên bắt ở đâu?

Với một worker đọc queue liên tục, mẫu thường gặp:

```java
static void consume(java.util.concurrent.BlockingQueue<String> queue) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String message = queue.take();
            process(message);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        releaseResources();
    }
}
```

Đây là **mẫu phác thảo**, giả định ứng dụng đã định nghĩa `process(String)` và `releaseResources()`; không phải chương trình Java độc lập. Mã sử dụng `take()` để ngừng chờ khi không còn dữ liệu. Sau `catch`, phương thức kết thúc. Nếu `process` tự chặn hoặc ném lỗi, cần thêm xử lý phù hợp với hợp đồng thực tế của nó.

Sai lầm điển hình là đặt `catch` **bên trong** vòng lặp nhưng vẫn tiếp tục:

```java
// Minh họa lỗi thiết kế, không dùng như vòng lặp production.
while (true) {
    try {
        queue.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Sau đó lặp lại: take() lại bị ngắt ngay, có thể tạo vòng lặp nóng.
    }
}
```

Khi cờ đã được khôi phục, lần chờ có thể ngắt tiếp theo thường lập tức ném `InterruptedException`; vòng lặp có nguy cơ chiếm CPU và không thể shutdown. **Khôi phục cờ phải đi cùng hành động thích hợp**, chẳng hạn thoát vòng lặp hoặc truyền lỗi lên trên.

## 8. Liên hệ với `ExecutorService`, `Future` và hủy tác vụ

Trong executor có **hai luồng cần phân biệt**:

- **Worker** đang chạy `Callable.call()` hoặc `Runnable.run()`.
- **Caller** đang gọi `Future.get()` để chờ worker hoàn thành.

Khi caller đang ở `get()` và **caller bị interrupt**, caller nhận `InterruptedException` trực tiếp. Tác vụ worker **không mặc nhiên bị hủy**. Ngược lại, nếu worker nhận interrupt trong một thao tác chờ và `Callable` để `InterruptedException` thoát ra, tác vụ sẽ được đánh dấu kết thúc thất bại và `Future.get()` của caller thường ném `ExecutionException` có cause là `InterruptedException` — **nếu Future chưa bị chuyển sang trạng thái hủy**.

Ví dụ độc lập `FutureWorkerInterruptDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureWorkerInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> future = executor.submit(() -> {
                Thread.currentThread().interrupt();
                Thread.sleep(1_000);
                return "thành công";
            });

            try {
                System.out.println(future.get());
            } catch (ExecutionException e) {
                System.out.println("cause = "
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac FutureWorkerInterruptDemo.java
java FutureWorkerInterruptDemo
```

Kết quả:

```text
cause = InterruptedException
```

`Thread.sleep(...)` thấy cờ interrupt và ném `InterruptedException` trong worker. `Callable` không bắt ngoại lệ đó; executor lưu thất bại của tác vụ. Caller gọi `get()` nhận `ExecutionException`, trong đó `getCause()` là `InterruptedException` của worker. Caller **không nhận `InterruptedException` trực tiếp** trong tình huống này vì chính caller không bị interrupt.

Đối với hủy Future:

```java
boolean accepted = future.cancel(true);
```

Đây là đoạn mã minh họa, cần có biến `future` thuộc loại `Future<?>` trong phạm vi. Nếu hủy thành công, Future được đánh dấu canceled và `get()` ném **`CancellationException`**; `cancel(true)` cho phép yêu cầu interrupt worker đang chạy, nhưng không bảo đảm worker sẽ ngừng ngay. Khi `cancel(false)`, không yêu cầu ngắt worker đang thực thi. Việc ngắt worker và trạng thái Future **có quan hệ nhưng không phải cùng một khái niệm**.

Với executor:

- `shutdown()` dừng nhận công việc mới và để các công việc đã nhận tiếp tục thực thi; không tự động interrupt tất cả worker và không tự đợi chúng kết thúc.
- `shutdownNow()` thử dừng những tác vụ đang hoạt động (thường bằng interrupt), ngừng xử lý những tác vụ đang đợi và trả danh sách tác vụ chưa bắt đầu. Đây là **best effort**, không bảo đảm tác vụ phớt lờ interrupt sẽ dừng.
- `awaitTermination(...)` giúp caller đợi executor đóng và cũng có thể ném `InterruptedException` nếu caller bị ngắt.

Thiết kế lifecycle phải tách **yêu cầu dừng** khỏi **xác nhận đã kết thúc** (`join()`, `awaitTermination()`, hoặc cơ chế trạng thái hoàn tất).

## 9. Cờ interrupt bị xóa: nguyên tắc và ranh giới

Nhiều thao tác chờ được định nghĩa là **ném `InterruptedException` và xóa trạng thái interrupt**. Điều này giải thích vì sao `isInterrupted()` có thể là `false` trong nhánh `catch`.

Tuy nhiên, quy tắc “thấy interrupt là luôn tự xóa” là sai. Cờ thường vẫn được đặt khi luồng chỉ thực thi mã tính toán; `isInterrupted()` không xóa; `Thread.interrupted()` xóa theo chủ đích; các API I/O và đồng bộ khác có thể xử lý riêng. Đọc tài liệu của API đang dùng là cần thiết nếu việc duy trì cờ ảnh hưởng logic.

Mẫu xử lý an toàn ở lớp trung gian:

```java
static boolean waitUntilReady(java.util.concurrent.CountDownLatch latch) {
    try {
        latch.await();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Đây là một **phương thức hợp lệ**: khi bị interrupt, trả `false` để caller biết chờ không thành công **và giữ cờ interrupt**. Dù vậy, nếu thiết kế API cho phép `throws InterruptedException`, truyền tiếp thường minh bạch hơn so với mã hóa kết quả trong `boolean`.

Không nên gọi `Thread.interrupted()` chỉ để kiểm tra xem worker bị ngắt chưa rồi quên rằng nó đã xóa cờ. Nếu API cần chủ động tiêu thụ tín hiệu interrupt, phải ghi rõ quy tắc đó trong hợp đồng phương thức.

## 10. `InterruptedException` và `CancellationException`, `TimeoutException`

Ba loại sự kiện dễ bị nhầm:

| Tín hiệu | Tác nhân/tình huống | Hành vi cần nghĩ tới |
|---|---|---|
| `InterruptedException` | Luồng hiện tại bị interrupt khi thao tác có thể ngắt | Tôn trọng yêu cầu ngắt: truyền tiếp, khôi phục cờ rồi kết thúc, hoặc xử lý theo hợp đồng |
| `CancellationException` | Future/operation đã được đánh dấu hủy theo API của nó | Xử lý trạng thái canceled; không giả định mọi worker đã hoàn tất dọn dẹp |
| `TimeoutException` | Thao tác chờ có timeout không có kết quả trong thời hạn | Quyết định thử lại, báo quá hạn hay chủ động gọi cancel; timeout không tự đồng nghĩa với interrupt |

Ví dụ, `future.get(500, TimeUnit.MILLISECONDS)` có thể ném `TimeoutException` vì tác vụ còn chạy; lúc này caller có thể chọn `future.cancel(true)`. Còn `future.get()` có thể ném `InterruptedException` nếu caller bị ngắt khi chờ, dù tác vụ sau đó vẫn hoàn thành bình thường.

Khi thiết kế API, cần làm rõ **ngắt là yêu cầu đóng toàn bộ tác vụ**, **chỉ yêu cầu dừng chờ**, hay **một lựa chọn hủy trong luồng điều phối**. Không có một chính sách duy nhất đúng cho mọi hệ thống.

## 11. Các lỗi phổ biến và cách sửa

### 11.1. Nuốt interrupt rồi tiếp tục như bình thường

Sai:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    System.out.println("Có ngắt nhưng bỏ qua");
}
```

Hậu quả: caller yêu cầu dừng nhưng tín hiệu bị mất; tác vụ vẫn có thể tiếp tục chờ hoặc xử lý.

Tùy thiết kế, sửa bằng cách truyền `InterruptedException` lên ngoài, hoặc khôi phục cờ và **thoát**:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // Ví dụ bên trong một phương thức void.
}
```

Hai đoạn là **mảnh mã đặt trong phương thức**, với `queue` là một `BlockingQueue` đã tồn tại.

### 11.2. Gọi `Thread.interrupted()` khi chỉ định kiểm tra

```java
boolean wasInterrupted = Thread.interrupted();
```

Lệnh trên **xóa cờ của luồng hiện tại**. Nếu chỉ định quan sát, dùng:

```java
boolean interrupted = Thread.currentThread().isInterrupted();
```

Đừng trông đợi mã khác trong cùng luồng thấy cờ như trước sau khi bạn đã gọi `Thread.interrupted()`.

### 11.3. Khôi phục cờ nhưng không dừng, tạo vòng lặp bận

Khôi phục cờ rồi lặp lại một thao tác ném `InterruptedException` ngay có thể làm CPU tăng và worker không chịu kết thúc. Sửa bằng cách thoát vòng lặp, propagate, hoặc thiết kế quy tắc khôi phục và xử lý trạng thái rõ ràng.

### 11.4. Tưởng `interrupt()` giết worker ngay tức thì

Một tác vụ CPU không quan sát cờ, thao tác chặn không hỗ trợ ngắt, hoặc worker bắt rồi nuốt ngoại lệ có thể tiếp tục chạy. Muốn dừng có kiểm soát, phải thiết kế điểm kiểm tra cờ, các thao tác chờ có thể ngắt và tài nguyên cần dọn.

### 11.5. Nhầm luồng bị ngắt khi gọi `join()` hoặc `get()`

Nếu main bị interrupt khi gọi `worker.join()` hoặc `future.get()`, `InterruptedException` xuất hiện **trong main**. Nó không có nghĩa worker cũng đã bị interrupt. Khi cần hủy worker, phải gửi tín hiệu/hủy một cách riêng biệt và cân nhắc hậu quả.

### 11.6. Bắt `Exception` hoặc `Throwable` quá rộng

Trong vòng lặp worker, viết `catch (Exception e)` rồi tiếp tục thường vô tình bắt luôn `InterruptedException`, gây mất tín hiệu dừng. Nên bắt `InterruptedException` riêng và xử lý vòng đời có chủ đích; những lỗi nghiệp vụ khác có chính sách log/retry độc lập.

### 11.7. Dùng `Thread.stop()` để ép dừng

`Thread.stop()` là API lỗi thời, nguy hiểm vì có thể chấm dứt luồng khi trạng thái chia sẻ đang không nhất quán. Không dùng thay cho interrupt; thiết kế dừng hợp tác, đóng tài nguyên và cơ chế timeout phù hợp.

### 11.8. Trộn tín hiệu ngắt với lỗi nghiệp vụ

Một tác vụ bị ngắt khi chờ thường nên thoát sớm hoặc báo hủy; không nên mặc định ghi log mức lỗi nghiêm trọng như thể ứng dụng gặp bug. Tuy nhiên, nếu ngắt xuất hiện ngoài dự kiến trong một luồng không được phép dừng, cần điều tra nguyên nhân gửi interrupt và tác động đến tính đúng đắn của nghiệp vụ.

## 12. Quy trình chọn cách xử lý

```text
Thao tác chờ ném InterruptedException
                    │
                    ▼
       Phương thức có thể truyền tiếp?
              ┌─────┴─────┐
             Có          Không
              │            │
      khai báo throws       ▼
      InterruptedException  Có xử lý để thoát tại đây?
                           ┌┴─────────┐
                          Có         Không
                           │           │
                    restore flag       ▼
                    khi phù hợp     Chuyển lỗi theo hợp đồng,
                    và kết thúc     restore flag, giữ cause
```

Thực hành tốt là **xem interrupt như yêu cầu hợp tác**: nhận tín hiệu tại điểm chờ hoặc điểm kiểm tra, bảo toàn thông tin để tầng có trách nhiệm quyết định, kết thúc công việc an toàn, rồi xác nhận trạng thái đã hoàn tất nếu cần.

Checklist khi review code đồng thời:

- Có biết **luồng nào** được `interrupt()` và **luồng nào** đang đợi?
- Các thao tác dài hạn có cơ chế chờ có thể ngắt, timeout hoặc kiểm tra cờ?
- `InterruptedException` được truyền tiếp hay khôi phục cờ và thoát? Có nhánh bắt rộng vô tình nuốt nó không?
- `Thread.interrupted()` có được dùng với chủ đích xóa cờ?
- Sau `cancel(true)`/`shutdownNow()`, ứng dụng có tiếp tục theo dõi hoàn tất và dọn dẹp?
- Có phân biệt trạng thái hủy Future với ngoại lệ phát sinh bên trong worker?
- Các ví dụ/test có điều phối bằng latch, join hoặc đồng bộ thích hợp thay vì dựa vào thời gian sleep may rủi?

**Ghi nhớ:** `InterruptedException` chủ yếu là **tín hiệu rằng luồng hiện tại phải xem lại việc chờ/tiếp tục làm việc**. Phản ứng phù hợp thường là truyền tín hiệu lên caller hoặc khôi phục cờ rồi kết thúc an toàn. Chỉ gọi `interrupt()` chưa chứng minh worker đã dừng; chỉ bắt `InterruptedException` chưa có nghĩa đã xử lý xong yêu cầu hủy.
