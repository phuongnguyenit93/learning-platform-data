# Khóa, điều kiện chờ và khả năng hiển thị trạng thái giữa các luồng

Một ứng dụng Java có nhiều luồng thường chia sẻ dữ liệu và tài nguyên: worker đọc cấu hình, scheduler cập nhật trạng thái, request thread ghi vào cache, còn một tác vụ nền theo dõi tiến độ. Nếu các luồng truy cập cùng dữ liệu mà không có cơ chế phối hợp phù hợp, chương trình có thể gặp race condition, đọc giá trị cũ, cập nhật bị mất hoặc rơi vào deadlock.

Trong ứng dụng dùng CRaC, những vấn đề này còn liên quan trực tiếp đến thời điểm checkpoint. Trước khi lưu trạng thái tiến trình, ứng dụng cần đưa các luồng về ranh giới an toàn: không còn cập nhật dữ liệu dở dang, không còn tác vụ sử dụng tài nguyên sắp đóng và các điều kiện chia sẻ được bảo vệ nhất quán. Sau restore, các luồng cần tiếp tục từ trạng thái hợp lệ và chỉ chạy lại khi dependency đã sẵn sàng.

Để làm được điều đó, cần hiểu ba khái niệm nền tảng: **khóa (lock)** bảo vệ vùng dữ liệu dùng chung; **điều kiện chờ (condition)** cho phép luồng ngủ cho đến khi một trạng thái mong muốn xuất hiện; **khả năng hiển thị (visibility)** bảo đảm thay đổi của một luồng có thể được luồng khác quan sát theo Java Memory Model.

## 1. Vì sao nhiều luồng cần phối hợp?

Giả sử hai worker cùng tăng một bộ đếm:

```java
counter++;
```

Lệnh trên trông như một thao tác đơn, nhưng thực tế gồm các bước đọc giá trị hiện tại, tính giá trị mới và ghi lại. Nếu hai luồng cùng đọc giá trị `10`, cả hai có thể cùng tính ra `11` rồi ghi `11`. Kết quả cuối là `11` thay vì `12`. Đây là lost update, một dạng race condition.

Một vấn đề khác là visibility. Luồng A ghi `running = false`, nhưng luồng B không có quan hệ đồng bộ phù hợp. JVM và CPU có thể cho phép luồng B tiếp tục quan sát giá trị cũ trong một khoảng thời gian không xác định theo mô hình bộ nhớ Java. Vì vậy, vòng lặp sau không phải cách dừng thread an toàn:

```java
boolean running = true;

// Thread worker
while (running) {
    doWork();
}

// Thread quản lý
running = false;
```

Không có quan hệ happens-before giữa thao tác ghi và đọc `running`, nên worker không được bảo đảm nhìn thấy thay đổi. Cần dùng `volatile`, khóa hoặc một cơ chế đồng bộ phù hợp.

Trong ứng dụng thực tế, các lỗi đồng thời thường xuất hiện khi:

- Nhiều thread cập nhật cùng một object hoặc collection.
- Một thread kiểm tra trạng thái trong khi thread khác thay đổi trạng thái đó.
- Một worker đợi dữ liệu nhưng không được đánh thức đúng lúc.
- Một thread đóng connection hoặc executor trong khi thread khác vẫn sử dụng.
- Nhiều thread lấy khóa theo thứ tự khác nhau và chờ lẫn nhau.
- Checkpoint bắt đầu trong khi một nghiệp vụ đang cập nhật nhiều trường liên quan.

## 2. Khả năng hiển thị theo Java Memory Model

Java Memory Model (JMM) định nghĩa cách các thread nhìn thấy thao tác đọc và ghi bộ nhớ của nhau. Một thread không nhất thiết quan sát mọi thao tác của thread khác theo đúng thứ tự mã nguồn nếu không có quan hệ đồng bộ được JMM công nhận.

Điểm quan trọng là **happens-before**. Nếu thao tác A happens-before thao tác B, các thay đổi bộ nhớ trước A được bảo đảm hiển thị cho B theo các quy tắc của JMM.

Một số quan hệ happens-before thường dùng:

| Quan hệ | Ý nghĩa thực tế |
|---|---|
| Unlock một monitor happens-before lock tiếp theo trên cùng monitor | Thay đổi trong `synchronized` được thread lấy cùng khóa sau đó nhìn thấy |
| Ghi một biến `volatile` happens-before lần đọc tiếp theo của biến đó | Thread đọc thấy giá trị được công bố qua biến volatile và các thao tác trước lần ghi |
| Gọi `Thread.start()` happens-before các thao tác trong thread mới | Thread mới nhìn thấy trạng thái đã thiết lập trước khi gọi `start()` |
| Mọi thao tác trong một thread happens-before thread khác trả về thành công từ `join()` | Thread gọi `join()` nhìn thấy kết quả do thread đã kết thúc tạo ra |
| Thao tác trước khi đưa phần tử vào concurrent collection/queue được công bố theo hợp đồng của collection | Thread lấy phần tử có thể quan sát dữ liệu được chuẩn bị trước khi đưa vào |
| `countDown()` happens-before hành động tiếp theo sau một `await()` thành công trên cùng `CountDownLatch` | Thread chờ có thể quan sát kết quả được công bố trước khi đếm về 0 |

Không cần ghi nhớ mọi quy tắc trong một lần. Khi chia sẻ trạng thái, hãy xác định cơ chế đồng bộ nào tạo ra quan hệ happens-before giữa writer và reader.

### 2.1. Visibility khác atomicity

Visibility là khả năng một thread nhìn thấy thay đổi của thread khác. Atomicity là tính không thể bị quan sát ở trạng thái thực hiện dở dang đối với thao tác được bảo vệ. Hai khái niệm liên quan nhưng không giống nhau.

Ví dụ:

```java
private volatile int count;

public void increment() {
    count++;
}
```

`volatile` giúp các lần đọc/ghi biến `count` có ngữ nghĩa visibility và ordering theo JMM, nhưng `count++` vẫn là thao tác đọc–sửa–ghi. Hai thread có thể cùng đọc một giá trị rồi ghi đè kết quả của nhau. `volatile` không biến phép tăng thành atomic operation.

Nếu cần tăng bộ đếm độc lập, dùng `AtomicInteger`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int current() {
        return count.get();
    }
}
```

Nếu nhiều trường phải thay đổi như một invariant, chẳng hạn `balance` và `reservedAmount`, một atomic cho từng trường có thể chưa đủ. Khi đó cần một khóa bao quanh toàn bộ thao tác hoặc một cấu trúc dữ liệu nguyên tử được thiết kế cho invariant đó.

## 3. `synchronized` và intrinsic monitor

Từ khóa `synchronized` sử dụng monitor gắn với một object. Tại một thời điểm, chỉ một thread có thể sở hữu monitor đó. Thread khác muốn vào vùng `synchronized` trên cùng monitor phải chờ.

Ví dụ bảo vệ bộ đếm:

```java
public final class SafeCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
```

Hai method instance trên khóa cùng monitor `this`. Vì vậy, `increment()` và `get()` không chạy đồng thời trên cùng object. Khi một thread thoát khỏi vùng synchronized, thao tác unlock monitor happens-before lần lock tiếp theo trên cùng monitor. Điều này vừa bảo vệ atomicity của vùng code, vừa cung cấp visibility cho dữ liệu được bảo vệ.

Có thể dùng block `synchronized` để chọn phạm vi khóa:

```java
public void update() {
    validateInput();

    synchronized (stateLock) {
        updateSharedState();
    }

    publishMetric();
}
```

Chỉ phần cập nhật dữ liệu dùng chung cần khóa. Việc kiểm tra đầu vào hoặc ghi metric có thể ở ngoài vùng khóa nếu không phụ thuộc vào invariant đang bảo vệ.

### 3.1. Khóa trên object nào?

Không nên dùng một object dễ bị thay thế hoặc bị code bên ngoài khóa tùy ý. Có thể tạo một object riêng:

```java
private final Object stateLock = new Object();
```

Các thread cần phối hợp phải sử dụng đúng object khóa đó. Hai block `synchronized` trên hai object khác nhau không bảo vệ cùng một trạng thái.

Tránh khóa trên:

- String literal như `"LOCK"`, vì string có thể được intern và dùng chung ngoài ý muốn.
- Object công khai như `this` khi caller có thể đồng bộ trên cùng instance.
- Một object reference có thể bị gán lại, khiến các thread khóa trên những monitor khác nhau.
- Class object toàn cục nếu không cần khóa toàn bộ instance của class.

### 3.2. Monitor là reentrant

Java intrinsic monitor có tính reentrant: thread đang sở hữu monitor có thể vào một vùng `synchronized` khác trên cùng monitor mà không tự deadlock. Số lần vào được quản lý theo ownership của thread; thread phải thoát tương ứng khỏi các vùng synchronized trước khi monitor được nhả cho thread khác.

Tính reentrant không có nghĩa mọi thiết kế lồng khóa đều an toàn. Nếu thread A khóa X rồi Y, trong khi thread B khóa Y rồi X, hai thread vẫn có thể deadlock.

## 4. `wait`, `notify` và `notifyAll`

`Object.wait()`, `notify()` và `notifyAll()` phối hợp các thread thông qua monitor của object.

- `wait()` yêu cầu thread đang sở hữu monitor nhả monitor và chờ.
- `notify()` đánh thức một thread đang chờ trên monitor đó.
- `notifyAll()` đánh thức tất cả thread đang chờ trên monitor đó; từng thread phải lấy lại monitor trước khi tiếp tục.

Các method này phải được gọi khi thread đang sở hữu monitor tương ứng, thường bên trong block `synchronized`. Gọi chúng ngoài monitor sẽ ném `IllegalMonitorStateException`.

### 4.1. Luôn kiểm tra điều kiện trong vòng lặp

Không viết:

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useResource();
}
```

Một thread có thể thức dậy do spurious wakeup; `notify` cũng không bảo đảm điều kiện nghiệp vụ vẫn đúng khi thread lấy lại monitor. Thread khác có thể đã thay đổi trạng thái trước đó. Vì vậy, phải kiểm tra lại điều kiện trong `while`:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    useResource();
}
```

`wait()` nhả monitor trong lúc chờ và lấy lại monitor trước khi method trả về. Sau khi lấy lại monitor, thread kiểm tra lại predicate `ready` dưới cùng khóa.

### 4.2. Ví dụ producer–consumer đơn giản

```java
import java.util.ArrayDeque;
import java.util.Queue;

public final class OneSlotQueue<T> {
    private final Object lock = new Object();
    private final Queue<T> queue = new ArrayDeque<>();

    public void put(T item) throws InterruptedException {
        synchronized (lock) {
            while (!queue.isEmpty()) {
                lock.wait();
            }
            queue.add(item);
            lock.notifyAll();
        }
    }

    public T take() throws InterruptedException {
        synchronized (lock) {
            while (queue.isEmpty()) {
                lock.wait();
            }
            T item = queue.remove();
            lock.notifyAll();
            return item;
        }
    }
}
```

Producer chỉ thêm phần tử khi queue rỗng; consumer chỉ lấy phần tử khi queue có dữ liệu. Cả predicate và thao tác thay đổi queue đều được bảo vệ bởi cùng monitor. `notifyAll()` đánh thức những thread đang chờ để chúng kiểm tra lại điều kiện.

Ví dụ này chỉ minh họa cơ chế monitor. Trong ứng dụng thực tế, `BlockingQueue` thường là lựa chọn đơn giản và ít lỗi hơn vì nó đã đóng gói thao tác chờ, đánh thức và đồng bộ:

```java
BlockingQueue<Job> queue = new LinkedBlockingQueue<>();

// Producer
queue.put(job);

// Consumer
Job next = queue.take();
```

### 4.3. Vì sao thường chọn `notifyAll()`?

`notify()` chỉ đánh thức một thread bất kỳ đang chờ trên monitor. Nếu có nhiều loại predicate cùng chờ trên một monitor, thread được đánh thức có thể không phải thread có điều kiện vừa trở thành đúng. Nó có thể quay lại chờ trong khi thread phù hợp vẫn ngủ.

`notifyAll()` đánh thức tất cả thread để mỗi thread tự kiểm tra predicate. Cách này thường dễ đúng hơn, dù có thể tạo thêm cạnh tranh lấy monitor. Nếu cần hiệu năng tốt hơn, nên tách condition/monitor hoặc dùng `Condition` để đánh thức nhóm thread phù hợp.

## 5. `ReentrantLock` và `Condition`

`ReentrantLock` cung cấp khả năng khóa tường minh với các tính năng như thử lấy khóa, lấy khóa có timeout, chờ có thể bị interrupt và nhiều condition gắn với cùng lock.

Ví dụ:

```java
import java.util.concurrent.locks.ReentrantLock;

public final class LockedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    public void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock();
        }
    }

    public int get() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
```

Mọi lần `lock()` thành công phải có `unlock()` tương ứng. Đặt `unlock()` trong `finally` để exception không làm rò khóa. Không gọi `unlock()` từ thread khác vì `ReentrantLock` chỉ cho phép thread sở hữu nhả khóa.

### 5.1. Condition là predicate gắn với lock

`Condition` tương tự cơ chế `wait/notify`, nhưng gắn với một `Lock` cụ thể. Một lock có thể tạo nhiều condition, ví dụ `notEmpty` và `notFull` cho queue.

Ví dụ chờ queue có dữ liệu:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class ConditionQueue<T> {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Condition notFull = lock.newCondition();
    private final java.util.ArrayDeque<T> queue =
            new java.util.ArrayDeque<>();
    private final int capacity;

    public ConditionQueue(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    public void put(T item) throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (queue.size() == capacity) {
                notFull.await();
            }
            queue.addLast(item);
            notEmpty.signal();
        } finally {
            lock.unlock();
        }
    }

    public T take() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (queue.isEmpty()) {
                notEmpty.await();
            }
            T item = queue.removeFirst();
            notFull.signal();
            return item;
        } finally {
            lock.unlock();
        }
    }
}
```

`await()` nhả lock trong lúc chờ và lấy lại lock trước khi tiếp tục. Predicate vẫn phải được kiểm tra trong `while` vì có thể có spurious wakeup hoặc thread khác thay đổi queue trước khi thread được đánh thức lấy lại lock.

### 5.2. `lock()` và `lockInterruptibly()`

`lock()` chờ lấy khóa và không ném `InterruptedException` khi thread bị interrupt trong lúc chờ. Cờ interrupt vẫn có thể được đặt. `lockInterruptibly()` cho phép hủy thao tác chờ bằng interrupt và ném `InterruptedException`.

Với tác vụ nền cần dừng có kiểm soát trước checkpoint, khả năng chờ có thể bị interrupt thường hữu ích. Khi bắt `InterruptedException`, hãy phục hồi cờ interrupt nếu không truyền exception lên:

```java
try {
    lock.lockInterruptibly();
    try {
        updateState();
    } finally {
        lock.unlock();
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

Không nuốt interrupt rồi tiếp tục vòng lặp vô hạn. Interrupt là tín hiệu điều phối để thread có thể kết thúc hoặc chuyển trạng thái theo chính sách ứng dụng.

## 6. `volatile`: công bố trạng thái đơn giản

`volatile` phù hợp với một trạng thái đơn giản mà nhiều thread đọc và một hoặc nhiều thread ghi, khi thao tác không cần một transaction gồm nhiều bước.

Ví dụ cờ dừng worker:

```java
public final class Worker implements Runnable {
    private volatile boolean running = true;

    public void requestStop() {
        running = false;
    }

    @Override
    public void run() {
        while (running) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Xử lý một đơn vị công việc có ranh giới xác định.
    }
}
```

Ghi `running = false` được công bố cho thread đọc biến volatile. Khi worker đọc được `false`, nó thoát vòng lặp ở ranh giới kiểm tra tiếp theo. Điều này không tự chờ worker kết thúc; thread quản lý vẫn cần gọi `join()` hoặc dùng latch để chờ.

`volatile` không bảo vệ một invariant gồm nhiều trường. Ví dụ, nếu `state` và `lastUpdatedAt` phải thay đổi đồng bộ, một volatile cho từng field không bảo đảm người đọc nhìn thấy một cặp giá trị nhất quán. Hãy dùng một lock hoặc công bố một object bất biến qua một volatile reference.

## 7. Atomic classes và concurrent utilities

### 7.1. Atomic classes

Các lớp trong `java.util.concurrent.atomic` dùng thao tác nguyên tử như compare-and-set (CAS) để cập nhật một giá trị đơn mà không cần khóa tường minh.

Ví dụ:

```java
AtomicInteger activeTasks = new AtomicInteger();

int current = activeTasks.incrementAndGet();
int remaining = activeTasks.decrementAndGet();
```

`AtomicInteger`, `AtomicLong`, `AtomicBoolean` và `AtomicReference` phù hợp với counter, cờ hoặc reference đơn. Nếu cần cập nhật đồng thời nhiều giá trị có quan hệ với nhau, hãy cân nhắc lock hoặc một immutable state object được thay thế nguyên tử.

### 7.2. CountDownLatch

`CountDownLatch` giúp một thread đợi nhiều công việc hoàn thành:

```java
CountDownLatch completed = new CountDownLatch(3);

for (int i = 0; i < 3; i++) {
    executor.submit(() -> {
        try {
            performTask();
        } finally {
            completed.countDown();
        }
    });
}

if (!completed.await(30, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Tasks did not finish in time");
}
```

`countDown()` phải được gọi trong `finally` để lỗi ở worker không khiến thread chờ mãi. Latch chỉ đếm xuống, không reset để dùng cho chu kỳ tiếp theo. Nếu cần tái sử dụng cho nhiều pha, xem xét `Phaser` hoặc tạo latch mới.

### 7.3. Semaphore

`Semaphore` giới hạn số thread cùng truy cập một nhóm tài nguyên. Ví dụ, giới hạn tối đa năm tác vụ đồng thời gọi một dịch vụ bên ngoài:

```java
Semaphore permits = new Semaphore(5);

permits.acquire();
try {
    callExternalService();
} finally {
    permits.release();
}
```

Permit phải được trả trong `finally`. Nếu thread bị interrupt khi chờ `acquire()`, cần xử lý interrupt theo chính sách của tác vụ.

### 7.4. BlockingQueue và ExecutorService

`BlockingQueue` cung cấp cơ chế chờ khi queue rỗng hoặc đầy. `ExecutorService` quản lý worker thread và hàng đợi task. Đây thường là các abstraction nên dùng thay vì tự viết cơ chế wait/notify.

Trước checkpoint, cần xác định task nào đã được nhận, task nào đang chạy và task nào còn trong queue. `shutdown()` ngăn nhận task mới nhưng cho task đã submit chạy tiếp; `shutdownNow()` yêu cầu dừng và trả lại task đang chờ nhưng không thể cưỡng ép một task đang chạy kết thúc an toàn. Sau restore, không nên giả định executor đã shutdown có thể được khởi động lại; thông thường tạo executor mới rồi mới submit công việc.

## 8. Deadlock, livelock và starvation

### 8.1. Deadlock

Deadlock xảy ra khi các thread chờ tài nguyên của nhau và không thread nào có thể tiếp tục.

Ví dụ:

```java
Object lockA = new Object();
Object lockB = new Object();

// Thread 1
synchronized (lockA) {
    synchronized (lockB) {
        updateAAndB();
    }
}

// Thread 2
synchronized (lockB) {
    synchronized (lockA) {
        updateBAndA();
    }
}
```

Nếu Thread 1 giữ `lockA` và chờ `lockB`, trong khi Thread 2 giữ `lockB` và chờ `lockA`, cả hai bị kẹt.

Cách phổ biến để phòng tránh là quy định thứ tự khóa toàn cục: mọi thread phải lấy `lockA` trước `lockB`. Ngoài ra:

- Giữ vùng khóa ngắn.
- Tránh gọi code bên ngoài không kiểm soát khi đang giữ lock.
- Tránh chờ I/O, network hoặc user callback trong vùng khóa.
- Dùng `tryLock(timeout)` khi cần giới hạn thời gian chờ và có phương án xử lý timeout.
- Thu thập thread dump khi phát hiện thread bị treo.

### 8.2. Livelock và starvation

Livelock xảy ra khi các thread vẫn hoạt động và liên tục phản ứng với nhau nhưng không hoàn thành công việc. Starvation xảy ra khi một thread liên tục không được cấp tài nguyên hoặc CPU cần thiết để tiến triển.

Lock fairness có thể giảm một số trường hợp starvation nhưng có thể làm giảm throughput. Không bật fairness theo mặc định nếu chưa có nhu cầu đo được. Hãy quan sát latency và thời gian chờ thực tế.

## 9. Khóa và điều kiện chờ trong chu kỳ CRaC

Checkpoint lưu trạng thái của một tiến trình đang chạy. Việc các thread có lock, condition hoặc đang chờ không thay thế yêu cầu phối hợp ở cấp ứng dụng. Một snapshot có thể khôi phục trạng thái bộ nhớ và thực thi của thread theo khả năng nền tảng, nhưng điều đó không bảo đảm một nghiệp vụ đang dở dang sẽ có ý nghĩa đúng khi tiếp tục.

Ví dụ, một worker có thể đang giữ lock và đã cập nhật một field nhưng chưa cập nhật field thứ hai. Nếu checkpoint được tạo ở một ranh giới không phù hợp, tiến trình sau restore có thể tiếp tục từ trạng thái trung gian mà nghiệp vụ không mong muốn. Tương tự, một thread đang chờ một tín hiệu từ hệ thống bên ngoài có thể tiếp tục chờ sau restore trong khi tín hiệu đó đã xảy ra, bị mất hoặc không còn được gửi.

Trước checkpoint, nên:

1. Dừng nhận công việc mới từ HTTP, message broker, scheduler hoặc queue.
2. Yêu cầu worker kết thúc đơn vị công việc hiện tại hoặc đi đến điểm an toàn.
3. Chờ worker bằng `join()`, `CountDownLatch`, `Phaser` hoặc condition có timeout.
4. Đảm bảo invariant của dữ liệu chia sẻ đã được cập nhật hoàn chỉnh.
5. Đóng tài nguyên sau khi không còn thread sử dụng chúng.
6. Hủy checkpoint nếu hết timeout mà worker chưa drain xong.

Sau restore, nên:

1. Phục hồi dependency bên ngoài như database pool, HTTP client và message connection.
2. Xác minh trạng thái dùng chung cần thiết.
3. Tạo lại executor hoặc worker nếu lifecycle của thư viện yêu cầu.
4. Mở cổng nhận việc và đánh dấu readiness sau khi dependency sẵn sàng.

Không dùng `Thread.sleep()` để chờ worker “có lẽ đã xong”. Sleep không tạo quan hệ đồng bộ và không chứng minh task đã hoàn thành. Dùng một primitive phối hợp có điều kiện và timeout.

### 9.1. Ví dụ gate để dừng nhận task và drain worker

Ví dụ sau dùng `ReentrantLock` và `Condition` để bảo vệ trạng thái chấp nhận task cùng số lượng task đang chạy:

```java
import java.time.Duration;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class TaskGate {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition drained = lock.newCondition();

    private boolean accepting = true;
    private int activeTasks;

    public boolean tryBeginTask() {
        lock.lock();
        try {
            if (!accepting) {
                return false;
            }
            activeTasks++;
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void endTask() {
        lock.lock();
        try {
            if (activeTasks <= 0) {
                throw new IllegalStateException("No active task to finish");
            }
            activeTasks--;
            if (activeTasks == 0) {
                drained.signalAll();
            }
        } finally {
            lock.unlock();
        }
    }

    public boolean pauseAndDrain(Duration timeout)
            throws InterruptedException {
        long remaining = timeout.toNanos();
        lock.lockInterruptibly();
        try {
            accepting = false;
            while (activeTasks != 0) {
                if (remaining <= 0) {
                    accepting = true;
                    drained.signalAll();
                    return false;
                }
                try {
                    remaining = drained.awaitNanos(remaining);
                } catch (InterruptedException interrupted) {
                    accepting = true;
                    drained.signalAll();
                    throw interrupted;
                }
            }
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void resume() {
        lock.lock();
        try {
            accepting = true;
            drained.signalAll();
        } finally {
            lock.unlock();
        }
    }

    public int activeTasks() {
        lock.lock();
        try {
            return activeTasks;
        } finally {
            lock.unlock();
        }
    }
}
```

Worker phải gọi `tryBeginTask()` trước khi bắt đầu đơn vị công việc và luôn gọi `endTask()` trong `finally`:

```java
if (taskGate.tryBeginTask()) {
    try {
        processOneJob();
    } finally {
        taskGate.endTask();
    }
}
```

Trước checkpoint, coordinator dừng producer hoặc consumer để không tiếp tục đưa task mới vào, rồi gọi `pauseAndDrain()` với timeout. Nếu trả về `false`, checkpoint chưa có ranh giới an toàn và ứng dụng cần hủy yêu cầu. Nếu trả về `true`, không còn task được chấp nhận đang chạy qua gate này.

Gate chỉ theo dõi các task đã đăng ký qua nó. Nó không tự dừng scheduler, message consumer hoặc queue producer; các nguồn đó phải được điều phối riêng. Trong ứng dụng thực tế, cần đảm bảo mọi đường vào worker đều đi qua gate, nếu không số `activeTasks` không phản ánh đầy đủ hoạt động.

## 10. Khả năng hiển thị trạng thái sau restore

Khi restore, trạng thái bộ nhớ của tiến trình được khôi phục theo cơ chế CRaC và nền tảng. Tuy nhiên, không nên xem restore như một tín hiệu đồng bộ giữa các thread hoặc giữa nhiều instance.

Các quy tắc JMM vẫn là nền tảng để thread phối hợp khi tiếp tục chạy:

- Dữ liệu bảo vệ bởi cùng monitor phải tiếp tục được đọc/ghi qua monitor đó.
- Trạng thái công bố qua `volatile` cần được đọc qua cùng field volatile.
- Trạng thái atomic cần được cập nhật qua các atomic operation.
- Queue, latch và concurrent collection cần được sử dụng theo đúng hợp đồng đồng bộ của chúng.
- Các thread mới cần nhận dữ liệu khởi tạo trước `Thread.start()` hoặc qua một cơ chế publish an toàn.

Nếu ứng dụng có trạng thái thay đổi từ bên ngoài trong thời gian image được lưu, bản sao trong heap có thể đã cũ. Ví dụ, một cờ `databasePrimary = true` được đọc trước checkpoint không chứng minh node đó vẫn là primary sau restore. Hãy truy vấn hoặc xác thực lại trạng thái bên ngoài.

Tương tự, một `volatile boolean connected` trong heap có thể vẫn là `true` sau restore dù socket đã mất. Visibility chỉ đảm bảo các thread nhìn thấy giá trị theo JMM; nó không xác nhận tài nguyên bên ngoài còn sống. Sau restore, cập nhật trạng thái kết nối dựa trên kết quả kiểm tra thật.

## 11. Những lỗi đồng thời thường gặp

**Dùng `volatile` cho phép tăng bộ đếm.** Visibility không biến `count++` thành atomic. Dùng `AtomicInteger` hoặc khóa.

**Đọc predicate ngoài lock rồi mới gọi `wait()`.** Trạng thái có thể thay đổi giữa lúc kiểm tra và lúc bắt đầu chờ, dẫn đến missed notification. Kiểm tra và chờ dưới cùng monitor.

**Dùng `if` thay cho `while` quanh `wait()`/`await()`.** Có thể có spurious wakeup hoặc predicate đã thay đổi. Luôn kiểm tra lại điều kiện trong vòng lặp.

**Gọi `notify()` mà không hiểu các nhóm thread đang chờ.** Có thể đánh thức nhầm thread. Dùng condition riêng hoặc `notifyAll()` khi cần đánh thức mọi waiter.

**Quên unlock trong `finally`.** Exception có thể làm các thread khác chờ vô hạn. Luôn đặt `unlock()` trong `finally`.

**Nuốt `InterruptedException`.** Thread không còn phản hồi tín hiệu dừng. Truyền exception lên hoặc phục hồi cờ interrupt.

**Giữ lock khi gọi I/O hoặc callback chậm.** Thread khác không thể tiến triển và dễ tạo deadlock dây chuyền. Thu hẹp critical section.

**Lấy nhiều lock theo thứ tự khác nhau.** Có thể tạo deadlock. Quy định một thứ tự toàn cục.

**Checkpoint khi worker đang ở giữa cập nhật nghiệp vụ.** Trạng thái bộ nhớ có thể được lưu ở điểm không phù hợp về nghiệp vụ. Hãy drain task đến ranh giới an toàn.

**Dùng sleep thay cho phối hợp.** Sleep chỉ trì hoãn thread, không chứng minh điều kiện đã đúng và không tạo happens-before. Dùng condition, latch, join hoặc queue.

**Coi cờ `connected` sau restore là bằng chứng socket còn sống.** Trạng thái trong heap có thể cũ. Kiểm tra dependency bên ngoài rồi mới công bố readiness.

## 12. Hướng dẫn chọn primitive đồng bộ

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Bảo vệ nhiều field phải nhất quán cùng nhau | `synchronized` hoặc `ReentrantLock` |
| Công bố một cờ trạng thái đơn giản | `volatile` |
| Tăng/đổi một giá trị đơn nguyên tử | `AtomicInteger`, `AtomicLong`, `AtomicReference` |
| Chờ một điều kiện gắn với khóa | `Condition` hoặc `Object.wait()` |
| Đợi một nhóm task hoàn tất một lần | `CountDownLatch` |
| Đồng bộ nhiều pha có thể tái sử dụng | `Phaser` hoặc `CyclicBarrier` tùy mô hình |
| Giới hạn số tác vụ đồng thời | `Semaphore` |
| Truyền công việc giữa producer và consumer | `BlockingQueue` |
| Quản lý worker và vòng đời task | `ExecutorService` |
| Chờ một thread kết thúc | `Thread.join()` |

Hãy chọn abstraction cao nhất đáp ứng được nhu cầu. `BlockingQueue` thường dễ sử dụng và ít lỗi hơn việc tự viết queue bằng `wait/notify`; `ExecutorService` thường tốt hơn việc tự tạo và quản lý nhiều thread thủ công.

## 13. Quy trình áp dụng vào ứng dụng CRaC

Có thể triển khai theo các bước sau:

1. **Liệt kê dữ liệu chia sẻ.** Xác định object, field, collection và tài nguyên được nhiều thread truy cập.
2. **Xác định invariant.** Ghi rõ những trường nào phải thay đổi cùng nhau và điều kiện nào worker phải chờ.
3. **Chọn cơ chế đồng bộ.** Dùng monitor/lock cho invariant, volatile cho cờ đơn, atomic cho thao tác đơn và concurrent utilities cho phối hợp task.
4. **Giới hạn critical section.** Không giữ lock trong lúc gọi network, database hoặc callback có thể chặn lâu.
5. **Thiết kế dừng worker.** Ngừng nguồn công việc mới, drain task đang chạy và chờ bằng primitive có timeout.
6. **Tích hợp `beforeCheckpoint`.** Chỉ đóng dependency sau khi worker đã dừng và trạng thái chia sẻ đạt ranh giới an toàn.
7. **Tích hợp `afterRestore`.** Phục hồi dependency, xác thực trạng thái bên ngoài rồi mới resume worker.
8. **Kiểm thử lỗi và timeout.** Thử worker bị chậm, bị interrupt, dependency không sẵn sàng và callback thất bại.
9. **Theo dõi thread dump và metrics.** Ghi nhận thời gian drain, số task đang chạy, lock contention và thời gian từ restore đến readiness.

## 14. Tự kiểm tra mức độ hiểu

1. **Vì sao `count++` không an toàn khi nhiều thread dùng chung?** Vì đây là chuỗi đọc–sửa–ghi; các thread có thể ghi đè kết quả của nhau.
2. **`volatile` bảo đảm điều gì và không bảo đảm điều gì?** Nó cung cấp visibility và ordering theo JMM cho truy cập biến volatile, nhưng không tự làm atomic một phép toán ghép như `count++`.
3. **Vì sao `wait()` phải nằm trong vòng `while`?** Vì có thể xảy ra spurious wakeup hoặc predicate đã thay đổi trước khi thread lấy lại monitor.
4. **`wait()` có nhả monitor không?** Có. Nó nhả monitor trong lúc chờ và lấy lại monitor trước khi trả về.
5. **Vì sao `unlock()` cần nằm trong `finally`?** Để bảo đảm lock được nhả ngay cả khi code trong critical section ném exception.
6. **Làm thế nào phòng tránh deadlock khi cần hai khóa?** Quy định và tuân thủ cùng một thứ tự lấy khóa ở mọi thread.
7. **Vì sao không dùng `Thread.sleep()` để chờ worker hoàn tất trước checkpoint?** Sleep không chứng minh điều kiện đã đạt, không tạo quan hệ đồng bộ và có thể thức dậy quá sớm hoặc quá muộn.
8. **Sau restore, cờ `connected` trong heap có chứng minh database còn kết nối không?** Không. Phải kiểm tra lại tài nguyên bên ngoài và cập nhật trạng thái theo kết quả thực tế.

## Kết luận

Khóa, điều kiện chờ và khả năng hiển thị là nền tảng để nhiều thread cùng sử dụng trạng thái an toàn. `synchronized` và `ReentrantLock` bảo vệ invariant; `wait/notify` và `Condition` phối hợp thread theo predicate; `volatile` công bố trạng thái đơn giản; atomic classes và concurrent utilities hỗ trợ các thao tác phổ biến mà không cần tự quản lý khóa ở mức thấp.

Trong chu kỳ CRaC, hãy dùng những primitive này để đưa worker về ranh giới an toàn trước checkpoint và khởi động lại chúng sau khi dependency được phục hồi. Ngừng nhận công việc mới, drain task bằng cơ chế có timeout, tránh giữ lock trong lúc I/O và xác thực lại trạng thái bên ngoài sau restore. Nhờ đó, snapshot phản ánh trạng thái ứng dụng nhất quán và các thread có thể tiếp tục phối hợp đúng khi tiến trình được khôi phục.
