# Thiết kế cancellation flag, volatile và cleanup trong Java Concurrency

Trong một ứng dụng đa luồng Java, **hủy tác vụ (cancellation)** không đơn giản là “giết một thread”. Khi thread đang xử lý một vòng lặp, chờ dữ liệu từ queue, thực hiện I/O hoặc giữ tài nguyên, việc chấm dứt phải được **phối hợp**: bên yêu cầu hủy công bố ý định, worker nhận biết ý định ấy tại điểm an toàn, dừng nhận việc mới, rồi **giải phóng tài nguyên** trước khi kết thúc.

Ba khái niệm có vai trò khác nhau:

- **Cancellation flag:** biến trạng thái biểu thị đã yêu cầu dừng, thường dùng `volatile boolean` hoặc `AtomicBoolean` để các thread chia sẻ nhận biết thay đổi.
- **Interruption:** `Thread.interrupt()` gửi tín hiệu hợp tác; đặc biệt hữu ích để đánh thức các thao tác chờ có thể bị ngắt như `sleep()`, `wait()`, `BlockingQueue.take()`, `Condition.await()`.
- **Cleanup:** code `finally`, `try-with-resources` hoặc một lifecycle rõ ràng bảo đảm dọn dẹp **khi worker thực sự rời khỏi phần việc**, không phải ngay tại thời điểm bên ngoài gọi `cancel()`.

**Nguyên tắc:** yêu cầu hủy không đồng nghĩa đã hủy xong. Bên gọi cần phân biệt trạng thái “đã gửi yêu cầu”, “worker đã xác nhận”, “worker đã kết thúc” và “tài nguyên đã được dọn”.

## 1. Vì sao Java dùng cooperative cancellation?

Java hiện đại khuyến khích **cooperative cancellation**: thread tự quyết định khi nào có thể dừng mà không làm hỏng invariant của dữ liệu. Một yêu cầu hủy hợp lý cần xác định:

1. **Ai có quyền yêu cầu dừng?** Owner của tác vụ, dịch vụ quản lý worker hoặc thread gọi.
2. **Yêu cầu được lưu ở đâu?** Biến cờ dễ quan sát hoặc trạng thái lifecycle được phối hợp.
3. **Worker kiểm tra khi nào?** Đầu/cuối mỗi vòng, trước khi nhận việc mới, sau khi hoàn tất bước không thể chia nhỏ, hoặc khi một blocking call bị interrupt.
4. **Làm sao đánh thức worker đang chờ?** `interrupt()`, queue/sentinel, condition signal, đóng nguồn dữ liệu… phù hợp với loại thao tác chờ.
5. **Cleanup do ai thực hiện?** Thread sở hữu tài nguyên, trong `finally` hay `try-with-resources`, hoặc thành phần lifecycle có contract rõ ràng.
6. **Làm sao biết đã dừng thật?** `Thread.join()`, `Future.get()`, `ExecutorService.awaitTermination()` hoặc cơ chế hoàn thành tương đương.

Tránh dùng `Thread.stop()`: đây là API cũ không an toàn, có thể làm thread dừng khi đang giữ invariant chưa hoàn tất hoặc đang thao tác với tài nguyên chung. `interrupt()` **không phải** phiên bản an toàn của ép dừng: nó là một yêu cầu hợp tác, và worker vẫn cần thực thi logic chấm dứt.

## 2. Cancellation flag và volatile: công bố ý định dừng

Một cờ đơn hướng tương đối đơn giản:

```java
private volatile boolean cancelRequested;

public void requestCancel() {
    cancelRequested = true;
}
```

Đây là trích đoạn trong class, không phải chương trình độc lập. `volatile` phù hợp nếu chỉ cần **một thread ghi true, nhiều thread đọc**, và không có quy trình chuyển trạng thái phức tạp hơn.

Theo Java Memory Model (JMM), thao tác **ghi volatile** có quan hệ đồng bộ hóa với những lần đọc volatile tương ứng về sau theo thứ tự đồng bộ hóa. Thread đọc cờ trong vòng lặp có cơ sở nhìn thấy thay đổi của thread yêu cầu hủy; compiler/JIT không được coi cờ là hằng bất biến rồi bỏ qua việc đọc cần thiết.

Không có `volatile`, một thread đọc shared boolean không được đồng bộ hóa thích hợp có thể gặp lỗi **visibility**: worker không có bảo đảm thấy thay đổi từ thread kia trong thời gian mong đợi. Chạy thử trên máy cá nhân và “lúc nào cũng dừng” không chứng minh code đúng theo JMM.

Tuy nhiên, `volatile` **không cung cấp** các đặc tính sau:

- Không làm `if (!cancelRequested) performWork()` thành một transaction nguyên tử: cờ có thể chuyển sang true **sau khi kiểm tra** nhưng trước khi hành động bắt đầu.
- Không đánh thức thread đang chặn vô thời hạn trong `queue.take()`, `wait()` hoặc `Condition.await()`. Worker phải có đường thức dậy độc lập.
- Không làm cập nhật `x++`, chuyển trạng thái nhiều field hoặc cleanup đồng thời trở nên nguyên tử.
- Không chứng minh worker **đã kết thúc** hay cleanup hoàn tất chỉ vì `cancelRequested == true`.

Do đó cần xác định nghĩa của cờ: **“đã yêu cầu dừng”**, chứ không phải **“đã dừng xong”**.

## 3. Ví dụ 1 — Volatile flag cho vòng xử lý không chặn

Đây là ví dụ nhỏ tập trung vào visibility. Worker chủ động đọc cờ mỗi vòng; `Thread.onSpinWait()` là một gợi ý cho runtime trong vòng spin, **không** phải primitive chờ có thể bị interrupt và không làm tiết kiệm CPU như blocking queue. Không dùng vòng spin này làm mặc định cho tác vụ production.

Tạo file **`VolatileCancellationDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class VolatileCancellationDemo {
    static final class Worker extends Thread {
        private volatile boolean cancelRequested;
        private final CountDownLatch started = new CountDownLatch(1);
        private final AtomicInteger cleanupCount = new AtomicInteger();

        void requestCancel() {
            cancelRequested = true;
        }

        void awaitStart() throws InterruptedException {
            started.await();
        }

        int cleanupCount() {
            return cleanupCount.get();
        }

        boolean cancellationRequested() {
            return cancelRequested;
        }

        @Override
        public void run() {
            started.countDown();
            try {
                while (!cancelRequested) {
                    // Chỉ để học cách quan sát volatile; tránh busy-spin thực tế.
                    Thread.onSpinWait();
                }
            } finally {
                cleanupCount.incrementAndGet();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Worker worker = new Worker();
        worker.start();
        worker.awaitStart();

        worker.requestCancel();
        worker.join();

        System.out.println("Cancellation requested: "
                + worker.cancellationRequested());
        System.out.println("Cleanup calls: " + worker.cleanupCount());
        System.out.println("Worker alive: " + worker.isAlive());
    }
}
```

```bash
javac VolatileCancellationDemo.java
java VolatileCancellationDemo
```

Kết quả khi không có interrupt từ bên ngoài:

```text
Cancellation requested: true
Cleanup calls: 1
Worker alive: false
```

**Phân tích:** main chờ worker bắt đầu qua `CountDownLatch`, ghi cờ `volatile`, sau đó `join()` đợi worker hoàn tất. Worker thấy yêu cầu dừng trong vòng lặp và đi qua `finally`; cleanup chạy một lần. `join()` mang lại quan hệ *happens-before* từ hành động trong worker tới thread chờ sau khi phát hiện kết thúc, nên main quan sát được kết quả hoàn tất.

Với một vòng có công việc thực, hãy kiểm tra cờ **giữa những đơn vị công việc có thể dừng** (batch, item, bước tính). Không nên bỏ dở một phép cập nhật đang giữ lock hoặc giữa chừng một transaction chỉ vì cờ chuyển sang true; xác định **điểm hủy an toàn** rồi dừng ở đó.

## 4. Vì sao flag không đủ khi worker bị chặn?

Xét:

```java
while (!cancelRequested) {
    String item = queue.take();
    process(item);
}
```

Đây là trích đoạn minh họa: `queue` là `BlockingQueue<String>`, `process()` do ứng dụng định nghĩa, `take()` ném `InterruptedException`. Nếu queue rỗng, worker kẹt ở `take()`; việc thread khác đặt `cancelRequested = true` **không buộc `take()` trả về**. Nó chỉ kiểm tra lại cờ nếu chờ kết thúc theo một đường nào đó.

Các phương án tùy contract:

- Gửi **`worker.interrupt()`** để yêu cầu blocking API hỗ trợ interruption chấm dứt việc chờ.
- Dùng `poll(timeout, unit)` để worker định kỳ trở về kiểm tra cờ, nếu timeout có ý nghĩa với thiết kế.
- Đưa một **sentinel / poison pill** vào queue để báo kết thúc, nếu số lượng consumer và việc đóng queue được kiểm soát đúng.
- Với `Condition.await()`, cập nhật predicate đóng/hủy dưới lock rồi `signalAll()` cho các condition queues bị ảnh hưởng.
- Nếu đợi I/O không hỗ trợ interruption, có thể cần đóng tài nguyên qua cơ chế API riêng hoặc thiết kế timeout cấp I/O.

**Không mặc định mọi lời gọi blocking đều phản ứng với interrupt**. `Thread.interrupt()` không cưỡng bức dừng socket, native call, thư viện ngoài hoặc đoạn tính toán không kiểm tra cờ interrupt. Phải đọc hợp đồng API được sử dụng.

## 5. Interruption: một kênh tín hiệu hợp tác

Mỗi thread có một **interrupt status**. `thread.interrupt()` yêu cầu đặt trạng thái này (và có thể làm các chờ có hỗ trợ interrupt ném `InterruptedException`). Một worker có thể quan sát nó:

```java
if (Thread.currentThread().isInterrupted()) {
    // Thoát tại điểm dừng an toàn.
}
```

Hoặc trong vòng lặp:

```java
while (!Thread.currentThread().isInterrupted()) {
    doUnitOfWork();
}
```

Hai trích đoạn trên không độc lập và cần định nghĩa `doUnitOfWork()`. `isInterrupted()` **không xóa** trạng thái interrupt, còn phương thức static `Thread.interrupted()` **đọc rồi xóa** interrupt status của thread hiện tại. Dùng nhầm `Thread.interrupted()` trong điều kiện vòng lặp có thể làm mất thông tin hủy mà tầng trên cần xử lý.

Các thao tác như `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()`, `Condition.await()` hoặc `Thread.join()` có thể ném `InterruptedException`. Theo hợp đồng thông thường, khi exception được ném vì interrupt, trạng thái interrupt **bị xóa**, nên nếu không ném exception tiếp mà cần giữ tín hiệu, hãy khôi phục:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Thoát hoặc giao trách nhiệm hủy cho tầng trên.
}
```

Đây là trích đoạn, giả định queue đã khai báo. Khôi phục cờ **không** có nghĩa cứ lặp lại blocking call vô hạn: nếu cờ đang được đặt, lần chờ tiếp có thể lập tức ném exception và tạo vòng lặp nóng. Thường nên thoát vòng xử lý hoặc ném tiếp để tầng trên quyết định.

Khi worker dùng nhiều primitive hủy, nên định nghĩa rõ interrupt mang nghĩa gì: yêu cầu **shutdown**, hủy một đơn vị công việc hay đánh thức tạm thời? Không dùng interruption cho mục đích điều khiển tùy tiện nếu nơi khác của chương trình đã sở hữu hợp đồng hủy thread đó.

## 6. Ví dụ 2 — Interrupt đánh thức BlockingQueue.take(), cleanup trong finally

Ví dụ sau tạo worker đang chờ item trên queue rỗng. Main đợi worker bước vào vùng chuẩn bị chờ, sau đó interrupt; worker bắt `InterruptedException`, khôi phục cờ và đi qua `finally` để đóng tài nguyên mô phỏng.

Tạo file **`InterruptibleCleanupDemo.java`**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptibleCleanupDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean closed = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                queue.take();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Worker interrupted");
            } finally {
                closed.set(true);
            }
        }, "queue-worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("Resource closed: " + closed.get());
        System.out.println("Worker alive: " + worker.isAlive());
    }
}
```

```bash
javac InterruptibleCleanupDemo.java
java InterruptibleCleanupDemo
```

Kết quả:

```text
Worker interrupted
Resource closed: true
Worker alive: false
```

`entered.countDown()` xảy ra trước lời gọi `take()`, nên main có thể interrupt **trước khi worker chạm đến take** hoặc **khi nó đang đợi**. Cả hai đều được `take()` xử lý như một đường interruption theo hợp đồng. Thread không dùng `System.exit()` hoặc `stop()`; nó chạy qua `finally`. Sau `join()`, main xác nhận worker đã kết thúc và cleanup flag được đặt.

Trong thực tế, cleanup có thể là đóng stream, trả kết nối về pool hoặc dọn một tài nguyên đã được thread sở hữu. Ví dụ đặt `AtomicBoolean` chỉ để chứng minh **đã đi qua nhánh finally**; nó không đại diện cho một resource bên ngoài.

## 7. Kết hợp volatile flag và interrupt: yêu cầu hủy + đánh thức

Một pattern phổ biến là: `requestCancel()` ghi cờ **trước**, rồi gọi `interrupt()` lên worker. Cờ giữ **ý định dừng**, interrupt đánh thức lời chờ có hỗ trợ. Worker kiểm tra cờ khi thức dậy, hoàn tất cleanup và chấm dứt.

```java
// Trích đoạn trong class quản lý một Thread worker.
private volatile boolean cancelRequested;

public void requestCancel() {
    cancelRequested = true;
    worker.interrupt();
}
```

Trình tự cờ trước → interrupt làm ý định hủy đã được công bố khi worker kiểm tra sau khi thức dậy. Nếu worker chưa vào blocking call, interrupt status cũng có thể được blocking API quan sát. Nhưng nó không bảo đảm task dừng tức thời: worker vẫn có thể đang ở điểm xử lý không thể ngắt, hoặc có đường làm việc không kiểm tra cờ.

### Ví dụ 3 — Service nhỏ tự sở hữu vòng đời worker

Tạo file **`CooperativeServiceDemo.java`**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class CooperativeServiceDemo {
    static final class Service {
        private final BlockingQueue<Integer> queue =
                new LinkedBlockingQueue<>();
        private final CountDownLatch started = new CountDownLatch(1);
        private final AtomicInteger cleanups = new AtomicInteger();
        private volatile boolean cancelRequested;
        private final Thread worker = new Thread(this::runLoop, "service-worker");

        void start() {
            worker.start();
        }

        void awaitStarted() throws InterruptedException {
            started.await();
        }

        void requestCancel() {
            cancelRequested = true;
            worker.interrupt();
        }

        void awaitTermination() throws InterruptedException {
            worker.join();
        }

        int cleanupCalls() {
            return cleanups.get();
        }

        boolean cancelRequested() {
            return cancelRequested;
        }

        boolean isAlive() {
            return worker.isAlive();
        }

        private void runLoop() {
            started.countDown();
            try {
                while (!cancelRequested) {
                    try {
                        Integer item = queue.take();
                        // Nếu hủy đã được yêu cầu trong lúc chờ:
                        if (cancelRequested) {
                            break;
                        }
                        process(item);
                    } catch (InterruptedException e) {
                        if (cancelRequested) {
                            break;
                        }
                        // Contract demo: interrupt bất ngờ cũng kết thúc service.
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            } finally {
                cleanups.incrementAndGet();
            }
        }

        private void process(int item) {
            // Mô phỏng xử lý nhanh; chương trình không cần có item để hủy.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Service service = new Service();
        service.start();
        service.awaitStarted();
        service.requestCancel();
        service.awaitTermination();

        System.out.println("Cancel requested: " + service.cancelRequested());
        System.out.println("Cleanup calls: " + service.cleanupCalls());
        System.out.println("Service alive: " + service.isAlive());
    }
}
```

```bash
javac CooperativeServiceDemo.java
java CooperativeServiceDemo
```

Kết quả:

```text
Cancel requested: true
Cleanup calls: 1
Service alive: false
```

Giao thức service:

1. `Service` là chủ sở hữu thread; API bên ngoài chỉ gọi `requestCancel()` và `awaitTermination()`, không tự truy cập trực tiếp queue/worker.
2. `cancelRequested` là `volatile`, nên thread khác quan sát được ý định dừng theo JMM; `interrupt()` giúp kết thúc `take()` đang chặn.
3. Worker kiểm tra cờ ở đầu vòng và sau khi `take()` trở về, không tiếp tục xử lý item mới sau khi đã phát hiện yêu cầu hủy.
4. Bất kể dừng vì flag hay vì `InterruptedException`, khối `finally` chạy và cập nhật `cleanups`.
5. `join()` cung cấp mốc **đã kết thúc**; chỉ sau đó main kết luận cleanup trong worker đã thực hiện.

**Ranh giới:** worker có thể đã bắt đầu xử lý một item **ngay trước** khi nhận lệnh hủy. Một phép kiểm tra cờ không khóa được toàn bộ thao tác nghiệp vụ tiếp theo; nếu cần đảm bảo “không có tác dụng phụ sau khi API cancel trả về”, phải thiết kế giao thức mạnh hơn như trạng thái atomically guarded, khóa, transaction hoặc đợi hủy hoàn tất. Mẫu này đảm bảo **dừng hợp tác tại điểm kiểm tra**, không phải cắt ngang ngay lập tức.

Với service thực tế, cần quy định `start()` chỉ gọi một lần, `requestCancel()` trước start có hợp lệ hay không, các item còn trong queue được xử lý hay bỏ, và xử lý item quá lâu hoặc I/O không ngắt được. Demo gọi đúng thứ tự `start → awaitStarted → requestCancel → awaitTermination`.

## 8. Cleanup bằng finally, try-with-resources và ownership

Một worker thường sở hữu resource trong khoảng vòng đời xử lý. Quy tắc dễ kiểm chứng:

```java
Resource resource = acquireResource();
try {
    while (!cancelRequested) {
        useResource(resource);
    }
} finally {
    resource.close();
}
```

Đây là mã ý tưởng, không phải chương trình độc lập: `Resource`/`acquireResource()`/`useResource()` cần tự định nghĩa; xử lý checked exception của `close()` tùy API.

Nếu resource triển khai `AutoCloseable`, ưu tiên **try-with-resources** cho ownership từ lúc tạo tới lúc hủy:

```java
try (Resource resource = acquireResource()) {
    while (!cancelRequested) {
        useResource(resource);
    }
}
```

`try-with-resources` gọi `close()` khi ra khỏi khối do hoàn tất, `break`, `return` hoặc exception. Một ngoại lệ ở `close()` có thể được ghi dưới dạng **suppressed exception** nếu đã có exception chính từ thân khối. Việc cleanup cần được thiết kế để không che mất nguyên nhân lỗi và không tạo deadlock khi đang giữ lock.

**Sở hữu rõ ràng:** worker không nên tùy tiện đóng resource đang được thread khác dùng nếu đó là resource chia sẻ. Bên quản lý phải xác định ai có quyền đóng, khi nào đóng, xử lý close lặp ra sao và liệu close có thể chặn không.

### Ví dụ 4 — Try-with-resources vẫn đóng khi worker bị interrupt

Tạo file **`ResourceCleanupDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ResourceCleanupDemo {
    static final class Resource implements AutoCloseable {
        private final AtomicInteger closeCount;

        Resource(AtomicInteger closeCount) {
            this.closeCount = closeCount;
        }

        @Override
        public void close() {
            closeCount.incrementAndGet();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger closeCount = new AtomicInteger();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try (Resource resource = new Resource(closeCount)) {
                entered.countDown();
                Thread.sleep(60_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "resource-worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("Close calls: " + closeCount.get());
        System.out.println("Worker alive: " + worker.isAlive());
    }
}
```

```bash
javac ResourceCleanupDemo.java
java ResourceCleanupDemo
```

Kết quả:

```text
Close calls: 1
Worker alive: false
```

Nếu interrupt đến khi worker đang ngủ thì `sleep()` ném `InterruptedException`. Nếu đến trước `sleep()`, trạng thái interrupt khiến lời ngủ xử lý tín hiệu theo hợp đồng. Dù đường nào, khi rời khỏi khối try-with-resources, `close()` được gọi một lần. Main chờ `join()` rồi mới in kết quả; `60_000` chỉ là thời gian ngủ dự phòng để demo thao tác chặn, không phải thời gian chương trình sẽ phải chờ khi đã interrupt thành công.

**Điểm giới hạn:** `finally`/try-with-resources không bảo vệ trước mọi kiểu sự cố (ví dụ JVM bị dừng đột ngột, process bị kill hoặc mất điện). Cleanup tài nguyên bên ngoài có thể cần timeout, recovery hoặc giao thức đóng riêng.

## 9. Cancellation nhiều lần: dùng AtomicBoolean cho chuyển trạng thái một lần

Nếu nhiều caller có thể đồng thời hủy một service, thao tác `cancelRequested = true` lặp lại thường không nguy hiểm **nếu chỉ là ghi cờ**. Nhưng nếu “lần đầu cancel” còn có tác dụng phụ **phải chạy tối đa một lần** (phát một tín hiệu đóng, cập nhật lifecycle, gửi lời nhắc), kiểm tra rồi đặt cờ bằng hai bước không đủ.

```java
// KHÔNG nguyên tử nếu hai caller gọi đồng thời:
if (!cancelRequested) {
    cancelRequested = true;
    performCancelHook();
}
```

`volatile` không tự làm nguyên tử chuỗi check-then-act này. Dùng `AtomicBoolean.compareAndSet(false, true)` để bảo vệ quyền trở thành caller đầu tiên:

```java
if (cancelRequested.compareAndSet(false, true)) {
    performCancelHook();
}
```

Đây là trích đoạn, với `cancelRequested` là `AtomicBoolean`. Nếu hook có thể ném exception hoặc bị ngắt giữa chừng, **CAS chỉ đảm bảo quyền chạy hook được cấp một lần, không đảm bảo hook thực sự hoàn tất**. Cần chính sách retry/recovery khác khi nghiệp vụ yêu cầu thực hiện đúng một lần và chịu lỗi.

### Ví dụ 5 — Nhiều caller cancel, chỉ một lượt chấp nhận chuyển trạng thái

Tạo file **`IdempotentCancelDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class IdempotentCancelDemo {
    static final class CancellationController {
        private final AtomicBoolean cancelRequested = new AtomicBoolean();
        private final AtomicInteger firstRequests = new AtomicInteger();

        boolean requestCancel() {
            if (cancelRequested.compareAndSet(false, true)) {
                firstRequests.incrementAndGet();
                return true;
            }
            return false;
        }

        boolean isCancellationRequested() {
            return cancelRequested.get();
        }

        int firstRequestCount() {
            return firstRequests.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CancellationController controller = new CancellationController();

        Thread first = new Thread(controller::requestCancel);
        Thread second = new Thread(controller::requestCancel);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Cancel requested: "
                + controller.isCancellationRequested());
        System.out.println("First requests: "
                + controller.firstRequestCount());
    }
}
```

```bash
javac IdempotentCancelDemo.java
java IdempotentCancelDemo
```

Kết quả:

```text
Cancel requested: true
First requests: 1
```

CAS chỉ cho một thread chuyển trạng thái từ false sang true. Bộ đếm minh họa “số lần nhận quyền lần đầu”, **không phải bộ đếm cleanup**. Cleanup phải gắn với lifecycle worker và được chờ hoàn tất riêng nếu caller cần xác nhận.

`AtomicBoolean` cũng có semantics hiển thị bộ nhớ tương đương với các thao tác atomic phù hợp; với yêu cầu chỉ đặt một cờ true đơn hướng và không có hook, `volatile boolean` thường đã đủ và đơn giản hơn.

## 10. Vòng đời hủy: requested, stopping, terminated

Một boolean có thể đủ cho yêu cầu “hãy dừng khi có thể”, nhưng nhiều dịch vụ cần phân biệt:

```text
NEW -> RUNNING -> STOP_REQUESTED -> STOPPING -> TERMINATED
                                  \-> FAILED
```

Đây là sơ đồ **lifecycle logic của dịch vụ**, không phải tên các giá trị trong enum `Thread.State` của JVM. Một thiết kế rõ ràng có thể định nghĩa:

- **RUNNING:** nhận việc và thực hiện bình thường.
- **STOP_REQUESTED:** đã công bố yêu cầu, worker có thể vẫn đang bận.
- **STOPPING:** worker đã vào đường thoát, ngừng nhận việc mới và làm cleanup.
- **TERMINATED:** mọi phần việc thuộc quyền sở hữu worker đã dừng; cleanup có thể xác nhận theo contract.
- **FAILED:** worker thoát do exception; không tự suy thành “hủy thành công”.

Với state machine có nhiều nhánh, `AtomicReference<Lifecycle>` và CAS, monitor hoặc khóa phù hợp dễ bảo đảm chuyển trạng thái hợp lệ hơn việc tạo nhiều boolean rời rạc. Cần tránh các trạng thái vô nghĩa như `terminated=true` trong khi cleanup chưa được hoàn tất, trừ khi contract định nghĩa điều đó rõ ràng.

**Lưu ý:** `Thread.isAlive() == false` sau khi thread từng được start cho biết thread đã kết thúc, nhưng không cho biết nó thành công, bị cancel hay thất bại. Nếu cần phân biệt, lưu kết quả/lỗi và chỉ đọc sau một cơ chế đồng bộ hoàn thành phù hợp.

## 11. Chờ kết thúc: join(), timeout và hủy không hoàn tất

Sau khi gọi `requestCancel()`, bên quản lý có thể đợi worker:

```java
worker.interrupt();
worker.join();
```

Đây là trích đoạn bên ngoài worker; phương thức chứa phải xử lý hoặc khai báo `InterruptedException`. `join()` **không tự yêu cầu dừng** mà chỉ đợi thread đích kết thúc. Nếu worker không bao giờ hợp tác hoặc kẹt trong I/O không ngắt được, `join()` không thời hạn có thể chờ mãi.

Nếu dùng `join(timeoutMillis)`, việc trả về **không đảm bảo đã kết thúc**: có thể là worker hoàn tất hoặc timeout. Phải kiểm tra:

```java
worker.join(1_000);
if (worker.isAlive()) {
    // Chưa thể khẳng định cleanup hoàn tất;
    // báo timeout/chuyển sang chính sách phục hồi.
}
```

Đây là trích đoạn minh họa, cần xử lý `InterruptedException`. Đối với overload `join(long)`, giá trị 0 có nghĩa **chờ vô thời hạn**, không phải “không chờ”. Một hạn chờ có ý nghĩa phải lớn hơn 0.

`join()` sau khi quan sát thread kết thúc còn tạo quan hệ **happens-before** từ các hành động trong worker đến các hành động sau join của thread đợi. Nhờ vậy, bên quản lý có thể đọc dữ liệu hoàn tất/cleanup mà worker đã ghi trước khi kết thúc, miễn không có truy cập tranh chấp ngoài giao thức.

**Không gọi `join()` trên chính thread hiện tại** như một cách “chờ cleanup”; nó sẽ tự chờ chính mình và có thể bị treo. Worker nên thực thi cleanup trong đường thoát; thread quản lý mới chịu trách nhiệm chờ.

## 12. Future.cancel(true) và ExecutorService: cùng bản chất hợp tác

Khi công việc được gửi qua `ExecutorService`, caller thường không giữ trực tiếp `Thread`:

```java
Future<?> future = executor.submit(task);
boolean accepted = future.cancel(true);
```

Đây là trích đoạn, `executor` và `task` đã có. `cancel(true)` yêu cầu hủy `Future`; nếu task đang chạy, implementation có thể cố interrupt thread thực thi. **Nó không bảo đảm code task đã kết thúc hoặc cleanup đã hoàn tất** vào đúng thời điểm `cancel(true)` trả về. `Future.isDone()` cũng có thể true khi trạng thái Future đã canceled mà worker vẫn đang thực hiện cleanup.

Với executor, cần phân biệt:

- `shutdown()`: ngừng nhận task mới nhưng cho task đã nộp được tiếp tục theo contract.
- `shutdownNow()`: cố dừng các task đang chạy (thường bằng interrupt) và trả các task còn trong hàng chờ; không bảo đảm mọi task dừng ngay.
- `awaitTermination(timeout, unit)`: đợi executor thực sự terminated, có kết quả boolean để phân biệt timeout.

Nếu task mở resource, hãy dùng try-with-resources/finally bên trong task; không coi việc Future được đánh dấu canceled là bằng chứng resource đã đóng. Tùy kiến trúc, có thể cần một lifecycle riêng để xác nhận cleanup.

## 13. Ranh giới đúng: không bắt đầu tác dụng phụ sau khi đã request cancel?

Một cờ `volatile` chỉ phản ánh **điều kiện tại thời điểm đọc**. Mã:

```java
if (!cancelRequested) {
    sendOrder();
}
```

Đây là đoạn minh họa, với `sendOrder()` là một tác dụng phụ. Thread cancel có thể đặt cờ true **sau kiểm tra** nhưng **trước `sendOrder()`**. Vì thế không thể tuyên bố “một khi `requestCancel()` trả về, tuyệt đối không có tác dụng phụ mới bắt đầu” nếu chỉ dùng cờ đơn giản.

Nếu hợp đồng cần ranh giới mạnh, có thể phải:

- Bảo vệ đoạn “cho phép bắt đầu tác vụ” và “yêu cầu đóng cửa” bằng cùng lock hoặc một state machine với phép chuyển trạng thái nguyên tử.
- Ngăn nhận thêm việc mới, chờ các việc **đã bắt đầu** hoàn tất rồi mới báo TERMINATED.
- Với hệ thống ngoài JVM, dùng transaction, idempotency key hoặc cơ chế thực thi có đảm bảo của hệ thống đích; khóa JVM không tạo atomicity cho lời gửi mạng.

**Cancellation không phải rollback.** Hủy một thread sau khi đã gửi dữ liệu không tự thu hồi tác dụng phụ bên ngoài.

## 14. Cleanup đúng và những lỗi dễ mắc

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Cờ hủy là boolean bình thường, bị đọc/ghi cạnh tranh | Không có bảo đảm visibility theo JMM. | Dùng `volatile`, `AtomicBoolean` hoặc một lock nhất quán. |
| Đặt flag rồi cho rằng `BlockingQueue.take()` sẽ tự thức | Worker có thể đợi vô hạn. | Interrupt, timeout, sentinel hoặc cơ chế đóng phù hợp. |
| Chỉ gọi `interrupt()` mà worker không kiểm tra/không chờ API interruptible | Có thể không dừng. | Xác định điểm hợp tác; kiểm tra flag/interrupt ở vòng xử lý. |
| Catch `InterruptedException` rồi tiếp tục như bình thường | Bỏ mất yêu cầu hủy; có thể lặp nóng. | Ném tiếp hoặc khôi phục cờ rồi thoát theo contract. |
| Dùng `Thread.interrupted()` tưởng không xóa cờ | Cờ interrupt của thread hiện tại bị xóa ngoài ý muốn. | Dùng `isInterrupted()` để đọc không xóa khi thích hợp. |
| Gọi cleanup ngay tại `requestCancel()` khi worker còn dùng resource | Đóng resource đang sử dụng, race và lỗi nghiệp vụ. | Xác định ownership và cleanup tại điểm worker thoát, đợi hoàn tất. |
| Giữ lock rồi đợi worker `join()` trong khi worker cần lock đó để cleanup | Deadlock. | Không đợi thread trong lúc giữ khóa mà thread đó cần. |
| Không có `finally` hoặc try-with-resources | Resource có thể rò rỉ khi return/exception/interrupt. | Bọc ownership trong cấu trúc cleanup thích hợp. |
| Nhiều caller chạy cancel hook theo `if (!flag) flag=true` | Side effect cancel có thể chạy nhiều lần. | `AtomicBoolean.compareAndSet(false,true)` hoặc lock. |
| Tưởng `Future.cancel(true)` là đã đóng hết resource | Cleanup có thể còn đang chạy. | Có cơ chế xác nhận termination/cleanup riêng. |
| Không quy định tác vụ còn trong queue khi hủy | Có thể mất dữ liệu hoặc xử lý thừa. | Thiết kế drain, discard, retry và báo lỗi rõ theo nghiệp vụ. |
| Dùng `Thread.stop()` | Dừng không an toàn tại trạng thái giữa chừng. | Cooperative cancellation; không sử dụng stop. |

Một số lỗi khó phát hiện hơn:

- **Cleanup ném exception:** `finally` chạy nhưng `close()` có thể thất bại; cần ghi nhận và truyền lỗi phù hợp, không tự tuyên bố “đã đóng chắc chắn”.
- **Cleanup chặn quá lâu:** cần timeout của resource và khả năng quan sát tiến độ; `finally` không bảo đảm kết thúc trong thời gian hữu hạn.
- **Hủy khi task chưa start:** nếu lifecycle cho phép, cancellation state phải được kiểm tra trước khi tạo/chạy worker; không gọi `interrupt()` trên một thread chưa start rồi giả định trạng thái dừng đã hoàn tất.
- **Tài nguyên dùng chung:** không đóng từ một worker nếu những worker khác vẫn cần nó, trừ khi ownership/ref-counting/hợp đồng đóng đã quy định.

## 15. Phương án thay thế theo kiểu tác vụ

| Loại công việc | Cơ chế hủy/đóng thường hợp lý |
|---|---|
| Tính toán CPU có các bước nhỏ | `volatile`/`AtomicBoolean` hoặc kiểm tra interrupt giữa các đơn vị công việc. |
| Chờ queue có thể interrupt | Cờ hủy + `interrupt()`, hoặc sentinel và hợp đồng đóng queue. |
| Chờ `Condition.await()` | Đổi predicate đóng dưới lock, `signalAll()`, xử lý `InterruptedException`. |
| Chờ `CountDownLatch.await()`/`sleep()` | `interrupt()` và xử lý exception theo lifecycle. |
| Task qua ExecutorService | `Future.cancel(true)`, shutdown/awaitTermination, cleanup bên trong task. |
| I/O có API timeout/hủy riêng | Dùng API cụ thể hoặc đóng resource theo ownership; đừng giả định interrupt đủ. |
| Tác vụ cần đóng nhiều resource | `try-with-resources`, `finally`, thứ tự giải phóng và chính sách lỗi. |
| Cập nhật dữ liệu ngoài JVM | Giao thức idempotency/transaction/recovery độc lập với thread cancellation. |

Đối với công việc chờ, một primitive cấp cao có hợp đồng rõ ràng thường dễ dùng đúng hơn busy polling. Đối với công việc CPU, tránh kiểm tra flag ở mỗi phép toán cực nhỏ nếu gây overhead không cần thiết; lựa chọn điểm kiểm tra theo granularity công việc và mục tiêu latency hủy.

## 16. Quy trình thiết kế cancellation an toàn

1. **Định nghĩa hợp đồng:** hủy là best-effort hay phải hoàn tất? Khi requestCancel trả về, đảm bảo điều gì? Có timeout không?
2. **Xác định owner:** ai tạo worker, ai có quyền interrupt, ai đóng resource và ai đợi completion?
3. **Lựa chọn state:** `volatile boolean` cho cờ đơn hướng đơn giản; `AtomicBoolean` nếu cần CAS hoặc nhiều caller; state machine khi có nhiều pha.
4. **Đánh dấu cancellation point:** trước nhận việc mới, giữa đơn vị xử lý, khi chờ interruptible, sau chờ trước khi thực thi item.
5. **Bảo vệ bất biến:** không hủy giữa lúc cập nhật dữ liệu nhiều field nếu không có rollback/transaction hoặc điểm nhất quán.
6. **Lựa chọn wake-up:** interrupt cho API có hỗ trợ, timeout hoặc signal/sentinel nếu hợp đồng đó phù hợp.
7. **Đảm bảo cleanup:** `try/finally` hoặc `try-with-resources`; tránh resource bị đóng đồng thời ngoài ownership.
8. **Truyền kết quả/lỗi:** lưu thất bại và trạng thái dừng theo một giao thức đồng bộ; không tự đánh đồng “thread chết” với “task thành công”.
9. **Chờ completion:** `join()`, `awaitTermination()` hoặc cơ chế hoàn thành riêng; nếu timeout, báo còn chạy thay vì khẳng định đã dừng.
10. **Kiểm thử nhiều lịch xen kẽ:** yêu cầu hủy trước start, ngay trước khi blocking, khi đang blocking, trong lúc xử lý, khi cleanup và khi nhiều caller cùng cancel.
11. **Giám sát liveness:** worker có thể không hợp tác, bị deadlock hoặc mắc I/O không ngắt được. Thiết kế fallback vận hành ở tầng hệ thống nếu cần.
12. **Tách khỏi transaction ngoài tiến trình:** hủy thread không tự rollback một giao dịch đã commit ở nơi khác.

## 17. Tự kiểm tra kiến thức

1. **Vì sao flag hủy thường dùng `volatile`?** Để có bảo đảm hiển thị/thứ tự theo JMM khi nhiều thread đọc/ghi cờ.
2. **`volatile boolean` có thể bảo đảm `if (!cancelled) doWork()` nguyên tử không?** Không; trạng thái có thể đổi sau khi check.
3. **Tại sao đặt cờ không đánh thức `BlockingQueue.take()`?** Vì việc đặt cờ không tác động trực tiếp lên giao thức blocking của queue.
4. **`interrupt()` có giết thread ngay không?** Không; đó là tín hiệu hợp tác, chỉ một số blocking call phản ứng bằng exception.
5. **`Thread.interrupted()` khác `isInterrupted()` thế nào?** Phương thức static đọc và xóa cờ của thread hiện tại; `isInterrupted()` đọc cờ thread cụ thể mà không xóa.
6. **Tại sao cleanup đặt trong `finally`?** Để đi qua đường dọn khi vòng xử lý thoát vì return, break hoặc exception.
7. **Sau `requestCancel()`, có thể báo “worker đã chết” ngay không?** Không; cần chờ một cơ chế termination thực sự.
8. **Vì sao `AtomicBoolean.compareAndSet(false,true)` hữu ích khi nhiều caller cancel?** Vì chỉ một caller được quyền chuyển trạng thái lần đầu một cách nguyên tử.
9. **`Future.cancel(true)` có đảm bảo resource đã đóng không?** Không; trạng thái Future bị cancel không đồng nghĩa cleanup của task đã hoàn tất.
10. **Nếu interrupt đến trước một lần `sleep()` thì sao?** Blocking call có thể phát hiện interrupt status và ném `InterruptedException` ngay theo hợp đồng.
11. **Nếu cleanup cần lock mà caller giữ lock đó trong khi gọi `join()` thì sao?** Có thể deadlock; không chờ worker khi giữ lock mà worker cần.
12. **Nếu tác vụ đã gửi request ra hệ thống khác, cancel có hoàn tác không?** Không; cần transaction, idempotency hoặc bù trừ theo hợp đồng hệ thống ngoài JVM.

**Ghi nhớ:** `volatile`/`AtomicBoolean` **công bố ý định hủy**, `interrupt()` **giúp thoát khỏi những thao tác chờ hỗ trợ interruption**, còn `finally`/`try-with-resources` **dọn tài nguyên khi worker thực sự rời khỏi công việc**. Chỉ kết luận “đã dừng và cleanup xong” sau một cơ chế xác nhận hoàn tất đúng hợp đồng.
