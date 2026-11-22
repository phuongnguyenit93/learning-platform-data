# Race condition, cancellation và deadline trong Java 8+

> **Chủ đề cha:** Kiểm thử và tối ưu. Trong ứng dụng đa luồng, race condition làm kết quả phụ thuộc thứ tự thực thi; cancellation cho phép yêu cầu công việc dừng; deadline giới hạn thời gian toàn bộ công việc được phép tiêu thụ. Thiết kế đúng cần phối hợp Java Memory Model, đồng bộ hóa, interrupt hợp tác và một ngân sách thời gian dùng chung.

## 1. Mục tiêu

Sau bài này, bạn có thể nhận diện race condition/data race; phân biệt atomicity, visibility và ordering; chọn synchronized, Lock, Atomic classes hoặc concurrent collections; thiết kế cancellation bằng interrupt/Future; xử lý InterruptedException; phân biệt timeout với deadline; dùng System.nanoTime() để tính thời gian còn lại; truyền deadline qua queue/lock/retry/downstream; xử lý race giữa cancel và commit; đóng ExecutorService có kiểm soát; và kiểm thử các hành vi này bằng Java 8.

## 2. Race condition là gì?

**Race condition** xảy ra khi kết quả hoặc hành vi chương trình phụ thuộc vào thứ tự/timing của thao tác đồng thời. Một trường hợp phổ biến là *data race*: nhiều thread truy cập cùng dữ liệu chia sẻ, có ít nhất một thao tác ghi, nhưng không được đồng bộ đúng cách.

```java
class Counter {
    int value = 0;

    void increment() {
        value++;
    }
}
```

`value++` không phải một thao tác nguyên tử duy nhất. Về mặt logic, nó gồm đọc giá trị, tính giá trị mới rồi ghi lại. Nếu hai thread cùng đọc 0 trước khi một thread ghi, cả hai có thể cùng ghi 1. Kết quả cuối là 1 dù đã gọi increment hai lần. Đây là *lost update*.

### 2.1. Một interleaving gây mất cập nhật

Giả sử `value=0`:

| Thời điểm | Thread A | Thread B | value |
| --- | --- | --- | ---: |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Tính 1 | | 0 |
| 4 | | Tính 1 | 0 |
| 5 | Ghi 1 | | 1 |
| 6 | | Ghi 1 | 1 |

Mong đợi là 2, kết quả là 1. Việc chương trình chạy đúng vài lần không chứng minh code thread-safe; interleaving xấu có thể hiếm xuất hiện trên máy developer nhưng xảy ra khi tải cao hoặc môi trường khác.

### 2.2. Race condition rộng hơn data race

Không phải mọi race condition đều là truy cập biến không đồng bộ. Ví dụ hai request cùng kiểm tra tồn kho rồi cùng trừ hàng có thể gây oversell, ngay cả khi mỗi lần ghi riêng lẻ được bảo vệ. Đây là race giữa một chuỗi hành động nghiệp vụ (*check-then-act*).

```text
if (stock >= requested) {
    stock -= requested;
    acceptOrder();
}
```

Cần thực hiện kiểm tra và cập nhật như **một thao tác nguyên tử đối với invariant**. Khóa riêng câu lệnh trừ stock sau khi đã kiểm tra là chưa đủ; hai request vẫn có thể cùng nhìn thấy số lượng cũ.

### 2.3. Vì sao sleep không sửa được race?

Thêm Thread.sleep(10) trước hoặc sau lệnh ghi chỉ thay đổi xác suất interleaving. Nó không tạo mutual exclusion, atomicity hay happens-before. Khi CPU, scheduler, số core hoặc tải thay đổi, lỗi vẫn có thể xuất hiện. Dùng synchronization primitive để định nghĩa quan hệ đúng giữa các thread, không dùng delay để hy vọng chúng chạy theo thứ tự.

## 3. Bốn khái niệm cần tách biệt

| Khái niệm | Câu hỏi | Cơ chế thường dùng |
| --- | --- | --- |
| Atomicity | Thao tác có bị xen giữa và mất cập nhật không? | synchronized, Lock, atomic classes |
| Visibility | Thread khác có nhìn thấy giá trị đã ghi không? | volatile, monitor/lock, concurrent utilities |
| Ordering | Các thao tác có quan hệ happens-before không? | monitor, volatile, executor/future, synchronizers |
| Invariant | Nhiều field/bước nghiệp vụ có nhất quán cùng nhau không? | Một lock chung, transaction, immutable state/CAS |

Một giải pháp có thể bảo đảm một thuộc tính nhưng không bảo đảm các thuộc tính còn lại. Ví dụ volatile có visibility và ordering cho biến đó, nhưng không làm phép value++ trở thành atomic.

## 4. Java Memory Model và happens-before

Java Memory Model (JMM) xác định khi nào một thread được bảo đảm nhìn thấy hành động của thread khác. *Happens-before* là quan hệ thứ tự bộ nhớ: nếu A happens-before B, các ghi trước A được bảo đảm nhìn thấy bởi thao tác đọc sau B theo quy tắc JMM.

Một số quan hệ quan trọng:

- Unlock monitor happens-before lần lock tiếp theo trên cùng monitor.
- Ghi vào biến volatile happens-before các lần đọc tiếp theo của cùng biến theo quy tắc volatile.
- Các thao tác trước khi submit task vào ExecutorService happens-before hành động của task đó.
- Hành động trong computation happens-before thao tác sau khi caller lấy kết quả qua Future.get().
- Các thao tác trước CountDownLatch.countDown() happens-before thao tác sau await() thành công tương ứng.

Đồng bộ hóa vừa điều phối thực thi, vừa tạo bảo đảm visibility/ordering.

### 4.1. volatile không làm phép tăng atomic

```java
class PublishedState {
    volatile boolean ready;
    int data;

    void publish() {
        data = 42;
        ready = true;
    }
}
```

Nếu thread đọc `ready == true`, quy tắc volatile giúp nó nhìn thấy `data=42` đã ghi trước đó. Nhưng `volatile int count; count++` vẫn là read-modify-write, không atomic. Hai thread vẫn có thể đọc cùng giá trị rồi ghi đè nhau. Dùng AtomicInteger hoặc khóa nếu cần tăng chính xác.

### 4.2. Safe publication

Một object có thể được tạo đúng nhưng thread khác vẫn quan sát trạng thái không mong muốn nếu reference được chia sẻ mà không có publication phù hợp. Các cách phổ biến:
- Gán reference vào field volatile.
- Công bố/đọc reference dưới cùng synchronized lock.
- Lưu vào concurrent collection hoặc atomic reference.
- Khởi tạo trong static initializer.
- Dùng đúng final-field semantics và không để this thoát khỏi constructor.

Safe publication không làm object mutable tự nhiên trở nên thread-safe. Sau khi công bố, các thay đổi state vẫn cần synchronization hoặc thiết kế immutable.

## 5. Chọn công cụ sửa race

### 5.1. synchronized bảo vệ invariant nhiều bước

```java
class BankAccount {
    private long balance;

    public synchronized boolean withdraw(long amount) {
        if (amount < 0 || balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    public synchronized long balance() {
        return balance;
    }
}
```

Cả kiểm tra và cập nhật nằm trong cùng critical section. Mọi thread truy cập account phải dùng cùng monitor; nếu method khác đọc/ghi field mà bỏ khóa, invariant vẫn có thể bị phá. Giữ critical section ngắn, tránh gọi remote service, chờ I/O hoặc chạy callback không kiểm soát khi đang giữ monitor.

### 5.2. Atomic classes cho một biến độc lập

```java
AtomicInteger counter = new AtomicInteger();

int after = counter.incrementAndGet();
int previous = counter.getAndAdd(5);
```

AtomicInteger/AtomicLong cung cấp atomic read-modify-write cho một biến. compareAndSet(expected,updated) hữu ích khi state transition cần điều kiện:

```java
AtomicInteger state = new AtomicInteger(0);
boolean started = state.compareAndSet(0, 1);
```

Chỉ một thread chuyển state từ 0 sang 1 thành công. Atomic classes không tự bảo vệ nhiều biến cùng lúc; nếu nhiều field phải đổi nhất quán, dùng lock hoặc immutable state qua AtomicReference/CAS.

### 5.3. Lock khi cần timeout hoặc interruptible acquisition

ReentrantLock hỗ trợ lockInterruptibly() và tryLock(timeout,unit). Điều này hữu ích khi chờ khóa cũng phải tuân theo cancellation/deadline:

```java
if (!lock.tryLock(remainingNanos, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("lock deadline exceeded");
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

remainingNanos phải được tính từ cùng deadline của request; không cấp lại toàn bộ timeout mỗi lần thử. unlock() luôn nằm trong finally sau khi acquire thành công.

### 5.4. Concurrent collections và LongAdder

Dùng ConcurrentHashMap, BlockingQueue, CopyOnWriteArrayList hoặc concurrent utilities khi semantics của cấu trúc phù hợp. Các method putIfAbsent/computeIfAbsent có semantics atomic cho thao tác được mô tả; callback nên ngắn và tránh side effect khó lặp lại.

LongAdder phù hợp với counter thống kê có contention cao khi ưu tiên thông lượng. sum() không phải snapshot nguyên tử trong lúc cập nhật diễn ra. Không dùng nó làm số dư tài khoản, sequence number cần duy nhất hoặc điều kiện đồng bộ nghiệp vụ.


## 6. Cancellation: yêu cầu dừng công việc

Cancellation trong Java thường là **cooperative cancellation**: một thread yêu cầu task dừng; task phải có cơ hội nhận biết yêu cầu, dọn dẹp tài nguyên và kết thúc. Java không cung cấp cách an toàn để cưỡng ép một thread bất kỳ dừng ngay lập tức tại một instruction tùy ý.

Các API phổ biến:
- Thread.interrupt(): đặt interrupt status hoặc đánh thức thread đang chờ trong API interruptible.
- Future.cancel(boolean): yêu cầu hủy computation được đại diện bởi Future; tham số true cho phép implementation thử interrupt thread đang chạy nếu biết thread đó.
- ExecutorService.shutdown(): từ chối task mới, cho task đã submit hoàn tất.
- ExecutorService.shutdownNow(): best-effort ngắt task đang chạy và lấy task đang chờ khỏi queue; không bảo đảm task đang chạy đã kết thúc khi method trả về.

### 6.1. Interrupt là tín hiệu, không phải kill thread

Khi thread đang ở sleep, wait, join hoặc một số blocking operation interruptible, interrupt có thể làm method ném InterruptedException. Với nhiều thao tác blocking, exception được ném sau khi **interrupt status bị clear**.

Với CPU loop không gọi blocking API, interrupt thường chỉ đặt cờ. Task phải tự kiểm tra:

```java
while (!Thread.currentThread().isInterrupted()) {
    doOneSmallUnitOfWork();
}
cleanup();
```

Không viết vòng lặp vô hạn mà không có điểm kiểm tra cancellation, đặc biệt khi task chạy trong thread pool.

### 6.2. Xử lý InterruptedException đúng

Nếu method hiện tại có thể truyền exception lên caller, hãy khai báo throws InterruptedException. Nếu không thể truyền, thường cần khôi phục interrupt status trước khi thoát:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Không nuốt exception rồi tiếp tục chạy như chưa có gì. Thread.interrupted() đọc **và xóa** interrupt status; Thread.currentThread().isInterrupted() đọc trạng thái mà không xóa.

### 6.3. Vì sao không dùng Thread.stop()?

Dừng thread cưỡng ép có thể khiến lock/monitor và invariant bị bỏ dở trong trạng thái không nhất quán. Thread.stop() và các API điều khiển thread kiểu cưỡng ép đã deprecated từ lâu; không dùng chúng để implement cancellation. Hãy dùng interrupt, cancellation state, timeout, resource close và cleanup ở ranh giới an toàn.

## 7. Future.cancel và giới hạn thực tế

```java
Future<Result> future = executor.submit(task);

// Khi caller không còn cần kết quả:
boolean accepted = future.cancel(true);
```

- Nếu task chưa bắt đầu, executor sẽ không chạy task đó nếu cancellation thành công.
- Nếu task đã chạy, cancel(true) thử interrupt worker thread đã biết.
- Task có thể dừng nhanh nếu đang chờ trong API interruptible hoặc thường xuyên kiểm tra interrupt.
- Task bỏ qua interrupt, kẹt trong API không interruptible hoặc chạy native code có thể tiếp tục.
- isCancelled() và isDone() phản ánh trạng thái Future; chúng **không chứng minh side effect đã dừng**.

cancel(false) yêu cầu hủy mà không interrupt computation đang chạy. Nó vẫn có thể ngăn task chưa bắt đầu; không dùng nó nếu bạn cần đánh thức worker đang chờ.

### 7.1. Future.get(timeout) không tự hủy task

```java
try {
    Result result = future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true); // Gửi yêu cầu cancellation riêng.
}
```

get(timeout) chỉ giới hạn thời gian **caller chờ kết quả**. Khi hết timeout, task có thể vẫn đang chạy. Muốn yêu cầu dừng, phải gọi cancel hoặc một cancellation protocol phù hợp. Caller cũng phải xử lý ExecutionException, CancellationException và InterruptedException.

### 7.2. CompletableFuture trong Java 8 có khác biệt quan trọng

CompletableFuture hữu ích để ghép các stage bất đồng bộ. Nhưng trong Java 8, cancel(mayInterruptIfRunning) được xử lý như một kiểu exceptional completion với CancellationException. Tham số mayInterruptIfRunning **không có tác dụng** trong implementation này vì CompletableFuture không kiểm soát trực tiếp computation đã tạo ra nó.

Nếu cần interrupt worker thật sự, giữ tham chiếu Future từ ExecutorService.submit hoặc tự xây cancellation token/bridge có vòng đời rõ. Hủy một stage không mặc nhiên dừng network call, task nguồn hay mọi stage đã được tạo trước đó.

Các method orTimeout và completeOnTimeout xuất hiện từ Java 9, không có trong Java 8. Với module Java 8, dùng Future.get(timeout), ScheduledExecutorService hoặc deadline tự quản lý.

## 8. Deadline và timeout khác nhau thế nào?

**Timeout** thường là khoảng thời gian tối đa cho một thao tác chờ cụ thể, ví dụ chờ lock 100 ms hoặc chờ Future 200 ms.

**Deadline** là giới hạn thời gian của cả công việc. Nhiều bước dùng chung deadline:
- Chờ task được lấy khỏi queue.
- Acquire lock.
- Gọi downstream service.
- Thử lại sau lỗi tạm thời.
- Đọc/ghi I/O.
- Hoàn thành xử lý và commit.

Nếu mỗi tầng tự bắt đầu timeout 500 ms mới, request có 4 tầng có thể kéo dài gần 2 giây, chưa kể queue/retry. End-to-end deadline bảo đảm các tầng cùng tiêu thụ **một ngân sách thời gian**.

### 8.1. Dùng System.nanoTime() cho thời gian trôi qua

System.nanoTime() đo thời gian monotonic tương đối trong cùng JVM, không đại diện giờ UTC hay timestamp lịch. Nó phù hợp để đo elapsed time và timeout. Không dùng System.currentTimeMillis() để đo khoảng thời gian vì wall clock có thể bị chỉnh bởi đồng bộ thời gian hoặc thao tác hệ thống.

Để tránh tràn số khi cộng thời điểm kết thúc, dùng phép trừ:

```java
long started = System.nanoTime();
long budget = TimeUnit.MILLISECONDS.toNanos(500);

// Sau một bước xử lý:
long elapsed = System.nanoTime() - started;
long remaining = budget - elapsed;

if (remaining <= 0) {
    throw new TimeoutException("deadline exceeded");
}
```

Đừng kiểm tra System.nanoTime() >= started + budget. Phép cộng có thể overflow. Cách tính elapsed/remaining dùng hiệu hai giá trị, với khoảng đo thực tế nhỏ hơn khoảng 292 năm theo giới hạn signed long nanoseconds.

### 8.2. Một deadline, nhiều tầng

Tạo deadline **trước khi submit** để queue delay cũng được tính:

```java
long started = System.nanoTime();
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(500);

Future<Result> future = executor.submit(task);

long remaining = budgetNanos - (System.nanoTime() - started);
if (remaining <= 0) {
    future.cancel(true);
    throw new TimeoutException("request deadline exceeded");
}

Result result = future.get(remaining, TimeUnit.NANOSECONDS);
```

Mỗi tầng nhận cùng deadline/budget object hoặc tính remaining từ cùng mốc bắt đầu. Không tạo timeout mới ở mỗi lần gọi. Nếu retry, thời gian backoff cũng trừ vào ngân sách tổng.

nanoTime có origin tùy ý theo JVM; không serialize trực tiếp giá trị nanoTime để truyền sang JVM/máy khác. Deadline phân tán cần protocol rõ, ví dụ deadline theo wall clock có quy tắc clock-skew hoặc remaining budget có tính đến thời gian truyền và hop overhead.

### 8.3. Deadline không bảo đảm scheduler chạy đúng thời điểm

Timeout là giới hạn mà API cố gắng tuân thủ; scheduler/OS có thể khiến thread được đánh thức muộn. Không diễn giải timeout 100 ms thành cam kết CPU sẽ chạy lại chính xác sau 100 ms. API timed thường chờ ít nhất khoảng yêu cầu và phát hiện timeout theo best effort.

### 8.4. Timeout từng tầng có thể vượt deadline tổng

Một kết nối có connect timeout 300 ms và read timeout 300 ms không đồng nghĩa toàn bộ request hoàn tất trong 300 ms. Có thể có nhiều lần đọc, retry hoặc queue delay. Adapter I/O phải nhận remaining budget và cấu hình timeout tương ứng; nếu API chỉ cung cấp timeout từng thao tác, cần kiểm tra deadline giữa các thao tác.

## 9. Dùng remaining budget với các API timed

Tính remainingNanos từ cùng deadline rồi dùng cho từng lần chờ:

```java
long remaining = deadline.remainingNanos();
if (remaining <= 0) {
    throw new TimeoutException("expired");
}

if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("lock timeout");
}
try {
    // Critical section.
} finally {
    lock.unlock();
}
```

Các API thường có overload timeout:
- Future.get(timeout,unit).
- Lock.tryLock(timeout,unit).
- CountDownLatch.await(timeout,unit).
- BlockingQueue.poll(timeout,unit) và offer(timeout,unit).
- Condition.awaitNanos(nanos).
- ExecutorService.awaitTermination(timeout,unit).

Luôn kiểm tra giá trị trả về. Ví dụ CountDownLatch.await(timeout,unit) trả false khi hết thời gian; tryLock trả false nếu không lấy được lock; poll trả null khi không có phần tử trong thời hạn. Timeout không phải lúc nào cũng ném exception.

### 9.1. Retry và backoff phải tiêu thụ cùng deadline

```java
while (true) {
    long remaining = deadline.remainingNanos();
    if (remaining <= 0) {
        throw new TimeoutException("retry budget exhausted");
    }

    try {
        return callDownstream(remaining);
    } catch (TemporaryFailure failure) {
        long delay = computeBackoffNanos();
        remaining = deadline.remainingNanos();
        if (remaining <= delay) {
            throw new TimeoutException("no budget for retry");
        }
        TimeUnit.NANOSECONDS.sleep(delay);
    }
}
```

Đây là pseudocode cần đặt trong method có throws InterruptedException, TimeoutException. Backoff không được reset deadline. Nếu sleep bị interrupt, hãy truyền interruption lên caller hoặc khôi phục interrupt status theo hợp đồng của method.

## 10. Race giữa cancellation và completion

Một task có thể hoàn thành đúng lúc caller gửi cancel:
- Task đã hoàn thành trước: cancel có thể trả false.
- Task chưa hoàn thành: cancel có thể thành công và đánh dấu Future cancelled.
- Task đã thực hiện side effect nhưng chưa publish kết quả: caller có thể thấy cancelled trong khi side effect đã xảy ra.
- Task bỏ qua interrupt: Future đã cancelled nhưng code bên dưới vẫn có thể tiếp tục chạy.

Do đó cancellation không phải rollback.

### 10.1. Đặt ranh giới commit rõ ràng

Với thao tác nghiệp vụ, tách:
1. Tính toán/chuẩn bị dữ liệu.
2. Kiểm tra cancellation/deadline.
3. Commit bằng transaction hoặc thao tác atomic.
4. Trả kết quả.

Nếu cancellation đến sau khi commit thành công, ứng dụng phải xử lý như một kết quả đã commit, không giả vờ dữ liệu chưa thay đổi. Với request retry, dùng idempotency key/deduplication để tránh chạy side effect hai lần.

Một kiểm tra isInterrupted() ngay trước commit chỉ giảm cửa sổ race, không tự tạo atomicity giữa kiểm tra và commit. Nếu phải bảo đảm cancel thắng commit hoặc commit thắng cancel, cần state machine/lock/transaction điều phối hai sự kiện.

### 10.2. Atomic state transition khi cần một bên thắng

```java
AtomicInteger state = new AtomicInteger(0);
// 0 = RUNNING, 1 = CANCELLED, 2 = COMMITTED

boolean cancellationWon = state.compareAndSet(0, 1);
boolean commitWon = state.compareAndSet(0, 2);
```

Chỉ một transition từ RUNNING có thể thắng. Ví dụ này chỉ bảo vệ state transition trong bộ nhớ; nếu commit liên quan database, cần transaction/conditional update đồng bộ với state nghiệp vụ. AtomicInteger cục bộ không thay thế transaction phân tán.

## 11. Executor lifecycle và cancellation

ExecutorService.shutdown() ngăn task mới và cho task đã submit hoàn tất. Nó **không chờ** tất cả task kết thúc. Muốn chờ, gọi awaitTermination.

shutdownNow() cố gắng interrupt task đang chạy và trả về task chưa bắt đầu; nó cũng không đợi task đang chạy kết thúc. Worker bỏ qua interrupt có thể giữ pool sống lâu hơn dự kiến.

Một pattern shutdown hai pha:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
            // Ghi nhận pool chưa dừng.
        }
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Thời hạn chờ shutdown nên theo lifecycle/service deadline. Không bỏ qua kết quả awaitTermination; ghi nhận task không chịu dừng để điều tra. Không tạo thread pool mới cho từng request nếu không có kế hoạch quản lý tài nguyên.

## 12. Kiểm thử concurrency đúng cách

Test concurrency không nên chỉ chạy một vòng rồi hy vọng race xuất hiện. Cần điều khiển interleaving:
- Dùng CountDownLatch để đồng bộ thời điểm bắt đầu/hoàn thành.
- Dùng CyclicBarrier để ép nhiều thread cùng vượt một điểm trước khi ghi.
- Dùng Future.get(timeout) để test không treo vô hạn.
- Dùng timeout tổng cho test suite và cleanup executor trong finally.
- Test cancellation ở trạng thái queued, đang chạy, đã hoàn thành và đang commit.
- Test interruption khi task chờ và khi task chạy CPU loop.
- Kiểm tra side effect, không chỉ Future.isCancelled().
- Dùng stress test/JCStress khi cần tìm race ở memory-model level; một test đơn giản không chứng minh tuyệt đối thread-safe.

Không dựa vào Thread.sleep để điều phối interleaving. Sleep chỉ có thể dùng cho test thời gian với biên rộng; latch/barrier giúp test tái lập và ít flaky hơn.


## 13. Chương trình Java 8 hoàn chỉnh

Chương trình dưới đây kiểm tra:
- Ép hai thread đọc cùng giá trị trước khi ghi để tái hiện lost update.
- Dùng AtomicInteger để giữ đủ hai lần tăng.
- Tạo deadline monotonic và chờ ngân sách hết.
- Dùng Future.get(timeout) giới hạn thời gian chờ, sau đó chủ động cancel(true).
- Task bắt InterruptedException, ghi nhận tín hiệu và khôi phục interrupt status.
- Kiểm tra kết quả bằng AssertionError; không cần -ea.

Lưu thành `RaceCancellationDeadlineDemo.java`:


```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class RaceCancellationDeadlineDemo {
    static final class UnsafeCounter {
        int value;

        void increment(CyclicBarrier gate) throws Exception {
            int observed = value;
            gate.await(1, TimeUnit.SECONDS);
            value = observed + 1;
        }
    }

    static final class Deadline {
        private final long startedAtNanos;
        private final long budgetNanos;

        private Deadline(long budgetNanos) {
            this.startedAtNanos = System.nanoTime();
            this.budgetNanos = budgetNanos;
        }

        static Deadline after(long timeout, TimeUnit unit) {
            if (timeout <= 0) {
                throw new IllegalArgumentException("timeout must be positive");
            }
            long nanos = unit.toNanos(timeout);
            return new Deadline(nanos);
        }

        long remainingNanos() {
            long elapsed = System.nanoTime() - startedAtNanos;
            long remaining = budgetNanos - elapsed;
            return remaining > 0 ? remaining : 0L;
        }

        boolean isExpired() {
            return remainingNanos() == 0L;
        }
    }

    private static void stop(ExecutorService executor) {
        executor.shutdownNow();
        try {
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("executor did not terminate");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService racePool = Executors.newFixedThreadPool(2);
        int unsafeValue;
        int atomicValue;
        try {
            UnsafeCounter unsafe = new UnsafeCounter();
            CyclicBarrier unsafeGate = new CyclicBarrier(2);
            Future<?> unsafeA = racePool.submit(() -> {
                unsafe.increment(unsafeGate);
                return null;
            });
            Future<?> unsafeB = racePool.submit(() -> {
                unsafe.increment(unsafeGate);
                return null;
            });
            unsafeA.get(2, TimeUnit.SECONDS);
            unsafeB.get(2, TimeUnit.SECONDS);
            unsafeValue = unsafe.value;

            AtomicInteger safe = new AtomicInteger(0);
            CyclicBarrier safeGate = new CyclicBarrier(2);
            Future<?> safeA = racePool.submit(() -> {
                safeGate.await(1, TimeUnit.SECONDS);
                safe.incrementAndGet();
                return null;
            });
            Future<?> safeB = racePool.submit(() -> {
                safeGate.await(1, TimeUnit.SECONDS);
                safe.incrementAndGet();
                return null;
            });
            safeA.get(2, TimeUnit.SECONDS);
            safeB.get(2, TimeUnit.SECONDS);
            atomicValue = safe.get();
        } finally {
            stop(racePool);
        }

        Deadline deadline = Deadline.after(25, TimeUnit.MILLISECONDS);
        boolean initiallyPositive = deadline.remainingNanos() > 0;
        TimeUnit.NANOSECONDS.sleep(deadline.remainingNanos());
        boolean expired = deadline.isExpired();

        ExecutorService cancellationPool =
                Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch interruptObserved = new CountDownLatch(1);
        AtomicBoolean workerSawInterrupt = new AtomicBoolean(false);
        Future<String> future;
        boolean timedOut;
        boolean cancellationAccepted;
        boolean workerStoppedCooperatively;
        boolean markedCancelled;
        boolean getReportedCancellation;

        try {
            future = cancellationPool.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                    return "unexpected completion";
                } catch (InterruptedException ex) {
                    workerSawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    interruptObserved.countDown();
                    return "interrupted";
                }
            });

            require(started.await(1, TimeUnit.SECONDS),
                    "worker did not start");

            timedOut = false;
            try {
                future.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }

            cancellationAccepted = future.cancel(true);
            workerStoppedCooperatively =
                    interruptObserved.await(1, TimeUnit.SECONDS);
            markedCancelled = future.isCancelled();

            getReportedCancellation = false;
            try {
                future.get();
            } catch (CancellationException expected) {
                getReportedCancellation = true;
            }
        } finally {
            stop(cancellationPool);
        }

        System.out.println("unsafe counter after two increments: "
                + unsafeValue);
        System.out.println("atomic counter after two increments: "
                + atomicValue);
        System.out.println("deadline initially had budget: "
                + initiallyPositive);
        System.out.println("deadline expired: " + expired);
        System.out.println("Future.get timed out: " + timedOut);
        System.out.println("Future.cancel(true) accepted: "
                + cancellationAccepted);
        System.out.println("worker observed interrupt: "
                + workerStoppedCooperatively);
        System.out.println("Future marked cancelled: " + markedCancelled);
        System.out.println("Future.get reports cancellation: "
                + getReportedCancellation);

        require(unsafeValue == 1, "expected deterministic lost update");
        require(atomicValue == 2, "atomic counter lost an update");
        require(initiallyPositive, "deadline had no initial budget");
        require(expired, "deadline did not expire");
        require(timedOut, "Future.get did not time out");
        require(cancellationAccepted, "cancellation was not accepted");
        require(workerStoppedCooperatively && workerSawInterrupt.get(),
                "worker did not observe cancellation interrupt");
        require(markedCancelled && getReportedCancellation,
                "Future cancellation state was not observed");
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 9+ với target/API Java 8:

```bash
javac --release 8 RaceCancellationDeadlineDemo.java
java RaceCancellationDeadlineDemo
```

Trên JDK 8, dùng `javac RaceCancellationDeadlineDemo.java` và `java RaceCancellationDeadlineDemo`.

**Stdout thực tế đã kiểm thử trên JDK 24:**

```text
unsafe counter after two increments: 1
atomic counter after two increments: 2
deadline initially had budget: true
deadline expired: true
Future.get timed out: true
Future.cancel(true) accepted: true
worker observed interrupt: true
Future marked cancelled: true
Future.get reports cancellation: true
Checks passed.
```

```text
unsafe counter after two increments: 1
atomic counter after two increments: 2
deadline initially had budget: true
deadline expired: true
Future.get timed out: true
Future.cancel(true) accepted: true
worker observed interrupt: true
Future marked cancelled: true
Future.get reports cancellation: true
Checks passed.
```

### 13.1. Giải thích kết quả

- Hai task của UnsafeCounter đọc cùng giá trị trước khi cùng vượt CyclicBarrier; mỗi task tính 0+1 và ghi 1. Kết quả cuối là 1 dù hai lần increment đã chạy.
- AtomicInteger.incrementAndGet() là một thao tác read-modify-write nguyên tử, nên hai lần tăng cho kết quả 2.
- Deadline lưu thời điểm bắt đầu và budget, rồi tính remaining bằng hiệu nanoTime; ví dụ chờ ngân sách 25 ms kết thúc với trạng thái expired.
- Future.get(20 ms) timeout vì worker đang chờ CountDownLatch chưa được mở. Timeout chỉ dừng caller chờ.
- cancel(true) gửi interrupt đến worker đang chạy. Worker đang ở await() nhận InterruptedException, ghi nhận tín hiệu, khôi phục interrupt status rồi thoát.
- Future được đánh dấu cancelled và get() ném CancellationException; điều đó phản ánh trạng thái Future. Chương trình còn đợi latch để xác nhận worker thực sự đã quan sát interrupt.
- Checks passed chỉ in sau khi mọi điều kiện được kiểm tra bằng AssertionError chủ động.

**Giới hạn của demo:** UnsafeCounter cố ý chứa data race và chỉ dùng để tái hiện lỗi. Deadline là monotonic budget trong cùng JVM, không phải timestamp để truyền sang máy khác. Cancellation test dùng CountDownLatch interruptible; task không interruptible sẽ cần cơ chế dừng phù hợp với API/tài nguyên đang sử dụng.

## 14. Mẫu deadline có thể tái sử dụng

Một lớp Deadline nhỏ giúp các tầng dùng chung một mốc bắt đầu và ngân sách:

```java
final class Deadline {
    private final long startedAtNanos = System.nanoTime();
    private final long budgetNanos;

    Deadline(long timeout, TimeUnit unit) {
        if (timeout <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        this.budgetNanos = unit.toNanos(timeout);
    }

    long remainingNanos() {
        long elapsed = System.nanoTime() - startedAtNanos;
        long remaining = budgetNanos - elapsed;
        return remaining > 0 ? remaining : 0L;
    }

    boolean isExpired() {
        return remainingNanos() == 0L;
    }

    void throwIfExpired() throws TimeoutException {
        if (isExpired()) {
            throw new TimeoutException("deadline exceeded");
        }
    }
}
```

Ví dụ gọi qua nhiều tầng:

```java
Result handle(Request request, Deadline deadline)
        throws InterruptedException, ExecutionException, TimeoutException {
    deadline.throwIfExpired();

    long remaining = deadline.remainingNanos();
    Future<Result> future = executor.submit(
            () -> service.call(request));

    remaining = deadline.remainingNanos();
    if (remaining == 0) {
        future.cancel(true);
        throw new TimeoutException("request expired");
    }

    try {
        return future.get(remaining, TimeUnit.NANOSECONDS);
    } catch (TimeoutException ex) {
        future.cancel(true);
        throw ex;
    }
}
```

Snippet cần đặt trong class có field executor và các kiểu Request/Result phù hợp. Deadline phải được tạo ở entry point trước khi request xếp hàng; tạo nó sau khi task bắt đầu sẽ bỏ sót queue delay. Các tầng downstream nhận cùng object deadline hoặc cùng mốc/budget, không tạo một ngân sách mới.

### 14.1. Chuyển deadline qua biên process

Giá trị nanoTime không có ý nghĩa ngoài JVM đã tạo nó. Không gửi nguyên số nanoTime qua RPC, lưu database hoặc so sánh giữa hai host. Với hệ thống phân tán, chọn một protocol:
- Truyền deadline wall-clock theo UTC, xác định chính sách clock skew và đồng bộ đồng hồ.
- Truyền remaining budget nhưng trừ cả thời gian gửi/truyền/queue theo cách được protocol định nghĩa.
- Dùng metadata deadline chuẩn của RPC framework nếu framework cung cấp semantics end-to-end.

Không cộng lại timeout mặc định ở từng service vì cách đó làm tổng thời gian vượt SLA của request ban đầu.

## 15. Cancellation token cho tác vụ không sở hữu thread

Đôi khi một component không giữ Future hoặc không điều khiển thread trực tiếp. Có thể truyền một cancellation token:

```java
final class CancellationToken {
    private final AtomicBoolean cancelled = new AtomicBoolean();

    void cancel() {
        cancelled.set(true);
    }

    boolean isCancelled() {
        return cancelled.get();
    }

    void throwIfCancelled() {
        if (isCancelled()) {
            throw new CancellationException();
        }
    }
}
```

Worker kiểm tra token ở các điểm an toàn, ví dụ giữa các batch hoặc trước commit. Token không tự đánh thức thread đang block; nếu task chờ I/O/queue, cần interrupt hoặc đóng resource tương ứng. Có thể kết hợp token với deadline để task dừng khi **bị hủy hoặc hết thời gian**.

Không dùng một AtomicBoolean chung cho nhiều request độc lập nếu cancellation của request A có thể làm dừng request B. Token nên có scope rõ theo một operation/request.

## 16. Scheduled cancellation và timeout orchestration

ScheduledExecutorService có thể lên lịch gửi cancellation khi deadline hết:

```java
ScheduledFuture<?> alarm = scheduler.schedule(
        () -> taskFuture.cancel(true),
        remainingNanos,
        TimeUnit.NANOSECONDS);

try {
    return taskFuture.get(remainingNanos, TimeUnit.NANOSECONDS);
} finally {
    alarm.cancel(false);
}
```

Đây là pattern minh họa, cần quản lý race giữa task completion và timer firing. Hủy timer trong finally để không giữ task/tài nguyên thừa; timer callback phải idempotent và không thực hiện side effect nghiệp vụ. Nếu dùng get(timeout) cùng remaining như ví dụ, timer thường chỉ cần thiết khi hệ thống khác cần nhận tín hiệu cancellation, không phải để caller tự timeout.

Không tạo ScheduledExecutorService mới cho mỗi request. Dùng scheduler có lifecycle được quản lý, đặt giới hạn queue/metric phù hợp và bảo đảm shutdown. Nếu callback timeout và task completion cùng xảy ra, state machine/atomic transition quyết định trạng thái cuối.

## 17. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ count++ là atomic | Lost update | AtomicInteger hoặc lock |
| Chỉ thêm volatile cho count++ | Có visibility nhưng vẫn mất cập nhật | Atomic read-modify-write |
| Dùng sleep để tránh race | Lỗi chỉ ít xuất hiện hơn | Synchronization primitive |
| Khóa riêng thao tác ghi sau check | Check-then-act vẫn race | Khóa toàn invariant |
| Dùng AtomicInteger cho nhiều field liên quan | State có thể không nhất quán | Một lock hoặc immutable aggregate |
| Coi cancel(true) là kill thread | Task có thể bỏ qua interrupt | Cooperative cancellation và cleanup |
| Coi Future.get(timeout) tự hủy task | Task vẫn chạy sau TimeoutException | Gọi cancel/đóng resource rõ ràng |
| Nuốt InterruptedException | Caller mất tín hiệu cancellation | Propagate hoặc restore interrupt |
| Dùng Thread.interrupted() chỉ để kiểm tra | Vô tình clear cờ | Dùng isInterrupted() |
| Coi Future.isCancelled() chứng minh task đã dừng | Side effect có thể còn chạy | Quan sát task termination/cleanup |
| Hủy CompletableFuture và mong worker bị interrupt | Java 8 CompletableFuture không điều khiển worker | Giữ Future task thực hoặc token |
| Tạo timeout mới ở mỗi service | Tổng thời gian vượt request SLA | Truyền chung deadline |
| Dùng currentTimeMillis để đo elapsed | Clock có thể nhảy | nanoTime |
| So sánh now >= start + timeout | Có thể overflow | now - start >= timeout |
| Truyền nanoTime giữa máy | Origin khác nhau | Protocol deadline/remaining budget |
| Nghĩ timeout đảm bảo scheduler chạy đúng hạn | Thread có thể được đánh thức muộn | Thiết kế biên thời gian và quan sát latency |
| Dùng shutdownNow rồi giả định pool đã dừng | Task không interruptible có thể còn chạy | awaitTermination và kiểm tra kết quả |
| Commit rồi mới kiểm tra cancellation | Side effect đã xảy ra | Định nghĩa ranh giới commit/state machine |
| Retry reset timeout | Request kéo dài theo số lần retry | Dùng remaining budget chung |

## 18. Kiểm thử và vận hành trong production

### 18.1. Test race có chủ đích

Dùng latch/barrier để buộc các thread gặp nhau ở điểm đã chọn. Kiểm tra invariant sau khi tất cả Future hoàn tất; đặt timeout để test không treo. Với race ở cấp Java Memory Model, dùng stress testing hoặc JCStress để tăng độ tin cậy; một unit test không chứng minh mọi interleaving đều an toàn.

### 18.2. Test cancellation ở nhiều trạng thái

Kiểm tra task còn trong queue khi cancel; task đang block ở interruptible method; task đang chạy CPU loop và có điểm kiểm tra interrupt; task bỏ qua interrupt hoặc chờ API không hỗ trợ interrupt; task đã commit nhưng Future chưa được caller quan sát; caller bị interrupt trong khi gọi Future.get hoặc await; timer timeout và task completion xảy ra gần như đồng thời.

Xác minh cả trạng thái Future, thread/task termination, resource cleanup và side effect. Không chỉ assert isCancelled().

### 18.3. Metric và log hữu ích

Theo dõi số request/task timeout theo tầng và tổng deadline; queue wait, lock wait, downstream latency và retry/backoff; số task cancellation được yêu cầu, số worker nhận interrupt và số task còn chạy sau cancel; executor active count, queue depth, rejected task và thời gian shutdown; số race/invariant violation và số lần CAS retry nếu có.

Không log dữ liệu nhạy cảm hoặc toàn bộ payload chỉ để debug concurrency. Correlation ID và operation ID thường đủ để nối log giữa các tầng.

### 18.4. Deadline cần có budget cho cleanup

Nếu deadline nghiệp vụ đã hết, task có thể vẫn cần một khoảng ngắn để rollback/close file/return connection. Phân biệt thời gian hoàn tất công việc chính với thời gian cleanup; không để cleanup bị bỏ qua vì caller đã timeout. Cleanup phải bounded, idempotent và không giữ lock quá lâu.

## 19. Phân biệt API Java 8 với API bổ sung ở các phiên bản mới

Các API cốt lõi dùng trong bài có từ Java 5–8: ExecutorService/Future, interrupt, synchronized, Lock, AtomicInteger, CountDownLatch, CyclicBarrier, ScheduledExecutorService, CompletableFuture và TimeUnit. Đây là những API hiện hành và vẫn phù hợp với Java 8 module.

Một số tiện ích xuất hiện sau Java 8:
- CompletableFuture.orTimeout/completeOnTimeout: từ Java 9.
- ExecutorService.close(): từ Java 19.
- Virtual threads: từ Java 21.

Các API mới có thể hữu ích trên JDK mới, nhưng không được dùng trong source phải compile với Java 8. Không dựa vào Thread.stop/suspend/resume hoặc các cơ chế cưỡng ép thread cũ để thiết kế cancellation.

## 20. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 8 — Thread](https://docs.oracle.com/javase/8/docs/api/java/lang/Thread.html): interrupt, isInterrupted, interrupted và cách InterruptedException ảnh hưởng interrupt status.
- [Oracle Java SE 8 — Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html): cancel, get(timeout), isCancelled và isDone.
- [Oracle Java SE 8 — CompletableFuture](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html): cancellation không dùng interrupt để điều khiển computation.
- [Oracle Java SE 26 — System.nanoTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): monotonic elapsed time và cách so sánh timeout tránh overflow.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): semantics cancel/get và best-effort interruption.
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow, awaitTermination và memory consistency.
- [Oracle Java SE 26 — AtomicInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic increment/CAS và side-effect-free update function.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lockInterruptibly và tryLock(timeout).
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): await(timeout), interruption và happens-before.
- [Java Language Specification — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): monitor, synchronization và Java Memory Model.

**Ghi nhớ:** Race condition cần được giải quyết bằng atomicity, visibility và invariant phù hợp. Cancellation là tín hiệu hợp tác; interrupt không phải lệnh kill. Timeout giới hạn một lần chờ, còn deadline là ngân sách chung của toàn bộ request. Dùng nanoTime để tính remaining, truyền deadline qua mọi tầng, xử lý cancellation/commit race và xác minh task thực sự đã dừng trước khi coi công việc hoàn tất.
