# Blocking operation trong Fork/Join và ManagedBlocker

## 1. Bài toán: worker Fork/Join phải đợi dữ liệu hoặc tài nguyên

`ForkJoinPool` được thiết kế chủ yếu cho công việc **chia để trị (divide-and-conquer)**: tách một bài toán lớn thành các `ForkJoinTask` nhỏ, worker thực thi task và có thể **work-stealing** lấy công việc từ hàng đợi của worker khác. Cơ chế này phát huy hiệu quả khi các task chủ yếu **tính toán và có khả năng tiến triển**, thay vì phải chờ một tài nguyên bên ngoài quá lâu.

Nhưng nhiều thuật toán thực tế vẫn cần chờ:

- `BlockingQueue.take()` đợi dữ liệu từ producer.
- `CountDownLatch.await()` đợi tín hiệu kết thúc một giai đoạn.
- Đợi lock, semaphore, socket, file hoặc một dịch vụ bên ngoài.
- `Future.get()` đợi kết quả do một hệ thống khác tạo.
- Một callback hoàn thành bất đồng bộ mà thread hiện tại quyết định chờ.

Nếu nhiều Fork/Join worker bị chặn ở các điểm này, **parallelism hữu ích giảm**. Các task khác có thể đang nằm trong queue nhưng không còn worker rảnh để chạy. Trường hợp xấu là **thread starvation deadlock**: những worker hiện có đang đợi kết quả của các task mà chính pool ấy chưa thể thực thi.

JDK cung cấp `ForkJoinPool.ManagedBlocker` và `ForkJoinPool.managedBlock(...)` để **thông báo cho ForkJoinPool về một thao tác chờ có thể gây block**. Khi được gọi trong ForkJoin worker, pool có thể **cố gắng bù đắp worker** nhằm duy trì mức song song mục tiêu trong lúc worker hiện tại bị chặn. Đây là cơ chế **best effort**, không bảo đảm có worker bổ sung trong mọi cấu hình/tình huống.

Bài này thuộc **Java concurrency nói chung**. Ví dụ dùng **Java 17+**, chỉ có API JDK và không phụ thuộc Spring.

## 2. Phân biệt work-stealing, fork/join waiting và blocking bên ngoài

### 2.1. Work-stealing khi task tiếp tục tiến triển

Một phép tính đệ quy có thể tạo hai nhánh bằng `fork()`, tự tính một nhánh, rồi `join()` nhánh kia. Khi chờ một `ForkJoinTask` trong cùng cơ chế Fork/Join, worker có các kỹ thuật phối hợp hỗ trợ tiến triển, ví dụ giúp thực thi task còn sẵn sàng.

Sơ đồ:

```text
Bài toán tính tổng
        |
        v
   tách left / right
        |
        +-- left.fork() --------> task có thể chạy bởi worker
        |
        +-- right.compute() ---> worker hiện tại tiếp tục tính
        |
        +-- left.join() -------> nhận kết quả nhánh trái
        |
        v
      gộp kết quả
```

Sự phối hợp này không có nghĩa `join()` luôn không bao giờ chờ. Nhưng nó cho thấy `ForkJoinTask.join()` được thiết kế trong mô hình Fork/Join và **khác về bản chất** với việc worker gọi một I/O operation tùy ý.

### 2.2. Blocking operation ngoài mô hình Fork/Join

Giả sử worker đang thực thi:

```java
String payload = inbox.take();
```

Đây là snippet, giả sử `inbox` đã được khai báo là `BlockingQueue<String>`. Khi inbox rỗng, thread có thể bị chặn trong `take()`. Nó không còn chủ động tìm task khác trong ForkJoinPool để thực thi. Pool cũng không nhất thiết biết thao tác nào đang giữ worker bận và thời gian chờ sẽ kéo dài bao lâu.

**Hệ quả:** một `ForkJoinPool` có `parallelism = 2` có thể có hai worker đang đợi ngoại vi và nhiều task sẵn sàng chưa được chạy. `parallelism` biểu diễn mức song song mục tiêu, **không phải một bảo đảm tuyệt đối** rằng số task tính toán hữu ích luôn được duy trì.

### 2.3. Managed blocking

Thay vì gọi `take()` trực tiếp, ta triển khai `ManagedBlocker` mô tả:

1. **`isReleasable()`**: kiểm tra **nhanh, không gây blocking dài** xem việc chờ đã không còn cần thiết hay chưa.
2. **`block()`**: nếu chưa thỏa, thực hiện thao tác có thể block và trả về cho biết còn cần chờ thêm không.
3. **`ForkJoinPool.managedBlock(blocker)`**: điều phối việc lặp kiểm tra/chờ và, khi đang trong một ForkJoin worker, có thể bổ sung worker nếu cần và nếu pool cho phép.

Về logic, pool có thể hiểu:

```text
Nếu blocker.isReleasable() == true:
    Xong, không cần chờ

Nếu chưa:
    Pool có thể chuẩn bị compensation
    Gọi blocker.block()
    Nếu chưa xong thì kiểm tra lại
```

Đây là **mô tả luồng logic**, không phải lời cam kết về số lần gọi, trình tự nội bộ hoặc thời điểm pool tạo worker mới. Một `ManagedBlocker` phải chịu được việc hai phương thức được gọi nhiều lần trong chu trình xử lý.

## 3. Hợp đồng `ForkJoinPool.ManagedBlocker`

Interface chuẩn:

```java
public interface ManagedBlocker {
    boolean block() throws InterruptedException;
    boolean isReleasable();
}
```

Đây là **chữ ký rút gọn** của interface lồng trong `ForkJoinPool`, không phải file riêng để biên dịch.

### `isReleasable()`

- Trả `true` nếu **không cần chặn thêm** để hoàn thành yêu cầu của blocker.
- Nên nhanh, không chờ dài. Có thể thử lấy dữ liệu bằng `queue.poll()` không timeout, thử một điều kiện đã được đồng bộ hoặc kiểm tra một flag an toàn.
- Có thể được gọi nhiều lần, cả trước và sau `block()`. Tránh side effect không thể lặp lại; nếu nó thực sự lấy được phần tử khỏi queue, phải **lưu phần tử vào blocker** để không làm mất dữ liệu.

### `block()`

- Có thể chặn, ví dụ `queue.take()` hoặc `latch.await()`.
- Trả `true` nếu không cần thêm blocking; `false` nếu cần thử lại. JDK có thể tiếp tục kiểm tra `isReleasable()` và gọi `block()` thêm.
- Có thể ném `InterruptedException` khi thao tác chờ hỗ trợ interrupt. Caller phải xử lý hoặc truyền tiếp theo hợp đồng của task.
- Không được dựa vào giả định `block()` chỉ chạy một lần trong mọi implementation.

### `managedBlock(blocker)`

- Đây là **phương thức static**: `ForkJoinPool.managedBlock(blocker)`.
- Với **ForkJoin worker thread**, pool có thể cố gắng kích hoạt worker bù để duy trì parallelism.
- Khi thread gọi **không phải** ForkJoin worker, API vẫn thực hiện giao thức `isReleasable()/block()` nhưng **không có tác dụng bù worker của một pool liên quan**.
- Nếu không thể cấp thêm worker theo giới hạn/cấu hình hoặc pool cạn tài nguyên, khả năng compensation không được đảm bảo; một số tình huống có thể dẫn đến lỗi như `RejectedExecutionException` tùy implementation/cấu hình.
- Không nên xem ManagedBlocker như một transaction, một lock hay cơ chế tự hủy công việc.

**Quan trọng:** `ManagedBlocker` không tạo ra dữ liệu đang thiếu. Nếu một task đợi tín hiệu mà không ai có khả năng phát, mọi worker bổ sung cũng không làm điều kiện tự đúng.

## 4. Ví dụ Java 17+ hoàn chỉnh: ManagedBlocker cho BlockingQueue

Ta dùng một `BlockingQueue<String>` và một `CountDownLatch` để biết khi nào worker đã bước tới chỗ thực hiện thao tác chờ. Main cung cấp dữ liệu sau tín hiệu đó. Không dùng `Thread.sleep()` để đoán rằng thread đã bắt đầu.

Tạo file `ManagedQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class ManagedQueueDemo {
    private static final class QueueTaker
            implements ForkJoinPool.ManagedBlocker {
        private final BlockingQueue<String> queue;
        private final CountDownLatch aboutToWait;
        private String item;

        QueueTaker(BlockingQueue<String> queue,
                   CountDownLatch aboutToWait) {
            this.queue = queue;
            this.aboutToWait = aboutToWait;
        }

        @Override
        public boolean isReleasable() {
            if (item != null) {
                return true;
            }
            item = queue.poll(); // Thử không blocking.
            return item != null;
        }

        @Override
        public boolean block() throws InterruptedException {
            if (item == null) {
                aboutToWait.countDown();
                item = queue.take(); // Có thể chờ dữ liệu.
            }
            return true;
        }

        String result() {
            return item;
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch aboutToWait = new CountDownLatch(1);
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            Future<String> consumer = pool.submit(() -> {
                QueueTaker taker = new QueueTaker(queue, aboutToWait);
                ForkJoinPool.managedBlock(taker);
                return taker.result();
            });

            aboutToWait.await();
            queue.put("payload");

            System.out.println("Received: " + consumer.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ManagedQueueDemo.java
java ManagedQueueDemo
```

Đầu ra khi không có interrupt từ ngoài:

```text
Received: payload
```

**Vì sao chương trình đúng?**

1. `ForkJoinPool` nhận một Callable; task được chạy trên một worker của pool.
2. `QueueTaker.isReleasable()` thử `queue.poll()` ngay. Queue ban đầu rỗng, nên cần chờ.
3. `block()` báo qua `aboutToWait.countDown()` rồi gọi `queue.take()`. Main chỉ đưa dữ liệu **sau** khi thấy tín hiệu.
4. `ForkJoinPool.managedBlock(taker)` cho pool biết worker có thể bị chặn; pool **có thể** bù worker nếu còn công việc và cấu hình cho phép. Ví dụ không phụ thuộc compensation để tránh deadlock, vì **main thread độc lập** là producer.
5. Sau khi nhận `payload`, `block()` trả `true`. Future hoàn tất với chuỗi đó; `consumer.get()` công bố kết quả cho main.
6. `shutdown()` bắt đầu orderly shutdown. Không gọi `shutdownNow()` tùy tiện sau khi đã nhận kết quả.

**Chi tiết ownership:** phần tử lấy ra trong `isReleasable()` hoặc `block()` đều được lưu trong `item`. Nếu chỉ dùng `queue.poll() != null` rồi gọi `take()`, ta có thể **vô tình tiêu thụ phần tử đầu** mà không lưu, sau đó chờ phần tử thứ hai. Lỗi này rất phổ biến khi triển khai ManagedBlocker cho queue.

### Phân biệt thông báo và việc bù worker thực tế

`managedBlock` cho pool **cơ hội** compensation, không cam kết chương trình sẽ tạo chính xác một worker mới. Vì demo này chỉ có một task consumer và producer nằm ở main, việc có worker bù hay không **không thay đổi đầu ra**. Điều quan trọng để học là contract, không phải đoán số worker thông qua thread name hoặc timing.

## 5. Java 17+: chia để trị thuần CPU không cần ManagedBlocker

Để so sánh, một task tính toán có thể `fork` một nhánh, tính nhánh còn lại và `join` kết quả. Tạo file `ForkJoinSum.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSum {
    private static final class SumTask extends RecursiveTask<Long> {
        private final long[] data;
        private final int from;
        private final int to;

        SumTask(long[] data, int from, int to) {
            this.data = data;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= 4) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += data[i];
                }
                return sum;
            }

            int mid = (from + to) / 2;
            SumTask left = new SumTask(data, from, mid);
            SumTask right = new SumTask(data, mid, to);

            left.fork();
            long rightValue = right.compute();
            long leftValue = left.join();
            return leftValue + rightValue;
        }
    }

    public static void main(String[] args) {
        long[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println("Sum: " +
                    pool.invoke(new SumTask(numbers, 0, numbers.length)));
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ForkJoinSum.java
java ForkJoinSum
```

Đầu ra:

```text
Sum: 36
```

Mẫu `fork → compute → join` tận dụng đặc tính Fork/Join. `left.join()` **không tương đương** một thao tác I/O tùy ý; pool có cơ chế đặc thù để hỗ trợ tiến triển của `ForkJoinTask`. **Không cần** bao một `ForkJoinTask.join()` thông thường vào `ManagedBlocker` chỉ vì thấy chữ “đợi”.

Ngược lại, nếu bên trong `compute()` gọi trực tiếp `socket.read()`, `BlockingQueue.take()` hay một thao tác ngoại vi dài, worker có thể đứng chờ mà không giúp thực thi các nhánh khác. Hãy cân nhắc đổi kiến trúc hoặc dùng managed blocking khi thực sự phù hợp.

## 6. Java 17+: ManagedBlocker chờ CountDownLatch

`CountDownLatch.await()` là thao tác blocking interruptible. Có thể xây dựng blocker dựa trên việc count đã về 0 hay chưa.

Tạo file `ManagedLatchDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class ManagedLatchDemo {
    private static final class LatchBlocker
            implements ForkJoinPool.ManagedBlocker {
        private final CountDownLatch latch;

        LatchBlocker(CountDownLatch latch) {
            this.latch = latch;
        }

        @Override
        public boolean isReleasable() {
            return latch.getCount() == 0L;
        }

        @Override
        public boolean block() throws InterruptedException {
            latch.await();
            return true;
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch entered = new CountDownLatch(1);

        try {
            Future<String> waiting = pool.submit(() -> {
                entered.countDown();
                ForkJoinPool.managedBlock(new LatchBlocker(gate));
                return "released";
            });

            entered.await();
            gate.countDown(); // Main độc lập giải phóng điều kiện.

            System.out.println("Result: " + waiting.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ManagedLatchDemo.java
java ManagedLatchDemo
```

Đầu ra:

```text
Result: released
```

`isReleasable` đọc `CountDownLatch.getCount()` để thử xem đã có tín hiệu chưa. Khi latch chưa mở, `block` có thể đợi bằng `await()`. Main đóng vai trò phát tín hiệu nên không cần pool có một worker dư mới bảo đảm tiến triển.

**Không suy ra rằng một task trong cùng pool luôn có thể giải phóng latch** nếu mọi worker đều đang chờ và compensation đã bị hạn chế. Thiết kế đúng phải có nguồn phát tín hiệu có khả năng chạy.

## 7. Timeout và interrupt khi ManagedBlocker phải chờ

`ForkJoinPool.managedBlock(...)` khai báo `throws InterruptedException` vì `block()` có thể đợi ở một API interruptible. Nếu caller hủy task hoặc worker nhận interrupt:

- `BlockingQueue.take()` và `CountDownLatch.await()` có thể ném `InterruptedException`.
- Task phải **truyền tiếp**, hoặc bắt exception, **khôi phục interrupt status** nếu không truyền tiếp, rồi dừng phù hợp.
- Phải giải phóng lock, permit, stream hoặc những tài nguyên đã lấy được trong `finally`.
- `managedBlock` không tự tạo timeout. Muốn chờ có hạn, dùng **blocking operation có timeout**, ví dụ `queue.poll(remaining, unit)`, đồng thời thiết kế `isReleasable`/`block` sao cho biết khi nào **hết hạn**.
- `Future.cancel(true)` là yêu cầu hủy, không phải bảo đảm task đã dừng. Nếu task không kiểm tra interrupt, pool vẫn có thể bị giữ lâu.

### Ví dụ Java 17+: ManagedBlocker với timeout

Tạo file `TimedManagedQueue.java`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedManagedQueue {
    private static final class TimedTaker
            implements ForkJoinPool.ManagedBlocker {
        private final BlockingQueue<String> queue;
        private final long started = System.nanoTime();
        private final long budgetNanos;
        private boolean done;
        private String item;

        TimedTaker(BlockingQueue<String> queue, long timeoutMillis) {
            this.queue = queue;
            this.budgetNanos = TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        }

        @Override
        public boolean isReleasable() {
            if (done) {
                return true;
            }
            item = queue.poll();
            if (item != null) {
                done = true;
            } else if (System.nanoTime() - started >= budgetNanos) {
                done = true;
            }
            return done;
        }

        @Override
        public boolean block() throws InterruptedException {
            if (isReleasable()) {
                return true;
            }
            long elapsed = System.nanoTime() - started;
            long remaining = budgetNanos - elapsed;
            if (remaining > 0L) {
                item = queue.poll(remaining, TimeUnit.NANOSECONDS);
            }
            done = true;
            return true;
        }

        String result() {
            return item;
        }
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        ForkJoinPool pool = new ForkJoinPool(1);
        try {
            Future<String> answer = pool.submit(() -> {
                TimedTaker blocker = new TimedTaker(queue, 30);
                ForkJoinPool.managedBlock(blocker);
                return blocker.result() == null ? "timeout" : blocker.result();
            });
            System.out.println("Result: " + answer.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac TimedManagedQueue.java
java TimedManagedQueue
```

Đầu ra khi không có thread nào khác ghi vào queue:

```text
Result: timeout
```

**Điểm thiết kế của timeout:**

1. `started = System.nanoTime()` là mốc đo thời gian trôi qua trong JVM; không dùng `currentTimeMillis()` như đồng hồ deadline tương đối.
2. `isReleasable()` thử `poll()` không chờ rồi kiểm tra ngân sách. Nếu thời gian hết, nó xác nhận **không cần block thêm**, dù `item == null`.
3. `block()` tính **thời gian còn lại**, không reset timeout sau mỗi lượt gọi. Nó dùng `poll(remaining, NANOSECONDS)` thay cho `take()` vô hạn.
4. Kết quả null là “không có phần tử trong thời hạn được cấp”, không phải chứng cứ producer đã chết.
5. Demo không có producer nên luôn trả `timeout`; thời điểm thức dậy thực tế còn phụ thuộc scheduler và độ phân giải timer, không cam kết chính xác 30 ms.

**Giới hạn phạm vi:** demo này dùng timeout dương nhỏ. Khi triển khai utility tổng quát, cần xử lý timeout âm, ngân sách quá lớn, chuyển đổi đơn vị và tràn phép tính. Cân nhắc `Duration`/`TimeUnit` cùng hợp đồng giới hạn rõ ràng.

## 8. Vì sao không có compensation tuyệt đối?

`ManagedBlocker` giúp ForkJoinPool **có thông tin** để cố duy trì parallelism, nhưng không thể hứa “mỗi worker blocked sẽ có một worker mới”.

Những giới hạn thực tế:

- Cấu hình pool và **giới hạn tổng worker/spare thread**.
- Số thread đang hoạt động, số worker blocked, tài nguyên hệ điều hành và tình trạng JVM.
- Khả năng tạo thread, chính sách thread factory, exceptional conditions.
- Task đang chờ **một điều kiện không thể được tạo ra** dù có thêm worker.
- Deadlock do lock order/ownership hoặc một vòng phụ thuộc I/O, chứ không đơn thuần thiếu worker.
- Những điểm chặn **không** được bao trong `managedBlock` khiến pool không có cùng thông tin để quản lý.
- Pool có thể từ chối việc cần thiết để bù trong một số hoàn cảnh, ví dụ quá giới hạn spare threads tùy cấu hình.

**Không viết thuật toán chỉ đúng khi compensation bắt buộc xảy ra.** Cấu trúc lành mạnh phải có luồng phát dữ liệu/tín hiệu độc lập hoặc cơ chế phụ thuộc có thể tiến triển và có đường timeout/cancellation.

### Common pool và pool riêng

`ForkJoinPool.commonPool()` là pool dùng chung của JVM cho nhiều kiểu tác vụ, bao gồm một số thao tác parallel streams và các tác vụ bất đồng bộ mặc định. Dùng blocking operation dài trong common pool có thể ảnh hưởng **những công việc không liên quan**.

Nếu có workload blocking thường xuyên, cân nhắc executor dành riêng cho I/O, `ThreadPoolExecutor` có giới hạn phù hợp hoặc ở Java 21+ có thể cân nhắc virtual threads cho nhiều tác vụ chờ I/O. `ManagedBlocker` là một giải pháp khi **cần tích hợp chờ trong một thuật toán Fork/Join đang có**, không phải lý do để đặt mọi network call trong common pool.

## 9. Một nguy cơ: nhiều task chờ nhau trong cùng pool

Giả sử pool có một worker:

```text
Worker duy nhất:
   chạy Task A
   Task A chờ kết quả Task B
   Task B vẫn ở queue của chính pool
   => không ai thực thi Task B
```

Nếu A dùng `Future.get()` trên một tác vụ không có cơ chế tiến triển phù hợp, có thể gây **thread starvation deadlock**. Nếu A đang giữ một lock mà B cần, **kể cả thêm worker** cũng không tự giải quyết vòng chờ.

Cách tránh:

1. Không giữ worker chỉ để chờ một task khác cùng pool nếu có cách compose kết quả mà không block.
2. Với các bài toán Fork/Join chuẩn, dùng `RecursiveTask`/`RecursiveAction` và `fork/join` đúng mẫu.
3. Với dependency bất đồng bộ, xem xét `CompletableFuture` hoặc `ExecutorCompletionService`, tránh `get()` bừa bãi trong worker.
4. Đặt timeout khi phụ thuộc có thể không hoàn thành; phản hồi interrupt/cancellation.
5. Tránh khóa chéo hoặc giữ lock trong thời gian chờ tác vụ bên ngoài.
6. Đánh giá kích thước pool, độ dài task và hàng đợi nhưng không coi tăng parallelism là cách sửa logic deadlock.

**Phân biệt rất quan trọng:** `ForkJoinTask.join()` có thể tận dụng sự hỗ trợ của Fork/Join runtime; `Future.get()` tùy ý, `BlockingQueue.take()` hoặc I/O thường không thể giả định được runtime giúp như vậy. Nếu cần chờ ngoại vi, `ManagedBlocker` là cơ chế khai báo chờ chuyên biệt.

## 10. ManagedBlocker có thay thế đồng bộ và memory visibility không?

**Không.** `ManagedBlocker` báo việc chờ để pool có thể quản lý capacity; nó **không** biến mọi biến mutable thành thread-safe.

Ví dụ:

- `BlockingQueue` cung cấp hợp đồng đồng bộ cho thao tác `put/take/poll`. `QueueTaker` an toàn vì dùng queue và truyền kết quả qua `Future.get()`.
- `CountDownLatch` có cơ chế happens-before cho các hành động trước `countDown` và sau `await` thành công theo hợp đồng.
- Một biến `boolean ready` thường bị writer sửa và worker đọc không đồng bộ **không** trở nên an toàn chỉ vì worker gọi `managedBlock`. Cần volatile, lock, atomic hoặc primitive phối hợp khác.
- Nếu worker và producer cùng sửa một `ArrayList` không được bảo vệ, `managedBlock` không ngăn data race.
- Nếu thao tác nghiệp vụ gồm nhiều cập nhật, ManagedBlocker không tạo một transaction.

**Tách trách nhiệm:**

| Nhu cầu | Cơ chế chính |
| --- | --- |
| Chia nhỏ tính toán, gom kết quả | `RecursiveTask`/`RecursiveAction`, `fork()`, `join()` |
| Duy trì khả năng dùng worker khi chờ ngoại vi | `ForkJoinPool.ManagedBlocker` + `managedBlock` |
| Truyền dữ liệu an toàn giữa thread | `BlockingQueue`, latch, volatile/atomic/lock phù hợp |
| Hủy/chờ có thời hạn | Interrupt hợp tác, timed poll/await, Future timeout |
| Bảo vệ bất biến nhiều biến | `synchronized`, `Lock`, immutable state hoặc thiết kế khác |

## 11. Những lỗi thường gặp

1. **“ForkJoinPool tự bù worker cho mọi blocking call.”** Sai: không thể dựa vào compensation tự động với I/O hay `queue.take()` tùy ý.
2. **“ManagedBlocker chắc chắn tạo thêm thread.”** Sai: chỉ là cơ chế cố điều chỉnh parallelism, phụ thuộc giới hạn/cấu hình.
3. **“`isReleasable()` được phép block dài vì cũng là blocker.”** Không nên; phương thức này phải kiểm tra nhanh để runtime quyết định có cần chặn hay không.
4. **“`isReleasable()` có thể gọi `queue.poll()` bỏ qua kết quả.”** Sai: có thể làm mất phần tử; phải lưu item nếu poll thành công.
5. **“`block()` chắc chắn gọi đúng một lần.”** Không nên dựa vào đó; hợp đồng có thể gọi lại nếu chưa hoàn thành.
6. **“`ManagedBlocker` là một lock hoặc Condition.”** Sai: nó mô tả việc chờ, không tự quản lý bất biến dữ liệu.
7. **“`ForkJoinTask.join()` và `Future.get()` giống nhau khi chờ.”** Sai: cơ chế phối hợp/progress khác nhau.
8. **“Một tác vụ đang đợi chính pool chỉ cần ManagedBlocker là hết deadlock.”** Sai khi không thể bù hoặc có vòng phụ thuộc khác.
9. **“Pool parallelism = 4 nghĩa đúng 4 thread tồn tại mọi lúc.”** Sai: đây là mức mục tiêu, thread có thể thay đổi và compensation có thể ảnh hưởng số worker.
10. **“Task bị interrupt thì mọi I/O đều ngừng.”** Sai: phụ thuộc hợp đồng từng API; nên có timeout/close theo giao thức.
11. **“ManagedBlocker giúp code chia sẻ List không cần đồng bộ.”** Sai: nó không thay Java Memory Model hoặc thread safety của dữ liệu.
12. **“Đo số worker tăng trong một lần chạy là chứng minh tính đúng.”** Sai: tiến triển và invariant quan trọng hơn metric tình cờ.
13. **“Dùng commonPool cho mọi I/O chờ lâu là miễn phí.”** Sai: có thể gây ảnh hưởng task dùng chung của JVM.
14. **“Đã gọi `shutdown()` nghĩa task đang đợi chắc chắn bị hủy.”** Sai: orderly shutdown vẫn để task đã nhận tiếp tục chạy.

## 12. Kiểm tra và theo dõi khi vận hành

`ForkJoinPool` có các metric như `getParallelism()`, `getPoolSize()`, `getActiveThreadCount()`, `getRunningThreadCount()`, `getQueuedTaskCount()` và `getStealCount()`. Phần lớn là số liệu **ước lượng** tại thời điểm lấy mẫu và có thể thay đổi ngay.

Gợi ý đọc tín hiệu:

- **Running thấp, queued nhiều:** có thể worker đang chặn hoặc task bị nghẽn; cần xem thread dump/JFR và đường chờ thực tế.
- **Pool size tăng do compensation:** có thể chỉ ra các managed blocking points; không mặc định mọi worker mới đều giúp giải quyết bài toán.
- **Task latency tăng trong khi CPU nhàn:** nghĩ tới chờ lock/I/O và pool bị giữ bởi external blocking.
- **Steal count thay đổi:** phản ánh work-stealing, không phải số request nghiệp vụ thành công.
- **Active/running khác nhau:** thread active có thể bao gồm các trạng thái đợi theo cách đếm của pool; không coi bất cứ số nào là CPU utilization chính xác.

Không dùng metric đang đổi để ra quyết định atomic, ví dụ `if (pool.getQueuedTaskCount() < limit) pool.submit(task)` vẫn có race giữa kiểm tra và gửi. Khi cần giới hạn tải, dùng bounded admission/backpressure theo cơ chế thích hợp.

## 13. Checklist áp dụng ManagedBlocker

1. **Có thật sự cần Fork/Join không?** Nếu toàn bộ task là I/O blocking, executor phù hợp hoặc virtual threads (Java 21+) có thể đơn giản hơn.
2. **Blocking point thuộc loại nào?** Queue, latch, semaphore, I/O, lock hay Future? Có API chờ có hạn/interruptible?
3. **`isReleasable()` có nhanh không?** Tránh chờ dài, bảo đảm kiểm tra điều kiện đồng bộ đúng.
4. **`block()` có thể được gọi lặp không?** Thiết kế idempotent theo trạng thái blocker, kiểm tra kết quả trước khi chờ.
5. **Nếu poll lấy được item, có lưu lại không?** Tránh mất dữ liệu giữa `isReleasable` và `block`.
6. **Ai có thể phát tín hiệu/ghi dữ liệu?** Nguồn phát không được lệ thuộc vào một worker đang bị block mà pool không thể bù.
7. **Có timeout/cancellation khi không tiến triển?** Đừng chờ vô hạn một sự kiện có thể không bao giờ tới.
8. **InterruptedException được xử lý thế nào?** Propagate hoặc restore interrupt status theo hợp đồng và cleanup tài nguyên.
9. **Có khóa nào đang được giữ lúc chờ không?** Tránh lock order/ownership deadlock và gọi callback ngoại vi trong critical section.
10. **Có đủ quyền/giới hạn compensation không?** Đừng thiết kế phụ thuộc vào số thread bù cố định.
11. **State chia sẻ đã thread-safe chưa?** ManagedBlocker không thay queue, atomic, lock hay memory publication.
12. **Có đo throughput, latency và blocked workers không?** Benchmark workload thật, quan sát JFR/thread dump để phân tích.
13. **Common pool có bị ảnh hưởng không?** Xem xét pool riêng nếu workload blocking nhiều hoặc cần isolation.
14. **Các ví dụ được kiểm thử với lịch đa dạng chưa?** Dùng latch để điều phối test, tránh suy từ một lần timing.

**Kết luận:** `ForkJoinPool` tối ưu cho công việc có thể chia nhỏ và work-stealing. Nếu worker phải chờ **dữ liệu hoặc tài nguyên bên ngoài**, blocking trực tiếp có thể làm suy giảm khả năng tiến triển của pool. `ForkJoinPool.ManagedBlocker` cung cấp hợp đồng `isReleasable()/block()` để `managedBlock()` biết thời điểm cần chờ và **có thể cố bù worker**. Cơ chế này hữu ích nhưng không bảo đảm tạo thread, không tự giải quyết deadlock, không thay đồng bộ dữ liệu và không miễn trách nhiệm quản lý interrupt, timeout và vòng đời executor.