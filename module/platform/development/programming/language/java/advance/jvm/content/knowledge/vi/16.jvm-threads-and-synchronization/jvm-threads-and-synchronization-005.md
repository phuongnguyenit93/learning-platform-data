# `wait`, `notify`, `notifyAll` và mối quan hệ giữa wait set với quyền sở hữu monitor trong Java

Trong lập trình đa luồng Java, `Object.wait()`, `Object.notify()` và `Object.notifyAll()` là bộ ba nguyên thủy để **phối hợp trạng thái giữa các threads bằng intrinsic monitor**. Những phương thức này không phải các lệnh “tạm dừng/tiếp tục một thread theo ý muốn” và cũng không tương đương `Thread.sleep()`. Muốn dùng đúng, cần hiểu đồng thời **ba thứ khác nhau**:

1. **Monitor ownership:** thread nào hiện đang sở hữu khóa nội tại của object?
2. **Wait set:** những threads nào đã tự nguyện nhường monitor bằng `wait()` trên chính object ấy và đang chờ một sự kiện để được xem xét tiếp tục?
3. **Điều kiện nghiệp vụ (guarded predicate):** dữ liệu nào cho biết thao tác có thể thực hiện, ví dụ `ready == true`, hàng đợi không rỗng hoặc buffer còn chỗ?

Nguyên tắc cốt lõi: **`wait()` chỉ được gọi khi thread đang sở hữu monitor của đúng object; nó đưa thread vào wait set và nhường toàn bộ quyền sở hữu monitor ấy. `notify()`/`notifyAll()` cũng đòi quyền sở hữu cùng monitor, nhưng không nhả monitor ngay. Thread đã nhận tín hiệu chỉ được trở lại từ `wait()` sau khi giành lại monitor.**

Vì một thread có thể thức dậy do notification, interruption, timeout hoặc *spurious wakeup*, **luôn kiểm tra điều kiện bằng `while` trong cùng một vùng đồng bộ**:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Thực hiện công việc khi condition đúng dưới cùng monitor.
}
```

Đoạn trên là **mẫu ý tưởng**, chưa phải một file chạy độc lập; `lock` và `condition` phải có khai báo và logic cập nhật. Bài học thuộc mục **Luồng và đồng bộ**, dựa trên **Java SE 17 – JLS §17.1–17.4** và `java.lang.Object` Javadoc. Các chương trình độc lập bên dưới sử dụng Java 17, có hướng dẫn biên dịch, stdout xác định khi chạy bình thường và giải thích phần scheduling không thể dự đoán.

## 1. Mỗi Java object có một monitor và một wait set

Theo Java Language Specification (`17.1, `17.2), một object gắn với:

- **Monitor:** cơ chế mutual exclusion mà `synchronized` và synchronized methods sử dụng.
- **Wait set:** tập các threads đã gọi `wait` trên object trong các điều kiện hợp lệ và chưa hoàn tất giai đoạn chờ theo quy tắc JLS.

Khi object mới được tạo, wait set của nó **rỗng**. Việc thêm/xóa một thread khỏi wait set được mô hình hóa như những hành động nguyên tử. Mỗi object có wait set **riêng biệt**: gọi `notifyAll` trên object A không đánh thức các threads đang `wait` trên object B.

```text
                       OBJECT lock
        ┌────────────────────────────────────┐
        │ Monitor: tại một thời điểm chỉ     │
        │ một thread sở hữu monitor          │
        │                                    │
        │ Wait set: {T2, T3, ...}            │
        │ thread đã gọi lock.wait()          │
        └────────────────────────────────────┘
                  ▲               │
     vào synchronized(lock)      lock.wait()
                  │               ▼
     T1 giữ monitor        T2 nhường monitor và chờ
                  │               │
       lock.notifyAll()           │ được lấy khỏi wait set
          khi T1 còn khóa          ▼
                  │         T2 tranh quyền giành lại monitor
                  │               │
       T1 rời synchronized        │
          → unlock               ▼
                       T2 giành lại lock, wait() trả về
                       và chỉ khi đó tiếp tục kiểm tra condition
```

**Đừng hiểu hình này là scheduler có một FIFO entry queue được Java specification cam kết.** “Entry set/entry list”, “monitor owner”, “wait set” thường được vẽ trong tài liệu JVM để giải thích scheduling. **Wait set** và quyền sở hữu monitor là ngữ nghĩa được JLS mô tả; thứ tự tranh monitor, cấu trúc các hàng đợi native và fairness không được bảo đảm theo những sơ đồ giáo khoa.

### 1.1. Quyền sở hữu monitor (ownership) có nghĩa gì?

Một thread lấy monitor bằng một trong những cách phổ biến:

```java
synchronized (lock) {
    // Thread hiện sở hữu monitor của lock.
}

synchronized void instanceMethod() {
    // Sở hữu monitor của this.
}

static synchronized void classMethod() {
    // Sở hữu monitor của Class object tương ứng.
}
```

Đây là các **snippets** minh họa; hai method thuộc một class thích hợp. Lưu ý:

- `synchronized(lock)` khóa **đúng instance mà `lock` trỏ tới**.
- `synchronized instanceMethod()` khóa **`this`**, không khóa một field `lock` bất kỳ.
- `static synchronized` khóa **Class object**, ví dụ `Sample.class`, không khóa một instance của `Sample`.
- `new Object()` mỗi lần tạo một monitor khác nhau. Không thể dùng hai monitor không liên quan rồi mong `wait/notify` giao tiếp.
- Một thread đang `synchronized(other)` không tự động có quyền gọi `lock.wait()`.

### 1.2. Monitor reentrant

Intrinsic monitors trong Java có tính **reentrant**: thread đã giữ monitor có thể đi vào synchronized block/method trên cùng object thêm lần nữa mà không tự deadlock.

```java
synchronized (lock) {
    synchronized (lock) {
        // Vẫn chỉ một thread sở hữu lock; ownership reentrant.
    }
}
```

Trong mô hình JLS, nếu thread giữ monitor của object `lock` qua **n lần lock actions chưa được ghép unlock**, lời gọi `lock.wait()` hợp lệ phải **nhường toàn bộ n mức sở hữu trên chính monitor đó**. Khi đủ điều kiện trở lại, thread phải **giành lại cùng số mức** để tiếp tục.

Điều này khác với chỉ “giảm lock count một lần”. Nếu `wait()` không nhường hết các mức sở hữu lock, thread khác sẽ không thể vào monitor để thay đổi trạng thái và gửi notification trong nhiều trường hợp.

## 2. Chữ ký ba nhóm API `Object`

Java 17 định nghĩa:

```java
public final void wait() throws InterruptedException;
public final void wait(long timeoutMillis) throws InterruptedException;
public final void wait(long timeoutMillis, int nanos)
        throws InterruptedException;

public final native void notify();
public final native void notifyAll();
```

Các signature này mô tả API; không phải file chạy. Bản `wait()` không giới hạn thời gian tương đương `wait(0L, 0)`; bản `wait(long)` với tham số `0` là đợi vô hạn cho tới khi có sự kiện đánh thức/interrupt/spurious wakeup, không phải “đợi 0 ms rồi trả về”.

| Phương thức | Cần sở hữu monitor của receiver? | Tác động chính |
| --- | --- | --- |
| `lock.wait()` | **Có** | Thêm current thread vào wait set của `lock`; nhường monitor ấy và đợi sự kiện |
| `lock.wait(millis)` | **Có** | Như trên nhưng cho phép timeout khi thời gian tương ứng trôi qua |
| `lock.wait(millis, nanos)` | **Có** | Timed wait với đơn vị millisecond + nanosecond component hợp lệ |
| `lock.notify()` | **Có** | Chọn **một thread tùy ý** trong wait set của `lock` để cho phép nó tranh lock trở lại |
| `lock.notifyAll()` | **Có** | Loại **tất cả threads** đang ở wait set của `lock` để chúng có thể tranh lock trở lại |
| `Thread.sleep(...)` | **Không** cần monitor | Tạm ngủ theo thời gian, **không tự nhả monitor** đã giữ |
| `Thread.join()` | Caller không bắt buộc sở hữu target monitor | Đợi target thread kết thúc theo API, không phải cơ chế signaling nghiệp vụ do caller tự viết |

Cả `wait`, `notify` và `notifyAll` đều là **instance methods của `Object`**, không phải static methods của `Thread`. Muốn điều phối bằng monitor `queueLock` thì gọi `queueLock.wait()`/`queueLock.notifyAll()`.

## 3. Một lời gọi `wait()` hợp lệ đi qua những bước nào?

Theo JLS 17.2.1, một thread T gọi `m.wait()` sau khi đã giữ monitor của object `m`:

1. Xác minh T **đang sở hữu monitor `m`**. Nếu không, ném `IllegalMonitorStateException`.
2. Xử lý điều kiện argument/tình trạng interrupted theo đặc tả.
3. T được **đưa vào wait set của `m`**, và nhường **toàn bộ n lần lock** đang giữ trên `m`.
4. T ở trạng thái chờ cho tới khi được loại khỏi wait set bởi notification, interrupt, timed wait expiry hoặc spurious wakeup.
5. **T cố giành lại monitor `m`**, cùng độ sâu reentrant phù hợp.
6. Chỉ **sau khi đã giành lại monitor**, `wait()` mới trả về bình thường hoặc ném `InterruptedException` tương ứng.

```text
T đang chạy trong synchronized(m)
    │ sở hữu monitor m
    ▼
m.wait()
    │ add T to wait set(m), release monitor m
    ▼
T đợi (không thực thi code sau wait)
    │ notify / notifyAll / interrupt / timeout / spurious
    ▼
T rời wait set(m)
    │
    ▼
T PHẢI tranh lại monitor m
    │ nếu thread khác đang giữ m → vẫn không vào được
    ▼
T giành lại monitor m (restored reentrancy)
    │
    ├─ interrupted theo trường hợp áp dụng → InterruptedException
    └─ bình thường → quay lại kiểm tra predicate trong while
```

**Điểm cốt lõi:** Rời wait set ≠ đang sở hữu monitor. “Đã được `notify`” chỉ là một bước cho phép thread tiếp tục cạnh tranh quyền sở hữu monitor; không phải một lệnh cưỡng chế nó chạy ngay lập tức.

### 3.1. `wait()` nhả monitor nào?

Nó chỉ nhả monitor của **object được gọi `wait()`**, không tự nhả tất cả các monitor mà thread đang giữ.

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
        // Vẫn đang giữ outer trong lúc chờ inner!
    }
}
```

Đây là snippet cần khai báo `outer`/`inner` và xử lý `InterruptedException`. Nếu thread khác cần monitor `outer` trước khi có thể thay đổi dữ liệu rồi gọi `inner.notifyAll()`, bạn có thể tạo **deadlock**. Không dựa vào `wait()` để tự giải phóng toàn bộ các locks đang nắm giữ.

### 3.2. Thread bị đánh thức có chắc chạy tiếp ngay không?

Không. `notifyAll()` có thể làm nhiều threads rời wait set, nhưng chúng chỉ có thể giành monitor **mỗi lần một thread**. Thread vừa gọi `notifyAll()` vẫn giữ monitor cho đến khi thoát khối `synchronized` hoặc trả về từ synchronized method.

Trong các ví dụ, một notifier có thể cập nhật `ready=true` và gọi `notifyAll()`, nhưng nếu còn thực hiện nhiều phép tính tốn thời gian **trong cùng synchronized block**, waiters phải chờ lock được nhả. Đây là lý do nên làm critical sections ngắn, không làm I/O blocking không cần thiết trong monitor.

## 4. `notify()` và `notifyAll()` thay đổi wait set, không nhả monitor

### 4.1. `notify()` đánh thức một thread nào?

Nếu wait set của `m` không rỗng, `m.notify()` **chọn một thread tùy ý** từ wait set để loại khỏi set. Java **không bảo đảm**:

- Chọn thread vào wait set sớm nhất (FIFO).
- Chọn thread có priority cao nhất.
- Chọn thread mà predicate hiện đang đúng.
- Chọn theo thứ tự tên/id.
- Đối xử công bằng theo số lần đợi.
- Thread được chọn sẽ giành monitor trước những threads khác đang cạnh tranh.

Nếu wait set **rỗng**, notification **không được lưu lại như một token để dành cho thread đợi sau**. Đây là nguồn của lỗi **lost notification** nếu code chỉ dựa vào sự kiện gọi notify mà không lưu trạng thái điều kiện.

### 4.2. `notifyAll()` đánh thức tất cả rồi chúng làm gì?

`notifyAll` đưa mọi threads hiện có trong wait set của **object nhận lời gọi** sang tình huống có thể tranh monitor trở lại. Sau notifier unlock, một thread giành được monitor, kiểm tra predicate, rồi:

- Nếu điều kiện đúng, thực hiện công việc và có thể cập nhật state.
- Nếu điều kiện sai, quay lại `wait()` theo vòng `while`, nhường monitor tiếp.
- Những threads khác đợi lượt giành monitor, không được phép cùng lúc vào critical section.

Gọi `notifyAll` **không đồng nghĩa** “tất cả threads được làm công việc ngay” và **không bảo đảm** tất cả sẽ thấy predicate đúng sau đó. Khi nhiều waiters cần cùng một tài nguyên, chỉ một số thread có thể xử lý, các thread còn lại tiếp tục đợi.

### 4.3. Nên chọn `notify` hay `notifyAll`?

- **`notifyAll`** thường là lựa chọn an toàn hơn khi nhiều loại predicates (producers chờ buffer trống, consumers chờ buffer có hàng) chia sẻ **cùng một wait set**, hoặc khi khó chứng minh thread được notify luôn có thể tiến triển.
- **`notify`** có thể dùng trong thiết kế đơn giản có **một loại điều kiện và chứng minh được một notification đủ cho tiến triển**, nhưng việc chỉ chọn một thread tùy ý khiến thuật toán dễ bị trì trệ nếu chọn “nhầm waiter”.
- `notifyAll` có thể gây **thundering herd**: nhiều threads được đánh thức rồi cùng cạnh tranh lock dù chỉ một thread đủ điều kiện, tốn context switching.
- Nếu cần phân biệt cụ thể producer-condition và consumer-condition, `java.util.concurrent.locks.Condition` có thể cung cấp **nhiều condition queues trên một Lock**.

**Không có quy tắc** “`notifyAll` luôn nhanh hơn” hoặc “`notify` luôn đúng nếu chỉ sửa một biến”. Phải kiểm tra protocol và states thực.

## 5. `IllegalMonitorStateException`: giữ đúng monitor, không phải bất kỳ lock nào

Những đoạn sau là **sai**:

```java
Object lock = new Object();
lock.wait();      // IllegalMonitorStateException nếu không đang sở hữu lock.
lock.notify();    // Tương tự.
lock.notifyAll(); // Tương tự.
```

Phép gọi `wait()` còn có checked `InterruptedException`, nên đoạn là **phản ví dụ** chưa hoàn chỉnh để biên dịch, mục đích chỉ ra lỗi sở hữu monitor.

Đúng:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}

synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

Đây là snippet cần khai báo `ready`/`lock` và xử lý interruption. Dữ liệu `ready` phải được bảo vệ bằng **cùng monitor** để tránh check-then-wait race.

### 5.1. Giữ lock A rồi gọi `B.wait()` có hợp lệ không?

Không, trừ khi thread cũng đang giữ monitor B.

```java
Object a = new Object();
Object b = new Object();
synchronized (a) {
    b.notifyAll(); // Sai: sở hữu a không phải sở hữu b.
}
```

Gọi notify trên `b` trong khối giữ `a` sẽ ném `IllegalMonitorStateException` nếu thread không sở hữu monitor `b`. Cần nhất quán identity của **object dùng làm monitor** trên cả hai phía.

### 5.2. Một chương trình Java 17 độc lập cho lỗi ownership

Lưu file **`MonitorOwnershipDemo.java`**:

```java
public class MonitorOwnershipDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        try {
            lock.notify();
        } catch (IllegalMonitorStateException ex) {
            System.out.println("notifyWithoutOwner=true");
        }

        try {
            lock.wait(1);
        } catch (IllegalMonitorStateException ex) {
            System.out.println("waitWithoutOwner=true");
        }

        synchronized (lock) {
            lock.notifyAll(); // Hợp lệ kể cả khi không có waiter.
            System.out.println("notifyAllWithOwner=true");
        }
    }
}
```

Chạy:

```bash
javac --release 17 MonitorOwnershipDemo.java
java MonitorOwnershipDemo
```

**Stdout chính xác:**

```text
notifyWithoutOwner=true
waitWithoutOwner=true
notifyAllWithOwner=true
```

Không phải mỗi `notifyAll()` cần có waiter để được phép gọi; nó chỉ cần **current thread đang sở hữu receiver monitor**. Khi wait set rỗng, không có thread để đánh thức.

## 6. Guarded block: vòng `while` quan trọng hơn bản thân notification

**Sai:**

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useSharedState();
}
```

Đây là snippet minh họa với `ready` và `useSharedState()` chưa khai báo. Nguy cơ:

1. Thread có thể tỉnh do *spurious wakeup*.
2. Thread có thể được notify vì **điều kiện khác**.
3. Thread khác có thể giành monitor **trước** thread vừa tỉnh, tiêu thụ resource hoặc thay state.
4. Timed wait có thể hết hạn dù predicate vẫn sai.

**Đúng:**

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    useSharedState();
}
```

Vòng `while` kiểm tra **predicate thực tế**, không kiểm tra đơn giản “đã nhận tín hiệu hay chưa”. Khi waiter giành lại monitor, nó đánh giá lại trạng thái mới nhất được bảo vệ bởi cùng monitor.

### 6.1. Tại sao không kiểm tra predicate ngoài `synchronized`?

**Phản ví dụ lost-notification race:**

```java
if (!ready) {             // Đọc ngoài synchronized(lock): có thể race.
    synchronized (lock) {
        lock.wait();
    }
}
```

Timeline:

```text
T1 waiter: đọc ready == false
T2 notifier: synchronized(lock) {
                 ready = true;
                 lock.notifyAll();    // wait set còn rỗng
             }
T1 waiter: vào synchronized(lock), gọi lock.wait()
           → rơi vào wait set, nhưng notification trước đó đã mất
           → có thể chờ mãi dù ready đã true
```

Chỉ dùng một `volatile boolean ready` **không sửa được check-then-wait không nguyên tử** nếu thiếu protocol chung. Điều cần có là **kiểm tra predicate và quyết định wait dưới cùng monitor**, trong khi phía notifier **cập nhật predicate và gửi notify trong cùng monitor**.

### 6.2. Notification không lưu trạng thái

`notify/notifyAll` không phải message queue, semaphore permit hoặc persistent event. Nếu notifier phát tín hiệu khi không có waiter, tín hiệu **không được lưu**; nhưng nếu notifier cập nhật `ready=true` dưới monitor, thread đến sau **thấy trạng thái đã đúng** và không cần wait.

Vì vậy, trong thiết kế tốt:

- **Predicate** là nguồn sự thật.
- **Notification** chỉ là gợi ý đánh thức những threads có thể cần **đọc lại predicate**.
- **Monitor** kết nối phép đọc/ghi predicate với việc vào/rời wait set một cách an toàn theo giao thức Java.

## 7. Java 17 demo 1 — một Gate có điều kiện không bị mất tín hiệu

Tạo file **`MonitorGateDemo.java`**:

```java
public class MonitorGateDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait(); // Receiver là this, monitor đang giữ cũng là this.
            }
        }

        synchronized void open() {
            open = true;
            notifyAll(); // Thức dậy để kiểm tra lại open.
        }

        synchronized boolean isOpen() {
            return open;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("workerPassed=true");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("workerInterrupted=true");
            }
        });

        worker.start();
        gate.open();
        worker.join();

        System.out.println("gateOpen=" + gate.isOpen());
    }
}
```

Chạy:

```bash
javac --release 17 MonitorGateDemo.java
java MonitorGateDemo
```

**Stdout xác định trong lần chạy thông thường không bị interrupt từ bên ngoài:**

```text
workerPassed=true
gateOpen=true
```

Giải thích:

- Nếu worker vào `awaitOpen()` **trước** khi main gọi `gate.open()`, worker thấy `open=false` rồi gọi `wait()`, nhường monitor. Main sau đó vào `open()`, ghi `open=true` và `notifyAll()`.
- Nếu main gọi `gate.open()` **trước** khi worker vào `awaitOpen()`, worker thấy `open=true` và **không gọi `wait()`**. Tín hiệu không cần được lưu vì **predicate đã được lưu**.
- Sau `worker.join()`, main mới in `gateOpen=true`. `join()` đảm bảo worker kết thúc trước dòng in cuối, nên **thứ tự hai dòng ổn định**.
- Ví dụ **không chứng minh** worker thực sự đã đi vào wait set ở mọi run; nó chứng minh **protocol dùng state + monitor vẫn đúng dưới cả hai interleavings**.

Không thêm `Thread.sleep(100)` để “ép worker chờ” rồi đưa ra kết luận chắc chắn. Sleep chỉ ảnh hưởng xác suất scheduling, không tạo một synchronization handshake đáng tin.

## 8. Thread States: WAITING, BLOCKED, TIMED_WAITING

Java API `Thread.State` có các trạng thái quan sát được:

| Trạng thái | Ví dụ tình huống | Ghi chú |
| --- | --- | --- |
| **RUNNABLE** | Đang thực thi hoặc đủ điều kiện được JVM/OS schedule | Không bảo đảm đang chiếm CPU thật sự |
| **BLOCKED** | Đang đợi vào một intrinsic monitor vì thread khác sở hữu | Đợi **quyền lock**, khác đợi predicate trong wait set |
| **WAITING** | `Object.wait()` không timeout, `Thread.join()` không timeout, `LockSupport.park()` | Đợi vô hạn tới khi có sự kiện phù hợp |
| **TIMED_WAITING** | `Object.wait(timeout)`, `Thread.sleep(timeout)`, `Thread.join(timeout)` | Đợi có hạn; không phải thời gian thực cứng |
| **TERMINATED** | Thread đã hoàn tất | Không nằm trong monitor wait set |
| **NEW** | Thread object chưa `start()` | Chưa tham gia thực thi |

Đặc biệt:

```text
T1 gọi lock.wait() khi giữ lock
    │
    └─ WAITING (đã nhả monitor và ở wait set)

T2 gọi lock.notify() nhưng còn giữ lock
    │
    └─ T1 ra khỏi wait set; T1 phải đợi giành monitor
       → có thể quan sát trạng thái BLOCKED

T2 rời synchronized(lock)
    │
    └─ T1 có thể giành lock và tiếp tục (RUNNABLE)
```

**Đây là mô hình khái niệm về trạng thái**, không phải một lịch trạng thái API phải chuyển đúng tại từng nanosecond. Polling `getState()` là một snapshot có race; trạng thái có thể thay đổi ngay sau khi đọc và không nên dùng để điều khiển thuật toán signaling.

### 8.1. `Thread.sleep` không giống `Object.wait`

Trong:

```java
synchronized (lock) {
    Thread.sleep(1000);
}
```

thread **vẫn giữ monitor `lock`** trong khi sleep. Không có thread nào khác có thể vào `synchronized(lock)` cho tới khi thread ngủ thoát critical section (trừ chính thread reenter). `Thread.sleep` không đưa thread vào wait set của `lock` và không tự nhả monitor.

Ngược lại, `lock.wait(1000)` khi sở hữu lock **nhường monitor `lock`**, cho phép thread khác giành lock và cập nhật predicate. Nhưng bản timed wait vẫn đòi kiểm tra predicate trong vòng `while`.

## 9. `wait()` có thể trở lại bởi những nguyên nhân nào?

JLS 17.2 mô tả một thread có thể rời wait set do:

1. Được chọn bởi `notify()` trên đúng object.
2. `notifyAll()` trên đúng object.
3. Thread bị `interrupt()`.
4. **Timed wait** đến thời điểm hết hạn theo quy tắc thời gian.
5. **Spurious wakeup:** JVM có thể loại thread khỏi wait set dù không có explicit notification/interrupt/timeout phù hợp.

Mọi trường hợp này đều dẫn đến **bước giành lại monitor trước khi hoàn tất wait action**.

### 9.1. Spurious wakeup là gì?

Một thread gọi `wait()`, sau đó có thể được cho phép trở lại dù chưa có notifier nào báo trạng thái nghiệp vụ đã thay đổi. Java specification cho phép điều này. Một chương trình đúng **không được** giả định “`wait()` trả bình thường ⇒ điều kiện đã đúng”.

Do đó:

```java
synchronized (lock) {
    while (queue.isEmpty()) {
        lock.wait();
    }
    Item item = queue.remove();
}
```

Đây là snippet, cần `queue`, `Item` và xử lý interrupt. Khi tỉnh dậy vì bất cứ lý do nào mà queue vẫn rỗng, thread lại vào `wait()`. Không phải bug của JVM mà là **ngữ nghĩa được phép**.

### 9.2. Interrupt là yêu cầu hủy/đánh thức có cơ chế riêng

Nếu thread đang đợi bằng `wait()` và bị interrupt theo tình huống JLS mô tả, nó rời wait set, phải giành lại monitor, rồi `wait()` ném `InterruptedException`, đồng thời **xóa interrupt status** khi ném exception.

Điểm quan trọng:

- `interrupt()` không “giết” thread một cách cưỡng bức.
- Không mặc định xem mọi interruption là signal `ready=true`.
- Nếu method của bạn muốn cho caller xử lý cancellation, hãy **propagate `InterruptedException`** khi API cho phép.
- Nếu thread worker bắt exception ở tầng không ném được checked exception, thường nên **khôi phục status bằng `Thread.currentThread().interrupt()`** và dừng/hủy công việc theo policy.
- Không catch `InterruptedException` rồi bỏ qua và tiếp tục vòng chờ vô hạn nếu hệ thống cần cancellation.

### 9.3. Notification và interruption đến gần nhau

JLS 17.2.4 giải thích: nếu một waiter đồng thời có thể được notify và interrupt, JVM phải hành xử **tương ứng một thứ tự hợp lệ** giữa các sự kiện. Thread có thể:

- Trở lại bình thường từ `wait()` với interruption **vẫn pending**, hoặc
- Ném `InterruptedException` theo tình huống interrupt được xử lý trước và xóa status.

Không được dạy “khi notify và interrupt cùng lúc thì exception chắc chắn thắng”. Java còn đặt quy tắc để notification không bị đánh mất do cuộc đua với interrupt trên một wait set hiện có.

### 9.4. Java 17 demo 2 — interrupt một waiter mà không lệ thuộc sleep

Lưu file **`InterruptWaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptWaitDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                entered.countDown();
                try {
                    // Vòng lặp chống spurious wakeups:
                    for (;;) {
                        lock.wait();
                    }
                } catch (InterruptedException ex) {
                    System.out.println("interruptCaught=true");
                    System.out.println("interruptFlagCleared=" +
                            !Thread.currentThread().isInterrupted());
                }
            }
        });

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();
        System.out.println("done");
    }
}
```

Chạy:

```bash
javac --release 17 InterruptWaitDemo.java
java InterruptWaitDemo
```

**Stdout xác định khi chương trình chạy bình thường:**

```text
interruptCaught=true
interruptFlagCleared=true
done
```

**Vì sao chắc hơn dùng `sleep`?** `CountDownLatch` bảo đảm worker đã vào vùng đồng bộ và báo sẵn sàng trước khi main gọi interrupt. Main không cần chờ một số milliseconds được đoán. Nếu interrupt tới **trước** lời gọi `wait()`, `wait()` thấy interrupt status rồi ném exception; nếu tới **trong lúc** worker đang wait, waiter rời wait set theo quy tắc. Nếu có spurious wakeup, vòng `for (;;)` vẫn quay lại `wait()`, không in nhầm kết quả.

Đây là một demo học **interruption semantics**, không phải mẫu business loop. Trong code thật, vòng `while(!condition)` tốt hơn một vòng vô tận trừ khi đang minh họa chờ interrupt như trong bài.

## 10. Timed wait: tránh tưởng `wait(timeout)` là một deadline cứng

`wait(long timeoutMillis)` và `wait(long timeoutMillis, int nanos)` cho phép chờ **tối đa theo ý định timeout của wait set**, nhưng thời điểm thread hoàn tất method còn cần **giành lại monitor** và chịu ảnh hưởng scheduling/OS.

- `timeoutMillis` phải **không âm**.
- `nanos` ở overload hai tham số phải trong **0..999999**.
- `wait(0)` và `wait(0, 0)` là **đợi vô hạn** theo quy tắc API.
- `wait(0, 1)` là **timed wait**, không phải vô hạn.
- Thời gian chờ thực và lúc thread được schedule có thể vượt giá trị chỉ định.
- Timed wait có thể kết thúc **trước timeout** bởi notify, interrupt hoặc spurious wakeup.
- Hết timeout **không tự khiến predicate đúng**.

### 10.1. Kiểu đợi có deadline dùng `System.nanoTime`

Nếu yêu cầu “đợi tối đa khoảng X về mặt logic”, phải kiểm tra **thời gian còn lại sau mỗi wakeup**, không gọi lại `wait(timeout)` với toàn bộ timeout sau mỗi spurious wakeup (có thể làm kéo dài liên tục).

Một mô hình minh họa Java 17:

```java
long deadline = System.nanoTime() + timeoutNanos;
synchronized (lock) {
    while (!ready) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0L) {
            break;  // timeout theo logic; ready vẫn có thể false.
        }

        long millis = remaining / 1_000_000L;
        int nanos = (int) (remaining % 1_000_000L);
        lock.wait(millis, nanos);
    }
}
```

Đây là **snippet** cần khai báo `timeoutNanos` (nên là duration dương có giới hạn hợp lý), `lock` và `ready`; caller phải xử lý `InterruptedException`. `System.nanoTime` phù hợp đo khoảng thời gian trôi qua hơn wall-clock. Phép cộng deadline cần tránh overflow với các khoảng thời gian cực lớn; với timeout thông thường hợp lý, đây là mẫu cách kiểm tra **remaining duration**, không bảo đảm thread sẽ được schedule đúng deadline.

### 10.2. Tại sao không dùng `System.currentTimeMillis` làm đồng hồ deadline?

Wall-clock có thể được đồng bộ lại/chỉnh bởi hệ điều hành hoặc quản trị viên, gây những thay đổi không tương ứng elapsed duration. `System.nanoTime` đo thời gian tương đối tốt hơn cho các vòng chờ. Dù vậy, scheduler/lock contention vẫn có thể khiến việc thực tế tiếp tục code vượt deadline.

Với code hiện đại, thường nên ưu tiên API đã thiết kế timeout như `BlockingQueue.poll(timeout, unit)`, `Condition.awaitNanos` hoặc `CountDownLatch.await(timeout, unit)` thay vì tự viết nhiều phép toán thời gian.

## 11. Java Memory Model: notify không thay thế quy tắc happens-before

Dữ liệu dùng làm điều kiện phải được đọc/ghi **có đồng bộ phù hợp**. Với intrinsic monitor, mỗi lần thoát `synchronized(lock)` thực hiện unlock và lần vào `synchronized(lock)` sau đó thực hiện lock. Theo JLS §17.4.4–17.4.5:

> **Unlock trên monitor `m` happens-before một lần lock sau đó trên cùng monitor `m`** theo synchronization order.

Vì thế:

```text
T2 notifier, giữ lock:
   ready = true;
   payload = value;
   lock.notifyAll();
   [unlock lock] ────── happens-before ─────► [lock lock] T1 waiter
                                               đọc ready, payload
```

Điều bảo đảm visibility trong mẫu này dựa trên **monitor unlock/lock và guarded state**, không phải một sự thần kỳ rằng bản thân `notify` “copy mọi biến sang thread khác” mà không cần cùng lock.

### 11.1. Có cần `volatile` cho predicate đã guard bằng synchronized không?

Nếu **mọi truy cập** đến `ready`/`payload` đều nằm trong đúng `synchronized(lock)`, cơ chế unlock/lock đã thiết lập visibility và ordering cần thiết. `volatile` không phải điều kiện bắt buộc chỉ vì nhiều threads dùng biến.

Ngược lại, nếu một phía viết `ready` ngoài monitor và phía còn lại đọc trong monitor, protocol có thể hỏng. Đặt `volatile` cho riêng `ready` không thay thế yêu cầu **atomic check-then-wait** của guarded block.

### 11.2. Tại sao `notify()` không đủ khi thiếu predicate?

Một thread được notify **không được cấp dữ liệu** chỉ bởi tín hiệu. Khi giành monitor, nó phải đọc shared state để biết có job nào, buffer còn chỗ không, hoặc task đã hủy chưa. Nếu không có state invariant rõ ràng, notification là một sự kiện dễ bị miss và khó debug.

### 11.3. `Thread.start()` và `Thread.join()` cũng có happens-before

JLS §17.4.4 nói start action synchronizes-with hành động đầu tiên của thread mới; việc nhận biết thread đã kết thúc qua `join()` tạo quan hệ synchronization tương ứng. Đây là lý do các ví dụ dùng `join()` để **sắp xếp stdout cuối cùng**, nhưng `join` không thay lock nội tại để quản lý trạng thái được chia sẻ **khi các threads còn đang thực thi song song**.

## 12. Producer–consumer: wait set và monitor cùng một object

Bài toán **one-slot buffer**:

- Producer chỉ được `put` khi slot rỗng.
- Consumer chỉ được `take` khi slot có giá trị.
- Nếu không thỏa điều kiện, thread phải nhường monitor và chờ.
- Sau thay đổi trạng thái, thread thông báo để các waiters kiểm tra lại điều kiện.

Một implementation cơ bản:

```java
final class OneSlot {
    private Integer value;  // null = empty

    synchronized void put(int number) throws InterruptedException {
        while (value != null) {
            wait();          // Nhường monitor của this.
        }
        value = number;
        notifyAll();
    }

    synchronized int take() throws InterruptedException {
        while (value == null) {
            wait();
        }
        int result = value;
        value = null;
        notifyAll();
        return result;
    }
}
```

Đây là snippet class; file độc lập ở ngay phần sau. Đọc/ghi `value` và `wait/notifyAll` đều diễn ra dưới **monitor của cùng instance OneSlot**. Điều kiện `value==null` là dữ liệu điều khiển, còn `notifyAll` là tín hiệu giúp threads đã chờ thức dậy để kiểm tra lại.

### 12.1. Vì sao gọi `notifyAll` cả sau `put` lẫn `take`?

Sau `put`, slot chuyển **empty → full**, nên consumer có thể tiếp tục. Sau `take`, slot chuyển **full → empty**, nên producer đang chờ có thể tiếp tục.

Nếu dùng chỉ một wait set và có nhiều producers/consumers, `notify()` có thể chọn thread **không có predicate phù hợp**. Ví dụ buffer đầy nhưng notifier đánh thức một producer khác thay vì consumer cần tiến triển, rồi producer thấy đầy và lại wait. Không có bằng chứng tiến triển trọn vẹn nếu cứ lựa chọn một thread tùy ý. `notifyAll` đánh thức cả hai nhóm, rồi `while` lọc lại đúng điều kiện.

### 12.2. Java 17 demo 3 — chương trình one-slot hoàn chỉnh

Lưu file **`OneSlotDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class OneSlotDemo {
    static final class OneSlot {
        private Integer value;

        synchronized void put(int number) throws InterruptedException {
            while (value != null) {
                wait();
            }
            value = number;
            notifyAll();
        }

        synchronized int take() throws InterruptedException {
            while (value == null) {
                wait();
            }
            int result = value;
            value = null;
            notifyAll();
            return result;
        }

        synchronized boolean isEmpty() {
            return value == null;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        OneSlot slot = new OneSlot();
        AtomicInteger sum = new AtomicInteger();

        Thread producer = new Thread(() -> {
            try {
                for (int n = 1; n <= 5; n++) {
                    slot.put(n);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                for (int n = 1; n <= 5; n++) {
                    sum.addAndGet(slot.take());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        producer.start();
        consumer.start();

        producer.join();
        consumer.join();

        System.out.println("sum=" + sum.get());
        System.out.println("empty=" + slot.isEmpty());
        System.out.println("done");
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 OneSlotDemo.java
java OneSlotDemo
```

**Stdout xác định khi không có interrupt ngoài ý muốn:**

```text
sum=15
empty=true
done
```

Giải thích:

1. Producer đặt lần lượt `1, 2, 3, 4, 5`. Slot dung lượng một, nên có lúc producer phải chờ consumer lấy đi.
2. Consumer lấy đúng năm giá trị, cộng thành `1+2+3+4+5=15`. Có thể consumer hoặc producer bắt đầu trước — protocol vẫn đúng.
3. Mỗi lần `wait()` nhường monitor **của cùng object `slot`**, cho thread bên kia vào để cập nhật `value`.
4. `notifyAll` đánh thức waiters nếu có; các thread kiểm tra lại `while` khi giành monitor.
5. `producer.join()` và `consumer.join()` đảm bảo main chỉ in kết quả sau khi hai threads đã xong. Không cần `Thread.sleep` để ép lịch chạy.
6. `AtomicInteger` giúp mô tả kết quả được publish an toàn; vì main đọc sau `join`, visibility cũng được thiết lập qua thread termination. Dùng `AtomicInteger` không thay thế monitor guarding `value`.

**Giới hạn:** Đây là ví dụ học cách dùng monitor, không có close/cancel protocol đầy đủ khi một producer/consumer bị interrupt. Trong hệ thống thực, nếu một worker bất ngờ chết mà phía kia cứ đợi vô hạn, cần thêm **shutdown state** và signaling để tránh treo.

## 13. Vì sao check điều kiện và notify phải trong cùng synchronization protocol?

### 13.1. Tình huống thread A check, thread B update

Gọi `lock.wait()` bên trong synchronized nhưng kiểm tra predicate **ngoài** synchronized tạo khoảng race:

```text
A: if (queueEmpty)              // không guard
B: synchronized(lock) {
     put(item);
     lock.notifyAll();           // A chưa wait; notification mất
   }
A: synchronized(lock) { lock.wait(); }
```

Lúc này queue đã có item nhưng A có thể chờ vô hạn. Sửa bằng việc đặt cả **check và wait** trong cùng critical section, còn producer đặt **update và notify** dưới cùng monitor.

### 13.2. Có cần notify khi predicate không thay đổi?

Notification nên gắn với những **state transitions có thể làm điều kiện của waiter thành true**, thay vì tùy tiện gọi notify mỗi khi chạy qua một function. Tín hiệu quá thừa gây wakeups/cạnh tranh, còn thiếu tín hiệu sau transition quan trọng gây mất tiến triển. Nếu nhiều predicates cùng chia monitor, dùng `notifyAll` khi chưa có chứng minh protocol mạnh hơn.

### 13.3. Không được giữ monitor trong lúc chờ một thứ sẽ cần chính monitor đó

Một deadlock pattern:

```java
synchronized (lock) {
    while (!ready) {
        Thread.sleep(100);
    }
}
```

Đây là phản ví dụ: `sleep` **không nhả `lock`**, nên nếu thread khác cần `synchronized(lock)` để đặt `ready=true`, nó không thể vào, và waiter có thể kẹt mãi. Đúng hơn là `lock.wait()` trong vòng while theo predicate để **nhường monitor**.

## 14. Đối chiếu `Thread.sleep`, `Object.wait`, `Thread.join`, `Condition.await`

| API | Đợi vì điều gì? | Nhả intrinsic monitor? | Cơ chế đánh thức/hoàn tất |
| --- | --- | --- | --- |
| `Thread.sleep(ms)` | Thời gian | **Không** nhả monitor đang giữ | Timeout hoặc interrupt |
| `obj.wait()` | Tín hiệu/sự kiện trên `obj` | **Có, chỉ monitor `obj`** | Notify/notifyAll, interrupt, spurious wakeup |
| `obj.wait(ms)` | Tín hiệu hoặc timeout | **Có, chỉ monitor `obj`** | Notify, interrupt, timeout, spurious |
| `thread.join()` | Target thread kết thúc | Không có contract “nhả mọi monitor của caller” | Target thread termination, interruption, timeout với overload |
| `condition.await()` | Điều kiện qua explicit Lock | **Nhả associated Lock theo contract và lấy lại trước khi return** | `signal`/`signalAll`, interrupt, spurious |
| `LockSupport.park()` | Permit/`unpark`/interrupt/spurious | **Không tự nhả intrinsic monitor** | Permit, interrupt hoặc spurious; caller tự kiểm tra condition |
| `CountDownLatch.await()` | Count về 0 | Không phải intrinsic-monitor wait do caller tự signal | `countDown`, interrupt hoặc timeout overload |
| `BlockingQueue.take()` | Có item trong queue | API tự quản synchronization | Producer `put/offer` hoặc interrupt |

**Cảnh báo:** `join()` trong HotSpot/Java platform có thể sử dụng monitor-wait nội bộ theo phiên bản và implementation, nhưng người sử dụng nên dựa vào **contract API**, không gọi `thread.notifyAll()` như một cách “tự triển khai join”. `Thread` object không nên được dùng làm monitor nghiệp vụ tùy tiện, vì API/runtime còn dùng những cơ chế đồng bộ liên quan thread lifecycle.

## 15. `Condition` trên `ReentrantLock`: nhiều wait sets nghiệp vụ

Intrinsic monitor mỗi object cung cấp **một wait set**, vì vậy producer và consumer cùng chia sẻ waiters trong một set nếu cùng synchronized object.

`ReentrantLock` hỗ trợ nhiều `Condition` objects, mỗi condition có **condition wait queue riêng** liên kết với một explicit Lock. Dùng khi cần quản lý các predicate khác nhau rõ hơn:

```java
final ReentrantLock lock = new ReentrantLock();
final Condition notEmpty = lock.newCondition();
final Condition notFull = lock.newCondition();

void put(Item item) throws InterruptedException {
    lock.lock();
    try {
        while (queue.isFull()) {
            notFull.await();
        }
        queue.add(item);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}

Item take() throws InterruptedException {
    lock.lock();
    try {
        while (queue.isEmpty()) {
            notEmpty.await();
        }
        Item result = queue.remove();
        notFull.signal();
        return result;
    } finally {
        lock.unlock();
    }
}
```

Đây là **snippet minh họa**, cần import `java.util.concurrent.locks.*`, định nghĩa `Item`/`queue`, và đặt các fields/methods trong class. Nó không phải file runnable độc lập.

- `await()` nhường associated `ReentrantLock` rồi đợi condition.
- `signal()`/`signalAll()` phải được gọi với lock ownership phù hợp theo Condition implementation thông thường.
- Sau notification, waiter vẫn phải **giành lại Lock**, rồi kiểm tra predicate trong `while`.
- `Condition` không tự mang dữ liệu. Guarded predicate trong `queue` mới quyết định có thể `take/put`.
- Multiple conditions cho phép đánh thức đúng nhóm waiters hơn so với một intrinsic wait set trên `this`, giảm wakeups không cần thiết.

### 15.1. Không được trộn hai hệ đồng bộ không tương thích

**Sai:**

```java
synchronized (lock) {
    condition.await();  // Không phải cách sở hữu ReentrantLock.
}
```

Ở đây biến `lock` được giả định là một `ReentrantLock` object. `synchronized(lock)` chỉ sở hữu **intrinsic monitor của instance ReentrantLock**, **không** gọi `lock.lock()` và không thỏa ownership rule của `Condition.await`. Với `ReentrantLock`/`Condition`, phải dùng `lock.lock()/unlock()` theo protocol.

Ngược lại, sở hữu `ReentrantLock` bằng `lock.lock()` không tự cấp quyền gọi `lock.wait()` trên intrinsic monitor của chính `ReentrantLock` object. Hai cơ chế có ownership khác nhau.

## 16. Khi nào `notify()` có thể gây trì trệ với nhiều conditions?

Giả sử một hàng đợi dung lượng 1:

- Producers P1/P2 chờ “slot **trống**”.
- Consumers C1/C2 chờ “slot **có item**”.
- Cả hai nhóm đang dùng **wait set của cùng monitor `queue`**.

Nếu thread gọi `notify()` sau một transition cần đánh thức consumer mà nó lại chọn producer không đủ điều kiện, producer thức dậy nhưng thấy slot vẫn đầy và trở lại wait. Nếu không có future notifications từ threads khác, hệ thống có thể **không tiến triển** mặc dù một consumer đủ điều kiện cũng đang chờ.

```text
Wait set(queue) = {P1, P2, C1, C2}
state: buffer FULL

notify() → chọn P1 (arbitrary)
P1 giành monitor → thấy FULL → lại wait

C1/C2 vẫn trong wait set, dù có item để lấy.
Không có bảo đảm sẽ có tín hiệu tiếp theo.
```

Ví dụ trên mô tả **rủi ro chọn sai loại waiter trong các giao thức đa điều kiện**; để kết luận deadlock cụ thể cần xem interleavings và invariant của toàn bộ producer-consumer implementation. Nhưng nó đủ chứng minh rằng `notify()` không tự biết predicate nghiệp vụ của từng thread.

Giải pháp:

- Dùng `notifyAll()` với `while` để mọi waiters được kiểm tra lại, hoặc
- Dùng các `Condition` queues riêng `notEmpty/notFull` rồi `signal` nhóm thích hợp, hoặc
- Dùng sẵn `BlockingQueue` nếu không cần tự viết đồng bộ cấp thấp.

### 16.1. Thundering herd của `notifyAll` là trade-off

Nếu có 1.000 waiters và chỉ một token/tài nguyên, notifyAll có thể gây nhiều thread transitions và lock contention; phần lớn thức dậy chỉ để lại wait. Trong high-load production, có thể chọn abstraction như `Semaphore`, `Condition`, `BlockingQueue` hoặc work-queue pool thay vì intrinsic wait set chung.

Không hy sinh correctness chỉ vì giảm số lần wakeup: trước tiên chứng minh state machine không mất tín hiệu, không starvation, không deadlock trong các interleavings hợp lệ.

## 17. Interrupt và shutdown trong các hệ thống thực tế

Trong `OneSlotDemo`, worker catch interruption, khôi phục flag rồi kết thúc. Đó là đủ cho ví dụ không hủy giữa chừng, nhưng một dịch vụ production cần **lifecycle protocol** rõ hơn:

- Biến `closed` hoặc `stopping` được guard bằng cùng monitor.
- Khi đóng, đặt `closed=true` dưới monitor và gọi `notifyAll()`.
- Trong các loops `while`, kiểm tra đồng thời điều kiện nghiệp vụ và `closed` để quyết định dừng/throw exception.
- Quy định xử lý dữ liệu đã nằm trong queue: drain trước khi đóng hay từ chối hết.
- Xác định liệu `interrupt()` là yêu cầu cancel một operation hay đóng cả pipeline.
- Với nhiều workers, đảm bảo không thread nào chờ vô hạn sau khi đối tác thất bại.

Mẫu ý tưởng:

```java
synchronized (lock) {
    while (queue.isEmpty() && !closed) {
        lock.wait();
    }
    if (queue.isEmpty() && closed) {
        return; // hoặc tín hiệu end-of-stream tùy API.
    }
    // xử lý item
}
```

Đoạn này là **snippet** cần biến/kiểu/method phù hợp. `closed` cần được cập nhật cùng lock rồi notifyAll để waiters đang đợi thức dậy nhìn thấy thay đổi trạng thái và không quay lại wait mãi.

### 17.1. Đừng nuốt `InterruptedException` vô điều kiện

**Phản mẫu:**

```java
while (!ready) {
    try {
        lock.wait();
    } catch (InterruptedException ignored) {
        // Bỏ qua mọi yêu cầu dừng.
    }
}
```

Đây là snippet bên trong `synchronized(lock)` phù hợp. Nếu một thread bị cancel và `ready` không bao giờ true, nó có thể chờ lại mãi.

**Tốt hơn:** propagate `InterruptedException` từ method nếu API cho phép; nếu không, khôi phục flag và thoát tác vụ theo quyết định rõ ràng.

### 17.2. Không notify bằng cách interrupt bừa một thread khác

`Thread.interrupt()` là một **cơ chế yêu cầu interruption**, không phải replacement của predicate `ready`. Nếu thread đợi queue item và bạn chỉ interrupt mà không sửa state, nó có thể ném exception và hủy thao tác, không phải xử lý dữ liệu mong muốn.

Dùng đúng primitive đúng semantics: `notify/notifyAll` để gợi ý thay đổi guarded state; `interrupt` để báo hủy/ngắt; `Semaphore` cho permits; `BlockingQueue` cho trao đổi items.

## 18. Deadlock: giữ lock khác trong khi `wait()`

Một tình huống khó:

```text
T1:
  synchronized(A) {
      synchronized(B) {
          B.wait();    // Nhả B, VẪN GIỮ A
      }
  }

T2:
  synchronized(A) {    // Muốn vào để cập nhật predicate
      synchronized(B) {
          B.notifyAll();
      }
  }

T1 chờ T2 notify trên B.
T2 chờ T1 nhả A.
⇒ Deadlock theo protocol này.
```

**Quan trọng:** `B.wait()` là hợp lệ khi T1 sở hữu B; vấn đề không nằm ở `IllegalMonitorStateException` mà ở việc **không nhả monitor A**. Để sửa, giảm nested locks, không wait khi đang giữ lock khác mà notifier cần, và thống nhất lock order.

### 18.1. Monitor ordering và lock ordering

Nếu một workflow bắt buộc giữ nhiều locks, phải quy định thứ tự lấy chúng trên mọi code paths, giảm phạm vi critical sections và không gọi I/O chặn lâu khi còn giữ lock. Intrinsic monitor không tự phát hiện và giải quyết vòng chờ.

Java `ThreadMXBean.findDeadlockedThreads()` có thể giúp chẩn đoán một số deadlocks liên quan monitors/ownable synchronizers, nhưng **không thay thế reasoning về protocol**. Một chương trình chờ predicate không bao giờ trở thành true cũng có thể “treo” mà không xuất hiện trong deadlock detector vì nó không phải chu trình monitor ownership đơn thuần.

## 19. Phân tích thread dump và thread state

Với HotSpot JDK 17, có thể lấy thread dump qua:

```bash
jcmd <pid> Thread.print
```

Khi quan sát một thread, các trạng thái như `WAITING (on object monitor)`, `TIMED_WAITING (on object monitor)` hoặc `BLOCKED (on object monitor)` có thể giúp phân biệt:

- **WAITING on object monitor:** thread đã gọi `Object.wait` và đang đợi điều kiện/sự kiện.
- **BLOCKED on object monitor:** thread muốn giành monitor nhưng thread khác đang sở hữu.
- **TIMED_WAITING:** một thao tác chờ có timeout (nhưng state chi tiết còn phụ thuộc API và JVM).
- **Lock owner:** thông tin về monitor mà một thread đang giữ (nếu dump có thể suy ra).
- **Stack trace:** vị trí Java-level, ví dụ `Object.wait`, method của queue và synchronized code.

### 19.1. Có đo được trực tiếp wait set bằng public Java API không?

Java standard API không cung cấp `lock.getWaitSet()` trả về toàn bộ danh sách threads đang `wait` trên object. `Thread.getState()` chỉ trả trạng thái snapshot của một thread, không phải một danh sách phân biệt chính xác “wait set của object A”.

Có thể dùng thread dump/JFR/monitor instrumentation để chẩn đoán, nhưng results phụ thuộc implementation/timepoint. Không xây protocol dựa trên việc polling thread states để quyết định có cần gọi notify.

### 19.2. Vì sao một thread đã notify vẫn bị chậm?

Thread nhận notify có thể:

1. Chờ notifier rời synchronized block.
2. Cạnh tranh monitor với nhiều threads khác.
3. Chờ CPU scheduling nếu hệ thống quá tải.
4. Vào lại critical section rồi thấy predicate sai và wait lần nữa.

Vì vậy “đã gọi notifyAll nhưng consumer chưa chạy” không tự chứng minh notifyAll không hoạt động. Phải xem thread dumps, lock owner, guarded state và scheduling.

### 19.3. Log khởi đầu cho monitor contention

Trong ứng dụng có vấn đề hiệu năng, đo **monitor enter contention**, time spent blocked/waiting và số lượng notification/wakeups qua JFR hoặc profiler thích hợp, rồi correlate với throughput/p99 latency. Không giả định `Thread.State.WAITING` đồng nghĩa CPU đang tốn 100%; một thread đang wait thường không thực thi active work.

## 20. Một số thiết kế không nên tự viết bằng `wait/notify`

Các primitives hiện đại giải quyết nhiều loại coordination phổ biến:

| Nhu cầu | API thường phù hợp | Tránh tự viết |
| --- | --- | --- |
| Hàng đợi producer-consumer | `ArrayBlockingQueue`, `LinkedBlockingQueue` | Dễ thiếu shutdown/interrupt/fairness |
| Một thread chờ công việc hoàn tất | `CountDownLatch`, `Future.get`, `CompletableFuture` | Dễ lost notification nếu tự lưu cờ sai |
| Giới hạn số tác vụ đồng thời | `Semaphore` | Dễ xử lý permits sai |
| Nhiều worker gặp nhau tại pha | `CyclicBarrier`, `Phaser` | Dễ lỗi theo generation/phase |
| Cần nhiều condition trên cùng lock | `ReentrantLock` + `Condition` | Một wait set khó chọn đúng nhóm |
| Atomic state đơn giản | `AtomicBoolean`, `AtomicInteger`, `VarHandle` | Không cần wait set nếu chỉ cập nhật atomic không chặn |
| Chờ kết quả bất đồng bộ | `CompletableFuture` hoặc futures | Không nên tự wait trên `Thread` object |

Các API này không “đánh bại mọi deadlock” hay “tự thay thế hoàn toàn review concurrency correctness”; chúng cung cấp **abstractions có contract rõ hơn** so với tự thiết kế nhiều vòng wait/notify và lifecycle state.

## 21. Những hiểu lầm phổ biến

1. **“`Object.wait()` có thể gọi khi không giữ lock.”** Sai; cần monitor ownership của chính receiver.
2. **“Giữ `synchronized(a)` là đủ để gọi `b.wait()`.”** Sai nếu không giữ monitor `b`.
3. **“`wait()` chỉ nhả một mức reentrant lock.”** Sai; nhả toàn bộ ownership trên chính monitor receiver và giành lại tương ứng.
4. **“`wait()` nhả mọi locks của thread.”** Sai; chỉ monitor object nhận lời gọi.
5. **“`notify()` tự nhả monitor ngay.”** Sai; notifier tiếp tục giữ tới khi unlock theo protocol.
6. **“Thread được notify lập tức sở hữu monitor.”** Sai; phải cạnh tranh giành lại lock.
7. **“`notify()` luôn chọn thread đợi lâu nhất.”** Sai; không có FIFO/fairness guarantee.
8. **“`notifyAll()` cho phép mọi waiters vào critical section cùng lúc.”** Sai; monitor vẫn mutual exclusion.
9. **“`notify()` trước `wait()` được lưu lại như một permit.”** Sai; nếu không có waiter, notification không được tích lũy.
10. **“Chỉ cần `volatile ready` là check-then-wait ngoài synchronized an toàn.”** Sai; cần atomic guarded check/wait protocol.
11. **“`if (!ready) wait()` luôn đúng.”** Sai; spurious wakeups, state changes và nhiều conditions yêu cầu `while`.
12. **“`wait()` chỉ trả về khi có `notify()`.”** Sai; notifyAll, interrupt, timeout và spurious wakeup.
13. **“Sau timeout thì predicate đã true.”** Sai; timeout chỉ là sự kiện cho waiter tiếp tục nếu giành được lock.
14. **“`wait(0)` nghĩa không đợi.”** Sai; zero timeout tương đương indefinite wait.
15. **“`Thread.sleep()` nhả monitor như `wait()`.”** Sai; sleep không giải phóng monitor.
16. **“`Thread.State.WAITING` và `BLOCKED` giống nhau.”** Sai; một bên đợi sự kiện, một bên đợi lock.
17. **“`notifyAll` luôn hiệu quả nhất.”** Sai; có thể wake nhiều waiters không cần thiết.
18. **“`notify` luôn nhanh hơn và đúng hơn `notifyAll`.”** Sai; chọn sai loại waiter có thể khiến hệ thống không tiến triển.
19. **“Interrupt lúc wait luôn giết thread.”** Sai; thường báo `InterruptedException`, caller quyết định.
20. **“Khi wait ném `InterruptedException`, interrupt flag luôn còn true.”** Sai; status bị clear khi ném exception theo API.
21. **“Notification đồng thời với interrupt luôn ưu tiên interrupt.”** Sai; JLS mô tả nhiều thứ tự hợp lệ.
22. **“Thêm một `notifyAll` đủ thay việc cập nhật guarded state.”** Sai; predicate vẫn là nguồn sự thật.
23. **“Đang synchronized static method là đang khóa mọi instances.”** Sai; khóa `Class` object tương ứng.
24. **“Java có `lock.getWaitSet()` chuẩn trả chính xác danh sách waiters.”** Sai; không có API như vậy.
25. **“`ReentrantLock.lock()` cấp quyền gọi `reentrantLock.wait()`.”** Sai; explicit Lock ownership khác intrinsic monitor ownership.
26. **“`Condition.await()` không cần giữ associated Lock.”** Sai; Condition của ReentrantLock đòi lock ownership phù hợp.
27. **“Thread dump `BLOCKED` luôn nghĩa deadlock.”** Sai; có thể chỉ monitor contention tạm thời.
28. **“`join` và `notifyAll` là hai phương thức hoán đổi cho nhau.”** Sai; contract khác.
29. **“Không dùng `sleep` thì concurrent code chắc chắn không có race.”** Sai; tính đúng phụ thuộc protocol và synchronization.
30. **“`wait/notify` là giải pháp tốt nhất cho mọi concurrent queue.”** Sai; blocking queues và latches thường an toàn, rõ ràng hơn.
31. **“Thấy waiter đã rời wait set là đủ kết luận đã đọc shared data mới.”** Sai; còn phải giành monitor, thực thi dưới đồng bộ và kiểm tra predicate.
32. **“Synchronized chỉ ngăn chạy đồng thời, không có visibility guarantee.”** Sai; unlock/lock tạo happens-before theo JMM.
33. **“`notifyAll` làm Java tự kiểm tra mọi predicate.”** Sai; code của mỗi waiter phải có `while` để tự kiểm tra.
34. **“Giữ lock B trong `B.wait` sẽ khiến thread A không thể cập nhật B.”** Sai: `wait` nhả B để notifier có thể giành nó; vấn đề thường ở locks **khác** vẫn bị giữ.
35. **“Dùng `wait/notify` đúng thì hệ thống đảm bảo hard real-time deadline.”** Sai; scheduling/fairness/timing không có cam kết như thế.

## 22. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** Tại sao `wait()` không thể được gọi bên ngoài synchronized block trên cùng object?

**Đáp án:** Vì phải sở hữu monitor receiver. Nếu không, `IllegalMonitorStateException`. Monitor phối hợp thao tác kiểm tra predicate với việc vào wait set an toàn.

**Câu 2.** Một thread giữ monitor `m` hai mức reentrant rồi gọi `m.wait()`. Nó nhả bao nhiêu mức?

**Đáp án:** Nhả **toàn bộ** số mức sở hữu trên monitor `m`, rồi giành lại cùng số mức trước khi tiếp tục; không nhả locks của những objects khác.

**Câu 3.** Notifier gọi `m.notifyAll()` khi còn ở giữa `synchronized(m)`. Waiters có chạy tiếp code sau `wait()` ngay không?

**Đáp án:** Không. Chúng phải giành lại `m` sau khi notifier unlock và scheduling cho phép.

**Câu 4.** `m.notify()` có FIFO guarantee không?

**Đáp án:** Không, chọn một thread tùy ý từ wait set.

**Câu 5.** Vì sao kiểm tra `ready` ngoài `synchronized` dễ lost notification?

**Đáp án:** Notifier có thể đặt `ready=true` và notify **sau check nhưng trước wait**; notification không được lưu và waiter có thể ngủ mãi.

**Câu 6.** Vì sao dùng `while` thay `if`?

**Đáp án:** Để kiểm tra lại predicate sau notification, spurious wakeup, timeout hoặc khi thread khác đã thay state trước lúc waiter giành lại monitor.

**Câu 7.** `Thread.sleep(100)` dưới monitor có giải phóng monitor không?

**Đáp án:** Không. `sleep` không release intrinsic monitors đã sở hữu.

**Câu 8.** `wait(0)` là nonblocking call hay indefinite wait?

**Đáp án:** Indefinite wait theo API, có thể kết thúc bởi notification, interrupt hoặc spurious wakeup.

**Câu 9.** `InterruptedException` từ `wait` xảy ra khi nào và lúc đó thread có giữ monitor không?

**Đáp án:** Sau quá trình thoát wait set do interruption hợp lệ và **giành lại monitor**; thread ở trong synchronized block khi catch chạy nếu catch nằm trong block.

**Câu 10.** `notify()` gọi khi wait set rỗng có gây lỗi không?

**Đáp án:** Không, nếu đã có monitor ownership. Nhưng notification không được tích lũy cho waiter tương lai.

**Câu 11.** Cơ chế visibility chính của guarded state dưới `synchronized(lock)` là gì?

**Đáp án:** Unlock-lock happens-before của **cùng monitor**, không phải notify tự thay thế đồng bộ dữ liệu.

**Câu 12.** Trong `OneSlotDemo`, vì sao sum chắc chắn là 15 trong lần chạy không bị interrupt?

**Đáp án:** Producer đặt đủ năm số 1..5, consumer lấy đủ năm số bằng protocol guarded buffer; tổng `1+2+3+4+5=15`.

**Câu 13.** `Condition.await()` có nhả intrinsic monitor của object `ReentrantLock` không?

**Đáp án:** Nó nhả **associated explicit Lock** theo contract Condition, không phải “intrinsic monitor của object ReentrantLock”; hai ownership models khác nhau.

**Câu 14.** Vì sao `notifyAll` có thể tốn CPU hơn `notify`?

**Đáp án:** Nhiều waiters thức dậy tranh cùng một monitor dù phần lớn predicates vẫn sai; phải trở lại wait.

**Câu 15.** Khi một thread còn giữ monitor A, rồi `wait()` trên B, rủi ro nào?

**Đáp án:** Nó nhả B nhưng **vẫn giữ A**; nếu notifier cần A để chuyển predicate/gửi tín hiệu B, có thể tạo deadlock.

**Câu 16.** Muốn nhiều producer/consumer dùng condition queues riêng, API nào có thể phù hợp?

**Đáp án:** `ReentrantLock` với hai `Condition` `notFull` và `notEmpty`; hoặc tốt hơn cho queue phổ thông, `BlockingQueue` đã xây sẵn protocol.

**Câu 17.** `getState() == WAITING` có chứng minh chính xác thread đang ở wait set của object cụ thể không?

**Đáp án:** Không. WAITING cũng xuất hiện từ `join`/`park`, và snapshot có race; cần thread dump/diagnostics cùng stack/monitor nếu muốn điều tra.

**Câu 18.** Tại sao interruption và notification gần nhau không thể áp quy tắc “interrupt luôn thắng”?

**Đáp án:** JLS cho phép những thứ tự sự kiện khác nhau và quy định kết quả tương ứng; notification/interruption interactions có semantics riêng bảo vệ trạng thái/notification.

## 23. Tổng kết: hình dung đúng wait set và monitor

```text
             MỖI OBJECT M CÓ:
   ┌────────────────────────────────┐
   │ intrinsic MONITOR             │
   │ current owner (hoặc không ai)  │
   │                                │
   │ WAIT SET của M                 │
   │ {T2, T3, ...}                  │
   └────────────────────────────────┘

T1 notifier:
  synchronized(m) {
      predicate = true;   // state
      m.notifyAll();      // lấy waiters ra khỏi wait set
      ...                 // T1 vẫn giữ monitor lúc này
  }                       // T1 unlock

T2 waiter:
  synchronized(m) {
      while (!predicate) {
          m.wait();       // vào wait set, nhả monitor M
      }                   // được đánh thức không có nghĩa chạy ngay
      doWork();           // chỉ sau khi giành lại M và predicate đúng
  }

Thread States (quan sát khái niệm):
  WAITING       chờ event/predicate sau wait()
  BLOCKED       chờ chiếm monitor M
  RUNNABLE      đủ điều kiện thực thi khi đã giành lại M

Correctness:
  shared predicate + SAME monitor + while + state-change notify
  + interruption/shutdown policy rõ ràng.
```

**Ghi nhớ:** `wait` **nhả toàn bộ ownership của monitor receiver, đưa current thread vào wait set, rồi bắt buộc giành lại monitor trước khi tiếp tục**. `notify` chọn một waiter tùy ý; `notifyAll` đánh thức tất cả waiters trên **đúng object**, nhưng **không giải phóng monitor ngay** và không đảm bảo fairness. Notification là tín hiệu nhất thời; **predicate được bảo vệ bằng synchronized mới là sự thật**. `while` cần thiết vì spurious wakeups, timeouts và cạnh tranh state. Với bài toán phức tạp, ưu tiên những abstractions trong `java.util.concurrent` có protocol rõ ràng hơn.

### Tài liệu tham khảo chính thức (Java SE 17)

- [JLS 17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1): monitor ownership và synchronized.
- [JLS 17.2 — Wait Sets and Notification](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2): wait set, notify, notifyAll, spurious wakeups.
- [JLS 17.2.1 — Wait](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2.1): nhường rồi giành lại monitor và interrupt semantics.
- [JLS 17.2.2 — Notification](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2.2): chọn một/tất cả waiters, không ưu tiên FIFO.
- [JLS 17.2.4 — Interactions of Waits, Notification, and Interruption](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2.4).
- [JLS 17.4.4–17.4.5 — Synchronization Order/Happens-Before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).
- [Java SE 17 — `Object.wait()/notify()/notifyAll()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).
- [Java SE 17 — `Thread.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html).
- [Java SE 17 — `Condition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html).
- [Java SE 17 — `BlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
- [JDK 17 — `jcmd`, `Thread.print`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
