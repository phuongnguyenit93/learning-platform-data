# Fork/Join trong Java: Tác vụ chặn và giao diện ManagedBlocker

## 1. Tình huống: worker Fork/Join bị chặn thì điều gì xảy ra?

`ForkJoinPool` trong Java được thiết kế để thực thi các tác vụ có thể phân rã thành phần nhỏ và phân phối qua nhiều worker bằng cơ chế **work-stealing**. Khi một worker hoàn tất hoặc hết việc trong deque riêng, nó có thể lấy việc từ queue khác để tận dụng CPU.

Mô hình này đặc biệt phù hợp với công việc **tính toán CPU**, chẳng hạn chia mảng, xử lý cây, tổng hợp độc lập hay các tác vụ `RecursiveTask`/`RecursiveAction`. Một số chương trình cũng đưa các tác vụ có thao tác chờ vào cùng pool, ví dụ:

- Đợi một thông điệp từ `BlockingQueue.take()`.
- Đợi `CountDownLatch.await()` trong một workflow có tín hiệu từ tác vụ khác.
- Chờ `ReentrantLock.lockInterruptibly()` hoặc một điều kiện đồng bộ.
- Gọi I/O/third-party API mà thread hiện tại có thể bị chặn trong một khoảng đáng kể.
- Đợi một tài nguyên bên ngoài trước khi tính toán tiếp.

Nếu nhiều worker bị chặn bởi các lời gọi như vậy, pool có thể không còn worker rảnh để chạy những tác vụ khác, kể cả tác vụ **có nhiệm vụ giải phóng điều kiện chờ**. Đây là rủi ro thiếu tiến triển (*starvation*) dù vẫn có công việc sẵn trong hàng đợi.

Java cung cấp **`ForkJoinPool.ManagedBlocker`** và phương thức **`ForkJoinPool.managedBlock(ManagedBlocker)`** để những đoạn chờ có thể **thông báo cho pool** rằng worker sắp block. Pool **có thể** huy động worker dự phòng để giữ khả năng tiến triển.

**Thông điệp trung tâm:** `ManagedBlocker` không làm một lời gọi `take()/await()/lock()` trở thành non-blocking; nó giúp pool **nhận biết chỗ có thể chặn và cân nhắc bù parallelism**. Không có bảo đảm rằng lúc nào cũng tạo được thêm thread, không có auto-timeout hay auto-cancel, và không phải tất cả ứng dụng I/O nên chạy trên Fork/Join.

Các API `ForkJoinPool`, `ForkJoinPool.ManagedBlocker` và `ForkJoinPool.managedBlock` có từ **Java 7** và vẫn có trong Java hiện đại. Ví dụ hoàn chỉnh trong bài chạy trên **Java 17+** và đã được biên dịch bằng `javac --release 17 -Xlint:all -Werror`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao blocking thông thường làm giảm parallelism khả dụng của ForkJoinPool.
2. Phân biệt `isReleasable()` và `block()`, hiểu điều kiện trả `true/false`.
3. Biết cách viết một ManagedBlocker cho `CountDownLatch`, `BlockingQueue` hoặc `ReentrantLock` mà không làm mất dữ liệu.
4. Biết vì sao cần gọi **`ForkJoinPool.managedBlock(blocker)`**, không phải tự gọi `blocker.block()`.
5. Phân biệt worker trong ForkJoinPool với thread ngoài pool.
6. Xử lý `InterruptedException`, cancellation, timeout và giới hạn bù worker.
7. Kiểm thử khả năng tiến triển khi `parallelism=1` và một task phải chờ task khác.
8. Chọn giải pháp phù hợp giữa ManagedBlocker, dedicated executor và mô hình concurrency khác của Java hiện đại.

## 2. ForkJoinPool được tối ưu cho dạng tải nào?

Một `ForkJoinTask` thường có cấu trúc:

```text
Tác vụ lớn
    |
    +-- tách A ----> tính A
    |
    +-- tách B ----> tính B
    |
    +-- join kết quả A,B
    |
    v
Kết quả tổng
```

Trong cấu trúc này, worker có thể fork task con và những worker khác steal task chưa chạy. Những phương thức phối hợp task như `fork`/`join` đã được thiết kế riêng cho Fork/Join.

Với một tác vụ **chặn đợi tài nguyên bên ngoài**, tình hình khác:

```text
Pool target parallelism = 2

worker-1: queue.take()  ---- đang chờ dữ liệu
worker-2: latch.await() ---- đang chờ tín hiệu

submitted producer/trigger tasks: vẫn nằm trong queue
```

Nếu hai worker chỉ block theo cách pool **không biết**, không có worker đang chạy tác vụ đưa item/tín hiệu vào. Đây là ví dụ có nguy cơ starvation; không phải mọi tình huống tương tự đều nhất thiết deadlock, vì một thread bên ngoài có thể tạo dữ liệu hoặc một cơ chế khác có thể giải phóng chờ.

Khi sử dụng `managedBlock`, pool có thể nhìn thấy một worker đang bước vào đoạn chờ và điều chỉnh số worker có thể chạy. Cơ chế này là **compensation** nhằm cố giữ **parallelism khả dụng** gần với mức mục tiêu trong những điều kiện pool hỗ trợ.

### 2.1. Parallelism mục tiêu khác số thread đang tồn tại

`new ForkJoinPool(2)` quy định **mức parallelism mục tiêu**, **không cam kết luôn có đúng hai thread trong hệ điều hành**.

Khi managed blocking xảy ra, pool **có thể** tạo hoặc đánh thức worker dự phòng. Vì vậy:

- `getParallelism()`: mức parallelism mục tiêu đã cấu hình.
- `getPoolSize()`: số worker đã khởi tạo và chưa kết thúc, có thể cao hơn mục tiêu.
- `getActiveThreadCount()`: ước tính số worker hoạt động theo định nghĩa API.
- `getRunningThreadCount()`: ước tính số worker không đang blocked trong các loại chờ do pool quản lý.
- `getQueuedTaskCount()` và `getQueuedSubmissionCount()`: thông tin **ước tính** về backlog.
- `getStealCount()`: ước tính số lần steal thành công.

Không dùng một snapshot các metric này để kết luận chắc chắn “ManagedBlocker tạo đúng một worker mới”. Giá trị có thể thay đổi giữa những lần đọc và khác JDK/provider.

### 2.2. `ForkJoinTask.join()` không phải mọi thao tác chờ đều cần ManagedBlocker

Một `ForkJoinTask` fork task con rồi gọi `join()` là mô hình phối hợp nội bộ đã có hỗ trợ riêng trong ForkJoinPool. Không cần tự bọc mọi lời gọi `ForkJoinTask.join()` bằng một ManagedBlocker tùy biến.

ManagedBlocker có giá trị nhất với **điểm blocking ngoài mô hình fork/join thông thường**: queue, latch, lock, hoặc API đồng bộ có thể block mà pool không trực tiếp nhận biết.

## 3. Giao diện `ForkJoinPool.ManagedBlocker`

Đây là một interface lồng trong `ForkJoinPool`:

```java
public static interface ForkJoinPool.ManagedBlocker {
    boolean block() throws InterruptedException;
    boolean isReleasable();
}
```

Đây là **chữ ký rút gọn minh họa**, không phải class Java riêng để tự khai báo lại. Mục đích là hiểu giao kèo hai phương thức.

### 3.1. `isReleasable()` — có thể tiếp tục mà không block?

`isReleasable()` trả:

- **`true`** nếu **không cần chặn nữa**: điều kiện chờ đã được thỏa mãn, dữ liệu đã sẵn, lock đã lấy được, hoặc đã tới trạng thái kết thúc theo policy của blocker.
- **`false`** nếu điều kiện chưa đạt và có thể phải block.

Phương thức này có thể được gọi **nhiều lần**, vì vậy phải thực hiện nhanh, an toàn cho việc kiểm tra lặp, và không nên tự gọi một thao tác blocking vô hạn. Những ví dụ phù hợp:

- `latch.getCount() == 0`: kiểm tra non-blocking.
- `queue.poll()` rồi **giữ lại item đã nhận**: kiểm tra sẵn dữ liệu mà không chờ.
- `lock.tryLock()` rồi **ghi nhớ rằng lock đã được sở hữu**: thử lấy khóa ngay.

**Cảnh báo về tác dụng phụ:** `isReleasable()` có thể lấy một item khỏi queue hoặc lấy một lock. Nếu làm vậy, phải **lưu kết quả trong blocker**; lần gọi kế tiếp không được lấy một item/lock thứ hai một cách âm thầm.

### 3.2. `block()` — chờ nếu thực sự cần

`block()` có thể chặn thread đang gọi cho tới khi điều kiện được thỏa mãn; nó trả:

- **`true`** khi **không cần block thêm**: nếu hỏi `isReleasable()` ngay sau đó, câu trả lời nên là `true` theo ngữ nghĩa blocker.
- **`false`** nếu cần được gọi/kiểm tra thêm; vòng `managedBlock` sẽ lặp cho tới khi một trong hai phương thức trả `true`.

`block()` được phép ném `InterruptedException` nếu chờ bị ngắt; không bắt buộc mọi loại blocker đều interruptible (ví dụ một cơ chế có API chờ không hỗ trợ interrupt).

**Một lỗi rất phổ biến:** nghĩ `false` nghĩa “thất bại” và `true` nghĩa “đã thêm worker”. Sai. Đây là **trạng thái điều kiện chờ**, không phải trạng thái về số thread của pool.

### 3.3. Trình tự gọi

Theo hợp đồng `ForkJoinPool.managedBlock(blocker)`, mỗi lần gọi `blocker.block()` đều được đi trước bởi một lần gọi `blocker.isReleasable()` trả `false`. Có thể diễn đạt khái niệm như sau:

```java
while (!blocker.isReleasable()) {
    if (blocker.block()) {
        break;
    }
}
```

Đây là **mã giả minh họa ngữ nghĩa vòng lặp**, không chứa phần logic bù worker của implementation. Khi chạy trên worker ForkJoinPool, pool có thể thực hiện thêm bước quản lý parallelism **trước khi** để worker gọi `block()`.

Mỗi `ManagedBlocker` phải chịu được việc `isReleasable()` được gọi lặp và **`block()` có thể được gọi nhiều lần** nếu chưa hoàn thành. Đừng viết blocker đòi hai phương thức nhất thiết được gọi đúng một lần theo lịch cố định.

### 3.4. `isReleasable` không được “nói dối”

Một implementation lỗi:

```java
@Override
public boolean isReleasable() {
    return true; // Sai nếu queue đang rỗng và chưa có item.
}
```

Nếu trả `true` sai, `managedBlock` có thể **không gọi `block`**, và caller tiếp tục khi dữ liệu/điều kiện vẫn chưa sẵn sàng.

Ngược lại, một implementation luôn trả `false` sẽ khiến pool có thể tiếp tục thử block ngay cả khi điều kiện đã được thỏa mãn; nếu `block` không trả đúng, ứng dụng có thể chờ không cần thiết hoặc lặp không kết thúc.

## 4. Cách dùng `ForkJoinPool.managedBlock` đúng

Mẫu chung:

```java
ForkJoinPool.ManagedBlocker blocker = createBlocker();
ForkJoinPool.managedBlock(blocker);
// Từ đây blocker đã ở trạng thái "không cần block nữa"
// theo hợp đồng của chính implementation blocker.
```

Đây là đoạn **minh họa** với `createBlocker` là hàm ứng dụng tự định nghĩa, và phương thức gọi có xử lý `InterruptedException`.

**Chỉ cài đặt interface chưa đủ:** nếu bạn tự gọi `blocker.block()` hoặc gọi thẳng `queue.take()`, pool không nhận được thông tin managed blocking qua lời gọi `ForkJoinPool.managedBlock` đó.

### 4.1. Khi chạy trong worker ForkJoinPool

Nếu lời gọi thực thi trong worker của một ForkJoinPool, `managedBlock` có thể điều chỉnh pool để đủ worker khả dụng trong lúc caller chặn. Cơ chế có thể dùng worker dự phòng và chịu ràng buộc cấu hình pool.

Không có lời hứa rằng:

- Luôn tạo thêm đúng một worker cho mỗi lần block.
- Mọi thao tác block sẽ kết thúc.
- Pool có thể tạo thread vô hạn.
- Throughput chắc chắn tăng hoặc latency chắc chắn giảm.
- Một lời gọi I/O trở thành asynchronous.
- Một resource bên ngoài tự được mở hoặc được giải phóng.

### 4.2. Khi gọi từ thread ngoài ForkJoinPool

`ForkJoinPool.managedBlock(blocker)` vẫn thực hiện vòng `isReleasable`/`block`, nhưng **không có ForkJoinPool worker hiện tại để bù parallelism**. Việc gọi từ main thread không tự làm bùng nổ workers của một pool cụ thể.

Đây là điểm quan trọng khi test: nếu chạy `managedBlock` hoàn toàn trên main thread rồi thấy chương trình đợi đúng, bạn **chưa** chứng minh pool đã thực hiện compensation. Ví dụ ở phần 8 thử hai task phụ thuộc nhau **cùng trong một pool có parallelism 1** để kiểm chứng tiến triển trong môi trường chạy thực tế.

### 4.3. Một blocker thường có state riêng cho một lần chờ

Các instance minh họa lưu item nhận từ queue hoặc trạng thái gate. Không nên tự chia sẻ một blocker stateful như vậy giữa nhiều task/worker mà không có thiết kế đồng bộ riêng; ownership của kết quả và tương tác giữa `isReleasable`/`block` sẽ dễ bị sai.

Một helper có thể tạo một blocker mới cho mỗi request rồi **trả dữ liệu ra bên ngoài sau khi `managedBlock` hoàn tất**.

## 5. Ví dụ tối giản với CountDownLatch

`CountDownLatch.await()` là lời gọi blocking thông thường. Nếu ForkJoinPool worker chờ một latch mà một tác vụ khác **trong chính pool** phải gọi `countDown()`, ta nên cân nhắc ManagedBlocker.

### 5.1. Xây LatchBlocker

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;

final class LatchBlocker implements ForkJoinPool.ManagedBlocker {
    private final CountDownLatch latch;

    LatchBlocker(CountDownLatch latch) {
        this.latch = latch;
    }

    @Override
    public boolean isReleasable() {
        return latch.getCount() == 0;
    }

    @Override
    public boolean block() throws InterruptedException {
        latch.await();
        return true;
    }
}
```

Đây là **class có thể biên dịch khi lưu trong file Java phù hợp**, và có thể được dùng từ một phương thức cho phép `InterruptedException`. Nếu latch đã về 0, `isReleasable` trả true và không cần block. Nếu chưa về 0, `block` đợi rồi trả true khi `await` hoàn tất.

**Lưu ý:** nếu không ai từng gọi `countDown()`, không có ManagedBlocker nào làm latch tự về 0. Compensation chỉ giúp một task đủ điều kiện có cơ hội được chạy; nó không sửa một **phụ thuộc vòng** hoặc lỗi thiếu tín hiệu trong logic ứng dụng.

### 5.2. Quy trình trong pool

```java
ForkJoinPool pool = new ForkJoinPool(1);
CountDownLatch gate = new CountDownLatch(1);

try {
    var waiter = pool.submit(() -> {
        ForkJoinPool.managedBlock(new LatchBlocker(gate));
        return "released";
    });

    // Sau khi worker thực sự đã bước vào managedBlock,
    // một tác vụ trong chính pool có thể countDown gate.
    var releaser = pool.submit(gate::countDown);
    releaser.get(5, TimeUnit.SECONDS);
    System.out.println(waiter.get(5, TimeUnit.SECONDS));
} finally {
    gate.countDown();
    pool.shutdownNow();
}
```

Đây là **đoạn minh họa không độc lập** vì cần import `TimeUnit`, xử lý interruption/exception và giao thức xác nhận worker thực sự đã bắt đầu chờ. Trong ví dụ hoàn chỉnh, có một latch thứ hai dùng để **đồng bộ thời điểm** cho phép main submit tác vụ mở gate; vì thế test không phụ thuộc may rủi worker đã chạy tới `await` hay chưa.

`ForkJoinPool(1)` là mức parallelism mục tiêu bằng 1. Khi một worker đã vào managed blocking, pool có thể sử dụng worker phụ để chạy tác vụ release. **Không được suy từ kết quả demo rằng mọi pool cấu hình cực hạn hoặc runtime không thể từ chối compensation**.

## 6. Ví dụ quan trọng: BlockingQueue và kết quả không được mất

Một worker ForkJoinPool cần đợi item từ `BlockingQueue<E>`. Cách đơn giản nhưng có rủi ro:

```java
E item = queue.take(); // Blocking không báo cho pool.
```

Nếu phải dùng ForkJoinPool cho tình huống này, xây ManagedBlocker.

### 6.1. Thiết kế QueueTaker

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ForkJoinPool;

final class QueueTaker<E> implements ForkJoinPool.ManagedBlocker {
    private final BlockingQueue<E> queue;
    private E item;

    QueueTaker(BlockingQueue<E> queue) {
        this.queue = queue;
    }

    @Override
    public boolean isReleasable() {
        if (item != null) return true;
        item = queue.poll(); // Không block; lưu item nếu có.
        return item != null;
    }

    @Override
    public boolean block() throws InterruptedException {
        if (isReleasable()) return true;
        item = queue.take(); // Chỉ take khi queue vẫn chưa có dữ liệu.
        return true;
    }

    E item() {
        return item;
    }
}
```

Đây là **class minh họa có thể biên dịch** khi đặt trong file phù hợp. `BlockingQueue` của Java không cho phép phần tử `null` nên `item == null` là sentinel “chưa nhận dữ liệu”.

Vì sao thiết kế như vậy?

1. `isReleasable()` cố `poll()` **không chờ**.
2. Nếu `poll()` lấy được item, **ghi nhớ** item, không lấy thêm ở lần gọi sau.
3. Nếu queue rỗng, trả false.
4. `block()` kiểm tra lại điều kiện phòng race giữa lần `isReleasable` của pool và thời điểm bắt đầu block.
5. Chỉ khi vẫn chưa có item mới gọi `queue.take()`.
6. Sau khi `managedBlock` hoàn tất thành công, caller lấy item đã giữ từ blocker.

### 6.2. Lỗi phổ biến: poll làm mất dữ liệu

Một cách cài đặt sai:

```java
@Override
public boolean isReleasable() {
    return queue.poll() != null; // Sai: bỏ rơi item vừa lấy.
}
```

Vì `poll()` **thực sự gỡ item khỏi queue**, đoạn trên vừa báo sẵn sàng vừa làm mất tham chiếu tới dữ liệu. Code sau `managedBlock` không biết item nào đã được nhận.

Quy tắc là: nếu phép kiểm tra non-blocking có **tác dụng phụ**, phải lưu lại kết quả và đảm bảo idempotent trong vòng đời blocker.

### 6.3. Không dùng một ByteBuffer/mutable item chung cho nhiều request

Mặc dù `BlockingQueue` thread-safe trong thao tác queue, object item lấy ra có thể là mutable. Các worker khác có thể không được phép sửa item cùng lúc. Định nghĩa ownership: một consumer nhận một item rồi xử lý; không vừa đưa item cho hai task vừa giả định dữ liệu tự an toàn.

### 6.4. Queue có item sẵn: đường đi không cần blocking

Nếu queue đã có item trước khi gọi `managedBlock`, `isReleasable` có thể lấy ngay bằng `poll` và trả true. Khi đó không cần bù worker và không gọi `queue.take()`.

Điều này minh họa ý đồ API: **đừng thông báo sắp block khi thực tế đã có thể tiếp tục**.

## 7. ManagedBlocker với ReentrantLock

Một trường hợp khác là lock có thể gây chờ đủ lâu. `isReleasable` có thể gọi `tryLock`, còn `block` gọi `lockInterruptibly` khi cần.

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.locks.ReentrantLock;

final class ManagedLocker implements ForkJoinPool.ManagedBlocker {
    private final ReentrantLock lock;
    private boolean acquired;

    ManagedLocker(ReentrantLock lock) {
        this.lock = lock;
    }

    @Override
    public boolean isReleasable() {
        return acquired || (acquired = lock.tryLock());
    }

    @Override
    public boolean block() throws InterruptedException {
        if (!acquired) {
            lock.lockInterruptibly();
            acquired = true;
        }
        return true;
    }
}
```

Đây là **class minh họa**, không phải chương trình độc lập. Khi dùng:

```java
ManagedLocker blocker = new ManagedLocker(lock);
ForkJoinPool.managedBlock(blocker);
try {
    // Làm việc trong critical section sau khi lock được cấp.
} finally {
    lock.unlock(); // Phải unlock bởi đúng thread đã lấy lock.
}
```

Đoạn này cần `lock` được khai báo/khởi tạo và caller xử lý `InterruptedException`. Đây là vấn đề **thread ownership** rất quan trọng: `ReentrantLock` được sở hữu bởi thread đã lấy nó. Đừng đưa object blocker sang worker khác và yêu cầu worker đó `unlock` thay cho thread sở hữu.

**Không coi ManagedBlocker là cách chữa mọi contention**. Nếu nhiều task chỉ tranh chấp vì cùng một critical section quá dài, thêm worker có thể tăng chi phí mà không tăng lượng công việc hoàn tất. Trước tiên cân nhắc rút ngắn vùng khóa, hạn chế shared mutable state hoặc dùng thuật toán không cần lock.

## 8. Chương trình Java 17+ hoàn chỉnh đã kiểm thử

Chương trình **`ManagedBlockingDemo.java`** dùng một `ForkJoinPool` riêng có parallelism mục tiêu là **1** để làm rõ tiến triển khi một worker đang chờ.

Các bước kiểm chứng:

1. Tạo pool target parallelism=1 và một latch chưa được giải phóng.
2. Submit task `waiter` vào pool; bên trong gọi `ForkJoinPool.managedBlock` với `LatchBlocker` và thông báo đã đi vào phần `block()`.
3. Chỉ khi main xác nhận task đang chờ, submit một task **cũng trong pool** gọi `gate.countDown()`.
4. Xác minh task release được chạy và task waiter hoàn thành. Trong môi trường JDK 17 đã chạy, pool thực hiện đủ compensation để có tiến triển.
5. Submit một consumer chờ `BlockingQueue` bằng `QueueTaker`; sau tín hiệu consumer đã vào `block`, submit producer **cũng trong pool**, đưa số 42 vào queue. Xác minh consumer lấy được đúng 42.
6. Bỏ số 7 vào một queue sẵn có rồi gọi `managedBlock` ngoài ForkJoinPool để xác minh **fast path**.
7. Tạo một thread độc lập đang chờ latch vô hạn thông qua `managedBlock`, interrupt thread đó và xác minh `InterruptedException` đi ra đúng; thread khôi phục interrupt flag trong `catch`.
8. Shutdown pool do chương trình sở hữu và chờ kết thúc.

Không có network, disk I/O hoặc file người dùng bị chỉnh sửa. Thí nghiệm chỉ kiểm tra orchestration và giao kèo blocking; không dùng số thread thực tế làm assertion vì phụ thuộc scheduler/pool implementation.

### 8.1. Mã chạy đầy đủ: `ManagedBlockingDemo.java`

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ManagedBlockingDemo {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static final class LatchBlocker
            implements ForkJoinPool.ManagedBlocker {
        private final CountDownLatch gate;
        private final CountDownLatch entered;

        LatchBlocker(CountDownLatch gate, CountDownLatch entered) {
            this.gate = gate;
            this.entered = entered;
        }

        @Override
        public boolean isReleasable() {
            return gate.getCount() == 0;
        }

        @Override
        public boolean block() throws InterruptedException {
            entered.countDown();
            gate.await();
            return true;
        }
    }

    private static final class QueueTaker<E>
            implements ForkJoinPool.ManagedBlocker {
        private final BlockingQueue<E> queue;
        private final CountDownLatch entered;
        private E item;

        QueueTaker(BlockingQueue<E> queue, CountDownLatch entered) {
            this.queue = queue;
            this.entered = entered;
        }

        @Override
        public boolean isReleasable() {
            if (item != null) return true;
            item = queue.poll();
            return item != null;
        }

        @Override
        public boolean block() throws InterruptedException {
            if (isReleasable()) return true;
            entered.countDown();
            item = queue.take();
            return true;
        }

        E item() {
            return item;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch gateEntered = new CountDownLatch(1);
        BlockingQueue<Integer> queue = new LinkedBlockingQueue<>();
        CountDownLatch queueEntered = new CountDownLatch(1);

        try {
            System.out.println("configured parallelism = "
                    + pool.getParallelism());

            Future<String> waiter = pool.submit(() -> {
                check(ForkJoinTask.getPool() == pool, "wrong pool");
                ForkJoinPool.managedBlock(
                        new LatchBlocker(gate, gateEntered));
                return "released";
            });
            check(gateEntered.await(5, TimeUnit.SECONDS),
                    "worker never entered latch block");

            Future<?> opener = pool.submit(gate::countDown);
            opener.get(5, TimeUnit.SECONDS);
            check("released".equals(waiter.get(5, TimeUnit.SECONDS)),
                    "latch result");
            System.out.println("managed latch result = released");

            Future<Integer> consumer = pool.submit(() -> {
                QueueTaker<Integer> blocker =
                        new QueueTaker<>(queue, queueEntered);
                ForkJoinPool.managedBlock(blocker);
                return blocker.item();
            });
            check(queueEntered.await(5, TimeUnit.SECONDS),
                    "worker never entered queue block");

            Future<?> producer = pool.submit(() -> {
                queue.add(42);
            });
            producer.get(5, TimeUnit.SECONDS);
            check(consumer.get(5, TimeUnit.SECONDS) == 42,
                    "queue consumer result");
            System.out.println("managed queue item = 42");

            BlockingQueue<Integer> ready = new LinkedBlockingQueue<>();
            ready.add(7);
            QueueTaker<Integer> fast =
                    new QueueTaker<>(ready, new CountDownLatch(1));
            ForkJoinPool.managedBlock(fast);
            check(fast.item() == 7, "fast path item");
            System.out.println("ready queue fast path = 7");

            AtomicBoolean wasInterrupted = new AtomicBoolean(false);
            CountDownLatch interruptEntered = new CountDownLatch(1);
            Thread waiting = new Thread(() -> {
                try {
                    ForkJoinPool.managedBlock(new LatchBlocker(
                            new CountDownLatch(1), interruptEntered));
                } catch (InterruptedException interrupted) {
                    wasInterrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            }, "blocking-interrupt-demo");
            waiting.start();
            check(interruptEntered.await(5, TimeUnit.SECONDS),
                    "interrupt thread never blocked");
            waiting.interrupt();
            waiting.join(5_000L);
            check(!waiting.isAlive() && wasInterrupted.get(),
                    "interrupt not handled");
            System.out.println("interrupt propagated = true");

            System.out.println("checks = PASS");
        } finally {
            gate.countDown();
            queue.offer(-1);
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "pool failed to terminate");
        }
        System.out.println("pool terminated = true");
    }
}
```

Biên dịch và chạy với **Java 17**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ManagedBlockingDemo.java
java ManagedBlockingDemo
```

### 8.2. Stdout chính xác đã kiểm chứng

```text
configured parallelism = 1
managed latch result = released
managed queue item = 42
ready queue fast path = 7
interrupt propagated = true
checks = PASS
pool terminated = true
```

Chương trình đã biên dịch không có warning bằng `-Xlint:all -Werror` và chạy thành công trên JDK 17. Việc mỗi `Future.get(5,SECONDS)` có timeout giúp **phát hiện** test treo thay vì chờ vô hạn. Timeout không có nghĩa test chắc chắn chạy xong nhanh trên mọi môi trường quá tải; nếu hệ thống bị chiếm tài nguyên hoặc bị hạn chế tạo thread, test có thể fail và cần điều tra.

### 8.3. Tại sao lại kiểm tra `ForkJoinTask.getPool() == pool`?

`ForkJoinTask.getPool()` trả về pool nơi thread **đang thực thi một ForkJoin task**, hoặc `null` nếu không ở trong ForkJoinPool. Test dùng phép so để bảo đảm đoạn managed blocking chính thật sự chạy trên worker của pool thử nghiệm; nếu chạy nhầm trên main thread, kết quả không chứng minh pool có cơ hội bù parallelism.

**Đừng nhầm tên API:** `getPool()` là phương thức static của **`ForkJoinTask`**, không phải `ForkJoinPool.getPool()`.

### 8.4. Tại sao chờ `gateEntered` trước khi submit opener?

Nếu main submit cả waiter và opener ngay lập tức, opener có thể chạy **trước khi** waiter thực sự bước vào `block`. Khi đó latch đã về 0, `isReleasable` trả true và không hề có blocking. Test vẫn PASS nhưng **không kiểm chứng được** tình huống cần compensation.

Vì vậy `LatchBlocker.block` gọi `entered.countDown()` ngay trước khi `gate.await()`; main chờ tín hiệu rồi submit opener. Có một cửa sổ scheduler nhỏ giữa tín hiệu và lệnh await, nhưng worker đã đi vào logic managed blocking và gate vẫn chưa được giải phóng. Thiết kế này vững hơn nhiều so với một `Thread.sleep` đoán thời điểm.

### 8.5. Tại sao không assert pool phải có hai worker?

ForkJoinPool được phép **quản lý/điều chỉnh** worker theo điều kiện hiện tại, giới hạn cấu hình và JDK. Kết quả bài test chỉ cho thấy **tác vụ dependent đã được chạy và điều kiện chờ được giải phóng** trong một môi trường. Không khẳng định có đúng hai thread tồn tại tại mọi thời điểm.

Nếu muốn quan sát, có thể lấy `getPoolSize`/`getRunningThreadCount` để logging, nhưng đó là **ước tính động**, không nên dùng làm tiêu chí correctness chính.

### 8.6. Tại sao fast path gọi ngoài pool vẫn thành công?

Queue đã có item 7. `isReleasable` nhận item bằng `poll`, trả true, `managedBlock` hoàn thành mà không cần `block`. Vì không có worker ForkJoinPool ở đây, **không có khái niệm bù worker của pool thử nghiệm**.

Điều này minh họa cùng một interface có thể dùng ngoài pool, nhưng khi đó nó chủ yếu thực hiện vòng điều kiện bình thường.

### 8.7. Test interrupt kiểm tra điều gì?

Một thread **riêng biệt** chạy `managedBlock` với latch chưa mở. Main chờ thread báo đang đi vào `block`, rồi gọi `waiting.interrupt()`. `CountDownLatch.await()` là thao tác interruptible nên ném `InterruptedException`; code bắt lỗi, ghi nhận và khôi phục cờ interrupt.

**Không suy rằng `ForkJoinTask.cancel(true)` nói chung đồng nghĩa interrupt native worker ngay lập tức.** Java Fork/Join có cơ chế cancellation riêng và phải thiết kế chờ/cancellation theo hợp đồng của từng loại task.

## 9. Xử lý `InterruptedException` đúng trong Fork/Join

`ForkJoinPool.managedBlock` khai báo `throws InterruptedException` bởi `ManagedBlocker.block` có thể ném lỗi đó.

### 9.1. Trong `Callable`

Một `Callable` có thể khai báo checked exception và cho phép operation propagate lên `Future`:

```java
Future<String> result = pool.submit(() -> {
    ForkJoinPool.managedBlock(new LatchBlocker(gate));
    return "done";
});
```

Đây là đoạn minh họa với `pool`, `gate`, `LatchBlocker` đã khai báo phù hợp. Khi có exception trong task, caller dùng `Future.get()` sẽ nhận `ExecutionException` chứa nguyên nhân.

### 9.2. Trong `RecursiveTask.compute()`

`compute()` không được khai báo checked `InterruptedException`; cần quyết định chính sách:

```java
@Override
protected Integer compute() {
    try {
        ForkJoinPool.managedBlock(blocker);
        return calculateResult();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new java.util.concurrent.CancellationException(
                "Interrupted while waiting");
    }
}
```

Đây là **đoạn minh họa chưa độc lập** vì `blocker`, `calculateResult()` và class cha `RecursiveTask<Integer>` phải được định nghĩa. Quan trọng là:

- Không nuốt `InterruptedException` rồi báo task hoàn thành bình thường.
- Khi catch mà không propagate checked exception, thường cần **khôi phục interrupt flag**.
- Dùng kiểu exception/state nhất quán với hợp đồng cancellation của ứng dụng.
- Không hiểu khôi phục cờ interrupt là tự động hủy tất cả task anh em.

### 9.3. Lựa chọn giữa interruptible và uninterruptible

Nếu blocker sử dụng `lockInterruptibly` hoặc `BlockingQueue.take`, interruption có thể được phát hiện. Nếu thư viện dùng I/O không hỗ trợ interrupt hoặc một cơ chế chờ không thể hủy, ManagedBlocker **không biến nó thành interruptible**.

Khi operation có deadline, cần dùng API timeout gốc của tài nguyên, hoặc thiết kế khả năng đóng/huỷ một cách an toàn. Không phó mặc shutdown cho `ManagedBlocker`.

## 10. Timeout và cancellation không xuất hiện tự động

`ForkJoinPool.managedBlock` không nhận tham số timeout. Nếu muốn có deadline, **chính blocker và tầng gọi** phải định nghĩa:

- Thế nào là condition “sẵn sàng”.
- Khi nào kết thúc chờ vì quá hạn.
- Sau timeout, code có được phép tính tiếp với giá trị mặc định hay phải fail?
- Làm sao phân biệt “có item” với “hết hạn mà không có item”.
- Làm sao dọn tài nguyên đang chờ và ngừng phát sinh task mới.

### 10.1. Ví dụ logic timeout cho latch

Một ý tưởng đơn giản là trong `block` dùng `latch.await(timeout,unit)`, lưu boolean kết quả, rồi trả true vì lần chờ này đã kết thúc theo chính sách — **kể cả khi timeout**. Khi kết thúc `managedBlock`, caller phải kiểm tra cờ kết quả, không được giả vờ latch đã về 0.

Không nên chỉ viết:

```java
public boolean block() throws InterruptedException {
    latch.await(100, TimeUnit.MILLISECONDS);
    return true;
}
```

và ngầm xem return true đồng nghĩa latch đã giải phóng. Trường hợp timeout, lời gọi `await` trả false nhưng code trên đã bỏ mất thông tin.

Một blocker có timeout thực tế còn cần lưu **deadline tính từ lúc bắt đầu tác vụ**, không tự “gia hạn thêm 100 ms” vô hạn mỗi lần `block` được gọi lại.

### 10.2. Future.get(timeout) là timeout của người đợi

Nếu caller ngoài pool chờ:

```java
String result = future.get(2, TimeUnit.SECONDS);
```

rồi gặp `TimeoutException`, đó chỉ là **thread này đã đợi quá hạn**. Nó không có nghĩa underlying ForkJoinTask bị dừng hoặc blocker đã được interrupt. Cần chính sách cancellation/cleanup riêng.

Tương tự, `cancel(true)` trên một `ForkJoinTask` không nên bị coi là bảo đảm interrupt worker đang mắc kẹt trong mọi loại blocking call. Thiết kế có thể cần flag, resource close, signal hoặc timeout gốc để bảo đảm tiến triển.

### 10.3. Không lấy timeout làm cách giả tạo throughput

Nếu benchmark đếm mọi tác vụ timeout là “hoàn thành nhanh” rồi tính throughput cao hơn, kết quả không có ý nghĩa. Phải tách success/error/timeout và đo tài nguyên thực tế. ManagedBlocker là kỹ thuật điều phối, không phải biện pháp bỏ bớt công việc khi thiếu công suất.

## 11. Giới hạn compensation và rủi ro tạo quá nhiều worker

Khi worker báo managed blocking, ForkJoinPool **có thể** mở rộng số worker có thể chạy. Nhưng:

- Cấu hình pool có giới hạn worker và mức parallelism mục tiêu.
- Pool có thể không bù được do giới hạn OS/memory/thread factory.
- Một pool với số task chờ vô hạn vẫn có thể cạn nguồn lực, kể cả khi dùng ManagedBlocker đúng.
- Khi quá nhiều request cùng chờ I/O, số platform threads tăng có thể làm memory và context switching tăng.
- Nếu điều kiện chờ phụ thuộc vòng (*deadlock logic*), bù worker không giải quyết.
- Nếu bottleneck chính là service/backend ngoài, bù worker có thể chỉ tăng số request dồn lên backend.

Để kiểm soát, ứng dụng có thể dùng:

1. **Hàng đợi bounded** và chính sách backpressure.
2. **Semaphore** giới hạn số thao tác chờ/connections/request.
3. **Timeout/deadline** phù hợp thao tác.
4. **Dedicated executor** cho I/O có nhiều chờ dài.
5. **Metrics** để phát hiện saturation, rejection và tail latency.
6. **Shutdown protocol** đảm bảo tín hiệu cho blocker còn đang đợi.

Không biến “ManagedBlocker có thể bù worker” thành một tuyên bố “pool tự động co giãn vô hạn” hay “không cần vận hành capacity”.

### 11.1. `RejectedExecutionException` và thiếu worker

Khi pool không thể sắp xếp/chạy thêm công việc hoặc thiếu nguồn lực để duy trì cấu hình, một số đường thực thi có thể gặp `RejectedExecutionException` hoặc lỗi tài nguyên. Không hardcode cách khôi phục giống nhau với mọi tình huống; log trạng thái pool, loại thao tác và nguyên nhân, rồi áp dụng backpressure/circuit breaker nếu phù hợp.

Với một pool custom cấu hình hạn mức workers nghiêm ngặt, cần integration test kịch bản nhiều worker đồng thời managed blocking.

### 11.2. Điều phối workers không thay đổi tính đúng đắn của dữ liệu

Ngay cả khi pool bù được thread, bạn vẫn cần:

- Thread-safe queue, lock/condition có thứ tự đúng.
- Xác minh item không bị tiêu thụ hai lần.
- Đảm bảo producer chắc chắn có thể tạo dữ liệu.
- Hạn chế phụ thuộc vòng giữa các task.
- Xử lý exception/cancellation và release tài nguyên.
- Không share mutable blocker state tùy tiện giữa thread.

ManagedBlocker giải quyết một phần bài toán **scheduling/parallelism**, không giải quyết mọi lỗi đồng bộ hóa.

## 12. Khi nào KHÔNG nên dùng ManagedBlocker?

### 12.1. Công việc chỉ CPU-bound, không chặn

Một thuật toán chia để trị cộng mảng hoặc tính toán cây không cần ManagedBlocker nếu nó chỉ chạy CPU và dùng `fork/join` theo mẫu thông thường. Bọc một phép tính CPU trong ManagedBlocker không biến nó thành I/O, không tạo lợi ích scheduling có ý nghĩa.

### 12.2. Nhiều tác vụ I/O chờ rất dài

Nếu phần lớn task là HTTP request, database query, socket read blocking hoặc chờ thiết bị ngoài, ForkJoinPool có thể không phải scheduler phù hợp ngay từ đầu. Cân nhắc:

- Một `ExecutorService` chuyên cho blocking I/O với giới hạn concurrency rõ.
- API async chính thức của thư viện/driver khi tích hợp thật sự bất đồng bộ.
- Với **Java 21+**, virtual threads có thể giúp lập trình theo kiểu blocking với nhiều tác vụ đồng thời; vẫn cần giới hạn tài nguyên bên ngoài, timeout và kiểm soát overload. Virtual threads **không có nghĩa hệ thống có infinite network/file handles**, cũng không làm mọi lời gọi đều hoàn toàn non-blocking trên mọi provider.
- Tách CPU-bound fork/join tasks khỏi I/O tasks thay vì biến một pool chung thành nơi chờ của toàn bộ ứng dụng.

Đây là các lựa chọn **hiện hành**, không đề xuất dùng API Java đã deprecated.

### 12.3. Đợi chính `ForkJoinTask.join()`

Cơ chế `join` của ForkJoinTask đã được thiết kế cho cấu trúc phối hợp Fork/Join và có tối ưu riêng. Không tự bọc `join` bằng một ManagedBlocker chỉ vì nó *có thể* chờ. Trường hợp chờ bên ngoài như `BlockingQueue.take` là mục tiêu rõ ràng hơn.

### 12.4. Bài toán cần event-driven không giữ worker

ManagedBlocker có thể **chặn platform thread hiện tại**. Nếu ứng dụng cần throughput cực lớn và mọi I/O đều có API completion thật, một thiết kế event-driven có thể phù hợp hơn. Đừng giả định ManagedBlocker tự động tạo callback hay trả quyền điều khiển khi đang chờ.

### 12.5. Không biết ai giải phóng điều kiện

Nếu task A chờ latch, task B chờ task A và không có actor nào làm latch về 0, có thêm worker cũng không cứu được. Trước khi tối ưu pool, vẽ graph phụ thuộc và xác định condition sẽ được báo hiệu ở đâu.

## 13. Đo và quan sát hiệu quả bằng workload thật

**Đừng chỉ nhìn thấy demo `parallelism=1` chạy xong rồi mặc định mọi ứng dụng chuyển sang ManagedBlocker sẽ nhanh hơn.**

Một phép đo nghiêm túc nên có các nhóm:

| Biến thể | Mục đích |
| --- | --- |
| ForkJoin CPU-only | Baseline cơ chế work-stealing khi không có chờ ngoài |
| ForkJoin + blocking thường | Thấy ảnh hưởng của chờ không được quản lý ở workload kiểm soát |
| ForkJoin + ManagedBlocker | Đo khả năng giữ tiến triển và độ sâu queue khi có chờ |
| Dedicated blocking executor | So với giải pháp tách I/O khỏi CPU pool |
| Java 21+ virtual threads (khi phù hợp) | So với mô hình blocking có khả năng mở rộng cao hơn |

Các metric nên ghi:

- Số tác vụ hợp lệ hoàn tất mỗi giây và **end-to-end latency**.
- p50/p95/p99, deadline violations và timeout rate.
- Số thread platform của pool, mức CPU và context switches.
- `getPoolSize()`, `getRunningThreadCount()`, queued submissions/tasks, steal count — là các số đo động.
- Số ManagedBlocker đang hoạt động, thời gian block và tỷ lệ fast path.
- Heap/stack memory, GC pause và tài nguyên backend.
- Tỷ lệ task bị cancel, exception, shutdown không hoàn tất.

### 13.1. Tại sao tăng throughput chưa đủ?

Nếu compensation cho phép pool hoàn tất nhiều request hơn nhưng tạo rất nhiều worker, CPU và memory tăng mạnh, p99 có thể xấu. Trong một dịch vụ nhạy SLA, cấu hình có throughput thấp hơn đôi chút nhưng ổn định, giới hạn tài nguyên và dễ vận hành có thể tốt hơn.

### 13.2. Không dùng `Thread.sleep` để “chắc chắn blocked”

Một test chỉ:

```java
Thread.sleep(200);
```

không xác minh logic `ManagedBlocker`, vì nó không có tín hiệu điều kiện/tác vụ giải phóng rõ ràng. Trên CI tải cao, thời gian wakeup của thread cũng không cố định. Nếu cần test khả năng tiến triển, dùng `CountDownLatch` riêng để điều phối thứ tự và timeout cho `Future` — như ví dụ hoàn chỉnh.

### 13.3. Lỗi do pool vs lỗi do nghiệp vụ

Nếu task thất bại, phân biệt:

- Không có producer/countDown đúng: lỗi giao thức ứng dụng.
- Pool bị shutdown/reject request: lỗi lifecycle/capacity.
- `InterruptedException` từ blocking API: yêu cầu dừng hoặc interrupt.
- `ExecutionException` khi main lấy Future: wrapper của lỗi xảy ra bên trong task.
- Backend/network không phản hồi: lỗi tài nguyên ngoài, không thể sửa chỉ bằng tăng worker.

## 14. Tình huống thực tế: có nên dùng cho BlockingQueue consumer?

Một hệ thống xử lý hàng đợi có worker liên tục:

```java
while (running) {
    Event event = queue.take();
    process(event);
}
```

Đây là **đoạn minh họa không độc lập**. Nếu mọi worker ForkJoinPool chạy vòng chờ này mãi, đó là **long-lived blocking consumers**, trong khi ForkJoinPool thường tối ưu hơn cho nhiều tác vụ tính toán nhỏ.

Có hai lựa chọn kiến trúc:

**Lựa chọn A — giữ ForkJoinPool có điều kiện:** nếu chỉ thỉnh thoảng một fork/join task cần lấy một kết quả từ BlockingQueue để tiếp tục tính toán, dùng QueueTaker ManagedBlocker là phù hợp; phải đo độ sâu concurrency và có shutdown policy.

**Lựa chọn B — tách consumer loop:** tạo dedicated executor hoặc thread chuyên tiêu thụ queue, rồi submit **công việc CPU đã có dữ liệu** sang ForkJoinPool. Cách này thường làm ranh giới ownership và resource budgets rõ hơn, không bắt CPU pool phải giữ nhiều worker chờ dài.

Một mẹo quan trọng: `queue.poll()` trong `isReleasable` **không tự khởi tạo producer**. Nếu phía sản xuất sẽ không bao giờ hoạt động do lifecycle lỗi, ManagedBlocker vẫn có thể chờ vô hạn.

### 14.1. Dùng ReentrantLock thì cần cân nhắc contention

Có thể dùng ManagedLocker ở mục 7 để worker biết trước khi vào chờ lock. Nhưng một vùng khóa độc quyền dài vẫn chỉ có **một owner**; thêm workers có thể làm hàng đợi tranh chấp lớn hơn. Rút ngắn critical section, cấu trúc dữ liệu lock-free hoặc phân vùng state thường đáng đánh giá trước.

### 14.2. Database/network blocking chưa chắc nên chạy trong pool này

ManagedBlocker có thể dùng cho một lời gọi đồng bộ blocking, nhưng không biết protocol/backpressure của database hoặc network. Nếu hệ thống có hàng trăm request chờ backend, tạo worker dự phòng có thể làm tăng số connection đang tranh nhau. Luôn có quota backend và timeout theo hợp đồng I/O.

## 15. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Coi ForkJoinPool phù hợp với mọi tác vụ chặn dài | Workers bị chiếm, queue backlog | Ưu tiên CPU work; phân tách I/O khi cần |
| Gọi `queue.take` trong pool mà không báo managed blocking | Pool không biết worker có thể bị chặn | Dùng `managedBlock` có blocker đúng hoặc executor khác |
| Chỉ triển khai `ManagedBlocker` rồi tự gọi `block` | Bỏ qua cơ chế compensation | Gọi `ForkJoinPool.managedBlock(blocker)` |
| Nghĩ `managedBlock` làm I/O non-blocking | Thread vẫn có thể bị chặn | Nó chỉ giúp pool quản lý parallelism |
| `isReleasable` luôn false | Có thể block dù sẵn điều kiện | Thử non-blocking và trả đúng kết quả |
| `isReleasable` luôn true | Caller chạy tiếp khi dữ liệu chưa sẵn | Chỉ true khi điều kiện đã đạt |
| `isReleasable` gọi `queue.take` | Kiểm tra khả dụng lại tự block | Dùng `poll` và lưu item |
| `queue.poll()!=null` nhưng bỏ item | Mất dữ liệu | Lưu item trong blocker |
| Mỗi lần `isReleasable` lại poll một item | Ăn mất nhiều item | Cache kết quả và trả true về sau |
| Gọi `block` và bỏ qua return value | Sai hợp đồng vòng chờ | Return true khi không cần block nữa |
| Viết `block` trả false mãi | Vòng lặp có thể không kết thúc | Trạng thái tiến triển rõ |
| Tin `block()` luôn được gọi đúng một lần | Sai khi fast path hoặc retry | Cài đặt idempotent theo state |
| Gọi `managedBlock` từ main rồi kết luận pool bù thread | Main không thuộc pool | Test trong worker ForkJoinPool |
| Assert `getPoolSize()==parallelism+1` | Pool size thay đổi động | Xác minh task tiến triển, metrics chỉ để quan sát |
| Quên timeout/interrupt khi chờ | Dễ treo hoặc shutdown khó | Có deadline/cancellation lifecycle |
| Catch `InterruptedException` rồi nuốt | Task tiếp tục khi cần dừng | Propagate hoặc restore interrupt flag |
| Nghĩ `Future.get(timeout)` tự dừng blocker | Task có thể vẫn chạy | Quản lý cancellation và cleanup |
| Dùng `Future.cancel(true)` như bảo đảm worker bị interrupt | Không phải mọi ForkJoinTask tuân semantics đó | Thiết kế signal/resource close/timeouts |
| Không có ai gọi `countDown` | ManagedBlocker không thể tạo tín hiệu | Sửa phụ thuộc logic |
| Để mọi request block không giới hạn | Có thể cạn worker/memory | Backpressure và concurrency budget |
| Giữ `ReentrantLock` ở thread A rồi unlock ở B | Sai thread ownership | Lock/unlock cùng thread |
| Đưa cùng blocker mutable cho nhiều workers | Race và mất dữ liệu | Blocker theo task hoặc synchronization riêng |
| Dùng ManagedBlocker để tối ưu CPU-only workload | Tăng phức tạp không cần thiết | Dùng fork/join thuần |
| Quên shutdown custom pool | Resource leak, thread tồn tại lâu | Shutdown/await theo owner |
| Shutdown common pool của toàn ứng dụng | Tác động task của component khác | Chỉ shutdown pool do mình sở hữu |
| Tin compensation không giới hạn | Có cấu hình hạn mức và OS resources | Capacity planning, metrics, giới hạn worker |
| Tự báo “nhanh hơn” không có benchmark | Kết luận hiệu năng không có căn cứ | Đo throughput, p99, CPU và correctness |

## 16. Bài tập thực hành kèm đáp án

### Bài 1 — Điều kiện trả true của isReleasable

Một latch có count=0. `isReleasable` nên trả gì?

**Đáp án:** `true` vì không cần chờ nữa. `ForkJoinPool.managedBlock` có thể hoàn tất ngay và không gọi `block`.

### Bài 2 — CountDownLatch chưa giải phóng

Latch count=1, `isReleasable` trả false. `block` gọi `await`. Điều gì phải xảy ra để thoát?

**Đáp án:** Có task/thread gọi `countDown` làm latch về 0, hoặc có interrupt/timeout theo implementation. ManagedBlocker không tự giảm count.

### Bài 3 — Giải thích compensation

Một worker ForkJoinPool bị chặn có quản lý. Pool có luôn tạo đúng một worker mới không?

**Đáp án:** Không. Pool *có thể* bù worker tùy trạng thái và giới hạn. Không có bảo đảm tăng đúng một thread hoặc bảo đảm đạt throughput cao hơn.

### Bài 4 — Ngoài pool

Main thread gọi `ForkJoinPool.managedBlock` cho một queue rỗng. Điều gì xảy ra?

**Đáp án:** Nó vẫn chạy logic kiểm tra/chờ, nhưng không có pool hiện tại để bù workers cho main thread.

### Bài 5 — Queue.poll

`isReleasable` gọi `queue.poll()` lấy được item nhưng không lưu lại. Có gì sai?

**Đáp án:** Item đã bị gỡ khỏi queue và bị bỏ rơi. Phải lưu vào trường `item` và trả lại cho caller sau managedBlock.

### Bài 6 — QueueTaker fast path

Queue có item sẵn. `isReleasable` trả true. Có cần gọi `queue.take` không?

**Đáp án:** Không. ManagedBlocker đã sẵn sàng và pool không cần bù worker vì điều kiện đã hoàn thành.

### Bài 7 — Sự khác nhau của hai boolean

`block()` trả `true` có đồng nghĩa pool đã bù được một worker không?

**Đáp án:** Không. Nó chỉ cho biết blocker không cần block thêm, không phải thông tin pool size.

### Bài 8 — Lặp isReleasable

Tại sao phải thiết kế `isReleasable` chịu được nhiều lần gọi?

**Đáp án:** `managedBlock` có thể kiểm tra điều kiện nhiều lần; nếu mỗi lần poll thêm item hoặc thao tác khác không idempotent thì có thể mất dữ liệu/lấy khóa nhiều lần.

### Bài 9 — Lặp block

Một ManagedBlocker có `block()` trả false để báo “chưa sẵn”. Sau đó điều gì có thể xảy ra?

**Đáp án:** `managedBlock` tiếp tục lặp kiểm tra `isReleasable` và có thể gọi `block` lại, cho tới khi một phương thức trả true hoặc xảy ra exception.

### Bài 10 — ForkJoinTask.join

Có nên bọc mọi lời gọi `ForkJoinTask.join()` trong ManagedBlocker không?

**Đáp án:** Không. ForkJoin đã có cơ chế nội bộ cho join. ManagedBlocker nhắm vào chờ ngoài mô hình fork/join như queue, latch hoặc lock.

### Bài 11 — Parallelism 1

Một waiter đang managedBlock trên latch; producer cũng được submit cùng pool mục tiêu parallelism=1. Vì sao chương trình demo vẫn tiến triển trên JDK 17 kiểm thử?

**Đáp án:** Pool có thể quản lý compensation khi biết worker đang chờ, cho producer có cơ hội chạy. Điều đó không đảm bảo mọi cấu hình/hạn mức đều có tiến triển.

### Bài 12 — InterruptedException

`block()` dùng `CountDownLatch.await` và bị interrupt. `managedBlock` xử lý ra sao?

**Đáp án:** `InterruptedException` được phép propagate. Caller phải có chính sách cancellation, propagate hoặc khôi phục interrupt status khi bắt.

### Bài 13 — Future timeout

`future.get(1,SECONDS)` timeout. Có chắc task đang managedBlock đã dừng không?

**Đáp án:** Không. Đây chỉ là timeout của waiter. Task có thể còn chờ; cần tín hiệu, cancellation policy hoặc timeout trong tài nguyên.

### Bài 14 — ReentrantLock

`isReleasable` dùng `lock.tryLock` và lấy được lock. `block` có phải luôn chạy không?

**Đáp án:** Không. `isReleasable` trả true là đủ. Caller phải bảo đảm `lock.unlock` bởi đúng thread đã lấy lock.

### Bài 15 — Deadlock logic

Task A chờ latch do task B phải mở, nhưng B lại chờ kết quả của A trước khi mở latch. ManagedBlocker có chữa được không?

**Đáp án:** Không. Đây là phụ thuộc vòng. Phải sửa workflow để có tiến triển độc lập.

### Bài 16 — Chọn executor

Hàng nghìn task chủ yếu chờ HTTP/network blocking, trong khi một tập tác vụ CPU đang chạy trong ForkJoinPool. Giải pháp nào đáng xem xét?

**Đáp án:** Tách blocking I/O sang dedicated executor hoặc xem xét virtual threads trên Java 21+, với giới hạn backend và timeout rõ. Không mặc định biến tất cả thành managedBlock của CPU pool.

### Bài 17 — Đo hiệu năng

Sau khi dùng ManagedBlocker, số thread tăng và throughput tăng nhẹ nhưng p99 gấp đôi. Có chắc đó là cải thiện toàn diện?

**Đáp án:** Không. Cần xét SLA tail latency, CPU, memory, backend pressure và khả năng vận hành.

### Bài 18 — Pool metrics

`pool.getPoolSize()` tại thời điểm T trả 2, nhưng parallelism=1. Có phải pool bị cấu hình sai?

**Đáp án:** Không nhất thiết. Pool có thể huy động thêm workers và metrics thay đổi động, đặc biệt khi managed blocking. Cần xem state/capacity, không chỉ một snapshot.

### Bài 19 — Shutdown

Custom ForkJoinPool còn task đang chờ queue. Gọi `shutdownNow` là đủ để đảm bảo mọi task đang `take` kết thúc chưa?

**Đáp án:** Không nên coi là bảo đảm trong mọi trạng thái. Phải có cancellation/signaling/resource cleanup, thu kết quả worker và kiểm tra termination.

### Bài 20 — Java version

`ManagedBlocker` có phải API đã lỗi thời sau Java 21 không?

**Đáp án:** Không. Nó vẫn là API chuẩn cho ForkJoinPool và phù hợp khi ứng dụng cần dùng work-stealing pool có điểm blocking. Java 21+ có thêm virtual threads như một lựa chọn khác cho một số workload, không làm ManagedBlocker trở thành deprecated.

## 17. Checklist thiết kế và QA

- [ ] Task chạy thật trong ForkJoinPool worker khi kỳ vọng compensation.
- [ ] Workload có đoạn **blocking ngoài fork/join join thông thường**, không phải CPU-only.
- [ ] Đã cân nhắc dùng dedicated executor hoặc mô hình async/virtual threads khi I/O dài và thường xuyên.
- [ ] `isReleasable` có nghĩa rõ ràng, không block lâu, chịu được nhiều lần gọi.
- [ ] Nếu `isReleasable` dùng `poll/tryLock`, đã lưu item hoặc trạng thái lock đúng.
- [ ] `block` chờ khi cần và trả true khi không cần block thêm.
- [ ] `block` có thể được gọi lại; không dựa vào số lần gọi cố định.
- [ ] Caller dùng `ForkJoinPool.managedBlock(blocker)`, không tự gọi `block()`.
- [ ] Có ownership cho blocker state và dữ liệu đầu ra.
- [ ] Không giả định target parallelism bằng số worker luôn tồn tại.
- [ ] Không assert compensation phải tạo chính xác một worker.
- [ ] Có timeout/cancel/interruption theo contract tài nguyên.
- [ ] `InterruptedException` được propagate hoặc khôi phục flag phù hợp.
- [ ] Không coi `Future.get(timeout)` là lệnh dừng underlying blocking task.
- [ ] Kiểm soát concurrency và backpressure, tránh chờ vô hạn hàng loạt.
- [ ] Có người tạo điều kiện giải phóng latch/queue/lock; tránh phụ thuộc vòng.
- [ ] Đã xác định lifecycle pool, chỉ shutdown pool do mình sở hữu.
- [ ] Có thể test cả đường fast path và đường thực sự cần chờ.
- [ ] Test được correctness và progress khi parallelism mục tiêu thấp.
- [ ] Không dùng `Thread.sleep` tùy tiện thay cho synchronization trong test.
- [ ] Theo dõi throughput, p95/p99, CPU, worker counts, queues và lỗi.
- [ ] Đã đọc hợp đồng API theo phiên bản JDK sử dụng.
- [ ] Không mô tả ManagedBlocker như API không đồng bộ hóa I/O hoặc bảo đảm tăng tốc.

## 18. Nguồn chính thức và tổng kết

Tài liệu Java SE chính thức:

- [Oracle JDK 17 — ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): hai phương thức `isReleasable`/`block`, yêu cầu kiểm tra lặp, ví dụ QueueTaker và ReentrantLock.
- [Oracle JDK 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): `managedBlock`, cơ chế có thể huy động worker dự phòng, các giới hạn và metric.
- [Oracle JDK 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork/join`, `getPool`, cơ chế task/cancellation.
- [Oracle JDK 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `poll`/`take` và ngữ nghĩa queue.
- [Oracle JDK 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): `await`, `countDown` và interruption.

**Kết luận:** `ForkJoinPool.ManagedBlocker` cho phép một task đang chạy trong ForkJoinPool mô tả **điểm có thể chặn** bằng `isReleasable()` và `block()`. Thay vì gọi một thao tác chờ trực tiếp rồi làm pool mất khả năng nhận biết worker đã blocked, caller dùng `ForkJoinPool.managedBlock(blocker)` để pool **có thể** cân nhắc bù worker khi cần.

Để dùng đúng, phải hiểu hai boolean là **điều kiện sẵn sàng**, không phải số lượng workers; thiết kế `isReleasable` an toàn khi gọi lặp; giữ kết quả từ `poll`; bảo đảm `block` kết thúc hoặc có chính sách timeout/cancel; và đánh giá khả năng cạn worker/resource. ManagedBlocker không chữa deadlock logic, không biến blocking I/O thành non-blocking và không là giải pháp mặc định cho toàn bộ network/database workloads. Khi cân nhắc kiến trúc, hãy đo tải thật và so với các mô hình concurrency phù hợp trong Java hiện đại.