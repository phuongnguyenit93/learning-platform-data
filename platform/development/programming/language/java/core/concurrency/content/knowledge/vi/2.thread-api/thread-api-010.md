# sleep(), yield() và các giới hạn khi điều phối thread trong Java

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích chính xác **Thread.sleep(...)** và **Thread.yield()** tác động đến **thread đang gọi** như thế nào.
- Phân biệt tạm ngừng theo thời gian, nhường cơ hội chạy và chờ một điều kiện/sự kiện.
- Xử lý **InterruptedException** khi thread đang ngủ, hiểu việc cờ interrupt bị xóa và cách khôi phục khi cần.
- Hiểu tại sao **sleep()** và **yield()** không đảm bảo thread khác chạy, không tạo đồng bộ hóa, không giải phóng monitor lock, không bảo đảm công bằng hay thứ tự chạy.
- Thay các cách điều phối dựa trên thời gian bằng cơ chế phù hợp của Java khi cần xác nhận hoàn thành, trao tín hiệu, quản lý tài nguyên hoặc chờ điều kiện.

Bài học thuộc **Java concurrency nói chung**, sử dụng API nền tảng của JDK; các cơ chế bất đồng bộ và quản lý task thuộc Spring là phạm vi riêng.

## 2. Bản chất việc điều phối thread

Trong một tiến trình Java có nhiều thread, mỗi thread có luồng lệnh và stack riêng; các thread có thể chạy xen kẽ trên một hoặc nhiều lõi CPU. JVM và hệ điều hành tham gia quyết định lúc nào thread được chạy. **Thread.State.RUNNABLE** bao gồm cả thread đang chạy và thread có thể được lập lịch chạy; trạng thái này không xác nhận thread đang chiếm CPU ở thời điểm quan sát.

Không có API Thread thông thường nào hứa rằng sau khi thread A tạm ngừng, thread B nhất định sẽ chạy ngay hoặc kết thúc trước A. Kết quả phụ thuộc vào scheduler, tải hệ thống, số CPU, ưu tiên, khóa, I/O và các thread khác. Hai chương trình giống nhau có thể cho thứ tự log khác nhau qua các lần chạy.

**sleep()** và **yield()** cùng thuộc lớp **java.lang.Thread**, đều là phương thức **static** tác động tới **thread hiện tại**:

- **Thread.sleep(...)**: đề nghị thread hiện tại ngừng thực thi ít nhất trong khoảng thời gian được yêu cầu theo khả năng đo thời gian của hệ thống, trừ khi bị ngắt. Khi hết thời gian, thread trở lại đủ điều kiện chạy; không có cam kết chạy lại ngay.
- **Thread.yield()**: đưa ra một **gợi ý** cho scheduler rằng thread hiện tại sẵn sàng nhường lượt sử dụng CPU. Scheduler có quyền bỏ qua hoàn toàn.

Cả hai phương thức đều **không phải primitive đồng bộ hóa** hay cơ chế chuyển điều khiển trực tiếp cho một thread cụ thể.

## 3. Thread.sleep(...): tạm dừng thread hiện tại

Các overload quan trọng trên Java 17:

~~~java
Thread.sleep(long millis);
Thread.sleep(long millis, int nanos);
~~~

Đây là chữ ký mô tả API, không phải các lời gọi đầy đủ; cả hai khai báo **throws InterruptedException**.

- **millis** biểu diễn số mili giây được yêu cầu. Giá trị âm gây **IllegalArgumentException**.
- Trong overload hai tham số, **nanos** là phần nano giây bổ sung, hợp lệ từ **0 đến 999_999**; giá trị ngoài phạm vi cũng gây **IllegalArgumentException**.
- Không nên suy luận độ chính xác nano giây từ overload có tham số nanos. Thời lượng thực tế chịu giới hạn của clock, độ phân giải timer và scheduler.
- **sleep(...)** không trả giá trị, không báo thread khác đã chạy bao lâu và không cam kết chính xác thời điểm thread tiếp tục.
- Viết **worker.sleep(100)** vẫn gọi phương thức static thông qua một tham chiếu (không nên làm): thread bị ngủ là **thread đang thực thi lời gọi**, không nhất thiết là đối tượng worker. Viết **Thread.sleep(100)** cho rõ ý định.

### Ví dụ 1: ngủ, khởi chạy và chờ kết thúc

Tệp **SleepJoinDemo.java**:

~~~java
public class SleepJoinDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("main: before start");

        Thread worker = new Thread(() -> {
            System.out.println("worker: before sleep");
            try {
                Thread.sleep(100);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("worker: interrupted");
                return;
            }
            System.out.println("worker: after sleep");
        }, "sleeper");

        worker.start();
        worker.join();
        System.out.println("main: after join");
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 SleepJoinDemo.java
java SleepJoinDemo
~~~

Khi không có ngắt bên ngoài, stdout:

~~~text
main: before start
worker: before sleep
worker: after sleep
main: after join
~~~

**Giải thích:**

1. **main** in dòng đầu trước khi gọi **start()**.
2. **worker** in dòng trước khi ngủ rồi gọi **Thread.sleep(100)** trên chính thread worker.
3. Khi khoảng ngủ kết thúc, worker được phép tiếp tục; nó có thể phải đợi scheduler cấp CPU.
4. **main** đang ở **worker.join()**, chỉ in dòng cuối sau khi worker hoàn thành.

Thứ tự ở ví dụ này ổn định nhờ chương trình và **join()**; **sleep(100)** không tạo ra thứ tự đó. Nếu có thread khác làm việc song song, thứ tự log của những thread đó không được bảo đảm.

### sleep() không phải đồng hồ chính xác

**sleep(100)** không có nghĩa là câu lệnh kế tiếp chắc chắn bắt đầu đúng sau 100 ms. Timer có độ phân giải nhất định, scheduler có thể cho thread tiếp tục trễ và lệnh ngủ có thể bị ngắt sớm. Đặt **sleep(10)** trong vòng lặp 100 lần cũng không bảo đảm tổng thời gian đúng một giây, bởi còn thời gian chạy logic mỗi vòng và độ trễ lập lịch.

Để **đo thời gian đã trôi qua**, dùng **System.nanoTime()** rồi lấy hiệu hai giá trị; không dùng trực tiếp thời gian đồng hồ lịch **System.currentTimeMillis()** làm thước đo đơn điệu cho độ trễ ngắn. Dù dùng nanoTime(), việc đo chính xác không làm cho scheduler chạy chính xác theo từng nano giây.

~~~java
long start = System.nanoTime();
Thread.sleep(100);
long elapsedNanos = System.nanoTime() - start;
System.out.println("elapsed ms = " + elapsedNanos / 1_000_000.0);
~~~

Đoạn trên là **mã minh họa**, cần đặt trong phương thức có xử lý/khai báo **InterruptedException**. Giá trị in ra thay đổi theo môi trường; không có stdout số cố định.

## 4. sleep() và interruption: dừng có hợp tác

**Thread.interrupt()** là tín hiệu yêu cầu thread hợp tác dừng hoặc hủy thao tác đang chờ. Nếu một thread bị interrupt trong lúc **sleep()**, lời gọi **sleep()** kết thúc bằng **InterruptedException**. Đồng thời, trạng thái interrupt của thread **được xóa khi exception được ném**. Nếu cờ đã được đặt trước khi gọi sleep(), lời gọi cũng có thể ném exception ngay và xóa cờ.

Vì **Runnable.run()** không cho checked exception thoát trực tiếp, mã trong run() thường cần bắt **InterruptedException**. Nếu task không thể xử lý yêu cầu dừng tại tầng hiện tại, cách phổ biến là **khôi phục cờ interrupt** bằng **Thread.currentThread().interrupt()** và kết thúc hợp tác.

### Ví dụ 2: interrupt một worker đang ngủ

Tệp **SleepInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class SleepInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                while (true) {
                    Thread.sleep(60_000);
                }
            } catch (InterruptedException ex) {
                System.out.println("worker: interrupted");
                Thread.currentThread().interrupt();
                System.out.println(
                    "worker: flag restored = "
                        + Thread.currentThread().isInterrupted()
                );
            }
        }, "sleeping-worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("main: worker done");
    }
}
~~~

~~~bash
javac -encoding UTF-8 SleepInterruptDemo.java
java SleepInterruptDemo
~~~

Stdout:

~~~text
worker: interrupted
worker: flag restored = true
main: worker done
~~~

**CountDownLatch** ở đây chỉ báo rằng worker đã tới điểm chuẩn bị ngủ; không khẳng định worker đã vào trạng thái TIMED_WAITING. Dù **interrupt()** đến trước hoặc trong khi ngủ, một lần sleep tiếp theo sẽ phát hiện yêu cầu ngắt; vòng lặp thoát qua catch. Dùng vòng lặp để kết quả không phụ thuộc vào việc main phải gửi tín hiệu trong đúng một lần ngủ. **join()** giữ main chờ đến khi worker đã kết thúc.

Không nên bắt InterruptedException rồi im lặng tiếp tục chạy vòng lặp vô hạn; thao tác đó có thể làm mất tín hiệu hủy. Nếu tầng gọi đã khai báo **throws InterruptedException** và phù hợp để xử lý, có thể để exception truyền lên. Nếu cần thoát sớm, dọn dẹp tài nguyên trong **finally** khi thích hợp.

Khác biệt của hai API đọc cờ:

| API | Đọc cờ của thread nào? | Có xóa cờ không? |
| --- | --- | --- |
| **thread.isInterrupted()** | Đối tượng thread được gọi | Không |
| **Thread.interrupted()** | Thread **hiện tại** | **Có** |

Không sử dụng **Thread.interrupted()** như một phép kiểm tra vô hại trong vòng lặp nếu không có chủ đích tiêu thụ tín hiệu ngắt.

## 5. sleep() không giải phóng monitor lock

Giả sử một thread đang ở trong **synchronized(lock)**. Khi nó gọi **Thread.sleep(...)**, thread ngủ nhưng **vẫn sở hữu monitor của lock** trong suốt phần synchronized cho đến khi rời khỏi phần đó. Thread khác muốn vào **synchronized(lock)** phải chờ, ngay cả khi CPU rảnh.

### Ví dụ 3: đối tượng lock vẫn được giữ

Tệp **SleepHoldsLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class SleepHoldsLockDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch hasLock = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (lock) {
                System.out.println("holder: acquired");
                hasLock.countDown();
                try {
                    Thread.sleep(100);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
                System.out.println("holder: leaving");
            }
        }, "lock-holder");

        holder.start();
        hasLock.await();

        synchronized (lock) {
            System.out.println("main: acquired");
        }

        holder.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 SleepHoldsLockDemo.java
java SleepHoldsLockDemo
~~~

Stdout (không có interrupt từ bên ngoài):

~~~text
holder: acquired
holder: leaving
main: acquired
~~~

Main chỉ tìm cách lấy lock sau khi latch báo holder đã giữ nó, và chỉ vào được synchronized sau khi holder rời khỏi synchronized. **sleep()** bên trong vùng khóa không tự mở khóa.

Điều này khác **Object.wait()**: phải gọi wait() khi đang sở hữu monitor của đối tượng, và thao tác wait() sẽ **nhả monitor của đối tượng đó trong khi chờ**, rồi lấy lại monitor trước khi wait() trả về bình thường. Với **ReentrantLock**, thao tác **Condition.await()** tương ứng sẽ nhả lock liên quan trong lúc chờ và lấy lại trước khi trở về. **sleep()** không làm những việc đó.

Hạn chế giữ lock trong khi thực hiện sleep, I/O hay chờ dài, vì các thread khác có thể bị chặn không cần thiết.

## 6. Thread.yield(): gợi ý nhường CPU, không phải lệnh chuyển lượt

**Thread.yield()** là phương thức **static void** không có tham số và không khai báo InterruptedException. Nó nói với scheduler rằng thread hiện tại sẵn lòng nhường quyền sử dụng CPU lúc này, nhưng **scheduler có thể bỏ qua gợi ý**.

Không có cam kết nào rằng:

- Thread hiện tại sẽ thực sự dừng, chuyển trạng thái hay mất CPU.
- Một thread cụ thể sẽ được chạy tiếp.
- Thread vừa yield sẽ bị xếp cuối hàng đợi.
- Thread có cùng ưu tiên sẽ được chạy công bằng kiểu round-robin.
- Một vòng lặp chứa yield() sẽ giúp task khác luôn có tiến độ.
- Yield sẽ giúp dữ liệu ghi từ thread khác trở nên nhìn thấy hoặc một điều kiện đúng.

**yield()** không ném InterruptedException, không đảm bảo delay tối thiểu và không có vai trò thay thế **sleep()**.

### Ví dụ 4: yield() không quyết định thứ tự thực thi

Tệp **YieldDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class YieldDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger completed = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                Thread.yield();
            }
            completed.incrementAndGet();
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("completed = " + completed.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 YieldDemo.java
java YieldDemo
~~~

Stdout:

~~~text
completed = 2
~~~

Kết quả luôn là 2 khi chương trình chạy bình thường, vì mỗi thread hoàn tất một lần tăng **AtomicInteger** và main đã **join()** cả hai. Không thể kết luận mỗi lệnh **yield()** đã nhường CPU hay hai thread luân phiên chạy. Không lấy ví dụ này làm benchmark: 10.000 lời gọi yield có thể tốn chi phí đáng kể mà không đem lại điều phối có ích.

Nếu chèn lệnh in tên thread bên trong vòng lặp, thứ tự các dòng của first và second có thể khác nhau trong mỗi lần chạy; không có stdout theo thứ tự cố định để kiểm thử.

### yield() vẫn giữ lock

Nếu gọi **Thread.yield()** trong **synchronized(lock)**, thread vẫn giữ monitor, giống như khi gọi sleep(). Các thread đang BLOCKED trên lock đó không vào được synchronized chỉ nhờ yield. Với lock khác như **ReentrantLock**, yield cũng không tự gọi unlock().

Do đó, thêm yield vào vùng khóa có thể tăng thời gian một thread giữ lock mà không tăng cơ hội cho thread đang chờ chính lock ấy.

## 7. Giới hạn sâu hơn: scheduling khác synchronization

Một chương trình concurrent cần giải quyết **hai vấn đề riêng**:

1. **Scheduling/progress:** thread nào được chạy, khi nào và trong bao lâu?
2. **Synchronization/memory visibility:** khi một thread ghi dữ liệu, thread khác có được thấy giá trị mới và được phép đọc/ghi đồng thời ra sao?

**sleep()** và **yield()** chỉ có thể ảnh hưởng đến lịch chạy; chúng **không tạo quan hệ happens-before**, không làm thao tác **count++** trở nên nguyên tử, không thay thế **volatile**, **synchronized**, lock, atomic types, blocking queues hoặc latch.

### Ví dụ phản tác dụng: chờ cờ bằng yield()

~~~java
class SharedState {
    boolean ready; // Không volatile.
}

// Mã minh họa lỗi, KHÔNG phải chương trình độc lập an toàn:
// Thread đọc cờ có thể không bao giờ quan sát được thay đổi.
SharedState shared = new SharedState();

Thread observer = new Thread(() -> {
    while (!shared.ready) {
        Thread.yield(); // Không đảm bảo visibility.
    }
});
observer.start();

shared.ready = true;
~~~

Đoạn trên **cố tình thiếu đồng bộ hóa** để minh họa lỗi. Việc cập nhật **ready** từ thread khác có data race; JMM không bảo đảm observer thấy thay đổi trong thời gian hữu hạn, kể cả có gọi **yield()** hoặc **sleep()** trong vòng lặp.

Đặt **ready** là **volatile** hoặc dùng **AtomicBoolean** giúp bảo đảm visibility phù hợp, nhưng vẫn còn một vòng lặp polling chiếm CPU hoặc tạo độ trễ. Khi cần **đợi sự kiện**, cách thích hợp hơn là **CountDownLatch.await()**, **BlockingQueue.take()**, **Object.wait()/notify()** khi có giao thức monitor đúng, hay **Condition.await()/signal()** đi kèm lock.

### Ví dụ 5: chờ tín hiệu thay cho sleep/yield polling

Tệp **SignalDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class SignalDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            System.out.println("worker: finished work");
            finished.countDown();
        }, "worker");

        worker.start();
        finished.await();
        System.out.println("main: observed completion");
        worker.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 SignalDemo.java
java SignalDemo
~~~

Stdout:

~~~text
worker: finished work
main: observed completion
~~~

Không có thời gian ngủ đoán trước. **await()** chờ cho đến khi đếm về 0 hoặc bị interrupt; **countDown()** tạo tín hiệu và các bảo đảm đồng bộ hóa tương ứng. Với trường hợp đơn thuần cần đợi một thread kết thúc, **join()** đã đủ; latch hữu ích khi tín hiệu cần biểu diễn một mốc công việc riêng, không nhất thiết là toàn bộ vòng đời của thread.

### Khi nhiều thread đang chờ

- **Thread.sleep(...)** chỉ đánh thức chính thread hiện tại sau khoảng thời gian dự kiến hoặc interruption; không có đối tượng điều kiện dùng chung.
- **Thread.yield()** không đánh thức một thread đang WAITING vì latch/monitor/condition.
- **Object.notify()/notifyAll()**, **CountDownLatch.countDown()**, **BlockingQueue.put(...)** và cơ chế condition phù hợp mới phát tín hiệu theo hợp đồng riêng của chúng.
- **join()** chờ một thread khác kết thúc; bản **join(timeout)** có thể trở về vì hết hạn khi thread đích còn sống, nên phải kiểm tra điều kiện sau khi chờ nếu cần chắc chắn.

## 8. Đọc Thread.State đúng cách

Trong các bản triển khai JVM thông thường, một thread đang ngủ sẽ được quan sát ở trạng thái **TIMED_WAITING**; sau khi khoảng ngủ hoàn thành, thread trở lại đủ điều kiện chạy. **yield()** không có một trạng thái Thread.State riêng tên là YIELDED. Đừng dùng getState() như một công cụ chứng minh một lệnh yield đã được scheduler tôn trọng.

| Tình huống | Trạng thái có thể quan sát | Điểm cần hiểu |
| --- | --- | --- |
| Thread vừa new, chưa start() | NEW | Chưa chạy |
| Thread đang chạy hoặc sẵn sàng chạy | RUNNABLE | Không bảo đảm đang chiếm CPU |
| Thread trong Thread.sleep(...) | TIMED_WAITING | Có deadline, vẫn giữ các lock đã sở hữu |
| Thread chờ monitor vào synchronized | BLOCKED | Đang chờ giành monitor |
| Thread đang join() không timeout | WAITING | Đang chờ thread khác kết thúc |
| Thread đã kết thúc run() | TERMINATED | Không thể start lại |

**getState()** là ảnh chụp tức thời; trạng thái có thể đổi ngay sau lần đọc. Không viết logic kiểu “đợi đến khi thread có state TIMED_WAITING rồi mới gửi interrupt” để đồng bộ: đây là race do quan sát trạng thái. Hãy dùng latch hoặc giao thức tín hiệu rõ ràng khi cần xác nhận một mốc.

## 9. Bảng so sánh: chọn đúng công cụ

| API | Mục đích chính | Điều gì làm việc chờ kết thúc? | Có tự nhả monitor đang giữ? | Bảo đảm về thread khác |
| --- | --- | --- | --- | --- |
| **Thread.sleep(duration)** | Tạm dừng thread hiện tại theo thời gian | Hết thời hạn hoặc InterruptedException | Không | Không bảo đảm thread nào chạy |
| **Thread.yield()** | Đưa hint nhường lượt CPU | Trả về theo quyết định triển khai/scheduler | Không | Không bảo đảm hint được chấp nhận |
| **Thread.join()** | Chờ thread đích kết thúc | Thread đích kết thúc; hoặc interruption/timeout | Không tự nhả monitor tùy ý của caller | Đợi đúng thread đích, có quy tắc memory ordering |
| **Object.wait()** | Đợi điều kiện qua monitor | notify/notifyAll, interrupt, timeout hoặc wakeup giả | Nhả monitor **của đối tượng đang wait** trong lúc đợi | Phải kiểm tra điều kiện trong vòng lặp |
| **CountDownLatch.await()** | Đợi số lần báo sự kiện đạt 0 | countDown đủ, interrupt hoặc timeout tương ứng overload | Không tự nhả monitor tùy ý | Giao thức đồng bộ hóa với countDown |
| **BlockingQueue.take()** | Đợi một phần tử | Có phần tử hoặc interrupt | Không tự nhả monitor tùy ý | Trao đổi dữ liệu thread-safe |

Lưu ý: “không tự nhả monitor” chỉ nói về lock **đã được caller sở hữu**; các công cụ concurrent có thể dùng lock nội bộ của chúng theo cách riêng. Với **Object.wait()**, thread phải sở hữu đúng monitor và sau khi được đánh thức cần tái giành monitor trước khi tiếp tục.

## 10. Các anti-pattern cần tránh

### Dùng sleep() thay cho join()

~~~java
worker.start();
Thread.sleep(100);
System.out.println("worker chắc đã xong"); // Giả định sai.
~~~

Worker có thể mất hơn 100 ms, bị thiếu CPU hoặc chờ I/O/lock. Khi cần đợi thực sự, gọi **worker.join()** (và xử lý InterruptedException) hoặc chờ tín hiệu hoàn tất tương ứng.

### Dùng sleep() làm hàng rào bộ nhớ

~~~java
shared.ready = true;
Thread.sleep(10);
// Không suy ra thread khác đã thấy shared.ready.
~~~

Đây là minh họa lỗi; giả định **shared** đã được khai báo. **sleep()** không thay thế cơ chế công bố giá trị chia sẻ an toàn.

### Dùng yield() để sửa race condition

~~~java
while (!state.ready) {
    Thread.yield();
}
~~~

Đoạn này cũng là minh họa lỗi nếu **state.ready** không được đồng bộ hóa. Yield không sửa data race, có thể gây busy waiting và có thể bị scheduler bỏ qua. Nếu bắt buộc polling, dùng visibility đúng và giới hạn/pacing phù hợp; ưu tiên chờ có tín hiệu.

### Ngủ trong synchronized rồi kỳ vọng thread khác vào được

~~~java
synchronized (lock) {
    Thread.sleep(1000);
}
~~~

Đây là đoạn minh họa trong phương thức đã khai báo/đã xử lý InterruptedException; **lock** là đối tượng đã có. Thread khác muốn vào synchronized(lock) phải đợi cho đến khi đoạn synchronized kết thúc.

### Dùng yield() làm cơ chế fairness

Lặp đi lặp lại yield() không thiết lập công bằng, giới hạn starvation hay thứ tự cố định. Thiết kế dựa vào **giao thức trao quyền** rõ ràng nếu có yêu cầu lần lượt; ví dụ Semaphore/BlockingQueue/lock theo nhu cầu, sau đó vẫn phải xem bảo đảm fairness cụ thể của từng API. Scheduler không có nghĩa vụ đáp ứng công bằng chỉ vì thread gọi yield.

### Đo “hiệu năng” bằng một lần sleep/yield

Một lần thử chịu nhiễu do JIT, GC, system load, CPU frequency, scheduler và I/O; không thể lấy thời gian chờ ngủ làm CPU-time của công việc. Khi nghiên cứu latency, phân biệt **wall-clock elapsed time**, CPU time và thời gian thread bị BLOCKED/WAITING; đo lặp lại bằng công cụ phù hợp và nêu rõ môi trường.

## 11. Khi nào có thể dùng sleep() hoặc yield()?

**sleep() có ích** khi thật sự muốn trì hoãn một công việc, thử nghiệm có chủ đích độ trễ, hoặc điều tiết polling đơn giản trong điều kiện chấp nhận độ trễ và có đường hủy đúng. Đối với lịch chạy định kỳ, tác vụ nhiều thread hoặc deadline quan trọng, dùng **ScheduledExecutorService**, timeout có điều kiện, hoặc bộ lập lịch phù hợp; các công cụ này cũng không thể hứa timing tuyệt đối, nhưng cho API quản lý tác vụ và hủy rõ ràng hơn.

**yield()** thường hiếm cần trong ứng dụng nghiệp vụ. Nó đôi khi hữu ích trong thử nghiệm, quan sát ứng xử khi lập lịch, hoặc một số kỹ thuật tối ưu hóa rất đặc biệt đã được đo kiểm; ngay cả khi đó phải chấp nhận scheduler có thể bỏ qua. Không dùng yield làm giải pháp mặc định cho chờ trạng thái, giảm CPU hoặc tránh deadlock.

Java 21 còn có **virtual threads** và các đặc điểm lập lịch khác so với platform threads; nhưng nguyên tắc nền tảng vẫn đúng: không lấy **sleep()** và **yield()** làm hợp đồng đồng bộ hóa, thứ tự thực thi hoặc fairness. Các ví dụ thực hành ở bài này dùng API Java 17+.

## 12. Câu hỏi tự kiểm tra

**1. Nếu gọi Thread.sleep(200) từ main, một đối tượng Thread tên worker có bị ngủ không?**  
Không. Sleep là static; **main** bị ngủ vì nó thực thi lời gọi. Muốn worker tự ngủ, mã chạy trong worker phải gọi sleep.

**2. yield() có đảm bảo thread khác cùng độ ưu tiên được chạy không?**  
Không. Chỉ là một hint có thể bị bỏ qua. Thread vừa yield cũng có thể chạy tiếp.

**3. Thread đang giữ monitor rồi sleep() có nhả monitor không?**  
Không. Thread khác cần monitor đó vẫn phải chờ. **Object.wait()** trên cùng monitor có cơ chế nhả/reacquire khác.

**4. Sau sleep(1000), công việc chắc chắn chạy lại đúng 1 giây không?**  
Không. Scheduler có thể cho chạy muộn; interrupt có thể khiến sleep kết thúc sớm bằng exception.

**5. Có thể dùng while (!ready) { Thread.yield(); } để bảo đảm đọc được cập nhật từ thread khác không?**  
Không. Yield không tạo happens-before và không giải quyết data race. Cần visibility/synchronization đúng và nên chờ qua tín hiệu khi có thể.

**6. Nếu ngủ bị interrupt, vì sao nhiều ví dụ gọi Thread.currentThread().interrupt() trong catch?**  
Vì khi **sleep()** ném **InterruptedException**, cờ đã bị xóa. Khôi phục cờ giúp tầng xử lý sau còn nhận biết yêu cầu ngắt, nếu đó là chính sách xử lý phù hợp.

**7. Nếu chỉ muốn main đợi worker hoàn tất, chọn sleep(100) hay worker.join()?**  
Chọn **join()**: nó đợi sự kiện hoàn tất thật sự của worker thay vì đoán một độ trễ.

## 13. Ghi nhớ

**Thread.sleep(...)** yêu cầu thread hiện tại tạm dừng theo thời gian; có thể bị interrupt và **không nhả lock**. **Thread.yield()** là một gợi ý cho scheduler, có thể bị bỏ qua và **không có bảo đảm tiến độ**. Cả hai đều **không tạo đồng bộ hóa hay memory visibility**. Khi bài toán thực chất là “đợi công việc xong”, “đợi trạng thái thay đổi”, “trao tín hiệu” hoặc “bảo đảm thread-safe”, hãy dùng API tương ứng như **join**, **CountDownLatch**, **BlockingQueue**, **synchronized/Condition** hoặc atomic/volatile theo đúng yêu cầu.
