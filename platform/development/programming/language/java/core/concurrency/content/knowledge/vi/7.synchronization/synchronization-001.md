# Intrinsic lock và monitor của mọi object trong Java

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Giải thích **intrinsic lock** (khóa nội tại, hay **monitor lock**) gắn với mỗi đối tượng Java và vì sao khóa là **danh tính đối tượng**, không phải tên biến hoặc giá trị của đối tượng.
- Dùng ba hình thức **synchronized**: khối synchronized, phương thức instance synchronized và phương thức static synchronized; xác định chính xác đối tượng monitor được khóa trong từng trường hợp.
- Hiểu **mutual exclusion**, **reentrancy**, thời điểm lấy/nhả monitor, và quan hệ **happens-before** giữa unlock/lock để bảo vệ dữ liệu chia sẻ.
- Phân biệt **BLOCKED** vì chờ monitor với **WAITING/TIMED_WAITING** do chờ điều kiện; nắm cách **Object.wait()**, **notify()**, **notifyAll()** tương tác với monitor.
- Nhận diện lỗi khóa sai đối tượng, khóa không bao phủ bất biến, lộ lock ra ngoài, giữ lock khi ngủ hoặc làm I/O, và deadlock do nhiều monitor.
- Chạy các ví dụ Java 17+ và tự giải thích kết quả mà không dựa vào thứ tự scheduling ngẫu nhiên.

Bài học thuộc **Java concurrency nói chung**, dựa trên Java Language Specification, Java Memory Model (JMM) và API JDK. Các cơ chế đồng bộ hóa riêng của Spring thuộc phạm vi khác.

## 2. Intrinsic lock là gì?

Về mặt ngữ nghĩa của Java, **mỗi object, bao gồm cả array và đối tượng Class, có một monitor liên kết với nó**. Khi một thread thực hiện synchronized trên một object, nó phải lấy quyền sở hữu monitor của object đó trước khi vào critical section; khi rời critical section, nó nhả monitor tương ứng. JVM có thể triển khai hoặc tối ưu cơ chế này theo nhiều cách; không nên giả định cấu trúc cụ thể của object header hoặc thao tác hệ điều hành chỉ từ hợp đồng ngôn ngữ.

~~~java
// Minh họa cú pháp, đặt trong một phương thức của lớp Java:
Object lock = new Object();

synchronized (lock) {
    // Chỉ một thread tại một thời điểm sở hữu monitor của lock
    // để thực thi vùng mã này.
}
~~~

Đây là đoạn minh họa cú pháp, **không phải chương trình độc lập có main()**.

### Khóa gắn với object identity

Hai biến tham chiếu trỏ đến **cùng một object** thì dùng cùng monitor:

~~~java
Object a = new Object();
Object alias = a;

synchronized (a) {
    // Đang sở hữu đúng monitor mà synchronized(alias) sẽ yêu cầu.
}
~~~

Ngược lại, hai object khác nhau dù có cùng nội dung logic vẫn là **hai monitor riêng**:

~~~java
Object a = new Object();
Object b = new Object();
// a != b, nên synchronized(a) và synchronized(b) không chặn nhau.
~~~

Không nhầm **equals()** với khóa: monitor được xác định bằng identity của object (**==**), không phải kết quả equals(), hashCode() hay chuỗi hiển thị. Nếu hai thread định dùng chung khóa, chúng phải thực sự cầm **cùng reference đến object khóa**.

**Một giới hạn thực tế:** biểu thức synchronized phải đánh giá thành một **reference khác null**. Nếu synchronized(null) sẽ ném **NullPointerException** trước khi vào critical section. Không thể synchronized trực tiếp trên primitive như int; chỉ object reference mới có monitor theo cơ chế này.

## 3. Mutual exclusion: cùng monitor, một chủ sở hữu

Một monitor có thể được **một thread** sở hữu tại một thời điểm. Nếu thread A đã giữ monitor của lock, thread B muốn vào synchronized(lock) phải chờ đến khi A nhả. Nếu thread C synchronized trên object khác, C không bị monitor của lock chặn, trừ khi nó còn đòi một khóa/tài nguyên khác.

Điều này bảo vệ **critical section**: chuỗi thao tác cần được quan sát như một đơn vị không bị các thread dùng **cùng monitor** xen vào.

~~~text
Thread A                         Thread B
--------                         --------
synchronized(lock) {             synchronized(lock) {
  đọc count                        chờ monitor của lock
  count = count + 1                ...
  ghi count                        khi A nhả lock -> vào
} // nhả lock                      ...
                                 } // nhả lock
~~~

Nếu một thread sửa count **ngoài** synchronized(lock), luật loại trừ này không tự ngăn nó. Cả reader và writer của dữ liệu cần tuân thủ cùng một chiến lược bảo vệ, hoặc một giao thức JMM tương thích khác.

### Ví dụ 1: bảo vệ phép tăng không nguyên tử

Tệp **MonitorCounterDemo.java**:

~~~java
public class MonitorCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        int[] counter = {0};

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                synchronized (monitor) {
                    counter[0]++;
                }
            }
        };

        Thread a = new Thread(increment, "counter-a");
        Thread b = new Thread(increment, "counter-b");
        a.start();
        b.start();
        a.join();
        b.join();

        synchronized (monitor) {
            System.out.println("counter = " + counter[0]);
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 MonitorCounterDemo.java
java MonitorCounterDemo
~~~

Stdout:

~~~text
counter = 20000
~~~

**Vì sao chính xác?** Hai worker đều dùng **cùng đối tượng monitor**, nên toàn bộ các bước đọc–tăng–ghi của counter[0] nằm trong một critical section mỗi lần. Không có lost update giữa hai worker. Hai lần join() làm main đợi cả hai kết thúc trước khi in; main còn đọc trong synchronized(monitor) để nhất quán với chiến lược bảo vệ biến.

Nếu thay mỗi lần synchronized(monitor) bằng synchronized(new Object()), mỗi thread/lượt sẽ khóa object khác nhau; không còn bảo vệ counter chung. Nếu chỉ đặt synchronized quanh dòng in cuối, các phép tăng trước đó vẫn thiếu đồng bộ hóa.

### Vùng khóa cần bao phủ **bất biến**, không chỉ một câu lệnh

Giả sử một yêu cầu là “nếu còn hàng thì giữ đúng một sản phẩm”. Đoạn mã sau sai vì check và decrement tách khỏi một critical section chung:

~~~java
// Mã minh họa lỗi: stock là biến chia sẻ, lock là khóa chung.
synchronized (lock) {
    if (stock <= 0) {
        return false;
    }
}
synchronized (lock) {
    stock--;
}
return true;
~~~

Giữa hai synchronized, thread khác có thể làm thay đổi stock. Nếu tất cả thao tác stock đi qua cùng monitor, check và update phải nằm **trong một lần giữ khóa**:

~~~java
// Mã minh họa bên trong phương thức trả boolean:
synchronized (lock) {
    if (stock <= 0) {
        return false;
    }
    stock--;
    return true;
}
~~~

Các mảnh trên minh họa hàm nghiệp vụ và cần khai báo biến/phương thức phù hợp mới biên dịch độc lập. **Mục tiêu của khóa là bảo vệ quy tắc đúng đắn toàn bộ**, không chỉ làm từng phép đọc/ghi riêng lẻ.

## 4. Ba hình thức synchronized và monitor tương ứng

### 4.1. synchronized trên một biểu thức

~~~java
synchronized (lock) {
    // critical section
}
~~~

JVM đánh giá biểu thức **lock** để lấy reference object, sau đó sở hữu monitor của object đó khi thực thi body. Body rời đi bằng cách kết thúc bình thường, return, break, hoặc exception thì monitor được nhả theo ngữ nghĩa synchronized. Lưu ý biểu thức có thể có side effect; tốt nhất khóa một field **private final Object** rõ ràng thay vì một biểu thức có thể thay reference.

### 4.2. Instance synchronized method khóa this

~~~java
public synchronized void update() {
    // Giống về monitor với synchronized (this) { ... }
}
~~~

Một phương thức instance synchronized lấy **monitor của this**. Mỗi instance có monitor riêng: hai instance của cùng class có thể chạy đồng thời các phương thức synchronized của mình.

Nếu một object có hai phương thức instance synchronized, hai thread gọi hai phương thức ấy **trên cùng instance** sẽ cạnh tranh cùng monitor. Nhưng nếu một phương thức khác truy cập field mà không lấy khóa, phương thức đó vẫn có thể vi phạm chiến lược đồng bộ.

### 4.3. Static synchronized method khóa Class object

~~~java
public static synchronized void updateGlobal() {
    // Monitor của chính Class object của lớp khai báo phương thức.
}
~~~

Một phương thức **static synchronized** lấy monitor của **Class object** tương ứng với lớp khai báo phương thức (ví dụ: **Example.class**). Nó **không** khóa this, vì phương thức static không có this. **Instance synchronized** và **static synchronized** thường dùng hai monitor khác nhau; không nên kỳ vọng chúng tự loại trừ nhau.

### Ví dụ 2: xem monitor nào đang được giữ

Tệp **MonitorKindsDemo.java**:

~~~java
public class MonitorKindsDemo {
    synchronized void instanceWork() {
        System.out.println(
            "instance lock held = " + Thread.holdsLock(this)
        );
        System.out.println(
            "class lock held = "
                + Thread.holdsLock(MonitorKindsDemo.class)
        );
    }

    static synchronized void classWork() {
        System.out.println(
            "static class lock held = "
                + Thread.holdsLock(MonitorKindsDemo.class)
        );
    }

    public static void main(String[] args) {
        MonitorKindsDemo service = new MonitorKindsDemo();
        service.instanceWork();
        classWork();

        Object explicitLock = new Object();
        synchronized (explicitLock) {
            System.out.println(
                "explicit lock held = " + Thread.holdsLock(explicitLock)
            );
        }

        System.out.println(
            "explicit lock after exit = "
                + Thread.holdsLock(explicitLock)
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 MonitorKindsDemo.java
java MonitorKindsDemo
~~~

Stdout:

~~~text
instance lock held = true
class lock held = false
static class lock held = true
explicit lock held = true
explicit lock after exit = false
~~~

**Thread.holdsLock(Object)** trả true nếu thread **hiện tại** đang sở hữu monitor của object đó. Nó thích hợp cho assert/chẩn đoán một phạm vi nhất định. Đừng dùng nó để hỏi thread khác có đang giữ monitor hay không hoặc thay thế giao thức đồng bộ.

## 5. Reentrant monitor: cùng thread có thể lấy lại chính khóa mình giữ

Intrinsic lock của Java là **reentrant**. Nếu thread A đã sở hữu monitor của lock, A có thể vào thêm một synchronized(lock) lồng nhau mà không bị chính mình chặn. JVM duy trì mức sở hữu/đếm vào khóa tương ứng; mỗi lần rời synchronized giảm mức giữ, và monitor chỉ được giải phóng hoàn toàn khi thread đã rời hết các mức giữ.

### Ví dụ 3: synchronized lồng nhau

Tệp **ReentrantMonitorDemo.java**:

~~~java
public class ReentrantMonitorDemo {
    public static void main(String[] args) {
        Object lock = new Object();

        synchronized (lock) {
            System.out.println("outer = " + Thread.holdsLock(lock));

            synchronized (lock) {
                System.out.println("inner = " + Thread.holdsLock(lock));
            }

            System.out.println("after inner = " + Thread.holdsLock(lock));
        }

        System.out.println("after outer = " + Thread.holdsLock(lock));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReentrantMonitorDemo.java
java ReentrantMonitorDemo
~~~

Stdout:

~~~text
outer = true
inner = true
after inner = true
after outer = false
~~~

Cùng một thread có thể gọi lẫn nhau giữa các phương thức synchronized trên cùng instance mà không gây self-deadlock chỉ vì lấy lại monitor đó. Nhưng **reentrancy không ngăn deadlock** khi nhiều thread giành **nhiều monitor khác nhau** theo thứ tự đối nghịch.

## 6. Khi nào monitor được nhả?

Khi synchronized block hoặc synchronized method **rời phạm vi** do chạy bình thường, return hoặc exception, monitor tương ứng được nhả tự động. Không có lệnh unlock tường minh cho intrinsic lock.

Ví dụ:

~~~java
// Phần thân minh họa của một phương thức Java:
synchronized (lock) {
    if (invalid) {
        throw new IllegalStateException("invalid");
    }
} // Khi exception thoát khỏi synchronized, monitor được nhả.
~~~

**lock** và **invalid** là các biến giả định; ví dụ không tự chạy. Việc nhả monitor khi exception thoát **không tự rollback** các field đã bị thay đổi trước exception. Nếu cập nhật nhiều trường rồi lỗi ở giữa, cần thiết kế bất biến và phục hồi nhất quán riêng.

### Ví dụ 4: exception vẫn giải phóng monitor

Tệp **MonitorExceptionDemo.java**:

~~~java
public class MonitorExceptionDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        Thread worker = new Thread(() -> {
            try {
                synchronized (lock) {
                    System.out.println("worker: acquired");
                    throw new IllegalStateException("failed");
                }
            } catch (IllegalStateException ex) {
                System.out.println("worker: caught");
            }
        }, "worker");

        worker.start();
        worker.join();

        synchronized (lock) {
            System.out.println("main: acquired");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MonitorExceptionDemo.java
java MonitorExceptionDemo
~~~

Stdout:

~~~text
worker: acquired
worker: caught
main: acquired
~~~

Main lấy được monitor sau khi worker đã thoát khối synchronized dù worker có ném exception. Trong ví dụ này, join() cũng buộc main chờ worker kết thúc nên stdout có thứ tự xác định.

## 7. Monitor trong Java Memory Model: không chỉ là chặn truy cập

Synchronized có hai loại bảo đảm quan trọng:

**Mutual exclusion:** tại một thời điểm chỉ một thread giữ monitor đang xét; các critical section dùng chung monitor không chồng lấn.

**Memory ordering/visibility:** hành động **unlock** của thread A trên một monitor **happens-before** hành động **lock tiếp theo** của thread B trên **cùng monitor**. Nhờ tính truyền bắc cầu của happens-before, các ghi trước khi A nhả monitor trở nên nhìn thấy theo các ràng buộc JMM đối với B sau khi lấy monitor.

~~~text
Thread A                               Thread B
--------                               --------
synchronized (lock) {                 synchronized (lock) {
    shared = 42;      -------- HB -->     read shared -> 42
} // monitor unlock                     } // monitor unlock
                     (nếu không có ghi khác chen vào)
~~~

Đây là sơ đồ lý tưởng hóa hai critical section với cùng lock và không có cập nhật khác chen giữa. Điểm mấu chốt là **cùng monitor**. Nếu A ghi dưới lock1 còn B đọc dưới lock2 không tương ứng, chỉ sự hiện diện của synchronized ở hai nơi không bảo đảm HB cho hai truy cập đó.

### Vì sao chỉ khóa bên ghi hoặc bên đọc vẫn sai?

~~~java
// Anti-pattern: writer khóa, reader không khóa.
// shared là một field thường được chia sẻ.
void writer() {
    synchronized (lock) {
        shared = 42;
    }
}

int reader() {
    return shared; // Không tham gia cùng giao thức monitor.
}
~~~

Đoạn trên minh họa phương thức trong một lớp, với các field lock và shared được định nghĩa ở nơi khác. Nếu không có một quan hệ đồng bộ hóa khác, reader không có bảo đảm thích hợp để thấy cập nhật. Khóa không tự phát tín hiệu đến mọi phép đọc tự do.

**Thread.sleep()** và **Thread.yield()** không thay thế monitor unlock/lock hay volatile/atomic operations về memory visibility.

### Không nên lẫn monitor với toàn bộ thread safety

Kể cả khi một class khóa đúng lúc khởi tạo, trạng thái mutable bên trong nó vẫn cần bảo vệ theo phạm vi cập nhật. Một biến đếm có thể dùng AtomicInteger; một bất biến trên nhiều field có thể cần một monitor hoặc cấu trúc bất biến được công bố an toàn. Chọn cơ chế theo dữ liệu và invariant, không chỉ theo việc “có synchronized ở đâu đó”.

## 8. BLOCKED, WAITING và TIMED_WAITING liên quan thế nào?

Một thread có thể được quan sát trong các trạng thái sau:

| Thread.State | Trường hợp liên quan | Ý nghĩa |
| --- | --- | --- |
| **RUNNABLE** | Đang hoặc đủ điều kiện chạy | Không nhất thiết đang có CPU |
| **BLOCKED** | Chờ **monitor** để vào synchronized | Chưa sở hữu monitor cần thiết |
| **WAITING** | Object.wait() không timeout, join() không timeout, latch await() không timeout | Đợi hành động/sự kiện khác |
| **TIMED_WAITING** | Thread.sleep(), Object.wait(timeout), join(timeout) | Đợi với giới hạn thời gian |
| **TERMINATED** | run() đã kết thúc | Không nói kết quả nghiệp vụ thành công hay thất bại |

**getState()** là snapshot; trạng thái có thể đổi ngay sau khi được đọc. Chỉ riêng Thread.State không phải một hợp đồng để điều phối chương trình.

Lưu ý: thread chờ **ReentrantLock.lock()** không nhất thiết hiển thị BLOCKED. BLOCKED của Thread.State gắn cụ thể với giành **intrinsic monitor**. Những dạng chờ trong java.util.concurrent thường dựa trên cơ chế park/condition có trạng thái quan sát khác.

## 9. sleep(), yield() và chờ khác có tự nhả monitor không?

**Không.** Nếu một thread gọi Thread.sleep(...) hoặc Thread.yield() khi đang giữ monitor, nó **vẫn giữ monitor** trong lúc ngủ/đề nghị nhường CPU. Các thread khác cần đúng monitor đó vẫn không thể vào synchronized cho đến khi chủ sở hữu rời khỏi khối hoặc dùng cơ chế wait tương ứng.

**CountDownLatch.await()**, **Thread.join()** và thao tác I/O ở trong synchronized cũng **không tự nhả các monitor mà caller đang sở hữu**. Chúng có thể làm thread chờ lâu, khiến các thread khác đang cần monitor bị chặn.

**Object.wait() là ngoại lệ có ngữ nghĩa riêng:** khi thread đang giữ monitor của object và gọi wait() trên chính object đó, thao tác wait sẽ **nhả monitor của đúng object được wait** trong khi đợi, và thread phải lấy lại monitor ấy trước khi tiếp tục. Wait không nhả các monitor khác mà thread đang sở hữu.

### Ví dụ 5: đợi latch không nhả monitor

Tệp **WaitKeepsMonitorDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class WaitKeepsMonitorDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (monitor) {
                System.out.println("holder: acquired");
                entered.countDown();

                try {
                    release.await(); // Không tự nhả monitor.
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }

                System.out.println("holder: releasing");
            }
        }, "holder");

        holder.start();
        entered.await();
        release.countDown();

        synchronized (monitor) {
            System.out.println("main: acquired");
        }

        holder.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 WaitKeepsMonitorDemo.java
java WaitKeepsMonitorDemo
~~~

Stdout (không có ngắt ngoài):

~~~text
holder: acquired
holder: releasing
main: acquired
~~~

Ngay cả khi holder đang ở **WAITING** do latch, nó vẫn có thể giữ monitor. Main phải chờ holder rời synchronized. Ví dụ dùng latch để tạo điều kiện chờ rõ ràng, không đoán timing bằng sleep.

**Tránh thiết kế deadlock:** nếu main giữ monitor rồi mới gọi release.countDown(), còn worker cần chính monitor đó để đếm xuống latch khác, có thể tạo vòng chờ. Hãy vẽ rõ tài nguyên nào giữ, tài nguyên nào đang chờ.

## 10. Object.wait(), notify() và notifyAll(): điều kiện dựa trên monitor

Mọi object có **wait()**, **notify()**, **notifyAll()** và một wait set riêng. Giao thức này phục vụ chờ **điều kiện của trạng thái chia sẻ**, không tạo một hàng đợi payload hay ghi nhớ các lượt notify đã qua.

- Thread gọi **wait()** phải đang giữ monitor của chính object được wait; nó nhả **đúng monitor ấy** trong lúc đợi và phải lấy lại trước khi tiếp tục. Các monitor khác đang giữ không tự nhả.
- Thread gọi **notify()/notifyAll()** phải giữ monitor tương ứng. **notify()** chọn một waiter không xác định; **notifyAll()** đánh thức mọi waiter hiện tại, nhưng chúng vẫn phải cạnh tranh lấy lại monitor sau khi thread phát tín hiệu nhả khóa.
- **Spurious wakeup**, tín hiệu dành cho điều kiện khác và thay đổi trạng thái do thread khác là lý do bắt buộc phải chờ trong **while (!predicate)**, không chỉ kiểm tra **if** một lần.
- Thay đổi predicate và phát tín hiệu cần được bảo vệ bởi **cùng monitor**, nếu không dễ bỏ lỡ tín hiệu hoặc đọc state sai. Gọi wait/notify khi không giữ monitor gây **IllegalMonitorStateException**.

~~~java
// Snippet minh họa trong method có lock, ready và consume:
synchronized (lock) {
    while (!ready) {
        lock.wait(); // Cần xử lý hoặc khai báo InterruptedException.
    }
    consume();
}
~~~

Đây là phần giới thiệu ngữ nghĩa monitor. Việc lựa chọn notify hay notifyAll, timed wait, interrupt, producer–consumer và nhiều waiter với predicate khác nhau được thực hành sâu trong bài **Đợi monitor bằng wait() và đánh thức bằng notify()/notifyAll()**. Một ví dụ đúng không dựa vào notify như token, mà dựa vào trạng thái được kiểm tra lại sau khi đã lấy lại monitor.

## 11. Thiết kế lock object an toàn

### Dùng private final lock khi cần khóa nội bộ

~~~java
public final class Balance {
    private final Object lock = new Object();
    private long cents;

    public Balance(long initialCents) {
        cents = initialCents;
    }

    public void deposit(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
        }
        synchronized (lock) {
            cents = Math.addExact(cents, amount);
        }
    }

    public long snapshot() {
        synchronized (lock) {
            return cents;
        }
    }
}
~~~

Đây là lớp Java có thể biên dịch nhưng không có main(). **Private final lock** giảm khả năng code bên ngoài vô tình lấy cùng monitor, đồng thời giữ một identity ổn định trong vòng đời đối tượng. Trường cents được đọc/ghi dưới cùng khóa.

Ví dụ minh họa tính an toàn của trạng thái trong một JVM; nếu đối tượng phải quản lý giao dịch ở nơi lưu trữ chung hoặc nhiều process, synchronized không thay thế transaction/idempotency thích hợp.

### Tránh khóa các object công khai hoặc thay đổi identity

Không tùy tiện sử dụng **String literal**, đối tượng Integer cache, Class object dùng chung, hoặc đối tượng nhận từ code không kiểm soát làm lock cho trạng thái nội bộ. Các object đó có thể bị thread khác lấy khóa vì mục đích không liên quan, làm phát sinh contention hoặc deadlock khó giải thích.

~~~java
// Anti-pattern: String literal có thể được intern và dùng chung.
synchronized ("shared-lock") {
    // Không nên dùng làm private monitor của dữ liệu ứng dụng.
}
~~~

Tránh:

~~~java
// Anti-pattern: dùng field có thể đổi object làm monitor.
private Object lock = new Object();

void replaceLock() {
    lock = new Object();
}
~~~

Những đoạn này minh họa lỗi thiết kế, không phải các chương trình độc lập. Nếu một thread giữ monitor cũ còn thread khác chuyển sang monitor mới, critical section tưởng chung lại không loại trừ nhau.

### synchronized(this) và phương thức synchronized có phải luôn sai?

Không. Chúng hợp lệ nếu **monitor của this là một phần cố ý của hợp đồng khóa** và việc code khác lấy khóa đó được xem xét. Nhưng với lớp có dữ liệu nội bộ riêng tư, **private final Object lock** thường giúp xác định ranh giới đồng bộ hóa rõ hơn.

## 12. Deadlock và lock ordering

Một monitor reentrant vẫn có thể tham gia deadlock khi hai thread lấy hai monitor **khác nhau** theo thứ tự ngược nhau:

~~~text
Thread A                         Thread B
--------                         --------
lock(monitor1)                   lock(monitor2)
  muốn lock(monitor2)              muốn lock(monitor1)
  -> chờ B                         -> chờ A
             === DEADLOCK ===
~~~

Nếu không thread nào tự bỏ lock, cả hai có thể chờ mãi. JVM không tự nhả monitor chỉ vì một thread đã chờ lâu. Deadlock thường xảy ra khi lock nhiều đối tượng trong quá trình chuyển tiền, cập nhật nhiều cấu trúc hoặc gọi callback dưới khóa.

Một nguyên tắc phòng tránh là **áp dụng thứ tự lấy khóa nhất quán**: ví dụ luôn lấy monitor của object có ID nhỏ hơn trước, rồi đến ID lớn hơn, và nhả theo scope ngược lại. Nếu có trường hợp cùng ID nhưng hai object khác nhau, cần chiến lược định thứ tự tổng quát/khóa tie-break; không chỉ so hashCode() và cho rằng không trùng. Các lựa chọn khác là giảm số lock, tránh gọi code ngoài khi đang giữ lock, hoặc dùng mô hình sở hữu dữ liệu/trao message.

**Không nên dùng chương trình cố ý deadlock trong bài thực hành chạy mặc định**, vì nó có thể treo không giới hạn. Dùng sơ đồ tài nguyên và công cụ chẩn đoán như thread dump để phân tích mà không biến ví dụ học thành quy trình chạy không có điểm kết thúc.

## 13. Sự khác biệt với ReentrantLock và các tiện ích JDK khác

**Intrinsic lock** là monitor được sử dụng qua cú pháp synchronized; Java tự thực hiện enter/exit monitor. **java.util.concurrent.locks.ReentrantLock** là lớp lock tường minh với phương thức lock(), unlock(), tryLock() và khả năng dùng Condition. Cả hai có tính reentrant, nhưng **không phải cùng một khóa** ngay cả khi liên quan cùng object chứa dữ liệu.

Ví dụ mẫu dùng ReentrantLock:

~~~java
// Đoạn minh họa: lock là ReentrantLock đã khởi tạo.
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đây không phải chương trình độc lập; updateSharedState() là phương thức giả định. Với ReentrantLock, phải đảm bảo unlock() trong finally vì Java không tự nhả lock tường minh khi thoát scope. Nếu muốn timeout hay khả năng ngắt khi giành lock, có các API phù hợp như tryLock(timeout, unit) và lockInterruptibly(), với điều kiện sử dụng đúng hợp đồng.

Với intrinsic lock, không có API **try-enter synchronized với timeout** trực tiếp tương đương, cũng không có tham số fairness được cấu hình. Thread đang chờ monitor enter không tự trở thành thread đã lấy monitor chỉ vì gọi interrupt() ở thread khác; cơ chế interrupt không phải lệnh ép monitor nhả.

Các tiện ích như CountDownLatch, Semaphore, BlockingQueue và AtomicInteger phục vụ mục đích khác nhau; hãy chọn chúng khi bài toán là chờ sự kiện, giới hạn số phép chạy đồng thời, trao dữ liệu, hoặc cập nhật nguyên tử một biến. Một monitor thường hợp lý khi cần bảo vệ bất biến ngắn, rõ ràng của trạng thái chia sẻ.

## 14. Hiệu năng, phạm vi và khả năng chẩn đoán

- **Giữ vùng synchronized ngắn và tập trung.** Đừng giữ monitor qua I/O mạng, sleep, chờ dài, callback có thể gọi ngược vào hệ thống hoặc tác vụ CPU nặng khi không cần cho bất biến.
- **Không biến mọi phương thức thành synchronized vô điều kiện.** Nếu dùng nhiều monitor khác nhau, phải giải thích quan hệ giữa dữ liệu và khóa; nếu dùng một monitor quá rộng, có thể tạo contention.
- **Không coi synchronized là luôn chậm.** JVM có tối ưu hóa; đánh giá bằng đo đạc ứng dụng thật và dữ liệu contention, thay vì dựa vào giả định từ các phiên bản JVM cũ.
- **Không đồng bộ hóa chỉ bên writer.** Reader và writer phải tuân thủ chiến lược memory visibility tương ứng.
- **Monitor không bảo vệ trạng thái giữa nhiều JVM/process.** Nếu dữ liệu được chia sẻ qua DB hay dịch vụ ngoài, cần giao thức ở nơi quản lý dữ liệu đó.
- **Quan sát thread dump khi nghi deadlock hoặc contention.** Stack trace, danh sách monitor đang giữ/chờ và trạng thái BLOCKED/WAITING giúp xác định đường khóa; kết hợp log có ID tác vụ và thời điểm để phân tích.
- **Thread.State không phải trạng thái nghiệp vụ.** Thread đang BLOCKED có thể đang xử lý một tác vụ RUNNING; thread TERMINATED không tự chứng minh công việc thành công.

### Bảng quyết định thực hành

| Nhu cầu | Cơ chế nên cân nhắc | Lý do |
| --- | --- | --- |
| Bảo vệ một bất biến nhiều bước trên một object trong JVM | synchronized(private final lock) | Mutual exclusion và happens-before qua cùng monitor |
| Một thao tác tăng số nguyên | AtomicInteger.incrementAndGet() | Một thao tác nguyên tử gọn, tránh monitor nếu không có bất biến phức tạp |
| Chờ một thread kết thúc | Thread.join() | Chờ completion thực tế, không đoán bằng sleep |
| Đợi tín hiệu một lần | CountDownLatch | Giao thức sự kiện rõ hơn tự viết wait/notify |
| Trao phần tử producer/consumer | BlockingQueue | Chờ và trao dữ liệu thread-safe theo API |
| Cần tryLock, timeout, interruptible acquisition | ReentrantLock | API tường minh phù hợp với yêu cầu |
| Bảo vệ trạng thái nhiều tiến trình | Cơ chế đồng bộ của nguồn dữ liệu chung | Monitor chỉ có phạm vi một JVM/classloader tương ứng |

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Hai object equals nhau dùng chung monitor | Khóa dựa trên identity, không dựa trên equals |
| synchronized bảo vệ toàn bộ object bất kể ai đọc/ghi | Chỉ code dùng giao thức khóa thích hợp mới nhận được bảo đảm |
| synchronized trên field đang thay reference vẫn là cùng khóa | Thay object khóa có thể tách đôi critical section |
| static synchronized khóa mọi instance | Nó khóa Class object; instance synchronized khóa this |
| Một thread không được vào cùng monitor hai lần | Intrinsic lock **reentrant** |
| sleep/yield/join/CountDownLatch.await làm nhả mọi monitor đang giữ | Chúng không tự nhả các monitor của caller |
| notify() lập tức chuyển CPU và monitor cho waiter | Notifier vẫn giữ monitor đến khi nhả; waiter phải tranh khóa và kiểm tra predicate |
| wait() và sleep() là như nhau | wait() trên object nhả **monitor của chính object đó** trong khi chờ; sleep() không nhả |
| Object.wait() luôn trở về khi điều kiện đúng | Có thể spurious wakeup, timeout, interrupt; dùng vòng while kiểm tra predicate |
| BLOCKED bao gồm mọi cách chờ | BLOCKED đặc biệt mô tả chờ intrinsic monitor enter |
| synchronized chỉ giúp tránh hai thread cùng chạy | Monitor unlock/lock còn có ngữ nghĩa happens-before về bộ nhớ |
| Một critical section được tách thành hai synchronized vẫn nguyên tử | Thread khác có thể chen giữa; phải giữ khóa trong toàn quyết định |
| Monitor tự động phòng deadlock | Hai hay nhiều monitor có thể tạo vòng chờ |
| Mọi object monitor đều là singleton lock toàn ứng dụng | Monitor của từng object có identity và phạm vi riêng |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Nếu hai biến a và b trỏ cùng một object, synchronized(a) và synchronized(b) có loại trừ nhau không?  
**Trả lời:** Có. Hai biểu thức yêu cầu cùng monitor vì identity object giống nhau.

**Câu 2.** Hai instance khác nhau gọi phương thức instance synchronized của cùng class có nhất thiết chặn nhau không?  
**Trả lời:** Không. Mỗi instance có monitor riêng, trừ khi code bên trong dùng thêm một monitor chung.

**Câu 3.** Static synchronized method lấy khóa nào?  
**Trả lời:** Monitor của Class object của lớp khai báo phương thức, ví dụ Example.class.

**Câu 4.** Tại sao phép tăng counter trong MonitorCounterDemo chính xác?  
**Trả lời:** Cả hai worker khóa cùng monitor trong toàn read–modify–write, nên không mất cập nhật; join đợi hoàn tất trước khi main in.

**Câu 5.** Khi thread đang giữ monitor rồi gọi Thread.sleep(100), thread khác có vào synchronized cùng monitor được không?  
**Trả lời:** Không, cho đến khi chủ sở hữu nhả monitor. Ngủ không đồng nghĩa nhả khóa.

**Câu 6.** Vì sao wait() phải đặt trong vòng while?  
**Trả lời:** Có thể spurious wakeup, nhiều waiter tranh điều kiện, hoặc điều kiện thay đổi trước khi reacquire monitor; phải kiểm tra lại predicate.

**Câu 7.** notifyAll() có khiến mọi waiter chạy cùng lúc trong critical section không?  
**Trả lời:** Không. Chúng vẫn phải lấy lại monitor và chỉ một thread có thể giữ monitor mỗi thời điểm.

**Câu 8.** Có thể xử lý deadlock bằng cách gọi interrupt() thread đang BLOCKED chờ monitor không?  
**Trả lời:** Không nên coi interrupt là cơ chế phá deadlock intrinsic monitor. Thiết kế lock ordering và tránh vòng chờ là cách phòng ngừa chính.

**Câu 9.** Nếu writer đồng bộ trên lock1 còn reader đồng bộ trên lock2 khác, có bảo đảm visibility không?  
**Trả lời:** Không thể suy ra từ hai synchronized đó. Phải dùng cùng một giao thức happens-before hoặc hình thức đồng bộ hóa khác đúng yêu cầu.

**Câu 10.** Một synchronized block có exception thoát ra sẽ giữ monitor mãi không?  
**Trả lời:** Không. Java tự nhả monitor khi rời synchronized do exception; nhưng các side effect dở dang không được tự rollback.

## 17. Kết luận

**Intrinsic lock** là quyền sở hữu monitor gắn với một object. synchronized dùng monitor đó để **loại trừ truy cập đồng thời** và thiết lập **happens-before** giữa các lượt khóa phù hợp. Instance synchronized khóa this; static synchronized khóa Class object; synchronized(expression) khóa chính object mà biểu thức đánh giá ra.

Khi thiết kế concurrency, hãy xác định **dữ liệu nào được bảo vệ bởi monitor nào**, giữ nguyên **identity** khóa, bao trùm **toàn bộ bất biến**, hạn chế giữ lock khi chờ lâu và dùng **wait/notifyAll với predicate trong while** nếu cần chờ điều kiện monitor. Với bài toán khác, chọn primitive JDK phù hợp thay vì biến mọi thao tác thành synchronized.
