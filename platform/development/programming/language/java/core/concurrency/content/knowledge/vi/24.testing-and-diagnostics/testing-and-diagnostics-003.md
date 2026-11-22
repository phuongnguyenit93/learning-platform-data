# Không dùng `Thread.sleep()` thay cho điều kiện đồng bộ trong test Java concurrency

## 1. Nguyên tắc: chờ sự kiện, không chờ một khoảng thời gian tùy ý

Một bài test concurrency thường phải trả lời các câu hỏi: worker đã bắt đầu chưa, đã đến điểm chờ chưa, hai thread đã cùng đọc trạng thái cũ chưa, công việc đã kết thúc hay chưa, và dữ liệu đã được chuyển giao đúng chưa. `Thread.sleep(100)` **không trả lời được câu hỏi nào trong số đó**. Nó chỉ tạm ngừng thread gọi trong khoảng thời gian được yêu cầu, tùy scheduler và hệ điều hành; khi thread chạy tiếp, worker có thể chưa được chạy, đang bị chặn, đã lỗi hoặc đã hoàn tất.

**Quy tắc thiết kế:** mô tả chính xác sự kiện cần quan sát bằng một primitive đồng bộ, chờ sự kiện ấy với timeout hữu hạn, kiểm tra kết quả, và dọn thread/executor trong `finally` nếu test thất bại.

Ví dụ cách dễ gây flaky:

~~~java
// Mảnh mã minh họa: state đã được khai báo ở nơi khác.
Thread worker = new Thread(() -> state.set(42));
worker.start();
Thread.sleep(100);                 // Không chứng minh worker đã xong.
if (state.get() != 42) {
    throw new AssertionError("Wrong value");
}
~~~

Dù máy mạnh và test pass liên tục, kết quả đó không chứng minh đã có giao thức đồng bộ đúng. Máy CI bận, giới hạn CPU, tranh chấp lock, GC hoặc thay đổi scheduler có thể khiến 100 ms trở nên quá ngắn. Tăng thành 1.000 ms chỉ làm test chậm hơn và thay đổi xác suất fail; không sửa nguyên nhân.

Nếu thật sự cần biết một `Thread` đã kết thúc, cách phù hợp là `join`:

~~~java
worker.start();
worker.join(2_000);
if (worker.isAlive()) {
    worker.interrupt();
    throw new AssertionError("Worker did not finish");
}
// Các hành động của worker đã kết thúc happen-before đoạn này.
~~~

Đây cũng là **mảnh minh họa**, với `worker` được tạo trước khi chạy. `join(2_000)` có thể trả về do hết hạn; cần kiểm tra `isAlive()`. `join` không tự chuyển exception trong worker về thread test; với tác vụ gửi vào executor, `Future.get()` thường thuận tiện hơn vì chuyển cả kết quả lẫn thất bại.

## 2. Bốn lý do khiến test dựa trên sleep thiếu tin cậy

**1. Không đồng bộ với lịch chạy:** lời gọi `start()` hoặc `executor.submit()` chỉ tạo/gửi công việc; chưa chứng minh thread đã bắt đầu chạy, đã vào critical section hoặc đã kết thúc. Khoảng sleep cố định không tạo ra quan hệ nguyên nhân giữa test và worker.

**2. Flakiness và lãng phí:** sleep ngắn tạo false failure trên máy chậm; sleep dài khiến test suite kéo dài không cần thiết. Nếu 500 test tuần tự ngủ 200 ms, có ít nhất khoảng 100 giây chờ, kể cả khi mọi task hoàn thành sau 1 ms.

**3. Không tạo quan hệ *happens-before*:** thời gian trôi qua không thay thế các quy tắc visibility và ordering của Java Memory Model. Một thread có thể cần `volatile`, lock, latch, queue hoặc completion signal theo đúng hợp đồng để thấy cập nhật từ thread khác. Dùng `volatile` cũng không khiến thao tác kép `counter++` trở thành nguyên tử.

**4. Có thể che bug và exception:** sleep làm thay đổi interleaving giữa các thread nên tình cờ làm race biến mất. Exception ném trong một thread riêng không mặc nhiên làm assertion trên thread test fail. `Future.get()` có thể chuyển lỗi qua `ExecutionException`; `Thread.sleep()` không có khả năng đó.

Cần phân biệt **flaky test** với bug concurrency thực sự: test dùng sleep có thể báo lỗi khi code đúng, hoặc pass khi code có lỗi. Cách sửa là tăng khả năng điều khiển và quan sát các sự kiện, không chỉ chạy lại test nhiều lần.

## 3. Chọn primitive đúng với điều kiện muốn chờ

| Điều kiện trong bài test | Cơ chế Java phù hợp | Điều phải lưu ý |
| --- | --- | --- |
| Một `Thread` đã kết thúc | `Thread.join(timeout)` | Kiểm tra `isAlive()` khi dùng timeout; exception cần chuyển riêng |
| Một tác vụ executor đã hoàn tất, lấy kết quả/lỗi | `Future.get(timeout, unit)` | Timeout không tự hủy task; cần cleanup |
| Worker đã tới checkpoint A | `CountDownLatch(1)`, `countDown()/await(timeout)` | Đặt `countDown` ở chính checkpoint A |
| Worker phải tạm dừng tại A đến khi test cho phép | Một `CountDownLatch` thứ hai làm “release gate” | Worker thực sự chờ gate; test kiểm soát thứ tự |
| N worker cùng tới mốc rồi mới tiếp tục | `CyclicBarrier` hoặc `Phaser` | Số bên tham gia phải được scheduling; xử lý timeout/interrupt |
| Producer chuyển item cho consumer | `BlockingQueue` + `poll(timeout)` | Chờ item thực tế, thay vì ngủ rồi đọc queue |
| Một trạng thái được bảo vệ bởi monitor/lock đổi giá trị | `wait/notifyAll`, `Condition.await/signalAll` | Luôn kiểm tra predicate trong vòng `while` |
| Tất cả tác vụ của một batch hoàn tất | `Future`, `invokeAll` hoặc latch đếm N | Định nghĩa timeout tổng, giữ exception và cancellation |

`CountDownLatch` là sự kiện một chiều, không reset. `CyclicBarrier` tái sử dụng được sau mỗi vòng thành công; `Phaser` hữu ích nếu có nhiều pha hoặc số bên tham gia thay đổi. Không thêm primitive phức tạp khi `Future.get` hoặc `join` đã mô tả chính xác điều muốn kiểm tra.

## 4. Ví dụ Java 17+: chờ worker đến cổng rồi mới giải phóng

Mục tiêu test là chứng minh **worker không cập nhật `state` trước khi cổng được mở** và **cập nhật thành 42 sau khi cổng mở**. Một latch báo rằng worker đã tới điểm kiểm tra; latch thứ hai giữ worker tại đó. Không có `sleep`.

Lưu chương trình độc lập thành `LatchTest.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchTest {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch reachedGate = new CountDownLatch(1);
        CountDownLatch releaseGate = new CountDownLatch(1);
        AtomicInteger state = new AtomicInteger(0);

        Future<?> task = executor.submit(() -> {
            reachedGate.countDown();
            try {
                releaseGate.await();
                state.set(42);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Worker interrupted", e);
            }
        });

        try {
            check(reachedGate.await(2, TimeUnit.SECONDS),
                    "Worker did not reach the gate");
            check(!task.isDone(), "Worker finished while gate was closed");
            check(state.get() == 0, "State changed too early");

            releaseGate.countDown();
            task.get(2, TimeUnit.SECONDS);

            check(state.get() == 42, "State was not updated");
            System.out.println("PASS: update occurs after release");
        } finally {
            releaseGate.countDown();
            task.cancel(true);
            executor.shutdownNow();
            check(executor.awaitTermination(2, TimeUnit.SECONDS),
                    "Executor did not terminate");
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LatchTest.java
java LatchTest
~~~

Stdout khi pass:

~~~text
PASS: update occurs after release
~~~

**Vì sao phép thử có ý nghĩa?**

1. Worker gọi `reachedGate.countDown()` đúng khi đến checkpoint. Test chờ `reachedGate.await(...)` trả `true`, thay vì đoán rằng một khoảng thời gian đã đủ để worker chạy.
2. Worker chặn tại `releaseGate.await()`. Khi test chưa mở cổng, worker chưa thể thực hiện `state.set(42)`. Vì test đã biết worker tới checkpoint, `state == 0` và `!task.isDone()` là kiểm tra trạng thái có cơ sở.
3. Test mở cổng bằng `releaseGate.countDown()`, sau đó `task.get(timeout)` chờ tác vụ kết thúc hoặc truyền exception.
4. Test mới kiểm tra giá trị 42. `finally` luôn giải phóng gate, cố hủy tác vụ còn chạy và dọn executor để test fail cũng không bỏ lại worker bị kẹt.

`CountDownLatch` có bảo đảm memory consistency: các hành động trước `countDown()` *happen-before* các hành động sau `await()` trả về khi latch về 0. Các hành động trong asynchronous computation cũng *happen-before* các hành động sau `Future.get()` thành công. Cơ chế này có ý nghĩa khác với việc đơn thuần để đồng hồ chạy qua N mili giây.

Timeout **2 giây** chỉ là ngưỡng bảo vệ minh họa, không phải độ dài cần ngủ. Khi task hoàn tất trong 1 ms, test tiếp tục ngay. Nếu CI quá tải, một timeout quá nhỏ vẫn có thể khiến test fail vì scheduling; hãy chọn ngân sách chờ phù hợp, giữ thông báo lỗi rõ ràng, nhưng đừng biến timeout thành “sleep thay tên”.

## 5. Ví dụ Java 17+: điều khiển interleaving để tái hiện lost update

Trong concurrency, chạy hai thread “cùng lúc” không bảo đảm chúng thực sự cùng đi qua vùng code muốn kiểm tra. Dùng `CyclicBarrier` đặt **ngay sau đọc, trước ghi** có thể buộc cả hai bên đọc trạng thái cũ trước khi ai được phép ghi. Điều này giúp tái hiện race theo chủ đích.

Lưu `InterleavingTest.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class InterleavingTest {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CyclicBarrier barrier = new CyclicBarrier(2);
        AtomicInteger counter = new AtomicInteger();

        try {
            Callable<Void> unsafe = () -> {
                int before = counter.get();
                barrier.await();           // Hai bên đều đã đọc 0.
                counter.set(before + 1);   // Hai bên đều ghi 1.
                return null;
            };

            runBoth(executor, unsafe);
            check(counter.get() == 1, "Expected lost update");
            System.out.println("Compound get/set: " + counter.get());

            counter.set(0);
            Callable<Void> safe = () -> {
                barrier.await();           // Barrier tái sử dụng.
                counter.incrementAndGet(); // Read-modify-write nguyên tử.
                return null;
            };

            runBoth(executor, safe);
            check(counter.get() == 2, "Expected two atomic increments");
            System.out.println("Atomic increment: " + counter.get());
        } finally {
            executor.shutdownNow();
            check(executor.awaitTermination(2, TimeUnit.SECONDS),
                    "Executor did not terminate");
        }
    }

    private static void runBoth(ExecutorService executor,
                                Callable<Void> action) throws Exception {
        Future<Void> first = executor.submit(action);
        Future<Void> second = executor.submit(action);

        try {
            first.get(2, TimeUnit.SECONDS);
            second.get(2, TimeUnit.SECONDS);
        } finally {
            first.cancel(true);
            second.cancel(true);
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac InterleavingTest.java
java InterleavingTest
~~~

Stdout khi hoàn tất bình thường:

~~~text
Compound get/set: 1
Atomic increment: 2
~~~

Dùng `AtomicInteger` không làm **hai lệnh tách rời** `get()` rồi `set()` trở thành một cập nhật nguyên tử. Ở vòng đầu, barrier buộc cả hai worker lấy giá trị 0 trước khi ghi; vì vậy kết quả cuối cùng là 1 bất kể thứ tự ghi. Đây là cách **cố ý tái hiện lỗi lost update** để học và kiểm chứng. Ở vòng thứ hai, `incrementAndGet()` tự nó là phép tăng nguyên tử nên kết quả đúng là 2.

Barrier phải có đủ hai bên tham gia, và executor cũng có đủ hai worker đang chạy. Nếu dùng pool chỉ có một worker mà yêu cầu hai task cùng tới barrier, test có thể tự deadlock. Khi một worker bị ngắt, lỗi hoặc không tới barrier, `Future.get(timeout)` thất bại có kiểm soát và `cancel(true)` cố giải phóng worker; có thể bổ sung `barrier.await(timeout, unit)` để giới hạn chờ ngay trong worker. Khi cần phủ nhiều interleaving hơn, dùng thêm test stress hoặc công cụ kiểm thử concurrency thích hợp: một barrier chỉ kiểm soát thứ tự tại các checkpoint đã đặt.

## 6. Chờ điều kiện thực tế trong producer/consumer và monitor

Với producer/consumer, điều kiện thường là **item đã sẵn sàng**, không phải “đã qua 50 ms”. `BlockingQueue` vừa chuyển dữ liệu vừa cung cấp cơ chế đồng bộ:

~~~java
// Mảnh mã minh họa: queue là BlockingQueue<String>.
queue.put("ready"); // Producer đưa dữ liệu vào queue.

// Ở thread consumer/test:
String item = queue.poll(2, TimeUnit.SECONDS);
if (!"ready".equals(item)) {
    throw new AssertionError("Missing or wrong item");
}
~~~

`poll(timeout)` trả `null` nếu hết hạn mà chưa có item. Khi lấy được item, test biết điều kiện chuyển giao đã xảy ra, có bảo đảm memory consistency của concurrent collection. Đừng sleep rồi kiểm tra `queue.peek()` như thể đó là chứng minh producer đã hoàn tất.

Khi production code dùng `synchronized` và `wait/notifyAll`, hãy kiểm tra predicate trong `while`:

~~~java
// Mảnh mã; ready và monitor thuộc về cùng giao thức đồng bộ.
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // ready đúng dưới monitor ở thời điểm này.
}
~~~

`wait()` có thể thức giấc giả (*spurious wakeup*), hoặc một thread khác có thể thay đổi trạng thái trước khi thread hiện tại giành lại lock. Bởi vậy không dùng một lần `if (!ready) monitor.wait()`. Code production/test cần có đường thoát và deadline nếu trạng thái có thể không bao giờ đạt; với timeout tổng, dùng `System.nanoTime()` tính thời gian còn lại trong vòng lặp. Kiểm tra predicate và chờ phải tuân thủ cùng lock để không gặp *lost notification*.

Các tín hiệu latch cũng phải đặt đúng nghĩa. `countDown()` báo “đã bắt đầu” **không bảo đảm đã hoàn tất**. Nếu muốn latch là “finished”, đặt đếm xuống sau công việc cần kiểm tra, thường trong `finally` khi quy ước là “đã kết thúc dù thành công hay thất bại”; lưu lỗi riêng qua `Future`.

## 7. Cách hiểu đúng về timeout, deadline, interrupt và lỗi từ worker

- `Future.get(timeout, unit)` trả kết quả khi hoàn tất; nếu worker ném exception, test nhận `ExecutionException`; nếu quá hạn, nhận `TimeoutException`. **Timeout không tự hủy task**.
- `CountDownLatch.await(timeout, unit)` trả `true/false`: phải kiểm tra giá trị trả về. Gọi `await()` không thời hạn có thể khiến toàn bộ test suite treo khi code lỗi.
- `Thread.join(timeout)` hết hạn không ném `TimeoutException`: kiểm tra `thread.isAlive()`.
- `Future.cancel(true)` gửi yêu cầu ngắt task đang chạy; không đảm bảo task đã dừng nếu nó bỏ qua interrupt. `shutdownNow()` cũng chỉ cố ngắt các worker và xử lý công việc còn trong queue; sau đó dùng `awaitTermination(timeout)` để kiểm tra.
- Worker bắt `InterruptedException` nên khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` hoặc truyền/hợp thức hóa cancellation đúng theo hợp đồng; không nuốt ngắt và tiếp tục vòng chờ vô hạn.
- Nếu kiểm tra **nhiều** futures, truyền timeout 2 giây độc lập cho mỗi `get` có thể làm tổng thời gian chờ lớn hơn 2 giây nhiều lần. Muốn giới hạn cả batch, dùng một deadline tính từ `System.nanoTime()` và truyền **thời gian còn lại** cho từng `get`, hoặc dùng `ExecutorService.invokeAll(tasks, timeout, unit)` rồi kiểm tra từng Future để phát hiện lỗi/hủy.

Đối với test cần đo **thời gian trôi qua**, `System.nanoTime()` thích hợp hơn `System.currentTimeMillis()` vì đồng hồ thực có thể bị điều chỉnh. Không dùng `nanoTime()` làm timestamp liên máy; chỉ lấy hiệu giữa các lần đọc trong cùng JVM. Timeout là công cụ an toàn để giới hạn chờ, **không phải bằng chứng rằng sự kiện đã xảy ra**.

Đặc biệt, exception trên thread riêng có thể không làm JUnit/test chính fail nếu chỉ `new Thread(...).start()` rồi bỏ qua. Thu exception bằng `Future.get`, hoặc có cơ chế chuyển lỗi về thread test; đừng chỉ log exception.

## 8. Phân biệt “đã xảy ra” và “chưa thể xảy ra”

Chờ một sự kiện **đã xảy ra** khá trực tiếp: `Future.get` hoàn tất hoặc `latch.await(timeout)` trả `true` với tín hiệu đã đặt đúng điểm.

Khẳng định “một sự kiện **chưa xảy ra**” khó hơn. Chỉ nhìn thấy nó chưa xảy ra sau 100 ms không chứng minh nó sẽ không xảy ra sau đó. Muốn kiểm tra một thuộc tính phủ định, hãy tạo điều kiện nhân quả: trong `LatchTest`, test biết worker đã tới checkpoint và còn bị chặn ở `releaseGate` nên việc cập nhật chưa thể chạy. Khi mở gate và `Future.get` trả, test mới khẳng định tác vụ đã xong. Cần kiểm tra chính **giao thức** thay vì xem một ảnh chụp ngẫu nhiên của scheduler.

Có ngoại lệ chính đáng: đặc tả yêu cầu “không gửi sự kiện trong 200 ms”, “debounce đủ 200 ms” hoặc “timeout phải xảy ra sau deadline”. **Thời gian là chính hành vi đang được kiểm thử**. Khi có thể, trừu tượng hóa `Clock`/scheduler và dùng thời gian điều khiển được; khi phải đo thời gian thật, định nghĩa ngưỡng, sai số và deadline rõ ràng. Đây là một test về timing; không dùng sleep để thay thế một tín hiệu completion.

## 9. Mẫu quy trình viết test concurrency ít flaky

1. **Phát biểu thuộc tính:** thay “đợi chút để worker chạy” bằng “worker đã vào checkpoint A”, “đã tiêu thụ đúng item”, “đã xong task”, hoặc “cả hai đã đọc trước khi ghi”.
2. **Chọn tín hiệu:** `Future` khi cần kết quả/lỗi, latch cho checkpoint, barrier cho cuộc đua có kiểm soát, queue cho trao đổi dữ liệu. Chỉ thêm hook test khi nó có ranh giới rõ; không làm thay đổi hành vi nghiệp vụ.
3. **Đảm bảo thực sự có cạnh tranh:** hai task không thể đi qua barrier cùng lúc nếu executor chỉ chạy một worker. Đừng suy luận rằng `start()` hai lần đồng nghĩa chạy đồng thời.
4. **Chờ bằng timeout hữu hạn:** kiểm tra boolean từ latch; để `Future.get` truyền lỗi; phân biệt timeout, assertion sai và exception worker. Dùng một deadline tổng nếu test gồm nhiều lần chờ.
5. **Assert sau mốc đồng bộ chính xác:** nếu latch báo “started”, đừng dùng nó như bằng chứng “completed”. Chỉ kiểm tra dữ liệu sau khi có bảo đảm visibility phù hợp.
6. **Giải phóng và đóng tài nguyên trong `finally`:** mở gate, cancel nếu còn chạy, shutdown executor, await termination. Tránh để test lỗi làm các test sau tiếp tục bị ảnh hưởng.
7. **Chạy lặp và quan sát lỗi có ý nghĩa:** deterministic interleaving test kiểm tra một tình huống được chỉ định; thêm stress test cho nhiều interleaving khác. Test 10.000 lần với sleep không chứng minh chương trình không có race.

Đối với lỗi hiếm, ghi lại checkpoint nào không đạt, task nào timeout, nguyên nhân exception và trạng thái executor/lock khi cần. Test thất bại có thông tin (“worker did not reach gate”) dễ chẩn đoán hơn lỗi chung chung (“expected true”).

## 10. Những lỗi phổ biến khi chuyển từ sleep sang đồng bộ

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `await()` không timeout | Test treo vô hạn khi bug | Dùng bounded wait và cleanup |
| Latch phát tín hiệu quá sớm | Tưởng đã xong dù task còn chạy | Tín hiệu tại checkpoint thực sự; `Future.get` khi cần hoàn tất |
| Latch không countDown trên nhánh lỗi | Worker/test chờ mãi | `finally` nếu latch mang nghĩa “finished” |
| `Future.get(timeout)` fail mà task không được hủy | Thread rò sang test kế tiếp | `cancel`, mở gate và dừng executor |
| Dùng `if` với `wait` | Wakeup giả hoặc predicate đổi giá trị | `while` dưới cùng monitor |
| `volatile int count` rồi `count++` | Vẫn có lost update | Atomic increment hoặc lock |
| Bắt exception trong worker rồi chỉ `printStackTrace` | Test pass giả | Propagate exception qua `Future` |
| Barrier có nhiều bên hơn số worker chạy được | Deadlock trong test | Bảo đảm pool đủ worker; đặt timeout |
| Kiểm tra `isDone` ngay sau `submit` | Scheduler quyết định test pass/fail | Dùng latch checkpoint hoặc `get` |
| Đo “đã xong” bằng kích thước queue | Queue rỗng nhưng task còn chạy | Chờ completion signal/Future |
| Chọn timeout cực nhỏ ở CI tải lớn | False failure do scheduling | Ngưỡng đủ rộng nhưng hữu hạn; báo lỗi rõ |

## 11. Câu hỏi tự kiểm tra

**1. `Thread.sleep(500)` sau `start()` bảo đảm worker đã xong chưa?** Chưa. `join` hoặc `Future.get` chờ kết thúc phù hợp hơn.

**2. `CountDownLatch.await(...)` trả `true` có nghĩa worker đã hoàn thành không?** Chỉ khi `countDown()` được đặt **sau** phần việc cần chứng minh. Latch “started” chỉ xác nhận đã bắt đầu.

**3. `Future.get(2, SECONDS)` hết hạn có hủy tác vụ không?** Không. Test phải cleanup theo chính sách cancellation/lifecycle.

**4. Vì sao cần cả “reached gate” lẫn “release gate”?** Gate thứ nhất xác nhận worker đã tới chỗ cần kiểm tra; gate thứ hai cho phép test chủ động giữ/giải phóng worker.

**5. Dùng `AtomicInteger` có bảo đảm `get() + set()` là một phép tăng nguyên tử không?** Không. Dùng `incrementAndGet()`, `compareAndSet` loop hoặc lock đúng hợp đồng.

**6. Một test latch luôn pass chứng minh không còn data race nào không?** Không. Nó chứng minh thuộc tính ở các checkpoint và lịch chạy đã điều khiển; kiểm tra thiết kế memory model và các interleaving khác vẫn cần thiết.

**7. Khi nào có thể kiểm tra delay thật?** Khi delay chính là đặc tả cần thử. Ưu tiên clock/scheduler điều khiển được, hoặc dùng deadline/biên sai số rõ ràng nếu phải đo đồng hồ thật.

**Điều cần ghi nhớ:** `Thread.sleep()` là thao tác chờ thời gian, không phải điều kiện đồng bộ. Một concurrency test tốt nói rõ ai phát tín hiệu, điều kiện nào đã được xác nhận, dữ liệu nào được bảo đảm nhìn thấy, giới hạn chờ là bao nhiêu và cách giải phóng worker khi lỗi.