# `wait()`, `notify()`, `notifyAll()` hoạt động trong monitor như thế nào?

Trong Java, `Object.wait()`, `Object.notify()` và `Object.notifyAll()` là các primitive phối hợp luồng ở cấp thấp, gắn trực tiếp với **intrinsic monitor** của mỗi object. Chúng cho phép một thread **tạm nhả monitor và chờ điều kiện**, còn thread khác **thay đổi trạng thái được bảo vệ rồi gửi tín hiệu** để các thread đang chờ có cơ hội kiểm tra lại điều kiện đó.

Ba phương thức này dễ bị dùng sai vì có ba khái niệm tách biệt:

1. **Có quyền vào critical section:** thread đã lấy được monitor của object.
2. **Điều kiện nghiệp vụ đã đúng:** ví dụ queue có phần tử, cổng đã mở, buffer còn chỗ.
3. **Thread được đánh thức:** có tín hiệu, interruption, timeout hoặc spurious wakeup; điều này **không tự chứng minh** điều kiện nghiệp vụ đã đúng.

Một thiết kế đúng phải bảo vệ **predicate (điều kiện trạng thái)** dưới **cùng monitor**, gọi `wait()` trong **vòng `while`** kiểm tra predicate, và cập nhật trạng thái trước khi gọi `notify/notifyAll`. Chỉ gọi `notify()` không phải là "gửi một permit" mà thread chưa bắt đầu chờ có thể giữ lại để dùng sau.

Bài này thuộc phần **Phối hợp luồng** của **Java concurrency nói chung**, với JDK 17+ và các API cốt lõi của `java.lang` / `java.util.concurrent`. Không bàn tới cơ chế xử lý luồng riêng của Spring Framework.

## 1. Mỗi đối tượng Java có một intrinsic monitor

Về mặt ngôn ngữ, mỗi object có monitor phục vụ các thao tác `synchronized`, `wait` và `notify`. Khi thread chạy:

```java
synchronized (lock) {
    // critical section
}
```

nó phải sở hữu **monitor của chính object `lock`**. Thread khác cũng muốn `synchronized (lock)` phải chờ cho đến khi monitor được nhả.

Hai dạng method cũng dùng monitor:

| Cú pháp | Monitor liên quan |
| --- | --- |
| `synchronized (lock) { ... }` | Object được tham chiếu bởi `lock` |
| `synchronized void method() { ... }` | `this` |
| `static synchronized void method() { ... }` | Object `Class` của lớp tương ứng |

Monitor giữ thông tin sở hữu và mức vào lại (intrinsic monitor **reentrant**). Nếu một thread đang sở hữu monitor `M`, chính thread đó có thể gọi lại method `synchronized` dùng `M` mà không bị self-deadlock chỉ vì lock này. Nhưng các thread khác vẫn không thể sở hữu `M` đồng thời.

Tính đồng bộ ở đây có thêm ý nghĩa của **Java Memory Model**: unlock monitor happens-before lần lock tiếp theo trên cùng monitor. Vì thế, những ghi được thực hiện theo cùng giao thức khóa có thể được thread khác quan sát phù hợp khi nó lấy monitor.

## 2. Ba phương thức thuộc `Object`, không phải `Thread`

Các method này được định nghĩa trên `java.lang.Object`; object dùng để chờ/báo có thể là một monitor riêng do class tạo:

```java
private final Object lock = new Object();
```

Đây là khai báo field minh họa trong một class; không phải chương trình độc lập. Những chữ ký quan trọng:

```java
public final void wait() throws InterruptedException;
public final void wait(long timeoutMillis)
        throws InterruptedException;
public final void wait(long timeoutMillis, int nanos)
        throws InterruptedException;

public final void notify();
public final void notifyAll();
```

Các chữ ký trên được trình bày theo cú pháp khai báo API để học, không phải mã đặt vào một class mới.

- **`wait()`:** thread đang sở hữu monitor của object gọi phương thức sẽ **nhả monitor đó** và chờ cho đến khi đủ điều kiện để tiếp tục (được notify, interrupt hoặc thức dậy khác theo hợp đồng), rồi **phải lấy lại monitor** trước khi method trả về hoặc ném `InterruptedException`.
- **`notify()`:** chọn **một** thread tùy ý trong nhóm thread đang `wait` trên **cùng object**, nếu có. Không cam kết công bằng, FIFO, chọn theo ưu tiên hay chính xác thread có predicate phù hợp.
- **`notifyAll()`:** đánh thức **tất cả** thread đang `wait` trên **cùng object**. Chúng vẫn phải tranh monitor để vào lại; không chạy phần `synchronized` cùng một lúc.

**Điều kiện bắt buộc:** caller của cả ba method phải đang sở hữu monitor của **object dùng để gọi method**. Nếu không, sẽ gặp `IllegalMonitorStateException`. Điều này áp dụng cho cả `wait`, `notify` và `notifyAll`.

## 3. Tại sao `wait()` bắt buộc đi cùng `synchronized`?

Vì bước **kiểm tra điều kiện và bắt đầu chờ** phải diễn ra như một giao thức atomic đối với những thread cập nhật trạng thái.

Xét:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // condition đã đúng tại thời điểm thread đang giữ lock.
}
```

Đây là mẫu minh họa với biến `lock` và `condition` thuộc cùng giao thức bảo vệ; đoạn thật phải khai báo `throws InterruptedException` hoặc xử lý exception.

Trình tự:

1. Thread A lấy monitor `lock`.
2. A kiểm tra `condition` **khi đang sở hữu monitor**.
3. Nếu false, A gọi `lock.wait()`. Việc đưa thread vào trạng thái chờ và nhả monitor được phối hợp theo ngữ nghĩa của monitor, tránh khoảng "đã kiểm tra false nhưng signal hợp lệ bị lọt giữa" khi writer cũng dùng cùng monitor.
4. Thread B lấy monitor `lock` khi A đã nhả, đổi `condition = true`, rồi gọi `lock.notifyAll()`.
5. B rời `synchronized`, nhả monitor.
6. A có cơ hội lấy lại monitor `lock`, trở về từ `wait`, **kiểm tra lại predicate**, sau đó mới sử dụng trạng thái.

**Không đặt điều kiện ở một field khác được sửa mà bỏ qua cùng monitor** nếu giao thức phụ thuộc vào việc kiểm tra và chờ nguyên tử. Không đặt `wait` bên ngoài lock rồi hy vọng thêm `volatile` ở một chỗ khác sẽ sửa toàn bộ lost-signal race.

## 4. Chờ, thông báo và lấy lại monitor: ba thời điểm riêng

Sơ đồ với monitor `M`:

```text
Thread A (consumer)                  Thread B (producer)
-------------------                  -------------------
lock(M)
while (queue.isEmpty()):
    wait(M)
    |  A vào wait set của M
    |  A nhả monitor M
    v
  WAITING                             lock(M)
                                      queue.add(item)
                                      notifyAll(M)
                                      | đánh thức waiter ở M
                                      | nhưng B vẫn giữ M
                                      unlock(M)
A phải lấy lại monitor M <-----------+
  có thể tạm BLOCKED khi chờ lock
kiểm tra lại queue.isEmpty()
lấy item
unlock(M)
```

**`notifyAll` không nhả monitor ngay khi được gọi.** Thread B vẫn sở hữu monitor đến khi nó rời vùng `synchronized` hoặc thực hiện một lời gọi `wait` hợp lệ trên cùng monitor. A chỉ có thể tiếp tục phần code sau `wait` khi đã được phép thức và lấy lại monitor.

Từ góc nhìn `Thread.State`, một thread trong `Object.wait()` không timeout thường ở `WAITING`; khi đã được notify nhưng còn chờ vào lại monitor, nó có thể ở `BLOCKED`. `Thread.getState()` chỉ là ảnh chụp tạm thời, không nên dùng nó để điều phối đúng thời điểm gọi `notify`.

## 5. Mẫu chuẩn: guarded block với `while`

Mẫu này là nền tảng cần nhớ:

```java
final class Gate {
    private boolean open;

    synchronized void awaitOpen() throws InterruptedException {
        while (!open) {
            wait();
        }
    }

    synchronized void open() {
        open = true;
        notifyAll();
    }
}
```

`wait()` và `notifyAll()` không có receiver tường minh nên receiver là `this`. Vì phương thức được `synchronized` theo instance, caller đang sở hữu monitor `this` khi gọi cả hai.

Điểm mấu chốt:

- `open` là **predicate trạng thái**, không phải một tín hiệu trôi qua.
- Nếu `open()` được gọi **trước** `awaitOpen()`, waiter vẫn thoát ngay nhờ kiểm tra `open == true`; không cần "ghi nhớ" một notification.
- Nếu waiter đang chờ, `open()` chuyển trạng thái rồi notify, cho waiter cơ hội kiểm tra lại.
- `while` xử lý spurious wakeup, các thread cạnh tranh và tình huống predicate lại thành false (nếu thiết kế cho phép đóng lại).
- Mọi đường đọc/ghi `open` đều tuân theo **cùng monitor**.

Mẫu này là class minh họa chưa có `main`. Ví dụ hoàn chỉnh ngay sau đây có thể biên dịch và chạy độc lập.

## 6. Ví dụ Java 17+: cổng mở bằng `notifyAll()`

Lưu thành `MonitorGateDemo.java`:

```java
public class MonitorGateDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait();
            }
        }

        synchronized void open() {
            open = true;
            notifyAll();
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
                System.out.println("Worker passed gate");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "gate-worker");

        worker.start();
        gate.open();    // Có thể diễn ra trước hoặc sau worker.wait().
        worker.join();

        System.out.println("Gate open: " + gate.isOpen());
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac MonitorGateDemo.java
java MonitorGateDemo
```

Stdout trong lần chạy bình thường:

```text
Worker passed gate
Gate open: true
```

Đây là chương trình **không dựa vào `Thread.sleep()` để đoán lúc worker đã chờ**. Nếu main gọi `open()` trước khi worker vào `awaitOpen()`, predicate đã true và worker đi tiếp; nếu main mở sau lúc worker chờ, `notifyAll` đánh thức worker. Cả hai cách đều hợp lệ và cho cùng kết quả.

`join()` đặt sau `open()` giúp main đợi worker kết thúc rồi mới in dòng cuối. Không nên thay nó bằng polling `worker.getState()` hoặc ngủ một khoảng cố định để đoán tiến độ.

Một hạn chế có chủ ý: chương trình không ép worker **nhất định phải vào WAITING**; nó kiểm chứng chính xác protocol "đi tiếp sau khi cổng đã mở", bất kể lịch chạy.

## 7. `notify()` và `notifyAll()` khác nhau ra sao?

Giả sử ba waiter cùng `wait()` trên object `lock`:

```text
wait set của lock: {T1, T2, T3}

lock.notify()
    -> đánh thức một waiter không được chỉ định (ví dụ T2)
    -> T1 và T3 vẫn chờ

lock.notifyAll()
    -> đánh thức mọi waiter trong wait set tại thời điểm đó
    -> T1, T2, T3 phải tranh monitor trước khi kiểm tra lại condition
```

**Không có FIFO guarantee** giữa các waiter chỉ nhờ `notify` hoặc `notifyAll`. Thứ tự tiếp tục phụ thuộc monitor acquisition, scheduling và những yếu tố triển khai khác.

| Tình huống | `notify()` | `notifyAll()` |
| --- | --- | --- |
| Một waiter duy nhất trên monitor | Có thể đủ khi predicate đúng | Cũng đúng, nhưng tổng quát hơn |
| Nhiều waiter cùng điều kiện, một lần cập nhật chỉ cho phép một consumer tiến | Có thể tối ưu nếu có chứng minh chặt chẽ | An toàn hơn khi còn bất định về waiter được chọn |
| Nhiều loại predicate dùng chung monitor | Có nguy cơ đánh thức waiter không thể tiến | Thường dễ chứng minh đúng hơn |
| Chuyển sang trạng thái terminal/close cần mọi waiter biết | Có thể bỏ sót nhiều waiter | Thường phù hợp |
| Có nhiều waiter và notification quá dày | Ít đánh thức hơn | Có thể gây nhiều wakeups và tranh monitor |

**`notifyAll()` không phải "luôn tốt nhất về hiệu năng"**, nhưng thường **dễ đúng hơn** khi condition sharing phức tạp. Nó có thể gây *thundering herd*: nhiều thread cùng thức, cuối cùng chỉ một hoặc vài thread thật sự tiến được, những thread còn lại lại `wait`. Khi hiệu năng quan trọng, cân nhắc `Condition` tách nhóm waiter hoặc các tiện ích ở `java.util.concurrent`.

## 8. Vì sao `notify()` có thể đánh thức sai loại waiter?

Một bounded buffer có hai predicate khác nhau:

- Producer chờ **buffer chưa đầy**.
- Consumer chờ **buffer không rỗng**.

Nếu tất cả chờ trên **cùng monitor**, trong wait set có thể đồng thời chứa producer và consumer. Một lần `notify()` không biết ai đang chờ điều kiện nào. Nó có thể đánh thức một producer trong khi buffer vẫn đầy, hoặc một consumer trong khi buffer vẫn rỗng.

Sự đánh thức đó không tạo tiến độ; thread thức dậy, lấy lại monitor, thấy predicate sai và chờ lại. Nếu thread có khả năng thực sự tiến không được đánh thức và không có thêm tín hiệu, hệ thống có thể mắc kẹt.

**`notifyAll()` cho mọi nhóm waiter cơ hội kiểm tra predicate của mình**, nhưng chúng vẫn phải dùng `while` và tranh monitor. Đặc biệt với nhiều condition trên cùng monitor, đó thường là lựa chọn dễ chứng minh đúng cho ví dụ học tập.

Nếu cần chọn nhóm chính xác hơn, `ReentrantLock` và hai `Condition` (ví dụ `notFull`/`notEmpty`) hoặc `ArrayBlockingQueue` có cơ chế phù hợp hơn.

## 9. Lỗi lost notification: notification không tích lũy như permit

Một lỗi phổ biến:

```java
// Thread A:
synchronized (lock) {
    lock.notify();
}

// Thread B (bắt đầu chờ muộn):
synchronized (lock) {
    lock.wait();
}
```

Hai đoạn là minh họa độc lập; không phải class runnable. Nếu A notify khi **chưa có waiter nào**, notification không được cất giữ để đánh thức B sau này. B có thể chờ mãi nếu không có notification khác.

Cách sửa **không phải chỉ đảo thứ tự start/sleep** giữa hai thread. Phải có state thể hiện sự kiện, ví dụ:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

và:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Đây là giao thức đúng nếu `ready` được bảo vệ bởi `lock` ở mọi đường liên quan. Khi signal đến sớm, `ready` vẫn true để reader thấy. Khi signal đến muộn, reader đợi và được đánh thức đúng cách.

**State là sự thật, notification chỉ là lời nhắc kiểm tra lại state.** Đây là cách nghĩ đáng tin nhất về monitor condition.

## 10. Spurious wakeup: tại sao phải dùng `while` thay cho `if`?

`Object.wait()` được phép trở về khi không có notification rõ ràng mà ứng dụng kỳ vọng (spurious wakeup). Ngoài ra, một waiter có thể được notify vì **predicate khác** trên cùng monitor, hoặc một thread khác lấy tài nguyên trước waiter khi nó lấy lại monitor.

Sai:

```java
synchronized (lock) {
    if (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst(); // Có thể không có phần tử.
}
```

Đây là anti-pattern minh họa. Ngay cả nếu `wait()` trở lại, queue **có thể vẫn rỗng**.

Đúng:

```java
synchronized (lock) {
    while (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst();
}
```

Ở đây giả định `queue` thuộc trạng thái được bảo vệ bằng `lock`. `while` bắt buộc waiter kiểm tra lại predicate sau mọi lần thức. Điều kiện được kiểm tra **trong monitor**, nên một thread khác không thể đồng thời thay đổi queue qua cùng monitor đúng lúc kiểm tra và lấy phần tử.

Với API public, ghi rõ `wait` có thể bị interruption và method có thể ném `InterruptedException`; đừng nuốt exception rồi tiếp tục như thể resource đã sẵn sàng.

## 11. Ví dụ Java 17+: producer–consumer dùng `wait/notifyAll`

Ví dụ dưới tạo một bounded queue capacity 2 với hai operation `put` và `take`. Producer chờ **chưa đầy**, consumer chờ **không rỗng**. Đây là cách viết để học cơ chế monitor; trong ứng dụng thực, `ArrayBlockingQueue` thường phù hợp hơn tự xây queue.

Lưu thành `MonitorQueueDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class MonitorQueueDemo {
    static final class BoundedQueue {
        private final Deque<Integer> items = new ArrayDeque<>();
        private final int capacity;

        BoundedQueue(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        synchronized void put(int value) throws InterruptedException {
            while (items.size() == capacity) {
                wait();
            }
            items.addLast(value);
            notifyAll();
        }

        synchronized int take() throws InterruptedException {
            while (items.isEmpty()) {
                wait();
            }
            int result = items.removeFirst();
            notifyAll();
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BoundedQueue queue = new BoundedQueue(2);
        int[] result = new int[1];

        Thread producer = new Thread(() -> {
            try {
                for (int value = 1; value <= 5; value++) {
                    queue.put(value);
                }
                queue.put(0); // Sentinel: dữ liệu thực chỉ là số 1..5.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                int sum = 0;
                while (true) {
                    int value = queue.take();
                    if (value == 0) {
                        break;
                    }
                    sum += value;
                }
                result[0] = sum;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Sum: " + result[0]);
    }
}
```

Chạy:

```bash
javac MonitorQueueDemo.java
java MonitorQueueDemo
```

Stdout chính xác **trên đường chạy bình thường, không có interruption bên ngoài**:

```text
Sum: 15
```

Giải thích:

1. `items` là `ArrayDeque` thường, nhưng mọi lần thêm/lấy và kiểm tra `size/isEmpty` đều được bảo vệ bằng **monitor của `BoundedQueue`**. Không có writer nào được sửa trực tiếp `items` ngoài lớp.
2. Khi queue đầy, producer gọi `wait()` và nhả monitor, nhờ đó consumer vẫn có thể lấy một phần tử.
3. Khi queue rỗng, consumer gọi `wait()` và nhả monitor, nhờ đó producer vẫn có thể thêm phần tử.
4. `notifyAll()` sau mỗi thay đổi cấu trúc cho các waiter cơ hội kiểm tra lại predicate tương ứng.
5. Capacity 2 giới hạn số phần tử đang đợi. Sentinel `0` hợp lệ vì dữ liệu thường chỉ là 1 đến 5 và có đúng một consumer.
6. `result[0]` chỉ được consumer ghi; main đọc sau `consumer.join()`, nên quan hệ happens-before của join công bố kết quả mà không cần biến array thành atomic.
7. Không có cam kết thời điểm mỗi thread chạy; chương trình đúng với mọi lịch chạy bình thường đáp ứng giao thức.

**Giới hạn của demo:** nếu producer bị ngắt trước khi gửi sentinel hoặc consumer lỗi giữa chừng, bên còn lại có thể chờ vô hạn. Ứng dụng thực cần **close/failure protocol**, hủy và đường đánh thức waiter, hoặc dùng cấu trúc concurrent có lifecycle rõ. Đừng biến ví dụ nhỏ thành queue production mà không xử lý những nhánh đó.

## 12. Nhiều waiter và nhiều predicate: lý do dùng `notifyAll`

Một monitor có thể bảo vệ hai điều kiện khác nhau. Khi trạng thái cho phép **cả hai nhóm** tiến, `notifyAll` hợp lý vì nó không phải đoán waiter nào cần thức.

Lưu thành `TwoConditionsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoConditionsDemo {
    static final class Conditions {
        private boolean firstReady;
        private boolean secondReady;

        synchronized void awaitFirst(CountDownLatch ready)
                throws InterruptedException {
            ready.countDown();
            while (!firstReady) {
                wait();
            }
        }

        synchronized void awaitSecond(CountDownLatch ready)
                throws InterruptedException {
            ready.countDown();
            while (!secondReady) {
                wait();
            }
        }

        synchronized void releaseBoth() {
            firstReady = true;
            secondReady = true;
            notifyAll();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Conditions conditions = new Conditions();
        CountDownLatch entered = new CountDownLatch(2);
        AtomicInteger completed = new AtomicInteger();

        Thread first = new Thread(() -> {
            try {
                conditions.awaitFirst(entered);
                completed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread second = new Thread(() -> {
            try {
                conditions.awaitSecond(entered);
                completed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        first.start();
        second.start();
        entered.await();
        conditions.releaseBoth();
        first.join();
        second.join();

        System.out.println("Completed: " + completed.get());
    }
}
```

```bash
javac TwoConditionsDemo.java
java TwoConditionsDemo
```

Stdout chính xác trên đường chạy bình thường:

```text
Completed: 2
```

`entered` là latch riêng chỉ để main biết cả hai thread đã vào method chờ. Mỗi waiter `countDown()` trong monitor ngay trước vòng `wait`. Do main cũng cần monitor đó để gọi `releaseBoth()`, nó không thể đổi predicate giữa bước waiter đang sở hữu monitor và bước waiter nhả monitor trong `wait()`; đó là giao thức quan trọng của ví dụ.

`notifyAll()` khiến cả hai waiter có cơ hội lấy lại monitor và nhìn thấy predicate tương ứng đã true. Hai lời gọi `incrementAndGet` cập nhật cùng một atomic counter, main đọc sau `join`. Không cam kết waiter nào hoàn tất trước.

Đây là ví dụ **một lần mở điều kiện**. Đối với workload lặp lại, cần thêm quy tắc reset predicate, đóng và hủy; không nên tái sử dụng latch đã về 0 để đánh dấu một vòng mới.

## 13. InterruptedException: thread đang `wait` có thể bị ngắt

`Object.wait()` là một blocking operation **interruptible**. Nếu thread đang chờ bị `Thread.interrupt()`, nó có thể trở về bằng cách ném `InterruptedException` theo hợp đồng của API. Khi `InterruptedException` được ném do interruption, interrupt status bị xóa như một phần của hành vi ném exception; caller quyết định propagate, cleanup, hoặc khôi phục trạng thái khi không thể xử lý ngay.

Quan trọng: thread phải **lấy lại monitor của object** trước khi `wait()` trả về hoặc thoát bằng exception. Vì thế catch/finally bao quanh `wait` có thể thực thi khi thread lại đang sở hữu monitor.

Ví dụ độc lập, lưu thành `WaitInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class WaitInterruptDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();

        Thread waiter = new Thread(() -> {
            synchronized (monitor) {
                entered.countDown();
                try {
                    monitor.wait();
                } catch (InterruptedException e) {
                    caught.set(true);
                    Thread.currentThread().interrupt();
                }
            }
        }, "interruptible-waiter");

        waiter.start();
        entered.await();
        waiter.interrupt();
        waiter.join();

        System.out.println("Interrupted wait: " + caught.get());
    }
}
```

```bash
javac WaitInterruptDemo.java
java WaitInterruptDemo
```

Stdout chính xác:

```text
Interrupted wait: true
```

Ví dụ dùng latch để biết thread đã vào khối monitor trước khi main yêu cầu interrupt. Nếu interrupt đến **trước** lời gọi `wait()` thực tế, thread vẫn có interrupt status và `wait` sẽ phản hồi theo hợp đồng khi được gọi. Nếu interrupt đến **trong lúc đang chờ**, `wait` được đánh thức bởi interruption. Cả hai lịch chạy đều cho kết quả như trên.

Ở nhánh catch, `Thread.currentThread().interrupt()` khôi phục interrupt status để các lớp gọi bên ngoài có thể biết yêu cầu ngắt đã xảy ra. Trong API có `throws InterruptedException`, truyền exception lên caller thường rõ hơn việc bắt rồi nuốt lỗi.

**Không dùng `Thread.stop()`** để thay cho interruption hoặc xây logic hủy; cơ chế đó không phù hợp để bảo vệ invariant và đã bị deprecate vì không an toàn.

## 14. `wait(timeout)` và timed waiting

Java cung cấp:

- `wait()` hoặc `wait(0)`: chờ **không giới hạn thời gian** theo hợp đồng đợi của Object.
- `wait(timeoutMillis)` với timeout dương: yêu cầu chờ tối đa khoảng thời gian đó trước khi đủ điều kiện đánh thức do timeout; thời điểm lấy lại monitor có thể trễ hơn vì scheduling và lock contention.
- `wait(timeoutMillis, nanos)`: cho phép chỉ định thêm độ chính xác nanosecond trong phạm vi tham số hợp lệ.

**Timeout không đồng nghĩa predicate đã đúng.** Thread có thể trở về vì timeout, notification không liên quan, interruption hoặc spurious wakeup. Vì thế vẫn cần `while`.

Ví dụ dùng deadline thay vì mỗi lần thức lại chờ toàn bộ timeout ban đầu:

Lưu thành `TimedGateDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class TimedGateDemo {
    static final class Gate {
        private boolean open;

        synchronized boolean awaitOpen(long timeoutMillis)
                throws InterruptedException {
            if (timeoutMillis < 0) {
                throw new IllegalArgumentException("negative timeout");
            }

            long deadline = System.nanoTime()
                    + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
            long remaining;

            while (!open &&
                    (remaining = deadline - System.nanoTime()) > 0) {
                TimeUnit.NANOSECONDS.timedWait(this, remaining);
            }

            return open;
        }

        synchronized void open() {
            open = true;
            notifyAll();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        System.out.println("Opened: " + gate.awaitOpen(50));
        gate.open();
        System.out.println("Opened after signal: "
                + gate.awaitOpen(50));
    }
}
```

```bash
javac TimedGateDemo.java
java TimedGateDemo
```

Stdout chính xác trong lần chạy bình thường:

```text
Opened: false
Opened after signal: true
```

Giải thích: trong lần gọi đầu, không có thread nào mở `Gate` nên sau khi hết deadline predicate vẫn false. Lần sau `open()` đã được gọi nên `awaitOpen` trả true ngay, không cần `wait`.

`System.nanoTime()` phù hợp đo khoảng trôi qua vì nó là đồng hồ monotonic dành cho elapsed time, không phải giờ hệ thống. Đoạn demo sử dụng khoảng timeout ngắn và đơn giản; API thư viện production cần xem xét overflow của phép cộng deadline nếu cho phép timeout cực lớn, và quy tắc khi truyền 0. `TimeUnit.NANOSECONDS.timedWait` chuyển khoảng nanosecond thành lời gọi chờ có timeout thích hợp.

Nếu muốn trả về một kết quả thành công **chỉ khi predicate đã đạt**, không được dùng việc `wait` trả về như chứng cứ; method phải đọc predicate trong monitor trước khi trả true.

## 15. `wait()` khác `Thread.sleep()` như thế nào?

| Thuộc tính | `Object.wait()` | `Thread.sleep(...)` |
| --- | --- | --- |
| Receiver | Một object monitor | Static API trên `Thread` hiện tại |
| Phải giữ monitor trước khi gọi? | **Có**, monitor của receiver | Không |
| Trong lúc chờ có nhả monitor đang nói tới? | **Có**, nhả monitor của receiver | **Không**, không tự nhả monitor nào |
| Dùng để chờ predicate do thread khác đổi? | Có, qua guarded block | Không phù hợp làm tín hiệu |
| Thức do gì? | Notification, interruption, timeout, spurious wakeup theo hợp đồng | Hết khoảng ngủ hoặc interruption |
| Khi method trả về | Phải lấy lại monitor receiver | Không tự lấy monitor mới |
| Nguy cơ nếu đang giữ monitor khác | Các monitor khác vẫn có thể tiếp tục bị giữ | Vẫn giữ toàn bộ monitor đang sở hữu |

Nếu viết:

```java
synchronized (lock) {
    Thread.sleep(1_000);
}
```

thì thread **vẫn giữ monitor `lock` trong thời gian ngủ**. Thread khác cần `lock` có thể bị `BLOCKED` dù CPU không làm việc hữu ích. Đây không phải cách cho thread khác vào critical section để cập nhật điều kiện.

Ngược lại:

```java
synchronized (lock) {
    lock.wait();
}
```

thì thread sẽ nhả monitor `lock` trong lúc chờ. Nhưng nếu không có predicate và protocol signal, đoạn thứ hai có nguy cơ lost notification hoặc chờ vô hạn. Hai đoạn trên chỉ minh họa hành vi monitor, không phải chương trình chạy đầy đủ.

## 16. `wait()` chỉ nhả monitor của **receiver**, không nhả mọi khóa

Một thread có thể sở hữu nhiều monitor lồng nhau:

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

Đây là đoạn minh họa với hai object `outer` và `inner` giả định.

`inner.wait()` tạm nhả **monitor `inner`**, không tự nhả monitor `outer`. Trong lúc thread đang chờ trên inner, nó vẫn có thể đang giữ outer. Nếu một thread khác cần outer để chuẩn bị signal phù hợp, chương trình có thể deadlock.

Đây là lý do cần kiểm tra **những khóa còn giữ trên stack** trước khi gọi `wait` hoặc một operation blocking. `Object.wait` không phải primitive "unlock toàn bộ các resource".

Tương tự, `Condition.await()` của `java.util.concurrent.locks` nhả và lấy lại **lock gắn với Condition** theo hợp đồng, không tự giải phóng mọi monitor/lock khác mà caller đang giữ.

Với intrinsic monitor reentrant, `wait` nhả các mức sở hữu của **chính monitor receiver** trong khi chờ và khôi phục quyền sở hữu phù hợp trước khi trở về; nhưng không nhả các monitor độc lập.

## 17. `IllegalMonitorStateException` và các lỗi API dễ gặp

Sai:

```java
Object lock = new Object();
lock.wait();        // Caller không giữ monitor lock.
```

Sai tương tự:

```java
Object lock = new Object();
lock.notifyAll();   // Caller không giữ monitor lock.
```

Hai đoạn là ví dụ lỗi riêng lẻ; để chạy phải xử lý checked `InterruptedException` ở ví dụ `wait`. Trong cả hai trường hợp, việc không sở hữu monitor của receiver gây `IllegalMonitorStateException`.

Một lỗi tinh vi hơn:

```java
synchronized (firstLock) {
    secondLock.wait();
}
```

Nếu `firstLock` và `secondLock` là hai object khác nhau và caller không sở hữu monitor `secondLock`, vẫn lỗi. Không đủ chỉ "đang ở bên trong một block `synchronized` bất kỳ".

### `wait()` khác `join()`

`Thread.join()` là API cấp cao hơn để **đợi thread kết thúc**. Nó có giao thức completion và memory consistency phù hợp. Không cần người dùng tự gọi `wait()`, `notify()` trên object `Thread` để điều phối completion; làm vậy dễ va chạm với cách triển khai và giao thức của thư viện.

Nếu cần kết quả của task, dùng `Future.get()`; nếu cần tín hiệu one-shot, dùng `CountDownLatch`. Chúng trình bày mục tiêu rõ hơn việc tự thao tác monitor.

## 18. Happens-before: notification có vai trò gì với visibility?

Khi một thread đổi predicate và gọi `notifyAll()` trong monitor, sau đó rời monitor, thread được đánh thức chỉ đi tiếp khi đã lấy lại **cùng monitor**.

Ví dụ:

```java
synchronized (lock) {
    data = 42;
    ready = true;
    lock.notifyAll();
} // unlock lock
```

và:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    System.out.println(data);
}
```

Hai đoạn là minh họa của một giao thức chung với `data`, `ready` bảo vệ bằng `lock`. Nếu không có writer xung đột khác, reader sau khi vượt predicate sẽ thấy `42`.

Giải thích JMM:

1. Trong writer, cập nhật `data` và `ready` được thực hiện trước lần unlock monitor `lock` theo program order.
2. Unlock monitor `lock` **happens-before** lần lock tiếp theo trên cùng monitor mà waiter phải thực hiện trước khi rời `wait`.
3. Reader kiểm tra `ready` và đọc `data` khi đang giữ monitor, nên có quan hệ visibility/order phù hợp.
4. `notifyAll` là phần của **giao thức điều phối**; **không nên tách notification ra khỏi predicate và monitor** để suy luận rằng chỉ một lời gọi notify đã công bố mọi dữ liệu bất kỳ.

Nếu một writer thứ ba sửa `data` không qua monitor, vẫn có data race tiềm tàng. Monitor protocol chỉ có hiệu lực khi **mọi đường truy cập xung đột cần bảo vệ cùng tuân thủ giao thức**.

## 19. Multiple consumers: vì sao điều kiện có thể sai trở lại sau khi notify?

Giả sử queue vừa có một item. Một lần `notifyAll()` đánh thức ba consumer đang chờ trên cùng monitor.

```text
Producer:
  put 1 item
  notifyAll()
  unlock

Consumer A lấy monitor trước:
  queue không rỗng -> lấy item -> unlock

Consumer B lấy monitor sau:
  queue đã rỗng -> while kiểm tra lại -> wait

Consumer C lấy monitor sau:
  queue vẫn rỗng -> while kiểm tra lại -> wait
```

Không có gì sai ở đây: **notification chỉ trao cơ hội**, không dành riêng item cho từng waiter. Một waiter đã thức phải cạnh tranh monitor và kiểm tra lại trạng thái, vì thread khác có thể đã tiêu thụ điều kiện.

Đó là nguyên nhân thứ hai (ngoài spurious wakeup) khiến `if` là sai khi chờ resource có thể bị tiêu thụ bởi waiter khác.

Cần phân biệt:

- `notifyAll` đánh thức mọi waiter **đang trong wait set** của monitor, không tự thức mọi thread `BLOCKED` đang đợi vào `synchronized`.
- Thread vừa được đánh thức chưa được bảo đảm chạy trước thread mới đến lấy monitor.
- Không có FIFO hoặc fairness guarantee mặc định cho intrinsic monitor.
- Một waiter chỉ tiến qua vòng `while` khi **predicate đúng tại lúc nó giữ monitor**.

## 20. Đóng, hủy và lỗi trong giao thức monitor

Một bounded queue tự viết cần trả lời nhiều câu hỏi ngoài trường hợp bình thường:

- Nếu producer chết trước khi gửi sentinel, consumer thoát bằng cách nào?
- Nếu consumer bị hủy khi queue đang đầy, producer có thể kẹt trong `put` không?
- Nếu `close()` được gọi khi nhiều waiter đang `wait`, ai đánh thức họ?
- Sau khi close, `put` trả exception, false hay vẫn nhận item?
- `take` sau close có tiêu thụ hết item tồn trước đó hay dừng ngay?
- Nếu thread bị interrupt giữa operation, state có bị cập nhật nửa chừng không?

Một hướng thiết kế là bảo vệ thêm **`closed` predicate** dưới cùng monitor và `notifyAll` khi chuyển trạng thái đóng:

```java
synchronized void close() {
    closed = true;
    notifyAll();
}

synchronized Integer take() throws InterruptedException {
    while (items.isEmpty() && !closed) {
        wait();
    }
    if (items.isEmpty()) {
        return null; // Quy ước null nghĩa là closed và đã rỗng.
    }
    Integer value = items.removeFirst();
    notifyAll();
    return value;
}
```

Đây là minh họa phương thức trong một class giả định có `closed` và `items`; không phải chương trình độc lập. Trong contract cần cấm null là dữ liệu hợp lệ nếu `null` được dùng làm sentinel kết thúc. Đường `put` cũng phải kiểm tra `closed` trước/sau vòng chờ theo quy tắc thích hợp, không chỉ sửa mỗi `take`.

**Cần chuyển trạng thái trước khi notify** để waiter thức dậy không cần đoán nguyên nhân. Nếu `close` không đánh thức toàn bộ waiters, một số thread có thể vẫn chờ mãi dù hệ thống không nhận thêm dữ liệu.

Ứng dụng thực nên ưu tiên `BlockingQueue`, future, latch hoặc thành phần có lifecycle rõ nếu không có lý do cần hiện thực monitor condition từ đầu.

## 21. `wait/notify` so với các tiện ích Java cấp cao

| Bài toán | Primitive thường phù hợp | Vì sao |
| --- | --- | --- |
| Chờ một predicate của state bảo vệ bởi monitor | `synchronized` + `while` + `wait/notifyAll` | Kiểm soát trực tiếp state và monitor |
| Producer–consumer, queue có capacity | `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` | Đã đóng gói protocol not-empty/not-full |
| Đợi một nhóm task hoàn tất | `CountDownLatch` hoặc `Future` | Biểu diễn completion; không cần tự quản wait set |
| Đồng bộ nhiều vòng theo phase | `CyclicBarrier` hoặc `Phaser` | Có semantics cho nhiều lượt phối hợp |
| Giới hạn số tác vụ giữ resource | `Semaphore` | Permit, acquisition/release, timeout và interruption |
| Cần nhiều nhóm condition cùng một lock | `ReentrantLock` + `Condition` | Có thể tạo nhiều condition queues, giảm đánh thức không cần thiết |
| Chờ một thread kết thúc | `Thread.join()` | Hợp đồng lifecycle và HB trực tiếp |
| Chờ kết quả task async | `Future.get()` / `CompletableFuture` | Gắn việc chờ với kết quả và lỗi của task |

`Condition.await()` cũng phải được dùng với predicate trong vòng `while`; nó có thể có spurious wakeup. `Condition.signal` gần về vai trò với `notify`, nhưng thuộc condition queue gắn với một `Lock`, không phải monitor wait set của `Object`.

Không dùng `wait/notify` chỉ vì nó "thấp cấp nên nhanh hơn"; các tiện ích concurrent thường rõ semantics và dễ kiểm chứng hơn, có thể cho phép timeout/cancellation/lifecycle tốt hơn.

## 22. Callback hoặc I/O đang giữ monitor: rủi ro deadlock

Một thread có thể rời wait set nhưng **vẫn không tiến được** nếu thread khác giữ monitor quá lâu:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
    slowNetworkCall(); // Vẫn giữ lock!
}
```

Đây là đoạn anti-pattern minh họa. Việc gọi `notifyAll` **không thả khóa**. Nếu `slowNetworkCall` block vô hạn, waiter dù đã được đánh thức vẫn không lấy lại monitor để đi tiếp.

Mẫu tốt hơn:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
}
// Đã nhả monitor.
slowNetworkCall();
```

Cũng cần tránh callback do caller cung cấp, `Thread.join()`, `Future.get()`, `BlockingQueue.take()` hoặc I/O có thể block trong một critical section, nhất là nếu tác vụ được đợi cần chính monitor đó để hoàn tất.

Nếu I/O thay đổi state sau khi hoàn thành, cần **chụp snapshot dưới lock → làm I/O ngoài lock → lấy lock kiểm tra phiên bản/invariant và commit**. Việc nhả lock trước I/O không tự tạo transaction xuyên cả JVM và hệ thống bên ngoài.

## 23. Kiểm thử monitor protocol sao cho đáng tin?

Không nên thử bằng cách đoán thời gian:

```java
worker.start();
Thread.sleep(100);
synchronized (lock) {
    lock.notifyAll();
}
```

Đây là anti-pattern minh họa. `sleep` chỉ tạo độ trễ, không chứng minh worker đã vào wait set. Nếu không có predicate, signal đến sớm vẫn bị mất. Nếu có predicate đúng, không cần phụ thuộc sleep.

Với test, nên dùng:

1. **CountDownLatch/Phaser** để chủ động phối hợp mốc bắt đầu và kết thúc.
2. **Predicate dưới monitor** để bảo đảm notification sớm hay muộn đều đúng.
3. **Timeout giới hạn** trong test có khả năng treo khi lỗi, không dùng `join()` vô hạn cho một test sai thiết kế.
4. **Thread dump / ThreadMXBean** khi cần chẩn đoán waiter, owner và monitor.
5. **Kiểm tra invariant** sau khi các worker hoàn thành, không chỉ tìm exception.
6. **Stress test** qua nhiều lịch chạy, nhưng không coi việc chưa thấy lỗi là chứng minh an toàn.
7. **Test shutdown/interruption** để không để waiter ở lại vô thời hạn khi pipeline đóng hoặc một producer lỗi.

Một lưu ý kiểm thử: latch báo "worker đã tới trước `wait`" không tự đồng nghĩa worker **đã rơi vào `WAITING`**, trừ khi protocol còn bảo đảm monitor ownership/ordering phù hợp. Trong `TwoConditionsDemo`, cùng monitor với `releaseBoth` giúp kiểm tra điều này mà không dựa vào sleep.

## 24. Những nhầm lẫn thường gặp

**1. "`notify()` cho thread chờ quyền chạy ngay."** Không. Waiter còn phải lấy lại monitor; notifier vẫn giữ monitor cho đến khi nhả.

**2. "`notifyAll()` khiến mọi thread chạy trong monitor cùng lúc."** Không. Monitor vẫn mutual exclusive; các waiter tranh lock lần lượt.

**3. "`wait()` dùng ngoài `synchronized` cho nhanh."** Sai. Caller phải đang sở hữu monitor receiver, nếu không gặp `IllegalMonitorStateException`.

**4. "Chỉ cần đang ở một block synchronized bất kỳ."** Không. Phải sở hữu **đúng monitor của object gọi `wait/notify`**.

**5. "`wait` tự động nhả mọi lock."** Sai. Chỉ nhả monitor receiver, không nhả các monitor hoặc lock khác trên stack.

**6. "`sleep` cũng nhả lock như `wait`."** Sai. `Thread.sleep` không nhả monitor đang giữ.

**7. "`notify` được ghi nhớ nếu chưa ai đợi."** Sai. Không có permit tích lũy; dùng predicate bảo vệ trong monitor.

**8. "Sau khi `wait` trả về, condition chắc chắn đúng."** Sai. Có spurious wakeup, nhiều waiter tranh resource và các predicate khác; dùng `while`.

**9. "`if` đủ nếu chỉ có một producer."** Vẫn dễ sai khi cancellation, spurious wakeup hoặc nhiều consumer; nguyên tắc guarded block là `while`.

**10. "Dùng `notify` luôn tiết kiệm hơn mà vẫn đúng."** Không khi có nhiều loại predicate trên cùng wait set; có thể đánh thức sai waiter và mất tiến độ.

**11. "Gọi `notifyAll` sau khi nhả monitor là đúng."** Caller của notify phải đang **sở hữu monitor**; không được nhả trước rồi gọi ngoài `synchronized`.

**12. "Có `volatile` thì có thể tách check condition ra ngoài lock rồi `wait`."** Visibility đơn thuần không thay thế atomicity giữa kiểm tra predicate và nhả monitor/chờ.

**13. "`InterruptedException` nghĩa thread đã chết."** Không. Đó là tín hiệu interruption; code catch có thể tiếp tục chạy.

**14. "Timeout return nghĩa là điều kiện đúng."** Không. Hết thời gian chỉ nói thread đã thôi chờ; predicate phải được kiểm tra riêng.

**15. "`notifyAll` giải quyết mọi vấn đề deadlock."** Không. Nó không nhả monitor ngay, không giải phóng các khóa khác và không sửa dependency cycle hoặc resource leak.

**16. "Gọi `notify()` trên object `Thread` là cách chờ thread hoàn thành."** Không nên. Dùng `Thread.join()` để dựa vào contract lifecycle đúng.

## 25. Checklist khi viết `wait/notifyAll`

Trước khi gửi code vào production, kiểm tra:

1. **Monitor có cố định không?** Mọi waiter/notifier dùng đúng cùng một object, không đổi receiver giữa chừng.
2. **Predicate là gì?** Có field trạng thái rõ ràng thể hiện điều kiện cần, thay vì chỉ dựa trên một "tín hiệu"?
3. **Mọi đường truy cập state có cùng khóa không?** Nếu có đường bỏ qua monitor thì memory/invariant reasoning có thể sai.
4. **`wait` có ở trong `while (!predicate)` không?** Không dùng `if` làm guarded wait.
5. **State có được cập nhật trước notification không?** Người thức dậy phải có điều kiện để kiểm tra.
6. **`notify` có thực sự đủ không?** Khi nhiều predicate cùng wait set hoặc close phải đánh thức nhiều waiter, dùng `notifyAll` nếu không chứng minh được tính đúng của `notify`.
7. **Có giữ monitor quá lâu sau notify không?** Tránh callback, I/O, future wait và các thao tác block không cần thiết.
8. **Interruption xử lý ra sao?** Propagate hoặc khôi phục flag nếu không xử lý; cleanup không làm mất invariant.
9. **Có timeout/close/failure protocol không?** Waiter có đường thoát nếu producer chết hoặc hệ thống shutdown.
10. **Wait có giữ thêm lock khác không?** `Object.wait` chỉ nhả monitor receiver.
11. **Có nhiều consumers/producers không?** Một notification có thể đánh thức sai waiter; nhiều waiter thức lại có thể thấy predicate sai.
12. **Nếu state có thể reset, có vòng đời generation không?** Tránh dùng một flag một lần cho giao thức nhiều chu kỳ mà không quy định reset.
13. **Có primitive cấp cao thay thế không?** `BlockingQueue`, `CountDownLatch`, `Condition` hoặc `Future` thường giảm số lỗi phải tự xử lý.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao phải sở hữu monitor để gọi `wait()`?**

Vì waiter cần kiểm tra predicate và đi vào trạng thái chờ theo giao thức monitor. Không giữ đúng monitor sẽ ném `IllegalMonitorStateException` và không có atomicity giữa check và wait.

**2. Một thread vừa được `notifyAll()` có thể ở `BLOCKED` không?**

Có. Thread đó có thể đã được đánh thức khỏi wait set nhưng còn phải chờ lấy lại monitor trước khi `wait` trả về.

**3. Tại sao `while` đúng hơn `if` khi chờ queue không rỗng?**

Vì thread có thể thức do spurious wakeup, notification cho condition khác hoặc vì một consumer khác đã lấy item trước. Predicate phải kiểm tra lại khi giữ monitor.

**4. Nếu producer gọi `notify()` trước khi consumer gọi `wait()`, notification có được giữ lại không?**

Không. Cần predicate như `queue.isEmpty()` hoặc `ready`; consumer chỉ chờ nếu điều kiện thật sự chưa đạt.

**5. `wait` và `sleep` khác nhau về monitor thế nào?**

`wait` nhả monitor receiver trong lúc chờ và lấy lại trước khi trả về; `sleep` không nhả monitor mà thread đang giữ.

**6. Khi có cả producer lẫn consumer cùng chờ trên một monitor, vì sao `notifyAll` có thể an toàn hơn `notify`?**

Vì `notify` chọn một waiter không biết predicate nào hợp lệ; đánh thức sai nhóm có thể khiến hệ thống không tiến. `notifyAll` cho mọi nhóm cơ hội kiểm tra lại điều kiện của mình.

**7. Nếu `wait` ném `InterruptedException`, thread có còn giữ monitor không?**

Có. Thread phải lấy lại monitor receiver trước khi method thoát bằng exception; ứng dụng vẫn cần cleanup/propagate interrupt đúng cách.

**8. Có nên gọi `notifyAll` rồi làm HTTP request trước khi rời `synchronized` không?**

Thường không. Notified waiters vẫn phải đợi monitor, nên HTTP request chậm kéo dài lock hold time. Hãy tách I/O khỏi critical section và thiết kế commit/state-check phù hợp.

**9. Trong bounded queue, tại sao `put` và `take` đều nên notify khi state thay đổi?**

Vì `put` có thể làm buffer từ rỗng sang không rỗng (đánh thức consumer), còn `take` có thể làm buffer từ đầy sang còn chỗ (đánh thức producer). Với nhiều predicate chung monitor, `notifyAll` giúp hai nhóm kiểm tra lại đúng lúc.

**10. Một waiter thức dậy nhưng predicate vẫn false nên làm gì?**

Giữ monitor, quay lại `wait` trong vòng `while`, trừ khi có interruption, timeout, close hoặc chính sách hủy cần xử lý.

## 27. Tóm tắt bản chất

- **Monitor là cơ chế sở hữu khóa; predicate là sự thật nghiệp vụ; notification là tín hiệu kiểm tra lại.** Không đánh đồng ba khái niệm này.
- **`wait()`** chỉ hợp lệ khi caller sở hữu monitor receiver; nó nhả monitor đó trong lúc chờ và lấy lại monitor trước khi trả về hoặc ném `InterruptedException`.
- **`notify()`** đánh thức tối đa một waiter tùy ý, **`notifyAll()`** đánh thức mọi waiter trên cùng monitor. Không method nào nhả monitor ngay khi được gọi.
- **`while (!predicate) wait()`** là mẫu cốt lõi để xử lý spurious wakeup, tranh resource, các condition khác và notification tới sớm thông qua predicate.
- **Không dựa vào `Thread.sleep` hay lịch chạy giả định** để chứng minh tín hiệu sẽ đến đúng thời điểm; giữ state và signal trong cùng monitor.
- **Interruption, timeout, shutdown và lỗi producer/consumer** là một phần của giao thức phối hợp cần thiết kế, không phải phần tùy chọn trong hệ thống thực.
- **Hạn chế tự triển khai monitor condition khi có công cụ Java cao hơn phù hợp** như `BlockingQueue`, `CountDownLatch`, `Condition`, `Future` hoặc `Thread.join()`.

Khi nhìn thấy `wait/notify` trong Java, câu hỏi đầu tiên nên là: **"Predicate nào đang được bảo vệ bởi monitor nào, và mọi thread có kiểm tra lại predicate sau khi thức không?"** Nếu trả lời rõ được câu hỏi đó, phần lớn các lỗi lost notification và chờ sai điều kiện sẽ dễ nhận diện và sửa đúng bản chất.