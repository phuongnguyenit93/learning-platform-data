# Chờ thread hoàn tất mà không busy waiting trong Java

Khi một thread khởi động công việc ở thread khác, đôi khi thread gọi phải **đợi kết quả hoặc đợi công việc kết thúc** trước khi thực hiện bước tiếp theo. Cách thường thấy ở người mới là liên tục kiểm tra `isAlive()`, một biến cờ, hoặc trạng thái tác vụ trong vòng lặp. Kiểu chờ đó có thể tiêu tốn CPU, khó kiểm soát độ trễ và dễ mắc lỗi đồng bộ.

Java cung cấp các cơ chế **chờ có phối hợp (blocking wait)** như `Thread.join()`, `CountDownLatch.await()`, `Future.get()` và `ExecutorService.awaitTermination()`. Chúng cho phép thread đang đợi nhường quyền thực thi trong lúc điều kiện chưa đạt, thay vì liên tục chạy vòng lặp thăm dò.

Bài này nằm trong **vòng đời Thread của Java Concurrency nói chung**. Trọng tâm là biết **đợi một thread kết thúc đúng cách**, hiểu visibility, timeout, interruption và biết khi nào nên dùng một primitive khác. Các cơ chế đặc thù của Spring nằm ngoài phạm vi bài.

## 1. Busy waiting là gì và vì sao cần tránh?

*Busy waiting* (spin waiting) là khi một thread liên tục thực hiện phép kiểm tra trong lúc đợi điều kiện thay đổi, thường không nhường CPU một cách có chủ đích:

```java
Thread worker = new Thread(() -> doWork());
worker.start();

while (worker.isAlive()) {
    // Liên tục hỏi trạng thái: không làm việc hữu ích.
}
consumeResult();
```

Đây là **mã minh họa**, giả định `doWork()` và `consumeResult()` tồn tại. Vòng lặp có thể chạy hàng triệu lần trong thời gian worker làm việc. `Thread.isAlive()` cho biết thread đã được start và chưa kết thúc; nó không phải API chờ tối ưu.

Các hệ quả:

- **Tốn CPU:** thread đợi vẫn chạy, cạnh tranh thời gian xử lý với worker và các task khác.
- **Tốn năng lượng:** đặc biệt bất lợi khi chờ I/O, công việc dài hoặc chờ nhiều thread.
- **Dễ tạo độ trễ khó đoán:** `Thread.yield()` không bảo đảm nhường CPU; nhét `Thread.sleep(10)` vào vòng lặp chỉ biến nó thành *polling có khoảng nghỉ*, có thể thêm gần một chu kỳ đợi và vẫn cần xử lý cờ/interruption.
- **Khó xác định đúng điều kiện kết thúc:** một biến boolean bình thường được chia sẻ giữa thread có thể thiếu quan hệ *happens-before*, dẫn đến lỗi visibility. Dùng `volatile` làm cờ có thể giải quyết một phần visibility, nhưng không khiến việc polling trở thành lựa chọn phù hợp cho thời gian chờ dài.
- **Khó xử lý lỗi:** nếu worker ném exception và kết thúc, vòng lặp có thể dừng nhưng không cho biết công việc thành công hay thất bại.

Với nhu cầu “đợi thread A kết thúc”, thay đoạn `while (worker.isAlive())` bằng:

```java
worker.join();
```

`join()` có thể block **thread đang gọi**, không block worker. Khi worker kết thúc, lời gọi hoàn thành. Thread gọi phải sẵn sàng xử lý `InterruptedException` trong lúc chờ.

> Có những thuật toán đồng bộ cấp thấp cố ý dùng spin rất ngắn khi xác suất đợi thấp và chi phí chuyển ngữ cảnh lớn. `Thread.onSpinWait()` (Java 9+) là một gợi ý hiệu năng cho trường hợp đó, **không** thay thế `join()` khi công việc có thể kéo dài. Bài này chọn blocking wait cho việc theo dõi hoàn tất thread thông thường.

## 2. `Thread.join()`: đợi đúng sự kiện thread kết thúc

`join()` là instance method của `Thread`. Khi thread `main` gọi `worker.join()`, main sẽ đợi đến khi worker hoàn thành. Quan hệ cơ bản:

```text
Thread main                                Thread worker
    |                                           |
    |-- worker.start() ------------------------>|
    |                                           | run() thực thi
    |-- worker.join() ---- đợi ..................|
    |                                           | run() kết thúc
    |<-------------- join() trả về -------------|
    | main xử lý kết quả                         |
```

Các overload thường dùng:

| Lời gọi | Ý nghĩa | Giá trị trả về |
| --- | --- | --- |
| `worker.join()` | Đợi đến khi worker kết thúc, trừ khi thread gọi bị interrupt. | `void` |
| `worker.join(long millis)` | Đợi tối đa khoảng thời gian tính bằng millisecond; **`0` nghĩa là chờ không giới hạn**. | `void` |
| `worker.join(long millis, int nanos)` | Đợi với tham số millisecond/nanosecond hợp lệ theo hợp đồng API; có điều chỉnh độ chính xác theo implementation. | `void` |

Các overload trên có thể ném `InterruptedException` nếu **thread đang đợi** bị interrupt. Tham số thời gian không hợp lệ có thể gây `IllegalArgumentException`. Với phiên bản có timeout, việc trả về **không tự nói** thread đã hoàn thành hay hết thời gian. Hãy kiểm tra `worker.isAlive()` nếu cần phân biệt.

**Thứ tự sử dụng thông thường:**

1. Tạo `Thread` với đúng `Runnable`.
2. Gọi `start()` để khởi chạy thread (chỉ một lần).
3. Khi logic thực sự cần đợi, gọi `join()` hoặc `join(timeout)`.
4. Sau khi xác nhận thread đã kết thúc, đọc trạng thái/kết quả đã được worker công bố và xử lý lỗi theo cơ chế đã chọn.

Không gọi `worker.run()` để “chạy thread”: đó chỉ là lời gọi phương thức bình thường trên thread hiện tại. Không gọi `join()` trước khi `start()` rồi coi đó là đã đợi tác vụ: thread chưa từng start không có gì để chờ, nên `join()` có thể trả ngay.

## 3. Ví dụ Java 17+: đợi kết quả bằng `join()`

Tạo tệp `JoinResultDemo.java`:

```java
public final class JoinResultDemo {
    public static void main(String[] args) throws InterruptedException {
        int[] result = {0};

        Thread worker = new Thread(() -> {
            int sum = 0;
            for (int i = 1; i <= 5; i++) {
                sum += i;
            }
            result[0] = sum;
        }, "sum-worker");

        worker.start();
        worker.join();

        System.out.println("Thread finished: " + !worker.isAlive());
        System.out.println("Sum: " + result[0]);
    }
}
```

Chạy:

```bash
javac JoinResultDemo.java
java JoinResultDemo
```

Stdout chính xác:

```text
Thread finished: true
Sum: 15
```

**Phân tích:**

- `worker.start()` bắt đầu thực thi `Runnable` trên thread mới.
- Main gọi `join()` và chờ đến khi worker kết thúc. `join()` không yêu cầu vòng lặp kiểm tra thủ công.
- Worker ghi `result[0] = 15`. Sau khi `join()` hoàn thành vì worker đã kết thúc, main có thể đọc kết quả đó.
- `!worker.isAlive()` là `true` vì thread đã kết thúc và không thể start lần nữa.

`int[] result` chỉ dùng để minh họa **công bố kết quả sau khi join**. Nó không phải cấu trúc thread-safe để nhiều worker cùng cập nhật tùy ý. Nếu có nhiều worker ghi chung một kết quả, cần thêm quy tắc phối hợp, atomic operation, hoặc dùng `Future`/kiểu kết quả phù hợp.

Việc khai báo `main throws InterruptedException` giúp ví dụ ngắn và minh bạch: nếu main bị interrupt khi đang chờ, exception được truyền ra caller. Trong ứng dụng thực tế, luồng điều khiển cần có chính sách hủy và dọn dẹp rõ ràng.

## 4. Vì sao đọc kết quả sau `join()` là an toàn về visibility?

Java Memory Model cung cấp quan hệ *happens-before* liên quan đến vòng đời thread:

- Những hành động xảy ra trước `worker.start()` trong thread gọi **happens-before** các hành động do worker thực hiện sau khi được start.
- Tất cả hành động của worker **happens-before** việc thread khác phát hiện worker đã kết thúc thành công, chẳng hạn qua `worker.join()` hoặc `worker.isAlive()` trả `false`.

Vì thế trong ví dụ:

```text
worker ghi result[0] = 15
              |
              | worker kết thúc
              v
main gọi join() và nhận biết kết thúc
              |
              v
main đọc result[0] == 15
```

Nếu chỉ dùng `Thread.sleep(100)` trên main, **không có** bảo đảm rằng worker đã hoàn tất hoặc rằng lần đọc dựa trên một quan hệ đồng bộ đủ rõ. Máy nhanh/chậm, độ dài công việc và lịch chạy đều có thể thay đổi. Sleep là tạm dừng một khoảng thời gian; join là đồng bộ theo **sự kiện kết thúc**.

**Lưu ý quan trọng:** `join(timeout)` trả về vì hết thời gian khi worker vẫn sống **không** cung cấp bảo đảm “mọi phép ghi của worker đã xuất hiện”. Nếu sau đó `isAlive()` trả về `false`, bạn đã nhận biết thread kết thúc, và quan hệ happens-before của việc kết thúc được thiết lập. Nếu worker còn sống, không được giả định rằng tất cả kết quả đã sẵn sàng; muốn trao đổi kết quả từng phần cần synchronization, `volatile`, lock hoặc cơ chế concurrent phù hợp.

Happens-before bảo đảm **thứ tự quan sát và visibility theo mô hình bộ nhớ**, không bảo đảm thuật toán nghiệp vụ có logic đúng. Ví dụ worker hoàn thành phép tính sai thì join chỉ giúp main quan sát *kết quả sai ấy* một cách nhất quán.

## 5. Timed join: chờ có giới hạn nhưng vẫn kiểm tra kết thúc

Một tác vụ có thể treo do I/O, deadlock hoặc chờ sự kiện không đến. `join(timeout)` giúp thread gọi ngừng **chờ thêm** sau khoảng thời gian quy định, nhưng **không tự dừng worker**.

Ví dụ muốn có kết quả xác định mà không phụ thuộc `sleep()`: dùng `CountDownLatch` giữ worker ở trạng thái chưa kết thúc trong thời gian thử timed join.

Tạo tệp `TimedJoinDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public final class TimedJoinDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finishGate = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                finishGate.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "gated-worker");

        worker.start();
        try {
            worker.join(100);
            System.out.println("Still alive after timeout: "
                    + worker.isAlive());
        } finally {
            finishGate.countDown();
        }

        worker.join();
        System.out.println("Finished after gate opened: "
                + !worker.isAlive());
    }
}
```

Biên dịch/chạy bằng Java 17 trở lên:

```bash
javac TimedJoinDemo.java
java TimedJoinDemo
```

Stdout trong điều kiện chương trình được thực thi bình thường, không có external interruption:

```text
Still alive after timeout: true
Finished after gate opened: true
```

**Tại sao không bị phụ thuộc lịch ngủ của worker?** Worker không thể kết thúc trước khi `finishGate.countDown()` (trừ trường hợp bị external interruption), vì đang chờ latch. Main chỉ mở cổng trong `finally`, sau khi thử `join(100)`. Lần `join()` thứ hai đợi công việc thực sự kết thúc. Không sử dụng vòng lặp busy waiting.

**Cẩn thận với timeout:**

- `join(100)` có đơn vị millisecond và chỉ đưa ra giới hạn thời gian đợi theo hợp đồng API; thời gian tường đo được còn chịu độ trễ scheduling. Đừng diễn giải như một deadline thời gian thực tuyệt đối.
- `join(0)` là chờ vô hạn, **không** có nghĩa là “không chờ”.
- Sau `join(timeout)`, `worker.isAlive()` giúp xác định hiện tại worker còn sống hay không. Một lần kiểm tra `true` có thể trở nên lỗi thời ngay sau đó khi worker hoàn tất; nếu cần kết quả hoàn thành cuối cùng, vẫn phải phối hợp/chờ tiếp.
- Thời gian hết hạn không làm worker chết. Tự quyết định tiếp tục chạy background, yêu cầu hủy bằng interruption, ghi trạng thái “timeout”, hoặc từ bỏ kết quả.
- Nếu main bị interrupt trong timed join, `InterruptedException` được ném; `finally` vẫn mở cổng, tránh giữ worker mãi mãi ở latch do nhánh xử lý lỗi.

Ở các tác vụ không hợp tác với interruption, gọi `worker.interrupt()` cũng **không** bảo đảm dừng tức thì. Đừng dùng `Thread.stop()`; phương thức này không an toàn và đã bị loại khỏi những cách dừng thread được khuyến nghị.

## 6. Interruption: ai bị interrupt khi đang `join()`?

`join()` ném `InterruptedException` khi **thread đang thực hiện join** bị interrupt trong quá trình chờ. Ví dụ thread A gọi `worker.join()`; thread B interrupt A. Kết quả là A rời khỏi lời gọi chờ với exception; worker **không tự bị hủy** chỉ vì A bị interrupt.

Khi `InterruptedException` được ném từ các blocking method thường dùng, **interrupted flag của thread bắt exception bị xóa**. Bạn cần chọn chính sách:

- Ở tầng có thể khai báo `throws InterruptedException`, thường **truyền exception lên trên** để caller xử lý cancellation.
- Ở `Runnable.run()` không khai báo checked exception, thường bắt exception, gọi `Thread.currentThread().interrupt()` để **phục hồi cờ interruption**, rồi thoát tác vụ hoặc làm cleanup.
- Nếu đã được yêu cầu hủy cả worker, quyết định gọi `worker.interrupt()` theo hợp đồng task; không mặc nhiên cho rằng interrupt đồng nghĩa kill.

Ví dụ mảnh mã xử lý trong `Runnable`:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    worker.interrupt();                     // Chỉ khi muốn yêu cầu worker hủy.
    Thread.currentThread().interrupt();     // Phục hồi cờ ở thread đang chờ.
    return;                                 // Rời khỏi task đang chạy.
}
```

Đây là mảnh mã **không chạy độc lập**, giả định `worker` đã khai báo, đang được start và `return` nằm trong phương thức `void`. Lỗi phổ biến là bắt `InterruptedException` rồi tiếp tục một vòng lặp join vô hạn, khiến cancellation không còn hiệu lực.

Nếu ứng dụng cần **đợi worker dọn dẹp sau khi bị hủy**, hãy đưa ra deadline độc lập và quy trình ownership rõ ràng. Không cố chờ vô hạn trong thread đã bị interrupt chỉ để “bảo đảm” tác vụ hoàn tất; worker có thể kẹt hoặc không hợp tác.

## 7. `join()` khác `sleep()`, `wait()` và `yield()`

| API | Đợi điều gì? | Có phải thay thế trực tiếp cho `join()`? |
| --- | --- | --- |
| `Thread.join()` | Một thread cụ thể kết thúc. | Có — là API trực tiếp cho nhu cầu này. |
| `Thread.sleep(duration)` | Khoảng thời gian trôi qua. | **Không**: không biết worker đã kết thúc hay chưa. |
| `Object.wait()` | Notification hoặc sự kiện chờ/timeout trên monitor, kiểm tra predicate bằng giao thức `synchronized`. | Chỉ phù hợp nếu đang tự thiết kế điều kiện chia sẻ; dễ sai hơn `join()` cho nhu cầu chờ kết thúc thread. |
| `Thread.yield()` | Gợi ý scheduler cho thread khác cơ hội chạy. | **Không**: không có bảo đảm nhường CPU, kết thúc task hay visibility. |
| `Thread.onSpinWait()` | Gợi ý tối ưu processor cho vòng spin. | **Không** với tác vụ dài; vẫn là busy waiting nếu gọi trong vòng poll. |
| `LockSupport.park()` | Đợi permit / unparking hoặc interruption/spurious return. | Primitive cấp thấp, cần protocol riêng; không nên thay `join()` khi chỉ chờ thread kết thúc. |

`Object.wait()` khác `join()` về điểm gắn với **điều kiện** và monitor. Nó phải được gọi khi đang giữ monitor tương ứng; thường cần vòng `while (!predicate) wait()` để chịu được *spurious wakeup*. Dùng `wait()/notify()` để tự viết lại cơ chế chờ thread kết thúc có thể mắc lost notification nếu thiết kế sai.

`Thread.join()` trong một số JDK có thể được hiện thực dựa trên wait/notification nội bộ của đối tượng Thread. Đó là **chi tiết triển khai**; code của bạn nên dựa vào hợp đồng công khai `join()`, không tự gọi `notify()` trên đối tượng `Thread` để mong tác vụ kết thúc nhanh hơn.

## 8. Đợi nhiều thread: join từng thread hay CountDownLatch?

Nếu phải đợi một nhóm thread kết thúc, có thể gọi join từng thread:

```java
for (Thread worker : workers) {
    worker.join();
}
```

Đây là mảnh mã giả định `workers` là collection các thread đã start. Các worker vẫn **chạy song song**; join tuần tự chỉ quyết định thứ tự mà main chờ nhận completion. Nếu worker cuối kết thúc trước worker đầu thì main vẫn đợi worker đầu trước, sau đó các join khác có thể trả ngay.

Cần phân biệt hai điều:

- **Tất cả thread đã kết thúc**: join tất cả thread đúng mục tiêu.
- **Một số thao tác logic đã hoàn tất** nhưng thread vẫn tồn tại/chờ tác vụ khác: dùng tín hiệu completion (latch, Future, queue, condition) phù hợp hơn.

### 8.1 CountDownLatch cho nhiều công việc hoàn tất

`CountDownLatch` được khởi tạo với số sự kiện cần chờ. Mỗi công việc gọi `countDown()` khi đã làm xong; phía đợi gọi `await()`. Thread đang đợi **không** cần polling và không bận CPU. Latch là cơ chế **một lần**; bộ đếm giảm đến 0 và không reset để dùng vòng khác.

Tạo tệp `CompletionLatchDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class CompletionLatchDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 3;
        CountDownLatch completed = new CountDownLatch(taskCount);
        AtomicInteger successful = new AtomicInteger();

        Thread[] threads = new Thread[taskCount];
        for (int i = 0; i < taskCount; i++) {
            threads[i] = new Thread(() -> {
                try {
                    successful.incrementAndGet();
                } finally {
                    completed.countDown();
                }
            }, "task-" + i);
            threads[i].start();
        }

        completed.await();
        System.out.println("Completed signals: " + taskCount);
        System.out.println("Successful tasks: " + successful.get());

        // Nếu cần bảo đảm chính các Thread đã TERMINATED,
        // có thể join từng thread sau khi nhận tín hiệu hoàn thành.
        for (Thread thread : threads) {
            thread.join();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CompletionLatchDemo.java
java CompletionLatchDemo
```

Stdout:

```text
Completed signals: 3
Successful tasks: 3
```

**Vì sao dùng `finally`?** Nếu phần thân có exception, latch vẫn giảm, tránh main chờ vô hạn do thiếu tín hiệu. Tuy nhiên `await()` hoàn tất **không chứng minh mọi task thành công**; hãy lưu và đọc lỗi riêng. Trong chương trình này, thao tác tăng một atomic integer không có exception dự kiến, nên `Successful tasks: 3` có thể dự đoán.

Lời gọi `countDown()` diễn ra ngay trước phần cuối của `run()`. `await()` trả về khi bộ đếm đạt 0, nhưng một thread có thể **chưa chuyển hoàn toàn sang TERMINATED** tại thời điểm đó; nếu thực sự phải đợi kết thúc vòng đời thread, join như ví dụ.

Theo Java Memory Model, các hành động trong thread trước `countDown()` happen-before những hành động sau khi `await()` tương ứng trả về thành công. Vì thế main có thể đọc những cập nhật được công bố trước `countDown()` theo đúng quan hệ đồng bộ. Trong ví dụ, `AtomicInteger` còn cho phép tăng đồng thời chính xác.

### 8.2 Timed await

```java
boolean finished = completed.await(2, TimeUnit.SECONDS);
if (!finished) {
    // Hết thời gian chờ; xác định chính sách retry/hủy/báo timeout.
}
```

Đây là mảnh mã minh họa, giả định `completed` và `TimeUnit` đã có. Khác `Thread.join(timeout)` trả `void`, `CountDownLatch.await(timeout, unit)` trả `boolean`: `true` nếu bộ đếm đạt 0, `false` nếu hết hạn. `await()` cũng có thể bị interrupt.

**Không** gọi `countDown()` thay cho việc thực sự hoàn tất công việc. Nếu gọi trước khi ghi kết quả hoặc đóng tài nguyên, bên đợi có thể tiếp tục quá sớm. Ngược lại, nếu một task không bao giờ được start, bộ đếm bị thiếu tín hiệu; phải thiết kế lỗi submit/start và đường cancellation.

## 9. Chờ kết quả: Future thay vì quản lý Thread trực tiếp

Trong phần lớn chương trình xử lý nhiều task, bạn cần **giá trị trả về và exception** của công việc, không cần tên/đối tượng Thread của worker. `ExecutorService.submit()` trả `Future`; `Future.get()` đợi completion **mà không busy waiting** và có cơ chế báo lỗi.

Tạo tệp `FutureCompletionDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureCompletionDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = executor.submit(() -> 6 * 7);

            int value = answer.get();
            System.out.println("Answer: " + value);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac FutureCompletionDemo.java
java FutureCompletionDemo
```

Stdout:

```text
Answer: 42
```

Sự khác nhau cần nắm:

- `Thread.join()` cho biết **thread đã kết thúc**. Nó không trực tiếp trả giá trị, cũng không tự ném lại lỗi mà worker gặp trong `run()`.
- `Future.get()` cho biết **task đã hoàn tất**, trả kết quả hoặc ném `ExecutionException` chứa nguyên nhân lỗi; task có thể hoàn tất trên worker tiếp tục sống và chạy task khác.
- `Future.get(timeout, unit)` có thể ném `TimeoutException`. Hết hạn đợi không tự hủy task; nếu cần hủy, cân nhắc `future.cancel(true)` với chính sách interruption hợp tác.
- `Future.get()` có thể ném `InterruptedException` nếu thread đang đợi bị interrupt và `CancellationException` nếu task bị hủy. Bắt lỗi thích hợp khi nhiệm vụ thật cần phân biệt trạng thái.

Trong ví dụ, `awaitTermination(5, ...) ` chờ **executor kết thúc tất cả worker sau `shutdown()`**, không phải một task bất kỳ. Giá trị `boolean` của `awaitTermination` cho biết executor đã chấm dứt hay hết thời hạn. `shutdownNow()` cố gắng interrupt công việc đang chạy; nó không buộc task không hợp tác dừng ngay.

### 9.1 CompletableFuture và tên `join()` khác nhau

`CompletableFuture<T>.join()` **không phải** `Thread.join()`:

```java
CompletableFuture<Integer> value =
        CompletableFuture.supplyAsync(() -> 21 * 2);
System.out.println(value.join());
```

Mảnh mã này cần import `java.util.concurrent.CompletableFuture`. `CompletableFuture.join()` đợi **completion của future**, trả `T`, và khi tác vụ hoàn thành lỗi sẽ ném unchecked `CompletionException` (hoặc trường hợp hủy là `CancellationException`); nó không khai báo checked `InterruptedException`. Đừng nhầm việc không khai báo checked interruption với cơ chế hủy task hay deadline tự động.

Nếu phải đợi nhiều `CompletableFuture`, `CompletableFuture.allOf(...)` tạo một future hoàn thành khi tất cả future nguồn hoàn thành. Cần kiểm tra lỗi/kết quả của từng future theo mục tiêu nghiệp vụ; không mặc định “allOf hoàn thành” nghĩa mọi công việc thành công.

## 10. Đợi kết thúc toàn bộ executor

Khi đã gọi `shutdown()`, executor ngừng nhận thêm task, song những task đã nhận có thể vẫn hoạt động. Dùng `awaitTermination()` để đợi trạng thái **terminated** của executor:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
            System.err.println("Executor did not terminate");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Mảnh minh họa giả định `executor` là `ExecutorService` và đã import `TimeUnit`. Nó **không bảo đảm** rằng task bị mắc kẹt sẽ dừng: cancellation/interruption là cơ chế hợp tác. Bài toán shutdown còn phải xét worker đang thực hiện I/O không có timeout, giữ lock hoặc chờ task khác.

**Không** gọi `awaitTermination()` trước `shutdown()` rồi mong executor tự dừng: pool vẫn có thể tiếp tục nhận việc và duy trì worker. `Thread.join()` không thay thế quy trình shutdown của executor; worker thread có thể sống lâu hoặc được thay thế, còn lifecycle thuộc executor.

Nếu đang quản lý một vài `Thread` trực tiếp (không dùng executor), bạn tự chịu trách nhiệm yêu cầu chúng kết thúc, truyền tín hiệu hủy phù hợp và join các thread cần thiết.

## 11. Khi chờ làm chương trình bị kẹt

`join()` không tốn CPU theo kiểu polling, nhưng nó **vẫn là blocking** và có thể chờ vô hạn nếu thiết kế phụ thuộc sai.

### 11.1 Chờ chính mình

```java
Thread.currentThread().join();
```

Thread đang chạy không thể tự kết thúc trước khi `join()` trả về, nên nếu không bị interrupt, nó chờ vô hạn. Không gọi join trên current thread.

### 11.2 Vòng phụ thuộc giữa hai thread

Thread A join B, trong khi B lại join A: cả hai có thể chờ mãi nếu không có timeout/interruption. Lỗi này là một dạng deadlock ở mức phụ thuộc completion, không nhất thiết được bộ phát hiện deadlock monitor ghi nhận.

### 11.3 Gọi join khi đang giữ lock mà worker cần

Đây là **mã lỗi minh họa**:

```java
Object lock = new Object();
Thread worker = new Thread(() -> {
    synchronized (lock) {
        // Làm việc cần lock.
    }
});

synchronized (lock) {
    worker.start();
    worker.join(); // main giữ lock, worker không vào được synchronized.
}
```

Giả định `InterruptedException` đã được khai báo/xử lý ở method chứa đoạn này. Main giữ `lock` khi đợi kết thúc; worker cần chính `lock` để hoàn tất. Nếu không có interruption ngoài, cả hai kẹt. `join()` **không giải phóng mọi lock mà thread đang đợi đã giữ**. Cách sửa là không join trong critical section:

```java
Thread worker = new Thread(() -> {
    synchronized (lock) {
        // Làm việc ngắn với dữ liệu chia sẻ.
    }
});

worker.start();
worker.join(); // Không giữ lock cần cho worker.
```

Mảnh sửa giả định `lock` đã khai báo và method xử lý `InterruptedException`. Nếu buộc phải giữ lock để kiểm tra trạng thái, hãy thiết kế protocol với `Condition`/thông báo hoàn tất phù hợp, thay vì tạo vòng chờ lock.

### 11.4 Pool starvation

Một task chạy trong pool nhỏ gọi `future.get()` hoặc `join()` để đợi task khác **cũng đang nằm trong queue của chính pool**, trong khi không còn worker rảnh để chạy task đó. Kết quả là mọi worker bận chờ, còn tác vụ được chờ không bao giờ bắt đầu. Giải pháp nằm ở đồ thị phụ thuộc task, executor capacity, tránh blocking tùy tiện trong worker và cấu trúc phối hợp, không phải đổi một lời gọi busy loop sang `join()`.

### 11.5 Chờ vô hạn khi worker không bao giờ kết thúc

Worker có thể kẹt vì I/O, bug, deadlock hoặc thiếu tín hiệu. `join()` cũng sẽ chờ vô hạn nếu không bị interrupt. Dùng timeout và chính sách xử lý lỗi/hủy khi yêu cầu hệ thống có giới hạn thời gian. Cần quản lý resource và shutdown riêng; timeout của join chỉ giới hạn thời gian **caller chờ**, không phải runtime của worker.

## 12. Chọn primitive chờ theo điều kiện thật

| Bài toán | API ưu tiên | Điều kiện thực sự được chờ |
| --- | --- | --- |
| Đợi một `Thread` do mình tạo kết thúc. | `Thread.join()` / `join(timeout)` | Kết thúc vòng đời thread. |
| Đợi toàn bộ nhóm `Thread` kết thúc. | Join từng thread đã start. | Tất cả thread đã terminated. |
| Đợi N tác vụ/cột mốc phát tín hiệu hoàn tất. | `CountDownLatch.await()` | Bộ đếm tín hiệu bằng 0; thread có thể vẫn sống. |
| Đợi một tác vụ có giá trị trả về/lỗi. | `Future.get()` / `get(timeout)` | Task completion, kết quả hoặc lỗi. |
| Phối hợp kết quả của nhiều tác vụ bất đồng bộ. | `CompletableFuture.allOf(...)` hoặc các combinator. | Completion của các future; kiểm tra lỗi riêng. |
| Đợi executor shutdown xong. | `ExecutorService.awaitTermination()` | Executor chuyển sang terminated. |
| Đợi điều kiện dữ liệu trong vùng lock. | `Condition.await()` cùng vòng kiểm tra predicate, hoặc cấu trúc concurrent phù hợp. | Predicate được thỏa dưới đồng bộ đúng. |
| Đợi phần tử từ queue. | `BlockingQueue.take()` / `poll(timeout)` | Có phần tử (hoặc hết thời hạn), không nhất thiết thread producer kết thúc. |

**Nguyên tắc chọn:** xác định bạn cần đợi **thread kết thúc**, **task xong**, **kết quả sẵn sàng**, **đủ N tín hiệu** hay **executor dừng**. Dùng API gắn với điều kiện đó. Tránh quản lý Thread thủ công chỉ để lấy giá trị của một task mà executor/Future đã hỗ trợ.

## 13. Kiểm thử và quan sát việc chờ

Để kiểm tra code không bận CPU và xử lý completion đúng:

1. **Định nghĩa sự kiện hoàn tất.** Ví dụ worker đã kết thúc, latch về 0, future completed, hay executor terminated. Không lấy “đã ngủ đủ 200 ms” làm tiêu chí.
2. **Kiểm tra đường thành công.** Tạo worker làm việc xác định, start, join, rồi assert kết quả. Ví dụ `JoinResultDemo` cho stdout cố định.
3. **Kiểm tra đường timeout.** Dùng latch giữ worker để tạo điều kiện chờ chắc chắn thay vì phụ thuộc `Thread.sleep()` và may rủi scheduler; sau đó giải phóng mọi thread trong `finally`.
4. **Kiểm tra interruption.** Tạo một thread đang chờ một worker bị chặn có kiểm soát; interrupt thread chờ, xác nhận nó rời blocking wait và vẫn thực hiện cleanup.
5. **Kiểm tra lỗi của task.** `Thread.join()` không ném lại exception từ `Runnable`; nếu muốn thu thập lỗi, kiểm thử `Future.get()` và handler/lưu lỗi riêng.
6. **Quan sát thread dump khi treo.** Thread đang đợi join thường thể hiện trạng thái chờ (`WAITING` hoặc `TIMED_WAITING` tùy kiểu join/JDK). Truy stack trace và dependency của thread mục tiêu; một thread đang `WAITING` không đủ kết luận deadlock.
7. **Đo CPU và thời gian đợi.** Busy loop có thể chiếm một core; blocking wait thường nhường CPU. Tuy vậy nhiều task bị block có thể vẫn gây nghẽn tài nguyên hoặc exhaustion pool.
8. **Luôn thu hồi tài nguyên test.** Worker được giữ bằng latch phải được mở cổng; executor phải shutdown; không để non-daemon thread treo khiến test/JVM không thoát.

Ví dụ anti-pattern trong test:

```java
Thread.sleep(100);
assertEquals(42, result[0]);
```

Đoạn này *giả định* worker hoàn thành trong 100 ms. Trên CI chậm hoặc khi máy bận, test có thể thất bại dù code đúng; trên máy nhanh, test pass cũng không thiết lập quan hệ synchronization rõ. Đổi thành `worker.join(timeout)` rồi xác nhận `!worker.isAlive()` trước khi kiểm tra kết quả, hoặc dùng latch/future cho đúng sự kiện completion.

## 14. Câu hỏi tự kiểm tra

**1.** Vì sao `while(worker.isAlive()) {}` kém hơn `worker.join()` khi chờ tác vụ dài?  
Vòng while liên tục tiêu thụ CPU; join block thread gọi cho đến khi worker kết thúc (hoặc caller bị interrupt).

**2.** `worker.join(500)` trả về có đồng nghĩa worker đã kết thúc?  
Không. Nó có thể trả về vì timeout. Kiểm tra `worker.isAlive()` nếu cần phân biệt.

**3.** Nếu `join()` ném `InterruptedException`, worker có tự dừng không?  
Không. Thread **đang chờ** bị interrupt; worker có thể tiếp tục chạy. Chính sách hủy worker là quyết định riêng.

**4.** Main đọc một giá trị worker đã ghi sau khi `join()` hoàn tất thì có quan hệ happens-before không?  
Có, các hành động của worker happens-before việc thread khác nhận biết worker kết thúc qua join thành công.

**5.** Vì sao không gọi `worker.join()` trong `synchronized(lock)` nếu worker cần lock đó?  
Main giữ lock trong lúc chờ worker, còn worker phải lấy lock mới kết thúc; có thể deadlock.

**6.** Muốn đợi 10 tác vụ executor trả về kết quả/lỗi, nên giữ 10 `Thread` để join không?  
Thông thường không. Giữ `Future` rồi `get()` hoặc dùng CompletableFuture combinator; pool worker có thể xử lý nhiều task.

**7.** `CountDownLatch.await()` trả về có chứng minh tất cả thread phát tín hiệu đã terminated không?  
Không. Nó chỉ chứng minh đủ `countDown()` đã xảy ra; thread có thể còn chạy đoạn mã sau tín hiệu.

**8.** `Thread.sleep(10)` trong vòng kiểm tra trạng thái có biến vòng đó thành phương án đồng bộ đúng không?  
Không. Đó là polling với khoảng nghỉ, vẫn có độ trễ và phải giải quyết visibility, timeout, interruption; nên dùng primitive chờ đúng điều kiện.

**9.** `CompletableFuture.join()` và `Thread.join()` có giống nhau không?  
Không. Một bên đợi completion của Future và có thể trả kết quả/unchecked exception, bên còn lại đợi vòng đời Thread và trả `void`.

**10.** `awaitTermination(timeout)` khi executor chưa shutdown có bảo đảm pool dừng không?  
Không. Cần gọi `shutdown()`/`shutdownNow()` theo chính sách; awaitTermination chỉ chờ điều kiện terminated.

**Ghi nhớ:** Khi cần đợi một thread hoàn tất, **`Thread.join()` là lựa chọn trực tiếp**. Chọn timed join kèm kiểm tra trạng thái khi có deadline; xử lý `InterruptedException` rõ ràng; không chờ khi đang giữ lock worker cần. Khi bài toán đòi **task result, N tín hiệu hoặc shutdown**, hãy chuyển sang Future, CountDownLatch hoặc ExecutorService tương ứng. Blocking wait giúp tránh lãng phí CPU, còn an toàn dữ liệu và khả năng hoàn thành vẫn phải được thiết kế riêng.