# Fairness policy: throughput và starvation trong Java Locks & Conditions

## 1. Vì sao chính sách fairness ảnh hưởng tới ứng dụng đồng thời?

Khi nhiều thread cùng muốn vào một vùng **critical section**, khóa quyết định thread nào có quyền tiếp tục khi tài nguyên sẵn sàng. Nếu một số thread được vào liên tục còn những thread khác phải chờ rất lâu, hệ thống có thể có thông lượng tốt ở mức tổng thể nhưng trải nghiệm của từng công việc không đồng đều.

Trong Java, `ReentrantLock`, `ReentrantReadWriteLock` và `Semaphore` có tùy chọn **fairness**. Đây là chính sách về **thứ tự ưu tiên cấp quyền khi có cạnh tranh**, không phải lời hứa rằng mọi thread hoặc mọi request đều hoàn thành trong thời gian bằng nhau.

Ba khái niệm cần tách riêng:

- **Fairness (tính công bằng):** mức độ cơ chế cấp quyền tôn trọng các thread đã chờ trước khi thread mới đến.
- **Throughput (thông lượng):** số công việc hoàn tất trong một đơn vị thời gian, ví dụ giao dịch/giây hoặc số lần vào critical section/giây.
- **Starvation (đói tài nguyên):** một thread có thể phải chờ kéo dài bất thường hoặc không đạt tiến triển do những thread khác tiếp tục nhận tài nguyên.

Điểm quan trọng: **fairness mạnh hơn có thể làm giảm thông lượng**, đặc biệt khi có nhiều thread tranh chấp một khóa và việc chuyển quyền đòi hỏi đánh thức/chuyển ngữ cảnh. Ngược lại, cấu hình không công bằng thường tận dụng tốt cơ hội thread đang chạy tiếp tục lấy khóa, nhưng có thể tạo độ trễ đuôi rất lớn cho một số waiter.

Bài này chỉ bàn về API và hành vi concurrency **thuần Java**, không liên quan cấu hình framework.

### Kết quả học tập

Sau bài này, bạn cần:

1. Phân biệt `ReentrantLock(true)` và `ReentrantLock(false)`; hiểu `fair` không có nghĩa “FIFO tuyệt đối”.
2. Giải thích **barging**, lock convoy, starvation và sự đánh đổi giữa throughput với p95/p99 wait time.
3. Nhận diện ngoại lệ quan trọng của `tryLock()` đối với fair lock.
4. Hiểu `Condition.await()`, `signal()`, `signalAll()` và việc reacquire lock có quan hệ gì với chính sách fairness.
5. Phân biệt fairness của khóa với fairness của `Semaphore` và `ReentrantReadWriteLock`.
6. Viết Java 17+ có thể chạy, và biết thiết kế benchmark/kiểm thử thay vì kết luận từ một lần quan sát scheduler.

## 2. Fair và nonfair thực chất khác nhau ở đâu?

### 2.1. Nonfair lock: cho phép barging

Với `new ReentrantLock()` hoặc `new ReentrantLock(false)`, mặc định khóa là **nonfair**. Một thread mới đến có thể giành được khóa dù đã có thread khác đợi, tùy trạng thái và cách triển khai cấp khóa. Hành vi một thread đến sau vượt lên trước waiter thường gọi là **barging**.

Điều này đôi khi có ích cho throughput: thread đang chạy trên CPU có thể lấy khóa ngay, thay vì phải đánh thức một thread đang ngủ và chờ nó được lập lịch. Những khoản chi phí chuyển ngữ cảnh, cache locality và scheduling có thể giảm đi.

Nhưng nếu nhiều “khách mới” liên tục giành quyền, một waiter cụ thể có thể chờ rất lâu. Càng cạnh tranh mạnh, việc chỉ đo số giao dịch trung bình càng có nguy cơ che mất độ trễ rất lớn của nhóm waiter kém may mắn.

### 2.2. Fair lock: ưu tiên waiter đã chờ lâu

`new ReentrantLock(true)` yêu cầu chính sách fair. Theo hợp đồng API, khi có tranh chấp, fair lock **ưu tiên cấp khóa cho thread có thời gian chờ lâu nhất**. Chính sách này giúp giảm khả năng một thread chờ lock bị bỏ lại liên tục bởi các thread đến sau.

Tuy vậy, Java documentation lưu ý rất rõ: **fairness của lock không bảo đảm fairness của scheduler**. Một thread có thể được cấp khóa nhiều lần trong một giai đoạn trong khi thread khác chưa được CPU lập lịch; việc chờ lock chỉ là một phần vòng đời task.

Một fair lock cũng không buộc hai thread phải **bắt đầu** đúng thứ tự chúng được tạo, `start()` hay enqueue task. Chính sách áp dụng tại những điểm cạnh tranh khóa theo hợp đồng, không tạo thứ tự toàn cục cho toàn bộ ứng dụng.

### 2.3. So sánh khái quát

| Tiêu chí | Nonfair `ReentrantLock` | Fair `ReentrantLock(true)` |
| --- | --- | --- |
| Mặc định của `ReentrantLock()` | Có | Không |
| Quyền barging với `lock()` khi có waiter | Có thể | Thường nhường ưu tiên cho waiter chờ lâu |
| Mục tiêu điển hình | Throughput cao trong workload cạnh tranh | Giảm chênh lệch thời gian chờ cấp khóa |
| Độ trễ đuôi của một waiter | Có thể rất xấu | Thường dễ kiểm soát hơn, không có deadline tuyệt đối |
| Context switching / handoff | Có thể tiết kiệm hơn | Có thể tốn hơn khi tranh chấp mạnh |
| Loại bỏ deadlock | Không | Không |
| Bảo vệ shared mutable state nếu mọi đường truy cập cùng khóa | Có | Có |
| Bảo đảm scheduler cấp CPU công bằng | Không | Không |

Khi **ít hoặc không có contention**, việc bật fairness có thể không tạo lợi ích quan sát được; chỉ khi workload thực sự có nhiều waiter, chính sách này mới thành vấn đề vận hành đáng cân nhắc.

## 3. Cấu hình và quan sát fairness với ReentrantLock

Cách khai báo:

~~~java
// Minh họa cấu hình; đoạn này không phải chương trình độc lập.
ReentrantLock defaultLock = new ReentrantLock();
ReentrantLock explicitlyNonfair = new ReentrantLock(false);
ReentrantLock fairLock = new ReentrantLock(true);

System.out.println(defaultLock.isFair());       // false
System.out.println(explicitlyNonfair.isFair());  // false
System.out.println(fairLock.isFair());           // true
~~~

`isFair()` báo **chính sách đã cấu hình**, không báo số lần mỗi thread được cấp khóa hoặc xác nhận latency đã công bằng. Muốn đánh giá hiệu quả, phải đo thời gian chờ, thời gian giữ khóa, throughput, số lần timeout/rejection và độ trễ tổng thể.

### 3.1. Ví dụ 1 — nhiều thread dùng fair lock (Java 17+)

Ví dụ sau xác minh kết quả cập nhật dùng chung và cho thấy nơi cấu hình fairness. Nó cố ý **không khẳng định thứ tự thread vào khóa**: thứ tự đó có thể thay đổi theo scheduler.

Tạo tệp `FairCounterDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class FairCounterDemo {
    static final class Counter {
        private final ReentrantLock lock;
        private int value;

        Counter(boolean fair) {
            lock = new ReentrantLock(fair);
        }

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int value() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }

        boolean isFair() {
            return lock.isFair();
        }
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter(true);
        ExecutorService executor = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);
        Future<?>[] tasks = new Future<?>[4];

        try {
            for (int i = 0; i < tasks.length; i++) {
                tasks[i] = executor.submit(() -> {
                    try {
                        start.await();
                        for (int j = 0; j < 1000; j++) {
                            counter.increment();
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("fair = " + counter.isFair());
            System.out.println("count = " + counter.value());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FairCounterDemo.java
java FairCounterDemo
~~~

Stdout khi task không bị interrupt và hoàn thành bình thường:

~~~text
fair = true
count = 4000
~~~

Bốn worker cùng chờ latch mở, mỗi worker tăng bộ đếm 1.000 lần. `ReentrantLock` bảo vệ phép `value++` nên tổng bằng 4.000. `isFair()` là `true` vì constructor chọn chính sách fair. `Future.get()` giúp caller đợi từng task hoàn tất và nhận lỗi nếu task bị exception không được xử lý.

**Điều ví dụ không chứng minh:** Nó không đo fair lock nhanh/chậm hơn nonfair lock, không chứng minh một thread cụ thể được cấp khóa trước, và không cho biết độ trễ đuôi của waiter. Thay `Counter(true)` bằng `Counter(false)` vẫn cho tổng 4.000 nếu cùng khóa bảo vệ mọi cập nhật; khác biệt nằm ở **chính sách tranh chấp**, không ở correctness của phép đếm đã khóa.

Nếu task bị interrupt trong `start.await()`, nó sẽ khôi phục interrupt flag rồi bỏ qua vòng tăng; vì thế điều kiện “task hoàn tất bình thường” ở output còn bao gồm việc không có hủy/interrupt từ bên ngoài. Trong code sản phẩm, nên quyết định rõ cách trả thất bại khi task bị hủy thay vì chỉ bỏ qua phần việc.

### 3.2. Tại sao phải unlock trong finally?

~~~java
// Minh họa trong một phương thức; lock đã được khai báo.
lock.lock();
try {
    mutateSharedState();
} finally {
    lock.unlock();
}
~~~

Fairness **không** giúp nếu một thread giữ khóa rồi thoát do exception mà không release. `ReentrantLock` không tự mở khóa khi rời method như `synchronized`. Cần `finally` và tránh giữ khóa xuyên qua I/O không giới hạn, callback không kiểm soát hoặc sleep dài.

## 4. Ngoại lệ cần nhớ: tryLock() có thể barging ngay cả trên fair lock

Một nhầm lẫn quan trọng là suy ra `new ReentrantLock(true)` khiến **mọi cách lấy khóa** tuân thủ hàng đợi.

Thực tế, theo hợp đồng `ReentrantLock`:

- `lock()` trên fair lock áp dụng chính sách ưu tiên waiter khi có contention.
- `lockInterruptibly()` cho phép chờ có thể ngắt, vẫn tuân thủ chính sách fair của khóa.
- `tryLock()` **không có timeout** sẽ lấy khóa ngay nếu khóa đang rảnh, **kể cả khi các thread khác đang chờ**, tức cho phép **barging dù lock được cấu hình fair**.
- `tryLock(timeout, unit)` trên fair lock tôn trọng chính sách fairness khi chờ quyền lấy khóa và có thể bị interrupt.
- Theo hướng dẫn API, `tryLock(0, TimeUnit.SECONDS)` có thể dùng khi muốn thử lấy ngay mà vẫn tôn trọng fairness; khác `tryLock()` không tham số. Lưu ý dạng có timeout có thể ném `InterruptedException`.

Điều này có ý nghĩa nếu code vừa dùng `lock()` ở đường chính vừa dùng `tryLock()` không tham số ở đường khác: đường thử nhanh có thể vượt lên trước những waiter đang được xếp hàng. Không nên tuyên bố “không starvation vì lock đã fair” nếu ứng dụng còn nhiều đường barging.

### Ví dụ 2 — tryLock không chặn vô thời hạn (Java 17+)

Tạo tệp `TryLockWaitDemo.java`:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ReentrantLock lock = new ReentrantLock(true);
        lock.lock(); // Luồng main đang giữ khóa.

        try {
            Thread worker = new Thread(() -> {
                boolean immediate = lock.tryLock();
                System.out.println("immediate = " + immediate);

                if (immediate) {
                    lock.unlock();
                }

                try {
                    boolean timed =
                        lock.tryLock(50, TimeUnit.MILLISECONDS);
                    System.out.println("timed = " + timed);

                    if (timed) {
                        lock.unlock();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("interrupted");
                }
            }, "contender");

            worker.start();
            worker.join();
        } finally {
            lock.unlock();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TryLockWaitDemo.java
java TryLockWaitDemo
~~~

Stdout thông thường khi worker không bị interrupt:

~~~text
immediate = false
timed = false
~~~

Vì `main` giữ khóa cho đến **sau** `worker.join()`, worker không thể lấy khóa từ thread khác: `tryLock()` trả false ngay, còn `tryLock(50, MILLISECONDS)` chờ tối đa khoảng thời gian yêu cầu rồi trả false. Lời gọi timeout không bảo đảm chính xác 50 ms theo đồng hồ.

Ví dụ này cho thấy xử lý **thất bại có kiểm soát**, không phải một cuộc đua giữa các waiter. Nó không minh họa trực tiếp barging, vì khi worker thử, khóa chưa rảnh. Để nghiên cứu barging, cần thử trên những lịch thực thi có waiter đang xếp hàng, đo thứ tự cấp khóa, và chấp nhận rằng kết quả của một lần chạy không cố định.

### 4.1. tryLock không tự đảm bảo forward progress

Khi `tryLock` trả false, công việc vẫn chưa được thực hiện. Nếu code luôn thử lại trong một vòng lặp bận, một số thread có thể chiếm CPU mà không tiến triển, tạo contention mới hoặc livelock. Cần chọn backoff, giới hạn retry, deadline, queue hoặc một phương pháp blocking thích hợp.

Đối với nhiều khóa phải lấy cùng lúc, `tryLock` có thể giúp **trả lại khóa đã giữ** khi không lấy được khóa tiếp theo; nhưng vẫn cần thứ tự khóa hoặc giao thức phối hợp đúng để tránh deadlock, livelock và starvation.

## 5. Starvation khác deadlock và livelock như thế nào?

| Hiện tượng | Mô tả | Ví dụ |
| --- | --- | --- |
| **Starvation** | Một task không được tài nguyên đủ lâu dù công việc khác vẫn hoàn thành | Waiter liên tục bị task mới barging |
| **Deadlock** | Một nhóm task chờ nhau theo chu trình, không ai giải phóng phụ thuộc cần thiết | A giữ lock 1 chờ 2; B giữ 2 chờ 1 |
| **Livelock** | Task liên tục phản ứng/nhường nhau nhưng không hoàn tất việc hữu ích | Hai thread lặp lại tryLock rồi cùng retry đồng bộ |
| **Long blocking** | Một task chờ rất lâu vì owner giữ tài nguyên quá lâu | Holder gọi I/O chặn trong critical section |
| **Priority inversion** | Task ưu tiên cao phải đợi tài nguyên do task ưu tiên thấp đang giữ | High priority chờ lock; low priority chưa được chạy để release |

Có thể có starvation mà **không có deadlock**: một tập task liên tục hoàn thành trong khi task X vẫn chờ. Fair lock giúp giảm nguy cơ starvation **do thứ tự cấp khóa**, nhưng không giải quyết CPU scheduling starvation, deadlock do giữ nhiều khóa, pool worker starvation hoặc task giữ khóa quá lâu.

Cũng không có chứng minh “không starvation tuyệt đối” chỉ bằng `isFair() == true`. Nếu worker chưa từng được CPU lập lịch để chạy tới `lock()`, nó chưa nằm trong hàng đợi chờ khóa theo nghĩa cần xét. Nếu owner không release, waiter vẫn chờ bất kể chính sách nào.

## 6. Throughput, latency và lock convoy

### 6.1. Vì sao nonfair thường nhanh hơn khi tranh chấp mạnh?

Trong một workload có critical section ngắn, nhiều thread đang hoạt động và queue nhiều waiter:

1. Thread X release lock.
2. Một waiter Y đang đợi cần được đánh thức và CPU lập lịch.
3. Trong lúc đó thread Z vừa chạy trên CPU muốn lấy lock.

Với chính sách nonfair, Z có thể lấy khóa ngay nếu nó nhìn thấy khóa đang rảnh. Việc tận dụng thread đang chạy có thể giảm chờ scheduler và tránh một số lần chuyển ngữ cảnh.

Với chính sách fair, việc ưu tiên waiter đã chờ có thể yêu cầu chờ Y tiến triển. Nếu Y chưa được CPU lập lịch, những thread đang sẵn sàng chạy có thể phải đợi. Trong một số hệ thống, hiện tượng **lock convoy** (các thread xếp hàng chờ được phục vụ nối tiếp) làm throughput giảm.

Nhưng từ “thường” là định hướng thực nghiệm, **không phải định luật cho mọi tải**. Trong workload ít contention, rất nhiều thời gian nằm ở I/O, hoặc chính sách cấp CPU khác nhau, kết quả có thể khác. Chỉ benchmark trong môi trường đại diện mới xác định được mức đánh đổi.

### 6.2. Đừng chỉ đo số task hoàn thành

Một cấu hình có thể tạo 20.000 thao tác/giây nhưng một số task đợi vài giây mới lấy được lock. Cấu hình khác có thể xử lý 18.000 thao tác/giây nhưng giảm đáng kể thời gian chờ đuôi của waiter.

Chỉ số nên quan sát:

| Chỉ số | Câu hỏi |
| --- | --- |
| Throughput (ops/s) | Hệ thống hoàn tất bao nhiêu thao tác mỗi giây? |
| Lock wait p50/p95/p99 | Một waiter điển hình và waiter chậm nhất đợi bao lâu? |
| Max wait / timeout rate | Có task nào bị bỏ đói hoặc vượt deadline? |
| Critical-section hold time | Owner giữ khóa trong bao lâu? Có I/O/blocking trong khóa không? |
| Active waiters / queue length | Có bao nhiêu thread đang tranh chấp? |
| CPU/context switching | Scheduler overhead có đang lấn át công việc hữu ích? |
| GC/allocations | Công việc trong vùng khóa có tạo sức ép bộ nhớ không? |
| Per-thread completion distribution | Một số thread có được cấp quyền ít hơn hẳn không? |

Thông lượng cao nhưng p99 tăng đột biến có thể không phù hợp với tác vụ tương tác; ngược lại, một batch cần tổng tốc độ tối đa có thể chấp nhận chênh lệch thời gian chờ cá nhân nếu không có ràng buộc công bằng mạnh.

### 6.3. Fairness có thể tăng độ trễ trung bình không?

Có thể. Nếu chính sách handoff tốn thời gian mà tất cả task đều ngắn, tổng thời gian mỗi lần vào khóa có thể tăng. Đồng thời, việc giảm các lượt chờ cực dài có thể **cải thiện phân phối latency**. Cần nhìn cả average, tail latency và deadline miss; không có bảo đảm rằng fair luôn cải thiện p99 ở mọi môi trường.

Giảm thời gian giữ khóa, loại bỏ khóa không cần thiết, chia vùng trạng thái, dùng immutable snapshot hoặc message passing đôi khi mang lại lợi ích lớn hơn tranh luận fair/nonfair. Tuy nhiên, tối ưu không được phá invariant của dữ liệu chia sẻ.

## 7. Condition: được signal không đồng nghĩa được chạy ngay

`Condition` thường được tạo từ `ReentrantLock.newCondition()`, tách một hàng chờ **điều kiện nghiệp vụ** khỏi việc chờ **quyền sở hữu khóa**.

Quy trình cơ bản:

1. Thread giữ lock, thấy điều kiện chưa đúng.
2. Gọi `condition.await()`, **tạm release lock** và bắt đầu chờ tín hiệu.
3. Một thread khác lấy lock, cập nhật trạng thái rồi gọi `signal()` hoặc `signalAll()`.
4. Thread được đánh thức **phải lấy lại lock** trước khi `await()` hoàn tất và nó tiếp tục kiểm tra trạng thái.

**Signal không trực tiếp trao lock cho waiter**, và không có bảo đảm waiter được CPU chạy ngay sau `signal()`. Owner hiện tại vẫn giữ lock cho đến khi unlock, và nhiều thread khác có thể đang tranh chấp.

Theo hợp đồng `ConditionObject` của `ReentrantLock`, waiter được signal theo thứ tự FIFO trên hàng chờ condition, nhưng việc chúng **lấy lại lock** chịu chính sách acquisition của lock liên quan. Với fair lock, các thread cạnh tranh sau signal tuân thủ ưu tiên chờ khóa; điều đó vẫn không tạo deadline cứng hoặc bảo đảm scheduler.

### Ví dụ 3 — điều kiện và kiểm tra bằng while (Java 17+)

Tạo tệp `ConditionSignalDemo.java`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionSignalDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock(true);
        private final Condition openCondition = lock.newCondition();
        private boolean open;

        void awaitOpen() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!open) {
                    openCondition.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                open = true;
                openCondition.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        Thread waiter = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("Gate opened");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("Wait interrupted");
            }
        }, "gate-waiter");

        waiter.start();
        gate.open();
        waiter.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConditionSignalDemo.java
java ConditionSignalDemo
~~~

Khi waiter không bị interrupt, stdout là:

~~~text
Gate opened
~~~

Dù `gate.open()` có thể chạy **trước** khi waiter đi vào `await()`, chương trình vẫn đúng vì trạng thái `open` được lưu và kiểm tra dưới cùng lock. Nếu `open` đã là true, waiter không chờ và không phụ thuộc vào việc có “nhận được signal” hay không.

`while (!open)` là bắt buộc về mặt mẫu thiết kế: Condition cho phép **spurious wakeup**, và trạng thái có thể đổi giữa signal với thời điểm waiter reacquire lock. Dùng `if` đơn giản có thể khiến waiter tiếp tục dù điều kiện không còn đúng.

`signal()` chỉ đánh thức một waiter đủ điều kiện; `signalAll()` đánh thức tất cả, đôi khi tạo cạnh tranh lớn khi nhiều thread cùng cố reacquire lock. Chọn theo bất biến và số waiter có thể tiến triển, không theo giả định rằng signalAll luôn “công bằng hơn”.

### 7.1. Chờ Condition có thể starvation không?

Có. Ngay cả khi lock fair, một task có thể không bao giờ nhận tín hiệu phù hợp, hoặc predicate của nó liên tục trở thành false trước khi reacquire. Fairness của lock không thay thế logic điều phối condition và không bảo đảm thứ tự hoàn thành nghiệp vụ.

Phải đánh giá:

- Điều kiện chờ có thể trở thành true không?
- Mọi thay đổi trạng thái quan trọng có signal đúng condition không?
- Có cần `signalAll` vì nhiều waiter có các predicate khác nhau không?
- Có timeout/cancellation để xử lý chờ dài không?
- Có thread nào có thể giữ lock quá lâu hoặc bị scheduler bỏ đói không?

Các câu hỏi đó riêng biệt với việc bật `new ReentrantLock(true)`.

## 8. Fairness của Semaphore khác gì fairness của Lock?

`Semaphore` quản lý một số **permit**. Ví dụ một semaphore có ba permit cho phép tối đa ba thao tác cùng được cấp permit, thường dùng để giới hạn concurrency đi vào tài nguyên ngoài.

~~~java
// Minh họa, không phải chương trình độc lập.
Semaphore permits = new Semaphore(3, true);

permits.acquire();
try {
    accessLimitedResource();
} finally {
    permits.release();
}
~~~

Cần import `java.util.concurrent.Semaphore` và xử lý `InterruptedException` cho `acquire()`. Với `fair=true`, semaphore áp dụng thứ tự FIFO tại **các điểm xếp hàng nội bộ cụ thể** khi có contention. Không suy ra đơn giản “thread gọi acquire trước chắc chắn lấy permit trước” vì thứ tự thực sự phụ thuộc thread nào tới điểm đó trước.

**Ngoại lệ tương tự lock:** `Semaphore.tryAcquire()` không tham số có thể lấy permit đang rảnh **dù có waiter trước**, ngay cả khi semaphore được cấu hình fair. `tryAcquire(0, TimeUnit.SECONDS)` áp dụng fairness khi có contention và có thể ném `InterruptedException`.

`Semaphore` không ràng buộc owner như `ReentrantLock`; một thread có thể `release()` permit do thread khác lấy, nên logic cấp/trả permit phải đặc biệt cẩn thận để tránh trả thừa. Bật fair không sửa được việc release sai.

### Ví dụ 4 — giới hạn công việc bằng fair semaphore (Java 17+)

Tạo tệp `FairSemaphoreDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public class FairSemaphoreDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore slots = new Semaphore(2, true);

        slots.acquire(2);
        System.out.println("available = " + slots.availablePermits());

        slots.release();
        System.out.println("available = " + slots.availablePermits());

        slots.release();
        System.out.println("fair = " + slots.isFair());
        System.out.println("available = " + slots.availablePermits());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FairSemaphoreDemo.java
java FairSemaphoreDemo
~~~

Stdout:

~~~text
available = 0
available = 1
fair = true
available = 2
~~~

Ví dụ minh họa API và việc permit được quản lý đúng số lượng; vì không có tranh chấp giữa nhiều thread, nó **không** chứng minh chính sách fair làm thay đổi thứ tự phục vụ hay throughput. Khi benchmark semaphore, đo cả latency chờ permit và utilization của tài nguyên được bảo vệ.

## 9. Fairness của ReentrantReadWriteLock

`ReentrantReadWriteLock` tách **read lock** (cho phép nhiều reader cùng giữ khi không bị writer ngăn cản theo chính sách) và **write lock** (loại trừ quyền truy cập từ reader/writer khác).

- **Nonfair** là mặc định; không áp đặt ưu tiên theo thứ tự chờ và có thể khiến một số reader hoặc writer bị trì hoãn rất lâu trong điều kiện cạnh tranh liên tục.
- **Fair** (`new ReentrantReadWriteLock(true)`) áp dụng chính sách ưu tiên đến gần thứ tự thread yêu cầu: writer đơn lẻ chờ lâu và nhóm reader chờ lâu được phục vụ theo chính sách của JDK. Đó không phải yêu cầu mọi người đọc/ghi luôn hoàn thành theo thứ tự tuyệt đối.
- Các phương thức `readLock().tryLock()` và `writeLock().tryLock()` không tham số **không tôn trọng fairness**, tương tự `ReentrantLock.tryLock()`.
- Fairness không biến thời gian giữ read/write lock thành thời hạn có giới hạn; một writer vẫn có thể chờ reader đang giữ lock lâu, hoặc một reader bị gián đoạn/hết thời gian do yếu tố khác.

Đọc nhiều, ghi ít không đồng nghĩa read-write lock luôn nhanh hơn một `ReentrantLock`; cần xét số reader thực sự chạy song song, độ dài critical section, overhead của lock và khả năng writer bị chờ.

`ReentrantReadWriteLock.WriteLock` hỗ trợ `newCondition()`; `ReadLock.newCondition()` không hỗ trợ và ném `UnsupportedOperationException`. Các condition riêng của write lock cũng không tự cấp fairness cho predicate nghiệp vụ.

## 10. Chính sách fair không sửa các vấn đề nào?

### 10.1. Deadlock do thứ tự lấy nhiều khóa

Fair lock chỉ quyết định thứ tự **giữa các thread đang chờ cùng một lock**. Nó không loại bỏ vòng chờ:

~~~text
Thread A: giữ L1 -> chờ L2
Thread B: giữ L2 -> chờ L1
~~~

Cả L1 lẫn L2 đều cấu hình fair vẫn có thể deadlock. Phải dùng lock ordering thống nhất, giảm lồng khóa, hoặc giao thức tránh vòng chờ khác.

### 10.2. Giữ khóa quá lâu

Nếu một thread thực hiện truy vấn mạng, sleep hoặc ghi file chậm trong critical section, các waiter vẫn chờ đến lúc owner release. Fairness không ép owner nhường khóa theo time slice. Đo thời gian giữ khóa và đưa các tác vụ chặn dài ra ngoài vùng khóa khi bảo toàn bất biến cho phép.

### 10.3. Thread pool starvation

Một executor chỉ có một worker, task A đang chạy gửi task B vào cùng pool rồi chờ `B.get()`, có thể tự gây bế tắc phụ thuộc task. Bật fair cho một lock được task sử dụng không tạo thêm worker cho B.

### 10.4. CPU scheduler, priority và external resource

Fairness cấp khóa không kiểm soát thứ tự CPU scheduler, chính sách ưu tiên của OS, kết nối database, rate limit API hay tốc độ disk. Những điểm nghẽn đó cần biện pháp quản lý riêng: backpressure, timeout, bounded queues, capacity planning, v.v.

### 10.5. Correctness của dữ liệu dùng chung

Cả fair và nonfair lock đều có cơ chế mutual exclusion và memory visibility khi được dùng đúng cách. Một đường code đọc state ngoài khóa vẫn có thể sai dù khóa là fair. Lựa chọn fairness **không chữa data race** hoặc invariant bị vi phạm.

## 11. Dùng queue, thời gian chờ và quan sát trạng thái như thế nào?

`ReentrantLock` cung cấp các phương thức như `hasQueuedThreads()`, `hasQueuedThread(thread)`, `getQueueLength()` và `isFair()`. Chúng hữu ích cho **giám sát và chẩn đoán**, nhưng tình trạng queue có thể thay đổi ngay sau khi đọc. `getQueueLength()` là **ước lượng**, không phải số liệu giao dịch chính xác hoặc cơ sở để quyết định một thao tác compound an toàn.

Các giá trị đo nên gắn với task:

- Thời điểm ngay trước `lock()` và ngay sau khi acquire để tính thời gian chờ.
- Thời điểm acquire và release để tính thời gian giữ khóa.
- Thời điểm vào task và hoàn thành để tính end-to-end latency.
- Timeout/interrupt/retry count, phân phối theo loại task hoặc pool.
- Queue depth và context switching ở mức chẩn đoán.

Không nên log trên mỗi lần lấy khóa ở đường cực nóng nếu chính log trở thành nút thắt, hoặc làm sai phân phối latency của benchmark.

### 11.1. Mẫu đo thời gian chờ bằng System.nanoTime

~~~java
// Minh họa đặt trong phương thức có lock và recorder đã khởi tạo.
long started = System.nanoTime();
lock.lock();
long acquired = System.nanoTime();
try {
    performCriticalWork();
} finally {
    long released = System.nanoTime();
    lock.unlock();
    recorder.recordWaitNanos(acquired - started);
    recorder.recordHoldNanos(released - acquired);
}
~~~

Đây là mã minh họa, **không phải chương trình độc lập**. `System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng JVM; `recorder` phải có chi phí thấp và thread-safe. Để không cho lỗi recorder làm ảnh hưởng tới việc giải phóng khóa, có thể đo trong critical section và **ghi nhận metrics sau khi đã unlock**, hoặc đảm bảo recorder không ném exception và không block.

Trong mã minh họa trên, phép đo `released` đặt trước `unlock()`, nên đây là ước lượng thời gian giữ khóa, không đo chính xác toàn bộ chi phí release; một recorder production nên nhất quán về cách đo và kiểm tra overhead.

## 12. Benchmark fair và nonfair đúng cách

### 12.1. Mẫu thiết kế benchmark

Không so sánh bằng cách chạy một lần rồi in `System.currentTimeMillis()`. Java có JIT compilation, GC, scheduler, CPU frequency và nhiều nhiễu môi trường. Với benchmark nghiêm túc:

1. **Chọn workload đại diện:** số worker, tỷ lệ đọc/ghi, độ dài critical section, mức contention, chi phí I/O và số lõi.
2. **Dùng cùng logic nghiệp vụ:** chỉ thay chính sách fair/nonfair, giữ nguyên pool, dữ liệu đầu vào, timeout, số tác vụ và môi trường.
3. **Warm-up và nhiều lượt đo:** để giảm sai số của JIT và các dao động ngắn.
4. **Đo thông lượng lẫn latency:** p50/p95/p99 wait time, per-thread completion, max wait và deadline miss.
5. **Kiểm tra correctness:** công việc hoàn tất đủ, invariant dữ liệu không bị phá, không bỏ qua exception.
6. **Tránh tự tạo bottleneck khi đo:** log đồng bộ, lock recorder hoặc khởi tạo object bên trong phép đo có thể che hiệu ứng đang kiểm tra.
7. **Phân biệt CPU-bound với I/O-bound:** chuyển ngữ cảnh và lock hold time có thể rất khác nhau.
8. **Không mặc định một kết luận:** khóa fair thường làm tăng chi phí dưới contention, nhưng mức giảm throughput và lợi ích về phân phối thời gian chờ phụ thuộc tải.

JMH là công cụ benchmark phổ biến trong hệ sinh thái Java. Khi benchmark khả năng bị starvation lâu dài, cần thêm bài thử có queue/waiter cạnh tranh liên tục và báo cáo phân phối thời gian chờ thay vì chỉ số throughput gộp.

### 12.2. Cách đọc một kết quả giả định

Giả sử hai cấu hình được đo cùng workload:

| Chỉ số **giả định** | Nonfair | Fair |
| --- | ---: | ---: |
| Throughput | 42.000 ops/s | 35.000 ops/s |
| p99 chờ lock | 18 ms | 8 ms |
| Max wait quan sát | 250 ms | 42 ms |

Đây **chỉ là số liệu minh họa để đọc bảng**, không phải benchmark thực tế, cũng không phản ánh một JVM hay phần cứng cụ thể. Nếu mục tiêu ưu tiên số operation tổng, nonfair có thể hấp dẫn. Nếu có deadline cho từng công việc, phân phối wait time của fair có thể phù hợp hơn.

Tuy vậy, nếu ứng dụng có một task đôi khi giữ lock 2 giây, chuyển sang fair **không** tự sửa được điểm nghẽn đó. Tối ưu đường giữ khóa có thể quan trọng hơn thay đổi chính sách cấp quyền.

## 13. Các sai lầm thường gặp

**“Fair lock bảo đảm thread nào gọi `lock()` trước thì vào trước.”** Không hẳn. Hai thread có thể được CPU lập lịch khác nhau; chính sách fair áp dụng khi có contention và chờ khóa, không cho phép suy ra thứ tự từ thời điểm tạo thread hoặc gửi task.

**“Bật fairness là chắc chắn không starvation.”** Không đúng với CPU scheduling, owner không release, condition không được signal, external resource và nhiều đường dùng `tryLock()` barging.

**“`tryLock()` trên fair lock luôn tôn trọng FIFO.”** Sai: overload không tham số có thể barging. Khi cần thử không chờ mà vẫn tôn trọng fairness, cân nhắc overload có timeout bằng 0 và xử lý interrupt.

**“Nonfair lock luôn nhanh hơn.”** Không có bảo đảm cho mọi workload; phải đo contention, throughput và latency theo ứng dụng thực.

**“Fairness giải quyết deadlock.”** Không. Thứ tự lấy nhiều khóa và chu trình chờ tài nguyên là vấn đề khác với thứ tự waiter của một khóa.

**“`signal()` trao lock ngay cho waiter.”** Không. Waiter chỉ tiếp tục sau khi reacquire lock; phải kiểm tra condition trong vòng `while`.

**“Dùng `signalAll()` là công bằng hơn.”** SignalAll có thể tạo một đợt cạnh tranh lớn, làm nhiều waiter thức dậy rồi lại chờ; lựa chọn phải theo predicate và yêu cầu liveness.

**“Queue length bằng 0 nghĩa là không có contention.”** `getQueueLength()` chỉ ước lượng tại một thời điểm; ngữ cảnh có thể thay đổi ngay sau khi đọc.

**“Một lần chạy 4 thread đã chứng minh fair/nonfair hiệu năng tốt hơn.”** Không. Cần benchmark nhiều lượt, kiểm soát điều kiện và số liệu phân phối, không kết luận từ thứ tự log tình cờ.

**“Bật fair sẽ sửa code không thread-safe.”** Fairness chỉ là chính sách cấp khóa; code đọc/ghi ngoài giao thức khóa vẫn có thể sai.

## 14. Hướng dẫn chọn chính sách

| Bài toán | Điểm ưu tiên | Gợi ý ban đầu |
| --- | --- | --- |
| Nhiều thao tác rất ngắn, throughput là ưu tiên chính | Tổng thông lượng, lock contention | Bắt đầu với nonfair mặc định, đo thời gian chờ |
| Nhiều công việc cùng loại, mỗi công việc có deadline | p95/p99 và starvation risk | Đánh giá fair, đồng thời đo throughput |
| Ít contention | Đơn giản, correctness | Nonfair thường đủ; fairness có thể không quan trọng |
| Reader nhiều, writer ít | Read/write contention | Đo `ReentrantReadWriteLock` và rủi ro writer wait |
| Giới hạn tài nguyên ngoài JVM | Permit queue và overload | `Semaphore` có hoặc không fair, tùy SLA |
| Condition với nhiều predicate | Predicate/liveness | Thiết kế đúng `await`/`signal`, fairness chỉ hỗ trợ reacquire |
| Nhiều khóa phải giữ cùng lúc | Không deadlock | Lock ordering nhất quán trước khi tối ưu fair |
| Task bị block bởi pool hoặc I/O | Capacity/deadline | Sửa bottleneck; fairness của lock không đủ |

Một cách làm thực tế là bắt đầu từ **tính đúng đắn** và **bất biến**, đo mức contention và yêu cầu chờ, sau đó chọn fair khi có bằng chứng về starvation hoặc latency đuôi đáng xử lý. Đừng chỉ thấy một thread chậm rồi vội bật fair: nguyên nhân có thể nằm ở thời gian giữ khóa, executor hoặc downstream.

## 15. Câu hỏi tự kiểm tra

**1.** `new ReentrantLock(true)` có bảo đảm task A hoàn thành trước task B nếu A được submit trước không?

Không. Thứ tự submit, được lập lịch, tới lời gọi lock, thời gian giữ lock và công việc sau critical section là các thứ tự khác nhau. Fairness chủ yếu xét quyền lấy lock khi có waiter.

**2.** Một fair `ReentrantLock` có hàng đợi waiter. Thread mới gọi `tryLock()` khi khóa vừa rảnh. Nó có thể vượt hàng không?

Có. `tryLock()` không tham số có thể barging dù khóa được cấu hình fair. Overload có timeout trên fair lock có ngữ nghĩa fairness khác.

**3.** Fairness có chữa deadlock giữa A giữ L1 chờ L2 và B giữ L2 chờ L1 không?

Không. Đó là vòng chờ của nhiều lock; cần thứ tự khóa chung hoặc giao thức khác tránh circular wait.

**4.** `condition.signal()` có làm waiter lập tức thực thi phần sau `await()` không?

Không. Waiter cần reacquire lock trước khi `await()` trả về; owner hiện tại vẫn có thể giữ lock và scheduler quyết định khi thread được chạy.

**5.** Vì sao phải đo cả throughput và p99 lock wait?

Throughput mô tả tổng số thao tác hoàn tất; p99 cho biết nhóm waiter chậm có thể chịu độ trễ lớn thế nào. Một cấu hình tổng thể nhanh hơn vẫn có thể tệ với các task có deadline.

**6.** Chỉ chọn `Semaphore(3,true)` có bảo đảm ba request sẽ hoàn thành theo đúng thứ tự nhận request không?

Không. Fairness áp dụng tại các điểm acquisition nội bộ của permit; việc được cấp permit không đồng nghĩa thời gian chạy công việc như nhau, và `tryAcquire()` không tham số có thể barging.

**Ghi nhớ:** **Fairness là chính sách cấp quyền khi cạnh tranh**, không phải một lời hứa về CPU scheduler hay thời hạn hoàn thành. Fair lock thường hỗ trợ giảm nguy cơ một waiter bị vượt hàng liên tục, đổi lại có thể giảm throughput. Hãy dùng đúng overload của API, giữ critical section ngắn, thiết kế condition chuẩn và đo cả hiệu năng tổng thể lẫn thời gian chờ của từng nhóm task.