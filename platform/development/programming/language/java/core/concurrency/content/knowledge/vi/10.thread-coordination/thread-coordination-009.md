# Missed signal và lost notification: nguyên nhân trong Java Concurrency

Khi hai thread phối hợp, một bên phát tín hiệu “đã có dữ liệu” hoặc “điều kiện đã đúng”, bên còn lại chờ để tiếp tục. Lỗi **missed signal / lost notification** xảy ra khi thread chờ không nhận được thông báo cần thiết, có thể chờ mãi dù sự kiện mà nó quan tâm đã xảy ra. Với `Object.wait()/notify()/notifyAll()`, thông báo không phải một message được JVM lưu lại để phát cho thread tham gia sau đó.

Điểm cốt lõi của bài học không phải “gọi `notify` nhiều lần hơn” mà là **xây dựng giao thức trạng thái**: có một *predicate* mô tả điều kiện thật, kiểm tra nó và chuyển sang chờ **dưới cùng một monitor**, thay đổi predicate rồi phát tín hiệu theo cùng monitor, và luôn kiểm tra lại khi thức dậy. Nếu bài toán có primitive cấp cao phù hợp như `CountDownLatch`, `Semaphore`, `BlockingQueue`, `Future`, hãy ưu tiên hợp đồng rõ hơn thay vì tự viết wait/notify.

Bài này thuộc **Phối hợp luồng của Java Concurrency nói chung**, không bàn đến cơ chế riêng của Spring.

## 1. Phân biệt “sự kiện”, “trạng thái” và “thông báo”

Giả sử một consumer cần đợi tới khi producer tạo xong kết quả. Ba khái niệm khác nhau:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Trạng thái nghiệp vụ** | `ready == true`; queue không rỗng; `remaining == 0` | Sự thật mà chương trình cần kiểm tra. |
| **Predicate (điều kiện chờ)** | `ready`; `!queue.isEmpty()` | Khi predicate đúng, thread có thể tiếp tục. |
| **Thông báo** | `notify()`, `notifyAll()`, `Condition.signal()` | Gợi ý cho thread đang chờ thức dậy để kiểm tra trạng thái lại. |

`notify()` **không tự ghi** vào trạng thái `ready` và không tạo hàng đợi thông báo. `notifyAll()` cũng không biến thông báo thành “permit” được để dành cho thread sẽ gọi `wait()` trong tương lai.

Một giao thức đúng lưu **sự thật cần nhớ** trong state:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Consumer đọc predicate dưới cùng lock:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // Điều kiện ready đã đúng tại thời điểm sở hữu lock.
}
~~~

Hai khối trên là **mảnh mã minh họa**, giả định `lock` và `ready` đã khai báo; method chờ phải xử lý hoặc khai báo `InterruptedException`. Đây là mẫu *guarded block* chuẩn.

## 2. Cơ chế của Object.wait/notify

Với intrinsic monitor, Java có *wait set* gắn với một object. Những hành động quan trọng:

1. Thread phải **đang sở hữu monitor** của object khi gọi `wait()`, `notify()` hoặc `notifyAll()` trên object đó; nếu không, JVM ném `IllegalMonitorStateException`.
2. Gọi `wait()` khiến thread vào wait set, **nhả monitor của chính object đó**, rồi chờ notification, interruption, timeout (nếu có) hoặc spurious wakeup.
3. Trước khi `wait()` trả về hoặc ném `InterruptedException`, thread phải **lấy lại monitor** đó. Nó không thể chạy tiếp trong critical section ngay khi mới được notify nếu holder chưa nhả khóa.
4. `notify()` chọn **một thread** đang ở wait set của object, nếu có; không có bảo đảm nó chọn waiter “đúng mục đích”.
5. `notifyAll()` đánh thức **tất cả thread** hiện đang chờ trong wait set; chúng lần lượt cạnh tranh để sở hữu monitor sau khi monitor được giải phóng.
6. Khi **không có waiter** trong wait set tại thời điểm notify, thông báo không được tích lũy để thread đến sau sử dụng.
7. Spurious wakeup có thể xảy ra, nên việc một lần `wait()` trả về **không chứng minh** predicate đã đúng.

Mô tả “đánh thức” không có nghĩa waiter chạy ngay. `notify` chỉ thay đổi khả năng tiếp tục chờ monitor; thread gọi vẫn có thể sở hữu monitor cho đến khi thoát `synchronized`. Và `wait()` chỉ nhả **monitor mà nó đang wait**, không tự nhả những monitor khác đang giữ.

### 2.1 Không nhầm với Thread.sleep

- `Thread.sleep(100)`: tạm dừng thread một thời gian nhưng **không nhả monitor** đang giữ và không chờ sự kiện nghiệp vụ.
- `Object.wait(100)`: phải đang giữ đúng monitor; tạm nhả monitor đó trong khi chờ. Nó có thể trả về vì timeout, notification hoặc spurious wakeup.
- `Thread.join()`: chờ **vòng đời thread cụ thể kết thúc**, không phải chờ một predicate tự do.
- `LockSupport.park()`: cơ chế permit cấp thấp khác, có thể nhớ tối đa một permit trong giao thức park/unpark; không đồng nhất với Object.notify.

## 3. Lost notification khi notify xảy ra trước wait

Xét thời điểm:

~~~text
Producer                         Consumer
--------                         --------
synchronized(lock) {
    notifyAll()   // Chưa ai wait
}
                                 synchronized(lock) {
                                     wait() // Bắt đầu chờ sau thông báo
                                 }
                                 Không có tín hiệu mới => có thể chờ mãi.
~~~

Thông báo trước `wait()` **không được lưu lại**. Nếu không có predicate state, consumer không có cách nào biết sự kiện đã xảy ra.

### 3.1 Ví dụ Java 17+ tái hiện khoảng hở

Tạo `EarlyNotifyDemo.java`:

~~~java
public final class EarlyNotifyDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        synchronized (lock) {
            lock.notifyAll(); // Chưa có waiter; không được lưu lại.
        }
        System.out.println("Notified before wait");

        synchronized (lock) {
            lock.wait(50); // Timed wait để demo không bị treo vô hạn.
        }
        System.out.println("Wait returned; notification was not stored");
    }
}
~~~

Biên dịch và chạy JDK 17+:

~~~bash
javac EarlyNotifyDemo.java
java EarlyNotifyDemo
~~~

Stdout (không có interruption bên ngoài):

~~~text
Notified before wait
Wait returned; notification was not stored
~~~

Dòng cuối **không** khẳng định `wait(50)` nhất thiết đã ngủ đúng 50 ms: lời gọi có thể kết thúc do timeout hoặc spurious wakeup, và scheduling cũng ảnh hưởng thời gian thực. Dữ liệu chắc chắn của demo là `notifyAll` xảy ra khi chưa có waiter; không tồn tại notification được lưu sẵn cho `wait` về sau. `wait(50)` chỉ giúp chương trình ví dụ kết thúc được, **không sửa giao thức sai**.

### 3.2 Điều gì không giải quyết được?

- Thay `notify()` bằng `notifyAll()` **không** lưu thông báo khi không có waiter.
- Gọi `Thread.sleep(200)` trước khi notify để “đợi consumer kịp chạy” chỉ làm lỗi ít tái hiện hơn; scheduler không đưa ra bảo đảm.
- Dùng `volatile boolean ready` nhưng vẫn gọi `wait()` vô điều kiện không sửa lỗi; waiter phải **kiểm tra ready trước khi chờ**, và quan hệ check→wait phải đúng.
- Đợi một lần notify mà không có state không phân biệt được “chưa từng có sự kiện”, “đã xảy ra sớm” và “có spurious wakeup”.

## 4. Missed signal do check rồi wait không nguyên tử

Một kiểu lỗi khác phát sinh khi consumer kiểm tra điều kiện **ngoài monitor** rồi mới vào monitor để wait:

~~~java
if (!ready) {
    synchronized (lock) {
        lock.wait();
    }
}
~~~

Đây là mảnh **sai**, chưa phải chương trình độc lập. `ready` có thể là volatile và vẫn có race logic:

~~~text
Consumer                         Producer
--------                         --------
if (!ready) => true
                                 synchronized(lock) {
                                     ready = true
                                     notifyAll()     // Không ai đang wait
                                 }
synchronized(lock) {
    wait()  // Bắt đầu đợi mặc dù ready đã true
}
~~~

Không nhất thiết là lỗi visibility: consumer có thể đã đọc `ready == false` **đúng ở thời điểm kiểm tra**. Lỗi là khoảng hở thời gian giữa **check** và **đăng ký chờ**; producer có thể phát tín hiệu trong khoảng đó.

Ngay cả đặt check trong một khối `synchronized` **riêng**, rồi ra khỏi lock và vào lại để wait, vẫn có khoảng hở:

~~~java
boolean shouldWait;
synchronized (lock) {
    shouldWait = !ready;
}
if (shouldWait) {
    synchronized (lock) {
        lock.wait();
    }
}
~~~

Code sai vì hai lần lấy lock **không** tạo một thao tác check-and-wait. Producer có thể thay đổi predicate giữa hai critical section.

### 4.1 Vì sao một khối synchronized giải quyết race?

Mẫu đúng:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Khi consumer đang giữ `lock` để kiểm tra `ready`, producer không thể đồng thời vào `synchronized(lock)` để thay `ready`. Nếu consumer thấy false, nó gọi `wait()`; việc nhả monitor và chuyển vào trạng thái wait **được phối hợp nguyên tử theo hợp đồng monitor** đối với producer muốn lấy lock ấy. Producer chỉ có thể lấy lock, ghi ready và notify sau khi consumer đã sẵn sàng chờ, hoặc producer đã ghi ready trước khi consumer lấy lock (lúc đó consumer thấy true và **không wait**).

Đây là cách loại bỏ cửa sổ **check → subscribe** của giao thức. Không cần đoán consumer chạy nhanh hơn producer.

## 5. Quy tắc protected predicate: trạng thái và wait cùng một lock

Một giao thức có thể chứng minh đúng có ba quy tắc:

1. **Định nghĩa predicate rõ ràng:** chẳng hạn `ready == true`, `queue.size() > 0` hoặc `remaining == 0`.
2. **Mọi lần kiểm tra/đổi predicate đều dưới cùng monitor:** cùng object lock, không chỉ cùng tên biến; tránh writer cập nhật không đồng bộ.
3. **Notify sau khi thay state:** cập nhật predicate và gọi `notifyAll()` trong cùng critical section; waiter dùng `while (!predicate) wait()`.

Writer:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Waiter:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Cặp này xử lý cả hai trường hợp:

- **Signal sớm:** producer đặt ready=true trước, consumer lấy lock và không vào wait.
- **Waiter sớm:** consumer kiểm tra false, nhả lock qua wait, producer vào đổi ready và notify; consumer thức dậy, reacquire lock, kiểm tra lại true.

### 5.1 Vì sao dùng while, không dùng if?

Lỗi:

~~~java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useResource();
}
~~~

Đây là mảnh mã sai, giả định `useResource()` cần ready true. `wait()` có thể trả về do **spurious wakeup**, hoặc bị đánh thức bởi một notification cho điều kiện khác, hoặc nhiều waiter thức dậy và một waiter khác đã tiêu thụ tài nguyên trước khi waiter này lấy được monitor. Khi đó ready có thể vẫn false.

Dùng `while` luôn kiểm tra lại **predicate nghiệp vụ**, không coi notification là lời khẳng định điều kiện đã đúng.

## 6. Ví dụ Java 17+: guarded block xử lý cả signal sớm và waiter sớm

Tạo `GuardedSignalDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class GuardedSignalDemo {
    private static final class Gate {
        private final Object lock = new Object();
        private boolean open;

        void open() {
            synchronized (lock) {
                open = true;
                lock.notifyAll();
            }
        }

        void awaitOpen(CountDownLatch approachingWait)
                throws InterruptedException {
            synchronized (lock) {
                while (!open) {
                    if (approachingWait != null) {
                        approachingWait.countDown();
                    }
                    lock.wait();
                }
            }
        }

        boolean isOpen() {
            synchronized (lock) {
                return open;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // Trường hợp 1: signal trước khi có waiter.
        Gate early = new Gate();
        early.open();
        early.awaitOpen(null);
        System.out.println("Early signal observed: " + early.isOpen());

        // Trường hợp 2: waiter đến trước signal.
        Gate late = new Gate();
        CountDownLatch approachingWait = new CountDownLatch(1);

        Thread waiter = new Thread(() -> {
            try {
                late.awaitOpen(approachingWait);
                System.out.println("Late signal observed: " + late.isOpen());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "waiter");

        waiter.start();
        approachingWait.await();
        late.open();
        waiter.join();
        System.out.println("Done");
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac GuardedSignalDemo.java
java GuardedSignalDemo
~~~

Stdout trong lần chạy bình thường, không có external interruption:

~~~text
Early signal observed: true
Late signal observed: true
Done
~~~

**Giải thích từng điểm đồng bộ:**

- `Gate.open()` lưu state `open = true` **trước** notification, dưới cùng monitor.
- `awaitOpen` dùng `while (!open)` và `wait()` dưới monitor đó.
- Với early signal, waiter đọc `open == true` và **không cần chờ**. Điều được nhớ là state, không phải notify.
- Với late signal, waiter gọi `approachingWait.countDown()` khi đang giữ monitor ngay trước `wait()`. Main đợi latch, rồi gọi `late.open()`. Dù main có tranh monitor trước hay sau waiter chuyển sang wait, không mất sự kiện: waiter vẫn giữ monitor đến lúc gọi `wait()` và sau đó mới nhả monitor cho producer.
- `wait()` nhả monitor, cho `open()` cập nhật state. Khi waiter được đánh thức, nó lấy lại monitor, kiểm tra predicate và in kết quả.
- `waiter.join()` giúp main đợi worker hoàn tất trước khi in Done. Không cần `sleep()` hoặc vòng spin để ước lượng thứ tự.

Lưu ý: `approachingWait` là thiết bị điều phối của **demo**, không phải thành phần bắt buộc trong guarded block thực tế. Một `Gate` dùng lâu dài cần thêm quy tắc reset/đóng hoặc cancellation nếu API yêu cầu. Vì state chỉ chuyển false→true một lần nên ví dụ này là **one-shot signal**.

## 7. Tại sao notifyAll thường an toàn hơn notify khi nhiều predicate?

`Object.notify()` không nhận tham số “đánh thức thread đang chờ notEmpty”. Nó chọn **một waiter bất kỳ** trong wait set của monitor. Nếu nhiều loại waiter có predicate khác nhau, thông báo có thể đánh thức **đúng monitor nhưng sai nhóm**.

Ví dụ bounded buffer có hai điều kiện:

- Producer đợi `notFull` để còn chỗ đặt phần tử.
- Consumer đợi `notEmpty` để có phần tử lấy ra.

Nếu hai loại waiter cùng `wait()` trên một monitor, `notify()` có thể chọn thread mà predicate vẫn false. Thread ấy thức dậy, kiểm tra lại và tiếp tục chờ. Trong một vài lịch xen kẽ, thread cần được đánh thức không nhận thêm notification nào, gây **liveness failure** dù trạng thái đã cho phép tiến triển.

`notifyAll()` đánh thức tất cả waiter, mỗi thread tự kiểm tra lại predicate. Đây thường là lựa chọn **dễ chứng minh đúng hơn** khi nhiều predicate/không kiểm soát chặt số waiter. Đánh đổi là **thundering herd**: nhiều thread thức dậy, tranh lại monitor, rồi đa số lại wait, tăng scheduling/contending overhead.

Khi chỉ có một predicate, số waiter và giao thức được kiểm soát nghiêm ngặt, `notify()` có thể đủ. Nhưng phải **chứng minh** rằng một waiter được chọn bất kỳ đều có thể tiến triển theo protocol, không chỉ hy vọng nó là người mình muốn.

### 7.1 Condition phân chia wait set

`ReentrantLock.newCondition()` cho phép tạo các nhóm chờ riêng, ví dụ `notEmpty` và `notFull`. Khi producer put item, nó có thể `notEmpty.signal()`, tránh đánh thức producer chờ chỗ trống. Tuy nhiên Condition vẫn **không tích lũy tín hiệu tự động** cho waiter đến sau; predicate vẫn là nguồn sự thật.

## 8. ReentrantLock và Condition: cùng lỗi nếu check ngoài lock

Protocol tương ứng với `Condition`:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
~~~

Writer:

~~~java
lock.lock();
try {
    ready = true;
    condition.signalAll();
} finally {
    lock.unlock();
}
~~~

Đây là **mảnh mã minh họa**, giả định `lock` là `ReentrantLock`, `condition = lock.newCondition()` và `ready` được bảo vệ bởi lock. Method chờ xử lý `InterruptedException`.

`Condition.await()` có những điểm tương ứng `Object.wait()`:

- Caller phải đang sở hữu lock liên kết với Condition.
- Await nhả lock trong lúc chờ, rồi reacquire trước khi trả về.
- Có thể trả về do signal, spurious wakeup hoặc bị interrupt; vẫn dùng `while`.
- `signal()` không lưu token/permit cho thread chưa await.
- `signalAll()` đánh thức tất cả waiter của **Condition cụ thể đó**, không phải mọi Condition thuộc cùng ReentrantLock.

Đừng viết:

~~~java
if (!ready) {              // Đọc ở ngoài lock.
    lock.lock();
    try {
        condition.await(); // Có thể chờ sau khi signal đã xảy ra.
    } finally {
        lock.unlock();
    }
}
~~~

Câu lệnh sai trên tạo cùng cửa sổ lost signal như Object.wait; việc chuyển sang `ReentrantLock` không tự sửa **giao thức**.

## 9. Ví dụ Java 17+: Condition chờ một predicate

Tạo tệp `ConditionSignalDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class ConditionSignalDemo {
    private static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition opened = lock.newCondition();
        private boolean isOpen;

        void open() {
            lock.lock();
            try {
                isOpen = true;
                opened.signalAll();
            } finally {
                lock.unlock();
            }
        }

        void awaitOpen(CountDownLatch approachingWait)
                throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!isOpen) {
                    approachingWait.countDown();
                    opened.await();
                }
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        CountDownLatch approachingWait = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            try {
                gate.awaitOpen(approachingWait);
                System.out.println("Condition satisfied");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        approachingWait.await();
        gate.open();
        consumer.join();
        System.out.println("Done");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConditionSignalDemo.java
java ConditionSignalDemo
~~~

Stdout trong lần chạy bình thường:

~~~text
Condition satisfied
Done
~~~

Ở đây `CountDownLatch` giúp main biết consumer đã đến vùng kiểm tra điều kiện. Main có thể được schedule trước khi consumer thực sự vào `await()` nhưng vẫn không thể cập nhật `isOpen` khi consumer còn giữ lock. Việc `await()` nhả lock và chuyển sang chờ được phối hợp với signaler lấy lock nên không có check→wait gap.

Khác với intrinsic monitor, `ReentrantLock.lockInterruptibly()` cho phép hủy một thread đang chờ acquire lock bằng interruption. Điều này hữu ích khi task có cancellation contract rõ ràng; nó không loại bỏ nhu cầu kiểm tra predicate bằng while.

## 10. CountDownLatch: trạng thái completion được giữ lại

Khi yêu cầu chỉ là “đợi sự kiện đã hoàn tất một lần”, `CountDownLatch` thường đơn giản và ít lỗi hơn wait/notify.

~~~java
CountDownLatch done = new CountDownLatch(1);

// Producer, có thể gọi trước consumer:
done.countDown();

// Consumer, kể cả khi đến sau:
done.await();
~~~

Đây là mảnh code minh họa. `countDown()` chuyển bộ đếm từ 1 về 0, **trạng thái 0 được lưu lại**. Mọi lần `await()` sau đó trả về ngay nếu bộ đếm đã bằng 0; không mất tín hiệu khi consumer đến muộn.

Đặc điểm:

- Latch là **one-shot**, không reset. Khi cần chu kỳ mới, tạo latch mới hoặc dùng primitive cho nhiều vòng.
- `await()` có thể bị interrupt; overload timeout trả boolean.
- Hành động của producer trước `countDown()` happens-before hành động của thread khác sau `await()` hoàn tất thành công theo memory-consistency effects.
- Latch báo đủ tín hiệu, nhưng **không tự chứa giá trị kết quả hay exception** của task.
- Với nhiều producer, count phải phản ánh đúng số mốc hoàn tất; tín hiệu thiếu khiến waiter có thể đợi mãi.

## 11. Semaphore: permit được giữ lại cho acquire sau

`Semaphore` quản lý số permit. Khi producer gọi `release()` lúc chưa có consumer, số permit tăng (trong giới hạn số nguyên theo hợp đồng), nên consumer `acquire()` đến sau có thể sử dụng permit đó.

~~~java
Semaphore permit = new Semaphore(0);
permit.release();   // Đến trước acquire.
permit.acquire();   // Lấy permit đã được giữ.
~~~

Đây là mảnh code minh họa, yêu cầu import `java.util.concurrent.Semaphore` và xử lý `InterruptedException`.

Khác biệt:

- `Object.notify` không tích lũy notification.
- `Semaphore.release` **tăng số permit**, permit được giữ cho lần acquire sau.
- Permit là **quyền/số lượng**, không phải tự động một payload hay event identity. Nếu có 10 kết quả khác nhau, cần cơ chế dữ liệu/queue tương ứng.
- Khi dùng semaphore để giới hạn concurrency, cần release đúng số permit đã acquire. Nếu release thừa, có thể mở rộng số người truy cập ngoài giới hạn mong muốn.
- Fairness option của semaphore không thay thế deadline/cancellation và không làm business state atomic.

Với one-shot completion, dùng latch thường diễn đạt ý nghĩa rõ hơn. Với đếm tài nguyên hoặc producer/consumer dạng permit, semaphore có thể phù hợp.

## 12. BlockingQueue: giữ cả dữ liệu lẫn điều kiện “có phần tử”

Một `BlockingQueue` thường là lựa chọn tốt hơn `wait()/notify()` tự viết cho producer–consumer:

~~~java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(10);

// Producer:
queue.put("message");

// Consumer:
String message = queue.take();
~~~

Đây là mảnh code minh họa, cần import `BlockingQueue`, `ArrayBlockingQueue` và xử lý `InterruptedException`. Nếu producer put trước consumer take, phần tử được giữ trong queue, không bị “mất thông báo”; consumer lấy dữ liệu thật.

Khác biệt với `notify`: queue lưu **phần tử**, không chỉ cố đánh thức thread. Nó còn định nghĩa API blocking, timeout, capacity, rejection hoặc backpressure tùy implementation.

Tuy nhiên cần chú ý:

- Queue không tự bảo đảm một consumer duy nhất nhận mọi message; nhiều consumer có thể chia việc.
- Queue có thể đầy; `put()` sẽ đợi nếu không còn chỗ, `offer(timeout)` cho phép deadline.
- Nếu producer sửa object mutable **sau khi put**, consumer có thể đua với lần sửa; hãy publish immutable message/snapshot hoặc có protocol riêng.
- Queue không tự giải quyết shutdown/cancellation; có thể dùng interruption, sentinel/poison pill theo hợp đồng hoặc chính sách lifecycle rõ ràng.
- Có memory-consistency effects cho việc chuyển giao phần tử theo hợp đồng concurrent collection/queue.

## 13. Ví dụ Java 17+: các primitive nhớ trạng thái hoặc dữ liệu

Tạo `StoredSignalDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;

public final class StoredSignalDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch done = new CountDownLatch(1);
        done.countDown();    // Signal xảy ra trước await.
        done.await();
        System.out.println("Latch: completed");

        Semaphore permits = new Semaphore(0);
        permits.release();   // Permit xảy ra trước acquire.
        permits.acquire();
        System.out.println("Semaphore: acquired");

        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        queue.put(42);       // Data đến trước take.
        System.out.println("Queue: " + queue.take());
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac StoredSignalDemo.java
java StoredSignalDemo
~~~

Stdout:

~~~text
Latch: completed
Semaphore: acquired
Queue: 42
~~~

Ba primitive lưu lại **ba loại thông tin khác nhau**: latch giữ trạng thái bộ đếm hoàn tất, semaphore giữ permit, queue giữ phần tử dữ liệu. Vì thế đều xử lý đúng tình huống producer tới trước consumer, nhưng không thể thay thế nhau một cách cơ học nếu semantics nghiệp vụ khác nhau.

## 14. Future và CompletableFuture: chờ completion có kết quả

Nếu signal thực chất nghĩa là “một tác vụ đã tính xong hoặc thất bại”, `Future` thường đúng ngữ nghĩa hơn một biến `ready`:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<Integer> answer = executor.submit(() -> 6 * 7);
    System.out.println(answer.get());
} finally {
    executor.shutdown();
}
~~~

Đây là mảnh code minh họa, cần import `ExecutorService`, `Executors`, `Future` và method xử lý các exception liên quan. `Future.get()` chờ completion, trả kết quả khi thành công, hoặc báo lỗi/huỷ bằng exception thích hợp; task có thể hoàn thành **trước** thời điểm caller gọi get. Completion được lưu trong Future, không bị mất như một notification rỗng.

`CompletableFuture` còn cung cấp combinator như `thenApply`, `thenCompose`, `allOf`. `CompletableFuture.join()` đợi completion và có unchecked `CompletionException` đối với lỗi thay vì checked `ExecutionException` của `Future.get()`. Đừng nhầm `CompletableFuture.join()` với `Thread.join()`; cái sau chờ vòng đời thread.

Trong hệ thống nhiều task, sử dụng result-bearing primitive giúp tránh phải tự phối hợp một cờ ready, một nơi lưu kết quả và một nơi lưu exception rời rạc.

## 15. Timeout, interruption và spurious wakeup

Một chờ đúng về mặt notification vẫn có thể chờ vô hạn nếu producer chết, bỏ quên signal hoặc điều kiện không bao giờ thành sự thật. Hãy thiết kế **đường hủy và deadline** theo yêu cầu.

### 15.1 Timed wait cũng phải kiểm tra predicate

Sai:

~~~java
synchronized (lock) {
    lock.wait(1_000);
    if (!ready) {
        // Không có bảo đảm rõ tại sao wait trả về.
    }
}
~~~

Đây là mảnh mã minh họa. Một lần timed wait không đủ cho protocol vì `wait` có thể trả về do notification không liên quan/spurious wakeup trước deadline. Phải dùng vòng kiểm tra predicate và tính **thời gian còn lại**, nếu không mỗi lần thức dậy rồi wait lại đủ 1.000 ms có thể kéo dài deadline ngoài dự kiến.

Với `Condition`, `awaitNanos` trả khoảng thời gian còn lại theo hợp đồng và phù hợp vòng lặp kiểm tra:

~~~java
boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0L) {
                return false;
            }
            remaining = condition.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}
~~~

Đây là mảnh method minh họa: `lock` là `ReentrantLock`, `condition` là Condition liên kết cùng lock, `ready` là predicate. Khi `true` được trả, predicate đúng trong lúc thread đang giữ lock. Khi `false`, deadline đã hết mà predicate chưa được quan sát đúng theo protocol; producer có thể làm ready=true **ngay sau khi method nhả lock**, nên caller phải xử lý race thời điểm kết thúc theo hợp đồng.

### 15.2 InterruptedException không phải notification

`wait()`, `Condition.await()`, `CountDownLatch.await()` và `BlockingQueue.take()` có thể ném `InterruptedException`. Interruption **không** có nghĩa predicate đã đúng hoặc job đã hoàn thành.

Nếu method có thể truyền exception, thường để nó propagate. Trong `Runnable.run()` không khai báo checked exception, có thể xử lý bằng:

~~~java
try {
    awaitWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là mảnh trong method `void run()`, giả định `awaitWork()` là method có thể throw. Việc gọi `Thread.currentThread().interrupt()` khôi phục cờ bị xóa khi `InterruptedException` được ném ở các blocking API thông thường; sau đó thoát hoặc cleanup phù hợp.

**Không** bắt exception rồi gọi `wait()` lại vô hạn và bỏ qua cancellation. Nếu thread đang giữ resource/lock khác, cần thiết kế cleanup để không giữ trạng thái dở dang.

### 15.3 Spurious wakeup

JMM và API cho phép `wait()`/`Condition.await()` thức dậy mà không có notification đúng điều kiện. Đây là lý do **bắt buộc kiểm tra predicate bằng while**, không phải một hiện tượng chỉ có ở một CPU hiếm gặp. Trong kiểm thử, đừng assert “mọi lần wait trả về đều có notify trước đó” như một luật Java.

## 16. Visibility và happens-before: notify không tự thay predicate

Một protocol phối hợp đúng cần cả **atomic handoff** của check→wait và **memory visibility** cho state được công bố.

Khi writer:

~~~java
synchronized (lock) {
    result = 42;
    ready = true;
    lock.notifyAll();
}
~~~

và reader:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    System.out.println(result);
}
~~~

thì cùng monitor tạo mutual exclusion, và một lần unlock của writer happens-before lần lock sau đó trên cùng monitor của reader. Nhờ đó reader thấy state đã publish theo giao thức, không cần làm tất cả field thành volatile.

`notifyAll` tự nó không biến mọi dữ liệu khác của ứng dụng thành thread-safe. Những truy cập không tuân thủ monitor protocol vẫn có thể race. Tương tự, một `volatile ready` chỉ hữu ích khi read/write được đặt đúng thứ tự; nó không bảo đảm các field khác giữ một invariant nhiều bước nguyên tử.

Với `CountDownLatch`, hành động trước `countDown()` happens-before những hành động sau `await()` thành công; với queue/future, hợp đồng memory-consistency của API xác định đường publish dữ liệu.

### 16.1 Cảnh báo “đồng bộ nhầm monitor”

Sai:

~~~java
synchronized (producerLock) {
    ready = true;
    producerLock.notifyAll();
}

// Consumer:
synchronized (consumerLock) {
    while (!ready) {
        consumerLock.wait();
    }
}
~~~

Đây là mảnh minh họa với **hai object lock khác nhau**. Producer notify trên `producerLock`, còn consumer wait trên `consumerLock`: chúng ở hai wait set khác nhau. Dù cả hai đều gọi synchronized và notify/wait đúng cách về mặt cú pháp, consumer vẫn có thể kẹt.

Trong một giao thức event đơn giản, giữ cùng một `lock` và cùng predicate state; đặt chúng dưới ownership của một object thay vì cho caller tự truyền lock tùy ý.

## 17. notify trước khi release lock có “báo sớm” không?

Một số người sửa bug bằng cách đưa `notify()` ra **ngoài synchronized**:

~~~java
synchronized (lock) {
    ready = true;
}
lock.notifyAll(); // IllegalMonitorStateException.
~~~

Đây là mã lỗi vì caller không còn sở hữu monitor của `lock`. `notify` phải gọi **bên trong** vùng synchronized của cùng object.

Gọi notify trước khi ra khỏi critical section là **bình thường**:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
    // Có thể làm nốt ít việc không blocking.
}
~~~

Waiter được notify nhưng sẽ chờ lấy lại monitor cho đến khi writer nhả. Điều này giúp writer có thể hoàn tất update invariant trước khi waiter đọc. Tuy nhiên đừng tiếp tục giữ lock quá lâu sau notify (I/O, callback, sleep), vì nó làm tăng latency của thread đang được đánh thức.

Nguyên tắc đúng là **cập nhật trạng thái và signal dưới lock, rồi nhả lock sớm**, không tách signal ra khỏi lock.

## 18. Lost notification trong producer-consumer và shutdown

Những lỗi signal thường trở nên phức tạp khi hệ thống có nhiều người sản xuất/tiêu thụ hoặc cần dừng.

### 18.1 Nhiều waiter tranh một phần tử

Khi producer đưa **một phần tử** vào buffer rồi notifyAll, nhiều consumer có thể thức dậy. Consumer đầu lấy item, consumer thứ hai đến sau thấy queue trống. Nếu dùng `if` thay `while`, consumer thứ hai có thể cố lấy từ queue trống hoặc trả dữ liệu sai. Vòng `while (empty) wait()` giải quyết điều kiện đã thay đổi trước khi waiter reacquire.

### 18.2 Shutdown cũng cần predicate

Giả sử consumer đợi “queue có phần tử”, trong khi producer đã dừng mãi mãi. Nếu không có predicate `closed` hoặc cơ chế interruption/sentinel, consumer có thể chờ vô hạn. Một pattern rõ ràng là:

~~~text
while queue empty AND not closed:
    await

if queue empty AND closed:
    exit
else:
    take item
~~~

Đây là **mã giả**, không phải Java độc lập. Khi đóng queue, update `closed=true` dưới cùng lock và `signalAll/notifyAll` để đánh thức những waiter đang chờ. Predicate của wait giờ là “queue có phần tử **hoặc** hệ thống đã đóng”. Thread đến sau shutdown cũng thấy `closed` được lưu và không chờ.

Nếu dùng `BlockingQueue`, cần định nghĩa cách kết thúc vì Java BlockingQueue thông thường không có operation `close()` chung cho mọi implementation; cân nhắc interruption, sentinel có hợp đồng, hoặc lifecycle controller riêng.

### 18.3 Các vòng sự kiện cần thế hệ (generation)

Một `boolean ready` chỉ phù hợp nếu trạng thái one-shot false→true. Khi producer có nhiều vòng “đã xong lần thứ N”, một cờ true không phân biệt các thế hệ. Dùng **sequence number/generation** hoặc primitive tương ứng như `Phaser`/`CyclicBarrier` khi bài toán yêu cầu phối hợp theo vòng.

Ví dụ thread consumer ghi nhận `lastSeenVersion`, rồi đợi cho đến khi `version > lastSeenVersion`. Producer tăng version dưới lock trước khi notifyAll; trạng thái version được lưu, nên notification sớm không làm mất thông tin “đã có một vòng mới”. Cần xử lý overflow và số thế hệ nếu thực sự dùng lâu dài.

## 19. Kiểm thử missed signal có tính quyết định

Lỗi lost notification thường “không xảy ra ở máy tôi” vì interleaving hiếm. Kiểm thử bằng `sleep()` có thể pass hàng nghìn lần rồi fail trên CI. Cách thử đáng tin hơn:

1. **Tạo lịch signal-sớm:** producer signal trước, rồi mới cho consumer bắt đầu đợi. Với API đúng, consumer phải nhận biết predicate đã đúng ngay, không block.
2. **Tạo lịch waiter-sớm:** consumer kiểm tra predicate dưới lock, sử dụng latch đánh dấu đã tới điểm wait, rồi producer signal. Đảm bảo completion xảy ra.
3. **Tạo contention:** nhiều consumer cùng chờ, một producer phát item; mọi consumer thức dậy phải kiểm tra lại predicate bằng while, không tiêu thụ trùng.
4. **Thử notification không liên quan:** nếu waiter thức dậy mà predicate vẫn false, phải quay lại chờ chứ không chạy tiếp.
5. **Thử interruption:** waiter rời blocking operation theo policy, không bỏ lock/state dở dang.
6. **Thử timeout:** khi không có producer, method không chờ vô hạn nếu contract có deadline; khi hết thời gian phải báo status rõ.
7. **Thử shutdown:** consumer đã chờ và consumer đến sau khi close đều phải được xử lý đúng.
8. **Thử nhiều vòng:** nếu protocol có generation, các thế hệ không bị bỏ sót theo contract (nếu được yêu cầu lưu từng event, dùng queue).
9. **Dọn test trong finally:** mở latch/cancel/interrupt đúng cách, join worker, tránh test treo và để thread không-daemon sống ngoài test.

### 19.1 Test đúng điều kiện, không test ngẫu nhiên thời gian

Đừng viết:

~~~java
Thread.sleep(20);
producer.signal();
Thread.sleep(20);
assertTrue(consumerCompleted);
~~~

Đây là mảnh lỗi minh họa; `Thread.sleep` không bảo đảm thread đã đến điểm `wait`. Thay vào đó, dùng `CountDownLatch` đánh dấu mốc đồng bộ, `Future.get(timeout)` để giới hạn thời gian test và assert predicate/kết quả.

Khi test cho thấy timeout, kiểm tra stack trace của waiter: thread `WAITING` trong `Object.wait()`, `Condition.await()` hay một blocking queue? Kiểm tra cùng lock hay sai lock, thứ tự update predicate, notification có phát trước wait không, có signal nhầm nhóm không, có thread khác tiêu thụ state trước không.

## 20. Phân biệt lost notification với deadlock và starvation

| Hiện tượng | Nguyên nhân cốt lõi | Dấu hiệu |
| --- | --- | --- |
| **Lost notification** | Event notify xảy ra khi không có waiter, hoặc check→wait gap để waiter bỏ lỡ signal. | Waiter ngủ dù predicate/sự kiện đã xảy ra; không có signal tiếp theo. |
| **Wrong waiter selection** | `notify` đánh thức waiter có predicate vẫn false. | Waiter thức rồi chờ lại; waiter phù hợp vẫn ngủ. |
| **Spurious wakeup** | Wait trả về mà không có event đáp ứng predicate. | Nếu dùng if thay while, code chạy sai. |
| **Deadlock** | Vòng phụ thuộc lock/điều kiện khiến các participant không tiến triển. | Thread A chờ B, B lại chờ A hoặc monitor tương ứng. |
| **Starvation** | Một thread không được phục vụ trong khi thread khác tiếp tục tiến triển. | Có hoạt động tổng thể nhưng waiter cụ thể không hoàn tất. |
| **Visibility bug** | Dữ liệu đọc/ghi thiếu quan hệ HB phù hợp. | Thread có thể không nhìn thấy cập nhật; thêm sleep/log thay đổi kết quả. |

Những lỗi có thể đi cùng nhau. Ví dụ writer notify trên monitor sai khiến waiter chờ mãi, hoặc thread giữ lock rồi `join()` worker cần lock ấy tạo deadlock dù notification protocol của một phần khác đúng.

Không kết luận “lost notification” chỉ vì thread dump cho thấy `WAITING`. Trạng thái đó có thể là trạng thái đúng khi predicate chưa thành. Cần đối chiếu *state, signal, monitor ownership, generation và đường đi của từng thread*.

## 21. Những lỗi phổ biến và cách sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `notifyAll` trước khi waiter tồn tại, không lưu state. | Waiter đến sau có thể chờ vô hạn. | Lưu predicate `ready`, hoặc dùng latch/semaphore/queue. |
| Kiểm tra `ready` ngoài lock rồi mới `wait()`. | Producer có thể signal giữa check và wait. | Check + wait trong **cùng synchronized block**. |
| Dùng `if (!ready) wait()`. | Spurious wakeup hoặc waiter khác tiêu thụ state. | Dùng `while (!ready) wait()`. |
| Producer sửa predicate ngoài lock nhưng notify trong lock. | Giao thức không có cùng ranh giới đồng bộ. | Update state và notify dưới cùng monitor. |
| Producer và consumer dùng hai object lock khác nhau. | Wait set không khớp, không đánh thức đúng waiter. | Dùng cùng monitor và một owner rõ. |
| Dùng `notify()` khi nhiều loại predicate cùng wait. | Đánh thức sai nhóm, liveness failure. | `notifyAll()` hoặc nhiều Condition. |
| Gọi `notify()` ngoài synchronized. | `IllegalMonitorStateException`. | Sở hữu đúng monitor lúc notify. |
| Sau notify vẫn giữ lock để I/O lâu. | Waiter đã thức nhưng không reacquire được. | Nhả lock sớm, I/O ngoài critical section. |
| Bắt `InterruptedException` rồi lặp lại wait không giới hạn. | Cancellation không có hiệu lực. | Propagate hoặc restore interrupt và thoát an toàn. |
| Dùng `wait(timeout)` một lần rồi coi predicate đúng. | Timeout/spurious wakeup có thể trả về không vì điều kiện. | Loop kiểm tra predicate và deadline. |
| Dùng boolean one-shot cho nhiều vòng sự kiện. | Không biết có generation mới. | Version/generation hoặc queue sự kiện. |
| Producer kết thúc mà không signal shutdown. | Consumer có thể đợi mãi. | Predicate closed/cancellation và notifyAll khi đóng. |
| Dùng `sleep()` thay bảo đảm handshake. | Race chỉ trở nên ngẫu nhiên hơn. | Dùng primitive đồng bộ đúng giao thức. |

## 22. Chọn primitive theo điều bạn thực sự cần nhớ

| Mục tiêu | Lựa chọn Java hợp lý | Tín hiệu đến trước waiter có còn được nhớ? |
| --- | --- | --- |
| Một thay đổi trạng thái đơn giản, predicate tự quản lý | `synchronized` + `while` + `wait/notifyAll` | Có, **nhờ predicate**, không phải do notify. |
| Chờ nhiều predicate trên cùng state có lock | `ReentrantLock` + nhiều `Condition` | Có, nếu **state** được cập nhật/kiểm tra đúng; signal tự nó không tích lũy. |
| Một lần hoàn tất (hoặc N mốc) | `CountDownLatch` | Có, count về 0 được giữ. |
| Đếm permit/quyền truy cập | `Semaphore` | Có, permit đã release có thể được acquire về sau. |
| Chuyển một message từ producer sang consumer | `BlockingQueue` | Có, item nằm trong queue cho tới khi được take, theo dung lượng/policy. |
| Nhận kết quả hoặc lỗi của task | `Future` / `CompletableFuture` | Có, completion/result/error được giữ. |
| Đợi vòng đời một `Thread` kết thúc | `Thread.join()` | Có, completion của thread được nhận biết qua join. |
| Phối hợp nhiều giai đoạn lặp | `Phaser` / `CyclicBarrier` hoặc generation protocol | Theo hợp đồng từng primitive; cần xử lý timeout/broken parties. |

Đừng chọn từ khóa `notifyAll` chỉ vì “cần báo tín hiệu”. Hãy chọn **loại state phải giữ lại**: boolean, count, permit, dữ liệu, kết quả hay thế hệ. Primitive càng gần bài toán thì số nhánh cạnh tranh cần tự chứng minh càng ít.

## 23. Câu hỏi tự kiểm tra

**1.** Producer gọi `notifyAll` khi chưa có waiter. Consumer gọi `wait` sau đó. Consumer có tự nhận notification cũ không?  
**Không.** Notification không được xếp hàng. Consumer chỉ có thể tránh chờ nếu predicate state cho biết công việc đã xong.

**2.** Vì sao `volatile ready` vẫn có thể lost notification nếu consumer đọc ready rồi mới vào synchronized để wait?  
**Vì** producer có thể chuyển ready và notify trong khoảng giữa hai bước. Đây là check→wait race, không chỉ visibility race.

**3.** Vì sao `while (!ready) lock.wait()` đúng hơn `if`?  
**Vì** wait có thể spurious wakeup, hoặc tình trạng đã thay đổi trước khi waiter lấy lại lock; cần kiểm tra predicate mỗi lần.

**4.** `Object.wait()` nhả mọi lock mà thread đang giữ không?  
**Không.** Nó nhả monitor của object được wait, không nhả những monitor khác.

**5.** `notifyAll()` có đảm bảo mọi waiter sẽ chạy ngay không?  
**Không.** Các waiter còn phải reacquire monitor; scheduler và trạng thái predicate quyết định tiến triển.

**6.** Vì sao cập nhật ready rồi notify phải ở cùng synchronized block?  
**Để** việc kiểm tra predicate và chuyển sang wait phối hợp đúng với lần thay state/notify của producer, đồng thời có memory visibility theo monitor.

**7.** Một consumer thức dậy khi buffer đã bị consumer khác lấy hết. Nó nên làm gì?  
**Kiểm tra lại predicate trong while** và chờ tiếp nếu buffer vẫn trống.

**8.** Khi nào `notify()` có rủi ro lớn hơn `notifyAll()`?  
**Khi** cùng wait set có nhiều waiter hoặc nhiều predicate; notify có thể chọn waiter không thể tiến triển.

**9.** `CountDownLatch.countDown()` đến trước `await()` có bị mất không?  
**Không.** Bộ đếm được giữ lại; await trả ngay khi count đã bằng 0.

**10.** `Semaphore.release()` và `Object.notify()` khác nhau ở điểm nào?  
**Release** tạo/tăng permit được giữ lại; **notify** chỉ đánh thức một waiter hiện đang chờ, không lưu event.

**11.** `Condition.signal()` có lưu thông báo cho thread gọi `await()` về sau không?  
**Không.** Vẫn cần predicate state và check/await dưới cùng lock.

**12.** Một lần `wait(1000)` trả về có đồng nghĩa ready đã true không?  
**Không.** Có thể do timeout, notification không liên quan hoặc spurious wakeup; phải kiểm tra ready dưới lock.

**13.** Nếu consumer chờ queue có item nhưng producer đã shutdown vĩnh viễn, cần thêm gì?  
**Một trạng thái closed/cancellation và tín hiệu đánh thức** để consumer không chờ mãi.

**14.** Tại sao log và sleep trong test có thể che giấu lost notification?  
**Vì** chúng thay đổi scheduling và thời gian interleaving; cần latch/barrier để buộc lịch thử cụ thể.

**15.** Cách nghĩ quan trọng nhất khi thiết kế đồng bộ tín hiệu?  
**Lưu sự thật vào state**, dùng một protocol check→wait nguyên tử, rồi xem notification chỉ là cơ chế đánh thức để kiểm tra state lại.

**Ghi nhớ:** Trong `Object.wait()/notify()`, **notification không phải message được lưu trữ**. Hai nguồn gây mất tín hiệu phổ biến nhất là **notify xảy ra trước wait** và **tách check predicate khỏi wait**. Chữa đúng bằng guarded block `synchronized(lock) { while (!predicate) lock.wait(); }`, cập nhật predicate và `notifyAll` dưới cùng monitor, xử lý spurious wakeup, interruption và shutdown. Khi có primitive cấp cao lưu đúng thứ cần nhớ, hãy ưu tiên `CountDownLatch`, `Semaphore`, `BlockingQueue` hoặc `Future` để giảm rủi ro giao thức.