# Nhận diện `wait()`, `notify()`, `notifyAll()` và đối tượng làm khóa trong Java

Trong Java, mỗi object thông thường có một **intrinsic monitor** (còn gọi là *monitor lock* hoặc *intrinsic lock*). Cơ chế `synchronized` giúp thread **chiếm quyền sở hữu monitor** trước khi truy cập vùng trạng thái dùng chung; ba method `wait()`, `notify()` và `notifyAll()` của `java.lang.Object` giúp các thread **phối hợp dựa trên điều kiện trạng thái** khi cùng sử dụng monitor ấy.

Câu hỏi quan trọng nhất khi đọc code đa luồng không phải chỉ là “thread nào chờ?”, mà còn là:

> **Object nào đang làm khóa? Thread nào đang sở hữu monitor của object đó? Những thread nào đang đợi trên wait set gắn với đúng object ấy?**

Một ví dụ tối giản:

```java
final Object lock = new Object();
boolean ready = false;

// Thread chờ:
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // Chỉ đến đây khi điều kiện đã đúng.
}

// Thread phát tín hiệu, ở một thời điểm khác:
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

Đây là **hai đoạn dành cho hai luồng trong một thiết kế đồng bộ hoàn chỉnh**, không phải một tệp Java có thể chạy độc lập như viết ở trên. Mỗi thread phải kiểm tra và thay đổi `ready` **dưới cùng monitor `lock`**. Người học cần nhớ bốn sự thật:

1. `wait()`, `notify()` và `notifyAll()` là **instance methods trên `Object`**, không phải các static methods của `Thread`.
2. Muốn gọi một trong ba method trên object `lock`, thread hiện tại phải **đang giữ monitor của chính `lock`**, thường nhờ `synchronized (lock)`.
3. `lock.wait()` **nhả monitor `lock` một cách nguyên tử với việc chuyển thread sang trạng thái chờ**; thread có thể tiếp tục chỉ sau khi đáp ứng cơ chế đánh thức và **chiếm lại monitor đó** (hoặc bị gián đoạn theo quy tắc).
4. `lock.notify()` đánh thức **một waiter tùy ý** trên wait set của `lock` (nếu có); `lock.notifyAll()` đánh thức **tất cả waiters** trên wait set ấy. Thread phát tín hiệu **vẫn giữ monitor** cho đến khi thoát khỏi vùng `synchronized` hoặc nhả khóa bằng cơ chế thích hợp.

Bài giải thích chính xác monitor identity, cú pháp, vòng đời chờ/đánh thức, sự khác nhau giữa `wait` và `sleep`, vì sao phải dùng `while`, cách tránh bỏ lỡ tín hiệu (*lost notification*), xử lý `InterruptedException`, ví dụ producer–consumer và khi nào nên dùng các tiện ích `java.util.concurrent` thay cho monitor mức thấp. Tất cả ví dụ chạy độc lập sử dụng **Java 17+**, có tên file, lệnh `javac`/`java` và stdout được thiết kế **không phụ thuộc thứ tự scheduling ngẫu nhiên**.

## 1. Ba method này thuộc `Object`, không thuộc `Thread`

Các method chính có dạng:

```java
public final void wait() throws InterruptedException;
public final void wait(long timeout) throws InterruptedException;
public final void wait(long timeout, int nanos)
        throws InterruptedException;

public final void notify();
public final void notifyAll();
```

Đây là **API signatures để nhận diện**, không phải đoạn khai báo class mới. Những phương thức này do `java.lang.Object` cung cấp; `wait()`/`notify()`/`notifyAll()` là `final`, subclass không override được.

Do mọi class thông thường kế thừa `Object`, ta có thể thấy:

```java
Object lock = new Object();
lock.wait();
lock.notify();
lock.notifyAll();
```

Nhưng **chỉ viết được cú pháp không có nghĩa gọi hợp lệ tại runtime**. Các method này yêu cầu thread hiện tại đang giữ monitor tương ứng. Gọi `lock.wait()` hoặc `lock.notify()` khi không giữ `lock` sẽ gây `IllegalMonitorStateException`. Riêng `wait` còn có khả năng ném `InterruptedException`.

### Không lẫn với `Thread.sleep`

```java
Thread.sleep(100);
```

là lời gọi static method thuộc `Thread`. Nó **không phải** lời gọi vào wait set của `lock`, và bản thân `sleep` **không nhả monitor** thread đang nắm giữ.

Tương tự:
- `Thread.join()` là API chờ một thread kết thúc, nhưng cách dùng/contract ở mức ứng dụng khác cơ chế trực tiếp `lock.wait()`.
- `Object.wait()` là phối hợp bằng một monitor và một condition predicate.
- `Condition.await()` là cơ chế tương tự ở tầng `java.util.concurrent.locks`, nhưng phải dùng với đúng `Lock`/`Condition` tương ứng.

## 2. Monitor là gì?

Một **monitor** theo mô hình đồng bộ Java gắn với object. Khi thực hiện:

```java
synchronized (lock) {
    // critical section
}
```

thread phải lấy được intrinsic monitor của **object mà biểu thức `lock` trỏ tới**. Trong cùng thời điểm, **không có hai threads khác nhau** đồng thời giữ quyền sở hữu monitor ấy.

Một thread đã giữ monitor có thể đi vào một vùng `synchronized` khác với **cùng monitor** theo cơ chế *reentrancy*. Những lần vào lồng nhau thuộc về **cùng thread**, không phải cấp quyền cho thread khác.

### Monitor giúp giải quyết hai việc

1. **Mutual exclusion (loại trừ tương hỗ):** bảo vệ một critical section trước truy cập đồng thời không đúng.
2. **Ordering/visibility theo Java Memory Model:** thao tác unlock trên một monitor *happens-before* thao tác lock thành công kế tiếp trên chính monitor đó, giúp thread sau quan sát những cập nhật được công bố đúng cách.

`wait`/`notify` dùng thêm phần **condition synchronization**: không chỉ khóa dữ liệu, mà còn để thread không tiếp tục cho đến khi điều kiện nghiệp vụ đúng.

### Monitor không phải một biến `boolean`

`boolean ready` chỉ là **điều kiện trạng thái**. `Object lock` mới là **đối tượng dùng để đồng bộ**.

```text
Shared state: ready = false
Protecting monitor: lock object
Waiting thread: sở hữu lock -> kiểm tra ready -> lock.wait()
Signaling thread: sở hữu lock -> đặt ready=true -> lock.notifyAll()
```

Đừng nhầm “thread đang chờ ready” với “ready là object monitor”. Điều kiện có thể là `int count`, queue size, trạng thái đóng/mở, job đã hoàn tất... nhưng mọi truy cập liên quan phải đồng bộ đúng.

## 3. `synchronized` xác định object làm khóa

Có ba cách xuất hiện phổ biến:

| Code | Monitor được dùng |
| --- | --- |
| `synchronized (lock) { ... }` | Runtime object được tham chiếu bởi `lock` |
| `synchronized void method() { ... }` (instance method) | `this`, tức object receiver |
| `static synchronized void method() { ... }` | `SomeClass.class`, tức `Class` object tương ứng |

**Không phải** “mọi method synchronized của một class dùng chung một khóa”. Hai instances khác nhau của cùng class có **hai `this` monitors khác nhau**.

### Minh họa bằng ASCII

```text
Counter a = new Counter();
Counter b = new Counter();

a.increment() instance synchronized -> monitor của a
b.increment() instance synchronized -> monitor của b
Counter.resetAll() static synchronized -> monitor của Counter.class
```

Ba monitor này **khác nhau**. Nếu trạng thái cần bảo vệ thuộc về một counter instance, khóa instance có thể đúng. Nếu trạng thái là static shared data, khóa per-instance không đủ để bảo vệ toàn bộ chương trình.

### Cách kiểm tra mình có giữ monitor không

`Thread.holdsLock(Object)` trả về `true` nếu **thread hiện tại** giữ intrinsic monitor của object được chỉ định. Nó không báo “một thread khác đang giữ khóa”.

## 4. Chương trình: xác định monitor đang giữ

Lưu **`MonitorIdentityDemo.java`**:

```java
public class MonitorIdentityDemo {
    private final Object lock = new Object();

    private synchronized boolean holdsThis() {
        return Thread.holdsLock(this);
    }

    private boolean holdsDedicatedLock() {
        synchronized (lock) {
            return Thread.holdsLock(lock);
        }
    }

    public static void main(String[] args) {
        MonitorIdentityDemo demo = new MonitorIdentityDemo();

        System.out.println(Thread.holdsLock(demo));
        System.out.println(demo.holdsThis());
        System.out.println(demo.holdsDedicatedLock());

        synchronized (demo.lock) {
            System.out.println(Thread.holdsLock(demo.lock));
            System.out.println(Thread.holdsLock(demo));
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac -encoding UTF-8 MonitorIdentityDemo.java
java MonitorIdentityDemo
```

**Stdout chính xác:**

```text
false
true
true
true
false
```

Giải thích:
- Ban đầu `main` không giữ monitor của `demo`.
- Khi đi vào `synchronized` instance method `holdsThis()`, thread giữ monitor `this == demo`.
- Khi đi vào `synchronized(lock)`, thread giữ monitor riêng `demo.lock`.
- Giữ `demo.lock` không tự làm thread giữ `demo`. **Monitor identity là theo object cụ thể**, không chỉ theo class hay phương thức chứa code.

## 5. Quy tắc sở hữu monitor khi gọi `wait/notify`

Đối với:

```java
lock.wait();
lock.notify();
lock.notifyAll();
```

thread **phải đang giữ monitor của `lock`** tại thời điểm gọi.

Ví dụ hợp lệ:

```java
synchronized (lock) {
    lock.notifyAll();
}
```

Ví dụ sai:

```java
synchronized (otherLock) {
    lock.notifyAll(); // Chưa chắc giữ monitor lock!
}
```

Kể cả hai biến có type `Object` và hai objects được tạo gần nhau, chúng vẫn có identity khác nhau.

**Điểm quyết định là object receiver của lời gọi** `wait/notify/notifyAll`, không phải object của synchronized block bất kỳ.

Nếu `lock == otherLock` do hai biến alias cùng object, thread sẽ giữ đúng monitor. Nếu không, chỉ giữ `otherLock` không đáp ứng yêu cầu.

### Monitor của `this`

Trong một `synchronized` instance method, bạn thường có thể gọi:

```java
synchronized void awaitReady() throws InterruptedException {
    while (!ready) {
        wait();  // Tương đương this.wait().
    }
}
```

vì receiver implicit là `this` và thread đang giữ monitor `this`. Nhưng nếu bên trong gọi `someOtherObject.wait()` thì phải giữ monitor **của someOtherObject** riêng.

## 6. Lỗi `IllegalMonitorStateException` rõ nhất

Lưu **`WrongMonitorDemo.java`**:

```java
public class WrongMonitorDemo {
    public static void main(String[] args) {
        Object first = new Object();
        Object second = new Object();

        synchronized (first) {
            try {
                second.notify();
            } catch (IllegalMonitorStateException error) {
                System.out.println("notify: wrong monitor");
            }

            try {
                second.notifyAll();
            } catch (IllegalMonitorStateException error) {
                System.out.println("notifyAll: wrong monitor");
            }

            try {
                second.wait();
            } catch (IllegalMonitorStateException error) {
                System.out.println("wait: wrong monitor");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 WrongMonitorDemo.java
java WrongMonitorDemo
```

**Stdout:**

```text
notify: wrong monitor
notifyAll: wrong monitor
wait: wrong monitor
```

Trong chương trình, `main` giữ `first` nhưng calls đều nhắm `second`. `wait()` không thực sự chuyển sang chờ vì điều kiện sở hữu monitor chưa đáp ứng.

**Không sửa bằng cách chỉ thêm một `synchronized` bất kỳ.** Phải bao vùng kiểm tra điều kiện và wait/signal bằng **cùng monitor nhất quán** bảo vệ shared state.

## 7. `wait()` làm gì?

Với:

```java
synchronized (lock) {
    lock.wait();
}
```

và giả định thread chưa bị interrupt, monitor được giữ đúng:

1. Thread đang giữ monitor của `lock`.
2. Lời gọi `lock.wait()` đưa thread vào **wait set** của object `lock` và **nhả quyền sở hữu monitor `lock`** theo cơ chế nguyên tử của monitor wait.
3. Trong thời gian thread đang chờ, **thread khác có thể vào `synchronized(lock)`** để thay shared state.
4. Thread có thể trở nên đủ điều kiện thức dậy vì `notify`, `notifyAll`, interrupt, timeout với overload timed, hoặc **spurious wakeup**.
5. Trước khi `wait` hoàn tất bằng cách return hoặc ném `InterruptedException`, thread phải **lấy lại monitor `lock`** theo các quy tắc monitor.
6. Sau khi `wait` return bình thường, thread vẫn đang ở **bên trong vùng synchronized**, nên vẫn giữ monitor `lock` cho đến khi ra khỏi vùng đó.

**Từ khóa:** `wait` **không chỉ ngủ**; nó **nhả monitor receiver**, chờ, rồi **lấy lại monitor trước khi tiếp tục**.

### Nó có nhả tất cả locks đang giữ không?

**Không.** `lock.wait()` nhả monitor của **`lock`**. Nếu thread đang giữ một monitor **khác** do đồng bộ lồng nhau, nó không tự nhả monitor khác đó.

Ví dụ ý tưởng:

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

Thread nhả `inner` trong lúc đợi, nhưng vẫn giữ `outer`. Đây có thể tạo deadlock nếu thread phát tín hiệu phải lấy `outer` mới thay được predicate.

**Quy tắc thiết kế:** hạn chế giữ nhiều locks khi wait; định nghĩa rõ thứ tự khóa nếu bắt buộc.

## 8. `notify()` làm gì?

`lock.notify()` có tác dụng chọn **một thread bất kỳ** đang chờ trong wait set **của `lock`** (nếu có) để đưa tới giai đoạn có thể cạnh tranh lấy lại monitor.

Điều `notify()` **không bảo đảm**:
- Không bảo đảm chọn thread chờ lâu nhất.
- Không bảo đảm FIFO.
- Không bảo đảm thread được báo thức chạy ngay.
- Không làm predicate trở thành true.
- Không lập tức chuyển monitor từ thread phát tín hiệu sang thread nhận.
- Không “lưu sẵn token” nếu hiện tại không có thread nào đang wait.

Phải **thay shared state** phù hợp trước khi hoặc đồng thời với thông báo, dưới cùng monitor.

```java
synchronized (lock) {
    ready = true;
    lock.notify();
}
```

Sau `notify()`, thread phát tín hiệu vẫn có thể chạy tiếp **trong synchronized block**. Thread nhận phải chờ đến lúc lấy lại được monitor.

### `notify()` khi không có waiter

Nếu `notify()` được gọi hợp lệ khi wait set của object rỗng, lời gọi không đánh thức ai và không tích lũy một notification để thread tương lai dùng. Đây là một lý do **điều kiện trạng thái** mới là sự thật cần lưu, không phải “đã gửi notify” tự nó.

## 9. `notifyAll()` làm gì?

`lock.notifyAll()` thông báo cho **tất cả threads hiện nằm trong wait set của `lock`**. Chúng sau đó cạnh tranh lấy lại monitor theo cơ chế JVM.

**Không phải tất cả cùng chạy vùng synchronized một lúc**: intrinsic monitor vẫn chỉ được sở hữu bởi một thread tại một thời điểm.

Một số thread sau khi lấy monitor có thể thấy predicate vẫn false, vì:
- Một thread khác đã tiêu thụ tài nguyên trước;
- Có nhiều loại điều kiện dùng chung wait set;
- Predicate đã đổi lại;
- Thread thức dậy mà không có condition thỏa.

Vì vậy mỗi waiter vẫn phải kiểm tra lại condition trong `while`.

### `notifyAll` có phải chạy mọi thread trong chương trình?

**Không.** Nó chỉ tác động đến các waiters hiện đang ở **wait set của đúng receiver object**. Threads đang chờ trên monitor khác, đang sleep, đang làm I/O hay đợi ở một API khác không được `notifyAll` này trực tiếp đánh thức.

## 10. Bảng so sánh `wait`, `notify` và `notifyAll`

| Thuộc tính | `wait()` | `notify()` | `notifyAll()` |
| --- | --- | --- | --- |
| Khai báo tại | `Object` | `Object` | `Object` |
| Cần sở hữu monitor receiver? | Có | Có | Có |
| Bản thân nhả monitor receiver? | Có, trong lúc chờ | Không | Không |
| Mục tiêu | Tạm chờ điều kiện | Báo một waiter tùy ý | Báo tất cả waiters của object |
| Thread gọi bị chặn do chính API? | Thường có thể chờ | Không do chính notify | Không do chính notifyAll |
| Có thể ném `InterruptedException`? | Có | Không | Không |
| Có thể ném `IllegalMonitorStateException`? | Có | Có | Có |
| Bảo đảm predicate trở thành true? | Không | Không | Không |
| Tự thay đổi dữ liệu nghiệp vụ? | Không | Không | Không |
| Bảo đảm FIFO/fairness? | Không | Không | Không |

**Đừng hiểu `notifyAll` = thay `while` bằng `if`.** Hai cơ chế có vai trò khác nhau: notifyAll là **thông báo**, while là **điều kiện đúng mới đi tiếp**.

## 11. Predicate: sự thật phải được kiểm tra trong `while`

Một *condition predicate* là biểu thức mô tả **khi nào thread được phép tiếp tục**.

Ví dụ:
- `ready == true`.
- `!queue.isEmpty()` để consumer có thể lấy item.
- `queue.size() < capacity` để producer có thể thêm item.
- `availablePermits > 0`.
- `closed || hasWork` để waiter không treo vĩnh viễn sau khi service ngừng.

Mẫu đúng:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    doWork();
}
```

Mẫu dễ sai:

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    doWork();
}
```

### Vì sao phải dùng `while`?

Có **ít nhất ba lý do**:

1. **Spurious wakeup:** Java cho phép `wait` quay về mà không có thông báo tương ứng; cần kiểm tra lại.
2. **Cạnh tranh điều kiện:** waiter đã được thông báo nhưng trước khi lấy monitor, thread khác có thể làm predicate false hoặc tiêu thụ resource.
3. **Nhiều điều kiện trong cùng wait set:** `notifyAll` đánh thức cả những waiters không thuộc điều kiện đã trở thành true.

Vòng `while` kiểm tra điều kiện **sau khi đã lấy lại khóa** trước khi cho chạy hành động cần được bảo vệ.

## 12. Chương trình phối hợp tối thiểu, output xác định

Lưu **`WaitNotifyHandshakeDemo.java`**:

```java
public class WaitNotifyHandshakeDemo {
    private static final Object LOCK = new Object();
    private static boolean ready;

    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = new Thread(() -> {
            synchronized (LOCK) {
                ready = true;
                LOCK.notifyAll();
            }
        }, "worker");

        synchronized (LOCK) {
            worker.start();

            while (!ready) {
                LOCK.wait();
            }

            System.out.println("ready = " + ready);
        }

        worker.join();
        System.out.println("worker finished");
    }
}
```

```bash
javac -encoding UTF-8 WaitNotifyHandshakeDemo.java
java WaitNotifyHandshakeDemo
```

**Stdout:**

```text
ready = true
worker finished
```

Phân tích không dựa vào may rủi:
1. Main vào `synchronized(LOCK)`, giữ monitor.
2. Main `start` worker nhưng vẫn giữ monitor; worker phải chờ để vào synchronized region.
3. Main thấy `ready == false` nên gọi `LOCK.wait()`, **nhả LOCK**.
4. Worker lấy LOCK, đặt `ready = true` rồi `notifyAll()`.
5. Worker thoát vùng synchronized và nhả LOCK.
6. Main lấy lại LOCK, kiểm tra `while`; `ready` đã true, in dòng đầu.
7. Main rời vùng synchronized và `join` worker đã hoàn tất; in dòng sau.

**Tại sao không deadlock?** Vì main **nhả monitor khi wait**, cho worker cơ hội lấy monitor để thay điều kiện.

**Chú ý:** `join()` được gọi **bên ngoài synchronized(LOCK)**. Nếu main giữ LOCK rồi join trong khi worker cần LOCK để kết thúc, đó là một kiểu deadlock.

## 13. `wait` và monitor release có ý nghĩa gì?

Nếu main không nhả monitor, worker không thể vào:

```java
synchronized (LOCK) {
    while (!ready) {
        // Busy-spin trong synchronized block: SAI.
    }
}
```

Worker cần `LOCK` để đặt `ready = true` nên không tiến triển. Thậm chí sử dụng `Thread.sleep(...)` bên trong vòng lặp cũng **không nhả LOCK**, nên không giải quyết nút thắt.

`LOCK.wait()` đặc biệt hữu ích vì nó phối hợp hai yếu tố:
- **Atomically** nhả LOCK và gia nhập wait set, tránh khoảng hở nguy hiểm giữa “kiểm tra điều kiện” và “bắt đầu chờ”.
- Khi tiếp tục, lấy lại LOCK rồi cho code kiểm tra lại condition.

Cơ chế này khiến *guarded suspension* có thể lập trình đúng bằng intrinsic monitor.

## 14. Không bị “lost notification” nhờ kiểm tra predicate

Lỗi thiết kế:

```java
// Một thread:
synchronized (lock) {
    lock.notifyAll();
}

// Sau đó thread khác:
synchronized (lock) {
    lock.wait(); // Có thể chờ mãi.
}
```

Nếu thông báo đã xảy ra khi chưa ai chờ, wait set rỗng; notification **không được tích trữ**. Thread đến sau có thể chờ vĩnh viễn nếu không có thông báo tiếp.

Thiết kế đúng lưu **sự kiện có ý nghĩa** vào state:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

Và phía nhận:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Nếu signal đã xảy ra **trước** khi receiver lấy monitor, receiver sẽ thấy `ready == true` và **không wait**. Nếu receiver wait trước, signal làm thay predicate và đánh thức. **Thứ cần tồn tại bền giữa hai thời điểm là predicate**, không phải chính lời gọi notify.

### Khi predicate chuyển lại false thì sao?

Tùy domain, condition có thể là “item hiện có trong queue”, không phải event đã xảy ra một lần. Vì vậy consumer cần kiểm tra queue state sau mỗi lần thức dậy; một thông báo cũ không cấp quyền tự động lấy item nếu queue đã rỗng trở lại.

## 15. Chương trình không bỏ lỡ tín hiệu dù signal xảy ra trước

Lưu **`NotifyBeforeWaitSafeDemo.java`**:

```java
public class NotifyBeforeWaitSafeDemo {
    private static final Object LOCK = new Object();
    private static boolean ready;

    public static void main(String[] args)
            throws InterruptedException {

        synchronized (LOCK) {
            ready = true;
            LOCK.notifyAll(); // Chưa có waiter.
        }

        synchronized (LOCK) {
            while (!ready) {
                LOCK.wait(); // Không được gọi trong case này.
            }
            System.out.println("condition already true");
        }
    }
}
```

```bash
javac -encoding UTF-8 NotifyBeforeWaitSafeDemo.java
java NotifyBeforeWaitSafeDemo
```

**Stdout:**

```text
condition already true
```

`notifyAll` trước khi có waiter không “để dành tín hiệu”. Chương trình vẫn đúng vì **shared state `ready` đã được cập nhật và đọc dưới cùng monitor**.

### Không phải mọi thông báo cần biến boolean

Với producer–consumer, một queue chứa dữ liệu chính là predicate. Với một counter, `count > 0` là predicate. Với request đã hoàn tất, `result != null || failed` có thể là predicate nếu null được xử lý đúng. Quan trọng là thiết kế **state biểu diễn điều kiện thật**.

## 16. `notify()` đánh thức một waiter bất kỳ

Khi có ba threads cùng gọi `lock.wait()`, một lần `lock.notify()`:

- Có thể chọn **bất kỳ một** waiter trong wait set của `lock`.
- Không nhất thiết chọn waiter đã vào wait set trước.
- Không bảo đảm waiter được chọn xử lý thành công điều kiện.
- Không bảo đảm hai waiters còn lại tự được đánh thức khi predicate đổi.

Nếu tín hiệu cho biết **chỉ có một tài nguyên mới**, và **mọi waiter cùng chờ đúng một condition**, `notify()` có thể phù hợp với protocol được thiết kế đúng. Nhưng với nhiều conditions khác nhau trên cùng monitor, `notify()` có thể đánh thức waiter **không thể tiến triển**, làm một thread khác có thể tiến triển lại chưa được báo.

### Ví dụ ý tưởng: hai loại waiter

```text
Producer chờ: queue chưa đầy
Consumer chờ: queue không rỗng

Cả hai cùng wait() trên lock.
Một thread gọi notify() -> chọn một waiter bất kỳ.
Nếu chọn waiter có predicate vẫn false -> có thể không ai tiến triển.
```

Trong bounded buffer đơn giản dùng **một intrinsic monitor cho cả “not empty” và “not full”**, `notifyAll()` thường dễ chứng minh đúng hơn.

**Đừng chọn notify chỉ để “tiết kiệm đánh thức” khi chưa chứng minh mọi đường trạng thái đều có khả năng tiến triển.**

## 17. `notifyAll()` không “đánh thức cùng lúc để cùng giữ lock”

Trong ví dụ có nhiều waiters:

```java
synchronized (lock) {
    opened = true;
    lock.notifyAll();
}
```

Các waiter được đánh thức từ wait set nhưng **không tất cả lập tức chạy code sau `wait()`**. Chúng phải **cạnh tranh và chiếm lại lock từng thread một**. Lời gọi notifyAll chỉ là tín hiệu để các waiters thử tiến triển.

Điều này giữ đúng mutual exclusion của synchronized.

### Thứ tự thread nào tiếp tục không được Java bảo đảm

Nếu thread A và B cùng đợi, chương trình không được giả định stdout:

```text
A
B
```

thay vì:

```text
B
A
```

trừ khi có thêm cơ chế ép thứ tự phù hợp. Các ví dụ tiếp theo **không in dựa vào scheduler**: chúng lưu kết quả rồi sắp xếp sau khi cả hai threads kết thúc.

## 18. Ví dụ hai waiters được `notifyAll`, output xác định

Lưu **`NotifyAllBroadcastDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class NotifyAllBroadcastDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch WAITERS_READY =
            new CountDownLatch(2);

    private static boolean opened;
    private static final List<String> resumed = new ArrayList<>();

    private static Thread waiter(String name) {
        return new Thread(() -> {
            synchronized (LOCK) {
                WAITERS_READY.countDown();

                while (!opened) {
                    try {
                        LOCK.wait();
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                resumed.add(name);
            }
        }, name);
    }

    public static void main(String[] args)
            throws InterruptedException {

        Thread a = waiter("A");
        Thread b = waiter("B");

        a.start();
        b.start();

        WAITERS_READY.await();

        synchronized (LOCK) {
            opened = true;
            LOCK.notifyAll();
        }

        a.join();
        b.join();

        Collections.sort(resumed);
        System.out.println("resumed = " + resumed);
    }
}
```

```bash
javac -encoding UTF-8 NotifyAllBroadcastDemo.java
java NotifyAllBroadcastDemo
```

**Stdout:**

```text
resumed = [A, B]
```

Tại sao kết quả ổn định?

1. Mỗi waiter giảm `WAITERS_READY` **trong synchronized(LOCK)** rồi thực thi `LOCK.wait()` khi `opened` false.
2. Main đợi count về 0. Waiter cuối cùng sẽ nhả LOCK khi đi vào wait; main chỉ set `opened` sau khi lấy LOCK, nên không có lỗ hổng “đếm xong nhưng chưa wait” gây bỏ lỡ.
3. Main set predicate true và gọi `notifyAll()`.
4. Mỗi waiter lần lượt giành lại LOCK, thoát while và thêm tên vào `resumed` dưới cùng monitor.
5. Main `join` cả hai threads rồi sort kết quả trước khi in.

`CountDownLatch` ở đây chỉ điều phối **thời điểm cả hai waiters đã sẵn sàng** để demo đáng tin; bản chất mà chúng ta muốn quan sát vẫn là **`Object.wait/notifyAll`**.

**Không suy ra thứ tự chạy thực tế là A rồi B.** Sorting chỉ giúp stdout ổn định.

## 19. Monitor của instance và monitor của class

Một instance method:

```java
synchronized void await() throws InterruptedException {
    while (!ready) {
        wait(); // this.wait()
    }
}
```

giữ monitor `this`.

Một static synchronized method:

```java
static synchronized void signal() {
    SomeClass.class.notifyAll();
}
```

giữ monitor của `SomeClass.class`. Nếu thread khác đang đợi trên `instance.wait()`, `SomeClass.class.notifyAll()` **không đánh thức** waiter đó: chúng là **hai object monitors khác nhau**.

### Lỗi dễ mắc với static field

Giả sử `static boolean ready` là shared across all instances. Nếu mỗi instance dùng `synchronized(this)` để bảo vệ nó, hai threads làm việc trên **hai objects khác nhau** có thể truy cập field mà không mutual exclusion thống nhất.

Cần dùng một monitor chung nếu toàn bộ trạng thái là static:

```java
private static final Object LOCK = new Object();
private static boolean ready;
```

hoặc cân nhắc `static synchronized` và `Class` monitor khi contract phù hợp.

**Thực hành thông dụng:** dùng một `private static final Object LOCK` chuyên dụng thay vì để class monitor bị mã bên ngoài dùng tùy ý.

## 20. Ví dụ static và instance lock độc lập

Lưu **`InstanceVsClassLockDemo.java`**:

```java
public class InstanceVsClassLockDemo {
    private synchronized boolean instanceLockHeld() {
        return Thread.holdsLock(this);
    }

    private static synchronized boolean classLockHeld() {
        return Thread.holdsLock(InstanceVsClassLockDemo.class);
    }

    public static void main(String[] args) {
        InstanceVsClassLockDemo first = new InstanceVsClassLockDemo();
        InstanceVsClassLockDemo second = new InstanceVsClassLockDemo();

        System.out.println(first.instanceLockHeld());
        System.out.println(classLockHeld());

        synchronized (first) {
            System.out.println(Thread.holdsLock(first));
            System.out.println(Thread.holdsLock(second));
            System.out.println(
                    Thread.holdsLock(InstanceVsClassLockDemo.class));
        }
    }
}
```

```bash
javac -encoding UTF-8 InstanceVsClassLockDemo.java
java InstanceVsClassLockDemo
```

Stdout:

```text
true
true
true
false
false
```

**Giải thích:** `instanceLockHeld()` và `classLockHeld()` đều kiểm tra đúng monitor mà chúng đang giữ, nên trả true. Nhưng synchronized block trên `first` không khiến thread giữ `second` hoặc `InstanceVsClassLockDemo.class`.

## 21. Khóa chuyên dụng: `private final Object lock`

Mẫu khuyến nghị cho state riêng:

```java
final class Gate {
    private final Object lock = new Object();
    private boolean open;

    void open() {
        synchronized (lock) {
            open = true;
            lock.notifyAll();
        }
    }

    void await() throws InterruptedException {
        synchronized (lock) {
            while (!open) {
                lock.wait();
            }
        }
    }
}
```

Ưu điểm:
- **Lock identity ổn định:** field `final` không bị gán lại sau construction.
- **Encapsulation:** external caller không thể lấy trực tiếp private lock để giữ lâu hoặc notify sai protocol.
- **State + lock cùng một owner:** giảm khả năng code dùng hai monitors khác nhau.
- **Condition predicate rõ:** `open` được đọc/ghi trong `synchronized(lock)`.

Từ khóa `final` giữ reference đến lock không đổi; nó **không** biến `open` thành immutable. `open` vẫn mutable, nhưng được bảo vệ bởi monitor.

### Tại sao tránh `synchronized(this)` khi không cần?

Dùng `this` không sai về mặt ngôn ngữ, nhưng một public object có thể được mã bên ngoài dùng làm monitor:

```java
synchronized (gate) {
    // Caller giữ lock của gate rất lâu.
}
```

Nếu nội bộ Gate cũng `synchronized(this)`, caller có thể vô tình gây contention/deadlock. Private lock giảm **khả năng người dùng bên ngoài can thiệp**.

## 22. Tránh khóa trên `String` interned hoặc boxed numbers

Các object có thể được chia sẻ ngoài ý muốn:

```java
String lock = "GLOBAL";      // String literal có thể intern.
Integer number = 100;        // Boxing/cache có thể chia sẻ object.
```

Nếu dùng chúng làm monitor, code không liên quan có thể vô tình khóa cùng object.

**Không khuyến khích:**

```java
synchronized ("GLOBAL") {
    // Có thể vô tình khóa trên interned String chung.
}
```

**Khuyến nghị:**

```java
private final Object lock = new Object();
```

Đối với thread coordination, lock object nên:
- Có identity riêng biệt được chọn có chủ đích;
- Không bị thay reference khi đang sử dụng;
- Không bị publish tùy tiện;
- Đi cùng một tập shared state/condition rõ ràng.

**Đừng dùng một object mutable được thay mới làm lock**, ví dụ field `lock = new Object()` ở giữa vòng đời nếu nhiều threads vẫn chờ trên monitor cũ; khi đó signal trên monitor mới sẽ không đánh thức các waiters của monitor cũ.

## 23. `wait()` và `Thread.sleep()`: phân biệt chính xác

| Thuộc tính | `Object.wait()` | `Thread.sleep(duration)` |
| --- | --- | --- |
| Thuộc API | Instance method của Object | Static method của Thread |
| Cần `synchronized` receiver? | Có | Không |
| Mục đích chính | Chờ predicate/monitor notification | Tạm dừng trong thời lượng |
| Nhả intrinsic monitor đang chờ? | Có, **monitor receiver** | Không tự nhả bất kỳ monitor đang giữ |
| Có wakeup do `notify`? | Có thể | Không |
| Có wakeup do timeout? | Với timed wait | Có thời lượng sleep |
| Có thể bị interrupt? | Có | Có |
| Có spurious wakeup theo contract? | Có | Không dùng như condition wait |
| Cần while predicate? | Có cho guarded condition | Sleep không thay condition protocol |

### Code minh họa sai

```java
synchronized (lock) {
    while (!ready) {
        Thread.sleep(10);
    }
}
```

Nếu thread khác cần `lock` để sửa `ready` thì nó bị khóa ngoài. `sleep` không giúp nhả lock, dẫn đến không tiến triển.

### Code đúng cho monitor predicate

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Đừng dùng “ngủ 100ms để chắc chắn producer chạy trước” như công cụ kiểm tra race; lịch chạy threads không được bảo đảm theo giấc ngủ.

## 24. Timeout: `wait(long)` và `wait(long, int)`

Ba overload:

```java
lock.wait();                  // Chờ không có timeout định trước.
lock.wait(200L);             // Timed wait với timeout milliseconds.
lock.wait(200L, 500_000);    // Milliseconds + nanos part.
```

Phải giữ monitor `lock` cho cả ba.

Lưu ý:
- `wait(0)` có nghĩa **chờ vô thời hạn** trừ các nguyên nhân thức dậy được quy định; nó **không** có nghĩa “đợi zero và trả ngay”.
- `wait(long)` nhận timeout milliseconds không âm; timeout âm làm phát sinh `IllegalArgumentException`.
- Overload `wait(long, int)` có quy tắc tham số, trong đó `nanos` hợp lệ từ `0` đến `999_999`; out-of-range làm phát sinh `IllegalArgumentException`.
- Một timed wait có thể trả về vì tín hiệu, interrupt, spurious wakeup hoặc timeout; **không đồng nghĩa predicate true**.
- Scheduler/monitor contention có thể làm thời gian thực tế trước khi thread tiếp tục **khác thời lượng truyền vào**; không dựa vào chính xác từng millisecond để kết luận.

### Dùng timeout với condition loop

```java
synchronized (lock) {
    while (!ready) {
        lock.wait(500L);
        // Sau mỗi lần return vẫn phải kiểm tra lại ready.
    }
}
```

Đoạn này **không** có nghĩa sẽ thoát sau tổng cộng 500ms; mỗi vòng có thể chờ tới 500ms rồi lặp lại vô hạn nếu `ready` luôn false.

Nếu bài toán yêu cầu **tổng thời hạn**, phải tính **remaining time** từ deadline, thường bằng đồng hồ monotonic `System.nanoTime()` và xử lý conversion cẩn thận để không vô tình gọi `wait(0)` khi mục tiêu là timeout.

## 25. Chương trình timed wait (không dự đoán elapsed time)

Lưu **`TimedWaitDemo.java`**:

```java
public class TimedWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Object lock = new Object();

        synchronized (lock) {
            lock.wait(20L);
            System.out.println("wait returned");
        }

        System.out.println("main continues");
    }
}
```

```bash
javac -encoding UTF-8 TimedWaitDemo.java
java TimedWaitDemo
```

**Stdout:**

```text
wait returned
main continues
```

Không có thread phát tín hiệu. Trong lần chạy thông thường, timed wait trả về khi timeout trôi qua; Java cũng cho phép spurious wakeup. Dù lý do là gì, chương trình không đo hoặc dự đoán thời gian chính xác.

**Đừng lấy timed wait đơn lẻ thay cho việc chờ một điều kiện nghiệp vụ**: chương trình đúng phải kiểm tra predicate nếu có shared state.

## 26. `InterruptedException`: thread có thể bị yêu cầu dừng chờ

`wait()` khai báo:

```java
throws InterruptedException
```

Nếu thread bị interrupt trong lúc chờ (hoặc có interrupt status thích hợp ở thời điểm gọi theo contract), lời gọi có thể ném `InterruptedException` sau các bước monitor cần thiết.

**Quan trọng về lock:** khi thread đang chờ trên monitor và bị interrupt, nó phải thực hiện việc lấy lại monitor theo quy tắc trước khi lời gọi `wait` hoàn tất bằng exception. Nó không “bỏ chạy khỏi synchronized block” mà bỏ qua kiểm soát monitor.

Trong handler:

```java
try {
    lock.wait();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    return;
}
```

**Khuyến nghị:** nếu method không thể xử lý interrupt một cách có ý nghĩa, **truyền tiếp** `InterruptedException` lên caller. Nếu bắt exception tại boundary và muốn bảo toàn yêu cầu ngắt, khôi phục interrupt status bằng `Thread.currentThread().interrupt()`, rồi kết thúc có kiểm soát.

**Đừng âm thầm nuốt interrupt:**

```java
catch (InterruptedException ignored) {
    // Không có chính sách xử lý: dễ khiến thread không chịu dừng.
}
```

## 27. Ví dụ interrupt waiter, output xác định

Lưu **`InterruptWaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                entered.countDown();

                try {
                    lock.wait();
                } catch (InterruptedException error) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            }
        });

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("interrupted = " + interrupted.get());
        System.out.println("worker alive = " + worker.isAlive());
    }
}
```

```bash
javac -encoding UTF-8 InterruptWaitDemo.java
java InterruptWaitDemo
```

**Stdout:**

```text
interrupted = true
worker alive = false
```

Ngay sau `entered.countDown()`, worker có thể đã vào `lock.wait()` hoặc chưa. Cả hai trường hợp đều hợp lệ:
- Nếu worker đã wait, interrupt khiến wait ném exception sau khi lấy lại monitor.
- Nếu interrupt xảy ra trước lúc wait thực sự chuyển sang chờ, `wait` vẫn xử lý interrupt status theo contract.

Vì vậy test dùng latch và interrupt, **không sleep để hy vọng race xảy ra theo đúng thứ tự**.

AtomicBoolean dùng để chuyển thông tin cho main; `join()` cũng bảo đảm worker đã kết thúc trước khi main in trạng thái.

## 28. Những trạng thái `Thread.State` dễ gây nhầm

Java định nghĩa các trạng thái:

- `NEW`: thread chưa được start.
- `RUNNABLE`: đang chạy hoặc đủ điều kiện chạy theo ngữ nghĩa JVM.
- `BLOCKED`: đang chờ lấy monitor để vào synchronized block/method.
- `WAITING`: đang chờ vô thời hạn qua một API như `Object.wait()` không timeout, `Thread.join()` không timeout...
- `TIMED_WAITING`: chờ có thời hạn, ví dụ timed wait hoặc sleep.
- `TERMINATED`: đã kết thúc.

**Sự khác nhau quan trọng:**

```text
Thread B muốn vào synchronized(lock)
trong khi Thread A đang giữ lock
  -> B có thể ở BLOCKED (chờ monitor).

Thread B đã sở hữu lock rồi gọi lock.wait()
  -> B nhả lock, sau đó có thể ở WAITING.

Thread A notifyAll, nhưng vẫn giữ lock
  -> B chưa chạy code sau wait;
     B còn cần lấy lại monitor, có thể ở BLOCKED.
```

Không nên viết test yêu cầu trạng thái phải luôn là `WAITING` ở một thời điểm cụ thể mà không có cơ chế kiểm soát race; `getState()` là một **snapshot racy** giữa các threads.

### `WAITING` không đồng nghĩa “đang chờ object lock”

Một thread `WAITING` có thể đang `Thread.join()` hoặc chờ cơ chế khác. Để xác định **monitor nào** có liên quan, phải đọc code/protocol hoặc dùng công cụ quan sát thread dump/stack phù hợp.

## 29. `notify` không truyền monitor ngay lập tức

Một tình huống:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
    doSomeLongCalculation();
}
```

Trong lúc `doSomeLongCalculation()` còn chạy và thread phát tín hiệu vẫn giữ monitor, waiters đã được báo vẫn **không thể tiếp tục qua `wait()`** nếu chưa lấy lại monitor.

Vì vậy tốt hơn khi có thể:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}

// Công việc dài thực hiện ngoài vùng giữ lock.
doSomeLongCalculation();
```

Tối ưu này phải giữ **tính đúng của invariant**. Không tự ý di chuyển thao tác cần atomicity ra ngoài critical section nếu làm thay đổi nghĩa chương trình.

### Tránh giữ lock khi gọi code không kiểm soát

Callback/HTTP call/SQL query dưới `synchronized(lock)` có thể giữ monitor rất lâu, chặn cả waiters và signallers. Hãy giới hạn vùng bảo vệ đúng shared state.

## 30. Producer–consumer: bài toán kinh điển

Ta có một **queue/buffer chia sẻ**:
- Producer chờ khi queue **đầy**.
- Consumer chờ khi queue **rỗng**.
- Producer `put` làm queue từ rỗng thành có item có thể đánh thức consumer.
- Consumer `take` làm queue từ đầy thành còn chỗ có thể đánh thức producer.

Hai điều kiện:

```java
while (queue.size() >= capacity) {
    lock.wait(); // Producer chờ "not full".
}

while (queue.isEmpty()) {
    lock.wait(); // Consumer chờ "not empty".
}
```

Cả hai cùng dùng một lock object thì thường chọn **`notifyAll()`** sau khi thay queue. Waiters thức dậy phải kiểm tra lại predicate của riêng mình.

### Vì sao queue là state tốt hơn notification?

Queue phản ánh **tình trạng còn item hay không**, kể cả khi producer tạo item trước khi consumer bắt đầu chờ. Một notification không được lưu lại; item trong queue thì vẫn ở đó cho tới khi consumer lấy.

**Đây là bản chất của condition waiting đúng:** chờ **state**, không chờ “một lời gọi notify trừu tượng”.

## 31. Ví dụ đơn giản: một producer, một consumer

Lưu **`SingleItemBufferDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

final class OneSlotBuffer {
    private final Object lock = new Object();
    private Integer value;

    void put(int next) throws InterruptedException {
        synchronized (lock) {
            while (value != null) {
                lock.wait();
            }

            value = next;
            lock.notifyAll();
        }
    }

    int take(CountDownLatch waiting)
            throws InterruptedException {

        synchronized (lock) {
            while (value == null) {
                waiting.countDown();
                lock.wait();
            }

            int result = value;
            value = null;
            lock.notifyAll();
            return result;
        }
    }

    boolean isEmpty() {
        synchronized (lock) {
            return value == null;
        }
    }
}

public class SingleItemBufferDemo {
    public static void main(String[] args)
            throws InterruptedException {

        OneSlotBuffer buffer = new OneSlotBuffer();
        CountDownLatch waiting = new CountDownLatch(1);
        int[] received = new int[1];

        Thread consumer = new Thread(() -> {
            try {
                received[0] = buffer.take(waiting);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        waiting.await();
        buffer.put(42);
        consumer.join();

        System.out.println("received = " + received[0]);
        System.out.println("buffer empty = " + buffer.isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 SingleItemBufferDemo.java
java SingleItemBufferDemo
```

**Stdout:**

```text
received = 42
buffer empty = true
```

Vì sao không race?
1. Consumer bắt đầu, lấy lock của buffer.
2. Queue rỗng, consumer báo latch rồi gọi `lock.wait()`; việc nhả lock thuộc thao tác wait.
3. Main chờ latch trước khi `put(42)`.
4. Producer (main) chỉ vào được `put` synchronized sau khi consumer nhả lock; sau đó set item và `notifyAll`.
5. Consumer lấy lại lock, thấy item, nhận 42, xóa slot, `notifyAll` và trả về.
6. Main `join` consumer rồi mới đọc kết quả.

**Giới hạn của ví dụ:** dùng một slot `Integer`, không dùng `null` làm item hợp lệ. Với API tổng quát, phải có contract rõ việc null có được đưa vào queue hay không.

## 32. Producer–consumer có nhiều threads: bounded buffer

Với nhiều producers/consumers, cần bảo vệ:
- `size() < capacity` trước khi put.
- `!queue.isEmpty()` trước khi take.
- Bất kỳ cập nhật nào tới queue.
- `notifyAll` sau khi trạng thái có thể cho phép nhóm waiter khác tiếp tục.

Một ví dụ đầy đủ dùng `ArrayDeque`, monitor chuyên dụng và hai methods:
- `put` đợi đến khi còn chỗ.
- `take` đợi đến khi có phần tử.

**Vì monitor được giữ đúng trong cả kiểm tra, thay đổi và signaling**, không có lỗ hổng check-then-act khiến hai consumers cùng lấy một item.

## 33. Chương trình bounded buffer Java 17 hoàn chỉnh

Lưu **`BoundedBufferDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class BoundedBuffer<T> {
    private final Object lock = new Object();
    private final ArrayDeque<T> queue = new ArrayDeque<>();
    private final int capacity;

    BoundedBuffer(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity <= 0");
        }
        this.capacity = capacity;
    }

    void put(T value) throws InterruptedException {
        synchronized (lock) {
            while (queue.size() == capacity) {
                lock.wait();
            }

            queue.addLast(value);
            lock.notifyAll();
        }
    }

    T take() throws InterruptedException {
        synchronized (lock) {
            while (queue.isEmpty()) {
                lock.wait();
            }

            T value = queue.removeFirst();
            lock.notifyAll();
            return value;
        }
    }

    int size() {
        synchronized (lock) {
            return queue.size();
        }
    }
}

public class BoundedBufferDemo {
    public static void main(String[] args)
            throws InterruptedException {

        BoundedBuffer<Integer> buffer = new BoundedBuffer<>(3);
        List<Integer> received =
                Collections.synchronizedList(new ArrayList<>());

        Thread producer1 = new Thread(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        Thread producer2 = new Thread(() -> {
            try {
                for (int i = 6; i <= 10; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        Runnable consumeFive = () -> {
            try {
                for (int i = 0; i < 5; i++) {
                    received.add(buffer.take());
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        };

        Thread consumer1 = new Thread(consumeFive);
        Thread consumer2 = new Thread(consumeFive);

        consumer1.start();
        consumer2.start();
        producer1.start();
        producer2.start();

        producer1.join();
        producer2.join();
        consumer1.join();
        consumer2.join();

        Collections.sort(received);

        int sum = received.stream()
                .mapToInt(Integer::intValue).sum();

        System.out.println("received = " + received);
        System.out.println("sum = " + sum);
        System.out.println("buffer size = " + buffer.size());
    }
}
```

```bash
javac -encoding UTF-8 BoundedBufferDemo.java
java BoundedBufferDemo
```

**Stdout:**

```text
received = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
sum = 55
buffer size = 0
```

### Vì sao output không phụ thuộc scheduling?

Producers tạo đúng các giá trị 1..10, mỗi giá trị một lần. Consumers thực hiện tổng cộng đúng 10 lần `take`, và mỗi thao tác remove xảy ra khi giữ monitor duy nhất nên không lấy cùng item hai lần. Sau khi join toàn bộ threads, main **sort danh sách đã nhận** trước khi in; nó không khẳng định thứ tự tiêu thụ ban đầu.

### Vì sao dùng `notifyAll`?

Cùng một monitor có **hai predicates khác nhau**:
- Producers chờ queue chưa đầy.
- Consumers chờ queue không rỗng.

Nếu chỉ `notify()`, có thể đánh thức thread không thỏa điều kiện trong một số lịch chạy; thread ấy quay lại wait và một nhóm cần tiến triển lại chưa được báo. `notifyAll` + `while` giúp các waiters tự lọc theo predicate.

### Các giới hạn cần nhận diện

- `ArrayDeque` không cho phần tử null; code nhận null có thể ném `NullPointerException`. Hợp đồng nên validate đầu vào khi cần.
- Demo không triển khai `close()`/shutdown; hệ thống thật cần cách báo producers/consumers dừng chờ khi dịch vụ kết thúc.
- Nếu một thread bị interrupt và thoát giữa chừng, thiết kế cần chính sách cancellation, báo lỗi cho coordinator và có thể gửi tín hiệu cho những waiters còn lại.
- Chương trình không hứa thứ tự các phần tử **được lấy**; chỉ tập kết quả cuối và tổng là xác định.

Trong ứng dụng thực tế, `BlockingQueue` đã xử lý nhiều chi tiết đúng đắn và nên được ưu tiên nếu không có lý do học hoặc tối ưu đặc biệt.

## 34. Vì sao `if (...) wait()` có thể sai trong buffer?

Giả sử có hai consumers A, B:
1. Queue đang rỗng, cả hai wait.
2. Producer put một item, notifyAll.
3. Cả A và B có cơ hội thức dậy, nhưng chỉ một consumer lấy item trước.
4. Consumer còn lại khi lấy được monitor sẽ thấy queue lại **rỗng**.

Với:

```java
if (queue.isEmpty()) {
    lock.wait();
}
return queue.removeFirst();
```

consumer còn lại có thể cố remove từ queue rỗng.

Với:

```java
while (queue.isEmpty()) {
    lock.wait();
}
return queue.removeFirst();
```

nó nhận thấy predicate vẫn false và đợi tiếp.

**Spurious wakeup** là một lý do độc lập khác khiến dùng `while` là bắt buộc đối với guarded wait, ngay cả khi chương trình “chỉ có một producer, một consumer”.

## 35. `notifyAll` khác `notify` về liveness, không chỉ tốc độ

`notifyAll` có chi phí đánh thức nhiều waiters, thường được gọi là nguy cơ *thundering herd*. Nhưng **tính đúng trước, tối ưu sau**:

- Nếu chỉ có một condition và một thread có thể giải quyết công việc, `notify` có thể đủ khi đã chứng minh protocol an toàn.
- Nếu nhiều conditions chia sẻ wait set, `notifyAll` đơn giản hơn cho liveness.
- Nếu có nhiều classes của waiters, `notify` có nguy cơ chọn sai nhóm.
- Nếu muốn tối ưu cao với hai wait queues tách biệt, cân nhắc `ReentrantLock` với **hai `Condition` objects** (`notEmpty`, `notFull`), hoặc dùng `BlockingQueue`.

**Không có thứ tự FIFO hay fairness mặc định** cho `notifyAll`. Nó làm các waiter đủ điều kiện tranh monitor, chứ không xếp hàng theo lịch của bạn.

## 36. Không dùng `notify` như cơ chế truyền dữ liệu

Đoạn:

```java
synchronized (lock) {
    lock.notifyAll();
}
```

không truyền một message payload tới waiter. Java monitor notification chỉ là **tín hiệu thay đổi trạng thái có thể liên quan**.

Dữ liệu phải được lưu ở nơi có synchronization/happens-before thích hợp:

```java
synchronized (lock) {
    result = 42;
    finished = true;
    lock.notifyAll();
}
```

Waiter:

```java
synchronized (lock) {
    while (!finished) {
        lock.wait();
    }
    int answer = result;
}
```

Vì cả producer và consumer dùng cùng lock, memory visibility được thiết lập qua monitor synchronization, không cần riêng một flag `volatile` cho đúng giao thức này.

### Có nên thêm `volatile`?

Có thể không cần khi **tất cả** truy cập vào predicate và dữ liệu liên quan đều thực hiện dưới đúng monitor. `volatile` **không thay thế** thao tác nguyên tử check-predicate + wait dưới cùng monitor; thêm volatile mà vẫn kiểm tra ngoài lock rồi wait có thể tạo race.

## 37. Java Memory Model: vì sao đọc lại state thấy cập nhật?

Một quy tắc cốt lõi: **unlock monitor M happens-before mọi lock thành công sau đó trên chính M**.

Trong protocol:

```java
// Thread A:
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}

// Thread B:
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // đọc ready và state liên quan
}
```

Thread A cập nhật `ready` khi giữ monitor, sau đó nhả monitor. Thread B lấy lại monitor trước khi kiểm tra tiếp. Memory model bảo đảm quan hệ visibility đúng theo monitor synchronization.

**Không chỉ notification tạo nên ordering:** việc giữ và nhả cùng monitor là phần thiết yếu. Nếu một thread ghi `ready` ngoài monitor và thread khác đọc ngoài monitor mà không synchronization, bạn có thể có data race dù vẫn có một lệnh notify ở nơi khác.

### Không làm condition predicate “ngoài khóa”

Không nên:

```java
if (!ready) {              // Không được bảo vệ bởi lock.
    synchronized (lock) {
        lock.wait();
    }
}
```

Giữa kiểm tra `!ready` và vào synchronized, thread khác có thể đặt `ready = true`, notify rồi kết thúc. Thread này có thể wait mãi dù condition đã đúng. Đúng là **kiểm tra predicate và wait cùng nằm trong synchronized(lock)**.

## 38. Reentrancy và `wait`

Intrinsic monitors của Java có tính **reentrant**: cùng thread có thể lấy monitor đã sở hữu nhiều lần qua synchronized lồng nhau.

Ví dụ:

```java
synchronized (lock) {
    synchronized (lock) {
        // Thread vẫn là owner của cùng monitor.
    }
}
```

Khi `lock.wait()` được gọi trong quá trình giữ monitor nhiều lần, JVM nhả monitor receiver theo mức sở hữu cần thiết cho wait, và khi return/throw theo quy tắc, thread lấy lại monitor tương ứng để các lớp synchronized lồng vẫn hợp lệ.

**Không nhầm** với việc giải phóng **mọi monitors khác nhau**. Nếu một thread cũng giữ `otherLock`, `lock.wait()` không tự nhả `otherLock`.

### Rủi ro deadlock khi giữ khóa ngoài

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

Nếu thread khác cần outer mới gọi `inner.notifyAll()`, nó sẽ bị chặn vì waiter vẫn giữ outer. Khi thiết kế, tránh khóa lồng nhiều monitor trong thao tác chờ hoặc đặt ra thứ tự và ranh giới rất rõ.

## 39. `wait`, `notify` và visibility không thay thế cấu trúc chương trình

Một monitor protocol đúng cần:

1. **State được khai báo rõ**: queue, flag, count, mode.
2. **Monitor ổn định**: một object khóa đúng cho mỗi tập invariant.
3. **Mọi truy cập tới protected state** được đồng bộ đúng.
4. **Predicate trong while** để quyết định khi nào thread được đi tiếp.
5. **Tín hiệu sau khi state change** có thể cho phép waiters tiến triển.
6. **Error/cancellation path**: handling interrupt và shutdown.
7. **Không gọi method chờ vô thời hạn** khi không có thread nào có thể làm condition đúng.
8. **Không giữ lock khi làm công việc không cần bảo vệ**.

Không nên coi một lời gọi `notifyAll()` là “sửa mọi lỗi đồng bộ” nếu code vẫn có data race, deadlock hoặc predicate thiếu chính xác.

## 40. Khi nào nên dùng `java.util.concurrent` thay thế?

Nhiều bài toán đồng bộ đã có API cấp cao:

| Nhu cầu | API thường thích hợp |
| --- | --- |
| Producer–consumer buffer | `BlockingQueue` (ví dụ `ArrayBlockingQueue`) |
| Chờ N thao tác hoàn thành | `CountDownLatch` |
| Đồng bộ các giai đoạn | `Phaser`, `CyclicBarrier` tùy use case |
| Giới hạn số hoạt động đồng thời | `Semaphore` |
| Gửi một kết quả tương lai | `CompletableFuture` / `Future` |
| Exclusive lock và nhiều wait conditions | `ReentrantLock` + `Condition` |
| Các counters đơn giản | `AtomicInteger` / `LongAdder` khi phù hợp |
| Task scheduling và thread pools | `ExecutorService` |

Những API này cung cấp contracts rõ hơn cho nhiều trường hợp, giảm nguy cơ quên `while`, dùng sai monitor hoặc bỏ lỡ notification.

**Tuy nhiên hiểu `Object.wait/notify` vẫn quan trọng**:
- Để đọc và bảo trì mã Java cũ.
- Để hiểu bản chất monitor và `synchronized`.
- Để phân biệt deadlock, contention và condition waits.
- Để thiết kế class có internal synchronization đúng khi cần.

## 41. `BlockingQueue` thay cho hand-written wait/notify

Ví dụ chức năng tương tự một buffer một slot, nhưng dùng thư viện chuẩn:

Lưu **`BlockingQueueAlternativeDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueAlternativeDemo {
    public static void main(String[] args)
            throws InterruptedException {

        BlockingQueue<Integer> queue =
                new ArrayBlockingQueue<>(1);

        Thread producer = new Thread(() -> {
            try {
                queue.put(42);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        producer.start();
        int result = queue.take();
        producer.join();

        System.out.println("received = " + result);
        System.out.println("remaining = " + queue.size());
    }
}
```

```bash
javac -encoding UTF-8 BlockingQueueAlternativeDemo.java
java BlockingQueueAlternativeDemo
```

Stdout:

```text
received = 42
remaining = 0
```

`BlockingQueue` tự quản lý các điều kiện cần thiết cho `put/take` theo contract của nó. **Không cần** người dùng gọi `wait/notifyAll` thủ công hay tự chọn monitor.

**Khác biệt mục tiêu:** `BoundedBufferDemo` ở trên dùng để học intrinsic monitor; ví dụ `BlockingQueue` là lựa chọn ưu tiên thường gặp cho hệ thống sản xuất.

## 42. `Condition.await/signal` không phải `Object.wait/notify`

`java.util.concurrent.locks.Condition` đi với một `Lock` như `ReentrantLock`.

Ví dụ dạng minh họa:

```java
ReentrantLock lock = new ReentrantLock();
Condition condition = lock.newCondition();

lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
```

- `condition.await()` nhả lock tương ứng theo contract `Condition` trong lúc chờ, rồi reacquire trước khi trả.
- `condition.signal()` gần với ý nghĩa đánh thức một waiter của condition queue.
- `condition.signalAll()` gần với ý nghĩa đánh thức tất cả waiters của condition.
- **Không được thay `Object.wait()` và `Condition.await()` cho nhau** tùy tiện; mỗi cơ chế đòi hỏi sở hữu loại lock/condition thích hợp.

**Ưu điểm khi dùng `Condition`:** một `ReentrantLock` có thể có hai condition queues riêng như `notEmpty` và `notFull`, giúp tín hiệu có mục tiêu hơn so với chỉ một wait set trên Object monitor.

### Hợp đồng tương tự

Dù dùng `Condition.await`, pattern:

```java
while (!predicate) {
    condition.await();
}
```

vẫn quan trọng vì spurious wakeups và cạnh tranh state.

## 43. Ví dụ chạy được: hai conditions riêng

Lưu **`ConditionAlternativeDemo.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

final class SimpleGate {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition openedCondition = lock.newCondition();
    private boolean opened;

    void open() {
        lock.lock();
        try {
            opened = true;
            openedCondition.signalAll();
        } finally {
            lock.unlock();
        }
    }

    void awaitOpen() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (!opened) {
                openedCondition.await();
            }
        } finally {
            lock.unlock();
        }
    }
}

public class ConditionAlternativeDemo {
    public static void main(String[] args)
            throws InterruptedException {

        SimpleGate gate = new SimpleGate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        gate.open();
        worker.join();

        System.out.println("gate is open");
    }
}
```

```bash
javac -encoding UTF-8 ConditionAlternativeDemo.java
java ConditionAlternativeDemo
```

Stdout:

```text
gate is open
```

Chương trình vẫn đúng nếu `gate.open()` xảy ra **trước khi worker thực sự vào `awaitOpen()`**, bởi `opened` là state lưu điều kiện. Nếu worker đã chờ, signalAll cho phép thức dậy và kiểm tra lại. Điều này cho thấy **predicate protocol** quan trọng không kém lựa chọn primitive.

## 44. Các anti-pattern quan trọng

### 44.1. Gọi `wait` ngoài monitor

```java
Object lock = new Object();
// lock.wait(); // Sai runtime: không giữ monitor lock.
```

**Sửa:** đưa vào `synchronized(lock)` và thiết kế predicate.

### 44.2. Đồng bộ monitor A nhưng gọi `notify` trên B

```java
synchronized (a) {
    b.notifyAll(); // IllegalMonitorStateException nếu không giữ b.
}
```

**Sửa:** mọi waiter và signaller phải dùng **đúng object khóa** bảo vệ state.

### 44.3. `if` thay vì `while`

```java
if (!ready) {
    lock.wait();
}
```

**Sửa:** `while (!ready)` để chống spurious wakeups/cạnh tranh.

### 44.4. Coi `notify` là stored event

```java
lock.notifyAll();
// Future waiter không tự nhận “quyền đã notify” trước đó.
```

**Sửa:** lưu trạng thái `ready/result/queue`.

### 44.5. Sleep dưới monitor

```java
synchronized (lock) {
    Thread.sleep(1000);
}
```

Không nhả `lock`. Nếu chỉ muốn ngủ thì hãy cân nhắc ngủ **ngoài critical section**; nếu chờ predicate, dùng wait/condition/higher-level API.

### 44.6. Khóa trên public hoặc interned object

```java
synchronized ("READY") {
    // Khóa có thể dùng chung ngoài ý muốn.
}
```

**Sửa:** private final monitor object.

### 44.7. Quên dừng waiter khi shutdown

Một waiter chỉ có:

```java
while (queue.isEmpty()) {
    lock.wait();
}
```

có thể chờ mãi nếu service đã stop và không bao giờ có item mới.

**Sửa:** state `closed` và condition:

```java
while (queue.isEmpty() && !closed) {
    lock.wait();
}
```

kèm `notifyAll` khi close. Sau vòng lặp, quyết định rõ trả end-of-stream, ném exception hoặc drain remaining items tùy contract.

### 44.8. Bắt `InterruptedException` rồi bỏ qua

Nuốt interrupt làm cancellation khó hơn. Truyền tiếp hoặc khôi phục status rồi thoát/cleanup phù hợp.

### 44.9. Lồng locks sai thứ tự

Thread A giữ M1 rồi chờ M2; thread B giữ M2 rồi chờ M1 → deadlock. `wait` chỉ nhả monitor receiver, không tự xử lý mọi cycle.

### 44.10. Kiểm tra condition ngoài lock

`if (!ready) synchronized(lock){lock.wait();}` dễ có lost-notification race. Predicate phải được kiểm tra và wait nguyên tử dưới cùng monitor.

## 45. Bài toán phân tích: khóa nào phải dùng?

Cho đoạn:

```java
final Object a = new Object();
final Object b = new Object();
boolean ready = false;
```

Thread 1:

```java
synchronized (a) {
    while (!ready) {
        a.wait();
    }
}
```

Thread 2:

```java
synchronized (b) {
    ready = true;
    b.notifyAll();
}
```

**Sai ở đâu?**

- Thread 1 wait trên wait set của **a**.
- Thread 2 notifyAll trên wait set của **b**.
- Notify của b **không** đánh thức waiter của a.
- `ready` được đọc/ghi dưới hai monitors khác nhau nên còn có vấn đề data-race/visibility.
- Có thể bị treo dù thread 2 đã set `ready = true`.

**Sửa một cách đơn giản:** dùng **cùng một monitor `a` hoặc một private final lock** cho cả hai phía; đọc/ghi `ready` dưới monitor đó và notify đúng object ấy.

## 46. Bài tập 1 — Phương thức thuộc class nào?

**Hỏi:** `wait()`, `notify()`, `notifyAll()` được khai báo bởi `Thread` hay `Object`?

**Đáp án:** Chúng thuộc **`java.lang.Object`**. `Thread.sleep` thuộc `Thread` và có contract khác.

## 47. Bài tập 2 — Cần khóa gì trước `lock.wait()`?

```java
Object lock = new Object();

synchronized (lock) {
    lock.wait();
}
```

**Đáp án:** Thread phải giữ **monitor của chính `lock`**. Đoạn code thỏa yêu cầu sở hữu monitor, nhưng nếu không ai notify/interrupt và không dùng timeout, nó có thể chờ vô hạn. Ví dụ chỉ minh họa điều kiện gọi hợp lệ, không phải một chương trình đầy đủ nên dùng trong production.

## 48. Bài tập 3 — `wait` có nhả `lock` không?

```java
synchronized (lock) {
    lock.wait();
}
```

**Đáp án:** Có, **monitor của receiver `lock`** được nhả trong thời gian chờ, rồi được lấy lại trước khi `wait` return/throw theo quy tắc. Nó không nhả các monitor khác mà thread vẫn giữ.

## 49. Bài tập 4 — `notify` đánh thức thread nào?

Có ba waiters A, B, C ở wait set của lock.

**Đáp án:** Một thread **bất kỳ** trong số đang wait; không có bảo đảm A là người đến trước hoặc thread nào được scheduler chạy trước. `notify` không tự làm predicate true.

## 50. Bài tập 5 — `notifyAll` chạy cả ba threads đồng thời?

**Đáp án:** Không. Nó thông báo cho tất cả waiters trên **cùng object**, nhưng các threads phải **lần lượt lấy monitor** để thoát khỏi wait và tiếp tục vùng synchronized.

## 51. Bài tập 6 — Sai monitor

```java
Object a = new Object();
Object b = new Object();

synchronized (a) {
    b.notifyAll();
}
```

**Đáp án:** `IllegalMonitorStateException` vì thread giữ monitor a, không giữ monitor b.

## 52. Bài tập 7 — Vì sao dùng `while`?

```java
synchronized (lock) {
    while (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst();
}
```

**Đáp án:** Để kiểm tra predicate sau spurious wakeup và sau khi thread khác có thể tiêu thụ item trước khi waiter giành lại monitor. `if` không đủ bảo đảm.

## 53. Bài tập 8 — `sleep` có thay `wait` được không?

**Đáp án:** Không trong condition protocol monitor. `sleep` không nhả monitor đang giữ; thread khác có thể bị chặn không đổi được shared state. `wait` nhả monitor receiver và phối hợp với notification/predicate.

## 54. Bài tập 9 — `wait(0)` là trả về ngay?

**Đáp án:** Không. Theo API, `wait(0)` là **wait không timeout định trước**. Nếu muốn chờ tối đa một khoảng thời gian, dùng overload timed dương và quản lý deadline/predicate đúng.

## 55. Bài tập 10 — Tín hiệu trước waiter

Producer set `ready = true` và notifyAll khi chưa có waiter. Sau đó consumer bắt đầu.

**Đáp án:** Notification không được tích trữ. Consumer vẫn tiến triển an toàn nếu kiểm tra `while (!ready)` dưới đúng monitor; vì `ready` đã true nên không cần wait.

## 56. Bài tập 11 — Static synchronized khóa object nào?

```java
class Cache {
    static synchronized void refresh() {
    }
}
```

**Đáp án:** Sử dụng **monitor của `Cache.class`**, không phải monitor của từng instance `new Cache()`.

## 57. Bài tập 12 — Instance synchronized khóa object nào?

```java
class Counter {
    synchronized void increment() {
    }
}
```

**Đáp án:** Monitor của **receiver `this`**. Hai `Counter` instances khác nhau có locks khác nhau.

## 58. Bài tập 13 — Giữ hai locks rồi wait một cái

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

**Đáp án:** Thread **nhả inner** trong thời gian chờ, nhưng vẫn giữ `outer`. Nếu signaller cần `outer`, có thể tạo deadlock.

## 59. Bài tập 14 — Interrupted waiter

Một thread bị interrupt khi `lock.wait()`.

**Đáp án:** `wait` có thể ném `InterruptedException`, đồng thời thread thực hiện reacquire monitor theo contract trước khi hoàn tất call bằng exception. Caller cần chính sách truyền tiếp, khôi phục interrupt status hoặc cleanup/thoát phù hợp; không nên nuốt exception.

## 60. Bài tập 15 — Bounded buffer dùng notify hay notifyAll?

Có cả producers chờ `notFull` và consumers chờ `notEmpty` trên một monitor.

**Đáp án:** `notifyAll` thường là lựa chọn đúng, dễ chứng minh liveness trong mô hình một wait set đa điều kiện; mọi waiter tự kiểm tra lại predicate trong `while`. Với hai `Condition` queues riêng, có thể dùng signal có mục tiêu theo contract của `ReentrantLock`.

## 61. Bài tập 16 — Biến `volatile` có thay toàn bộ synchronized không?

```java
volatile boolean ready;
```

**Đáp án:** Không. `volatile` có semantics visibility/order riêng nhưng không tạo atomic check-then-wait protocol và không cấp quyền sở hữu monitor để gọi `wait/notify`. Muốn dùng Object.wait vẫn cần synchronized đúng receiver và kiểm tra predicate dưới lock.

## 62. Bài tập 17 — `notifyAll` gọi sau khi đã thoát synchronized?

```java
synchronized (lock) {
    ready = true;
}
lock.notifyAll();
```

**Đáp án:** `IllegalMonitorStateException` nếu thread hiện tại không đang giữ monitor của lock tại lời gọi `notifyAll`. Hãy gọi notifyAll **bên trong** `synchronized(lock)` thích hợp.

## 63. Bài tập 18 — Hai references tới cùng lock object

```java
Object a = new Object();
Object b = a;

synchronized (a) {
    b.notifyAll();
}
```

**Đáp án:** Hợp lệ về **monitor ownership**, vì `a == b` tham chiếu cùng object. Không đánh thức ai nếu wait set của object rỗng. Điều quan trọng là **object identity**, không phải tên biến.

## 64. Bài tập 19 — Chọn thư viện chuẩn

Bài toán: queue tối đa 100 items, nhiều producers và consumers.

**Đáp án:** Trong ứng dụng thực tế, cân nhắc `ArrayBlockingQueue<>(100)` hoặc một `BlockingQueue` phù hợp hơn tự viết `wait/notifyAll`. Hiểu intrinsic monitor giúp kiểm tra mã cũ, còn thư viện cấp cao giảm nguy cơ lỗi.

## 65. Bài tập 20 — Nên in stdout theo thứ tự thread nào?

Hai threads được `notifyAll` và tự in `A`/`B` ngay khi lấy lại lock.

**Đáp án:** Không thể dự đoán một thứ tự cố định chỉ từ notification. Muốn stdout deterministic, thu kết quả rồi `join` và sort, hoặc dùng thêm một protocol đồng bộ thứ tự có chủ đích.

## 66. Checklist khi đọc một đoạn code `wait/notify`

1. **Xác định object receiver thực tế** của `wait/notify/notifyAll`.
2. **Xác định object monitor đang được synchronized**: có đúng cùng identity không?
3. Nếu dùng instance synchronized method, nhớ monitor là **`this`**.
4. Nếu dùng static synchronized method, nhớ monitor là **`ClassName.class`**.
5. Trạng thái được bảo vệ là **biến nào/queue nào**?
6. Mọi đọc/ghi của predicate có nhất quán dưới **cùng lock** không?
7. Waiter có kiểm tra predicate trong **`while`** không?
8. Có thể có spurious wakeup, cạnh tranh dữ liệu hoặc signal cho điều kiện khác không?
9. Signaller có **thay trạng thái trước khi notify** không?
10. Nếu signal xảy ra trước waiter, predicate có giúp waiter không bị treo không?
11. Có lệnh `notify` nào gọi không giữ monitor receiver gây exception không?
12. Có dùng `wait(0)` nhưng tưởng là “không chờ” không?
13. Có xử lý timeout bằng **deadline thật** khi cần không?
14. Có bắt `InterruptedException` và xử lý cancellation hợp lý không?
15. `wait` có đang được gọi khi thread giữ thêm monitor khác dẫn tới deadlock không?
16. Có `sleep` hoặc I/O dài **bên trong synchronized** giữ monitor quá lâu không?
17. Có lồng locks ngược thứ tự giữa các threads không?
18. Có dùng `String`/boxed number/public object làm lock vô tình chia sẻ không?
19. Lock field có **private final** nếu nó phải ổn định, không lộ ra ngoài không?
20. Nếu nhiều wait conditions trên một lock, dùng `notifyAll` hoặc tách `Condition` queues đã hợp lý chưa?
21. Các waiters có cần tín hiệu **shutdown/close** để không chờ vĩnh viễn không?
22. Có đang dựa vào thứ tự scheduler hoặc `Thread.sleep` để thử nghiệm không?
23. Có nhầm `Thread.State.BLOCKED` và `WAITING` không?
24. Có hiểu rằng `notifyAll` **không trao monitor ngay** cho waiters không?
25. Nếu mục tiêu là queue, latch hoặc semaphore, liệu API `java.util.concurrent` phù hợp hơn không?

## 67. Ghi nhớ nhanh

- **`wait()`, `notify()`, `notifyAll()` là các instance methods `final` của `java.lang.Object`.**
- Mỗi object có một **intrinsic monitor**; tất cả thao tác wait/notify phải dùng **cùng object monitor** bảo vệ condition state.
- **`synchronized(lock)`** giữ monitor của object `lock`; **instance synchronized method** giữ `this`; **static synchronized method** giữ `ClassName.class`.
- **`lock.wait()` nhả monitor `lock` trong khi chờ**, rồi lấy lại trước khi tiếp tục hoặc hoàn tất bằng interrupt exception theo quy tắc; nó **không** nhả mọi monitor khác.
- **`lock.notify()`** báo **một waiter tùy ý**; **`lock.notifyAll()`** báo tất cả waiters của **cùng lock**, nhưng không cấp monitor ngay lập tức.
- Luôn dùng **`while (!predicate) lock.wait();`**, không dùng `if` để bảo vệ condition wait.
- **Trạng thái** như `ready`/queue mới là nguồn sự thật; notification **không được tích trữ** cho thread đến muộn.
- `Thread.sleep` **không nhả monitor**, nên không thay thế `wait` trong condition synchronization.
- Timeout, interruption, spurious wakeup và shutdown đều cần **protocol xử lý rõ**.
- Với producer–consumer hoặc đồng bộ nhiều thread, ưu tiên **`BlockingQueue`, `CountDownLatch`, `Condition`** hoặc tiện ích cấp cao khi đáp ứng yêu cầu.

Khi cần giải thích “thread nào được đánh thức” và “vì sao không deadlock”, hãy bắt đầu bằng **identity của lock object**, **predicate được bảo vệ** và **thời điểm thread nhả/lấy lại monitor**. Ba yếu tố ấy quyết định tính đúng của chương trình, không phải tên thread hay số mili giây sleep.
