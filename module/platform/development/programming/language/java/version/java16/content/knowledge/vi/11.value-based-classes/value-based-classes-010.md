# Kiểm thử tranh chấp luồng sau khi chuyển sang khóa đồng bộ riêng

Khi thay một wrapper hoặc value-based instance bằng khóa riêng như **private final Object lock = new Object()**, cần xác minh rằng tất cả luồng vẫn phối hợp đúng trên cùng monitor và trạng thái không bị cập nhật sai. Một phép thử chỉ gọi phương thức tuần tự không thể phát hiện race condition hoặc lỗi mất cập nhật khi nhiều luồng cùng chạy.

Kiểm thử đồng thời nên tập trung vào kết quả và invariant của dữ liệu, tạo điểm bắt đầu chung cho các worker, chờ hoàn tất bằng **Future** và đặt timeout để phát hiện tác vụ bị treo. Không dựa vào **Thread.sleep()** hoặc thời gian chạy để kết luận khóa đúng hay sai. Bài học này trình bày cách xây dựng các phép thử như vậy sau khi chuyển sang khóa đồng bộ riêng trong Java hiện đại.

## 1. Cần xác minh điều gì sau khi thay khóa?

Giả sử trước đây code dùng một wrapper làm monitor:

~~~java
Integer lock = Integer.valueOf(1);

synchronized (lock) {
    count++;
}
~~~

Sau khi sửa, khóa được sở hữu riêng bởi lớp:

~~~java
private final Object lock = new Object();

public void increment() {
    synchronized (lock) {
        count++;
    }
}
~~~

Việc thay biểu thức khóa chỉ đúng khi mọi thao tác cần phối hợp đều dùng cùng khóa mới. Khi kiểm thử, hãy xác minh các điểm sau:

1. **Không mất cập nhật:** nhiều luồng cùng tăng hoặc giảm dữ liệu, kết quả cuối phải đúng.
2. **Invariant luôn được giữ:** các field liên quan phải thay đổi như một thao tác nguyên tử.
3. **Đọc được dữ liệu đã ghi:** các phương thức đọc sử dụng cùng giao thức đồng bộ với phương thức ghi.
4. **Tác vụ hoàn tất:** không có luồng bị kẹt do khóa hoặc chờ vô hạn.
5. **Phạm vi khóa đúng:** các instance độc lập không vô tình phụ thuộc vào cùng một khóa toàn cục; dữ liệu static dùng chung phải có khóa chung.
6. **Không còn đường truy cập dùng khóa cũ:** tất cả caller, callback và helper đều tuân theo giao thức mới.

Một bài kiểm thử đồng thời tốt phải kiểm tra hành vi quan sát được qua API của đối tượng, không cần truy cập trực tiếp field khóa private.

## 2. Vì sao không nên dùng Thread.sleep() để tạo tranh chấp?

Cách viết sau không tạo ra một phép thử đồng thời đáng tin cậy:

~~~java
Thread first = new Thread(counter::increment);
Thread second = new Thread(counter::increment);

first.start();
Thread.sleep(10);
second.start();
~~~

**Thread.sleep()** yêu cầu luồng hiện tại tạm ngừng trong khoảng thời gian chỉ định, nhưng không bảo đảm thời điểm luồng tiếp tục chạy hoặc luồng nào được scheduler chọn tiếp theo. Nó không bảo đảm luồng thứ nhất đã vào vùng tới hạn, cũng không bảo đảm luồng thứ hai sẽ chạy đúng thời điểm mong muốn. Kết quả phụ thuộc vào scheduler, tải máy và môi trường CI.

Thay vào đó, dùng các công cụ phối hợp trong **java.util.concurrent**:

- **CountDownLatch** để báo rằng worker đã sẵn sàng và cùng chờ tín hiệu bắt đầu.
- **ExecutorService** để quản lý nhóm worker.
- **Future.get()** để chờ kết quả và nhận exception phát sinh trong worker.
- Timeout để phát hiện task bị treo hoặc không hoàn tất.
- **AtomicInteger** khi cần đếm kết quả thành công từ nhiều worker trong chính bài kiểm thử.

Các API này có sẵn từ lâu và vẫn phù hợp trong Java hiện đại.

## 3. Tạo điểm bắt đầu chung cho nhiều worker

Một start gate bằng **CountDownLatch** giúp các worker cùng chờ trước khi bắt đầu thao tác. Khi tất cả worker đã sẵn sàng, luồng kiểm thử mở gate một lần.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

int workerCount = 8;

CountDownLatch ready = new CountDownLatch(workerCount);
CountDownLatch start = new CountDownLatch(1);

// Mỗi worker:
ready.countDown();

if (!start.await(30, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Không nhận được tín hiệu bắt đầu");
}

// Luồng điều phối:
if (!ready.await(30, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Worker chưa sẵn sàng");
}
start.countDown();
~~~

**ready** có số đếm bằng số worker. Mỗi worker giảm số đếm khi đã tới vị trí chờ. Luồng điều phối chỉ mở **start** sau khi tất cả worker đã sẵn sàng.

Cách này làm các thao tác bắt đầu gần nhau hơn và tăng khả năng tạo tranh chấp trên cùng trạng thái. Nó không ép scheduler chạy tất cả luồng đồng thời chính xác tại cùng một thời điểm, nhưng tạo điều kiện kiểm thử nhất quán hơn so với dùng sleep.

## 4. Kiểm thử không mất cập nhật với private lock

Một lỗi phổ biến khi đồng bộ sai là lost update: nhiều luồng cùng đọc một giá trị, tính toán rồi ghi đè kết quả của nhau. Phép tăng **count++** không phải thao tác nguyên tử nếu không có đồng bộ phù hợp.

Lớp cần kiểm thử:

~~~java
final class Counter {
    private final Object lock = new Object();
    private long value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public long value() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Mỗi instance sở hữu một monitor riêng. Cả thao tác tăng và đọc đều dùng cùng khóa, vì vậy việc đọc không đi vòng qua giao thức đồng bộ.

Đặt lớp **Counter** ở phần trên trong cùng package (có thể để ở file **Counter.java**) và đặt harness dưới đây trong file **CounterConcurrencyCheck.java**. Chương trình kiểm thử dùng **ExecutorService**, **CountDownLatch** và **Future**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CounterConcurrencyCheck {
    private static final int WORKERS = 8;
    private static final int INCREMENTS_PER_WORKER = 50_000;

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter();

        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < WORKERS; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();

                    if (!start.await(30, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Start gate timeout");
                    }

                    for (int j = 0; j < INCREMENTS_PER_WORKER; j++) {
                        counter.increment();
                    }
                    return null;
                }));
            }

            if (!ready.await(30, TimeUnit.SECONDS)) {
                throw new TimeoutException("Workers are not ready");
            }

            start.countDown();

            for (Future<?> future : futures) {
                future.get(1, TimeUnit.MINUTES);
            }

            long expected = (long) WORKERS * INCREMENTS_PER_WORKER;
            if (counter.value() != expected) {
                throw new AssertionError(
                    "Expected " + expected + ", got " + counter.value()
                );
            }

            System.out.println("PASS: " + counter.value());
        } finally {
            start.countDown();
            pool.shutdownNow();
            pool.awaitTermination(30, TimeUnit.SECONDS);
        }
    }
}
~~~

Với tám worker, mỗi worker tăng 50.000 lần, kết quả mong đợi là **400.000**. Nếu một số lần tăng bị mất do race condition, phép kiểm tra cuối sẽ thất bại.

Các điểm quan trọng trong phép thử:

- **ready** bảo đảm các worker đã tới start gate trước khi bắt đầu.
- **start.countDown()** mở gate cho tất cả worker.
- **Future.get()** chờ mỗi task và ném lỗi nếu task thất bại.
- Timeout giúp test kết thúc có kiểm soát khi một task bị treo.
- **finally** luôn mở gate và dừng executor, kể cả khi một assertion hoặc task phát sinh lỗi.

Trong test suite, có thể chuyển logic này thành một test method của framework đang dùng. Điều quan trọng là giữ cơ chế phối hợp và xác minh kết quả cuối, không phụ thuộc vào khoảng ngủ cố định.

## 5. Kiểm thử invariant giữa nhiều field

Một khóa có thể bảo vệ nhiều field cần thay đổi như một đơn vị. Ví dụ, kho hàng có số lượng còn khả dụng và số lượng đã đặt:

~~~java
public final class Inventory {
    private final Object lock = new Object();
    private int available;
    private int reserved;

    public Inventory(int initialStock) {
        if (initialStock < 0) {
            throw new IllegalArgumentException("initialStock must not be negative");
        }
        this.available = initialStock;
    }

    public boolean reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        synchronized (lock) {
            if (available < amount) {
                return false;
            }

            available -= amount;
            reserved += amount;
            return true;
        }
    }

    public int available() {
        synchronized (lock) {
            return available;
        }
    }

    public int reserved() {
        synchronized (lock) {
            return reserved;
        }
    }
}
~~~

Invariant cần duy trì là:

\[
available \geq 0
\]

và:

\[
available + reserved = initialStock
\]

Hai field phải được cập nhật bên trong cùng khối **synchronized (lock)**. Nếu cập nhật từng field bằng hai khóa riêng, một luồng khác có thể quan sát trạng thái trung gian hoặc hai thao tác có thể xen kẽ làm sai invariant.

Có thể kiểm thử với nhiều worker cùng cố gắng đặt hàng:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

int initialStock = 20_000;
Inventory inventory = new Inventory(initialStock);
AtomicInteger successfulReservations = new AtomicInteger();

runConcurrently(8, () -> {
    for (int i = 0; i < 10_000; i++) {
        if (inventory.reserve(1)) {
            successfulReservations.incrementAndGet();
        }
    }
});

if (successfulReservations.get() != initialStock) {
    throw new AssertionError("Số lượt đặt thành công không đúng");
}

if (inventory.available() != 0) {
    throw new AssertionError("Số lượng khả dụng phải bằng 0");
}

if (inventory.reserved() != initialStock) {
    throw new AssertionError("Số lượng đã đặt không đúng");
}

if (inventory.available() + inventory.reserved() != initialStock) {
    throw new AssertionError("Inventory invariant bị vi phạm");
}
~~~

Ví dụ sử dụng helper **runConcurrently()** được định nghĩa ở phần tiếp theo. Tám worker thực hiện tổng cộng 80.000 yêu cầu đặt một đơn vị, trong khi kho chỉ có 20.000 đơn vị. Chính xác 20.000 yêu cầu phải thành công; các yêu cầu còn lại phải nhận **false**. Sau khi tất cả task kết thúc, tổng số lượng khả dụng và đã đặt phải bằng lượng ban đầu.

**AtomicInteger** ở đây chỉ đếm số yêu cầu thành công trong phần kiểm thử. Trạng thái nghiệp vụ của **Inventory** vẫn được bảo vệ bằng một monitor chung.

## 6. Viết helper chạy nhiều worker có timeout

Để tránh lặp code thiết lập executor và start gate trong nhiều test, có thể tạo helper:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

@FunctionalInterface
interface ConcurrentTask {
    void run() throws Exception;
}

static void runConcurrently(int workerCount, ConcurrentTask task)
        throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(workerCount);
    CountDownLatch ready = new CountDownLatch(workerCount);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<?>> futures = new ArrayList<>();

    try {
        for (int i = 0; i < workerCount; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();

                if (!start.await(30, TimeUnit.SECONDS)) {
                    throw new TimeoutException("Start gate timeout");
                }

                task.run();
                return null;
            }));
        }

        if (!ready.await(30, TimeUnit.SECONDS)) {
            throw new TimeoutException("Workers are not ready");
        }

        start.countDown();

        for (Future<?> future : futures) {
            future.get(1, TimeUnit.MINUTES);
        }
    } finally {
        start.countDown();
        pool.shutdownNow();
        pool.awaitTermination(30, TimeUnit.SECONDS);
    }
}
~~~

Helper này có thể tái sử dụng cho các test có cùng số worker và cùng tác vụ. Trong test suite thực tế, có thể đưa timeout thành tham số hoặc dùng timeout của framework để phù hợp thời lượng CI.

Đặt **ConcurrentTask** và phương thức **runConcurrently()** bên trong lớp test hoặc lớp tiện ích kiểm thử. Tác vụ truyền vào được gọi đồng thời trên nhiều worker, vì vậy các biến mà lambda chia sẻ phải bất biến hoặc tự có cơ chế đồng bộ phù hợp.

Không nuốt **ExecutionException** từ **Future.get()**. Nếu code trong worker phát sinh lỗi, test phải thất bại để người phát triển nhìn thấy nguyên nhân. Không chỉ kiểm tra rằng thread đã kết thúc; cần kiểm tra cả kết quả và invariant sau khi hoàn tất.

## 7. Rà soát việc chuyển từ khóa cũ sang khóa riêng

Sau khi thay wrapper bằng khóa **private final Object**, có thể code vẫn còn một đường truy cập sử dụng monitor cũ. Ví dụ, phương thức cập nhật dùng **lock** mới nhưng một phương thức khác lại khai báo **synchronized** trên **this**:

~~~java
public class MixedLock {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public synchronized int value() {
        return value;
    }
}
~~~

Hai phương thức khóa hai object khác nhau: **increment()** khóa field **lock**, còn **value()** khóa **this**. Chúng không phối hợp qua cùng monitor. Cách sửa là dùng cùng **lock** trong cả hai phương thức.

Khi review thay đổi, hãy tìm:

- Các khối **synchronized** còn dùng wrapper, value-based instance, **this** hoặc object công khai.
- Các phương thức **synchronized** được thêm trước đây, vì chúng khóa **this**.
- Các lời gọi **wait()**, **notify()** và **notifyAll()** trên monitor cũ.
- Getter hoặc helper đọc field ngoài vùng đồng bộ.
- Callback, listener hoặc code bên ngoài giữ monitor trong thời gian dài.
- Các field cùng tạo invariant nhưng đang được bảo vệ bởi nhiều khóa không nhất quán.

Có thể bật cảnh báo identity của javac hiện đại:

~~~bash
javac -Xlint:identity -d out src/example/Main.java
~~~

Nhóm lint giúp phát hiện một số thao tác nhạy cảm với identity trên value-based class. Nó không thay thế việc rà soát các kiểu khóa được che dưới **Object** hoặc các giao thức đồng bộ giữa nhiều phương thức.

## 8. Phân biệt kiểm thử tính đúng đắn và đo hiệu năng

Một phép thử tranh chấp luồng nhằm xác minh kết quả và invariant. Nó không nên kết luận khóa nhanh hay chậm dựa trên một lần chạy.

Không viết assertion kiểu:

~~~java
// Không dùng thời gian chạy làm bằng chứng khóa đúng
// assertTrue(elapsedMillis < 100);
~~~

Thời gian chạy thay đổi theo CPU, hệ điều hành, tải CI, JIT compilation và lịch thực thi luồng. Một test có thể thất bại dù code đúng chỉ vì máy chạy chậm, hoặc thành công dù code có race condition chưa xuất hiện trong lần chạy đó.

Nếu cần đo hiệu năng, hãy dùng benchmark chuyên dụng như **JMH** với warmup, nhiều lần đo và cấu hình tải rõ ràng. Giữ benchmark tách khỏi test correctness.

Một số giới hạn cần nhớ:

- Một lần chạy thành công không chứng minh chương trình không có race condition.
- Tăng số worker và số vòng lặp giúp tăng áp lực tranh chấp nhưng không bảo đảm bao phủ mọi lịch thực thi.
- Timeout phát hiện task không hoàn tất trong giới hạn đã đặt; timeout không tự xác định nguyên nhân deadlock.
- Nếu cần kiểm tra các hành vi rất nhạy với Java Memory Model, cân nhắc công cụ stress test chuyên biệt và phân tích thread dump khi có hiện tượng treo.

Hãy kết hợp test xác định kết quả, test invariant, rà soát giao thức khóa và benchmark riêng khi có yêu cầu hiệu năng.

## 9. Quy trình kiểm thử sau khi chuyển sang khóa riêng

Có thể áp dụng quy trình sau trong một pull request:

1. Xác định trạng thái và invariant mà khóa cũ bảo vệ.
2. Thay bằng **private final Object** cho trạng thái instance hoặc **private static final Object** cho trạng thái static dùng chung.
3. Chuyển mọi thao tác đọc, ghi và phối hợp chờ sang cùng giao thức khóa.
4. Viết test nhiều worker với start gate bằng **CountDownLatch**.
5. Dùng **Future.get(timeout)** để chờ task và truyền lỗi từ worker về test.
6. Kiểm tra kết quả cuối, giới hạn dữ liệu và invariant giữa các field.
7. Lặp test với số worker và số lần thao tác phù hợp, tránh assertion theo thời gian chạy.
8. Rà soát các monitor cũ, thứ tự lấy nhiều khóa và các đường truy cập gián tiếp.
9. Chạy test trên JDK và cấu hình CI mà dự án hỗ trợ; nếu cần hiệu năng, tạo benchmark riêng.

## 10. Kết luận

Sau khi chuyển sang khóa đồng bộ riêng, cần kiểm tra rằng các luồng thực sự dùng cùng monitor để bảo vệ cùng trạng thái. **CountDownLatch** tạo điểm bắt đầu chung, **ExecutorService** quản lý worker, **Future.get()** chờ và truyền lỗi, còn assertion trên kết quả cuối xác minh không mất cập nhật và invariant được giữ.

Không dùng **Thread.sleep()** hoặc ngưỡng thời gian chạy để chứng minh tính đúng đắn. Kết hợp test nhiều worker, kiểm tra invariant, rà soát các đường truy cập còn dùng khóa cũ và benchmark riêng khi cần đánh giá hiệu năng. Cách kiểm thử này giúp xác nhận thay đổi khóa đã giữ được hành vi đồng bộ của ứng dụng trong môi trường nhiều luồng.

## Tài liệu tham khảo

- [CountDownLatch — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [ExecutorService — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html)
- [TimeUnit — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/TimeUnit.html)
- [AtomicInteger — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [JLS 27 — Synchronization (Section 17.1)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.1)
- [JLS 27 — Happens-before Order (Section 17.4.5)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.4.5)
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)

