# Sửa race condition trong Java: ownership, locking, atomic và immutable state

## Mục tiêu của bài học

**Race condition** xuất hiện khi tính đúng đắn của kết quả phụ thuộc vào thứ tự xen kẽ giữa các thao tác đồng thời nhưng chương trình thiếu một giao thức phối hợp đủ mạnh. Với trạng thái chia sẻ, dấu hiệu thường là **lost update**, kiểm tra điều kiện rồi hành động trên dữ liệu đã thay đổi, hoặc quan sát một tổ hợp các trường không nhất quán. Bài này trình bày bốn chiến lược sửa ở cấp **Java SE / Java Memory Model**, không sử dụng tính năng riêng của Spring:

1. **Ownership:** một owner có quyền cập nhật mutable state; bên khác gửi yêu cầu.
2. **Locking:** các thread truy cập qua cùng lock để bảo vệ một invariant (bất biến) nghiệp vụ.
3. **Atomic:** dùng thao tác nguyên tử như `incrementAndGet`, `compareAndSet` hoặc `getAndUpdate`.
4. **Immutable state:** không sửa object đã công bố; thay bằng snapshot mới thông qua một cơ chế publish/update an toàn.

Bạn sẽ học cách nhận diện phạm vi trạng thái cần bảo vệ, hiểu atomicity/visibility/ordering, chọn giải pháp theo invariant, và tự chạy các ví dụ **Java 17+** với kết quả có thể kiểm chứng.

## 1. Xác định race và invariant trước khi chọn giải pháp

Cho một counter đơn giản:

~~~java
class Counter {
    int count;

    void increment() {
        count++;
    }
}
~~~

`count++` về mặt logic gồm **đọc → cộng một → ghi**. Hai thread có thể xen kẽ:

~~~text
Ban đầu count = 0

Thread A              Thread B
--------              --------
đọc 0
                      đọc 0
tính 1                tính 1
ghi 1
                      ghi 1

Đã gọi increment 2 lần nhưng count cuối có thể là 1.
~~~

Đây là **lost update**. Nếu các truy cập vào biến thường thiếu happens-before và có ít nhất một ghi, còn có thể là **data race** theo Java Memory Model. Hai khái niệm liên quan nhưng khác nhau:

- *Data race*: truy cập bộ nhớ xung đột giữa các thread không được sắp thứ tự bằng happens-before cần thiết.
- *Race condition*: tính đúng đắn bị phụ thuộc timing/ordering; có thể tồn tại **ngay cả khi dùng `volatile` hoặc từng phép đọc/ghi là atomic**, vì cả chuỗi thao tác nghiệp vụ vẫn chưa nguyên tử.

Bài toán phải được mô tả bằng **invariant**. Chẳng hạn: số lần tăng thành công phải bằng giá trị counter; khi bán hàng `available >= 0`; và nếu ban đầu có 500 sản phẩm thì `available + sold == 500`. Với một tài khoản, thao tác “nếu đủ tiền thì trừ” phải được xem là **một đơn vị logic**. Khi invariant gồm hai trường, đồng bộ riêng từng trường không tự bảo vệ tổ hợp của chúng.

### Ví dụ Java 17: volatile vẫn mất cập nhật

Tạo tệp **`LostUpdateDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    private static volatile int count = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increase = () -> {
            int observed = count;
            bothRead.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = observed + 1;
        };

        Thread a = new Thread(increase);
        Thread b = new Thread(increase);
        a.start();
        b.start();

        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("expected=2 actual=" + count);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Stdout khi hai thread không bị interrupt:

~~~text
expected=2 actual=1
~~~

Hai latch cố tình đảm bảo mỗi thread **đã đọc giá trị 0** trước khi thread nào được phép ghi. `volatile` giúp đọc/ghi đơn lẻ có semantics visibility/ordering rõ ràng, nhưng **không biến ba thao tác đọc–tính–ghi thành một thao tác atomic**. Đây là thí nghiệm xác định thay vì dựa vào may rủi của scheduler.

## 2. Ba khía cạnh phải giải quyết: visibility, atomicity, ordering

| Thuộc tính | Vấn đề | Cách hiểu |
| --- | --- | --- |
| **Visibility** | Thread khác có nhìn thấy ghi mới không? | Giá trị chung phải được publish/đọc theo giao thức bộ nhớ hợp lệ. |
| **Atomicity** | Một cập nhật nghiệp vụ có bị xen vào giữa không? | Check-then-act phải được bảo vệ cùng nhau. |
| **Ordering** | Những thao tác nào được bảo đảm xuất hiện trước những thao tác khác? | Dựa vào happens-before chứ không đoán scheduler. |

Một số quan hệ **happens-before** trong Java:
- Unlock một monitor xảy ra trước lock tiếp theo trên **cùng monitor**.
- Ghi `volatile` xảy ra trước các lần đọc sau đó của cùng biến trong thứ tự đồng bộ.
- Hành động xảy ra trước `Thread.start()` happens-before hành động của thread được khởi chạy.
- Các hành động của thread xảy ra trước việc một thread khác tiếp tục sau `join()` thành công.
- Các API `ExecutorService`, `Future` và concurrent collections có các bảo đảm memory consistency được tài liệu hóa; ví dụ việc chuẩn bị dữ liệu trước `submit` happens-before hành động của task, và hành động task happens-before việc sử dụng kết quả sau `Future.get()`.

Chỉ có visibility **không bảo đảm atomicity**: `volatile int count` vẫn không sửa được `count++`. Đồng thời, một phép CAS đơn lẻ được thực hiện đúng có thể giải quyết cả visibility và cập nhật nguyên tử của **một vị trí trạng thái**, nhưng không tự tạo transaction trên hai đối tượng riêng rẽ.

## 3. Chiến lược 1 — Ownership / confinement

### 3.1. Một owner chịu trách nhiệm cập nhật

Thay vì cho nhiều thread tự sửa một mutable object, giao quyền ghi cho **một owner**. Các bên khác gửi command/message; owner xử lý lần lượt:

~~~text
Producer A --- command ---\
Producer B --- command ----> Queue --> Owner --> mutable state
Producer C --- command ---/

Chỉ owner sửa trạng thái. Producer không giữ đường ghi trực tiếp.
~~~

Nếu một state được tạo và chỉ được sử dụng trong đúng một thread, đó là **thread confinement**. Một `ExecutorService` với một worker hoạt động tại một thời điểm có thể trở thành bộ xử lý command tuần tự. Lưu ý `newSingleThreadExecutor()` bảo đảm **tối đa một task chạy mỗi lúc**, nhưng khi worker chết, executor có thể thay thế bằng Java thread mới. Thiết kế phụ thuộc **tính tuần tự**, không phụ thuộc một thread ID cố định mãi mãi.

### 3.2. Ví dụ chạy được: counter có một owner

Tạo file **`OwnerCounterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class OwnerCounterDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService owner = Executors.newSingleThreadExecutor();
        final int[] counter = {0};

        try {
            List<Future<?>> writes = new ArrayList<>();
            for (int i = 0; i < 1_000; i++) {
                writes.add(owner.submit(() -> counter[0]++));
            }

            // Lệnh đọc cũng đi qua owner; main không đọc array trực tiếp.
            Future<Integer> result = owner.submit(() -> counter[0]);

            for (Future<?> write : writes) {
                write.get();
            }

            System.out.println("count=" + result.get());
        } finally {
            owner.shutdown();
            if (!owner.awaitTermination(1, TimeUnit.MINUTES)) {
                owner.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac OwnerCounterDemo.java
java OwnerCounterDemo
~~~

Stdout:

~~~text
count=1000
~~~

`counter[0]++` không trở thành atomic về bản chất. Nó đúng ở đây vì **không có hai updater cùng lúc** và mọi task được thực thi tuần tự theo thứ tự submit của executor. Việc đọc diễn ra trong một task gửi sau tất cả tác vụ cập nhật. `Future.get()` giúp chờ và phát hiện lỗi task, tránh trường hợp test báo thành công khi một task ném exception.

Để ownership **thật sự** loại race, phải thỏa:
- Không có một phương thức ngoài owner hoặc một tham chiếu mutable bị rò rỉ cho bên khác để sửa state.
- Mọi cập nhật và lần đọc cần snapshot nhất quán đều đi qua owner hoặc qua immutable snapshot publish an toàn.
- Chuyển quyền sở hữu một buffer phải có giao thức rõ: bên gửi **không còn sửa buffer** sau khi bàn giao.
- Command queue cần quản lý capacity/backpressure; một owner xử lý chậm có thể làm hàng đợi tăng vô hạn nếu producer liên tục gửi.
- Không block owner bằng cách chờ `Future.get()` của một command khác chỉ **chính owner đó** mới có thể thực thi: đây là mẫu tự deadlock.

**Phù hợp:** trạng thái session riêng, actor-like component, bộ tổng hợp event, processing theo một key, logic nhiều trường có thể tuần tự hóa.

**Hạn chế:** owner có thể thành bottleneck; một command I/O rất chậm giữ các command sau đợi. Nếu chia trạng thái thành nhiều owner/partition, bất biến đi qua nhiều partition sẽ cần giao thức phối hợp bổ sung.

### 3.3. ThreadLocal không tự tạo ownership theo task

`ThreadLocal` cho mỗi Java thread một giá trị riêng, nhưng thread pool có thể tái sử dụng worker giữa nhiều task. Nếu giữ dữ liệu request trong ThreadLocal rồi quên `remove()` trong `finally`, task sau có thể nhìn thấy dữ liệu cũ. Hơn nữa một công việc có thể chuyển qua nhiều thread. Chỉ dùng ThreadLocal cho trạng thái đúng nghĩa gắn với thread, không đồng nhất nó với ownership của nghiệp vụ.

## 4. Chiến lược 2 — Locking

### 4.1. Bảo vệ toàn bộ invariant bằng cùng monitor

Khi nhiều thread phải trực tiếp đọc/ghi state, có thể bảo vệ critical section bằng `synchronized`:

~~~java
private final Object lock = new Object();
private int count;

void increment() {
    synchronized (lock) {
        count++;
    }
}

int currentCount() {
    synchronized (lock) {
        return count;
    }
}
~~~

Mutual exclusion đảm bảo một thread ở trong critical section tại một thời điểm trên monitor này. Unlock rồi lock cùng monitor còn tạo happens-before giúp đọc thấy dữ liệu đúng theo quy tắc bộ nhớ.

**Khóa cả đường đọc có liên quan.** Nếu writer dùng synchronized nhưng reader đọc một mutable field trực tiếp ngoài lock, reader có thể thiếu visibility hoặc thấy trạng thái giữa nhiều cập nhật. Một getter có khóa khác với setter cũng không tự giúp.

### 4.2. Check-then-act phải cùng một vùng khóa

Sai:

~~~java
if (account.getBalance() >= amount) {
    account.setBalance(account.getBalance() - amount);
}
~~~

Dù `getBalance()` và `setBalance()` riêng lẻ đều synchronized, sau bước kiểm tra có thể có một thread khác đổi số dư. Đúng hơn là một nghiệp vụ `withdrawIfEnough(amount)` kiểm tra và trừ dưới **cùng một lock**.

### 4.3. Ví dụ Java 17: invariant hai trường

Tạo file **`LockedInventoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LockedInventoryDemo {
    private static final class Inventory {
        private int available = 500;
        private int sold;

        synchronized boolean sellOne() {
            if (available == 0) {
                return false;
            }
            available--;
            sold++;
            return true;
        }

        synchronized Snapshot snapshot() {
            return new Snapshot(available, sold);
        }
    }

    private record Snapshot(int available, int sold) {}

    public static void main(String[] args) throws Exception {
        Inventory inventory = new Inventory();
        ExecutorService pool = Executors.newFixedThreadPool(10);

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int worker = 0; worker < 10; worker++) {
                futures.add(pool.submit(() -> {
                    int successes = 0;
                    for (int i = 0; i < 100; i++) {
                        if (inventory.sellOne()) {
                            successes++;
                        }
                    }
                    return successes;
                }));
            }

            int successes = 0;
            for (Future<Integer> future : futures) {
                successes += future.get();
            }

            Snapshot s = inventory.snapshot();
            System.out.printf(
                    "available=%d sold=%d successes=%d invariant=%b%n",
                    s.available(), s.sold(), successes,
                    s.available() >= 0 && s.available() + s.sold() == 500);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LockedInventoryDemo.java
java LockedInventoryDemo
~~~

Stdout khi 10 task hoàn tất không có lỗi:

~~~text
available=0 sold=500 successes=500 invariant=true
~~~

**Vì sao đúng?** Mỗi lần `sellOne()` kiểm tra và thay đổi cả `available`/`sold` trong **một critical section**. Sau 500 lần bán thành công, tồn kho bằng 0; 500 nỗ lực còn lại trả `false`. `snapshot()` cũng giữ cùng monitor, nên người đọc thấy một phiên bản cùng lúc của hai trường. Đặt `synchronized` riêng trên mỗi phép đọc hoặc sửa một field sẽ không tương đương.

### 4.4. ReentrantLock và vấn đề liveness

`ReentrantLock` cung cấp thao tác có timeout, lock có thể bị interrupt và `Condition` để chờ predicate; hình thức điển hình là:

~~~java
lock.lock();
try {
    // Kiểm tra và cập nhật đầy đủ invariant.
} finally {
    lock.unlock();
}
~~~

Đây là đoạn minh họa trong một method có `lock` kiểu `ReentrantLock` đã khởi tạo. Không để exception làm bỏ quên `unlock()`. Khi cần giới hạn thời gian đợi lock, dùng `tryLock(timeout, unit)` và **xử lý trường hợp không lấy được lock**. `ReentrantLock` không được mặc định là nhanh hơn `synchronized`: hãy đo contention và chọn theo semantics cần thiết.

Những rủi ro của locking:
- **Deadlock:** Thread A giữ lock X, đợi Y; Thread B giữ Y, đợi X. Quy định **thứ tự lấy lock toàn cục** hoặc dùng một lock chung cho invariant có liên hệ.
- **Contention:** critical section quá dài khiến nhiều thread phải đợi; p99 latency có thể tăng.
- **Giữ lock khi gọi I/O chậm:** cả các thread khác cùng cần lock bị kẹt, dù CPU rảnh.
- **Đọc ngoài lock:** một bên không đi qua cùng giao thức sẽ phá bằng chứng correctness.
- **Callback trong lock:** method bên ngoài có thể tự gọi ngược hoặc đợi tài nguyên ngoài ý muốn; giảm phạm vi lock khi có thể nhưng vẫn phải giữ toàn bộ invariant nguyên tử.

Đặc biệt, `Thread.sleep()` trong khối `synchronized` **không tự nhả monitor**; để chờ điều kiện nên dùng `Object.wait()`/`Condition.await()` đúng hợp đồng, kiểm tra predicate bằng `while` sau khi được đánh thức.

## 5. Chiến lược 3 — Atomic operations

Các lớp `java.util.concurrent.atomic` như `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, `AtomicReference` hỗ trợ thao tác nguyên tử lên **một vị trí trạng thái**. Ví dụ:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

counter.incrementAndGet();      // Một lần tăng nguyên tử.
int snapshot = counter.get();   // Một lần đọc theo atomic semantics.
~~~

Không tương đương:

~~~java
counter.set(counter.get() + 1); // Hai thao tác riêng, vẫn có lost update.
~~~

Một object Atomic không khiến **chuỗi gọi nhiều phương thức** tự trở thành một transaction.

### 5.1. Ví dụ atomic cập nhật có điều kiện

Tạo file **`AtomicInventoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicInventoryDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger available = new AtomicInteger(500);
        ExecutorService pool = Executors.newFixedThreadPool(10);

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int worker = 0; worker < 10; worker++) {
                futures.add(pool.submit(() -> {
                    int successes = 0;
                    for (int i = 0; i < 100; i++) {
                        int previous = available.getAndUpdate(
                                current -> current > 0 ? current - 1 : current);
                        if (previous > 0) {
                            successes++;
                        }
                    }
                    return successes;
                }));
            }

            int sold = 0;
            for (Future<Integer> future : futures) {
                sold += future.get();
            }

            System.out.printf(
                    "available=%d sold=%d invariant=%b%n",
                    available.get(), sold, available.get() + sold == 500);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac AtomicInventoryDemo.java
java AtomicInventoryDemo
~~~

Stdout:

~~~text
available=0 sold=500 invariant=true
~~~

`getAndUpdate` trả **giá trị trước cập nhật**; mỗi phép bán thành công chỉ khi giá trị đó lớn hơn 0. Không bao giờ có một cập nhật đi từ 0 xuống -1. Hàm lambda cập nhật phải không có **side effect**: thư viện có thể gọi lại hàm khi compare-and-set thất bại do contention. Nếu trong lambda gửi hóa đơn, cập nhật database hay tăng một counter khác, những việc ấy có thể xảy ra nhiều hơn số lần cập nhật được chấp nhận.

Ở ví dụ này, `sold` được tính **sau khi mọi `Future.get()` hoàn tất**. Vì vậy kết quả cuối đúng, nhưng trong lúc các task vẫn đang xử lý, `available` và một counter `sold` riêng biệt **không nhất thiết tạo snapshot nguyên tử**.

### 5.2. Compare-and-set (CAS)

CAS kiểm tra “trạng thái hiện tại vẫn đúng bằng giá trị tôi vừa đọc chứ?” rồi cập nhật nguyên tử nếu đúng:

~~~text
old = đọc state
next = tính state mới từ old
CAS(old, next)
    thành công -> thao tác có hiệu lực
    thất bại  -> thread khác đã thay đổi state, đọc/tính lại
~~~

Ví dụ phương thức độc lập có thể đặt vào một class:

~~~java
static boolean takeOne(
        java.util.concurrent.atomic.AtomicInteger remaining) {
    while (true) {
        int current = remaining.get();
        if (current <= 0) {
            return false;
        }
        if (remaining.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
~~~

CAS bảo đảm giá trị bị giảm một lần nếu còn dương tại thời điểm thành công. Khi nhiều thread cạnh tranh, có thể phải retry nhiều lần; **lock-free không đồng nghĩa wait-free hoặc không bao giờ tốn CPU**.

### 5.3. Hai atomic riêng không bảo vệ một invariant xuyên hai trường

Sai khi cần snapshot nhất quán:

~~~java
AtomicInteger available = new AtomicInteger(500);
AtomicInteger sold = new AtomicInteger(0);

available.decrementAndGet(); // Atomic riêng.
sold.incrementAndGet();      // Atomic riêng.
~~~

Ở giữa hai câu lệnh, reader có thể thấy `available + sold == 499`. Nếu yêu cầu là “mọi observer phải thấy invariant luôn đúng”, lựa chọn phù hợp là một **lock** bao cả cập nhật và đọc, một **owner** quản lý mọi trường, hoặc gộp trường vào một **immutable snapshot** trong `AtomicReference`.

`LongAdder` hữu ích cho counter đo lường có contention cao, nhưng `sum()` khi đang cập nhật đồng thời **không phải snapshot nguyên tử**; nó không phù hợp trực tiếp với số dư hay invariant cần exact observation. `ConcurrentHashMap.compute` hỗ trợ thao tác cập nhật theo từng key; không tự bảo đảm transaction xuyên nhiều key.

## 6. Chiến lược 4 — Immutable state và atomic publication

### 6.1. “Immutable” có nghĩa gì?

Một object immutable thực sự không có trạng thái quan sát được bị thay đổi sau khi xây dựng. Java 17 hỗ trợ `record` để diễn đạt value object:

~~~java
record Inventory(int available, int sold) {}
~~~

Với hai trường `int`, mỗi instance là một snapshot không thể thay đổi. Đọc hai field từ **cùng instance** giúp thấy một phiên bản nhất quán mà không phải khóa chính instance đó.

Tuy nhiên:
- Record tạo trường final, **không tự deep-immutable**. `record Data(int[] values) {}` vẫn chứa mảng có thể bị sửa.
- `final List<Person>` không khiến từng `Person` mutable bên trong immutable.
- Bản thân immutable object không ngăn **hai writer công bố hai phiên bản mới cạnh tranh nhau**, làm mất cập nhật.
- Cần **safe publication** cho reference (ví dụ `volatile`, `AtomicReference`, synchronized, queue/Future có memory consistency), và nếu cần read-modify-write của nhiều writer thì dùng CAS/lock/owner.

### 6.2. Ví dụ Java 17: AtomicReference cập nhật snapshot chứa hai trường

Tạo tệp **`ImmutableSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableSnapshotDemo {
    private record Inventory(int available, int sold) {}

    public static void main(String[] args) throws Exception {
        AtomicReference<Inventory> state =
                new AtomicReference<>(new Inventory(3, 0));
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                futures.add(pool.submit(() ->
                        state.updateAndGet(old ->
                                old.available() > 0
                                        ? new Inventory(
                                                old.available() - 1,
                                                old.sold() + 1)
                                        : old)));
            }

            for (Future<?> future : futures) {
                future.get();
            }

            Inventory snapshot = state.get();
            System.out.printf(
                    "available=%d sold=%d invariant=%b%n",
                    snapshot.available(), snapshot.sold(),
                    snapshot.available() >= 0
                            && snapshot.available() + snapshot.sold() == 3);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
~~~

Stdout:

~~~text
available=0 sold=3 invariant=true
~~~

Một lần `updateAndGet` có thể retry phép tính snapshot nhưng chỉ publish một kết quả theo semantics atomic của reference. Tám yêu cầu bán tranh chấp trên ba sản phẩm; ba yêu cầu đầu tiên được chấp nhận theo một thứ tự nào đó, năm yêu cầu còn lại không thay đổi state. Cặp `available/sold` luôn được tạo **cùng nhau** trong một instance.

**Quy tắc đọc snapshot:**

~~~java
Inventory view = state.get();
int available = view.available();
int sold = view.sold();
~~~

Đây là đoạn minh họa bên trong phạm vi nhìn thấy class `Inventory` và biến `state`. Không nên gọi `state.get()` riêng lẻ để lấy từng trường nếu cần phiên bản chung:

~~~java
int available = state.get().available();
int sold = state.get().sold(); // Có thể lấy một phiên bản mới hơn!
~~~

Khi writer cập nhật giữa hai lần `get()`, reader có thể ghép giá trị từ hai snapshot khác nhau, tạo ra invariant “sai” dù **mỗi snapshot riêng** luôn đúng.

### 6.3. Immutable + volatile, khi nào đủ?

Ví dụ field chỉ dùng để publish cấu hình mới sau khi đã xây xong:

~~~java
private volatile Config current = new Config("v1", 5);

record Config(String name, int limit) {}

void publish(Config next) {
    current = next;
}

Config snapshot() {
    return current;
}
~~~

Đây là đoạn **thành viên class**, không phải tệp chạy độc lập; trong Java, khi viết thành class thực tế hãy bố trí record và field ở vị trí hợp lệ. `volatile` đảm bảo visibility/publication của tham chiếu, và mỗi reader lấy một snapshot immutable. Nếu có **hai writer cùng đọc `current`, tính phiên bản mới dựa trên phiên bản cũ rồi gán lại**, thao tác read-modify-write vẫn có thể lost update. Dùng `AtomicReference.updateAndGet` hoặc lock cho trường hợp đó.

### 6.4. Defensive copy

Một record chứa mutable list hoặc array không tự immutable sâu. Nếu chỉ chứa `String` (immutable), có thể tạo bản sao cấu trúc:

~~~java
import java.util.List;

public record Names(List<String> values) {
    public Names {
        values = List.copyOf(values);
    }
}
~~~

Đây là một **record độc lập** lưu trong file `Names.java` nếu cần compile; `List.copyOf` tạo list không hỗ trợ sửa cấu trúc và tách khỏi việc sửa list đầu vào. Nó **không tự copy sâu** các phần tử mutable trong list. Cũng không thể dựa vào `Collections.unmodifiableList(original)` để tách khỏi nguồn dữ liệu vì wrapper chỉ ngăn sửa qua wrapper; nếu `original` vẫn bị sửa ở nơi khác thì view thay đổi.

## 7. So sánh lựa chọn

| Khía cạnh | Ownership | Locking | Atomic | Immutable snapshot |
| --- | --- | --- | --- | --- |
| Nguyên tắc | Một chủ sở hữu cập nhật | Bảo vệ critical section | CAS/thao tác nguyên tử | Thay giá trị mới, không sửa bản cũ |
| Phù hợp | Command queue, actor-like, state theo partition | Nhiều trường, logic check-then-act | Counter, flag, state gói trong một vị trí | Read-mostly, cấu hình, bộ state liên quan |
| Writer đồng thời | Đi qua owner tuần tự | Cạnh tranh cùng lock | Retry CAS khi cần | Cần atomic reference/lock/owner để thay |
| Reader nhất quán | Đọc qua owner/snapshot | Đọc qua cùng lock | `get()` trên atomic value | Một lần lấy tham chiếu snapshot |
| Rủi ro | Backlog, owner bottleneck | Contention, deadlock, giữ lock quá lâu | Retry nhiều, update function side effect | Allocation, mutable nested state, publish sai |
| Câu hỏi cần hỏi | Có đường bypass owner? | Tất cả đường truy cập có dùng cùng lock? | Invariant có nằm trong một giá trị? | Snapshot có immutable thật và publish đúng? |

Phương án có thể **kết hợp**: một owner quản lý mutable state và trả snapshot immutable; `AtomicReference` tham chiếu tới immutable record; lock bảo vệ việc xây và công bố cấu hình phức tạp. Chọn theo phạm vi invariant và cách đọc/ghi, không chọn theo khẩu hiệu “lock-free luôn nhanh”.

## 8. Từ bài toán đến thiết kế

### Trường hợp A — metric counter độc lập

Nếu chỉ cần tăng một biến nguyên tử, `AtomicLong.incrementAndGet()` đơn giản. Nếu workload ghi cực nhiều và cho phép số liệu snapshot xấp xỉ, `LongAdder` đáng đo thử. **Không** dùng hai lần `get/set` rồi hi vọng atomic.

### Trường hợp B — tồn kho không âm

Check-then-decrement là **một thao tác nghiệp vụ**. Dùng synchronized method, CAS loop trên AtomicInteger, hoặc owner xử lý message. Nếu đồng thời cập nhật `available` và `sold` và reader phải thấy đúng tổng ở mọi lúc, dùng lock chung hoặc immutable snapshot + AtomicReference.

### Trường hợp C — cấu hình có nhiều field

Tạo một record immutable chứa tất cả giá trị liên quan; cập nhật bằng cách thay toàn bộ reference `volatile` khi chỉ publish snapshot có sẵn, hoặc CAS/owner nếu có nhiều writer tính phiên bản mới từ phiên bản cũ. Reader lấy **một lần tham chiếu** rồi sử dụng thống nhất.

### Trường hợp D — shared mutable collection

Đừng cho rằng `Collections.synchronizedList` biến mọi vòng lặp thành atomic. Theo hợp đồng của wrapper, việc duyệt thường cần khóa đúng trên chính list:

~~~java
synchronized (list) {
    for (String item : list) {
        System.out.println(item);
    }
}
~~~

Đây là đoạn minh họa với `list` là synchronized list đã được tạo. Với read-mostly, có thể cân nhắc `CopyOnWriteArrayList`; với map cập nhật riêng từng key, cân nhắc `ConcurrentHashMap.compute`. Nếu invariant đi qua **nhiều phần tử/key**, các primitive riêng lẻ không đủ để gọi toàn bộ chuỗi là atomic.

### Trường hợp E — chuyển state giữa thread

Cho producer bàn giao buffer qua queue. Nếu producer tiếp tục sửa buffer sau khi `put()`, quyền sở hữu chưa thực sự độc quyền dù queue có memory consistency. Cần defensive copy, immutable value, hoặc giao thức rõ khi nào producer được phép sửa tiếp.

## 9. Những cách “sửa” dễ làm race còn nguyên

1. **`volatile` cho counter rồi giữ `counter++`.** Visibility tốt hơn, read-modify-write vẫn không atomic.
2. **Khóa bằng `synchronized(new Object())`.** Mỗi lần lại có monitor riêng; thread khác không bị chặn. Dùng một lock field ổn định được chia sẻ.
3. **Chỉ synchronized getter/setter.** `set(get()+1)` vẫn có khoảng trống cho thread khác chen vào. Gói cả nghiệp vụ thành một method atomic.
4. **Writer dùng lock, reader không dùng.** Reader có thể thấy phiên bản không nhất quán hoặc thiếu visibility; dùng cùng lock hoặc immutable snapshot publish an toàn.
5. **Mỗi field một lock khác nhau cho invariant tổng.** Từng field đúng nhưng reader có thể lấy một phần phiên bản cũ, một phần phiên bản mới.
6. **`AtomicInteger` nhưng gọi `set(get()+1)`.** Vẫn là hai thao tác riêng; dùng `incrementAndGet` hoặc CAS/update.
7. **Hai AtomicInteger rồi coi cả cặp là transaction.** Giữa hai lệnh cập nhật vẫn có trạng thái trung gian; dùng một snapshot nguyên tử.
8. **Callback CAS có side effect.** CAS có thể retry và gọi lại function; hàm tính state phải pure, không tự thanh toán/gửi email.
9. **Record chứa mảng mutable rồi gọi là immutable.** `final` chỉ giữ tham chiếu, không đóng băng phần tử; cần defensive copy hoặc đổi representation.
10. **`volatile` reference nhưng hai writer read-then-set.** Mất cập nhật vẫn có thể xảy ra; dùng CAS/lock/owner.
11. **Dùng `Thread.sleep` để đợi “thread kia cập nhật xong”.** Sleep không tạo happens-before; dùng `join`, latch, future hoặc primitive đúng mục đích.
12. **ThreadLocal gắn dữ liệu request trong pool không cleanup.** Worker tái sử dụng có thể làm rò dữ liệu sang task khác; gọi `remove()` trong `finally`.
13. **Để callback/network I/O chậm bên trong lock.** Giữ các thread khác chờ dài, làm tăng latency và rủi ro deadlock.
14. **Thấy một lượt stress test đúng rồi kết luận không có race.** Timing khác có thể lộ lỗi; cần giải thích invariant và quan hệ đồng bộ, kết hợp test để phát hiện regression.

### Một ví dụ deadlock cần tránh

~~~text
Thread A: giữ lock X rồi đợi lock Y
Thread B: giữ lock Y rồi đợi lock X

=> Không thread nào lấy được lock còn thiếu.
~~~

Để chuyển tiền giữa hai object có lock riêng, cần thứ tự khóa thống nhất (ví dụ theo ID duy nhất và quy tắc tie-break) hoặc một lock chung bảo vệ transaction nếu kiến trúc cho phép. Nếu state nằm trên nhiều process/host, primitive Java thread-level **không đủ** cho atomicity phân tán.

## 10. Cách kiểm chứng giải pháp

1. **Ghi rõ invariant bằng điều kiện quan sát được**, ví dụ `available >= 0` và `available + sold == initial`.
2. **Liệt kê mọi đường đọc/ghi**: caller, worker, callback, getter, map access, event handler và cleanup. Một đường bypass giao thức có thể phá toàn bộ.
3. **Xác định đơn vị thao tác nguyên tử**: command của owner, critical section, CAS hoặc lần thay AtomicReference thành công. Nếu một thao tác nhiều bước cần atomic, phải bao đúng cả chuỗi.
4. **Kiểm tra safe publication**: object được tạo xong trước khi thread khác đọc chưa? Có `volatile`/lock/queue/Future hoặc quan hệ happens-before phù hợp không?
5. **Thiết kế test tái hiện interleaving**, ví dụ CountDownLatch ở demo đầu thay vì sleep chờ may mắn. Đặt nhiều thread tranh chấp và kiểm tra invariant.
6. **Đọc kết quả task bằng `Future.get()`** để phát hiện exception. Chỉ đợi executor shutdown mà không kiểm tra Future có thể che lỗi task.
7. **Kiểm tra snapshot trong lúc cập nhật**, không chỉ trạng thái sau cùng. Một hệ thống có thể kết thúc với tổng đúng nhưng reader giữa chừng thấy tổng sai.
8. **Thử cancellation/failure**: khóa có nhả trong `finally` không? Owner xử lý queue backlog thế nào? CAS lambda có side effect không? Immutable graph có mutable data bị rò không?
9. **Đo performance sau khi đã đúng**: throughput thành công, p95/p99 latency, lock contention, queue depth, CAS retries, CPU/GC. Thực hiện warm-up, lặp nhiều lượt và giữ workload tương đương. Benchmark không thay thế chứng minh correctness.

Các công cụ như thread dump, Java Flight Recorder (JFR), profiler và metrics giúp quan sát contention hay blocked thread. Không có công cụ chạy thử nào bảo đảm tìm được mọi interleaving sai; dựa trên Java Memory Model và invariant mới là nền tảng.

## 11. Câu hỏi luyện tập

1. Hai thread cùng chạy `volatile int x; x++;`. Có còn race không? **Có**, read-modify-write chưa nguyên tử.
2. Vì sao `synchronized getBalance` và `synchronized setBalance` vẫn không đủ cho `if(getBalance()>=n) setBalance(getBalance()-n)`? **Lock bị nhả giữa các lời gọi, invariant không được bảo vệ trọn vẹn.**
3. Một owner chạy trên `newSingleThreadExecutor` có chắc Java thread ID không đổi suốt đời executor? **Không.** Executor đảm bảo tuần tự, có thể thay worker sau lỗi.
4. Tại sao callback trong `AtomicReference.updateAndGet` phải tránh side effect? **Có thể được chạy lại khi CAS cạnh tranh.**
5. `AtomicInteger available` và `AtomicInteger sold` riêng lẻ có đảm bảo `available + sold == 500` luôn đúng khi reader đọc đồng thời? **Không.**
6. Với immutable record trong `AtomicReference`, vì sao cần `Inventory s = state.get()` rồi đọc cả hai trường từ `s`? **Hai lần `get()` riêng có thể lấy hai phiên bản khác nhau.**
7. Record `Data(int[] numbers)` có deep immutable không? **Không**, array vẫn mutable.
8. Nếu state do một owner sửa, tại sao vẫn phải giới hạn queue command? **Producer có thể gửi nhanh hơn owner xử lý, gây backlog và OOM.**
9. Tại sao `Thread.sleep(100)` không sửa race? **Không tạo quan hệ happens-before hay mutual exclusion.**
10. Hai lock cần lấy cùng lúc phải làm gì để tránh deadlock? **Quy định thứ tự khóa nhất quán hoặc đổi kiến trúc khóa phù hợp.**
11. Khi nào `LongAdder` phù hợp hơn `AtomicLong`? **Với bộ đếm thống kê cập nhật rất nhiều, có contention và không yêu cầu tổng snapshot nguyên tử tại mọi thời điểm.**
12. Nếu một cách sửa làm kết quả đúng nhưng p99 latency tăng mạnh, cần đo gì? **Critical section, lock contention, queue depth, CPU, GC, offered load và throughput thành công.**

## Ghi nhớ

Bắt đầu từ **trạng thái chia sẻ và invariant nghiệp vụ**. **Ownership** loại bỏ writer cạnh tranh; **locking** bao trọn nghiệp vụ khi nhiều thread cùng cần access; **atomic** giải quyết cập nhật trên một biến hoặc một snapshot CAS; **immutable state** giúp các reader nhìn thấy phiên bản không thay đổi và kết hợp tốt với safe publication. Cần đảm bảo **atomicity, visibility, ordering, liveness** theo đúng phạm vi. Một từ khóa `volatile`, `synchronized` hay `AtomicInteger` dùng sai chỗ có thể khiến chương trình trông an toàn trong vài lần chạy mà vẫn chứa race.

## Tài liệu tham khảo

- [Java Language Specification 17, Chapter 17: Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, happens-before, data race.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic update và CAS.
- [Java SE 17 — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cập nhật snapshot.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): thực thi task và memory consistency.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic update theo key.
- [Java SE 17 — LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter với contention.
