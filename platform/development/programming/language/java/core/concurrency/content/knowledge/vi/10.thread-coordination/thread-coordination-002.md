# Điều kiện chờ trong Java: Vì sao dùng while thay vì if?

## 1. Mục tiêu và bối cảnh

Trong **phối hợp luồng (thread coordination)**, một thread thường cần chờ cho đến khi trạng thái chia sẻ cho phép nó làm tiếp: consumer chờ queue có phần tử, producer chờ buffer còn chỗ, worker chờ tài nguyên được cấp, hoặc nhiều thread chờ cờ `ready` được bật. Java cung cấp `Object.wait()` và `Condition.await()` để chờ mà không phải quay vòng tiêu CPU liên tục. Tuy nhiên, việc gọi đúng API thôi chưa đủ: **thread được đánh thức không có nghĩa điều kiện mà nó chờ đã trở thành đúng hoặc còn đúng**.

Quy tắc cốt lõi của bài:

~~~java
// Mẫu đúng về cấu trúc:
synchronized (lock) {
    while (!conditionIsTrue()) {
        lock.wait();
    }
    // Thực hiện thao tác phụ thuộc điều kiện khi còn giữ lock.
}
~~~

Trong đoạn minh họa này, `lock` và `conditionIsTrue()` được khai báo ở phạm vi phù hợp; caller phải xử lý/khai báo `InterruptedException`. **Không dùng `if` thay cho `while`** khi điều kiện phải được bảo đảm sau khi thức dậy.

Sau bài, bạn sẽ:
- Phân biệt **điều kiện nghiệp vụ (predicate)** với **tín hiệu đánh thức (notification)**.
- Giải thích chính xác các nguyên nhân khiến `wait()/await()` kết thúc dù predicate vẫn sai: **spurious wakeup**, cạnh tranh giữa các waiter, và điều kiện thay đổi trước khi thread lấy lại khóa.
- Hiểu việc **kiểm tra predicate và gọi wait phải nằm trong cùng một giao thức đồng bộ**, nếu không có thể mất thông báo.
- Nhận biết `wait()` nhả monitor, `notify()/notifyAll()` không lập tức chuyển lock, và waiter phải lấy lại monitor trước khi kiểm tra điều kiện.
- Sử dụng `while` với `Object.wait()`, `Condition.await()`, timeout, interruption và trạng thái đóng (shutdown).
- Chạy các chương trình Java 17+ chứng minh vì sao `if` sai ngay cả khi code có `synchronized`.

**Phạm vi:** cơ chế concurrency của **Java nói chung**, không sử dụng các annotation/API hoặc cấu hình bất đồng bộ riêng của Spring, vì Spring đã có chương riêng.

## 2. Hai sự thật khác nhau: “được báo” và “đủ điều kiện”

Giả sử queue ban đầu trống. Consumer chỉ được lấy một phần tử khi:

~~~text
predicate notEmpty := queue.size() > 0
~~~

Producer có thể thêm một phần tử rồi gọi `notifyAll()`. Nhưng đây là hai hành động khác nhau:
1. Producer **thay đổi trạng thái**: queue có dữ liệu.
2. Producer **phát tín hiệu**: thread đang chờ được quyền cố gắng thức dậy và tranh lock.

Đừng đánh đồng chúng. Notification không mang sẵn phần tử, không cung cấp “giấy phép lấy một item” và **không giữ chỗ** cho một consumer cụ thể. Trước khi consumer thức dậy và lấy được khóa, một consumer khác có thể đã lấy phần tử. Vì vậy câu “tôi vừa được notify” không chứng minh `!queue.isEmpty()`.

Một tình huống đơn giản:

~~~text
Queue có 0 phần tử.
C1 đang wait vì queue trống.
C2 cũng đang wait vì queue trống.

Producer thêm đúng 1 phần tử X và gọi notifyAll().
  |
  +-- C1 lấy lock trước, lấy X, queue trở lại rỗng.
  |
  +-- C2 lấy lock sau.
        Nếu dùng if: nhảy qua kiểm tra cũ rồi remove -> lỗi.
        Nếu dùng while: kiểm tra lại, queue vẫn rỗng -> chờ tiếp.
~~~

**Điều kiện (predicate)** trả lời “tôi có được làm tiếp không?”, còn **notification** trả lời “đã có một sự kiện có thể khiến điều kiện thay đổi, hãy kiểm tra lại”. Code đúng luôn dựa vào **predicate được đọc dưới đúng khóa**, không dựa vào một lời thông báo đã đến.

## 3. Cơ chế Object.wait() và monitor

### 3.1. Cùng một monitor phải bảo vệ cả predicate và state

Mẫu consumer:

~~~java
synchronized (monitor) {
    while (queue.isEmpty()) {
        monitor.wait();
    }
    return queue.removeFirst();
}
~~~

Mẫu producer cùng giao thức:

~~~java
synchronized (monitor) {
    queue.addLast(item);
    monitor.notifyAll();
}
~~~

Đây là các đoạn minh họa nằm trong method hợp lệ, giả định `monitor`, `queue`, `item` đã có; phía consumer khai báo hoặc xử lý `InterruptedException`. Tất cả đường sửa/đọc `queue` mà liên quan predicate phải dùng **cùng monitor**.

Lý do:
- Consumer lấy monitor để kiểm tra queue.
- Nếu trống, `monitor.wait()` đặt thread vào wait set và **nhả monitor đó** theo giao thức của `wait()`. Producer không thể chen vào giữa lần kiểm tra và bước wait theo cách làm mất tín hiệu khi cả hai cùng tuân thủ monitor.
- Producer lấy monitor, thêm phần tử, rồi gọi `notifyAll()` khi đang giữ monitor; sau đó nhả monitor.
- Consumer được đánh thức **phải lấy lại monitor** trước khi `wait()` trở về; chỉ lúc ấy nó mới kiểm tra lại `queue.isEmpty()`.
- Nếu điều kiện vẫn sai, vòng `while` gọi `wait()` lần nữa. Nếu đúng, hành động `removeFirst()` xảy ra **dưới cùng khóa** với lần kiểm tra cuối.

Một thread có thể giữ nhiều lock, nhưng `monitor.wait()` chỉ tự nhả **monitor của object `monitor`**. Nó không nhả các `synchronized` monitor khác hay `ReentrantLock` khác mà thread đang giữ. Giữ lock khác trong lúc chờ có thể gây deadlock hoặc ngăn thread phát tín hiệu tiến triển.

### 3.2. wait() khác sleep()

| API | Đặc tính chờ | Khả năng giải phóng khóa |
| --- | --- | --- |
| `monitor.wait()` | Chờ notification, interruption hoặc spurious wakeup | **Nhả đúng monitor được gọi wait**, lấy lại trước khi trả về |
| `monitor.wait(millis)` | Thêm khả năng hết timeout | Nhả và lấy lại đúng monitor |
| `Thread.sleep(millis)` | Ngủ theo thời gian | **Không nhả bất kỳ monitor nào** chỉ vì sleep |
| `condition.await()` | Chờ signal/interruption/spurious wakeup của `Condition` | Nhả rồi lấy lại **lock liên kết với Condition** |
| `BlockingQueue.take()` | Chờ queue có phần tử, trừ khi bị interrupt | Primitive tự phối hợp nội bộ; không phải gọi `wait()` thủ công |

`Thread.sleep(100)` bên trong `synchronized` không phải cách chờ producer đổi state: thread ngủ vẫn giữ monitor, ngăn producer cần monitor đó vào cập nhật. Thêm `sleep` cũng không tạo quan hệ happens-before cần thiết để sửa race.

### 3.3. Phải giữ monitor khi gọi wait/notify

Các lời gọi `wait()`, `notify()` và `notifyAll()` trên một object yêu cầu thread hiện tại đang giữ **monitor của chính object ấy**. Nếu không, Java ném `IllegalMonitorStateException`.

~~~java
Object lock = new Object();

// Sai về giao thức: lock.wait(); // Nếu không ở synchronized(lock).

synchronized (lock) {
    // lock.wait(); // Hợp lệ về ownership, nhưng sẽ đợi.
    lock.notifyAll(); // Hợp lệ về ownership.
}
~~~

Trên các ví dụ ở bài, phần thread gọi wait phải có đường thoát, không gọi `wait()` vô hạn trong main mà không có thread khác phát signal.

## 4. Ba lý do bắt buộc kiểm tra lại điều kiện bằng while

### 4.1. Spurious wakeup (thức dậy không do tín hiệu dự kiến)

Javadoc của `Object.wait()` và `Condition.await()` cho phép một lần chờ trở về dù không có notification hoặc sự kiện hoàn thành tương ứng. Đây gọi là **spurious wakeup**.

Ví dụ sai:

~~~java
synchronized (monitor) {
    if (!ready) {
        monitor.wait();
    }
    useResource(); // Không có bảo đảm ready == true.
}
~~~

Với một spurious wakeup, `wait()` trả về nhưng `ready` vẫn false, và code dùng `if` không quay lại kiểm tra. Với `while`:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    useResource(); // Predicate đã được kiểm tra đúng khi giữ monitor.
}
~~~

Java không hứa spurious wakeup xuất hiện trong mọi lần chạy; không dùng benchmark may rủi hoặc `Thread.sleep` để “chứng minh” nó. Nhưng code **phải đúng kể cả khi hiện tượng xảy ra**.

### 4.2. Nhiều waiter có thể cùng thức dậy nhưng chỉ có một tài nguyên

`notifyAll()` làm nhiều waiter cố thức dậy; mỗi waiter phải tranh để lấy lại monitor. Nếu producer thêm một item, **chỉ một consumer có thể lấy item ấy**. Consumer khác tỉnh sau đó có thể thấy queue rỗng.

Vấn đề này xảy ra **ngay cả không có spurious wakeup**. Vì thế lời giải thích “while chỉ để phòng JVM tự dưng đánh thức” là **chưa đầy đủ**.

### 4.3. Điều kiện đổi sau signal nhưng trước lúc waiter lấy lại lock

Ngay cả khi producer vừa gọi `notify()` vì điều kiện đã đúng:
- Producer vẫn giữ monitor cho đến khi nó rời vùng `synchronized`.
- Waiter vừa được notify chưa thể chạy phần sau `wait()` khi chưa lấy lại monitor.
- Một thread thứ ba có thể được scheduler cho lấy monitor sớm hơn waiter và thay đổi state.
- Tại lần waiter giữ monitor trở lại, predicate có thể đã sai.

Đây là cách nhìn tương đồng với **Mesa-style condition variable**: signal không “trao tay” điều kiện; waiter **tự kiểm tra** sau khi được quyền chạy. Không suy luận rằng `notifyAll()` chuyển trạng thái Thread ngay lập tức sang thực thi nghiệp vụ.

## 5. Ví dụ chạy được 1 — if tiếp tục sai sau một notification hợp lệ

Bài toán: worker chỉ được tiếp tục nếu `ready=true`. Main cố tình phát `notifyAll()` **mà không đổi `ready`**. Một chương trình dùng `if` sẽ tiếp tục khi điều kiện vẫn false. Chúng ta dùng latch để kiểm soát điểm đợi, không dựa vào sleep.

Lưu file **`IfWaitBugDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class IfWaitBugDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch enteringWait = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (MONITOR) {
                if (!ready) {
                    enteringWait.countDown();
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("proceeded-when-ready=" + ready);
            }
        }, "if-waiter");

        worker.start();
        enteringWait.await();

        synchronized (MONITOR) {
            // Một tín hiệu không gắn với việc predicate trở thành true.
            MONITOR.notifyAll();
        }

        worker.join();
    }
}
~~~

Chạy Java 17+:

~~~bash
javac IfWaitBugDemo.java
java IfWaitBugDemo
~~~

Stdout trên đường thực thi không có interruption:

~~~text
proceeded-when-ready=false
~~~

**Vì sao kết quả xác định trong thí nghiệm này?**
- Worker gọi `enteringWait.countDown()` **trong khi đang giữ MONITOR**, ngay trước `wait()`.
- Main đợi latch, sau đó cố vào `synchronized(MONITOR)`. Main **không thể vào** cho tới khi worker thật sự gọi `wait()` và nhả MONITOR (nếu worker vẫn đang giữ nó).
- Main phát `notifyAll()` khi `ready` vẫn false rồi nhả monitor.
- Worker lấy lại monitor, trả về khỏi `wait()` và **không kiểm tra lại** vì đã rời nhánh `if`. Nó in false.

Ngay cả một notification có thật vẫn có thể không đồng nghĩa condition mong muốn đã đúng. Ví dụ này làm rõ lỗi của `if` mà không phải chờ spurious wakeup ngẫu nhiên.

**Không dùng code `if` này trong production.** Nếu worker phụ thuộc vào một tài nguyên thực, hành động sau khi thức dậy có thể lấy dữ liệu không tồn tại hoặc vi phạm invariant nghiệp vụ.

## 6. Ví dụ chạy được 2 — while bỏ qua wakeup chưa đủ điều kiện

Sửa cùng tình huống bằng `while`. Lần notify đầu tiên không thay `ready`; worker kiểm tra và tiếp tục chờ. Main đợi xác nhận worker đã **kiểm tra lại false** trước khi đặt `ready=true` và notify lần thứ hai.

Tạo file **`WhileWaitDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class WhileWaitDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstWait = new CountDownLatch(1);
        CountDownLatch checkedFalseAgain = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            int falseChecks = 0;

            synchronized (MONITOR) {
                while (!ready) {
                    falseChecks++;

                    if (falseChecks == 1) {
                        firstWait.countDown();
                    }
                    if (falseChecks == 2) {
                        checkedFalseAgain.countDown();
                    }

                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                System.out.println(
                        "rechecked-false=" + (falseChecks >= 2));
                System.out.println("proceeded-when-ready=" + ready);
            }
        }, "while-waiter");

        worker.start();
        firstWait.await();

        synchronized (MONITOR) {
            MONITOR.notifyAll(); // Wakeup khi ready vẫn false.
        }

        checkedFalseAgain.await();

        synchronized (MONITOR) {
            ready = true;
            MONITOR.notifyAll();
        }

        worker.join();
    }
}
~~~

Chạy:

~~~bash
javac WhileWaitDemo.java
java WhileWaitDemo
~~~

Stdout khi hoàn thành bình thường:

~~~text
rechecked-false=true
proceeded-when-ready=true
~~~

**Lập luận:**
1. Worker lần đầu thấy `ready=false` và báo `firstWait`.
2. Main chỉ lấy được `MONITOR` sau khi worker đã vào wait và nhả monitor, nên notify đầu tiên đánh thức worker đang chờ; `ready` vẫn false.
3. Worker lấy lại monitor, vào đầu `while` và tăng `falseChecks`; latch `checkedFalseAgain` xác nhận nó đã **thấy false lần nữa**.
4. Main đặt `ready=true` dưới monitor và notify. Nếu worker chưa đi vào wait lần nữa, main phải chờ lock cho tới khi worker wait; nếu worker đã wait thì main có thể phát tín hiệu. Cả hai trường hợp đều an toàn.
5. Worker chỉ in `proceeded-when-ready=true` sau khi nó đã lấy lại monitor và điều kiện đúng.

Một spurious wakeup thêm cũng không phá chứng minh: có thể xuất hiện nhiều lần kiểm tra false hơn, nhưng cuối cùng chương trình chỉ vượt vòng `while` khi state thật sự cho phép. Demo cố tình không in **số lần chính xác** bị đánh thức vì JDK không bảo đảm số đó.

**Khác biệt cốt lõi:** `if` kiểm tra một lần trước lúc chờ; `while` kiểm tra **trước mỗi lần chờ và sau mỗi lần thức dậy**.

## 7. Ví dụ chạy được 3 — hai consumer được báo, chỉ một item

Nếu hai waiter đã chờ queue rỗng, producer thêm một phần tử và `notifyAll()`, mẫu `if` có thể khiến waiter thứ hai cố lấy phần tử không còn tồn tại.

Ví dụ này điều phối để **hai consumer đều đi vào wait set trước khi producer thêm item**. Ta bắt lỗi từ `removeFirst()` và đếm kết quả thay vì phụ thuộc thread nào thắng.

Tạo file **`TwoConsumersIfDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.NoSuchElementException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoConsumersIfDemo {
    private static final Object MONITOR = new Object();
    private static final ArrayDeque<String> queue = new ArrayDeque<>();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothWaiting = new CountDownLatch(2);
        AtomicInteger claimed = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();

        Runnable consume = () -> {
            synchronized (MONITOR) {
                if (queue.isEmpty()) {
                    bothWaiting.countDown();
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                try {
                    queue.removeFirst();
                    claimed.incrementAndGet();
                } catch (NoSuchElementException e) {
                    failures.incrementAndGet();
                }
            }
        };

        Thread a = new Thread(consume, "consumer-a");
        Thread b = new Thread(consume, "consumer-b");
        a.start();
        b.start();

        bothWaiting.await();
        synchronized (MONITOR) {
            queue.addLast("X");
            MONITOR.notifyAll();
        }

        a.join();
        b.join();

        System.out.println("claimed=" + claimed.get());
        System.out.println("empty-remove-failures=" + failures.get());
    }
}
~~~

Chạy:

~~~bash
javac TwoConsumersIfDemo.java
java TwoConsumersIfDemo
~~~

Stdout khi không có interruption:

~~~text
claimed=1
empty-remove-failures=1
~~~

Tại sao lỗi tái hiện được?
- `bothWaiting` chỉ về 0 sau khi cả hai thread **đã vào synchronized và chuẩn bị gọi wait**. Main chỉ có thể thêm item khi lấy được monitor, tức các waiter đã nhả monitor để chờ.
- `notifyAll()` đánh thức cả hai. Người đầu lấy lock lấy item X; người thứ hai lấy lock sau thì queue đã rỗng.
- Vì dùng `if`, người thứ hai không kiểm tra lại queue, nên `removeFirst()` ném `NoSuchElementException` và được đếm.
- `AtomicInteger` chỉ được dùng để tổng hợp kết quả demo; nó **không sửa lỗi điều kiện chờ**.

Việc **lock bảo vệ queue là cần nhưng chưa đủ** nếu code dùng `if` sau wait: thao tác tiêu thụ phải được thực hiện **chỉ khi predicate đúng tại lần giữ lock cuối cùng**.

## 8. Sửa tình huống nhiều waiter: while kết hợp điều kiện closed

Nếu đổi `if` thành `while(queue.isEmpty()) wait()` trong ví dụ trên, consumer thứ hai sẽ **chờ hợp lệ** sau khi item duy nhất bị lấy. Nhưng nếu producer không bao giờ thêm phần tử nữa, thread đó có thể chờ mãi. Đây không phải bug của `while`; đó là yêu cầu **liveness/shutdown** chưa được thiết kế.

Một giao thức tốt có hai điều kiện:
- Khi `queue` có item: lấy item.
- Khi `queue` trống **và đã đóng**: kết thúc đợi.
- Khi `queue` trống **và chưa đóng**: tiếp tục wait.

Tạo file **`TwoConsumersWhileDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoConsumersWhileDemo {
    private static final Object MONITOR = new Object();
    private static final ArrayDeque<String> queue = new ArrayDeque<>();
    private static boolean closed;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothWaiting = new CountDownLatch(2);
        AtomicInteger claimed = new AtomicInteger();
        AtomicInteger stopped = new AtomicInteger();

        Runnable consume = () -> {
            synchronized (MONITOR) {
                while (queue.isEmpty() && !closed) {
                    bothWaiting.countDown();
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                if (queue.isEmpty()) {
                    stopped.incrementAndGet();
                    return;
                }

                queue.removeFirst();
                claimed.incrementAndGet();
            }
        };

        Thread a = new Thread(consume, "consumer-a");
        Thread b = new Thread(consume, "consumer-b");
        a.start();
        b.start();

        bothWaiting.await();

        synchronized (MONITOR) {
            queue.addLast("X");
            closed = true;
            MONITOR.notifyAll();
        }

        a.join();
        b.join();

        System.out.println("claimed=" + claimed.get());
        System.out.println("stopped=" + stopped.get());
        System.out.println("remaining=" + queue.size());
    }
}
~~~

Chạy:

~~~bash
javac TwoConsumersWhileDemo.java
java TwoConsumersWhileDemo
~~~

Stdout:

~~~text
claimed=1
stopped=1
remaining=0
~~~

Tại sao phiên bản này an toàn?
1. Cả hai consumer đợi khi `queue.isEmpty() && !closed`.
2. Main cập nhật **queue và closed trong cùng monitor** rồi `notifyAll()`, tránh trạng thái trung gian không nhất quán.
3. Một consumer lấy X; consumer còn lại thấy queue rỗng nhưng `closed=true`, nên thoát thay vì wait vô hạn hoặc gọi `removeFirst()` sai.
4. Lần check và remove đều dưới cùng monitor. Không ai thay đổi queue giữa hai bước.
5. Các trường `claimed/stopped` chỉ phục vụ kết quả demo; main đọc sau `join()`, khi worker đã kết thúc.

**Lưu ý trong ứng dụng thật:** `closed` ở đây có nghĩa **không nhận thêm phần tử** và consumer vẫn có thể lấy nốt item đã có. Nếu nghiệp vụ yêu cầu hủy toàn bộ hàng chờ ngay khi đóng, cần định nghĩa semantics khác. Đừng tự động áp dụng một quy tắc shutdown cho mọi loại queue.

## 9. Lost notification: vì sao check–wait phải nằm cùng monitor?

Lỗi lost notification khác với lỗi `if` ở mục trước. Ví dụ một thread kiểm tra flag ngoài monitor rồi mới chờ:

~~~java
// SAI: ready được kiểm tra ngoài monitor.
if (!ready) {
    synchronized (monitor) {
        monitor.wait();
    }
}
~~~

Thread khác có thể làm `ready=true` và notify vào **khoảng giữa** hai bước. Lúc ấy không có waiter, notification bị mất; thread cũ bắt đầu wait và có thể chờ vô hạn. `volatile ready` có thể cải thiện visibility cho riêng biến ready, nhưng **không tự ghép** thao tác check và wait thành một giao thức nguyên tử.

Mẫu nhất quán là:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
}
~~~

Đường thay đổi `ready` cũng phải giữ `monitor`:

~~~java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
~~~

Đó là cách tránh missed notification mà **không cần lưu lịch sử tín hiệu**. Nếu signal đến trước, waiter thấy predicate đã đúng và không chờ. Nếu signal đến sau khi waiter chờ, nó đánh thức waiter để kiểm tra lại.

**Quy tắc giao thức:** predicate phải là trạng thái chia sẻ được bảo vệ; notification là một gợi ý “đến kiểm tra lại” dưới monitor/condition tương ứng. Không đọc predicate bằng một khóa nhưng chờ dưới khóa khác, trừ khi đã có thiết kế coordination khác được chứng minh đúng.

## 10. Trong mỗi vòng while, phải giữ invariant ở điểm nhả khóa

`while` không tự sửa mọi lỗi concurrency. Cần bảo đảm **state của đối tượng nhất quán trước khi `wait()` nhả lock**.

Ví dụ một buffer có `size` và dữ liệu thực trong queue. Nếu code giảm `size` rồi `wait()` trước khi xóa phần tử thật, thread khác vào monitor có thể nhìn thấy `size != queue.size()`. Nó sẽ dựa vào predicate sai và có thể làm hỏng dữ liệu.

Mẫu sai về nguyên tắc:

~~~java
synchronized (monitor) {
    available--;
    monitor.wait(); // Nhả lock lúc invariant chưa được khôi phục.
    reserved++;
}
~~~

Giả định invariant `available + reserved == total`. Sau khi giảm `available` nhưng chưa tăng `reserved`, invariant sai. Nếu thread bị interrupt hoặc exception xảy ra, nó có thể không hoàn tất bước sau; việc `synchronized` tự nhả lock không rollback các thay đổi đã xảy ra.

Một mẫu tốt:

~~~java
synchronized (monitor) {
    while (available <= 0) {
        monitor.wait();  // Chưa đổi state, invariant vẫn đúng.
    }

    available--;
    reserved++;          // Cập nhật đầy đủ trong cùng critical section.
    monitor.notifyAll(); // Nếu predicate của nhóm waiter khác có thể đổi.
}
~~~

Các đoạn trên là **snippet** trong method có xử lý `InterruptedException` và state được khai báo phù hợp. Đường trả/nhả tài nguyên phải dùng cùng monitor và phát tín hiệu sau khi state đổi.

**Invariant** nói đối tượng hợp lệ hay không; **predicate** nói thread đang chờ có thể hành động hay chưa. Buffer rỗng hoàn toàn có thể hợp lệ theo invariant `0 <= size <= capacity` nhưng không đáp ứng predicate `notEmpty`. Sau wakeup, `while` kiểm tra lại predicate; mọi đường cập nhật dưới monitor phải giữ invariant hợp lệ.

## 11. Bounded buffer chạy được với nhiều producer/consumer

Đây là abstraction tự viết để học phối hợp luồng. Trong code production, `BlockingQueue` của thư viện chuẩn thường hợp lý hơn; nhưng việc tự viết cho thấy vì sao cần **hai vòng while**.

Tạo file **`BoundedBufferWhileDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedBufferWhileDemo {
    private static final class Buffer<T> {
        private final ArrayDeque<T> queue = new ArrayDeque<>();
        private final int capacity;

        Buffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        synchronized void put(T value) throws InterruptedException {
            while (queue.size() == capacity) {
                wait();
            }
            queue.addLast(value);
            notifyAll();
        }

        synchronized T take() throws InterruptedException {
            while (queue.isEmpty()) {
                wait();
            }
            T value = queue.removeFirst();
            notifyAll();
            return value;
        }

        synchronized int size() {
            return queue.size();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Buffer<Integer> buffer = new Buffer<>(2);
        AtomicInteger sum = new AtomicInteger();
        List<Thread> threads = new ArrayList<>();

        for (int p = 0; p < 2; p++) {
            final int base = p * 5;
            Thread producer = new Thread(() -> {
                try {
                    for (int i = 1; i <= 5; i++) {
                        buffer.put(base + i);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            threads.add(producer);
        }

        for (int c = 0; c < 2; c++) {
            Thread consumer = new Thread(() -> {
                try {
                    for (int i = 0; i < 5; i++) {
                        sum.addAndGet(buffer.take());
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            threads.add(consumer);
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("sum=" + sum.get());
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Chạy:

~~~bash
javac BoundedBufferWhileDemo.java
java BoundedBufferWhileDemo
~~~

Stdout khi không có interruption:

~~~text
sum=55
remaining=0
~~~

**Chứng minh kết quả:** Hai producer đưa đúng các số từ 1 đến 5 và 6 đến 10 (tổng 55); hai consumer lấy tổng cộng 10 phần tử. `synchronized put/take` giữ invariant `0 <= size <= 2` và không cho hai consumer lấy cùng phần tử. `while` ngăn lấy từ queue rỗng hoặc thêm vào buffer đã đầy sau wakeup. `AtomicInteger` dùng để cộng kết quả từ hai consumer, tránh race trên tổng; `join()` chờ tất cả kết thúc trước khi main in.

**Những điều không cố định:** thứ tự phần tử giữa **hai producer khác nhau** và consumer nào nhận số nào không được dự đoán. Chương trình chỉ khẳng định tổng và số lượng cuối. Nếu một thread bị interrupt và dừng sớm, phía còn lại có thể chờ vô hạn; demo cố tình không có giao thức close để tập trung vào while, vì thế không thay nó cho một queue production chưa có cancellation/shutdown.

### Khi nhiều nhóm waiter dùng chung monitor

Producer chờ `notFull`; consumer chờ `notEmpty`. Một `notify()` ngẫu nhiên có thể đánh thức producer khi buffer vẫn đầy hoặc consumer khi vẫn rỗng, trong khi nhóm cần thức có thể còn ngủ. `notifyAll()` đơn giản và dễ chứng minh liveness hơn trong ví dụ monitor chung; mọi waiter phải kiểm tra lại predicate. Giá đổi lại là có thể đánh thức nhiều thread rồi chúng đi ngủ lại (contention/thundering herd).

Trong cấu trúc có nhiều loại predicate, `ReentrantLock` kết hợp nhiều `Condition` giúp signal đúng nhóm.

## 12. Condition.await() và signal(): cùng nguyên tắc while

Với `java.util.concurrent.locks.ReentrantLock`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Các thành viên/method của một class (snippet, không phải file độc lập):
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final ArrayDeque<String> queue = new ArrayDeque<>();

public String take() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (queue.isEmpty()) {
            notEmpty.await();
        }
        return queue.removeFirst();
    } finally {
        lock.unlock();
    }
}

public void put(String value) {
    lock.lock();
    try {
        queue.addLast(value);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}
~~~

Nếu sử dụng snippet này trong class, cần import thêm `java.util.ArrayDeque`. Các ràng buộc:
- Caller phải **giữ đúng ReentrantLock** gắn với Condition trước khi gọi `await()/signal()`.
- `await()` **nhả lock trong lúc chờ**, rồi lấy lại trước khi trở về hoặc ném `InterruptedException`.
- `signal()` **không nhả lock ngay** và không trao quyền vượt predicate.
- Ngay cả khi Condition chỉ có một loại waiter, spurious wakeup và các thread khác vẫn có thể khiến predicate sai; luôn dùng `while`.
- `unlock()` trong `finally` giúp nhả lock khi có exception.

**Không chuyển máy móc từ `notifyAll` sang `signal`** mà không xét liveness. `signal` chọn một waiter trên condition đó; nếu nhiều loại predicate dùng chung một Condition, đánh thức sai loại hoặc không đủ waiter có thể gây kẹt. Dùng các Condition riêng cho `notEmpty/notFull` khi cần, hoặc `signalAll` nếu giao thức yêu cầu đánh thức tất cả.

### Khi nào không cần viết while thủ công?

`BlockingQueue.take()` đã tự thực hiện giao thức chờ/lấy phần tử theo hợp đồng class; caller không cần kiểm tra `isEmpty()` rồi gọi `take()`:

~~~java
String item = blockingQueue.take();
~~~

Đây là snippet bên trong method có `blockingQueue` được khai báo, phải xử lý `InterruptedException`. Nếu cần không chờ, dùng `poll()`, trả `null` khi trống (với queue chuẩn không chứa null). Nếu cần thời gian chờ giới hạn, dùng `poll(timeout, unit)`.

**Không viết:**

~~~java
if (!blockingQueue.isEmpty()) {
    String item = blockingQueue.take();
}
~~~

Bởi một consumer khác có thể lấy hết queue sau `isEmpty()`, khiến `take()` đợi dù điều kiện đã từng đúng. Chỉ một lời gọi `take/poll` có semantics thích hợp sẽ tránh check-then-act ở phía caller.

## 13. Timed wait: while vẫn cần, nhưng không được khởi động lại timeout

Các overload như `Object.wait(long millis)`, `Condition.await(long time, TimeUnit unit)` và `Condition.awaitNanos(long nanosTimeout)` cho phép chờ có hạn.

**Lưu ý:** `Object.wait(0)` là chờ **không thời hạn**, không phải “không chờ”. Một lần timed wait có thể trở về vì tín hiệu, spurious wakeup, hết thời gian hoặc interruption; trong mọi trường hợp, không suy ra predicate đúng khi chưa kiểm tra.

Mẫu chưa đạt yêu cầu deadline tổng:

~~~java
while (!ready) {
    monitor.wait(1_000); // Mỗi wakeup lại cấp nguyên một giây.
}
~~~

Nếu có nhiều lần wakeup khi `ready` còn false, tổng thời gian đợi có thể vượt 1 giây rất xa. Với timeout tổng, dùng **thời gian còn lại**.

### Mẫu Condition.awaitNanos

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Snippet là field/method bên trong một class:
private final ReentrantLock lock = new ReentrantLock();
private final Condition readyChanged = lock.newCondition();
private boolean ready;

public boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0) {
                return false;
            }
            remaining = readyChanged.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}

public void makeReady() {
    lock.lock();
    try {
        ready = true;
        readyChanged.signalAll();
    } finally {
        lock.unlock();
    }
}
~~~

- `while` kiểm tra predicate sau mỗi lần return từ `awaitNanos`.
- `remaining` được giảm theo kết quả của API, tránh cấp lại timeout ban đầu.
- Method trả `false` nếu hết budget condition-wait trong lúc predicate chưa đúng.
- Method trả `true` **chỉ sau khi quan sát ready=true khi giữ lock**.
- Tính toán thời gian ở đây bao quát **quãng đợi condition**, không phải deadline end-to-end bao gồm lúc đầu chờ lấy `lock`. Nếu cần deadline toàn bộ, phải tính thời gian của cả `lockInterruptibly()` bằng một giao thức `tryLock(remaining, unit)`/deadline thích hợp.

Đừng dùng `Thread.sleep` lặp lại như timed condition wait trong ứng dụng có độ nhạy latency hoặc cần hủy nhanh.

## 14. Interruption và exception: không được vượt qua điều kiện

Khi thread bị interrupt lúc `Object.wait()` hoặc `Condition.await()`, API có thể ném `InterruptedException`. **Interruption không phải dấu hiệu predicate đã đúng**. Worker cần dừng, propagate exception hoặc xử lý một chính sách cancellation riêng. Không bắt exception rồi tiếp tục thao tác nghiệp vụ như thể đã được cấp quyền.

Mẫu phù hợp trong một method khai báo `throws InterruptedException`:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait(); // Nếu bị interrupt, ngoại lệ truyền ra.
    }
    useResource();
}
~~~

Nếu không thể propagate:

~~~java
try {
    doInterruptibleWait();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Khôi phục interrupt status.
    return; // Không sử dụng tài nguyên khi predicate chưa đúng.
}
~~~

Đây là snippet trong method trả `void`. Với `Object.wait()`, JVM bắt thread phải lấy lại monitor trước khi wait trở về hoặc ném interruption theo contract, bảo đảm `synchronized` vẫn kiểm soát vùng nhả khóa. Nhưng trạng thái chia sẻ có thể đã được **các thread khác** sửa trong khoảng chờ; không nên suy ra nó không đổi.

### Exception sau một thao tác nửa chừng

Giả sử invariant `available + reserved == total`; code cập nhật `available--` rồi gọi một phương thức có thể throw, sau đó mới tăng `reserved++`. Nếu exception xảy ra ở giữa, `synchronized` tự nhả monitor nhưng **không rollback** state. Hãy validate trước, commit thay đổi đầy đủ trong critical section và có rollback nếu nghiệp vụ yêu cầu; không bao giờ đi vào `wait()` khi trạng thái đang phá invariant mà các thread khác có thể quan sát.

### Shutdown phải là một phần của predicate

Nếu producer dừng vĩnh viễn, consumer có thể chờ mãi dù vòng `while` là chính xác. Cần thêm điều kiện `closed`/`cancelled` và phát `notifyAll/signalAll` khi shutdown:

~~~java
synchronized (monitor) {
    while (queue.isEmpty() && !closed) {
        monitor.wait();
    }

    if (queue.isEmpty()) {
        // closed == true và không còn item:
        // kết thúc theo giao thức (ví dụ Optional.empty).
    } else {
        // lấy phần tử và xử lý.
    }
}
~~~

Đây là snippet mô tả control flow, không phải một chương trình độc lập. Đường ghi `closed=true` phải nằm trong cùng monitor, rồi đánh thức tất cả waiter liên quan. Nếu có hai nhóm waiter như producer và consumer, shutdown có thể phải signal **cả hai** nhóm. Khi close có nghĩa là không được thêm mới nhưng được lấy hết hàng đợi, consumer vẫn có thể lấy item còn lại trước khi kết thúc.

## 15. Những hiểu lầm và lỗi điển hình

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `if (!ready) wait()` | Bỏ qua kiểm tra sau wakeup | `while (!ready) wait()` |
| Nghĩ `notify()` nghĩa điều kiện chắc chắn đúng | Notify không mang predicate/giữ chỗ | Đọc state dưới monitor sau wakeup |
| Chỉ nghĩ tới spurious wakeup | Bỏ qua contention giữa nhiều waiter | Xem cả cạnh tranh tiêu thụ tài nguyên |
| Check ngoài lock rồi mới wait trong lock | Missed notification | Check và wait dưới cùng monitor |
| Producer sửa state ngoài monitor | Không có giao thức nhất quán/visibility | Mọi đường truy cập dùng cùng lock |
| Gọi wait/notify mà không giữ đúng monitor | `IllegalMonitorStateException` | Giữ monitor của object được gọi |
| Cho rằng notifyAll giải phóng monitor | Waiter vẫn cần tranh lock | Thread signal phải thoát vùng khóa |
| Dùng `Thread.sleep()` thay wait | Sleep không nhả monitor | Dùng condition wait hoặc BlockingQueue |
| Dùng `getState() == WAITING` để quyết định notify | Snapshot có race và không phải predicate nghiệp vụ | Dựa vào state được bảo vệ |
| Nhả lock giữa check và lấy phần tử | Check-then-act race | Cả hai thao tác trong critical section |
| Chờ khi invariant đang sai | Thread khác có thể thấy state chưa hoàn chỉnh | Khôi phục invariant trước wait |
| Dùng `notify()` khi có nhiều loại waiter | Đánh thức sai nhóm, có thể mất tiến triển | `notifyAll` hoặc Condition riêng |
| Timed wait luôn dùng lại timeout ban đầu | Wakeups làm tổng chờ vượt deadline | Tính remaining/deadline |
| Bỏ qua `InterruptedException` | Cancellation/shutdown bị treo | Propagate hoặc restore rồi thoát |
| Chỉ có một item nhưng hai waiter, không có closed | Một waiter có thể chờ mãi hợp lệ | Thiết kế close/cancel protocol |
| Tự viết wait/notify cho một queue đơn giản | Dễ mắc lỗi không cần thiết | Ưu tiên `BlockingQueue.take/poll` |
| Dùng `LongAdder/AtomicInteger` để “sửa” if wait | Atomic counter không thay predicate/lock protocol | Thiết kế condition đúng |

## 16. Checklist thiết kế cơ chế chờ

1. **Predicate chính xác là gì?** Không chỉ là “có notification”, mà là một điều kiện có thể kiểm tra như `!queue.isEmpty()` hoặc `ready == true`.
2. **State nào tạo predicate?** Ai có quyền thay đổi, ai đọc, tất cả có dùng cùng monitor/lock không?
3. **Invariant là gì?** Nó có đúng trước khi thread nhả lock hoặc đi vào `wait()/await()` không?
4. **Kiểm tra predicate trong vòng while chưa?** Nếu thức dậy do spurious wakeup hoặc waiter khác tiêu thụ tài nguyên, chương trình có kiểm tra lại không?
5. **Điều kiện cuối và hành động có cùng critical section?** Nếu nhả lock giữa hai bước, condition có thể biến mất.
6. **Signal có đến sau khi state đổi không?** Signal không thay thế state; nếu state chưa đổi thì waiter sẽ lại chờ.
7. **Có thể signal xảy ra trước waiter không?** Mẫu đúng phải khiến waiter quan sát predicate đã đúng và không wait.
8. **Có nhiều nhóm waiter không?** Chọn `notifyAll` hoặc các `Condition` riêng để tránh đánh thức sai nhóm.
9. **Có timeout tổng và interruption không?** Không tái sử dụng nguyên timeout sau mỗi wakeup; có đường thoát khi task bị hủy.
10. **Có thể không còn producer không?** Cần `closed/cancelled`, poison pill hoặc giao thức kết thúc rõ.
11. **Có lock khác bị giữ khi wait không?** `wait()` chỉ nhả đúng monitor của nó.
12. **Có thể dùng primitive cấp cao?** `BlockingQueue` cho dữ liệu, `CountDownLatch` cho tín hiệu một lần, `Semaphore` cho permits, `Phaser` cho pha xử lý.
13. **Đã kiểm tra liveness?** Đúng invariant nhưng thread chờ mãi cũng có thể là lỗi thiết kế.
14. **Đã kiểm tra logic khi có exception?** Nhả lock không có nghĩa rollback.
15. **Đã dùng test điều phối thay vì sleep để tái hiện?** Latch/barrier giúp ép một interleaving; stress test bổ sung nhưng không chứng minh vắng race.

## 17. Câu hỏi tự kiểm tra

1. Vì sao sau `notifyAll()` không thể dùng `if` rồi mặc nhiên tiếp tục? **Vì thread khác có thể lấy tài nguyên trước, predicate có thể sai và có spurious wakeup.**
2. Nếu chỉ một consumer đang chờ, `while` có còn cần không? **Có**, vì spurious wakeup và predicate vẫn có thể thay đổi.
3. `Object.wait()` có nhả mọi lock đang giữ không? **Không**, chỉ monitor của object gọi wait.
4. `Thread.sleep(100)` bên trong synchronized có giúp producer vào monitor không? **Không**, sleep giữ monitor.
5. Nếu producer notify khi consumer chưa bắt đầu chờ, chuyện gì xảy ra với giao thức đúng? **Consumer kiểm tra state, thấy predicate đúng thì không wait.**
6. Tại sao `volatile ready` không tự ngăn missed notification khi check và wait tách rời? **Volatile không khiến hai bước đó nguyên tử trong một monitor protocol.**
7. Hai consumer được notifyAll với một item, tối đa bao nhiêu người lấy thành công? **Một**. Người kia phải check lại rồi đợi hoặc thoát nếu closed.
8. Nếu code dùng while mà vẫn chờ mãi khi không còn producer, đó có phải lỗi while không? **Không; thiếu giao thức kết thúc/timeout/cancel.**
9. Điều kiện nào để gọi `Condition.await()` hợp lệ? **Thread giữ lock gắn với Condition và xử lý interruption.**
10. Sau khi `Condition.await()` trả về, có được bỏ qua predicate không? **Không**, phải dùng while.
11. `notify()` và `notifyAll()` khác nhau thế nào? **Notify chọn một waiter; notifyAll đánh thức tất cả waiter trong wait set, không bảo đảm thứ tự chạy.**
12. Tại sao một timed wait trong vòng while không nên luôn dùng lại 1 giây? **Mỗi wakeup làm tổng thời gian tăng vượt deadline mong muốn.**
13. Khi `InterruptedException` xuất hiện, có thể tiếp tục dùng tài nguyên chờ được không? **Không tự động; interruption là đường hủy, không chứng minh điều kiện đúng.**
14. Vì sao gọi `wait()` giữa hai bước cập nhật state liên quan có thể sai invariant? **Wait nhả monitor, cho thread khác nhìn state trung gian.**
15. Có nên dùng `if (!queue.isEmpty()) queue.take()` để tránh block? **Không, queue có thể trống sau lần check; dùng `poll()` nếu muốn không chờ.**
16. Trong thí nghiệm `IfWaitBugDemo`, vì sao in false là hợp lệ dù đã nhận notify? **Thông báo được phát nhưng ready không đổi; if không kiểm tra lại.**
17. Trong thí nghiệm `TwoConsumersIfDemo`, vì sao một lần remove thất bại? **Cả hai waiter được đánh thức nhưng chỉ có một item; waiter thứ hai không kiểm tra lại.**
18. Điều gì quan trọng hơn việc quan sát `Thread.State.WAITING`? **Trạng thái nghiệp vụ và predicate dưới giao thức đồng bộ đúng.**

## Kết luận

**Một thread thức dậy không có nghĩa điều kiện đã sẵn sàng.** `wait()/await()` có thể trở về vì spurious wakeup, và ngay cả với notification thực, thread khác có thể tiêu thụ tài nguyên trước waiter. Do vậy, condition waiting trong Java phải dựa trên **while kiểm tra predicate dưới cùng khóa**, không dựa vào `if` chỉ kiểm tra một lần.

Giao thức đúng: **giữ khóa → kiểm tra predicate → nếu sai thì wait/await và nhả khóa → lấy lại khóa → kiểm tra lại trong while → thực hiện thao tác cần thiết khi vẫn giữ khóa → cập nhật invariant và phát tín hiệu → nhả khóa**. Cần bổ sung timeout, interruption và shutdown để bảo đảm tiến triển; ưu tiên primitive cấp cao như `BlockingQueue` khi không cần tự xây monitor protocol.

## Tài liệu tham khảo Java SE 17

- [java.lang.Object — wait, notify, notifyAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): monitor ownership, wait set, spurious wakeup, reacquire.
- [java.util.concurrent.locks.Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): await, signal, signalAll và điều kiện chờ.
- [java.util.concurrent.locks.ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock, lockInterruptibly, unlock.
- [java.util.concurrent.BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): take, poll và timeout.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before và Java Memory Model.
