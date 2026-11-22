# ReentrantLock: lock(), unlock() và finally trong Java

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Giải thích **java.util.concurrent.locks.ReentrantLock** và quan hệ giữa đối tượng khóa, thread sở hữu khóa, critical section và dữ liệu được bảo vệ.
- Viết đúng mẫu **lock.lock() → try → finally → lock.unlock()**, kể cả khi code trong critical section ném exception hoặc return sớm.
- Hiểu **reentrancy** (một thread có thể lấy lại khóa mình đang giữ), **hold count**, trạng thái owner và hậu quả khi gọi unlock() sai.
- Phân biệt **lock()**, **lockInterruptibly()**, **tryLock()** và **tryLock(timeout, unit)** theo khả năng chờ, ngắt và điều kiện nhả khóa.
- Nhận biết bảo đảm **mutual exclusion** và **happens-before** của Lock, giới hạn về fairness, và cách tránh deadlock do lock ordering.
- Nắm trường hợp **Condition.await()/signal()/signalAll()** phù hợp hơn vòng lặp sleep/yield hoặc tự triển khai chờ điều kiện.
- Chọn đúng giữa **synchronized** và ReentrantLock, giữ khóa ngắn và bảo vệ toàn bộ bất biến chia sẻ.

Phạm vi chỉ là **Java concurrency của JDK**. Những cơ chế riêng của Spring được học trong chương khác.

## 2. ReentrantLock là gì?

**ReentrantLock** là một lớp cụ thể của **java.util.concurrent.locks**, triển khai giao diện **Lock**. Nó cung cấp một khóa loại trừ lẫn nhau (mutual exclusion) có tính **reentrant** giống intrinsic monitor mà **synchronized** dùng, nhưng với API điều khiển khóa tường minh.

~~~java
import java.util.concurrent.locks.ReentrantLock;

// Đoạn mã minh họa trong một lớp/phương thức Java.
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    // Đọc/ghi dữ liệu dùng chung dưới cùng khóa.
} finally {
    lock.unlock();
}
~~~

Đây là đoạn minh họa cú pháp, không phải chương trình độc lập có main().

Khi một thread đã giữ ReentrantLock, các thread khác muốn lấy cùng đối tượng khóa sẽ phải chờ hoặc thất bại tùy phương thức sử dụng. Khác với **synchronized**, Java **không tự gọi unlock()** khi rời khỏi một khối mã bình thường, return hoặc ném exception. Vì vậy **finally** là yếu tố bảo toàn quyền sở hữu khóa.

Một số khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Lock object** | Đối tượng ReentrantLock dùng chung giữa mọi đoạn mã cần bảo vệ cùng bất biến |
| **Owner** | Thread hiện đang sở hữu khóa |
| **Critical section** | Đoạn đọc/ghi dữ liệu phải thực hiện khi owner nắm khóa |
| **Acquisition** | Lấy khóa thành công qua lock(), lockInterruptibly() hoặc tryLock() |
| **Release** | Gọi unlock() đúng số lần bởi **chính owner** |
| **Hold count** | Số mức khóa còn được thread hiện tại giữ do lấy khóa reentrant |
| **Waiter/contender** | Thread khác đang cố lấy khóa do owner hiện tại chưa nhả |

Tính an toàn phụ thuộc vào việc **tất cả đường truy cập có liên quan** dùng **cùng một đối tượng ReentrantLock**, hoặc một giao thức đồng bộ hóa khác có lập luận JMM thích hợp. Chỉ có biến tên lock trong mỗi thread chưa đủ: nếu các thread tự tạo **new ReentrantLock()** riêng thì không có mutual exclusion giữa chúng.

## 3. Mẫu bắt buộc: lock() rồi try/finally

Mẫu cơ bản đúng:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đây là mã minh họa; **lock** và **updateSharedState()** cần được định nghĩa ở lớp thực tế. Điểm đáng chú ý:

1. **lock.lock()** được gọi trước **try** và phải thành công thì thread mới được xem là owner.
2. Vừa lấy được khóa, đi vào **try** ngay để mọi đường thoát từ critical section đều tới **finally**.
3. Mọi thao tác cần bảo vệ nằm trong phạm vi try.
4. **finally** gọi unlock() đúng một lần tương ứng với lần lock() vừa lấy.
5. Nếu body return, break hoặc ném exception, **finally vẫn được thực thi** khi stack đi qua block đó; việc unlock không phụ thuộc đường thoát thông thường.
6. Nếu code trong finally có logic khác và bản thân nó ném exception trước khi unlock, khóa vẫn có thể bị giữ. Do đó nên để finally đơn giản, chỉ thực hiện thao tác giải phóng cần thiết.

**Vì sao try ở sau lock()?** Nếu một lần lấy khóa có khả năng thất bại mà chương trình vẫn gọi unlock(), thread không phải owner sẽ gặp **IllegalMonitorStateException**. Với lock() thông thường, lời gọi chờ đến khi lấy được khóa, nhưng đặt try **ngay sau** vẫn là mẫu chuẩn để không giải phóng khóa khi chưa sở hữu.

### Sai lầm 1: quên finally

~~~java
lock.lock();
updateSharedState(); // Nếu ném exception...
lock.unlock();        // ...câu này không chạy.
~~~

Đây là đoạn minh họa lỗi, không phải chương trình độc lập. Khóa có thể bị giữ mãi bởi thread đã gặp exception. Những thread khác cần khóa có thể chờ vô hạn, đặc biệt nếu thread owner vẫn còn sống. Nếu thread owner kết thúc sau exception, ReentrantLock **cũng không có cơ chế tự động unlock khi thread chết**; những thread đợi vẫn không thể nhờ vậy đi vào critical section.

### Sai lầm 2: unlock() khi chưa sở hữu

~~~java
// Anti-pattern nếu tryLock thất bại:
if (lock.tryLock()) {
    updateSharedState();
}
lock.unlock(); // Có thể ném IllegalMonitorStateException.
~~~

Nếu tryLock() trả false, caller không được cấp khóa. Nếu tryLock() thành công nhưng updateSharedState() ném exception, unlock bên ngoài cũng có thể bị bỏ qua.

Cách đúng:

~~~java
if (lock.tryLock()) {
    try {
        updateSharedState();
    } finally {
        lock.unlock();
    }
}
~~~

Chỉ nhả khóa khi acquisition thành công. Với **tryLock(timeout, unit)** và **lockInterruptibly()** cũng phải đặt finally trên **đường đi thực sự đã lấy được khóa**.

### Sai lầm 3: return sớm nhưng không nhả khóa

~~~java
lock.lock();
try {
    if (isRejected()) {
        return;
    }
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đây là mã minh họa bên trong một phương thức trả void; **isRejected()** là hàm giả định. Return bên trong try vẫn chạy finally trước khi method kết thúc. Vì thế cấu trúc try/finally an toàn hơn việc cố gắng nhớ gọi unlock ở từng nhánh if/else.

## 4. Ví dụ Java 17+: đếm chính xác bằng ReentrantLock

Tệp **ReentrantCounterDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantCounterDemo {
    static final class Counter {
        private final ReentrantLock lock = new ReentrantLock();
        private int value;

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int snapshot() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread a = new Thread(task, "worker-a");
        Thread b = new Thread(task, "worker-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("count = " + counter.snapshot());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ReentrantCounterDemo.java
java ReentrantCounterDemo
~~~

Stdout:

~~~text
count = 20000
~~~

**Lập luận đúng đắn:** cả hai thread chia sẻ cùng **Counter**, nên đều khóa **cùng Counter.lock**. Mỗi read–modify–write của value diễn ra khi một thread giữ khóa. Không có hai lần tăng cùng đè lên một giá trị cũ. snapshot() cũng đọc dưới khóa đó. Hai join() bảo đảm main đợi xong toàn bộ phép tăng trước khi kiểm tra kết quả.

Nếu increment() dùng ReentrantLock nhưng snapshot() đọc value tự do trong lúc các worker còn chạy, đó là thiết kế visibility không nhất quán. Với dữ liệu bảo vệ bằng lock, hãy thống nhất quy tắc truy cập cho mọi đường có liên quan.

### Độ rộng critical section

Không nên giữ lock cho toàn bộ vòng lặp nếu yêu cầu chỉ cần mỗi phép tăng riêng lẻ là nguyên tử; với một bất biến trải trên nhiều biến, ngược lại cần gói **toàn bộ quyết định nhiều bước** vào một critical section.

Ví dụ nghiệp vụ kiểm tra rồi trừ tồn kho:

~~~java
// Mã minh họa trong phương thức boolean reserve():
lock.lock();
try {
    if (stock <= 0) {
        return false;
    }
    stock--;
    return true;
} finally {
    lock.unlock();
}
~~~

**stock** là trường chia sẻ của cùng đối tượng, được bảo vệ bằng lock đã có. Đặt check ở ngoài rồi chỉ khóa quanh stock-- sẽ còn **logic race** vì thread khác có thể thay đổi stock giữa hai thao tác.

## 5. finally hoạt động ngay cả khi exception

Tệp **UnlockOnExceptionDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class UnlockOnExceptionDemo {
    public static void main(String[] args) {
        ReentrantLock lock = new ReentrantLock();

        try {
            lock.lock();
            try {
                System.out.println("inside = " + lock.isHeldByCurrentThread());
                throw new IllegalStateException("example failure");
            } finally {
                lock.unlock();
            }
        } catch (IllegalStateException ex) {
            System.out.println("caught = " + ex.getMessage());
        }

        System.out.println("after = " + lock.isHeldByCurrentThread());

        lock.lock();
        try {
            System.out.println("acquired again = true");
        } finally {
            lock.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnlockOnExceptionDemo.java
java UnlockOnExceptionDemo
~~~

Stdout:

~~~text
inside = true
caught = example failure
after = false
acquired again = true
~~~

**Giải thích:** exception thoát khỏi try chứa critical section, nhưng finally nhả lock trước khi catch ở ngoài xử lý lỗi. Câu kiểm tra sau catch trả false vì thread hiện tại không còn sở hữu khóa. Lần lock() tiếp theo được phép lấy khóa lại.

Cẩn thận: finally **nhả khóa**, nhưng **không tự rollback dữ liệu đã sửa**. Nếu đang cập nhật nhiều trường và ném exception ở giữa, cần giữ bất biến nhất quán hoặc có chiến lược phục hồi riêng; không nhầm giải phóng khóa với transaction.

## 6. Reentrancy và hold count

Reentrant nghĩa là một thread **đã sở hữu** ReentrantLock có thể gọi **lock() lần nữa** trên cùng đối tượng mà không tự deadlock. Mỗi lần lock thành công làm tăng hold count; mỗi lần unlock của owner làm giảm count. Khóa chỉ thực sự cho thread khác lấy khi hold count trở về 0.

Các phương thức hỗ trợ chẩn đoán:

- **isHeldByCurrentThread()**: thread đang gọi có sở hữu khóa này hay không.
- **getHoldCount()**: số lần thread hiện tại đang giữ khóa; với thread không sở hữu, trả 0.
- **isLocked()**: hiện có thread nào sở hữu khóa không; là snapshot, không thể dùng như điều kiện an toàn để thay lock().
- **isFair()**: khóa có được tạo với chính sách fair hay không.
- **getQueueLength()**: ước lượng số thread chờ, không phải số chính xác để quyết định nghiệp vụ.

### Ví dụ Java 17+: nested locking

Tệp **ReentrantHoldDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantHoldDemo {
    public static void main(String[] args) {
        ReentrantLock lock = new ReentrantLock();

        lock.lock();
        try {
            System.out.println("outer hold = " + lock.getHoldCount());

            lock.lock();
            try {
                System.out.println("inner hold = " + lock.getHoldCount());
            } finally {
                lock.unlock();
            }

            System.out.println("after inner = " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }

        System.out.println("after outer = " + lock.getHoldCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReentrantHoldDemo.java
java ReentrantHoldDemo
~~~

Stdout:

~~~text
outer hold = 1
inner hold = 2
after inner = 1
after outer = 0
~~~

Đây là một thread duy nhất nên thứ tự stdout xác định. **Mỗi lần lock thành công phải có một lần unlock tương ứng**. Nếu chỉ unlock một lần sau hai lần lock, thread vẫn giữ khóa ở mức 1; thread khác chưa thể lấy được.

Tính reentrant hữu ích khi phương thức đang giữ lock gọi một phương thức khác của cùng lớp cũng dùng đúng lock đó. Dù vậy, không nên tùy tiện lạm dụng nhiều cấp khóa hoặc phương thức gọi lẫn nhau quá khó kiểm soát.

### unlock sai owner

**ReentrantLock.unlock()** yêu cầu thread hiện tại đang giữ khóa. Nếu một thread khác gọi unlock(), hoặc caller chưa sở hữu khóa, nó ném **IllegalMonitorStateException**. Không được nhờ một thread khác “dọn khóa hộ” khi owner mắc kẹt; cần thiết kế task và cancel/timeout đúng, không dùng unlock trái owner.

## 7. Bốn con đường acquisition

### 7.1. lock(): đợi cho đến khi lấy được khóa

~~~java
lock.lock();
try {
    performCriticalAction();
} finally {
    lock.unlock();
}
~~~

Nếu đã có owner khác, caller chờ đến khi có thể lấy khóa. **lock() không phải lời gọi lấy khóa có thể bị hủy bằng InterruptedException**. Khi một thread bị interrupt trong lúc chờ, lock() vẫn có thể tiếp tục chờ đến khi lấy được khóa; hành vi chi tiết của interrupt status phụ thuộc hợp đồng triển khai, nhưng không được giả định rằng nó sẽ tự thoát chờ bằng checked exception.

Dùng lock() cho critical section phải hoàn thành và có thời gian giữ khóa ngắn, không cần khả năng hủy việc **đang chờ lấy khóa**.

### 7.2. lockInterruptibly(): lấy khóa có thể bị ngắt

~~~java
lock.lockInterruptibly();
try {
    performCriticalAction();
} finally {
    lock.unlock();
}
~~~

**lockInterruptibly() throws InterruptedException** khi bị ngắt trước khi lấy khóa; trong trường hợp đó caller **không sở hữu khóa**, nên finally bên trên không được chạy. Vì try bắt đầu sau lời gọi acquisition nên mẫu này đúng.

Nếu đã lấy khóa, một interrupt phát sinh sau đó không tự động nhả khóa: code trong try phải hợp tác xử lý interrupt theo chính sách của thao tác, và finally vẫn phải unlock.

### 7.3. tryLock(): thử ngay, trả boolean

~~~java
if (lock.tryLock()) {
    try {
        performCriticalAction();
    } finally {
        lock.unlock();
    }
} else {
    // Không có quyền vào critical section lúc này.
}
~~~

**tryLock()** trả true khi lấy được khóa ngay, false khi chưa thể; không phải lời gọi đợi có hạn. Nếu thread đã giữ khóa thì có thể lấy reentrant và trả true. Caller phải quyết định rõ fallback khi false; đừng bỏ qua công việc quan trọng hoặc chạy phần critical section không khóa.

### 7.4. tryLock(timeout, unit): chờ có giới hạn

~~~java
// Minh họa trong phương thức khai báo throws InterruptedException:
boolean acquired = lock.tryLock(500, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!acquired) {
    return;
}
try {
    performCriticalAction();
} finally {
    lock.unlock();
}
~~~

Đoạn này minh họa phương thức trả void, với lock và performCriticalAction() đã khai báo. **tryLock(timeout, unit)** có thể chờ tối đa khoảng thời gian được chỉ định, trả **false** nếu không lấy được khóa trước hạn, hoặc ném **InterruptedException** nếu bị ngắt trong khi chờ. Thời điểm timeout chịu độ phân giải timer và lập lịch; không dùng nó để hứa thời điểm tuyệt đối.

**Chỉ nhả khóa sau khi acquired == true.** Một lần timeout hoặc interruption trước acquisition không tạo nghĩa vụ unlock.

### So sánh

| Phương thức | Khi khóa đang bận | InterruptedException | Khi nào cần unlock? |
| --- | --- | --- | --- |
| **lock()** | Chờ đến khi lấy được | Không khai báo | Sau khi lock() trả về do lấy được |
| **lockInterruptibly()** | Chờ, có thể hủy do interrupt | Có | Chỉ sau khi lấy thành công |
| **tryLock()** | Trả false ngay | Không khai báo | Chỉ khi trả true |
| **tryLock(timeout, unit)** | Chờ trong giới hạn, hoặc trả false | Có | Chỉ khi trả true |

Tất cả đều tuân thủ quyền sở hữu: thread đã acquire phải release đủ số lần bằng chính thread đó.

## 8. Ví dụ tryLock(): bỏ qua tác vụ khi không lấy được khóa

Ví dụ dùng latch để khống chế thời điểm main thử lấy khóa, tránh các bài test mong kết quả dựa trên sleep.

Tệp **TryLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                locked.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                lock.unlock();
            }
        }, "holder");

        holder.start();
        locked.await();

        boolean acquiredWhileBusy = lock.tryLock();
        System.out.println("while busy = " + acquiredWhileBusy);
        if (acquiredWhileBusy) {
            lock.unlock();
        }

        release.countDown();
        holder.join();

        boolean acquiredAfter = lock.tryLock();
        System.out.println("after release = " + acquiredAfter);
        if (acquiredAfter) {
            try {
                System.out.println("main owns lock = " + lock.isHeldByCurrentThread());
            } finally {
                lock.unlock();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 TryLockDemo.java
java TryLockDemo
~~~

Stdout trong điều kiện chạy bình thường, không có interrupt bên ngoài:

~~~text
while busy = false
after release = true
main owns lock = true
~~~

Khi locked.await() trên main kết thúc, holder đã lấy lock và chưa được phép rời phần chờ release.await(). Lần tryLock đầu của main trả false. Sau khi phát tín hiệu và join(), holder đã unlock; lần tryLock tiếp theo lấy được khóa. Trong cả hai trường hợp, chương trình chỉ gọi unlock khi chính main đã lấy khóa thành công.

Trong ứng dụng thật, sau khi tryLock() trả false cần có chính sách cụ thể: bỏ qua công việc không quan trọng, retry có giới hạn, queue lại, hoặc báo bận. Đừng biến false thành “thành công” nếu tác vụ chưa được thực hiện.

## 9. Ví dụ lockInterruptibly(): hủy việc chờ khóa

Tệp **InterruptibleLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);

        lock.lock();
        try {
            Thread worker = new Thread(() -> {
                attempting.countDown();
                try {
                    lock.lockInterruptibly();
                    try {
                        System.out.println("worker: acquired");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("worker: interrupted");
                }
            }, "interruptible-worker");

            worker.start();
            attempting.await();
            worker.interrupt();
            worker.join();
            System.out.println("main: still owns lock = "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptibleLockDemo.java
java InterruptibleLockDemo
~~~

Stdout:

~~~text
worker: interrupted
main: still owns lock = true
~~~

**Giải thích:**

1. Main lấy lock trước khi khởi chạy worker, và giữ đến sau worker.join().
2. Worker chuẩn bị gọi lockInterruptibly(), báo điểm bắt đầu bằng latch.
3. Main gửi interrupt trước khi tự nhả lock. Dù tín hiệu đến trước hoặc trong lúc worker chờ, lockInterruptibly() xử lý interrupt và ném InterruptedException thay vì cấp khóa khi main vẫn đang giữ.
4. Worker không chạy finally unlock ở nhánh acquisition thất bại; nó chỉ khôi phục interrupt status và báo đã bị ngắt.
5. Main đợi worker kết thúc rồi xác nhận chính mình còn giữ khóa, sau đó finally mới unlock.

Nếu thay lockInterruptibly() bằng lock() thì không thể dựa vào interrupt để khiến worker thoát khỏi quá trình chờ như trên; tránh chạy cùng cấu trúc join khi main vẫn giữ khóa vì có thể tự tạo bế tắc.

## 10. ReentrantLock và Java Memory Model

**Lock** bảo đảm nhiều hơn việc chỉ cho một thread vào critical section: các triển khai Lock như ReentrantLock có ngữ nghĩa đồng bộ hóa bộ nhớ tương ứng với monitor.

- Một **unlock** thành công đối với lock có quan hệ *happens-before* với **lock** thành công kế tiếp đối với cùng lock.
- Các ghi xảy ra trước lần unlock được công bố cho thread sau khi lấy lock theo quy tắc JMM.
- **tryLock() thất bại** không có hiệu ứng synchronization của việc lấy khóa thành công.
- **isLocked()**, **getQueueLength()**, **hasQueuedThreads()** là quan sát phục vụ chẩn đoán; không dùng giá trị snapshot để thay việc acquire.
- Lock/unlock không khiến các truy cập dữ liệu từ code **không cùng giao thức** tự động an toàn.

~~~text
Thread A                       Thread B
--------                       --------
lock.lock()                    lock.lock()  [chờ]
try {                          try {
  shared = 42;                    read shared -> 42
} finally {                   } finally {
  lock.unlock();                  lock.unlock();
}                              }

A unlock ---- happens-before ----> B lock
(nếu B lấy khóa sau A và không có ghi xen giữa)
~~~

Đây là một sơ đồ theo giả định có hai critical section và không có writer khác chen giữa. Trong chương trình thật, phải xét mọi đường ghi và mọi khóa liên quan.

### ReentrantLock không thay thế atomicity của một nghiệp vụ nhiều bước nếu scope khóa sai

~~~java
// Mã minh họa logic race: hai critical section tách rời.
lock.lock();
try {
    if (stock <= 0) {
        return false;
    }
} finally {
    lock.unlock();
}

lock.lock();
try {
    stock--;
    return true;
} finally {
    lock.unlock();
}
~~~

Dù từng critical section hợp lệ, một thread khác có thể trừ stock giữa hai lần nhả/lấy. Phải khóa **bao quanh toàn quyết định** kiểm tra và trừ như ví dụ reserve ở phần 4.

## 11. Fair và nonfair ReentrantLock

Constructor mặc định:

~~~java
ReentrantLock fastLock = new ReentrantLock();
ReentrantLock fairLock = new ReentrantLock(true);
~~~

Đây là đoạn khai báo có thể đặt trong phương thức Java, không có main() độc lập.

- **Nonfair lock** là mặc định; một thread mới có thể giành lock trước các thread khác đã chờ, tùy lịch chạy.
- **Fair lock** được thiết kế để ưu tiên theo thứ tự chờ của các thread trong trường hợp cạnh tranh, nhưng **không cam kết fairness tuyệt đối của lịch CPU**, không cam kết mỗi thread nhận lượt đúng nhau và có thể làm giảm throughput.
- **tryLock() không có timeout** có thể giành được khóa ngay cả khi có thread khác đang chờ **dù lock được cấu hình fair**. Đây là hành vi barging được tài liệu hóa; không suy ra “fair” từ mọi lời gọi giống nhau.
- Khi dùng **tryLock(0, TimeUnit.SECONDS)** trên fair lock, lời gọi theo cơ chế acquisition có điều kiện và tôn trọng chính sách fairness của overload thời gian, đồng thời có thể bị interrupt.
- Không chọn fair=true theo thói quen. Cần đánh giá yêu cầu progress, độ trễ, tính công bằng và throughput của ứng dụng thực tế.

**Quan trọng:** Fairness không giải quyết **deadlock**, không bảo vệ dữ liệu ngoài khóa và không bảo đảm timeout thực thi chính xác từng nano giây.

## 12. Condition: chờ tín hiệu gắn với ReentrantLock

**Condition** được tạo từ **lock.newCondition()**, cung cấp tập thao tác chờ/phát tín hiệu tương tự Object.wait()/notify/notifyAll() nhưng gắn với một Lock tường minh.

- **condition.await()**: yêu cầu thread hiện tại đang giữ lock; nó nhả khóa tương ứng trong khi chờ và lấy lại khóa trước khi trả về hoặc ném InterruptedException theo hợp đồng.
- **condition.signal()**: báo cho một waiter của condition; waiter vẫn phải lấy lại lock mới tiếp tục.
- **condition.signalAll()**: báo cho tất cả waiter của condition; họ sẽ tranh lock và kiểm tra lại điều kiện.
- Vì có thể **spurious wakeup**, luôn dùng **while (!predicate) condition.await()**, không dùng một if duy nhất.
- Phải thao tác **await/signal dưới đúng lock** liên kết với condition. Gọi không phải owner dẫn tới IllegalMonitorStateException ở các thao tác có yêu cầu quyền sở hữu.

Ví dụ mẫu:

~~~java
// Đoạn minh họa: lock, ready và condition đã được khai báo.
lock.lock();
try {
    while (!ready) {
        condition.await();  // throws InterruptedException
    }
    consume();
} finally {
    lock.unlock();
}
~~~

Đây là mã minh họa trong phương thức có xử lý/khai báo InterruptedException; consume() là logic giả định. Một thread khác đổi ready=true rồi signal/signalAll khi sở hữu cùng lock.

### Ví dụ Java 17+: đợi condition và unlock đúng cách

Tệp **ConditionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition readyCondition = lock.newCondition();
        boolean[] ready = {false};
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            lock.lock();
            try {
                System.out.println("worker: waiting");
                started.countDown();

                while (!ready[0]) {
                    try {
                        readyCondition.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                System.out.println("worker: resumed");
            } finally {
                lock.unlock();
            }
        }, "condition-worker");

        worker.start();
        started.await();

        lock.lock();
        try {
            ready[0] = true;
            System.out.println("main: signaled");
            readyCondition.signalAll();
        } finally {
            lock.unlock();
        }

        worker.join();
        System.out.println("main: done");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConditionDemo.java
java ConditionDemo
~~~

Stdout nếu không có interrupt bên ngoài:

~~~text
worker: waiting
main: signaled
worker: resumed
main: done
~~~

Worker giữ lock, in dòng đầu, rồi gọi await() nếu ready chưa đúng. await() nhả lock và đợi. Main đã đợi started, nên chỉ sau khi worker báo bắt đầu mới cố lấy lock, đặt ready và signalAll. Nếu main tới sớm hơn lúc worker thật sự await(), nó phải chờ lock; sau đó điều kiện vẫn nhất quán vì cả hai đọc/ghi dưới cùng lock. Worker khi tiếp tục lấy lại lock và kiểm tra ready trong while.

Nếu điều kiện đang đúng từ trước, while bỏ qua await; vì thế không mất tín hiệu ngay cả khi thứ tự scheduling thay đổi. **Lock/Condition chỉ phục vụ synchronization**, không phải kết quả nghiệp vụ của tác vụ.

### Condition khác với CountDownLatch

Một Condition có thể dùng lặp lại với predicate thay đổi theo thời gian. CountDownLatch là bộ đếm giảm đến 0 và không reset về giá trị ban đầu; nó hữu ích cho sự kiện một lần như “đã sẵn sàng” hoặc “đã hoàn tất”. Với producer/consumer thường nên xét BlockingQueue thay vì tự xây mọi giao thức condition.

## 13. Deadlock: ReentrantLock không tự cứu khỏi vòng chờ

Một thread có thể lấy nhiều ReentrantLock. Nếu hai thread lấy hai lock theo thứ tự ngược nhau, có thể xuất hiện vòng chờ:

~~~text
Thread A                          Thread B
--------                          --------
lock(first)                       lock(second)
  muốn lock(second)                 muốn lock(first)
  -> chờ B                          -> chờ A
                 DEADLOCK
~~~

Tính **reentrant** chỉ cho phép một thread lấy lại **cùng khóa mình đang giữ**. Nó không giải quyết việc A giữ khóa 1 đợi khóa 2 do B giữ, trong khi B đợi khóa 1.

Biện pháp phòng tránh:

1. Định nghĩa **thứ tự lock nhất quán** (ví dụ theo ID bất biến) khi một thao tác phải giữ nhiều lock.
2. Giữ critical section ngắn; tránh gọi I/O, callback không kiểm soát hoặc chờ thread khác kết thúc khi đang giữ lock.
3. Cân nhắc tryLock(timeout) nếu yêu cầu cần tránh chờ mãi; **khi không lấy đủ lock, phải nhả toàn bộ lock đang giữ và xử lý retry an toàn**.
4. Tránh thiết kế mà thread A giữ khóa rồi gọi join() đợi thread B trong khi B phải lấy chính khóa đó mới hoàn thành.
5. Không dùng sleep/yield để “giải deadlock”: hai phương thức không giải phóng khóa, cũng không thiết lập lock ordering.

Với nhiều ReentrantLock, cần quan sát lock owner/stack traces và các mối quan hệ chờ thông qua thread dump, ThreadMXBean hoặc công cụ chẩn đoán phù hợp. ReentrantLock có API theo dõi queue, nhưng snapshot không thay thế lập luận về thứ tự và ownership.

## 14. Chọn giữa synchronized và ReentrantLock

| Tiêu chí | synchronized | ReentrantLock |
| --- | --- | --- |
| Cách sử dụng | Cú pháp ngôn ngữ, monitor intrinsic của object | Lớp Lock với API tường minh |
| Nhả khóa | Tự động khi rời synchronized | **Phải gọi unlock() trong finally** |
| Reentrant | Có | Có |
| Mutual exclusion và happens-before | Có, khi dùng cùng monitor | Có, khi dùng cùng lock |
| Thử lấy ngay | Không có try-enter trực tiếp | tryLock() |
| Thử chờ có timeout | Không có tham số timeout cho monitor enter | tryLock(timeout, unit) |
| Chờ lấy khóa có thể ngắt | Chờ vào monitor không ném InterruptedException | lockInterruptibly() |
| Condition queue | Object.wait/notify/notifyAll | Condition.await/signal/signalAll |
| Cấu hình fairness | Không có tham số fairness | ReentrantLock(true), có giới hạn |
| Nguy cơ bỏ quên giải phóng | Thấp hơn do cấu trúc ngôn ngữ | Cao hơn nếu thiếu finally |

**Ưu tiên synchronized** khi chỉ cần mutual exclusion ngắn, dễ đọc, không cần tính năng acquisition đặc biệt. **Chọn ReentrantLock** khi thực sự cần tryLock, timeout, interruptible lock acquisition, nhiều Condition riêng, hoặc điều khiển lock tường minh có chứng cứ.

Không chọn ReentrantLock chỉ vì “nhanh hơn synchronized”. JIT, mức tranh chấp, độ dài critical section, topology và yêu cầu throughput/latency ảnh hưởng kết quả thực tế. Đo benchmark có phương pháp nếu hiệu năng là lý do lựa chọn.

## 15. Một số lỗi thực tế và cách sửa

| Sai lầm | Hậu quả | Sửa |
| --- | --- | --- |
| Gọi lock() nhưng unlock ngoài finally | Exception/return khiến lock bị giữ | Dùng try/finally ngay sau acquire |
| Gọi unlock() dù tryLock() trả false | IllegalMonitorStateException | Chỉ unlock nếu đã lấy thành công |
| Mỗi thread tạo new ReentrantLock riêng | Không loại trừ truy cập trên biến chung | Dùng chung một lock object |
| Đọc shared state mà không dùng giao thức khóa | Thiếu visibility/atomicity | Đọc và ghi theo cùng giao thức |
| Khóa từng bước check và update riêng | Logic race giữa hai lượt khóa | Bảo vệ toàn bộ bất biến |
| Gọi lock() hai lần, unlock() một lần | Hold count còn 1, thread khác bị chặn | Cân bằng mỗi acquire/release |
| Gọi Condition.await() mà không giữ lock | IllegalMonitorStateException | Acquire lock trước await và finally unlock |
| Dùng if khi chờ condition | Spurious wakeup/lịch xen kẽ có thể làm sai | Dùng while kiểm tra predicate |
| Gọi sleep() khi đang giữ lock | Giữ khóa suốt lúc ngủ, tăng contention | Tách phần chờ khỏi critical section nếu có thể |
| Chờ join()/Future.get() khi đang giữ lock cần cho worker | Có thể tự tạo deadlock | Xem dependency, nhả lock trước khi chờ |
| Tin getQueueLength()/isLocked() là một kiểm tra an toàn để quyết định update | Snapshot thay đổi ngay | Dùng acquire/CAS/condition thực sự |
| Tin fair=true nghĩa là không starvation trong mọi tình huống | Scheduler và tryLock có ngoại lệ; vẫn có chờ dài | Định nghĩa SLA và đo thực tế |
| Interrupt worker đang giữ lock thì khóa tự nhả | Không tự nhả; thread phải tới finally | Viết code cleanup và exit hợp tác |
| Dùng ReentrantLock bảo vệ trạng thái trên nhiều JVM | Lock chỉ dùng chung giữa các thread có cùng đối tượng trong JVM | Cần coordination ở nguồn dữ liệu chia sẻ |

### Nhận diện đặc biệt: unlock() không phải wait/notify

**unlock()** làm giảm hold count và khi về 0 cho phép thread khác lấy lock. Nó **không phải Condition.signal()**. Nếu worker đang chờ một condition predicate, việc nhả lock của thread khác không tự tương đương một tín hiệu signal mà worker có thể dùng để rời await(). Cần cập nhật predicate và phát signal theo hợp đồng của Condition.

### Có nên dùng isLocked() trước lock()?

Không cần và có thể sai về mặt điều phối. **isLocked()** chỉ là ảnh chụp: ngay sau khi trả false, thread khác có thể lấy khóa. Nếu muốn không chờ, dùng **tryLock()**. Nếu muốn chờ đến khi lấy được, gọi **lock()**. Chọn API quyết định theo yêu cầu, không kiểm tra rồi hành động dựa trên snapshot.

## 16. Checklist áp dụng vào code

1. Xác định **đối tượng dữ liệu và invariant** được bảo vệ; mọi đường truy cập liên quan phải dùng cùng giao thức.
2. Lưu ReentrantLock làm field **private final** nếu khóa bảo vệ trạng thái nội bộ của một đối tượng.
3. Đặt **lock.lock()** ngay trước **try**. Bất kỳ đoạn nào có acquisition thành công phải đi tới **finally unlock()**.
4. Nếu dùng **tryLock()**, chỉ vào try khi trả true. Nếu dùng **lockInterruptibly()/timed tryLock**, xử lý InterruptedException trên đường chưa sở hữu.
5. Không giữ lock khi làm I/O/chờ lâu nếu bất biến không bắt buộc; tránh callback ngoài kiểm soát trong critical section.
6. Với nhiều lock, định nghĩa thứ tự acquisition và cách cleanup khi lấy không đủ.
7. Với Condition, giữ lock khi await/signal, lưu predicate dưới cùng lock và kiểm tra predicate trong **while**.
8. Viết test kiểm tra invariants sau khi các worker kết thúc bằng join/Future/latch; đừng chốt correctness chỉ từ log hoặc sleep.
9. Nếu lỗi/timeout/cancellation có thể xảy ra, xác định chính sách **đã làm được phần nào** và trạng thái nghiệp vụ; finally chỉ giải phóng khóa, không rollback side effect.
10. Nếu dữ liệu trải qua nhiều JVM/process, ReentrantLock cục bộ không thay thế cơ chế đồng bộ của kho dữ liệu chung.

## 17. Tự kiểm tra

**Câu 1.** Vì sao không viết lock.lock(); doWork(); lock.unlock();?  
**Trả lời:** Nếu doWork ném exception hoặc return trước unlock, khóa vẫn bị giữ. finally đảm bảo cleanup khi rời phạm vi.

**Câu 2.** Nếu tryLock() trả false thì có được unlock() không?  
**Trả lời:** Không. Caller chưa sở hữu khóa; unlock() có thể ném IllegalMonitorStateException.

**Câu 3.** ReentrantLock.lock() hai lần và unlock() một lần thì thread khác lấy được chưa?  
**Trả lời:** Chưa; hold count còn 1. Phải có unlock tương ứng lần lấy còn lại.

**Câu 4.** lockInterruptibly() khác lock() thế nào?  
**Trả lời:** Nó cho phép bỏ việc chờ lấy khóa bằng InterruptedException khi bị interrupt, thay vì chờ không thể hủy theo cơ chế đó.

**Câu 5.** Main gọi lock.isLocked() thấy false rồi sửa biến ngay có an toàn không?  
**Trả lời:** Không. Snapshot có thể đổi trước khi sửa; cần acquire thành công hoặc cơ chế đồng bộ đúng.

**Câu 6.** Một Condition.await() có tự nhả lock không?  
**Trả lời:** Có, nó nhả lock liên kết trong lúc chờ và lấy lại trước khi tiếp tục theo hợp đồng. Waiter phải giữ lock khi bắt đầu await và dùng while kiểm tra điều kiện.

**Câu 7.** Nếu class đã dùng ReentrantLock bảo vệ counter, một reader không khóa có luôn thấy giá trị mới không?  
**Trả lời:** Không. Reader phải tham gia giao thức đồng bộ hóa/happens-before thích hợp.

**Câu 8.** Khi một thread giữ lock rồi gọi Future.get() chờ worker mà worker cần cùng lock, điều gì có thể xảy ra?  
**Trả lời:** Deadlock: thread gọi không nhả khóa trước khi worker hoàn tất, còn worker không hoàn tất vì không lấy được khóa.

**Câu 9.** Fair lock có bảo đảm tryLock() không bao giờ vượt hàng không?  
**Trả lời:** Không. tryLock() không timeout có thể lấy khóa ngay kể cả khi lock fair đang có thread khác chờ.

**Câu 10.** Có thể thay mọi synchronized bằng ReentrantLock và luôn tăng hiệu năng không?  
**Trả lời:** Không. Hai cơ chế có trade-off khác nhau, và cần benchmark trên workload thực. ReentrantLock phù hợp khi cần tính năng API riêng, không phải lựa chọn tự động nhanh hơn.

## 18. Ghi nhớ

**ReentrantLock** cung cấp mutual exclusion và memory-ordering giống lock của monitor nhưng yêu cầu quản lý quyền sở hữu một cách tường minh. **Khi đã acquire thành công, luôn unlock trong finally; khi acquisition thất bại, không unlock.** Với lock() thông thường, đặt try ngay sau lock(). Với tryLock, chỉ chạy try/finally khi được cấp khóa. Với lockInterruptibly hoặc tryLock có timeout, phân biệt rõ nhánh InterruptedException, nhánh không lấy được khóa và nhánh đã sở hữu.

Dùng tính **reentrant** có kiểm soát, giữ **hold count** cân bằng, dùng Condition với predicate trong while, và xem xét lock ordering khi có nhiều khóa. Hãy thiết kế critical section theo **toàn bộ bất biến** của dữ liệu và dùng API Java phù hợp với yêu cầu chờ, hủy, timeout, thay vì phụ thuộc timing ngẫu nhiên.
