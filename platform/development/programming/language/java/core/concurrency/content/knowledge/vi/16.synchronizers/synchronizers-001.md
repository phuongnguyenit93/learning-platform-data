# CountDownLatch: chờ một mốc hoàn tất trong Java

## 1. CountDownLatch giải quyết bài toán gì?

Trong lập trình đa luồng, có nhiều lúc một thread phải **đợi một sự kiện hoặc một nhóm công việc đạt mốc hoàn tất** rồi mới tiếp tục. Ví dụ:

- Thread điều phối gửi ba công việc độc lập cho executor, chỉ tổng hợp kết quả sau khi cả ba đã kết thúc.
- Một bộ kiểm thử muốn đợi các worker chuẩn bị xong rồi đồng loạt phát tín hiệu bắt đầu.
- Một thread phải chờ một bước khởi tạo được báo hiệu thành công trước khi bắt đầu đọc dữ liệu.
- Nhiều thread cần chờ cùng một sự kiện “cấu hình sẵn sàng”.

`CountDownLatch` trong package `java.util.concurrent` là một **synchronizer dùng một lần** (one-shot). Nó quản lý một bộ đếm không âm được đặt khi xây dựng. Các thread có thể gọi `await()` để chờ cho đến khi bộ đếm về **0**; những thread báo hoàn tất gọi `countDown()` để giảm bộ đếm.

Một cách hình dung:

```text
CountDownLatch(3)

Worker A hoàn tất → countDown(): 3 → 2
Worker B hoàn tất → countDown(): 2 → 1
Worker C hoàn tất → countDown(): 1 → 0

Thread điều phối gọi await() ──đang chờ──► tiếp tục khi count = 0
```

Đây là **mốc đồng bộ**, không phải hàng đợi chứa dữ liệu, không tạo thread, không tự chạy task và cũng không tự đảm bảo task thành công. Việc bộ đếm về 0 chỉ cho biết các lần báo hiệu đã xảy ra theo hợp đồng do lập trình viên thiết kế.

Bài học tập trung vào **Java Concurrency thuần JDK**, không dùng các API chuyên biệt của Spring.

## 2. Những API cốt lõi

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch latch = new CountDownLatch(3);

// Thread báo một sự kiện/một phần việc đã đến mốc:
latch.countDown();

// Thread cần đợi mốc:
latch.await();

// Thread cần giới hạn thời gian chờ:
boolean reached = latch.await(500, TimeUnit.MILLISECONDS);

// Quan sát bộ đếm, chủ yếu để chẩn đoán:
long count = latch.getCount();
```

Đoạn trên minh họa API; hai lời gọi `await` là hai cách sử dụng thay thế, không phải chương trình độc lập.

| API | Hành vi | Điểm cần nhớ |
| --- | --- | --- |
| `new CountDownLatch(n)` | Tạo latch với bộ đếm ban đầu bằng `n` | `n` không được âm; `n == 0` nghĩa latch đã mở sẵn |
| `countDown()` | Giảm bộ đếm 1 nếu còn dương | Không chặn; ở 0 rồi thì không giảm xuống âm |
| `await()` | Đợi cho tới khi bộ đếm bằng 0 | Có thể ném `InterruptedException` |
| `await(long, TimeUnit)` | Đợi tối đa thời gian quy định | Trả `true` nếu về 0, `false` nếu hết hạn; cũng có thể bị interrupt |
| `getCount()` | Trả số đếm hiện tại | Dùng monitoring/debugging, không thay cho phối hợp đồng bộ |

Constructor `new CountDownLatch(-1)` ném `IllegalArgumentException`. Giá trị `0` hợp lệ và làm `await()` trở về ngay, trừ tình huống thread bị interrupt theo hợp đồng của API.

**Không có `reset()`.** Khi về 0, latch mở vĩnh viễn. Những lần `await()` tiếp theo không còn chờ; những lần `countDown()` tiếp theo không có tác dụng. Muốn chờ một giai đoạn mới, tạo một `CountDownLatch` mới hoặc chọn synchronizer có thể tái sử dụng khi thích hợp.

## 3. Cơ chế đợi và báo hiệu

Giả sử có một latch đếm 2:

1. Thread M gọi `latch.await()` khi bộ đếm là 2. M sẽ chờ, không liên tục tự kiểm tra trong vòng lặp busy-spin.
2. Worker 1 gọi `countDown()`: bộ đếm chuyển 2 → 1, M **chưa** được mở khóa vì còn một tín hiệu chưa đến.
3. Worker 2 gọi `countDown()`: bộ đếm chuyển 1 → 0, M đủ điều kiện tiếp tục.
4. Thread N sau đó cũng gọi `await()` trên latch này thì có thể tiếp tục ngay vì mốc đã đạt.

Lưu ý:

- **`countDown()` không đợi `await()`**. Worker có thể báo xong ngay cả khi chưa có thread nào chờ.
- **Nhiều thread cùng `await()`** được phép. Khi count về 0, tất cả đều đủ điều kiện được đánh thức; thứ tự thực tế chạy tiếp do scheduler quyết định.
- `await()` không “nhận” hoặc “tiêu thụ” một permit. Một lần mốc đạt 0 mở đường cho mọi awaiter, khác `Semaphore.acquire()` vốn nhận permit.
- CountDownLatch không tự biết có bao nhiêu task thực tế được submit hoặc chạy. Nếu cấu hình count sai, latch có thể mở quá sớm hoặc không bao giờ mở.

Một mốc về 0 không tương đương “mọi công việc đều thành công”. Nếu worker ném exception nhưng vẫn gọi `countDown()`, latch vẫn mở; caller cần đọc `Future`, trạng thái lỗi hoặc cơ chế riêng để biết kết quả.

## 4. Ví dụ Java 17 chạy độc lập: đợi ba tác vụ rồi tổng hợp

Chương trình tạo ba `Callable<Integer>` chạy trong `ExecutorService`. Mỗi worker báo mốc hoàn tất bằng `countDown()` đặt trong `finally`. Main đợi latch về 0, sau đó dùng `Future.get()` để kiểm tra việc thực thi và lấy giá trị. Vì việc in diễn ra **sau mốc đồng bộ**, stdout không phụ thuộc thứ tự các worker được lập lịch.

Lưu vào tệp `CountDownLatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CountDownLatchDemo {
    public static void main(String[] args) throws Exception {
        int taskCount = 3;
        CountDownLatch completed = new CountDownLatch(taskCount);
        ExecutorService pool = Executors.newFixedThreadPool(taskCount);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= taskCount; i++) {
                final int number = i;
                Callable<Integer> work = () -> {
                    try {
                        return number * 10;
                    } finally {
                        completed.countDown();
                    }
                };
                futures.add(pool.submit(work));
            }

            completed.await();
            System.out.println("All tasks signalled completion.");

            int sum = 0;
            for (Future<Integer> future : futures) {
                // Nếu một task lỗi, get() ném ExecutionException.
                sum += future.get();
            }

            System.out.println("Results count: " + futures.size());
            System.out.println("Total: " + sum);
            System.out.println("Latch count: " + completed.getCount());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac CountDownLatchDemo.java
java CountDownLatchDemo
```

Stdout:

```text
All tasks signalled completion.
Results count: 3
Total: 60
Latch count: 0
```

**Giải thích các điều kiện đúng:**

- Bộ đếm được đặt bằng đúng số công việc dự định báo hiệu.
- Mỗi `Callable` chỉ gọi `completed.countDown()` **một lần**, trong `finally`.
- `finally` chạy khi lời gọi `call()` của task đã bắt đầu đi tới đường kết thúc, kể cả khi phát sinh exception ở phần tính toán.
- Main chỉ in kết quả sau `completed.await()`. Tổng từ ba task là `10 + 20 + 30 = 60`.
- `Future.get()` vẫn quan trọng: latch không lưu kết quả và không mang exception của task. Nếu một task ném lỗi trước khi hoàn thành bình thường, `get()` sẽ ném `ExecutionException`; latch chỉ là tín hiệu mốc.
- `CountDownLatch` không bảo đảm thứ tự worker chạy; chương trình không in từ worker, nên kết quả hiển thị có thứ tự xác định.

**Ranh giới ví dụ:** Nếu `pool.submit(work)` thất bại trước khi nhận một task (chẳng hạn executor bị shutdown hoặc bị từ chối), worker tương ứng sẽ **không có cơ hội** gọi `countDown()`. Khi đó, chờ `await()` vô hạn sẽ không an toàn. Trong ứng dụng thật, cần cơ chế admission/rejection và timeout; phần tiếp theo giải thích cụ thể.

## 5. Vì sao countDown nên nằm trong finally?

Mã không an toàn:

```java
Runnable task = () -> {
    doWork();       // Nếu ném exception thì không chạy dòng tiếp.
    latch.countDown();
};
```

Đây là fragment: `doWork` và `latch` được khai báo ở nơi khác. Nếu `doWork()` ném `RuntimeException`, latch không giảm, khiến các thread đang đợi có nguy cơ chờ mãi.

Mẫu phù hợp hơn:

```java
Runnable task = () -> {
    try {
        doWork();
    } finally {
        latch.countDown();
    }
};
```

Đặt báo hiệu trong `finally` làm rõ hợp đồng: **“Task đã thoát khỏi phần công việc được bao”**, chứ **không nhất thiết là “task thành công”**. Chỉ cần bảo đảm mỗi task thuộc danh sách được tính vào latch thực sự bắt đầu thực thi. Nếu task bị hủy trước lúc bắt đầu, bị từ chối hoặc không được submit, `finally` trong task không chạy; phải xử lý việc báo hiệu/missing task ở tầng điều phối.

Một thiết kế khác là chỉ `countDown()` khi task thành công để mô hình hóa “đã có đủ N thành công”. Khi đó, nếu một task lỗi, việc đợi có thể không bao giờ kết thúc; bắt buộc phải có deadline hoặc đường lỗi riêng. Vì thế với nhu cầu **chờ mọi task kết thúc**, đặt `countDown()` trong `finally` thường rõ ràng và an toàn hơn.

## 6. Hai latch phối hợp thời điểm bắt đầu và kết thúc

Một kỹ thuật kiểm thử concurrency là dùng **hai hoặc ba latch riêng biệt**:

- `ready`: các worker xác nhận đã đến điểm chuẩn bị.
- `start`: main mở một cổng bắt đầu chung bằng một lần `countDown()`.
- `done`: các worker báo đã kết thúc công việc.

Cách này làm giảm sự phụ thuộc vào `Thread.sleep()` trong test. Nó không có nghĩa mọi worker chạy **đồng thời tuyệt đối**; scheduler vẫn quyết định worker nào nhận CPU trước.

Ví dụ minh họa độc lập, lưu tệp `StartTogetherDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class StartTogetherDemo {
    public static void main(String[] args) throws InterruptedException {
        int workers = 3;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        int[] results = new int[workers];

        try {
            for (int i = 0; i < workers; i++) {
                final int index = i;
                pool.execute(() -> {
                    ready.countDown();
                    try {
                        start.await();
                        results[index] = (index + 1) * 10;
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                });
            }

            ready.await();
            start.countDown();
            done.await();

            System.out.println("Results: "
                    + results[0] + "," + results[1] + "," + results[2]);
            System.out.println("All done: " + (done.getCount() == 0));
        } finally {
            start.countDown(); // Mở cổng nếu main bị interrupt.
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        }
    }
}
```

Chạy:

```bash
javac StartTogetherDemo.java
java StartTogetherDemo
```

Stdout trong lần chạy bình thường:

```text
Results: 10,20,30
All done: true
```

Mỗi worker ghi một chỉ số mảng khác nhau, không tranh ghi cùng ô. `done.await()` chỉ trả khi cả ba đã báo mốc, nên main có thể đọc các giá trị đã ghi. Nếu task bị interrupt trước khi ghi, chương trình vẫn có thể mở `done` vì `finally` chạy; trong hệ thống cần phân biệt thành công và lỗi thì phải thêm `Future` hoặc trạng thái kết quả. Demo dùng `shutdownNow()` trong `finally` sau khi đã hoàn thành, không phải cách hủy một khối công việc đang chạy bình thường.

**Một deadlock test dễ gặp:** dùng `newFixedThreadPool(2)` nhưng có ba worker đều phải đợi `start.await()`, rồi main đợi `ready` với count 3. Hai worker đang chờ cổng start, worker thứ ba nằm trong queue nên không thể báo ready, và main không bao giờ mở cổng. Để tránh, không đặt số worker bị chặn ở cổng lớn hơn capacity thread, hoặc thiết kế giao thức không yêu cầu toàn bộ task đồng thời chiếm worker.

## 7. await(timeout): không nên chờ vô hạn khi có lỗi ngoài ý muốn

`await()` không có timeout có thể chờ mãi nếu số lần `countDown()` không đủ. Trong phần mềm có yêu cầu về độ trễ, cân nhắc:

```java
boolean reached = latch.await(2, TimeUnit.SECONDS);
if (!reached) {
    // Deadline đã hết: ghi nhận những công việc còn chưa báo hiệu,
    // yêu cầu hủy, trả lỗi hoặc chuyển sang phương án dự phòng.
    handleTimeout();
}
```

Đây là fragment, `latch` và `handleTimeout()` do ứng dụng định nghĩa.

| Kết quả | Diễn giải |
| --- | --- |
| `true` | Bộ đếm đã về 0 trong thời gian chờ |
| `false` | Hết hạn chờ mà bộ đếm vẫn chưa về 0 |
| `InterruptedException` | Thread đợi bị interrupt trong thao tác chờ |

Nếu thời gian chờ bằng 0 hoặc âm, `await(timeout, unit)` không đợi để bộ đếm thay đổi; nó kiểm tra trạng thái rồi trả kết quả tương ứng, trừ trường hợp thread đã bị interrupt.

**Timeout không tự giảm bộ đếm, không hủy task, không shutdown executor.** Các worker có thể tiếp tục sau khi `await(timeout)` trả `false`. Nếu muốn dừng, caller phải quản lý `Future.cancel(true)`, executor lifecycle, interrupt và cleanup theo hợp đồng riêng. Không giả định cancel tức thời sẽ làm task đang chạy ngừng mọi side effect.

Một ví dụ chắc chắn không phụ thuộc tốc độ máy:

```java
CountDownLatch neverOpened = new CountDownLatch(1);
boolean reached = neverOpened.await(0, TimeUnit.MILLISECONDS);
System.out.println(reached); // false
```

Ở đây không thread nào gọi `countDown()`, nên việc kiểm tra không chờ trả `false`. Đoạn này là fragment cần thêm các `import` phù hợp.

## 8. InterruptedException và hủy lúc đang chờ

`await()` và `await(timeout, unit)` đều là các thao tác **interruptible**. Nếu thread đang chờ bị interrupt, chúng ném `InterruptedException`. Nếu thread đã có interrupt status khi vào `await`, API cũng có thể ném ngay theo hợp đồng.

Trong một method có khả năng truyền exception, cách đơn giản là cho `InterruptedException` lan ra:

```java
void waitForReady(CountDownLatch ready) throws InterruptedException {
    ready.await();
}
```

Nếu cần bắt để xử lý trong method không khai báo checked exception, hãy xử lý interruption theo hợp đồng và thường **khôi phục interrupt flag**:

```java
try {
    ready.await();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return; // Ví dụ method void; dừng xử lý thay vì tiếp tục mù quáng.
}
```

Đây là fragment; `ready` phải được khai báo trước. Khi `await` ném `InterruptedException`, trạng thái interrupt có thể đã được xóa bởi cơ chế kiểm tra interrupt. Việc gọi `interrupt()` lại giúp tầng trên có thể quan sát yêu cầu dừng.

**Đừng tiếp tục dùng dữ liệu như thể mốc đã đạt** sau khi `await` bị interrupt. Tương tự, nếu `await(timeout)` trả `false`, code không nên đọc kết quả đang được worker ghi với giả định chúng đã hoàn tất, trừ khi có cơ chế đồng bộ khác.

## 9. Bảo đảm nhìn thấy dữ liệu: happens-before

Một đặc tính quan trọng của `CountDownLatch` là **memory consistency effects** của nó. Theo hợp đồng API:

> Các hành động trong một thread xảy ra trước lời gọi `countDown()` sẽ *happen-before* các hành động xảy ra sau khi một `await()` tương ứng trả về thành công ở thread khác.

Ví dụ:

```java
final int[] result = new int[1];
CountDownLatch ready = new CountDownLatch(1);

// Thread worker:
result[0] = 42;
ready.countDown();

// Thread đợi, chạy ở thread khác:
ready.await();
System.out.println(result[0]); // Có quan hệ visibility với ghi trước countDown.
```

Đây là ví dụ minh họa các đoạn chạy ở **hai thread khác nhau**, không phải một chương trình độc lập. Nếu worker thật sự ghi `result[0] = 42` rồi gọi `countDown()` và thread khác chờ `await()` thành công trước khi đọc, thay đổi đã được công bố theo quan hệ happens-before.

Lưu ý giới hạn:

- Những ghi dữ liệu **sau** `countDown()` không tự có bảo đảm tương tự từ latch.
- Nếu `await(timeout)` trả `false` hoặc `await` ném `InterruptedException`, không được giả định quan hệ đồng bộ của việc await **thành công**.
- Latch không biến mọi thao tác với một object mutable thành thread-safe. Nếu hai worker đồng thời cập nhật cùng một `HashMap` hoặc tăng một biến bằng phép đọc–sửa–ghi không được bảo vệ, vẫn có data race và lost update.
- Khi cần kết quả của nhiều worker, mỗi worker nên ghi vào vùng không tranh chấp, dùng collection concurrent hoặc synchronization thích hợp; latch chủ yếu đảm bảo **đã đến mốc và công bố các hành động trước mốc**.

Đây là điểm khiến latch hữu ích hơn một vòng `while (flag == false)` trên biến không `volatile`. Vòng lặp đó vừa tốn CPU vừa thiếu bảo đảm visibility khi không có quan hệ đồng bộ phù hợp.

## 10. CountDownLatch không phải Future và không mang lỗi

Một latch có thể về 0 ngay cả khi tất cả worker đã thất bại, miễn là mỗi worker vẫn `countDown()` trong `finally`. Nó **không** trả kết quả từng task, không lưu stack trace và không phân biệt success/failure.

So sánh:

| Công cụ | Chờ cái gì? | Kết quả/lỗi | Khả năng hủy |
| --- | --- | --- | --- |
| `CountDownLatch` | Đủ N tín hiệu | Chỉ bộ đếm và trạng thái mốc | Không có API cancel task |
| `Future<T>` | Một task có kết quả | `get()` trả `T` hoặc báo lỗi/hủy | `cancel(...)` cho task |
| `ExecutorService.invokeAll(...)` | Một nhóm Callable hoàn tất hoặc hết hạn | Danh sách Future từng task | API có thể hủy task chưa hoàn tất trong một số đường |
| `CompletableFuture.allOf(...)` | Nhiều CompletableFuture hoàn tất | Cần xem từng future để lấy kết quả | Semantics cancel cần thiết kế riêng |

Khi bài toán là “đợi N công việc rồi gom kết quả và lỗi”, `Future` hoặc `invokeAll` có thể ít code điều phối hơn. `CountDownLatch` phát huy tác dụng khi sự kiện đợi **không nhất thiết gắn với Future**, hoặc khi nhiều thread cần được giải phóng cùng một mốc.

Ví dụ, nếu dùng `ExecutorService.submit(Callable)` và `Future.get()` cho từng task, việc đợi Future lần lượt cuối cùng vẫn đảm bảo các task được xử lý kết quả; một latch riêng không bắt buộc phải thêm vào nếu không có yêu cầu coordination khác.

## 11. Những nguồn treo chương trình thường gặp

### 11.1. Khởi tạo count sai

```java
CountDownLatch done = new CountDownLatch(4);
// Nhưng chỉ có 3 task sẽ gọi done.countDown() mỗi task một lần.
done.await(); // Có thể chờ mãi.
```

Muốn đợi ba task, nên đặt count = 3. Nếu số task chưa xác định hoặc task sinh thêm task, một latch cố định có thể không phù hợp; cân nhắc `Phaser` hoặc cơ chế quản lý số công việc động.

### 11.2. Quên finally

Nếu task ném exception trước `countDown()`, latch bị thiếu tín hiệu. Dùng `try/finally` trên đường thực thi task và thiết kế đường lỗi rõ ràng.

### 11.3. Task bị từ chối hoặc hủy trước khi bắt đầu

Ví dụ executor gọi `RejectedExecutionHandler` và không nhận một task, hoặc `Future.cancel(...)` hủy task chưa chạy. `finally` bên trong task **không thực thi**. Nếu đã tính nó vào count, latch có thể không mở. Cần ràng buộc chính xác between admission và số lần báo hiệu; có thể chọn giao thức “chốt danh sách task được nhận rồi mới tạo latch”, hoặc dùng cấu trúc khác khi admission thay đổi động.

### 11.4. Thread pool không đủ worker để qua cổng

Dùng 5 task đều chờ cổng start nhưng pool chỉ có 2 worker, trong khi main đợi cả 5 task báo ready trước khi mở cổng. Hai worker giữ thread, ba task còn ở queue: hệ thống deadlock. Không sử dụng latch như một rào khởi động cho số task lớn hơn số worker có thể chạy đồng thời, trừ khi đã đổi giao thức để không bị circular wait.

### 11.5. Báo hiệu quá sớm

`countDown()` trước khi ghi dữ liệu hoặc trước khi kết thúc cập nhật quan trọng khiến awaiter có thể tiếp tục trong lúc trạng thái vẫn đang được sửa. Đặt countDown **sau** những hành động mà awaiter cần quan sát. Trong `finally`, nếu phải dọn tài nguyên và muốn mốc nghĩa là “cleanup xong”, phải sắp xếp sao cho cleanup xảy ra **trước** countDown.

### 11.6. Gọi countDown nhiều lần cho một nhiệm vụ

CountDownLatch không biết nguồn tín hiệu. Một worker gọi `countDown()` hai lần có thể làm latch mở sớm, dù worker khác chưa hoàn tất. Mỗi tín hiệu phải có ownership và nghĩa rõ ràng; count dư sau khi đã về 0 chỉ bị bỏ qua.

### 11.7. Dùng lại latch đã mở

Một latch đã về 0 không thể “đóng lại”. `getCount()` sẽ tiếp tục trả 0; `await()` trên nó không đợi giai đoạn thứ hai. Cần tạo một latch mới cho mốc tiếp theo hoặc chọn cơ chế nhiều pha.

## 12. So sánh với CyclicBarrier, Phaser, Semaphore và Condition

| Synchronizer | Dùng khi nào? | Điểm khác CountDownLatch |
| --- | --- | --- |
| `CountDownLatch` | Chờ một mốc gồm N tín hiệu, một hoặc nhiều thread chờ | One-shot; bên báo tín hiệu không bắt buộc chờ |
| `CyclicBarrier` | Một nhóm thread cùng tới barrier rồi cùng đi tiếp qua **nhiều lượt** | Barrier có thể tái sử dụng; các bên tham gia cùng gọi `await()`; có thể broken |
| `Phaser` | Nhiều pha đồng bộ, số bên tham gia có thể đăng ký/hủy đăng ký | Hỗ trợ tiến pha và số party thay đổi |
| `Semaphore` | Giới hạn số thao tác đồng thời bằng permits | `acquire` lấy permit và `release` trả lại; không phải mốc đếm xuống một lần |
| `Condition` | Chờ một điều kiện trạng thái dưới `Lock` và được báo qua `signal`/`signalAll` | Phải giữ lock tương ứng, thường đợi trong vòng lặp kiểm tra predicate |
| `Thread.join()` | Đợi một `Thread` cụ thể kết thúc | Gắn với vòng đời thread; latch có thể đại diện N sự kiện hoặc task, không cần thread riêng cho mỗi tín hiệu |

Lựa chọn dựa trên hợp đồng nghiệp vụ:

- “Đợi ba bước hoàn tất rồi đi tiếp một lần”: `CountDownLatch(3)`.
- “Mười worker phải gặp nhau ở cuối mỗi vòng tính và tái sử dụng rào”: `CyclicBarrier(10)` hoặc `Phaser`.
- “Chỉ cho phép năm request truy cập tài nguyên cùng lúc”: `Semaphore(5)`.
- “Đợi trạng thái queue chuyển từ rỗng sang có phần tử”: `BlockingQueue` hoặc `Condition` phù hợp hơn một latch chỉ dùng một lần.

`CountDownLatch` **không đếm số lượng công việc đang chạy theo kiểu tăng/giảm tùy ý**. Nó chỉ giảm tới 0, nên không phù hợp thay cho một bộ đếm outstanding tasks có thể tăng trở lại sau khi giai đoạn trước kết thúc.

## 13. Thiết kế đúng khi có timeout và cancellation

Trong hệ thống có deadline, một giao thức chờ có thể cần:

1. Chọn **mốc nào** phải xảy ra trước deadline (mọi task thoát, tối thiểu một số task thành công, hay một phần của pipeline sẵn sàng).
2. Lưu các `Future<?>` nếu cần yêu cầu hủy task thực sự.
3. Dùng `await(timeout, unit)` và xử lý rõ `false`.
4. Khi timeout, yêu cầu `cancel(true)` trên những công việc cần dừng, **nhưng không giả định mọi task dừng tức thì**.
5. Thiết kế tác vụ hỗ trợ interrupt và timeout I/O; sử dụng `try/finally` để cleanup.
6. Nếu cần chứng minh tài nguyên đã giải phóng, dùng một mốc completion/cleanup riêng; Future có thể bị cancelled trước khi task thực sự dừng.
7. Đảm bảo có log/metric về task chậm, số tín hiệu còn thiếu và deadline.

Mẫu fragment:

```java
if (!completed.await(2, TimeUnit.SECONDS)) {
    for (Future<?> future : futures) {
        future.cancel(true);
    }
    reportTimeout(completed.getCount());
}
```

`completed`, `futures` và `reportTimeout` là các thành phần do ứng dụng cung cấp. `getCount()` lúc timeout chỉ là trạng thái quan sát hiện tại; nó có thể thay đổi ngay sau đó do worker khác đang gọi `countDown()`. Không dùng số này làm một giao dịch atomic để tính toán chính xác những tác vụ còn chưa chạy.

**Thận trọng với lỗi phân phối task:** Nếu công việc bị từ chối trước khi tạo Future, không thể yêu cầu hủy nó thông qua Future list. Hợp đồng đếm phải được thiết kế sao cho task chưa được nhận không bị chờ vô hạn.

## 14. Kiểm thử đồng thời bằng CountDownLatch

CountDownLatch được dùng nhiều trong test vì có thể tạo mốc xác định thay vì dựa vào `Thread.sleep()`:

- `ready` bảo đảm worker đã chạy tới điểm chuẩn bị.
- `start` cho phép test điều khiển lúc mở cổng.
- `done` giúp test đợi công việc kết thúc.
- Các assertion được thực hiện **sau** `await()` thành công để tránh đọc kết quả giữa chừng.

Tuy nhiên, test cũng có thể treo nếu setup count sai hoặc pool thiếu worker. Nên dùng `await(timeout)` và fail với thông tin cụ thể:

```java
boolean allReady = ready.await(3, TimeUnit.SECONDS);
if (!allReady) {
    throw new AssertionError("Workers not ready: " + ready.getCount());
}
start.countDown();
```

Đây là fragment; `ready` và `start` được khởi tạo trong test. Khi test thất bại, cần bảo đảm `start.countDown()` trong `finally` hoặc cleanup phù hợp để tránh các worker vẫn mắc kẹt trong lúc bộ test cố shutdown.

CountDownLatch giúp tạo trật tự giữa **các mốc có quan hệ xác định**, nhưng không đảm bảo thứ tự mọi instruction giữa các worker sau khi được giải phóng. Nếu một test cần phát hiện race condition, vẫn cần chạy đủ scenario, kiểm tra invariant và dùng các công cụ hoặc kỹ thuật test concurrency khác.

## 15. Checklist sử dụng CountDownLatch

- [ ] Bộ đếm ban đầu phản ánh **đúng số tín hiệu** mà nghiệp vụ sẽ phát.
- [ ] Mỗi nguồn tín hiệu gọi `countDown()` đúng một lần tại **thời điểm có ý nghĩa**.
- [ ] Với completion của task, dùng `finally` để báo khi task đã bắt đầu và thoát, kể cả khi lỗi.
- [ ] Xử lý task **không được nhận** và task **bị hủy trước khi chạy**; đừng trông chờ `finally` của chúng.
- [ ] Dùng `await(timeout)` khi có deadline; phân biệt kết quả true/false.
- [ ] Xử lý `InterruptedException` và không coi thread bị interrupt là đã đạt mốc.
- [ ] Không đọc trạng thái do worker ghi sau một await thất bại mà không có synchronization khác.
- [ ] Nếu cần biết task thành công/lỗi, kết hợp `Future` hoặc result status.
- [ ] Nếu có cổng start, bảo đảm pool đủ capacity để các worker cần báo ready thực sự có thể bắt đầu.
- [ ] Không tái sử dụng latch đã về 0; tạo latch mới cho giai đoạn mới.
- [ ] Không giữ lock quan trọng trong lúc `await()` nếu worker cần lock đó để hoàn thành.
- [ ] Khi phải đo “đã cleanup hoàn toàn”, đặt countDown sau cleanup hoặc dùng completion signal riêng.

## 16. Câu hỏi tự kiểm tra

**1. `new CountDownLatch(3)` rồi gọi `countDown()` hai lần, `await()` có trả về bình thường không?**  
Chưa, vì bộ đếm còn 1. Lần `countDown()` thứ ba mới đưa nó về 0.

**2. Khi latch về 0, gọi `countDown()` tiếp có làm số đếm âm không?**  
Không, bộ đếm duy trì ở 0.

**3. Nhiều thread có thể cùng đợi một latch không?**  
Có. Khi mốc về 0, tất cả awaiter đều đủ điều kiện đi tiếp, nhưng không có thứ tự chạy tiếp được bảo đảm.

**4. `await(timeout)` trả `false` có hủy các worker không?**  
Không. Nó chỉ báo đã hết thời gian chờ mà count chưa về 0.

**5. Đặt `countDown()` trong `finally` có chứng minh task thành công không?**  
Không. Nó báo thân task đã đi qua đường kết thúc có finally; lỗi vẫn có thể xảy ra.

**6. Một task bị hủy trước khi được worker chạy có thực hiện finally bên trong task không?**  
Không. Vì body chưa bắt đầu, finally đó chưa được thực thi; phải xử lý thiếu tín hiệu ở bên điều phối.

**7. Tại sao đợi `await()` thành công giúp nhìn thấy dữ liệu được ghi trước `countDown()`?**  
Vì CountDownLatch có bảo đảm memory consistency: các hành động trước `countDown()` happen-before các hành động sau `await()` thành công tương ứng.

**8. Khi cần đồng bộ lặp lại theo nhiều vòng, có nên dùng lại CountDownLatch đã về 0 không?**  
Không. Dùng một latch mới cho mỗi lượt hoặc chọn `CyclicBarrier`/`Phaser`.

**9. Vì sao `CountDownLatch(5)` với fixed thread pool 2 và năm task đều chờ start có thể deadlock?**  
Nếu main chờ đủ năm tín hiệu ready trước khi mở start, chỉ hai task đầu giữ worker; ba task còn lại ở queue không thể báo ready, trong khi hai worker đầu không thoát để nhường chỗ.

## Tài liệu tham khảo

- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)
