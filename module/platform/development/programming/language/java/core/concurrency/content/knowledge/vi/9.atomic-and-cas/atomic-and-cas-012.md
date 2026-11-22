# Chọn atomic, lock hay thread confinement trong Java Concurrency

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **atomic variables**, **khóa (lock)** và **thread confinement** theo mục tiêu bảo vệ dữ liệu, không chỉ theo cú pháp Java.
- Xác định **bất biến (invariant)** cần giữ, phạm vi cập nhật nguyên tử, số lượng thread có quyền sở hữu và quan hệ *happens-before* trước khi chọn cơ chế.
- Dùng **AtomicInteger**, **AtomicLong**, **AtomicReference** và **compareAndSet (CAS)** cho phép cập nhật độc lập hoặc chuyển đổi một trạng thái được đóng gói bất biến.
- Dùng **synchronized** hay **ReentrantLock** khi một quyết định cần bảo vệ nhiều phép đọc/ghi trong cùng critical section; hiểu lý do phải đọc và ghi theo cùng một giao thức khóa.
- Tổ chức **thread confinement**, **thread-local state** hoặc một worker sở hữu trạng thái để giảm nhu cầu chia sẻ mutable state; nhận biết giới hạn của **ThreadLocal**, thread pool, chuyển giao quyền sở hữu và callback.
- Tránh những suy luận sai: “atomic nghĩa là cả nghiệp vụ nguyên tử”, “volatile thay thế khóa”, “ThreadLocal tự động làm mọi thứ thread-safe”, hoặc “không có data race thì chắc chắn đúng”.
- Viết, chạy và kiểm thử Java 17+ theo đặc tả kết quả thay vì dựa vào sleep hoặc thứ tự log không xác định.

Bài học thuộc **Java concurrency nói chung**, trong nhóm **Atomic & CAS**. Các cơ chế chuyên biệt của Spring có chương riêng, không nằm trong phạm vi bài này.

## 2. Ba lựa chọn xử lý cùng một vấn đề

Giả sử nhiều thread cần xử lý yêu cầu đặt vé. Một cách thiết kế dùng biến nguyên tử cho số vé còn lại; cách khác giữ khóa khi kiểm tra số vé, ghi đơn và cập nhật tổng; cách thứ ba **chỉ một worker được quyền thay đổi** trạng thái đặt vé và các thread khác gửi yêu cầu đến worker đó.

Cả ba đều có thể hợp lệ nếu **đặc tả và giao thức sở hữu dữ liệu** phù hợp. Không có một lựa chọn “nhanh nhất” hoặc “đúng nhất” cho mọi bài toán.

| Lựa chọn | Ý tưởng trung tâm | Dùng tốt khi | Cần cảnh giác |
| --- | --- | --- | --- |
| **Atomic / CAS** | Một thao tác nguyên tử lên một biến hoặc một reference đại diện trạng thái | Bộ đếm, cờ, CAS chuyển trạng thái, snapshot bất biến | Chuỗi nhiều thao tác atomic riêng vẫn có logic race |
| **Lock** | Chỉ một thread mỗi lần thực hiện critical section bảo vệ bất biến | Nhiều trường liên quan, check–then–act, thao tác cần đọc rồi sửa | Deadlock, giữ khóa lâu, chọn sai lock, bỏ sót nhánh unlock |
| **Thread confinement** | Không cho nhiều thread đồng thời chạm vào mutable state | Bộ xử lý tuần tự, dữ liệu tạm riêng thread, ownership rõ | Reference bị rò, nhiều worker cùng truy cập, thread pool và chuyển thread |

**Lời giải bắt đầu từ câu hỏi “cái gì bắt buộc phải đúng?”**, không bắt đầu từ việc chọn AtomicInteger hay synchronized vì quen thuộc.

## 3. Câu hỏi thiết kế trước khi chọn cơ chế

Hãy trả lời theo thứ tự:

1. **Mutable state nằm ở đâu?** Là một số nguyên, một cặp số dư, một hàng đợi hay cả object graph?
2. **Thread nào được đọc hoặc ghi?** Một thread duy nhất, vài worker trong cùng JVM, hay nhiều JVM/process?
3. **Bất biến là gì?** Ví dụ tổng tiền được bảo toàn, stock không âm, một job chỉ được nhận một lần.
4. **Quyết định cần nguyên tử gồm mấy bước?** Chỉ increment; hay đọc stock, kiểm tra, trừ rồi ghi kết quả?
5. **Có chuyển giao ownership không?** Task được gửi qua queue, callback chạy trên thread nào, có trả về mutable object không?
6. **Cần blocking hay tránh blocking?** Hệ thống có thể chấp nhận contention, CAS retry, hoặc phải có đường timeout/hủy?
7. **Có external side effect không?** Ghi DB, file, gửi email hoặc gọi dịch vụ không trở thành transaction chỉ nhờ Java atomic/lock.
8. **Cần đo đạc gì?** Throughput, contention, fairness, latency đuôi, bộ nhớ và độ phức tạp bảo trì.

Nếu chỉ **một giá trị độc lập** cần cập nhật nguyên tử, atomic thường đơn giản. Nếu **nhiều trường phải đổi cùng nhau**, lock hoặc một snapshot bất biến được thay bằng CAS có thể phù hợp. Nếu có thể **không chia sẻ trạng thái để tránh đồng bộ hóa**, thread confinement thường giảm độ phức tạp. Đó là điểm khởi đầu, không phải quy tắc cứng.

## 4. Nền tảng: atomicity, visibility, ordering và happens-before

Các vấn đề concurrency thường trộn lẫn ba thuộc tính:

- **Atomicity:** thao tác cần thiết có diễn ra như một đơn vị không bị xen giữa hay không?
- **Visibility:** thread khác có nhìn thấy các ghi đã thực hiện không?
- **Ordering:** những thao tác nào bắt buộc xảy ra trước thao tác khác?

**Java Memory Model (JMM)** dùng quan hệ **happens-before** để quy định khả năng quan sát và thứ tự của các hành động.

Một vài quan hệ quan trọng:

- Các hành động trước **Thread.start()** happens-before các hành động của thread mới.
- Các hành động trong thread hoàn tất happens-before hành động của thread khác sau khi **join()** kết thúc do thread đích đã hoàn thành.
- **Unlock** một monitor happens-before lần **lock tiếp theo** trên monitor đó.
- Việc ghi một biến **volatile** happens-before các lần đọc volatile tương ứng về sau theo synchronization order.
- Các lớp atomic sử dụng ngữ nghĩa bộ nhớ theo hợp đồng API, và những thao tác như **compareAndSet** còn thực hiện kiểm tra–đổi giá trị một cách nguyên tử.

**Thread.sleep()**, **Thread.yield()** và việc log xuất hiện theo thứ tự “có vẻ đúng” không thay thế happens-before.

### Volatile không biến một chuỗi bước thành atomic

~~~java
// Minh họa lỗi trong lớp có field chia sẻ:
volatile int count;

// Hai thread cùng gọi:
count++; // Vẫn gồm đọc, cộng và ghi: không phải increment nguyên tử.
~~~

Volatile phù hợp với một số **cờ trạng thái** hoặc **công bố reference**, nhưng **count++** vẫn cần AtomicInteger, synchronized hay giải pháp sở hữu riêng nếu phải giữ số đếm chính xác.

### Không có data race vẫn có thể sai logic

~~~java
// Minh họa logic race: stock là AtomicInteger đã được tạo.
if (stock.get() > 0) {
    stock.decrementAndGet();
}
~~~

Từng lời gọi AtomicInteger là thread-safe, nhưng hai thread có thể cùng thấy stock bằng 1 rồi đều trừ, khiến stock thành -1. **Bất biến “stock không âm” bị phá** vì check–then–act không nguyên tử.

## 5. Atomic: khi một biến là đơn vị quyết định phù hợp

Các lớp trong **java.util.concurrent.atomic** cung cấp các phép đọc, ghi, tăng, cộng, CAS và cập nhật hàm trên một đơn vị trạng thái.

Ví dụ:

| API | Nhu cầu thường gặp | Giới hạn cần nhớ |
| --- | --- | --- |
| **AtomicInteger / AtomicLong** | Bộ đếm, sequence, trạng thái số | Không làm nhiều biến khác nhau thành một transaction |
| **AtomicBoolean** | Cờ chuyển trạng thái một lần | Boolean không mô tả nhiều giai đoạn nghiệp vụ phức tạp |
| **AtomicReference<T>** | Công bố hoặc CAS reference đến một snapshot | Đối tượng T cần được thiết kế bất biến hoặc đồng bộ khi sửa |
| **AtomicIntegerArray** và các atomic array | Cập nhật phần tử có bảo đảm atomic tương ứng | Nhiều phần tử không tự được cập nhật cùng lúc |
| **LongAdder** | Thống kê tăng cộng dưới contention cao | **sum() không phải atomic snapshot** khi đang cập nhật |

**CAS** là phép so sánh giá trị hiện tại với giá trị kỳ vọng và chỉ ghi giá trị mới nếu điều kiện so sánh thành công. CAS có thể thất bại vì thread khác vừa cập nhật; chương trình thường cần thử lại. Không coi CAS retry là miễn phí hoặc bảo đảm mọi thread được phục vụ công bằng.

### Ví dụ 1: AtomicInteger cộng chính xác

Tệp **AtomicCounterChoiceDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterChoiceDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("count = " + counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCounterChoiceDemo.java
java AtomicCounterChoiceDemo
~~~

Stdout:

~~~text
count = 20000
~~~

**Vì sao chọn atomic?** Mỗi yêu cầu chỉ cần tăng một counter dùng chung, không có bất biến trải trên nhiều trường. **incrementAndGet()** bảo đảm tăng nguyên tử; **join()** chỉ làm main chờ đủ hai worker trước khi in, chứ không phải cơ chế sửa lost update.

Nếu counter chỉ phục vụ thống kê nhiều luồng, không cần đọc ngay một tổng chính xác trong lúc cập nhật, có thể cân nhắc LongAdder; nhưng không thay AtomicLong bằng LongAdder khi API đòi một phép **getAndIncrement**, sequence tuyến tính hoặc snapshot ngay lập tức.

## 6. Atomic CAS: kiểm tra điều kiện và cập nhật trong cùng phép

Giả sử có đúng **1 vé** và hai thread cùng đặt vé. Bất biến: không chấp nhận hơn 1 yêu cầu và số vé còn lại không âm.

Nếu chỉ dùng **get()** rồi **decrementAndGet()**, hai thread có thể cùng vượt điều kiện. CAS giải quyết bằng cách **chỉ trừ nếu giá trị chưa đổi**.

Tệp **AtomicReservationDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicReservationDemo {
    static boolean reserve(AtomicInteger stock) {
        while (true) {
            int seen = stock.get();
            if (seen <= 0) {
                return false;
            }

            if (stock.compareAndSet(seen, seen - 1)) {
                return true;
            }
            // Có thread đã đổi stock: đọc lại và thử lại.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger stock = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger();

        Runnable buyer = () -> {
            if (reserve(stock)) {
                accepted.incrementAndGet();
            }
        };

        Thread first = new Thread(buyer, "buyer-1");
        Thread second = new Thread(buyer, "buyer-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("accepted = " + accepted.get());
        System.out.println("remaining = " + stock.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicReservationDemo.java
java AtomicReservationDemo
~~~

Stdout:

~~~text
accepted = 1
remaining = 0
~~~

CAS đảm bảo chỉ một chuyển đổi **1 → 0** thành công. Thread còn lại nhận trạng thái 0 và từ chối. Không cần dựa vào thread nào chạy trước.

**Giới hạn quan trọng:** Ví dụ chỉ quản lý số vé trong bộ nhớ của **một JVM**. Nếu sau khi CAS thành công còn gọi thanh toán, ghi đơn hàng hoặc phát thông báo, các side effect đó **không nằm trong một transaction cùng CAS**. Hãy phân biệt **giữ chỗ đã được cấp quyền** với **giao dịch nghiệp vụ hoàn tất** và thiết kế retry, rollback/compensation, idempotency tương ứng.

### Vì sao CAS loop có thể khó bảo trì?

Nếu logic chuyển đổi liên quan nhiều trường mutable, nested collection, điều kiện phức tạp hoặc thao tác cần I/O, việc xây state mới rồi CAS có thể tốn allocation, phải lặp lại nhiều lần và dễ sinh side effect trùng nếu đặt hành động bên ngoài vào trong vòng retry.

Một nguyên tắc: **hàm tính trạng thái mới trong CAS loop nên thuần (không có side effect không thể lặp)**. Việc có một CAS thất bại không có nghĩa hàm đã được gọi đúng một lần.

## 7. Nhiều trường vẫn có thể dùng CAS nếu đóng gói vào một snapshot bất biến

Không nên hiểu “atomic chỉ dùng cho một field” theo nghĩa tuyệt đối. Có thể đóng gói **cả bộ bất biến** vào một **record immutable** và thay **một reference** bằng CAS. Nhờ đó mọi reader nhận **snapshot nhất quán**.

Ví dụ hai trường **available** và **reserved** có bất biến:

- available không âm.
- reserved không âm.
- available + reserved luôn bằng tổng ban đầu.

Tệp **AtomicSnapshotDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Inventory(int available, int reserved) {}

    static boolean reserveOne(AtomicReference<Inventory> ref) {
        while (true) {
            Inventory old = ref.get();

            if (old.available() <= 0) {
                return false;
            }

            Inventory next = new Inventory(
                    old.available() - 1,
                    old.reserved() + 1
            );

            if (ref.compareAndSet(old, next)) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Inventory> ref =
                new AtomicReference<>(new Inventory(100, 0));

        Runnable task = () -> {
            for (int i = 0; i < 50; i++) {
                reserveOne(ref);
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(task, "worker-" + i);
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        Inventory end = ref.get();
        System.out.println("available = " + end.available());
        System.out.println("reserved = " + end.reserved());
        System.out.println(
                "total = " + (end.available() + end.reserved())
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicSnapshotDemo.java
java AtomicSnapshotDemo
~~~

Stdout:

~~~text
available = 0
reserved = 100
total = 100
~~~

**Vì sao đúng?** Mỗi chuyển đổi CAS thay **một reference** tới đối tượng Inventory đã hoàn tất xây dựng. Reader quan sát một phiên bản đầy đủ, không thấy trạng thái trung gian available đã giảm nhưng reserved chưa tăng. Bốn worker có tổng 200 lần thử giữ chỗ, trong khi chỉ có 100 vé; các lần thử còn lại từ chối.

**Điều kiện bắt buộc:**

- Inventory là **immutable** trong ví dụ: record chỉ chứa hai giá trị int, không có mutable collection lộ ra ngoài.
- Tất cả thay đổi có ý nghĩa với bất biến đều đi qua **cùng AtomicReference**.
- Không có thao tác bất hồi phục trong CAS loop.
- Người đọc cần snapshot nhất quán thì chỉ đọc **một lần ref.get()**, rồi dùng các field của cùng snapshot; đừng đọc reference hai lần để lấy hai field rồi coi đó là một phiên bản.

Nếu state rất lớn, allocation/GC hoặc CAS retry dưới contention có thể tốn chi phí. Với logic nhiều bước, khóa có thể dễ hiểu hơn.

### ABA và danh tính reference

CAS có thể gặp **ABA**: giá trị chuyển A→B→A, nên một thread thấy “vẫn là A” dù trạng thái đã qua một lần thay đổi. Điều này quan trọng khi semantics phụ thuộc lịch sử hoặc version, nhất là với cấu trúc lock-free.

Nếu cần nhận biết mọi lần thay đổi, có thể gắn **version** trong state immutable hoặc xét **AtomicStampedReference**. Với CAS trên reference đến các record immutable **mới được tạo mỗi lần** như ví dụ, từng lần thay thế dùng object mới nên không tự quay lại cùng reference cũ, nhưng không vì vậy mà mọi hệ thống dùng AtomicReference đều miễn nhiễm ABA.

## 8. Lock: bảo vệ một critical section nhiều bước

Khi quyết định gồm nhiều trường phải được cập nhật cùng nhau, **synchronized** hoặc **ReentrantLock** thường trực quan hơn CAS state phức tạp. Một lock bảo vệ **bất biến**, chứ không phải đơn thuần một biến.

Ví dụ kho có hai trường **available** và **reserved**. Nếu dùng hai AtomicInteger độc lập:

~~~java
// Mã minh họa lỗi nếu muốn snapshot nhất quán:
available.decrementAndGet();
reserved.incrementAndGet();
~~~

Mỗi phép cập nhật riêng lẻ đều atomic nhưng người đọc có thể nhìn thấy trạng thái **đã giảm available nhưng chưa tăng reserved**. Một ReentrantLock dùng chung cho các phương thức đọc/ghi sẽ tránh trường hợp đó.

### Mẫu ReentrantLock đúng

~~~java
// Mã minh họa trong một lớp có ReentrantLock lock và shared state.
lock.lock();
try {
    // Đọc điều kiện + cập nhật toàn bộ bất biến.
} finally {
    lock.unlock();
}
~~~

**finally** rất quan trọng: nếu code ném exception hoặc return sớm, thread phải nhả lock. Ngược lại, **tryLock()** trả false hay **lockInterruptibly()** ném InterruptedException **trước khi lấy được khóa** thì không được unlock khóa mình chưa sở hữu.

### Ví dụ 4: khóa bảo vệ stock và số lượng đã đặt

Tệp **LockedInventoryDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class LockedInventoryDemo {
    static final class Inventory {
        private final ReentrantLock lock = new ReentrantLock();
        private int available = 100;
        private int reserved;

        boolean reserveOne() {
            lock.lock();
            try {
                if (available == 0) {
                    return false;
                }

                available--;
                reserved++;
                return true;
            } finally {
                lock.unlock();
            }
        }

        int[] snapshot() {
            lock.lock();
            try {
                return new int[] {available, reserved};
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();

        Runnable task = () -> {
            for (int i = 0; i < 50; i++) {
                inventory.reserveOne();
            }
        };

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(task, "worker-" + i);
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }

        int[] end = inventory.snapshot();
        System.out.println("available = " + end[0]);
        System.out.println("reserved = " + end[1]);
        System.out.println("total = " + (end[0] + end[1]));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LockedInventoryDemo.java
java LockedInventoryDemo
~~~

Stdout:

~~~text
available = 0
reserved = 100
total = 100
~~~

**Điểm khác AtomicSnapshotDemo:** Inventory giữ hai trường **mutable** riêng biệt, nhưng mọi lần đọc/ghi liên quan đến bất biến đều đi qua **cùng ReentrantLock**. Trong critical section, check rồi giảm available và tăng reserved được thực hiện như một đơn vị đối với các thread tuân thủ giao thức.

**Lock phù hợp khi:**

- Cần bảo vệ nhiều field hoặc một collection có thao tác phức tạp.
- Có nhiều điều kiện phải kiểm tra trước khi commit.
- Logic cần sửa cùng lúc nhiều vùng nhớ mà CAS trên snapshot trở nên rườm rà.
- Cần đường chờ thông qua **Condition** (với ReentrantLock) hoặc monitor wait/notify.
- Có yêu cầu điều phối cụ thể như tryLock, chờ có timeout hoặc lock acquisition có thể ngắt.

**Lock không tự tạo transaction cho DB**, cũng không bảo vệ các instance ở JVM khác. Không giữ khóa qua cuộc gọi mạng hoặc I/O dài khi có thể tách các bước an toàn, vì tăng contention và nguy cơ deadlock.

### synchronized hay ReentrantLock?

| Tiêu chí | synchronized | ReentrantLock |
| --- | --- | --- |
| Nhả khóa khi thoát scope | Tự động nhả monitor | Phải đặt unlock trong finally |
| Reentrant | Có | Có |
| Memory visibility | Monitor unlock/lock có happens-before | Lock/unlock có ngữ nghĩa tương ứng |
| Thử lấy khóa không chờ | Không có cú pháp try-enter | tryLock() |
| Chờ lấy khóa có timeout | Không trực tiếp | tryLock(timeout, unit) |
| Ngắt khi đang chờ acquisition | Không ném InterruptedException khi vào monitor | lockInterruptibly() |
| Chờ condition | Object.wait/notify | Condition.await/signal |
| Fairness cấu hình | Không | Có tùy chọn, nhưng không bảo đảm công bằng tuyệt đối |

**Ưu tiên lựa chọn đơn giản nhất đáp ứng yêu cầu**. Không khẳng định ReentrantLock luôn nhanh hơn synchronized; hiệu quả phụ thuộc JIT, contention và thời gian giữ khóa.

## 9. Thread confinement: giảm chia sẻ thay vì khóa nhiều hơn

**Thread confinement** là cách tổ chức ownership để một mutable state **chỉ được truy cập bởi một thread** trong giai đoạn sử dụng. Nếu không có truy cập đồng thời từ thread khác, bản thân state đó có thể không cần atomic hoặc lock.

Các kiểu confinement:

1. **Stack/local confinement:** biến cục bộ và object được tạo trong phương thức, không để reference thoát sang thread khác. Không phải cứ “biến local” là an toàn nếu nó trỏ đến **đối tượng chia sẻ**.
2. **Thread-local confinement:** mỗi thread có bản sao dữ liệu riêng, có thể dùng **ThreadLocal<T>**. Không mặc nhiên giúp tổng hợp kết quả trên nhiều thread.
3. **Ownership confinement:** một worker/actor/event loop được giao **quyền duy nhất** cập nhật state; những thread khác gửi message/task và nhận kết quả qua giao thức đồng bộ.

Điểm cốt lõi là **quyền truy cập**, không phải chỉ đặt một biến vào ThreadLocal. Nếu reference đến object mutable bị gửi ra ngoài, quyền sở hữu có thể bị phá.

### Ví dụ 5: một worker sở hữu counter, không cần khóa trong counter

Tệp **ConfinedCounterDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConfinedCounterDemo {
    static final class Counter {
        private int value;

        void increment() {
            value++; // An toàn nếu chỉ owner thread sửa.
        }

        int snapshot() {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService owner = Executors.newSingleThreadExecutor();
        Counter counter = new Counter();

        try {
            for (int i = 0; i < 1_000; i++) {
                owner.submit(counter::increment);
            }

            Future<Integer> result = owner.submit(counter::snapshot);
            System.out.println("value = " + result.get());
        } finally {
            owner.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConfinedCounterDemo.java
java ConfinedCounterDemo
~~~

Stdout:

~~~text
value = 1000
~~~

**Vì sao đúng?**

- Executor một thread thực hiện các task đã submit theo thứ tự tuần tự; các lần **counter.increment()** không chạy chồng nhau.
- Main **không trực tiếp đọc/ghi counter.value** trong lúc owner xử lý. Thay vào đó main gửi task đọc **counter.snapshot()** tới chính owner, rồi lấy kết quả bằng **Future.get()**.
- Task snapshot được submit sau 1.000 task tăng từ cùng thread; trong executor một worker, nó chạy sau những task ấy nên trả 1.000.
- Future.get() cung cấp kết quả và quan hệ đồng bộ hóa tương ứng cho caller. Không cần synchronized trong Counter **vì giao thức ownership** đã loại bỏ truy cập đồng thời đến state đó.

**Ranh giới phải giữ:** Nếu main hoặc thread thứ ba gọi trực tiếp counter.increment() trong lúc executor đang sử dụng counter, confinement bị phá; code lại có nguy cơ race. Nếu dùng một thread pool nhiều worker thay vì **newSingleThreadExecutor()**, các task không còn được đảm bảo chạy trên cùng một thread theo mô hình này.

Đừng coi executor một worker là transaction hoặc durable queue. Nó không làm side effect bên ngoài trở thành atomic; kết quả lỗi trong task cần được xử lý qua Future, và lifecycle executor cần shutdown phù hợp.

## 10. ThreadLocal: trạng thái riêng cho từng thread, nhưng không phải per-request

**ThreadLocal<T>** cung cấp một giá trị gắn với **thread hiện tại**. Mỗi thread có thể nhận một object riêng từ **withInitial()**. Nó hữu ích cho buffer tạm, bộ đếm tạm hoặc ngữ cảnh thật sự có thread affinity.

~~~java
// Minh họa trong một lớp có các import tương ứng:
private static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);

// Trong phần mã chạy của một thread:
StringBuilder buffer = BUFFER.get();
try {
    buffer.append("work");
    // Dùng buffer trong chính thread này.
} finally {
    BUFFER.remove();
}
~~~

Đây là đoạn minh họa, không phải ứng dụng độc lập.

**Những giới hạn quan trọng:**

- **ThreadLocal không biến một shared mutable object thành riêng tư** nếu initializer trả về cùng một object được chia sẻ hoặc reference bị trao giữa threads.
- **Thread pool tái sử dụng thread:** một task kết thúc rồi task khác chạy trên cùng thread có thể thấy ThreadLocal còn sót lại; dùng **remove() trong finally** khi scope ngữ cảnh kết thúc.
- **ThreadLocal là per-thread, không phải per-request hay per-logical-task.** Một công việc di chuyển sang thread khác qua executor/callback không tự mang theo ThreadLocal.
- Cần tổng hợp dữ liệu từ nhiều thread thì phải có bước **merge** hoặc cơ chế đồng bộ riêng. Các giá trị ThreadLocal riêng lẻ không tự tạo một tổng toàn cục chính xác.
- ThreadLocal còn sống theo thread nếu không được dọn dẹp, có thể làm giữ reference/tài nguyên không mong muốn ở thread sống lâu.

Nếu bài toán là “tất cả task cập nhật một số dư dùng chung”, đừng dùng ThreadLocal rồi giả định số dư chung tự được bảo vệ. Thay vào đó xác định ownership hoặc cơ chế tổng hợp có đồng bộ hóa.

## 11. Confinement không miễn trừ safe publication và ownership transfer

Thread confinement an toàn khi quyền sở hữu rõ ràng. Khi dữ liệu được chuyển từ thread A sang thread B:

- Trước khi chuyển giao, A có thể tự sửa object.
- Khi giao quyền cho B, phải dùng một **giao thức giao tiếp an toàn** (ví dụ BlockingQueue, submit task tới ExecutorService, CompletableFuture với hợp đồng phù hợp).
- Sau khi giao quyền, A không tiếp tục sửa object đó đồng thời nếu B đang sử dụng, trừ khi có đồng bộ hóa riêng.
- Nếu cần nhiều người đọc, có thể gửi **snapshot immutable** thay vì object mutable.
- Nếu object được trả về cho caller rồi vẫn tiếp tục bị owner sửa, cần xem nó là shared mutable state chứ không còn confined.

### Ví dụ giao tiếp producer/consumer

Một producer có thể tạo các message bất biến và đưa vào **BlockingQueue**. Consumer sở hữu trạng thái tổng hợp và cập nhật tuần tự. Queue có các bảo đảm giao tiếp và memory consistency do API quy định. Nhưng nếu producer giữ tham chiếu tới một message mutable rồi sửa sau khi put, consumer có thể lại thấy race trên nội dung message; queue không “đóng băng” object.

**Confinement** thường đơn giản hơn khi task/message là immutable hoặc chỉ chứa dữ liệu không chia sẻ mutable.

### Confinement theo giai đoạn

Một thread có thể xây object hoàn chỉnh rồi trao **ownership độc quyền** sang thread khác. Đây là *ownership transfer*, không phải object buộc phải sống mãi trên cùng thread. Điều quan trọng là **không có hai chủ đồng thời và việc chuyển giao có safe publication**.

## 12. Bảng quyết định nhanh theo tình huống

| Tình huống | Ưu tiên xem xét | Lý do |
| --- | --- | --- |
| Tổng số request được ghi nhận chính xác, cập nhật độc lập | AtomicLong hoặc AtomicInteger | Một increment nguyên tử |
| Counter thống kê rất nhiều thread, chỉ cần đọc tổng ước lượng tại thời điểm đang cập nhật | LongAdder | Phân tán điểm tranh chấp; sum() không là snapshot nguyên tử khi có update |
| Một trạng thái PENDING → RUNNING chỉ được một thread nhận | AtomicReference/AtomicInteger CAS | Transition một biến có điều kiện nguyên tử |
| “Nếu còn vé thì trừ một” trên một biến số lượng | CAS loop | Gộp check và update |
| Stock và reserved phải cùng cập nhật | Lock hoặc AtomicReference tới immutable snapshot | Bảo vệ bất biến nhiều trường |
| Nhiều bước kiểm tra/gỡ lỗi hoặc thay đổi cấu trúc dữ liệu lớn | synchronized/ReentrantLock | Critical section rõ và dễ lập luận |
| Buffer riêng cho mỗi thread, không trao reference | Local/ThreadLocal confinement | Tránh chia sẻ mutable state |
| Một stream sự kiện được xử lý bởi một owner | Single-thread executor/actor-style ownership | Tuần tự hóa cập nhật |
| Cần cập nhật nhiều DB records bởi nhiều instance | Transaction/conditional update tại DB | Java lock/atomic chỉ có phạm vi JVM |
| Cần snapshot cấu hình thay nguyên khối | Volatile/AtomicReference tới immutable snapshot | Đọc một reference để thấy phiên bản nhất quán |
| Cần await condition hoặc acquisition timeout | ReentrantLock/Condition, hoặc blocking primitive phù hợp | API chờ/tín hiệu có hợp đồng rõ |
| Dữ liệu vừa được xử lý bởi thread pool vừa bị caller sửa trực tiếp | Phải thay đổi thiết kế ownership hoặc đồng bộ | Không còn confinement |

**Chọn theo bất biến lớn nhất**, không theo tên class. Một hệ thống có thể kết hợp: owner thread xử lý task, AtomicLong cho metrics độc lập, lock cho một cấu trúc chia sẻ khác. Từng cơ chế cần ranh giới sở hữu rõ ràng.

## 13. Hiệu năng: đừng giả định atomic luôn nhanh hơn lock

Trong tải nhẹ, synchronized hoặc ReentrantLock có thể rất đủ dùng. Trong tải nặng, CAS loop trên cùng một atomic có thể retry nhiều lần; một lock cũng có thể gây contention và chuyển ngữ cảnh. Confinement giảm tranh chấp trên state nhưng **giới hạn throughput theo tốc độ một owner**, có thể trở thành bottleneck.

| Cơ chế | Chi phí có thể phát sinh | Điểm cần đo |
| --- | --- | --- |
| Atomic/CAS | Cache-line contention, retry, spinning, allocation snapshot | CAS failures, throughput, latency |
| Lock | Lock contention, chờ, chuyển context, fairness overhead | Thời gian giữ/chờ lock, tail latency |
| Confinement | Queueing delay, chi phí message, bottleneck một owner | Queue length, latency chờ, tốc độ tiêu thụ |
| ThreadLocal | Nhiều bản sao bộ nhớ, cleanup/thread reuse | Memory footprint, lifecycle |

Không nên chạy benchmark bằng cách lặp một lần hoặc thêm Thread.sleep() rồi kết luận thứ tự hiệu năng. Nên thử dưới workload đại diện, với nhiều mức cạnh tranh, thời gian warmup/JIT và báo cáo cả throughput lẫn latency. Những lựa chọn cải thiện một metric có thể làm metric khác xấu đi.

Một **LongAdder.sum()** đang diễn ra trong lúc nhiều thread cập nhật có thể không phản ánh một thời điểm nguyên tử. Nếu cần số chính xác phục vụ cấp ID, check quota hoặc quyết định kinh doanh, hãy dùng cơ chế có hợp đồng đúng, không dùng LongAdder chỉ vì throughput cao.

## 14. Các anti-pattern cần tránh

### Một AtomicInteger không bảo vệ nhiều field khác

~~~java
// Minh họa sai nếu yêu cầu available + reserved luôn nhất quán:
AtomicInteger available = new AtomicInteger(10);
AtomicInteger reserved = new AtomicInteger();

available.decrementAndGet();
reserved.incrementAndGet();
~~~

Hai phép atomic có thể bị reader khác chen vào giữa. Sửa bằng lock bảo vệ toàn bộ thao tác, hoặc CAS trên immutable snapshot đại diện cả hai trường.

### Hai lock khác nhau cho cùng state

~~~java
// Minh họa lỗi nếu mỗi caller tạo lock riêng:
void update() {
    synchronized (new Object()) {
        shared++;
    }
}
~~~

Không có cùng monitor qua các lần gọi, nên không bảo vệ shared. Dùng một đối tượng khóa **private final** dùng chung cho tất cả đường truy cập liên quan.

### Check rồi act không nguyên tử

~~~java
// Minh họa lỗi:
if (jobStatus.get() == PENDING) {
    jobStatus.set(RUNNING);
}
~~~

Ví dụ giả định jobStatus là AtomicReference có các giá trị trạng thái PENDING/RUNNING định nghĩa trước. Hai thread đều có thể thấy PENDING và thực thi cùng job. Dùng **compareAndSet(PENDING, RUNNING)** rồi chỉ thread thành công mới được bắt đầu xử lý.

### Đọc state có lock nhưng ghi không lock

Nếu writer giữ lock còn reader đọc plain field ngoài khóa, reader không tham gia cùng giao thức đồng bộ hóa. Sử dụng cùng lock cho cả các đường truy cập liên quan, hoặc thiết kế khác có happens-before đúng.

### Dùng ThreadLocal để “cách ly” object chia sẻ

Nếu nhiều ThreadLocal giữ **cùng reference đến một ArrayList mutable**, những thread đó vẫn có thể sửa cùng object. ThreadLocal chỉ phân tách **slot theo thread**, không tự copy sâu object.

### Trả về mutable reference từ owner

Một owner thread sở hữu HashMap, nhưng trả chính HashMap đó cho caller rồi tiếp tục sửa. Caller có thể tự sửa hoặc iterate cùng lúc, phá confinement. Hãy trả immutable copy/snapshot hoặc dùng API gửi command tới owner.

### Giữ lock khi gọi I/O dài

~~~java
lock.lock();
try {
    // Gọi mạng, sleep, chờ Future.get(), callback không kiểm soát...
} finally {
    lock.unlock();
}
~~~

Mã minh họa này không phải chương trình độc lập. Nó có thể làm contention hoặc deadlock nếu thread khác cần lock để hoàn tất điều kiện chờ. Chỉ giữ khóa cho phần bắt buộc thuộc bất biến; không tự động tách critical section nếu điều đó phá atomicity.

### Nghĩ “không có data race” đồng nghĩa đúng nghiệp vụ

Một thuật toán có thể dùng toàn AtomicInteger nhưng check-then-act vẫn sai. Một actor có thể xử lý message tuần tự nhưng vẫn ghi cùng một đơn hai lần do duplicate command. Java concurrency hỗ trợ bảo đảm dữ liệu, **không tự định nghĩa idempotency/transaction**.

## 15. Chiến lược kết hợp và ranh giới hệ thống

### Atomic cho metrics, lock cho bất biến, owner cho pipeline

Một dịch vụ có thể:

- Dùng một worker sở hữu trạng thái đang xây dựng báo cáo.
- Dùng AtomicLong cho số task đã tiếp nhận từ nhiều thread.
- Dùng một lock cho cache nhỏ bắt buộc cập nhật nhiều field cùng nhau.
- Công bố snapshot bất biến cho người đọc qua AtomicReference.

Đây là các **miền đồng bộ khác nhau**. Không vì một miền dùng AtomicReference mà bỏ khóa ở miền khác.

### Giới hạn giữa nhiều JVM/process

**AtomicInteger, ReentrantLock, synchronized và ThreadLocal** hoạt động trên các đối tượng trong một JVM. Nếu nhiều tiến trình cùng ghi một tài khoản trong cơ sở dữ liệu, cần đồng bộ hóa **tại kho dữ liệu chung**, như cập nhật có điều kiện, optimistic locking/version, constraint, transaction hoặc cơ chế coordination phù hợp.

Ví dụ CAS trong JVM có thể ngăn hai thread đặt cùng một vé **trong process đó**, nhưng không ngăn hai instance khác nhau mỗi bên bán một vé cuối cùng từ một cache cục bộ. Hãy đặt bất biến “không oversell toàn hệ thống” ở nơi có thẩm quyền quản lý lượng vé thật.

### Cancellation và retry

Nếu một task bị interrupt hoặc timeout, trạng thái atomic/lock/confinement không tự rollback hành động trước đó. Xác định rõ:

- Quyền xử lý được cấp vào thời điểm nào?
- Đã commit side effect chưa?
- Nếu retry có thể xử lý trùng không?
- Kết quả đến muộn từ attempt cũ có được phép ghi đè trạng thái mới không?

Trả lời các câu hỏi này là phần của thiết kế nghiệp vụ; đừng kỳ vọng một Java Lock tự cung cấp exactly-once execution.

## 16. Kiểm thử tính đúng đắn

Viết test theo bất biến và kết quả quan sát được:

1. **AtomicCounterChoiceDemo**: sau khi hai thread join, count luôn bằng 20.000.
2. **AtomicReservationDemo**: với 1 vé và hai người mua, accepted=1, remaining=0.
3. **AtomicSnapshotDemo**: với 100 vé và 200 lần yêu cầu, available=0, reserved=100 và tổng=100.
4. **LockedInventoryDemo**: giữ cùng bất biến của ví dụ snapshot nhưng dùng khóa bảo vệ hai trường.
5. **ConfinedCounterDemo**: mọi increment chạy trên owner và snapshot được owner thực hiện sau các command, kết quả 1.000.

Khi thiết kế test bổ sung:

- Dùng **CountDownLatch** để tạo điểm bắt đầu cạnh tranh, nhưng đừng dùng latch thay cho synchronization của code cần kiểm thử.
- Thử cả nhiều số thread, mức contention và tình huống exception/interrupt.
- Với lock, kiểm tra các nhánh **return/throw** vẫn giải phóng khóa; với tryLock chỉ unlock khi đã acquire thành công.
- Với confinement, cố tình kiểm tra không có đường gọi trực tiếp trái ownership, và các message/immutable snapshot được công bố an toàn.
- Với CAS, kiểm tra điều kiện thất bại/retry, không đưa side effect không idempotent vào hàm cập nhật có thể bị gọi lại.
- Không suy ra “chắc chắn thread-safe” chỉ vì stress test chạy vài lần không lỗi; cần lập luận theo JMM và bất biến.

Thứ tự log giữa các worker có thể không xác định; đừng gắn stdout cứng cho những đoạn không đồng bộ có thể xen kẽ. Năm ví dụ trên chỉ in tổng hợp **sau khi có giao thức completion rõ ràng**, nên có stdout xác định trong điều kiện chạy bình thường.

## 17. Checklist ra quyết định

**Trước khi viết code:**

- [ ] Tôi có một định nghĩa bất biến cụ thể và biết biến nào thuộc bất biến đó.
- [ ] Tôi biết tất cả writer/reader và các ranh giới thread/JVM có liên quan.
- [ ] Tôi có thể tránh chia sẻ mutable state hoàn toàn hay không?
- [ ] Nếu chọn atomic, thao tác atomic bao phủ **toàn bộ quyết định** cần thiết không?
- [ ] Nếu chọn CAS trên snapshot, state có thật sự immutable và không có side effect trong retry không?
- [ ] Nếu chọn lock, mọi đường truy cập đều giữ **cùng lock**, không tạo lock riêng tùy caller.
- [ ] Với ReentrantLock, mọi acquisition thành công đều được nhả đúng owner trong finally.
- [ ] Nếu nhiều lock, có thứ tự khóa nhất quán để tránh circular wait.
- [ ] Nếu chọn ThreadLocal, có cleanup trên thread pool và không nhầm per-thread với per-request.
- [ ] Nếu chọn owner thread, reference mutable có bị rò sang thread khác không?
- [ ] Có giao thức completion/safe publication cho dữ liệu được gửi giữa threads không?
- [ ] Có chiến lược riêng cho DB, side effect, timeout, retry và cancellation không?

## 18. Câu hỏi tự kiểm tra

**1. Hai thread tăng một bộ đếm dùng chung, không liên quan trạng thái nào khác. Ưu tiên gì?**  
Có thể dùng **AtomicInteger.incrementAndGet()** hoặc AtomicLong. Nếu chỉ là thống kê cộng nhiều dưới contention cao và không cần snapshot tuyến tính, cân nhắc LongAdder.

**2. Có hai field stock và reserved, sau mỗi cập nhật phải luôn thỏa stock + reserved = total. Hai AtomicInteger riêng là đủ không?**  
Không. Reader có thể quan sát hai field ở các mốc khác nhau. Dùng một lock bao phủ cập nhật/đọc hoặc một AtomicReference tới immutable snapshot.

**3. Một worker tuần tự hóa toàn bộ cập nhật vào object mutable. Có cần synchronized trong object không?**  
Không nhất thiết nếu ownership confinement là thật: không thread khác truy cập đồng thời và chuyển giao công việc/kết quả có safe publication.

**4. ThreadLocal có đảm bảo một request chỉ chạy trên đúng một thread không?**  
Không. ThreadLocal gắn với thread thực thi, không gắn với request; task chuyển thread sẽ không tự mang giá trị. Thread pool có thể tái sử dụng dữ liệu còn sót nếu không remove().

**5. CAS có thể thất bại dù code của thread hiện tại không có bug không?**  
Có. Thread khác có thể cập nhật trước, khiến giá trị hiện tại khác expected. Cần retry hoặc nhánh xử lý phù hợp.

**6. Vì sao CAS loop không nên gọi API thanh toán ở trong vòng retry?**  
Vì mỗi lần retry có thể thực thi logic trước CAS nhiều lần dù chỉ một CAS thành công. Side effect có thể bị lặp; cần tách bước nghiệp vụ theo giao thức đúng.

**7. synchronized và ReentrantLock có thể bảo vệ trạng thái ở hai JVM không?**  
Không. Java lock chỉ có hiệu lực với những thread cùng dùng đối tượng khóa tương ứng trong JVM. Dữ liệu liên tiến trình cần cơ chế ở nguồn chia sẻ.

**8. Một ứng dụng vừa dùng AtomicLong vừa dùng ReentrantLock có sai kiến trúc không?**  
Không. Các biến/nhóm bất biến khác nhau có thể cần cơ chế khác nhau, miễn là ranh giới và ownership rõ ràng.

**9. Nếu dùng lock cho writer nhưng reader đọc field thường ngoài lock, có được bảo đảm thấy cập nhật không?**  
Không thể suy ra chỉ từ lock của writer. Reader phải tham gia cùng giao thức hoặc có một quan hệ happens-before khác được thiết kế đúng.

**10. Khi nào nên ưu tiên cách đơn giản hơn về mặt bảo trì?**  
Khi yêu cầu hiệu năng chưa được chứng minh, **synchronized nhỏ và rõ ràng** có thể tốt hơn CAS state machine phức tạp; khi có thể đảm bảo ownership một worker, tránh chia sẻ có thể còn đơn giản hơn cả hai.

## 19. Tổng kết

**Atomic** phù hợp khi toàn bộ quyết định có thể được thực hiện bằng một primitive nguyên tử hoặc một CAS trên snapshot bất biến; **lock** phù hợp khi cần bảo vệ một critical section gồm nhiều bước và nhiều trường; **thread confinement** phù hợp khi có thể thiết kế **một chủ sở hữu duy nhất** cho mutable state và chỉ trao dữ liệu qua giao thức rõ ràng.

Lựa chọn đúng được đánh giá theo **bất biến, happens-before, ownership, ranh giới JVM và side effect**, không chỉ theo số dòng code hay hiệu năng được đồn đoán. Khi cần, kết hợp các cơ chế trong những miền trạng thái tách biệt; nhưng luôn xác định ai được đọc, ai được ghi, cập nhật nào phải nguyên tử và cách kiểm chứng kết quả.
