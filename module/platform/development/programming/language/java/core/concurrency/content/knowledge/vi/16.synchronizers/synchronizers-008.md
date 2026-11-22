# Đếm permit và phòng tránh permit leak trong Java Synchronizers

## 1. Bài toán: giới hạn số công việc đồng thời phải luôn đúng

Một ứng dụng có thể chỉ cho phép tối đa ba yêu cầu cùng gọi dịch vụ ngoài, năm tác vụ cùng dùng connection đắt tiền, hoặc hai phép chuyển đổi dữ liệu nặng cùng chạy. Nếu không đặt giới hạn, hàng trăm thread có thể cùng tranh chấp tài nguyên, làm quá tải hệ thống.

`java.util.concurrent.Semaphore` là một synchronizer quản lý **số permit**. Một thread muốn đi vào đoạn code bị giới hạn phải **acquire** đúng số permit cần thiết; khi kết thúc quyền sử dụng tài nguyên, nó phải **release** đúng số permit đã lấy.

Trọng tâm của bài này là một bất biến rất đơn giản nhưng dễ làm sai:

> **Mỗi lần acquire thành công phải có đúng một lần release tương ứng, với đúng số permit; acquire không thành công thì không được release.**

Nếu lấy permit nhưng quên trả, hệ thống bị **permit leak**: khả năng phục vụ giảm dần, cuối cùng những công việc mới có thể chờ vô hạn. Nếu release quá số đã lấy hoặc release khi acquire thất bại, đó là **over-release**: hệ thống có thể cho phép nhiều công việc đi vào hơn giới hạn ban đầu, làm mất ý nghĩa của semaphore.

Bài thuộc phạm vi **Java concurrency nói chung**, tập trung vào API chuẩn của JDK, không dựa vào bất cứ framework riêng nào.

### Mục tiêu

Sau bài này, bạn cần:

1. Hiểu `Semaphore` là gì, `availablePermits()` phản ánh gì, và vì sao permit **không có ownership** như lock.
2. Viết đúng giao thức `acquire()`/`release()` và `tryAcquire()`/`release()`, kể cả timeout và interrupt.
3. Dùng `try/finally` đúng vị trí để không làm thất thoát permit hoặc trả permit chưa từng sở hữu theo logic nghiệp vụ.
4. Phân biệt **permit leak**, **over-release**, **double release**, **starvation** và **deadlock**.
5. Làm việc với `acquire(n)`, `release(n)`, fairness, shutdown và retry mà không phá bộ đếm.
6. Thiết kế phép đo, test và review để phát hiện lỗi trả permit trong workload đồng thời.
7. Biết khi nào nên dùng `Semaphore`, `BlockingQueue`, `ThreadPoolExecutor` hoặc tài nguyên tự quản lý khác.

## 2. Semaphore đếm permit như thế nào?

Một semaphore có một trạng thái permit count. Với `new Semaphore(3)`:

~~~text
Ban đầu:                    available = 3
Task A acquire():           available = 2
Task B acquire():           available = 1
Task C acquire():           available = 0
Task D acquire():           phải chờ
Task A release():           available = 1
Task D có thể acquire():    available = 0
~~~

Các thao tác acquire/release thay đổi trạng thái theo contract concurrency. Nhiều thread có thể gọi chúng cùng lúc mà không phải tự bảo vệ bộ đếm nội bộ bằng `synchronized`.

### 2.1. Ý nghĩa API chính

| API | Ý nghĩa và điều cần nhớ |
| --- | --- |
| `new Semaphore(permits)` | Tạo synchronizer với số permit ban đầu |
| `new Semaphore(permits, true)` | Chọn chính sách fair khi có thread cạnh tranh |
| `acquire()` | Chờ lấy một permit; có thể ném `InterruptedException` |
| `acquire(int n)` | Chờ lấy **n permit** theo thao tác đồng bộ của semaphore |
| `acquireUninterruptibly()` | Chờ mà không ném `InterruptedException` theo kiểu `acquire()`; cần cân nhắc cancellation |
| `tryAcquire()` | Thử lấy ngay một permit, trả boolean, không đợi |
| `tryAcquire(timeout, unit)` | Chờ có giới hạn nếu chưa lấy được permit, có thể bị interrupt |
| `tryAcquire(n, timeout, unit)` | Thử lấy n permit trong khoảng thời gian chỉ định |
| `release()` / `release(n)` | Trả đúng số permit theo protocol; không xác minh caller từng acquire |
| `availablePermits()` | Giá trị permit hiện có tại thời điểm đọc, **không phải reservation** |
| `drainPermits()` | Lấy hết các permit đang khả dụng và trả số đã lấy; API quản trị cấp thấp |
| `getQueueLength()` | Ước lượng số thread đang chờ acquire |
| `hasQueuedThreads()` | Gợi ý đang có waiter, không phải sự thật bất biến |
| `isFair()` | Cho biết semaphore được cấu hình fairness |

Các phương thức `acquire(n)` và `release(n)` yêu cầu n dương; n không hợp lệ có thể ném `IllegalArgumentException`. Dùng API nhiều permit thay vì lặp nhiều `acquire()` riêng khi một tác vụ cần **đồng thời** lấy đủ n permit trước khi bắt đầu. Điều đó tránh trạng thái “đã giữ một phần permit nhưng còn chờ nốt phần còn lại” của cách acquire lặp thủ công.

### 2.2. Semaphore không phải một lock có owner

`ReentrantLock` có thread sở hữu khóa; thread khác cố `unlock()` không đúng ownership sẽ bị từ chối. `Semaphore` **không buộc thread gọi release phải là thread đã acquire**: một thread có thể release permit mà thread khác lấy trước đó.

Đó là khả năng hữu ích cho một số giao thức handoff, nhưng cũng là nguồn lỗi:

~~~java
// SAI: không có chuyện Semaphore tự kiểm tra acquire trước đó.
// Một thread bất kỳ có thể tăng số permit bằng dòng này.
semaphore.release();
~~~

Chỉ vì `release()` không ném exception không có nghĩa bạn đã trả đúng permit. **Ownership của permit là một quy tắc do chương trình phải duy trì**, không được semaphore ép buộc.

### 2.3. Permit count không luôn là “capacity cố định”

Semaphore có thể được tạo với số permit bằng 0 để đóng vai trò **tín hiệu/permit producer-consumer**, hoặc với giá trị khác tùy giao thức. Java `Semaphore` còn cho phép các thao tác điều chỉnh thấp cấp. Vì vậy `availablePermits()` không phải một số luôn bị chặn phía trên bởi constructor.

Với cách dùng giới hạn đồng thời thông thường, ta đặt một **capacity logic N** và tự duy trì:

~~~text
0 <= availablePermits <= N
inFlight + availablePermits = N
~~~

Bất biến này chỉ đúng nếu mọi acquire/release thực sự tuân thủ giao thức và không có thao tác `drainPermits`, điều chỉnh permit hoặc cấp quyền ngoài quy tắc. `inFlight` cần được định nghĩa chính xác (số permit đã acquire nhưng chưa release), không đơn giản là số task đã submit.

## 3. Permit leak và over-release khác nhau như thế nào?

### 3.1. Permit leak

Một task gọi `acquire()` thành công, sau đó gặp exception, return sớm hoặc bị hủy nhưng không gọi `release()`. Mỗi permit bị mất khiến semaphore còn ít quyền vào hơn dự kiến.

~~~text
Capacity ban đầu: 3
Task A lấy 1 permit rồi thoát mà không release
Available tối đa về sau: 2
Task B lại leak 1 permit
Available tối đa về sau: 1
Task C tiếp tục leak permit
Available = 0, không còn tiến triển nếu không ai release
~~~

Đây không phải “rò rỉ object” hay “GC không thu hồi bộ nhớ”. Permit là **trạng thái đồng bộ**. Garbage collector không tự biết một tác vụ đã quên trả permit và không tự gọi `release()`.

### 3.2. Over-release

Task chưa acquire được permit nhưng gọi `release()`, hoặc một lần acquire lại có hai đường cleanup cùng release. Permit count có thể **vượt capacity logic**.

~~~text
Capacity logic N = 2
Available ban đầu = 2
Một release() nhầm -> available = 3
Ba task acquire() có thể cùng đi vào
=> giới hạn tối đa 2 đã bị phá.
~~~

Đối với semaphore giới hạn kết nối, over-release nguy hiểm không kém leak: thay vì throughput giảm, bạn có thể gây **quá tải hạ tầng ngoài**, lỗi tài nguyên và timeout dây chuyền.

### 3.3. Double release

Double release là một trường hợp over-release:

- `release()` trong `catch` rồi `release()` lại trong `finally`.
- Method bên trong tự release, method gọi bên ngoài cũng release.
- Một task timeout và cleanup release, sau đó callback hoàn tất cũng release.
- Retry logic giữ biến `acquired` sai, trả permit lần nữa sau attempt khác.

Cách giải quyết không phải chỉ “nhớ đừng release hai lần”, mà là xác định **một nơi có trách nhiệm release**, theo một quyền sở hữu logic rõ ràng.

## 4. Mẫu acquire/release an toàn nhất

### 4.1. Acquire bên ngoài, finally bên trong

Mẫu chuẩn với `acquire()`:

~~~java
// Mẫu Java, không phải chương trình độc lập.
semaphore.acquire(); // Có thể chờ và ném InterruptedException.
try {
    performProtectedWork();
} finally {
    semaphore.release();
}
~~~

**Vì sao acquire nằm trước try?** Nếu `acquire()` ném `InterruptedException` do chưa lấy được permit, không được chạy `release()`. Đặt `acquire()` phía ngoài bảo đảm chỉ đi vào khối `try/finally` khi acquire đã trở về thành công.

**Vì sao release nằm trong finally?** Nếu `performProtectedWork()` ném exception hoặc return, `finally` vẫn được gọi trong luồng điều khiển Java bình thường. Điều đó ngăn leak ở những đường thoát thông thường, không phải lời hứa trước crash JVM hoặc `Runtime.halt()`.

### 4.2. Mẫu nguy hiểm: finally ôm luôn acquire

~~~java
// SAI: nếu acquire bị interrupt trước khi thành công, vẫn release.
try {
    semaphore.acquire();
    performProtectedWork();
} finally {
    semaphore.release();
}
~~~

Nếu `acquire()` thất bại, đoạn này over-release. Đây là lỗi đặc biệt dễ mắc khi lập trình viên có thói quen “cứ thấy resource là đặt finally”.

Một mẫu thay thế khi cần nhiều nhánh phức tạp là giữ boolean `acquired`, đặt true **chỉ sau khi acquire thành công** và chỉ release khi boolean true. Nhưng nếu không thật sự cần, mẫu acquire trước try thường ngắn và khó sai hơn.

### 4.3. Kiểm soát vòng đời của tài nguyên ngoài

Gọi `release()` đúng lúc **quyền sử dụng tài nguyên hạn chế thực sự kết thúc**. Nếu bạn có một kết nối đang phục vụ I/O bất đồng bộ, release ngay sau khi **submit I/O** có thể quá sớm: request thật vẫn còn dùng connection nhưng permit đã trả cho request khác.

Ngược lại, giữ permit xuyên một thao tác callback không liên quan sau khi công việc giới hạn đã hoàn tất có thể làm giảm throughput. Xác định ranh giới tài nguyên trước khi chọn vị trí `try/finally`.

## 5. Ví dụ 1 — kế toán permit cơ bản (Java 17+)

Tạo tệp `PermitAccountingDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public class PermitAccountingDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(3);

        System.out.println("initial = "
            + semaphore.availablePermits());

        semaphore.acquire(2);
        System.out.println("after acquire(2) = "
            + semaphore.availablePermits());

        try {
            System.out.println("inside = true");
        } finally {
            semaphore.release(2);
        }

        System.out.println("after release(2) = "
            + semaphore.availablePermits());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PermitAccountingDemo.java
java PermitAccountingDemo
~~~

Stdout:

~~~text
initial = 3
after acquire(2) = 1
inside = true
after release(2) = 3
~~~

Hai permit được lấy trong một lời gọi `acquire(2)`; finally trả lại **đúng hai** bằng `release(2)`. Nếu chỉ trả một permit, available cuối là 2, thể hiện leak một permit. Nếu trả ba, available cuối là 4, thể hiện over-release một permit.

Không có thread khác trong ví dụ này, nên `availablePermits()` phản ánh bộ đếm tại các điểm xác định. Trong hệ thống nhiều thread, giá trị có thể thay đổi ngay sau khi quan sát.

### 5.1. Tại sao không lặp acquire từng permit?

Giả sử task cần hai permit nhưng viết:

~~~java
// Chỉ minh họa rủi ro với hai lời acquire độc lập.
semaphore.acquire();
semaphore.acquire();
try {
    doWork();
} finally {
    semaphore.release(2);
}
~~~

Nếu lần acquire thứ hai bị interrupt, lần đầu đã thành công nhưng khối finally chưa được thiết lập: **leak một permit**. Bài toán còn có thể gặp chờ kiểu hold-and-wait khi nhiều task cùng giữ permit một phần.

Ưu tiên `acquire(2)` khi cần hai permit cùng lúc; nếu phải lấy nhiều nguồn lực khác nhau, thiết kế giao thức rollback/lock ordering chặt chẽ.

## 6. tryAcquire: chỉ release khi thực sự thành công

`tryAcquire()` hoặc `tryAcquire(timeout, unit)` trả boolean:

- `true`: lời gọi đã **acquire đủ permit yêu cầu**.
- `false`: không có permit được cấp từ lời gọi đó; **không được release**.
- Phương thức timeout có thể ném `InterruptedException` khi bị ngắt; không được release cho lần gọi không thành công.

Mẫu chuẩn:

~~~java
// Mẫu Java, không phải chương trình độc lập.
boolean acquired =
    semaphore.tryAcquire(200, TimeUnit.MILLISECONDS);

if (!acquired) {
    return false;
}

try {
    performProtectedWork();
    return true;
} finally {
    semaphore.release();
}
~~~

Mẫu lỗi thường gặp:

~~~java
// SAI: over-release khi tryAcquire trả false.
try {
    if (!semaphore.tryAcquire()) {
        return;
    }
    doWork();
} finally {
    semaphore.release();
}
~~~

Vì `return` trong try **vẫn chạy finally**, nhánh tryAcquire false trên cũng `release()`. Một sai lầm nhỏ có thể làm số permit vượt capacity mà không có exception cảnh báo.

### 6.1. Ví dụ 2 — timeout không tạo permit giả (Java 17+)

Tạo tệp `TimedAcquireDemo.java`:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class TimedAcquireDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore permits = new Semaphore(1);
        permits.acquire();

        try {
            boolean gotAnother =
                permits.tryAcquire(0, TimeUnit.MILLISECONDS);

            System.out.println("second acquired = " + gotAnother);
            System.out.println("while held = "
                + permits.availablePermits());

            if (gotAnother) {
                permits.release();
            }
        } finally {
            permits.release(); // Trả permit ban đầu đúng một lần.
        }

        System.out.println("after = "
            + permits.availablePermits());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac TimedAcquireDemo.java
java TimedAcquireDemo
~~~

Stdout:

~~~text
second acquired = false
while held = 0
after = 1
~~~

Cùng một thread vẫn có thể gọi `tryAcquire` lần nữa vì semaphore **không có reentrancy/ownership** như một mutex; nhưng khi available bằng 0, lời thử với timeout 0 trả false. Vì thất bại không cấp permit nên không có release tương ứng.

Nhánh finally chỉ trả permit đã được `acquire()` thành công trước đó, do vậy kết quả cuối là 1 thay vì 2. Đây là một kiểm tra trực tiếp để phát hiện lỗi over-release.

## 7. InterruptedException: tại sao phải đặt finally đúng ranh giới?

`Semaphore.acquire()` là một phép chờ interruptible. Nếu thread bị interrupt trong lúc chờ, nó có thể ném `InterruptedException` mà **không có permit nào được cấp bởi lần acquire đó**.

Mẫu đúng:

~~~java
// Mẫu method trong code production; không độc lập.
void guardedJob() throws InterruptedException {
    semaphore.acquire();
    try {
        work();
    } finally {
        semaphore.release();
    }
}
~~~

Nếu `work()` cần phản hồi với interrupt ở giữa critical section, finally vẫn release khi method thoát do exception hoặc return. Nếu `acquire()` bị interrupt và không thành công, control không vào khối try nên không release.

### 7.1. Ví dụ 3 — worker bị interrupt khi chưa có permit (Java 17+)

Tạo tệp `InterruptedAcquireDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedAcquireDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(0);
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            entered.countDown();
            try {
                semaphore.acquire();
                try {
                    throw new AssertionError(
                        "This acquisition should not succeed"
                    );
                } finally {
                    semaphore.release();
                }
            } catch (InterruptedException ex) {
                noticed.set(true);
                Thread.currentThread().interrupt();
            }
        }, "waiting-worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("interrupted = " + noticed.get());
        System.out.println("available = "
            + semaphore.availablePermits());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac InterruptedAcquireDemo.java
java InterruptedAcquireDemo
~~~

Stdout khi không có tác động ngoài ví dụ:

~~~text
interrupted = true
available = 0
~~~

`entered` xác nhận worker đã tới vùng code trước khi main gửi interrupt, nhưng không cần bảo đảm nó đã chặn trong `acquire()`: nếu interrupt tới **trước** khi acquire, `acquire()` vẫn phản hồi bằng `InterruptedException`; nếu tới **trong lúc chờ**, kết quả cũng vậy. Không ai release một permit vào semaphore ban đầu bằng 0.

Dòng `semaphore.release()` chỉ nằm trong finally **sau** khi acquire đã trở về bình thường. Vì điều đó không thể xảy ra trong ví dụ có interrupt và không có producer permit, available cuối vẫn là 0. Việc khôi phục interrupt flag trong catch giúp tầng khác của worker biết tín hiệu đã tới, thay vì vô tình nuốt nó.

### 7.2. acquireUninterruptibly không có nghĩa “an toàn hủy hơn”

`acquireUninterruptibly()` đợi mà không truyền `InterruptedException` giống `acquire()`. Nó có thể tiếp tục chờ permit dù caller đã yêu cầu hủy. Trong hệ thống shutdown cần phản hồi nhanh, sử dụng nó bừa bãi có thể làm task mắc kẹt.

Khi không có lý do rõ ràng phải đợi không thể ngắt, ưu tiên `acquire()` hoặc `tryAcquire(timeout, unit)`, kết hợp deadline và chiến lược cancellation.

## 8. Giới hạn đồng thời thực tế với nhiều worker

Một semaphore giới hạn **số quyền vào đoạn code**, không giới hạn số task đã được gửi vào executor. Nếu 1.000 task được submit vào một pool và chỉ có hai permit, nhiều task có thể vẫn xếp hàng hoặc block trong acquire; việc đó có thể làm pool đầy, tăng latency và gây **thread pool starvation** khi các task trong pool lại phụ thuộc nhau.

### 8.1. Ví dụ 4 — ba task, tối đa hai permit (Java 17+)

Tạo tệp `BoundedWorkerDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedWorkerDemo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch twoEntered = new CountDownLatch(2);
        CountDownLatch releaseWork = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try {
            Future<?>[] tasks = new Future<?>[3];

            for (int i = 0; i < tasks.length; i++) {
                tasks[i] = pool.submit(() -> {
                    permits.acquire();
                    try {
                        twoEntered.countDown();
                        releaseWork.await();
                        completed.incrementAndGet();
                    } finally {
                        permits.release();
                    }
                    return null;
                });
            }

            twoEntered.await();
            System.out.println("available while held = "
                + permits.availablePermits());

            releaseWork.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("completed = " + completed.get());
            System.out.println("available after = "
                + permits.availablePermits());
        } finally {
            releaseWork.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BoundedWorkerDemo.java
java BoundedWorkerDemo
~~~

Stdout khi các task hoàn tất bình thường:

~~~text
available while held = 0
completed = 3
available after = 2
~~~

**Vì sao có thể kết luận?**

- Hai task đầu tiên lấy được permit sẽ `twoEntered.countDown()` rồi chờ `releaseWork`; lúc latch về 0, **chắc chắn có hai permit đang được giữ**.
- Task thứ ba chưa thể vượt qua acquire khi cả hai permit vẫn bị giữ, bất kể worker nào được scheduler chọn trước.
- Main in available = 0 rồi mở `releaseWork`. Tất cả ba task sẽ hoàn thành và mỗi task trả đúng một permit qua finally.
- `Future.get()` đợi từng task và chuyển lỗi của task thành `ExecutionException` nếu có; vì vậy dòng kết quả cuối không được in sớm.
- Không có worker nào in trực tiếp, nên thứ tự scheduler không làm thứ tự stdout thay đổi.

**Điểm cần nhìn xa hơn:** Một semaphore không tự đảm bảo fairness. Chương trình đúng về số permit nhưng không yêu cầu task được cấp permit theo thứ tự `submit`. Nếu SLA cần thứ tự chờ, xem xét fairness, loại queue hoặc mô hình worker riêng.

### 8.2. Giữ permit trong lúc block quá lâu

Nếu mỗi task giữ permit rồi đợi I/O không có timeout, hai permit có thể bị chiếm rất lâu. Đây không phải nhất thiết là **permit leak**: permit vẫn sẽ được trả nếu I/O kết thúc. Nhưng biểu hiện vận hành “available=0 kéo dài, queue tăng” có thể tương tự.

Để chẩn đoán, cần đo thời gian **giữ permit**, phân biệt task còn sống với task đã thoát, và biết downstream đang chặn ở đâu.

### 8.3. Không dùng semaphore để thay mọi loại queue

Nếu công việc đã được nhận nhưng cần **phân phối đúng một lần** cho các worker, `BlockingQueue.take()`/`poll()` hoặc `ThreadPoolExecutor` có queue bounded có thể biểu diễn ownership rõ hơn. Semaphore không lưu chính task và không tự xác nhận đã xử lý xong một task.

## 9. Over-release có thể xảy ra mà không có exception

Khác `ReentrantLock.unlock()`, `Semaphore.release()` không tra cứu owner. Do đó một lời gọi release sai có thể **làm tăng permit count** mà không ném `IllegalMonitorStateException`.

### 9.1. Ví dụ 5 — cố ý tạo lỗi over-release (Java 17+)

Tạo tệp `OverReleaseDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public class OverReleaseDemo {
    public static void main(String[] args) {
        Semaphore semaphore = new Semaphore(1);

        // SAI CÓ CHỦ Ý: chưa ai acquire nhưng lại release.
        semaphore.release();

        System.out.println("available = "
            + semaphore.availablePermits());
        System.out.println("limit violated = "
            + (semaphore.availablePermits() > 1));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OverReleaseDemo.java
java OverReleaseDemo
~~~

Stdout:

~~~text
available = 2
limit violated = true
~~~

Đây là **demo hành vi sai, không phải mẫu áp dụng**. Java không tự buộc available ≤ giá trị truyền vào constructor. Nếu coi constructor `Semaphore(1)` là mutex limit một tác vụ, việc gọi `release()` nhầm làm hai tác vụ khác có thể cùng acquire — phá ý nghĩa loại trừ.

### 9.2. Double release trong catch và finally

~~~java
// SAI: release hai lần khi doWork ném exception.
semaphore.acquire();
try {
    doWork();
} catch (RuntimeException ex) {
    semaphore.release();
    throw ex;
} finally {
    semaphore.release();
}
~~~

Cách sửa: **một finally duy nhất** chịu trách nhiệm release; catch chỉ ghi nhận/rethrow lỗi, không tự release nếu finally đã làm. Nếu một callback ngoài cũng release, phải xác định rõ việc bàn giao ownership; đừng để hai lớp cùng nghĩ mình có trách nhiệm cuối.

## 10. Dùng try-with-resources để giảm nguy cơ quên release

Khi một ứng dụng có nhiều method có thể return sớm, throw, hoặc gọi helper, một wrapper có ownership rõ ràng giúp review dễ hơn. Java cho phép dùng try-with-resources với một object `AutoCloseable` đại diện cho **permit lease**.

### 10.1. Thiết kế lease: acquire trước khi tạo token

Một lease nên:

- Được tạo **chỉ sau khi acquire thành công**.
- Biết số permit đã lấy và semaphore sẽ nhận release.
- Chỉ được close **một lần có tác dụng thực tế**, dù caller vô tình close lặp.
- Không chuyển quyền sở hữu sang nơi khác mà thiếu giao thức rõ.
- Không thực hiện I/O, logging hay logic nghiệp vụ bất định trong `close()`.

### 10.2. Ví dụ 6 — PermitLease AutoCloseable (Java 17+)

Tạo tệp `PermitLeaseDemo.java`:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class PermitLeaseDemo {
    static final class PermitLease implements AutoCloseable {
        private final Semaphore semaphore;
        private final int permits;
        private final AtomicBoolean closed = new AtomicBoolean();

        private PermitLease(Semaphore semaphore, int permits) {
            this.semaphore = semaphore;
            this.permits = permits;
        }

        static PermitLease acquire(
                Semaphore semaphore, int permits)
                throws InterruptedException {
            if (permits <= 0) {
                throw new IllegalArgumentException(
                    "permits must be positive"
                );
            }

            semaphore.acquire(permits);
            return new PermitLease(semaphore, permits);
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                semaphore.release(permits);
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(2);

        try (PermitLease lease =
                 PermitLease.acquire(semaphore, 2)) {
            System.out.println("inside = "
                + semaphore.availablePermits());
        }

        System.out.println("after close = "
            + semaphore.availablePermits());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PermitLeaseDemo.java
java PermitLeaseDemo
~~~

Stdout:

~~~text
inside = 0
after close = 2
~~~

`PermitLease.acquire` không tạo object lease trước khi semaphore `acquire(permits)` thành công. Nếu bị interrupt khi chờ, method ném exception và không có lease nào để close; không over-release. Sau khi acquire thành công, try-with-resources gọi `close()` ở cuối scope kể cả khi code bên trong ném exception hoặc return.

`AtomicBoolean` làm `close()` có hiệu lực đúng một lần nếu bị gọi lại. Đây là **bảo vệ ở cấp object lease**, không thay thế việc thiết kế ownership toàn hệ thống: hai lease khác nhau không được đại diện cho cùng một quyền permit nếu chưa có protocol chuyển giao.

### 10.3. Những giới hạn của wrapper

- `AutoCloseable` không làm resource ngoài tự được trả khi process chết. Nó chỉ tự gọi `close()` khi rời scope try-with-resources theo control flow Java.
- Không để lease bị giữ qua một tác vụ bất đồng bộ **ngoài lifetime của try** nếu tác vụ đó vẫn cần permit.
- Nếu một API thực sự cần bàn giao quyền release cho thread khác, phải dùng transfer-of-ownership rõ ràng; wrapper trong scope ban đầu có thể release quá sớm.
- Khi gói nhiều permit, nên tạo lease duy nhất có số permit chính xác, thay vì tạo nhiều lease cho cùng những permit đã acquire.
- Việc dùng `AtomicBoolean` tạo một allocation phụ, nên không mặc định lease wrapper là tối ưu throughput cho mọi hot path. Với code ngắn, một `try/finally` đúng có thể đơn giản và nhanh hơn.

## 11. Bulk permits: acquire(n) và release(n) phải cân bằng

Nếu một tác vụ tiêu thụ hai đơn vị capacity, ví dụ hai slot GPU logic, dùng `acquire(2)` và `release(2)`.

~~~java
// Mẫu Java, không phải chương trình độc lập.
semaphore.acquire(2);
try {
    processUsingTwoSlots();
} finally {
    semaphore.release(2);
}
~~~

Cần chú ý:

- Kiểm tra n > 0 và đúng với số permit cần theo nghiệp vụ.
- Không bao giờ acquire 2 nhưng release 1 hoặc 3.
- Nếu dùng `tryAcquire(2, timeout, unit)`, chỉ release(2) khi lời thử trả true.
- Nếu một task cần tất cả N permit để chạy thao tác độc quyền, nó có thể phải chờ lâu khi các task nhỏ liên tục lấy permit; cân nhắc fairness và starvation.
- Không trộn giữa giữ một permit rồi lại chờ thêm nhiều permit theo các đường code khác nhau nếu không có kế hoạch tránh deadlock và rollback.

### 11.1. Ví dụ 7 — thành công và thất bại khi cần hai permit (Java 17+)

Tạo tệp `BulkPermitDemo.java`:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class BulkPermitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(3);
        semaphore.acquire(2);

        try {
            boolean anotherTwo =
                semaphore.tryAcquire(
                    2, 0, TimeUnit.MILLISECONDS
                );

            System.out.println("second two = " + anotherTwo);
            System.out.println("available inside = "
                + semaphore.availablePermits());

            if (anotherTwo) {
                semaphore.release(2);
            }
        } finally {
            semaphore.release(2);
        }

        System.out.println("available after = "
            + semaphore.availablePermits());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BulkPermitDemo.java
java BulkPermitDemo
~~~

Stdout:

~~~text
second two = false
available inside = 1
available after = 3
~~~

Sau lần acquire(2) đầu, chỉ còn một permit. Lần tryAcquire(2, 0, ...) không lấy được đủ hai, trả false và không cấp permit nào. Chỉ có finally của lần acquire thành công release(2), nên tổng quay về 3.

**Không dùng giá trị `availablePermits()` để tự chia lấy permit:** giữa việc bạn đọc count và lời acquire, thread khác có thể thay đổi count. Nếu cần một tập n permit, hãy yêu cầu bằng `acquire(n)`/`tryAcquire(n, ...)` với atomic acquisition theo contract.

## 12. Fairness: ngăn barging không đồng nghĩa không leak

`new Semaphore(permits, true)` cho phép áp dụng chính sách **fair** tại các điểm acquisition theo API. Khi tranh chấp, nó ưu tiên thứ tự chờ theo các điểm xếp hàng nội bộ thay vì cho phép thread mới vượt lên liên tục như nonfair.

Nhưng fairness không giải quyết mọi vấn đề:

- **Permit leak**: một permit đã mất vẫn mất, bất kể fair.
- **Over-release**: `release()` sai vẫn tăng count; fair không kiểm tra ownership.
- **Owner giữ permit quá lâu**: những waiter vẫn phải chờ.
- **Deadlock đa tài nguyên**: hai task có thể giữ các permit/lock khác nhau rồi chờ nhau; fair không loại circular wait.
- **Scheduler fairness**: JVM/OS không đảm bảo mỗi task có CPU trong khoảng thời gian cố định.
- **Throughput**: fair có thể phải trả chi phí cấp quyền theo waiter cũ, nên có thể chậm hơn nonfair dưới contention.

### 12.1. Ngoại lệ của tryAcquire không timeout

`Semaphore.tryAcquire()` không tham số có thể lấy một permit **ngay lập tức nếu còn**, ngay cả khi semaphore fair và đã có waiter đang chờ. Tức phương thức này **cho phép barging**.

`tryAcquire(0, TimeUnit.SECONDS)` trên semaphore fair có thể dùng khi muốn thử không đợi mà vẫn tôn trọng fairness; dạng này có thể ném `InterruptedException`. Tương tự, `tryAcquire(n)` không timeout có chính sách barging của overload tương ứng.

Nếu yêu cầu ứng dụng là không cho task mới vượt hàng, phải xem **tất cả code path acquire**, không chỉ constructor `Semaphore(..., true)`.

### 12.2. Starvation không phải permit leak

Nếu một thread đợi rất lâu, chưa đủ chứng minh permit bị leak:

- Một thread khác đang giữ permit và thực sự làm việc quá lâu.
- Task chờ bị xếp lịch ít CPU.
- Nonfair barging làm waiter cũ chờ kéo dài.
- Task đang giữ một số permit trong lúc chờ tài nguyên khác.
- Một lỗi giao thức thật sự đã làm mất permit.

Cần đo owner/lifetime của permit và các trường hợp timeout thay vì chỉ nhìn queue length.

## 13. getQueueLength(), availablePermits() và quan sát

`availablePermits()` trả số permit khả dụng tại thời điểm đọc. `getQueueLength()` là **ước lượng** số thread chờ; `hasQueuedThreads()` chỉ là một quan sát tức thời. Ngay sau khi đọc, thread khác có thể acquire/release.

**Không dùng các giá trị này để tạo logic check-then-act như:**

~~~java
// SAI: có race giữa kiểm tra và acquire.
if (semaphore.availablePermits() > 0) {
    // Giả định chắc chắn acquire sẽ không chờ là sai.
    semaphore.acquire();
}
~~~

Thread khác có thể lấy permit ngay sau phép kiểm tra. Nếu muốn **không chặn**, dùng `tryAcquire()` và kiểm tra boolean; nếu có deadline, dùng overload timeout.

### 13.1. Số liệu hữu ích

| Metric | Ý nghĩa và giới hạn |
| --- | --- |
| Capacity logic | Số quyền vào tối đa được thiết kế |
| Available permits | Permit đang khả dụng; snapshot tức thời |
| In-flight permits | Số permit đã acquire chưa release theo protocol ứng dụng |
| Acquire latency p50/p95/p99 | Thời gian chờ để được cấp quyền |
| Hold duration p95/p99 | Thời gian permit được giữ |
| Timeout rate | Tỉ lệ task không lấy được permit trong deadline |
| Interrupt/cancellation count | Có bao nhiêu lần chờ bị ngắt |
| Estimated queue length | Gợi ý áp lực chờ, không phải số người đợi chính xác |
| Acquire/release event balance | Có event nào thiếu trả permit hoặc trả thừa không? |
| Work outcome | Task thành công/thất bại/hủy; không đồng nhất permit accounting |

Nếu ứng dụng dùng n-permit acquire, **đếm số lần acquire/release** không đủ; cần đếm **tổng số permit**. Một event acquire(3) phải được cân bằng với release(3), không phải với release() một lần.

### 13.2. Metric không làm thành một synchronization protocol

Nếu có nhiều thread cùng tăng metric “in-flight”, bản thân metric cũng phải thread-safe. Nhưng đừng đặt metric update ở vị trí khiến exception trong logger làm leak permit. Với code quan trọng, đơn giản hóa critical path, rồi quan sát bằng công cụ ít có thể thất bại.

Nếu muốn kiểm toán lịch sử, ghi nhận permit acquisition và release theo **một ID lease**, số permit và thời gian giữ. Không suy ra owner chỉ từ `availablePermits()` vì semaphore không biết owner của từng permit.

## 14. Các đường code dễ leak permit trong thực tế

### 14.1. Return sớm

~~~java
// SAI: return sớm khiến release bị bỏ qua.
semaphore.acquire();
if (!isValidRequest()) {
    return;
}
doWork();
semaphore.release();
~~~

Dùng finally:

~~~java
semaphore.acquire();
try {
    if (!isValidRequest()) {
        return;
    }
    doWork();
} finally {
    semaphore.release();
}
~~~

### 14.2. Exception ở giữa đường

~~~java
// SAI nếu process có thể ném exception.
semaphore.acquire();
process();
semaphore.release();
~~~

Ngay cả unchecked exception cũng làm bỏ qua dòng release nếu không có finally. Đừng chỉ catch một loại lỗi rồi release; hãy đặt release trong finally để bao phủ các đường thoát thông thường.

### 14.3. Timeout hoặc interrupt trước acquire

Nếu `tryAcquire(...)` trả false hoặc `acquire()` ném `InterruptedException`, không có permit được cấp bởi lời gọi đó. Một unconditional finally bên ngoài acquire khiến **over-release**, không phải leak. Cần xem mã trả permit và mã cấp permit là hai nửa của cùng giao thức.

### 14.4. Async callback

~~~java
// Sai thiết kế nếu externalCallAsync còn dùng tài nguyên
// sau khi hàm đã return.
semaphore.acquire();
try {
    externalCallAsync(); // Chỉ khởi động công việc.
} finally {
    semaphore.release(); // Quá sớm!
}
~~~

Cần xác định ai giữ lease cho tới khi callback/`CompletionStage` thực sự hoàn tất, và release đúng **một lần** trong đường success/failure/cancel. Nếu callback có thể được kích hoạt nhiều lần do bug hoặc API hứa at-most-once nhưng code có thêm fallback cleanup, phải có guard idempotent và ownership rõ ràng.

Cảnh giác với mẫu `whenComplete(... release)`: nếu bạn acquire trước khi tạo stage, nhưng bước tạo stage **ném exception đồng bộ trước khi đăng ký callback**, release sẽ bị bỏ qua. Hãy thiết kế việc chuyển ownership từ scope đồng bộ sang callback với trạng thái cụ thể, hoặc dùng wrapper lease được đóng đúng một lần.

### 14.5. Retry

Một task retry có thể acquire mới cho mỗi attempt. Mỗi attempt phải cân bằng permit của chính nó. Nếu muốn giữ permit xuyên mọi attempt, phải bảo đảm tổng thời gian giữ và deadline phù hợp; giữ permit khi ngủ backoff dài có thể làm nghẽn hệ thống dù không leak.

### 14.6. Nested acquire và dependency stall

Task A giữ permit rồi gọi task B cần **cùng semaphore**, trong khi capacity đã hết; nếu A block chờ B hoàn tất, có thể thành bế tắc phụ thuộc.

~~~text
Semaphore(1)
A: acquire -> available = 0
A: submit B và chờ kết quả
B: acquire -> chờ vì available = 0
A: không release cho đến khi B xong
=> B không thể vào; A không thể xong
~~~

Không có leak theo nghĩa bị mất permit, nhưng có **deadlock**. Thiết kế lại ownership: tránh giữ permit trong lúc chờ công việc phụ cũng cần permit, hoặc điều chỉnh phạm vi semaphore/luồng phụ thuộc.

## 15. Drain và giảm permit: API nâng cao cần cảnh giác

`Semaphore.drainPermits()` trả số permit khả dụng và đặt trạng thái khả dụng về 0 theo thao tác phù hợp. Nó có thể hữu ích cho vài giao thức quản trị, nhưng nếu không có ownership rõ ràng thì rất dễ “giữ” các permit đã drain rồi quên trả.

~~~java
// Minh họa API nâng cao; không phải chương trình độc lập.
int drained = semaphore.drainPermits();
try {
    reconfigureCapacity();
} finally {
    semaphore.release(drained);
}
~~~

Mẫu này chỉ phù hợp khi protocol của ứng dụng thực sự cần giữ số permit đã drain, và khi việc trả chúng đúng vào thời điểm cuối không phá giới hạn logic khác. Nếu có task đang giữ permit từ trước, drain **không thu hồi** những permit đang được sử dụng.

`reducePermits(int reduction)` là phương thức **protected** dành cho subclass và các giao thức đặc biệt; không coi nó là API công khai để arbitrary caller giảm capacity. Nếu triển khai dynamic capacity, phải thiết kế tương quan giữa available/in-flight/target capacity và các permit đã cấp, không chỉ gọi một method rồi suy ra số task được phép vào đã đổi ngay.

Không dùng `drainPermits()` như nút “hủy toàn bộ task”: nó chỉ lấy các permit còn khả dụng, không interrupt waiter và không thu hồi permit đang được task giữ.

## 16. Chọn Semaphore hay synchronizer khác?

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Giới hạn tối đa N đoạn code dùng cùng tài nguyên | `Semaphore(N)` | Đơn giản, có acquire/release và timeout |
| Giới hạn số task trong queue và số worker | `ThreadPoolExecutor` với bounded queue và rejection policy | Quản lý capacity task/pool, không chỉ quyền vào |
| Nơi có phần tử để producer/consumer trao đổi | `BlockingQueue` | Lưu item và cung cấp ownership tiêu thụ |
| Chờ một số hoạt động hoàn tất | `CountDownLatch` | Count-down một chiều, không cần trả permit |
| Đồng bộ nhiều thread theo pha | `CyclicBarrier` hoặc `Phaser` | Giao thức pha, không phải số slot |
| Bảo vệ invariant đa trường với một owner | `ReentrantLock` / `synchronized` | Lock ownership và mutual exclusion |
| Đồng thời nhiều reader nhưng writer độc quyền | `ReadWriteLock` | Semantics khác counting semaphore |
| Giới hạn số request/giây | Rate limiter/bucket có semantics thời gian | Semaphore giới hạn **concurrency**, không tự giới hạn rate |

**Ví dụ:** Capacity 10 permit và mỗi request xử lý 1 ms có thể cho throughput lớn; capacity 10 nhưng mỗi request giữ 10 s có thể throughput rất thấp. Semaphore không trực tiếp bảo đảm **10 request/giây**. Nếu cần rate limiting, phải đưa thời gian vào giao thức.

### 16.1. Semaphore(1) có thay mutex không?

`Semaphore(1)` có thể giới hạn một task cùng vào, nhưng **không có owner** và không reentrant theo kiểu `ReentrantLock`. Nếu bài toán cần bảo vệ state bằng một khóa, ownership và unlock nghiêm ngặt thường làm `ReentrantLock` hoặc `synchronized` dễ chứng minh đúng hơn.

Không gọi `Semaphore(1)` là mutex hoàn toàn tương đương khi bạn dựa vào hành vi của monitor hoặc lock ownership.

## 17. Kiểm thử permit leak và over-release

### 17.1. Không phụ thuộc lịch scheduler

Một test chỉ `Thread.sleep(50)` rồi đoán worker đã acquire không đáng tin trên máy CI bận. Dùng `CountDownLatch`, `Future.get()`, `join()` hoặc barrier để quan sát các điểm xác định.

Với code có thể block vô hạn do leak, test cần timeout khi chờ hoàn tất; nếu timeout, thu thread dump và làm cleanup có giới hạn, tránh làm cả test suite treo.

### 17.2. Những tình huống quan trọng

1. **Success path:** acquire thành công, doWork bình thường, release đủ.
2. **Unchecked exception:** doWork ném exception; finally vẫn release.
3. **Early return:** logic từ chối request; release vẫn xảy ra sau acquire.
4. **Acquire bị interrupt:** không release permit chưa lấy; khôi phục/propagate interrupt đúng.
5. **Timeout:** `tryAcquire` false; không gọi release.
6. **TryAcquire true:** có đúng một release cho lần thành công đó.
7. **Bulk permits:** acquire(n) được cân bằng bằng release(n).
8. **Nested ownership:** không có hai lớp cùng release một permit.
9. **Async completion:** release đúng một lần trên success/failure/cancel, không trả quá sớm.
10. **Cancellation:** task đang giữ permit bị interrupt; finally vẫn release.
11. **Contention:** số tác vụ đồng thời nằm trong vùng được bảo vệ không vượt capacity logic.
12. **Shutdown:** người đang chờ được hủy/đánh thức theo protocol; không giữ permit mãi vì task không chịu dừng.
13. **Over-release detector:** thử cố tình release trước acquire trên semaphore test riêng, xác nhận hệ thống test/linter/lease tracking có thể phát hiện hoặc ngăn lỗi ở tầng ứng dụng.
14. **Retries:** mỗi attempt tự cân bằng, không release lặp khi callback đến muộn.

### 17.3. Tự kiểm tra bất biến trong test

Nếu code đã bảo đảm không ai còn đang giữ permit và mọi task trong test đều đã hoàn tất, kiểm tra:

~~~java
// Mẫu assertion khi test đã chờ tất cả task xong;
// không phải chương trình độc lập.
if (semaphore.availablePermits() != initialCapacity) {
    throw new AssertionError("Permit imbalance");
}
~~~

**Cảnh giác:** Available quay về initial capacity chỉ chứng minh **net balance** tại thời điểm đó. Một leak và một over-release có thể triệt tiêu số học, nhưng hệ thống vẫn từng cho phép vượt capacity hoặc làm nghẽn. Test mạnh hơn cần theo dõi số permit đang thực sự giữ, max concurrent entries, một mã lease ID cho acquire/release và thời gian release.

Nếu có writer/caller khác vẫn thao tác semaphore, việc kiểm tra available bằng một giá trị cố định không còn có ý nghĩa; hãy đóng cửa nguồn task và chờ worker kết thúc trước khi assertion.

## 18. Checklist code review: mỗi permit có một đường trả rõ ràng

- Có capacity logic và số permit cần cho mỗi loại công việc được định nghĩa rõ?
- Mọi `acquire()` thành công đều vào **một finally** bảo đảm release?
- `acquire()` được đặt **trước** khối try/finally nếu không có flag acquired?
- Với `tryAcquire`, chỉ release khi boolean true?
- Với timeout/interrupt, có tránh release khi acquire chưa thành công?
- Với `acquire(n)`, có release **chính xác n** permit?
- Có đường return sớm, checked/unchecked exception, cancel, timeout, callback nào bỏ qua release?
- Có đường catch + finally hoặc wrapper + outer caller cùng release?
- Task có giữ permit lâu hơn vòng đời thực tế của tài nguyên không?
- Async operation có đảm bảo callback hoàn tất mới release, đồng thời không bỏ sót khi setup ném exception?
- Có giới hạn retry và xử lý idempotency, tránh leak giữa các attempt?
- Semaphore(1) có đang bị dùng như lock với yêu cầu ownership/reentrancy không?
- Có tác vụ giữ permit và đồng thời chờ task khác phải acquire cùng semaphore không?
- Fairness có được chọn trên số liệu throughput/starvation, không phải tin rằng fair sửa mọi leak?
- Có timeout và cancellation path để worker không chờ vô hạn nếu downstream bị treo?
- Có dùng `availablePermits()` làm metric thay vì “check rồi chắc chắn acquire được”?
- Có quan sát tổng permit in-flight và max concurrent entries trong test?
- Khi shutdown, những task giữ permit có chạy cleanup và chờ hoàn tất theo contract?
- Có tránh `drainPermits`/capacity adjustment mà không có protocol chính xác?
- Có phân biệt “tác vụ xử lý thất bại” với “quyền sử dụng slot phải được trả” trong mọi trường hợp?

## 19. Câu hỏi tự kiểm tra

**1.** Vì sao `try { semaphore.acquire(); work(); } finally { semaphore.release(); }` là mẫu sai?

Nếu `acquire()` bị interrupt trước khi thành công, finally vẫn `release()`; semaphore tăng permit dù caller chưa được cấp. Đặt acquire ngoài try, hoặc dùng flag acquired chặt chẽ.

**2.** `tryAcquire()` trả false. Có cần `release()` để “dọn dẹp” không?

Không. False nghĩa lời gọi đó chưa cấp permit; release sẽ là over-release.

**3.** Vì sao semaphore không tự phát hiện thread B trả permit mà thread A đã lấy?

Vì semaphore không ràng buộc permit với thread sở hữu như `ReentrantLock`. Đây là khả năng thiết kế, không phải lỗi JVM. Chương trình phải quản lý ownership logic.

**4.** `availablePermits() == 0` kéo dài có chắc là leak không?

Không. Có thể mọi permit đang được giữ bởi task chạy chậm, bị kẹt I/O, hoặc deadlock. Cần thêm thông tin holder, hold duration và lifecycle của worker.

**5.** Một task lấy ba permit mà trả hai permit là lỗi gì?

Permit leak **một permit**. Phải release đúng số đã acquire.

**6.** `release()` hai lần sau một acquire thành công có làm semaphore ném exception như `ReentrantLock.unlock()` không?

Không có owner check tương tự; available có thể tăng vượt capacity logic. Đây là over-release/double release.

**7.** Fair semaphore có ngăn mọi starvation và permit leak không?

Không. Fairness điều phối thứ tự waiter tại các điểm acquisition; không thu hồi permit bị mất, không ép owner trả, không sửa deadlock hay hủy sai.

**8.** Có nên giữ permit khi khởi chạy một việc bất đồng bộ rồi release ngay sau khi submit không?

Chỉ nếu quyền sử dụng tài nguyên **thực sự kết thúc** ngay sau submit. Nếu công việc bên trong còn dùng tài nguyên được giới hạn, release như vậy là quá sớm. Cần chuyển ownership release sang completion path.

**9.** Vì sao một latch là lựa chọn tốt để test giới hạn 2 permit?

Lập trình viên có thể giữ hai task đã acquire ở cùng một điểm chờ và xác nhận available = 0 trước khi cho chúng release, không phải đoán lịch scheduler bằng sleep.

**10.** Lúc shutdown, dùng `acquireUninterruptibly()` có nguy cơ gì?

Task đang chờ có thể không phản hồi yêu cầu interrupt để hủy nhanh; cần protocol riêng để đảm bảo liveness hoặc ưu tiên API interruptible.

**11.** `Semaphore(1)` có hoàn toàn tương đương với mutex không?

Không. Semaphore không ràng buộc owner/reentrancy như `ReentrantLock`. Chọn theo giao thức bạn cần bảo vệ.

**12.** Vì sao kiểm tra available bằng capacity sau khi test xong chưa đủ chứng minh không có lỗi?

Một leak và một over-release có thể bù trừ, hoặc hệ thống từng cho quá số task vào dù cuối cùng count cân bằng. Cần cả kiểm tra event balance và max concurrent entries.

## 20. Tài liệu JDK và kết luận

Để đối chiếu hành vi theo JDK:

- [Semaphore — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [ThreadPoolExecutor — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [BlockingQueue — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

**Quy tắc thực hành:**

~~~text
acquire() thành công:
    try { công việc bảo vệ } finally { release() }

tryAcquire() == true:
    try { công việc bảo vệ } finally { release() }

tryAcquire() == false:
    không được release

acquire() ném InterruptedException:
    không được release cho lời gọi đó
    propagate hoặc restore tín hiệu hủy theo hợp đồng

acquire(n) thành công:
    release(n) đúng một lần khi quyền sử dụng kết thúc
~~~

**Kết luận:** Semaphore chỉ giữ **bộ đếm permit**, không biết owner hay invariant nghiệp vụ. Để phòng permit leak và over-release, một acquire thành công phải chuyển thành một quyền sở hữu rõ ràng, có đúng một đường release ở cuối lifetime tài nguyên. Kết hợp `try/finally` hoặc một lease wrapper, xử lý timeout/interrupt chính xác, đo hold time và thiết kế test theo interleaving xác định để bảo toàn giới hạn đồng thời của ứng dụng.