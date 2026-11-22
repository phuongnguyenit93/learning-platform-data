# Khóa, biến atomic và cấu trúc dữ liệu đồng thời trong Java

Trong ứng dụng Spring, nhiều request HTTP, tác vụ `@Async`, `@Scheduled` hoặc luồng nền có thể truy cập cùng một đối tượng. Nếu đối tượng chứa trạng thái thay đổi được, chỉ dùng `HashMap` hay biến `int` thông thường là chưa đủ để đảm bảo kết quả đúng. Bài này tập trung vào cơ chế đồng bộ trong Java (`java.util.concurrent`) và cách chọn chúng khi viết ứng dụng Spring.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **race condition**, **visibility**, **atomicity**, **happens-before** và phân biệt an toàn dữ liệu với khả năng tiến triển của luồng.
- Chọn giữa `synchronized`, `Lock`, `ReadWriteLock`, `StampedLock`, biến atomic và thiết kế bất biến.
- Dùng đúng `ConcurrentHashMap`, `CopyOnWriteArrayList`, các queue đồng thời và collection được bọc đồng bộ.
- Nhận diện thao tác tổng hợp không atomic, xử lý interruption, tránh deadlock và áp dụng các nguyên tắc trên cho Spring singleton bean.

## 2. Vì sao dữ liệu dùng chung gặp lỗi?

Giả sử hai luồng đồng thời chạy `counter++` với `counter = 0`. Phép tăng gồm ba bước logic: đọc giá trị, cộng 1, ghi lại. Cả hai có thể cùng đọc 0 rồi cùng ghi 1; kết quả cuối là 1 thay vì 2. Đây là **lost update**, một dạng race condition. Khi nhiều luồng cùng đọc/ghi dữ liệu mà không có cơ chế đồng bộ phù hợp, vấn đề còn bao gồm việc thấy dữ liệu cũ hoặc thấy một tổ hợp trạng thái không nhất quán.

Ba thuộc tính cần tách biệt:

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Atomicity** | Thao tác có xuất hiện như một đơn vị không bị xen giữa? | Tăng một bộ đếm bằng `AtomicInteger.incrementAndGet()` |
| **Visibility** | Bản cập nhật ở luồng này có được luồng khác nhìn thấy đúng lúc? | Ghi rồi đọc một trường `volatile` |
| **Ordering / happens-before** | Có ràng buộc thứ tự bộ nhớ để luồng đọc thấy trạng thái đã công bố? | Thả khóa rồi luồng khác lấy lại **cùng khóa** |

Mô hình bộ nhớ Java (Java Memory Model, JMM) quy định quan hệ **happens-before**. Một số quan hệ thường dùng: thao tác `unlock` xảy ra trước `lock` tiếp theo trên cùng khóa; ghi `volatile` xảy ra trước lần đọc sau đó đối với chính biến đó; `Thread.start()` công bố hành động trước khi start cho thread mới; hành động của thread xảy ra trước khi một thread khác `join()` thành công. Các lớp atomic và concurrent collection có bảo đảm bộ nhớ riêng theo API.

**`volatile` không biến `counter++` thành atomic**: nó chủ yếu giải quyết visibility và ordering cho từng lần truy cập. `synchronized`, `Lock` hoặc thao tác atomic thích hợp mới bảo vệ được phép cập nhật tổng hợp. Không dùng `Thread.sleep()` để sửa race condition: độ trễ không tạo ra hợp đồng đồng bộ đáng tin cậy.

Một hệ thống **thread-safe** giữ đúng bất biến dữ liệu dù nhiều luồng thực thi. Tuy nhiên, nó vẫn có thể **deadlock** (các luồng chờ nhau), **starvation** (một luồng liên tục không được phục vụ) hoặc chậm vì tranh chấp khóa. Cần kiểm tra cả correctness lẫn liveness.

## 3. Khóa nội tại: `synchronized`

Mỗi object Java có monitor, dùng được với `synchronized`. Trong vùng khóa, chỉ một luồng sở hữu monitor tại một thời điểm; monitor đồng thời cung cấp quan hệ visibility khi thả và lấy khóa. Các phương thức `synchronized` trên cùng instance dùng chính monitor của instance đó; `static synchronized` dùng monitor của đối tượng `Class`.

Ví dụ một counter có thể dùng cùng khóa cho cả đọc lẫn ghi:

~~~java
public final class SynchronizedCounter {
    private final Object monitor = new Object();
    private int value;

    public void increment() {
        synchronized (monitor) {
            value++;
        }
    }

    public int get() {
        synchronized (monitor) {
            return value;
        }
    }
}
~~~

Đây là một lớp độc lập có thể biên dịch (không chứa `main`); các lời gọi `increment()` và `get()` đều sử dụng cùng đối tượng khóa. Nếu `get()` đọc trực tiếp `value` ở ngoài vùng `synchronized`, giao thức bảo vệ trạng thái bị phá vỡ. Nên dùng khóa `private final`; tránh khóa trên chuỗi literal, đối tượng công khai hoặc đối tượng mà mã bên ngoài cũng có thể khóa.

Monitor **reentrant**: luồng đang giữ khóa có thể vào lại một phương thức khóa cùng monitor mà không tự deadlock. `synchronized` tự thả monitor khi ra khỏi khối, kể cả có exception. Nó phù hợp với vùng tới hạn ngắn và logic đơn giản. Khi cần thử lấy khóa có timeout, nhận interruption khi chờ khóa hoặc dùng nhiều điều kiện chờ, cân nhắc `ReentrantLock`.

## 4. `Lock`, `ReentrantLock` và `Condition`

`java.util.concurrent.locks.Lock` tách thao tác lấy/thả khóa khỏi cú pháp khối `synchronized`. `ReentrantLock` thường dùng nhất. Các thao tác quan trọng:

- `lock()`: chờ đến khi lấy được khóa; bản thân việc chờ kiểu này không phản hồi interruption bằng `InterruptedException`.
- `lockInterruptibly()`: có thể hủy chờ khi thread bị interrupt.
- `tryLock()` hoặc `tryLock(timeout, unit)`: thử lấy khóa ngay hoặc trong một khoảng thời gian; dạng có timeout có thể ném `InterruptedException`.
- `unlock()`: phải gọi **trong `finally` sau khi đã lấy khóa thành công**; gọi khi không sở hữu khóa sẽ lỗi.

Ví dụ đầy đủ sau phối hợp `ReentrantLock` cho bất biến số dư và `AtomicInteger` cho số thao tác hoàn tất. Tệp **LockAtomicDemo.java**, Java 17+:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public final class LockAtomicDemo {
    private static final class Wallet {
        private final ReentrantLock lock = new ReentrantLock();
        private int balance;

        void add(int amount) {
            lock.lock();
            try {
                balance += amount;
            } finally {
                lock.unlock();
            }
        }

        int balanceValue() {
            lock.lock();
            try {
                return balance;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        final int operations = 1_000;
        Wallet wallet = new Wallet();
        AtomicInteger processed = new AtomicInteger();
        CountDownLatch finished = new CountDownLatch(operations);
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            for (int i = 0; i < operations; i++) {
                pool.execute(() -> {
                    try {
                        wallet.add(2);
                        processed.incrementAndGet();
                    } finally {
                        finished.countDown();
                    }
                });
            }

            finished.await();
            System.out.println("processed=" + processed.get());
            System.out.println("balance=" + wallet.balanceValue());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac LockAtomicDemo.java
java LockAtomicDemo
~~~

Stdout:

~~~text
processed=1000
balance=2000
~~~

`finished.await()` đợi 1.000 task gọi `countDown()` trước khi đọc kết quả; do đó kết quả không phụ thuộc thứ tự chạy cụ thể. Trong thực tế phải xử lý lỗi của task, giới hạn hàng đợi executor và có chiến lược shutdown; ví dụ này cố ý tập trung vào tính đúng của hai loại trạng thái.

### `Condition`: chờ một điều kiện của trạng thái

Một `ReentrantLock` có thể tạo một hoặc nhiều `Condition` qua `newCondition()`. Khi gọi `await()`, thread **nhả khóa trong lúc chờ**, rồi phải lấy lại khóa trước khi `await()` trở về. Thread làm thay đổi điều kiện có thể gọi `signal()`/`signalAll()` khi đang giữ khóa tương ứng. Luôn kiểm tra điều kiện bằng vòng `while`, không dùng `if`: có thể xảy ra wakeup bất ngờ hoặc điều kiện đã đổi trước khi thread được chạy.

Mẫu logic (đoạn minh họa nằm trong phương thức đang giữ `lock`, với `notEmpty` là `Condition` và `queue` được bảo vệ bởi khóa đó):

~~~java
while (queue.isEmpty()) {
    notEmpty.await();
}
var item = queue.removeFirst();
~~~

Chỉ dùng mô hình này khi thật sự cần điều kiện tùy biến. Với hàng đợi producer/consumer tiêu chuẩn, `BlockingQueue` đã đóng gói toàn bộ logic chờ và đánh thức, thường đơn giản và ít lỗi hơn.

### Khóa đọc/ghi và optimistic read

- `ReentrantReadWriteLock` có **read lock** cho nhiều reader đồng thời và **write lock** độc quyền. Có ích khi đọc nhiều, ghi ít và vùng đọc tương đối đáng kể. Không mặc định dùng vì overhead và vì một reader cố nâng cấp trực tiếp lên write lock có thể bị kẹt. Tính công bằng có tùy chọn, nhưng có chi phí.
- `StampedLock` hỗ trợ read/write lock và **optimistic read** bằng stamp: đọc dữ liệu, sau đó gọi `validate(stamp)`; nếu không hợp lệ, phải đọc lại dưới read lock. Không được sử dụng tổ hợp dữ liệu đọc thử trước khi validation đạt. Khóa này **không reentrant**, không có `Condition` theo cách `ReentrantLock` cung cấp; cần thận trọng khi cấu trúc dữ liệu phức tạp.
- Khóa công bằng như `new ReentrantLock(true)` có thể giảm hiện tượng chờ bất lợi nhưng thường giảm thông lượng; nó không biến scheduling của hệ điều hành thành hoàn toàn công bằng.

## 5. Biến atomic và Compare-and-Set (CAS)

Các lớp trong `java.util.concurrent.atomic` cung cấp cập nhật atomic trên một biến/trạng thái riêng lẻ mà không cần tự viết `synchronized`. Các lựa chọn phổ biến:

| Lớp / công cụ | Mục đích |
| --- | --- |
| `AtomicInteger`, `AtomicLong` | Đếm, tăng/giảm, cập nhật số với thao tác atomic |
| `AtomicBoolean` | Cờ trạng thái cần chuyển đổi/đọc-ghi atomic |
| `AtomicReference<T>` | Thay một reference atomically, có thể trỏ đến trạng thái bất biến |
| `AtomicStampedReference<T>` | Gắn version/stamp để phát hiện một số dạng **ABA** |
| `LongAdder`, `DoubleAdder` | Tích lũy thống kê dưới mức tranh chấp cập nhật cao |
| `AtomicIntegerArray` và họ atomic array | Cập nhật atomic cho từng phần tử mảng |

Một số API của `AtomicInteger`:

- `get()`, `set(v)`, `getAndSet(v)`: đọc/ghi/đổi giá trị.
- `incrementAndGet()` trả giá trị **sau** khi tăng; `getAndIncrement()` trả giá trị **trước** khi tăng.
- `addAndGet(delta)`, `updateAndGet(f)`, `accumulateAndGet(x, f)`: cập nhật theo phép toán.
- `compareAndSet(expected, newValue)` (CAS): chỉ ghi nếu giá trị hiện tại vẫn bằng expected; kết quả là `true` khi thành công.

CAS tạo cơ chế **optimistic retry**. Khi có tranh chấp, thread đọc lại trạng thái rồi thử lại; phép cập nhật thành công của atomic variable có tính nguyên tử. Ví dụ giữ số chỗ còn trống không âm:

~~~java
AtomicInteger seats = new AtomicInteger(3);
boolean reserved = false;

while (true) {
    int remaining = seats.get();
    if (remaining == 0) {
        break;
    }
    if (seats.compareAndSet(remaining, remaining - 1)) {
        reserved = true;
        break;
    }
}
~~~

Đây là **đoạn mã minh họa**, cần import `java.util.concurrent.atomic.AtomicInteger` và đặt trong phương thức. Nếu CAS thất bại vì thread khác đã đổi giá trị, vòng lặp đọc lại rồi quyết định. Việc trừ chỗ được bảo vệ; còn hành động thanh toán hoặc ghi database là tác vụ khác, cần hợp đồng nhất quán ở tầng phù hợp. Không đặt lời gọi mạng, log có tác dụng phụ hay tạo giao dịch bên trong hàm truyền cho `updateAndGet`: lambda có thể được tính lại khi CAS phải retry.

**ABA** xảy ra khi trạng thái chuyển từ A → B → A: CAS chỉ so sánh A hiện tại với A mong đợi có thể không biết trạng thái đã từng thay đổi. Chỉ cần cơ chế version/stamp khi lịch sử chuyển đổi quan trọng cho thuật toán; đây không phải lỗi của mọi bộ đếm atomic.

**Atomic không đồng nghĩa với một giao dịch nhiều trường.** Hai `AtomicInteger` độc lập chỉ bảo đảm riêng từng phép cập nhật, không tự giữ bất biến như `available + reserved = capacity` trong lúc nhiều thread đọc/ghi. Khi cần nhiều trường thay đổi cùng nhau, dùng chung một khóa, hoặc đóng gói trạng thái bất biến vào một `AtomicReference<State>` và đổi cả reference bằng CAS có retry.

### `AtomicLong` hay `LongAdder`?

`AtomicLong` thuận tiện khi cần giá trị chính xác tại từng thao tác atomic, ví dụ lấy số thứ tự tiếp theo. `LongAdder` phân tán cập nhật vào nhiều ô nội bộ để giảm tranh chấp, thường thích hợp với **metrics, số lần sự kiện**. `LongAdder.sum()` không phải một snapshot atomic khi vẫn có thread cập nhật; khi tất cả cập nhật đã kết thúc, tổng là chính xác. `reset()`/`sumThenReset()` cũng cần xem xét race nếu concurrent update.

## 6. Cấu trúc dữ liệu đồng thời

Một collection thread-safe bảo vệ những thao tác được API cam kết. Điều đó **không** đồng nghĩa chuỗi nhiều lời gọi tự động atomic hoặc mọi lần duyệt đều là snapshot nhất quán.

| Collection / cơ chế | Cách hoạt động và tình huống dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| `ConcurrentHashMap<K,V>` | Map cho nhiều reader/writer, thao tác key-level như `putIfAbsent`, `compute`, `merge` | Không chấp nhận key/value `null`; iterator weakly consistent; thao tác tổng hợp không tự atomic |
| `ConcurrentSkipListMap/Set` | Map/set sắp thứ tự với truy cập đồng thời | Thường tốn chi phí hơn hash-based khi không cần thứ tự |
| `CopyOnWriteArrayList` / `CopyOnWriteArraySet` | Bản sao khi ghi; iterator xem snapshot | Ghi tốn chi phí sao chép, tốn bộ nhớ; hợp với đọc/duyệt nhiều, ghi hiếm |
| `ConcurrentLinkedQueue` / `ConcurrentLinkedDeque` | Queue/deque đồng thời phi chặn, không đợi phần tử | Không cung cấp backpressure và không chặn khi rỗng; `size()` có thể tốn O(n) và biến động |
| `ArrayBlockingQueue` | Queue có sức chứa cố định; `put/take` có thể chờ | Chờ vô hạn nếu không có đối tác; cần shutdown/interruption |
| `LinkedBlockingQueue` | Queue chặn, có thể cấu hình capacity | Nếu không đặt capacity, giới hạn mặc định rất lớn; dễ tích hàng đợi ngoài dự tính |
| `PriorityBlockingQueue` | Lấy phần tử theo ưu tiên | Không bị chặn bởi capacity mặc định; phần tử cùng độ ưu tiên không hứa FIFO |
| `Collections.synchronizedList/Map` | Bọc collection thường để đồng bộ từng phương thức | Phải tự khóa quanh những chuỗi thao tác và lúc duyệt |

### Map an toàn vẫn có thể bị lost update

Đoạn sau **sai** khi nhiều thread cùng tăng một key:

~~~java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
counts.put("ok", counts.getOrDefault("ok", 0) + 1);
~~~

Từng lệnh `get` và `put` thread-safe, nhưng **cặp get → put không atomic**. Dùng API gộp cập nhật vào một thao tác:

~~~java
counts.merge("ok", 1, Integer::sum);
~~~

`merge`/`compute` của `ConcurrentHashMap` bảo vệ việc cập nhật cho key liên quan. Giữ mapping/remapping function **ngắn, thuần tính toán**, tránh I/O lâu hoặc tự thay đổi cùng map bên trong hàm. Khi cần bộ đếm tần suất tranh chấp cao, idiom chuẩn là:

~~~java
ConcurrentHashMap<String, LongAdder> frequencies = new ConcurrentHashMap<>();
frequencies.computeIfAbsent("ok", k -> new LongAdder()).increment();
~~~

Ở ví dụ này, `computeIfAbsent` đảm bảo cùng key được gắn một `LongAdder` phù hợp; `increment()` của adder xử lý cập nhật từ nhiều thread. Cần import `java.util.concurrent.ConcurrentHashMap` và `java.util.concurrent.atomic.LongAdder`. Tính nhất quán khi đọc cả map hoặc tổng nhiều key vẫn cần được thiết kế riêng.

### Duyệt collection: snapshot, weak consistency và khóa ngoài

- Iterator của `ConcurrentHashMap` thường **weakly consistent**: không ném `ConcurrentModificationException` theo kiểu fail-fast thông thường, có thể thấy một phần thay đổi gần đây nhưng không hứa snapshot giao dịch.
- Iterator của `CopyOnWriteArrayList` xem snapshot tại lúc tạo iterator; thay đổi sau đó không xuất hiện trong vòng duyệt đang chạy. `Iterator.remove()` không hỗ trợ.
- Với `Collections.synchronizedList(list)`, khi duyệt phải đồng bộ trên **wrapper list**: `synchronized (list) { for (var item : list) { ... } }`. Chỉ synchronized từng phương thức thì vòng duyệt vẫn có thể bị can thiệp.
- Collection bất biến như `List.of(...)` loại bỏ việc thay đổi chính cấu trúc list; nếu phần tử bên trong là object mutable thì bản thân object vẫn có thể cần đồng bộ. `Collections.unmodifiableList` là view không cho sửa qua view, không khiến backing list thành bất biến.

### `BlockingQueue`: producer/consumer và backpressure

`BlockingQueue.put` chờ khi queue đầy, `take` chờ khi rỗng; `offer(value, timeout, unit)`/`poll(timeout, unit)` có thể cho phép timeout. Với producer nhanh hơn consumer, queue **bounded** giúp giới hạn lượng công việc chờ và tạo backpressure. Không nên tăng capacity vô hạn chỉ để giấu vấn đề quá tải.

Ví dụ Java 17+ độc lập, tệp **QueueMapDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class QueueMapDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    String event = queue.take();
                    if ("STOP".equals(event)) {
                        break;
                    }
                    counts.computeIfAbsent(event, k -> new LongAdder())
                          .increment();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        queue.put("ok");
        queue.put("ok");
        queue.put("fail");
        queue.put("STOP");
        consumer.join();

        System.out.println("ok=" + counts.get("ok").sum());
        System.out.println("fail=" + counts.get("fail").sum());
    }
}
~~~

Chạy:

~~~bash
javac QueueMapDemo.java
java QueueMapDemo
~~~

Stdout:

~~~text
ok=2
fail=1
~~~

Queue chỉ chứa tối đa hai phần tử tại một thời điểm; `put` có thể đợi consumer lấy bớt. Chuỗi `"STOP"` đóng vai trò **sentinel** để kết thúc consumer trong demo; hệ thống thực phải dùng tín hiệu không thể trùng dữ liệu hợp lệ và, nếu có nhiều consumer, cần chiến lược dừng cho từng consumer. `join()` giúp main đợi consumer xử lý xong trước khi đọc kết quả. Trong ứng dụng thật còn phải xử lý trường hợp producer/consumer lỗi, timeout, cancellation và drain queue khi shutdown.

## 7. Áp dụng vào Spring

Thông thường `@Service`, `@Controller` và nhiều bean khác có scope singleton: nhiều request có thể gọi **cùng instance** đồng thời. Spring tạo và công bố bean an toàn, nhưng những trường **mutable sau khởi tạo** không vì thế mà tự thread-safe. Ví dụ một bộ đếm sự kiện trong bộ nhớ của từng instance ứng dụng:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import org.springframework.stereotype.Service;

@Service
public final class EventStats {
    private final ConcurrentHashMap<String, LongAdder> counts =
            new ConcurrentHashMap<>();

    public void record(String event) {
        counts.computeIfAbsent(event, k -> new LongAdder()).increment();
    }

    public long count(String event) {
        LongAdder value = counts.get(event);
        return value == null ? 0L : value.sum();
    }
}
~~~

Đây là **Spring component minh họa**, tệp `EventStats.java`, cần dependency Spring Framework và không có `main`. Bản đồ và các adder xử lý truy cập đồng thời trong **một JVM**; kết quả `count` là tổng quan sát được, không phải snapshot atomic nếu đang cập nhật. Không dùng dữ liệu này như số dư tài khoản, kho hàng hoặc nguồn sự thật cần tồn tại bền vững.

Khi thêm `@Async`, `@Scheduled` hoặc cấu hình `TaskExecutor`/`ThreadPoolTaskExecutor`:

1. Xác định các trường được chia sẻ giữa nhiều lời gọi; ưu tiên biến cục bộ, đối tượng bất biến và truyền state theo tham số. Tránh giữ thông tin riêng từng request trên field của singleton.
2. Nếu phải chia sẻ, mô tả **bất biến** và bảo vệ **mọi điểm truy cập** bằng cùng giao thức: atomic, lock hoặc cấu trúc đồng thời.
3. Thiết lập giới hạn thread/queue phù hợp, xử lý exception, timeout, interruption và đóng tài nguyên đúng vòng đời. Một số kiểu gọi nội bộ trong cùng bean có thể bỏ qua proxy `@Async` mặc định.
4. Không giữ JVM lock trong lúc chờ HTTP, database hoặc tác vụ kéo dài nếu có thể thay bằng thiết kế bất đồng bộ, queue hay giao dịch.

**Ranh giới cực kỳ quan trọng:** `synchronized`, `ReentrantLock` và `ConcurrentHashMap` chỉ đồng bộ trong phạm vi **một tiến trình JVM**. Nếu ứng dụng Spring chạy 3 replica, mỗi replica có trạng thái và khóa riêng. Với dữ liệu nghiệp vụ xuyên tiến trình, cân nhắc transaction của database, optimistic locking bằng version, câu lệnh cập nhật có điều kiện, unique constraint hoặc cơ chế phân phối phù hợp. `@Transactional` xử lý ngữ nghĩa giao dịch tài nguyên như database; nó **không tự khóa** trường Java trong singleton bean. Ngược lại, giữ JVM lock cũng không thay thế được transaction của database.

## 8. Bảng chọn giải pháp theo tình huống

| Yêu cầu thực tế | Khởi đầu nên cân nhắc | Vì sao |
| --- | --- | --- |
| Chỉ tăng một số đếm, cần thao tác đọc/cập nhật atomic | `AtomicInteger` / `AtomicLong` | Đơn giản, không cần tự quản lý khóa |
| Đếm sự kiện rất nhiều luồng, đọc metrics không cần snapshot tức thời | `LongAdder` | Giảm tranh chấp cập nhật |
| Nhiều field phải thay đổi cùng một bất biến | `synchronized` / `ReentrantLock` | Bảo vệ cả vùng cập nhật như một đơn vị |
| Muốn timeout hoặc interruption khi chờ lấy khóa | `ReentrantLock.tryLock` / `lockInterruptibly` | Kiểm soát liveness và hủy chờ |
| Đọc nhiều, ghi ít và thời gian giữ khóa đáng kể | `ReentrantReadWriteLock`; đôi khi `StampedLock` | Có thể tăng song song giữa reader sau khi đo đạc |
| Map nhiều luồng; thao tác theo key | `ConcurrentHashMap.compute/merge` | Cập nhật key atomic theo hợp đồng API |
| Danh sách listener đọc rất nhiều, thay đổi rất ít | `CopyOnWriteArrayList` | Duyệt snapshot, không cần tự khóa iterator |
| Pipeline producer/consumer có giới hạn tồn đọng | `ArrayBlockingQueue` / bounded `LinkedBlockingQueue` | Có backpressure, hỗ trợ chờ |
| Chỉ cần thứ tự và cập nhật đồng thời | `ConcurrentSkipListMap/Set` | Cấu trúc đồng thời có sắp thứ tự |
| Dữ liệu không cần thay đổi sau khởi tạo | Đối tượng bất biến / immutable collection | Giảm hẳn shared mutable state |
| Tồn kho/số dư dùng chung nhiều replica | Database transaction / optimistic version | JVM lock không bao phủ các replica |

Không có cấu trúc nào luôn nhanh nhất. Chi phí phụ thuộc contention, tần suất đọc/ghi, số lượng key, kích thước dữ liệu, độ dài vùng khóa và yêu cầu tính nhất quán. Đo bằng dữ liệu tải gần thực tế trước khi tối ưu.

## 9. Lỗi phổ biến và cách phòng tránh

1. **Dùng `volatile int count` rồi `count++`.** Đây vẫn là read-modify-write không atomic. Thay bằng `AtomicInteger` hoặc đồng bộ phù hợp.
2. **Tưởng `ConcurrentHashMap` khiến mọi chuỗi lệnh an toàn.** Mẫu `if (!map.containsKey(k)) map.put(k,v)` vẫn có race. Dùng `putIfAbsent`, `computeIfAbsent`, `compute` hoặc `merge` theo yêu cầu.
3. **Đọc một phần state dưới khóa, phần khác ngoài khóa.** Điều kiện bất biến nhiều field có thể bị vi phạm. Xác định rõ vùng bảo vệ và cùng sử dụng một khóa.
4. **Quên `unlock()` hoặc giữ khóa khi làm I/O.** Luôn `try/finally`; tách tính toán ngắn trong vùng khóa khỏi mạng/DB nếu có thể.
5. **Lấy nhiều khóa theo thứ tự bất kỳ.** Hai thread có thể khóa A rồi chờ B và khóa B rồi chờ A. Dùng một thứ tự khóa toàn cục, giảm nesting, hoặc `tryLock` với timeout và chiến lược retry có giới hạn.
6. **Bỏ qua `InterruptedException`.** Nếu không thể ném tiếp, thường nên khôi phục cờ bằng `Thread.currentThread().interrupt()` và thoát/cancel logic thích hợp, tránh tiếp tục âm thầm chờ.
7. **Dùng `CopyOnWriteArrayList` cho danh sách cập nhật liên tục.** Mỗi lần ghi sao chép backing array, dễ tốn CPU/bộ nhớ.
8. **Dùng `LongAdder.sum()` để đưa ra quyết định cần snapshot tuyến tính.** `sum()` không atomic trong lúc cập nhật; cân nhắc atomic counter hoặc khóa.
9. **Duyệt `Collections.synchronizedMap/list` mà không khóa ngoài.** Wrapper không tự bảo vệ cả vòng lặp; đồng bộ trên wrapper trong suốt thời gian duyệt.
10. **Cho rằng test chạy một lần không lộ race là code an toàn.** Interleaving phụ thuộc timing; kiểm tra bất biến, dùng barrier/latch cho tình huống tái lập, stress test nhiều lần. Dùng JFR/thread dump để phân tích tranh chấp/deadlock; dùng JMH khi so sánh hiệu năng.
11. **Giữ dữ liệu nghiệp vụ trên singleton field rồi scale ngang.** State tại mỗi replica khác nhau; chọn kho dữ liệu chung hoặc kiến trúc phân vùng phù hợp.
12. **Nghĩ virtual thread loại bỏ race condition.** Virtual thread (Java 21+) vẫn truy cập shared state như thread khác; vẫn cần đúng cơ chế đồng bộ, và nên hạn chế vùng khóa chặn dài.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `volatile` giúp các luồng nhìn thấy thay đổi nhưng không đảm bảo `x++` chính xác?
2. Khi nào một `AtomicReference` tới object state bất biến hợp lý hơn nhiều biến atomic rời rạc?
3. Vì sao `map.get` rồi `map.put` không an toàn dù `map` là `ConcurrentHashMap`? Bạn sẽ chọn `merge` hay `compute`?
4. `LongAdder` phù hợp với metrics, nhưng vì sao không nên dùng `sum()` để quyết định còn đúng một suất đặt chỗ?
5. Điều gì xảy ra nếu `ReentrantLock.unlock()` không nằm trong `finally` hoặc `Condition.await()` chỉ kiểm tra điều kiện bằng `if`?
6. Một Spring service chạy ba replica có thể dùng `synchronized` để bảo đảm không bán quá số lượng hàng trong database không? Vì sao?

## 11. Tài liệu tham khảo chính thức

- [Java SE 17 – java.util.concurrent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)
- [Java SE 17 – concurrent locks](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/package-summary.html)
- [Java SE 17 – atomic variables](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)
- [Java SE 17 – ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)

**Điểm cần ghi nhớ:** Hãy bắt đầu từ bất biến của dữ liệu và phạm vi chia sẻ (một object, một JVM hay nhiều tiến trình). Chọn công cụ nhỏ nhất đáp ứng atomicity, visibility và liveness; chỉ tối ưu dựa trên contention và nhu cầu quan sát thực tế.