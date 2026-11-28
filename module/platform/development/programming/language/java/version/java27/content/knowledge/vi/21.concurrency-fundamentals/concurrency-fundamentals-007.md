# CountDownLatch, Semaphore, barrier và phối hợp luồng trong Java 27

Khi nhiều luồng cùng xử lý một công việc, chúng không chỉ cần chạy đồng thời mà còn phải **phối hợp đúng thời điểm**. Có lúc một luồng cần đợi mọi tác vụ hoàn thành; có lúc ứng dụng chỉ cho phép tối đa một số tác vụ cùng truy cập tài nguyên; và có lúc tất cả worker phải hoàn thành vòng hiện tại trước khi bước sang vòng tiếp theo.

Trong **Java SE 27**, gói `java.util.concurrent` cung cấp các công cụ phối hợp quan trọng:

- **`CountDownLatch`**: một hoặc nhiều luồng đợi bộ đếm giảm về 0, thích hợp cho **điểm đồng bộ dùng một lần**.
- **`Semaphore`**: quản lý số **permit**, thường dùng để giới hạn số tác vụ cùng truy cập một tài nguyên.
- **`CyclicBarrier`**: một nhóm luồng có số thành viên cố định chờ nhau ở cuối **mỗi vòng xử lý**.
- **`Phaser`**: một barrier nhiều giai đoạn linh hoạt hơn, cho phép đăng ký và hủy đăng ký các bên tham gia.

Bài thuộc chương **Nền tảng lập trình đồng thời**, tập trung vào ngữ nghĩa, các ví dụ Java 27 và điều kiện sử dụng an toàn. Chúng ta cũng phân biệt các synchronizer này với `Future`, `CompletableFuture`, executor và virtual threads. Mọi API trong bài đều có giá trị sử dụng trong Java hiện đại.

## 1. Phân biệt bốn bài toán phối hợp

Giả sử một ứng dụng xử lý báo cáo:

1. Có bốn worker xử lý bốn phần dữ liệu. Luồng điều phối chỉ được tạo báo cáo cuối khi cả bốn đã xong.
2. Dù có hàng trăm yêu cầu, hệ thống chỉ cho phép tối đa ba yêu cầu cùng dùng dịch vụ bên ngoài.
3. Một thuật toán mô phỏng có năm worker. Sau mỗi vòng, tất cả phải gặp nhau trước khi bắt đầu vòng tiếp.
4. Một quy trình nhiều giai đoạn có thể bổ sung hoặc rút bớt worker trong thời gian chạy.

Bốn trường hợp tương ứng:

| Bài toán | Công cụ | Cơ chế |
|---|---|---|
| Đợi N tín hiệu hoặc mở một cổng khởi động | `CountDownLatch` | Đếm ngược về 0, chỉ mở một lần |
| Giới hạn số tác vụ đang sử dụng tài nguyên | `Semaphore` | Lấy và trả permit |
| Đồng bộ N worker cố định qua nhiều vòng | `CyclicBarrier` | Đợi đủ N parties ở mỗi vòng |
| Đồng bộ nhiều giai đoạn với số party thay đổi | `Phaser` | Đăng ký, báo đến và chờ phase tăng |

**Một semaphore có ba permit không có nghĩa là đợi ba tác vụ hoàn thành; một latch có count 3 cũng không có nghĩa là tối đa ba tác vụ được chạy đồng thời.**

### 1.1. Synchronization khác mutual exclusion và scheduling

- **Synchronization** xác định thời điểm một luồng được phép tiếp tục so với luồng khác.
- **Mutual exclusion** bảo vệ một khu vực để chỉ một hoặc một số luồng nhất định được truy cập cùng lúc.
- **Scheduling** quyết định công việc thực thi trên thread nào và khi nào, thường do executor/runtime điều phối.

Một barrier không tự chọn thread để chạy. Semaphore không tự tạo thread. Latch không tự thu thập kết quả hoặc ngoại lệ của worker.

## 2. Chạy tác vụ bằng ExecutorService trong Java 27

Các ví dụ sử dụng `ExecutorService` để quản lý vòng đời tác vụ thay vì tạo thủ công nhiều thread.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorExample {
    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newFixedThreadPool(3)) {

            executor.submit(() ->
                    System.out.println("Một tác vụ đang chạy")
            );
        }
    }
}
~~~

`Executors.newFixedThreadPool(3)` dùng một pool tối đa ba platform worker threads cho các tác vụ nộp vào. Trên Java 27, `ExecutorService` có thể dùng với try-with-resources để đóng executor theo hợp đồng của `close()`.

Java còn có **virtual threads**:

~~~java
try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    executor.submit(() ->
            System.out.println(Thread.currentThread())
    );
}
~~~

Virtual threads có ích khi nhiều tác vụ chủ yếu chờ I/O, nhưng **không làm phép tính CPU tự động nhanh hơn** và không loại bỏ deadlock logic. Nếu một party không bao giờ đến barrier, dùng virtual threads không sửa được điều kiện chờ sai.

## 3. CountDownLatch: đợi count giảm về 0

`CountDownLatch` được khởi tạo với một giá trị đếm không âm:

~~~java
CountDownLatch done = new CountDownLatch(3);
~~~

Các phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| `countDown()` | Nếu count lớn hơn 0, giảm đi 1; khi về 0, giải phóng các bên đang chờ |
| `await()` | Chờ đến khi count bằng 0, trừ khi bị interrupt |
| `await(timeout, unit)` | Chờ có thời hạn; trả `true` nếu count đạt 0, `false` nếu hết hạn |
| `getCount()` | Trả count hiện tại, hữu ích cho quan sát và chẩn đoán |

Minh họa:

~~~text
CountDownLatch(3)

Worker A: countDown() -> count = 2
Worker C: countDown() -> count = 1
Worker B: countDown() -> count = 0
                             |
                             v
                     await() đi tiếp
~~~

Thứ tự worker gọi `countDown()` không quan trọng.

### 3.1. One-shot: không reset được

Khi count đã về 0:

- Các lời gọi `await()` về sau trả ngay.
- Gọi `countDown()` thêm không làm count âm.
- Không có `reset()`.
- Muốn chờ một nhóm sự kiện mới, tạo latch mới hoặc xem xét `CyclicBarrier`/`Phaser` khi các bên cần tái đồng bộ qua nhiều vòng.

`CountDownLatch(1)` là một cổng khởi động đơn giản: nhiều worker cùng đợi tín hiệu từ một coordinator.

## 4. Ví dụ hoàn chỉnh: cổng khởi động và đợi mọi worker

Ba worker cùng đợi bắt đầu, sau đó làm công việc độc lập. Luồng chính đợi tất cả kết thúc và cần biết nếu task có lỗi.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class LatchCoordinationDemo {
    public static void main(String[] args)
            throws InterruptedException,
                   ExecutionException,
                   TimeoutException {

        int workers = 3;
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(workers);

        try (ExecutorService executor =
                     Executors.newFixedThreadPool(workers)) {

            List<Future<Void>> futures = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                int workerId = i + 1;

                Callable<Void> job = () -> {
                    try {
                        startGate.await();

                        System.out.println(
                                "Worker " + workerId + " bắt đầu"
                        );

                        long result = (long) workerId * workerId;

                        System.out.println(
                                "Worker " + workerId
                                + " có kết quả " + result
                        );

                        return null;
                    } finally {
                        // Báo tác vụ đã thoát, kể cả khi có lỗi.
                        finished.countDown();
                    }
                };

                futures.add(executor.submit(job));
            }

            System.out.println("Mở cổng bắt đầu");
            startGate.countDown();

            if (!finished.await(5, TimeUnit.SECONDS)) {
                for (Future<Void> future : futures) {
                    future.cancel(true);
                }

                throw new TimeoutException(
                        "Có worker chưa kết thúc đúng hạn"
                );
            }

            // Latch không chứa kết quả hoặc exception.
            for (Future<Void> future : futures) {
                future.get();
            }

            System.out.println("Tất cả worker thành công");
        }
    }
}
~~~

Phân tích:

1. `startGate` có count 1, các worker chờ đến khi coordinator gọi `countDown()`.
2. `finished` có count bằng số task đã nộp.
3. `finally` bảo đảm worker đã bắt đầu thực thi phần thân lambda sẽ gửi tín hiệu kết thúc ngay cả khi bị lỗi.
4. `finished.await(5, TimeUnit.SECONDS)` tránh việc đợi vô hạn khi một worker không kết thúc.
5. `Future.get()` nhận ngoại lệ nếu tác vụ thất bại; latch **không tự truyền exception**.

Thứ tự log của các worker không được bảo đảm.

**Giới hạn cần hiểu:** `Future.cancel(true)` yêu cầu hủy và có thể interrupt task, nhưng không bảo đảm một tác vụ không hợp tác dừng ngay. `ExecutorService.close()` cũng có thể tiếp tục đợi các task hoàn tất; timeout ở latch không tự giới hạn thời gian đóng executor. Hệ thống sản xuất cần chính sách hủy và deadline tổng thể riêng.

### 4.1. Đếm số tác vụ đã thoát khác số tác vụ thành công

Lời gọi `countDown()` trong `finally` xảy ra dù worker ném ngoại lệ. Vì vậy count về 0 chỉ nói rằng các task đã thoát khỏi đoạn mã liên quan, **không chứng minh thao tác nghiệp vụ đã thành công**.

Nếu yêu cầu là có đủ N kết quả hợp lệ, hãy kiểm tra `Future` hoặc trạng thái thành công/thất bại rõ ràng. Đừng chỉ `countDown()` khi thành công rồi đợi vô thời hạn, vì khi một task lỗi, latch sẽ không thể về 0.

### 4.2. Sai count hoặc task không bao giờ được chạy

~~~java
CountDownLatch done = new CountDownLatch(4);

// Nếu chỉ có ba task có thể gọi countDown()
// thì await() không có timeout có thể kẹt mãi.
~~~

Nếu `submit` thất bại, task bị hủy trước khi bắt đầu hoặc hệ thống thoát sớm, coordinator phải bảo đảm count và tập task thực tế vẫn nhất quán. Một `finally` bên trong task không chạy nếu task chưa bao giờ được thực thi.

`getCount()` chỉ để quan sát tại một thời điểm; không dùng vòng bận kiểm tra count thay cho `await()`.

## 5. Memory visibility của CountDownLatch

Đồng bộ không chỉ là khiến thread đợi. Java Memory Model còn quy định quan hệ **happens-before** để đảm bảo một số ghi dữ liệu được luồng khác nhìn thấy đúng.

Với `CountDownLatch`, các hành động **trước** `countDown()` ở một luồng *happen-before* các hành động **sau khi `await()` tương ứng trả về thành công** ở luồng khác, sau khi count về 0.

~~~java
import java.util.concurrent.CountDownLatch;

class SharedResult {
    int value;
}

SharedResult result = new SharedResult();
CountDownLatch ready = new CountDownLatch(1);

Thread worker = Thread.ofPlatform().start(() -> {
    result.value = 42;
    ready.countDown();
});

ready.await();
System.out.println(result.value); // 42
~~~

Đây là đoạn minh họa khi `result`, `ready` đã được khai báo trong một phương thức thích hợp. Không cần mặc định dùng `volatile` cho mọi trường chỉ để truyền một giá trị đơn giản qua đồng bộ latch đã thiết kế đúng.

Tuy nhiên, latch **không tự bảo vệ các ghi đồng thời** vào cùng một đối tượng trước khi count về 0. Nếu nhiều worker cùng cập nhật một biến với `counter++`, vẫn cần cơ chế an toàn như `AtomicInteger`, lock hoặc phân vùng dữ liệu.

## 6. Semaphore: giới hạn số tác vụ đang giữ permit

`Semaphore` duy trì số permit logic, không phải các đối tượng permit thật. Để dùng tài nguyên đang được hạn chế concurrency, một worker cần lấy permit bằng `acquire()`/`tryAcquire(...)` rồi trả bằng `release()` khi đã xong.

~~~text
Semaphore(2)

Worker A: acquire -> vào ┐
Worker B: acquire -> vào ├── tối đa hai permit đang được dùng
Worker C: acquire -> đợi│
                         |
Worker A: release --------+
Worker C: lấy permit -> vào
~~~

`Semaphore(2)` hạn chế tối đa hai tác vụ **đồng thời** nếu tất cả tuân thủ quy ước lấy/trả permit. Nó **không phải** rate limiter để giới hạn số request mỗi giây.

Các phương thức:

| Phương thức | Công dụng |
|---|---|
| `acquire()` | Chờ và lấy một permit; hỗ trợ interruption |
| `acquire(permits)` | Chờ đủ số permit yêu cầu |
| `tryAcquire()` | Lấy ngay nếu có; trả boolean |
| `tryAcquire(timeout, unit)` | Có thể chờ một thời hạn |
| `release()` | Tăng số permit thêm 1 |
| `release(permits)` | Trả nhiều permit |
| `availablePermits()` | Số permit hiện có tại thời điểm hỏi |

### 6.1. Ví dụ hoàn chỉnh: nhiều virtual threads, tối đa hai yêu cầu đồng thời

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreDemo {
    public static void main(String[] args) throws Exception {
        Semaphore limit = new Semaphore(2);
        AtomicInteger running = new AtomicInteger();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<Void>> futures = new ArrayList<>();

            for (int i = 1; i <= 6; i++) {
                int taskId = i;

                Callable<Void> task = () -> {
                    // InterruptedException ở đây không lấy permit.
                    limit.acquire();

                    try {
                        int concurrent = running.incrementAndGet();

                        try {
                            System.out.printf(
                                    "Tác vụ %d, đang dùng tài nguyên=%d%n",
                                    taskId,
                                    concurrent
                            );

                            Thread.sleep(100);
                            return null;
                        } finally {
                            running.decrementAndGet();
                        }
                    } finally {
                        // Chỉ release khi acquire đã thành công.
                        limit.release();
                    }
                };

                futures.add(executor.submit(task));
            }

            for (Future<Void> future : futures) {
                future.get();
            }
        }
    }
}
~~~

Ở mọi thời điểm, số tác vụ ở trong khu vực đang giữ permit không vượt quá hai nếu không có code khác thao tác sai với semaphore. Thứ tự các dòng log không cố định.

**Mẫu sử dụng chuẩn:**

~~~java
semaphore.acquire();
try {
    useLimitedResource();
} finally {
    semaphore.release();
}
~~~

Đoạn trên giả định các biến và phương thức được khai báo trong ngữ cảnh phù hợp. Đặt `acquire()` **trước** `try/finally` để không vô tình release permit chưa lấy được khi `acquire` ném `InterruptedException`.

Khi cần timeout:

~~~java
if (!semaphore.tryAcquire(2, TimeUnit.SECONDS)) {
    throw new IllegalStateException(
            "Không có permit trong thời hạn"
    );
}

try {
    useLimitedResource();
} finally {
    semaphore.release();
}
~~~

Chỉ gọi `release()` nếu `tryAcquire` trả về `true`.

### 6.2. Semaphore không có ownership theo thread

Semaphore không ghi nhận thread nào là "chủ" của một permit. Về mặt API, một thread có thể `release()` dù chính nó không gọi `acquire()`.

Vì vậy, **release dư** có thể phá giới hạn concurrency:

~~~java
Semaphore permits = new Semaphore(2);

permits.release();
// Số permit có thể là 3 dù giới hạn dự kiến là 2.
~~~

Luôn đảm bảo mỗi lần lấy permit thành công có một lần trả tương ứng. Nếu lấy nhiều permit cùng lúc, phải trả đúng số đã lấy.

Semaphore cũng **không tự bảo vệ mọi trạng thái chia sẻ**. Nếu có hai permit và hai thread cùng sửa một `ArrayList` không thread-safe, việc chúng cùng giữ permit không giúp thao tác `add` trở nên an toàn. Khi cần mutual exclusion, cân nhắc `synchronized` hoặc `Lock`; `Semaphore(1)` là binary semaphore nhưng có ngữ nghĩa ownership khác lock.

## 7. Fairness và starvation của Semaphore

Có thể tạo semaphore không công bằng hoặc công bằng:

~~~java
Semaphore nonFair = new Semaphore(3);
Semaphore fair = new Semaphore(3, true);
~~~

Khi `fair = true`, thứ tự chọn thread nhận permit dựa trên các điểm xếp hàng nội bộ được mô tả trong hợp đồng API. Đây không phải cam kết thứ tự tuyệt đối theo thời điểm thread bắt đầu chạy hoặc log ra màn hình.

**Lưu ý quan trọng:** phiên bản `tryAcquire()` **không có timeout** không tuân thủ fairness như các lời gọi chờ permit. Nó có thể lấy permit sẵn có ngay cả khi semaphore fair có người đang đợi.

~~~java
Semaphore fair = new Semaphore(1, true);

if (fair.tryAcquire()) {
    try {
        // Công việc ngắn.
    } finally {
        fair.release();
    }
}
~~~

Nếu muốn thử lấy permit đồng thời tôn trọng chính sách fairness, có thể xem xét phiên bản chờ có thời hạn với timeout bằng 0 theo hợp đồng API.

Fairness có thể giảm nguy cơ starvation nhưng phải trả chi phí điều phối; không mặc định rằng nó luôn tăng throughput.

### 7.1. availablePermits không phải thao tác giữ chỗ

~~~java
// KHÔNG AN TOÀN nếu dùng để quyết định ai được quyền lấy permit:
if (semaphore.availablePermits() > 0) {
    semaphore.acquire();
}
~~~

Thread khác có thể lấy permit giữa lần kiểm tra và `acquire()`. Hãy dùng trực tiếp `tryAcquire()` hoặc `acquire()`.

### 7.2. acquireUninterruptibly

`acquireUninterruptibly()` tiếp tục chờ dù thread bị interrupt, rồi giữ interrupted status theo hợp đồng khi trả về.

Trong hệ thống có hủy tác vụ, timeout hoặc yêu cầu phản hồi shutdown, thường nên ưu tiên `acquire()` hoặc `tryAcquire(timeout, unit)` để phản ứng interruption rõ ràng hơn.

## 8. CyclicBarrier: gặp nhau ở cuối mỗi vòng

`CyclicBarrier` đợi đủ số **parties** cố định tại một điểm đồng bộ và có thể tái sử dụng ở vòng tiếp theo:

~~~java
CyclicBarrier barrier = new CyclicBarrier(3);
~~~

~~~text
                    Vòng 1
Worker A: xử lý -------- await ┐
Worker B: xử lý -- await ------┤ đủ 3
Worker C: xử lý ------------ await
                               |
                         barrier mở
                               |
                    Vòng 2
Worker A: xử lý ---- await ---┐
Worker B: xử lý -------- await├ đủ 3
Worker C: xử lý -- await -----┘
                               |
                         barrier mở
~~~

Khác với `CountDownLatch`, các worker gọi `await()` vừa **báo đã đến** vừa **chờ các bên khác**, và barrier có thể sử dụng lại qua nhiều vòng.

### 8.1. Barrier action

Có thể cung cấp một `Runnable` chạy đúng một lần mỗi khi barrier đạt đủ parties:

~~~java
CyclicBarrier barrier = new CyclicBarrier(
        3,
        () -> System.out.println("Kết thúc một vòng")
);
~~~

Barrier action được chạy bởi **thread đến cuối cùng** trước khi những bên khác được giải phóng. Tránh đặt thao tác chặn lâu hoặc logic có rủi ro trong action.

### 8.2. Arrival index

`await()` trả về một chỉ số:

- `0` cho thread đến cuối cùng trong vòng.
- `getParties() - 1` cho thread đến đầu tiên trong vòng.

~~~java
if (barrier.await() == 0) {
    System.out.println("Một worker xử lý thống kê sau barrier");
}
~~~

Khi logic cần thực hiện **trước khi giải phóng mọi party**, dùng barrier action thay vì tự dựng cơ chế chọn một thread sau `await()`.

## 9. Ví dụ hoàn chỉnh: ba worker qua hai vòng

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CyclicBarrierDemo {
    public static void main(String[] args) throws Exception {
        int workers = 3;
        int rounds = 2;

        AtomicInteger completed = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(
                workers,
                () -> System.out.println(
                        "Hoàn thành vòng " + completed.incrementAndGet()
                )
        );

        try (ExecutorService executor =
                     Executors.newFixedThreadPool(workers)) {

            List<Future<Void>> futures = new ArrayList<>();

            for (int i = 1; i <= workers; i++) {
                int id = i;

                Callable<Void> job = () -> {
                    for (int round = 1; round <= rounds; round++) {
                        System.out.printf(
                                "Worker %d hoàn thành bước %d%n",
                                id,
                                round
                        );

                        barrier.await(5, TimeUnit.SECONDS);
                    }
                    return null;
                };

                futures.add(executor.submit(job));
            }

            for (Future<Void> future : futures) {
                future.get();
            }
        }

        System.out.println("Số vòng = " + completed.get());
    }
}
~~~

Trong trường hợp bình thường, barrier action chạy đúng hai lần. **Không được giả định thứ tự in giữa các worker**.

Trong ví dụ ba parties, executor có ba worker threads. Nếu pool chỉ có hai thread mà hai task đầu đều chặn tại barrier, task thứ ba sẽ nằm trong hàng đợi không có worker để chạy: đây là một loại **thread-starvation deadlock**. Phải đảm bảo các parties có khả năng đi đến điểm chờ.

## 10. CyclicBarrier bị broken khi một party lỗi

`CyclicBarrier` sử dụng mô hình **all-or-none breakage**. Nếu một party bị interrupt khi chờ, hết timeout hoặc barrier action thất bại, barrier chuyển sang trạng thái **broken**.

| Ngoại lệ | Ý nghĩa |
|---|---|
| `InterruptedException` | Thread chờ bị interrupt |
| `TimeoutException` | `await(timeout, unit)` hết thời hạn |
| `BrokenBarrierException` | Barrier đã bị phá vì party khác lỗi, reset, timeout hoặc action thất bại |

Ví dụ:

~~~java
try {
    barrier.await(2, TimeUnit.SECONDS);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng hoặc báo hủy lên coordinator.
} catch (java.util.concurrent.TimeoutException e) {
    // Barrier đã broken; không tiếp tục vòng như bình thường.
} catch (java.util.concurrent.BrokenBarrierException e) {
    // Một party khác thất bại hoặc barrier đã reset.
}
~~~

`barrier.reset()` đưa barrier về trạng thái ban đầu, nhưng những party đang chờ lúc reset sẽ nhận `BrokenBarrierException`. Không tự động reset ngay trong mọi catch block, vì các worker có thể đang ở những thế hệ barrier khác nhau. Nếu cần khôi phục, hãy dừng các tác vụ cũ và phối hợp tạo vòng mới; trong nhiều trường hợp dùng **barrier mới** đơn giản hơn.

Timeout **không tự hủy các tác vụ CPU/I/O** còn đang chạy. Coordinator cần quản lý `Future` hoặc cơ chế hủy riêng.

## 11. Phaser: barrier linh hoạt với nhiều phase

`Phaser` cho phép đăng ký hoặc rút bớt số parties trong quá trình hoạt động. Mỗi thế hệ đồng bộ có một **phase number**, bắt đầu từ 0.

| Phương thức | Vai trò |
|---|---|
| `register()` | Đăng ký thêm một party |
| `bulkRegister(n)` | Đăng ký n parties |
| `arrive()` | Báo đã đến phase hiện tại, không chờ |
| `arriveAndAwaitAdvance()` | Báo đến và đợi phase tăng |
| `arriveAndDeregister()` | Báo đến rồi rút đăng ký |
| `awaitAdvance(phase)` | Chờ phase thay đổi, không ném InterruptedException chỉ vì interruption |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | Chờ có hỗ trợ interruption và timeout |
| `getPhase()` | Phase hiện tại |
| `getRegisteredParties()` | Số parties đã đăng ký |
| `getUnarrivedParties()` | Số parties chưa đến trong phase hiện tại |
| `forceTermination()` | Kết thúc phaser, giải phóng các bên đang chờ |

### 11.1. arrive khác arriveAndAwaitAdvance

~~~java
int phase = phaser.arrive();
// Đã báo đến nhưng chưa chờ.

phaser.awaitAdvance(phase);
// Đợi phase khác với phase đã báo đến.
~~~

Đoạn này giả định `phaser` được khai báo và thread gọi đã đăng ký như một party. **Không gọi `arrive()` hai lần cho cùng một party trong cùng một phase** chỉ vì chưa thấy phase tăng.

Cách gọn khi muốn vừa đến vừa chờ:

~~~java
int nextPhase = phaser.arriveAndAwaitAdvance();
~~~

Nếu cần chờ có timeout và hỗ trợ interruption:

~~~java
int phase = phaser.arrive();
int next = phaser.awaitAdvanceInterruptibly(
        phase,
        5,
        TimeUnit.SECONDS
);
~~~

Khi `awaitAdvanceInterruptibly` thất bại do interruption hoặc timeout, nó **không tự làm phaser broken/terminated** như `CyclicBarrier`. Coordinator phải quyết định cho party deregister, force termination hoặc điều phối lại công việc, không được để các parties còn lại kẹt mãi.
## 12. Ví dụ hoàn chỉnh: Phaser với ba worker và hai phase

Ví dụ sau đăng ký **ba worker và một party điều phối**. Sau mỗi vòng, chỉ khi cả bốn parties đều báo đến thì phase mới tăng. Worker rút đăng ký sau vòng cuối.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;

public class PhaserDemo {
    public static void main(String[] args) throws Exception {
        int workers = 3;
        int rounds = 2;

        // Luồng chính là một party.
        Phaser phaser = new Phaser(1);

        // Đăng ký worker trước khi nộp task.
        phaser.bulkRegister(workers);

        try (ExecutorService executor =
                     Executors.newFixedThreadPool(workers)) {

            List<Future<Void>> futures = new ArrayList<>();

            for (int i = 1; i <= workers; i++) {
                int workerId = i;

                Callable<Void> task = () -> {
                    try {
                        for (int round = 1; round <= rounds; round++) {
                            System.out.printf(
                                    "Worker %d hoàn tất bước %d%n",
                                    workerId,
                                    round
                            );

                            int next =
                                    phaser.arriveAndAwaitAdvance();

                            if (next < 0) {
                                throw new IllegalStateException(
                                        "Phaser đã kết thúc"
                                );
                            }
                        }

                        return null;
                    } catch (RuntimeException | Error failure) {
                        // Một lỗi làm các bước tiếp theo không còn hợp lệ.
                        phaser.forceTermination();
                        throw failure;
                    } finally {
                        // Worker không phải party của các vòng sau.
                        phaser.arriveAndDeregister();
                    }
                };

                futures.add(executor.submit(task));
            }

            for (int round = 1; round <= rounds; round++) {
                int next = phaser.arriveAndAwaitAdvance();

                if (next < 0) {
                    throw new IllegalStateException(
                            "Worker lỗi hoặc phaser bị kết thúc"
                    );
                }

                System.out.println(
                        "Luồng chính thấy bước " + round + " hoàn tất"
                );
            }

            phaser.arriveAndDeregister();

            // Kiểm tra ngoại lệ từ các worker đã nộp.
            for (Future<Void> future : futures) {
                future.get();
            }
        }
    }
}
~~~

Phân tích:

1. `new Phaser(1)` đăng ký luồng chính.
2. `bulkRegister(3)` đăng ký ba worker, tổng cộng bốn parties.
3. Mỗi vòng, cả ba worker và luồng chính cùng gọi `arriveAndAwaitAdvance()`; phase chỉ tăng khi tất cả đã đến.
4. Worker gọi `arriveAndDeregister()` sau khi không còn tham gia.
5. Nếu worker ném lỗi runtime, chương trình gọi `forceTermination()` để các bên đang đợi có thể thoát và nhận biết thất bại.
6. Sau khi phase cuối hoàn tất, thứ tự các dòng log giữa worker và coordinator vẫn không cố định.

**Giới hạn của ví dụ:** `arriveAndAwaitAdvance()` không có overload timeout. Nếu một worker mất khả năng tiến triển mà không ném ngoại lệ, các bên khác vẫn có thể đợi vô hạn. Hệ thống thực tế nên dùng `arrive()` kết hợp `awaitAdvanceInterruptibly(..., timeout, unit)` và một coordinator chịu trách nhiệm hủy toàn bộ quy trình khi cần.

### 12.1. Số party có thể thay đổi theo thời gian

~~~java
Phaser phaser = new Phaser(1); // Coordinator.

phaser.register(); // Một worker mới tham gia.

// Worker đã xong phase cuối cùng của mình:
phaser.arriveAndDeregister();

// Coordinator không còn tham gia:
phaser.arriveAndDeregister();
~~~

Điểm quan trọng: **đăng ký động không đồng nghĩa có thể đăng ký tùy tiện vào bất kỳ thời điểm nào của thuật toán**. Đăng ký ngay khi các bên khác đang arrive có thể làm thay đổi điều kiện tiến triển. Cần thiết kế giao thức xác định worker mới bắt đầu tham gia **từ phase nào** và khi nào được phép deregister.

### 12.2. Termination và onAdvance

Phaser có thể được kết thúc bằng `forceTermination()` hoặc bởi `onAdvance(int phase, int registeredParties)` trả về `true`. Mặc định, phaser sẽ kết thúc nếu một lần deregister khiến số registered parties về 0.

Có thể định nghĩa điều kiện kết thúc sau hai phase:

~~~java
Phaser phaser = new Phaser(3) {
    @Override
    protected boolean onAdvance(int phase, int parties) {
        // Hoàn tất phase 0 và 1 thì kết thúc.
        return phase >= 1 || parties == 0;
    }
};
~~~

Khi phaser đã terminated, các phương thức liên quan phase trả về giá trị âm theo hợp đồng. Những bên tham gia phải kiểm tra trạng thái này, thay vì tiếp tục thuật toán như thể đồng bộ thành công bình thường.

### 12.3. Phaser không gắn danh tính với từng party

`Phaser` lưu số parties đã đăng ký và số parties chưa đến trong phase, nhưng **không ghi nhận danh tính từng tác vụ**. Do đó, về mặt API, gọi `arrive()` trên behalf một party cần được bảo đảm bằng giao thức do ứng dụng thiết kế.

Gọi `arrive` thừa hoặc quên `arriveAndDeregister` có thể gây sai lệch số parties và khiến chương trình kẹt hoặc tiến triển sai.

## 13. So sánh các kiểu đợi và tái sử dụng

| Tình huống | CountDownLatch | CyclicBarrier | Phaser |
|---|---|---|---|
| Chỉ đồng bộ một lần | Phù hợp | Có thể nhưng không cần cơ chế lặp | Có thể |
| Lặp nhiều vòng | Phải tạo latch mới | Tái sử dụng tự nhiên | Theo phase |
| Số bên tham gia | Count cố định | Parties cố định | Có thể thay đổi |
| Bên báo xong có phải chờ? | `countDown` không chờ | `await` vừa đến vừa chờ | Có `arrive` không chờ hoặc `arriveAndAwaitAdvance` |
| Chờ có thời hạn | `await(timeout)` trả boolean | `await(timeout)` ném `TimeoutException` nếu hết hạn | `awaitAdvanceInterruptibly` có timeout |
| Interruption trong lúc đợi | `InterruptedException` | `InterruptedException`; barrier có thể broken | `awaitAdvanceInterruptibly` ném nhưng phaser không tự terminated |
| Bị broken tự động? | Không có trạng thái broken | Có | Không tương đương; dùng termination |
| Có reset không? | Không | Có, nhưng cần phối hợp đúng | Điều phối bằng phase, có kết thúc |
| Có mang kết quả/lỗi task? | Không | Không | Không |

`Semaphore` trả lời câu hỏi khác: **bao nhiêu tác vụ được phép cùng vào một khu vực**. Nó không đợi N tác vụ báo hoàn tất cùng một phase.

## 14. Interruption, timeout và cancellation

Hệ thống thực tế thường gặp sự cố:

- Worker ném ngoại lệ trước khi đến điểm đồng bộ.
- Thread bị interrupt vì yêu cầu hủy.
- Dịch vụ ngoài không phản hồi.
- Một task bị cancel trước khi bắt đầu thực thi.
- Executor có ít worker threads hơn số parties đang cần tiến đến barrier.

### 14.1. Xử lý InterruptedException đúng cách

Nếu phương thức hiện tại có thể khai báo `throws InterruptedException`, hãy cho ngoại lệ truyền lên khi phù hợp. Nếu phải chuyển nó sang ngoại lệ khác, thường nên khôi phục interrupted status:

~~~java
try {
    latch.await();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Đã yêu cầu hủy", e);
}
~~~

Không chỉ ghi log rồi tiếp tục như thể thao tác chờ đã thành công. Việc chọn cách xử lý phụ thuộc giao thức hủy của ứng dụng.

### 14.2. Bảng so sánh phản ứng khi đợi

| API | Khi bị interrupt | Khi hết thời hạn |
|---|---|---|
| `CountDownLatch.await` | `InterruptedException` | `await(timeout)` trả `false` |
| `Semaphore.acquire` | `InterruptedException` | `tryAcquire(timeout)` trả `false` |
| `CyclicBarrier.await` | `InterruptedException`, barrier broken | `TimeoutException`, barrier broken |
| `Phaser.awaitAdvanceInterruptibly` | `InterruptedException`, phaser không tự terminated | `TimeoutException`, phaser không tự terminated |
| `Phaser.awaitAdvance` | Không chấm dứt chờ chỉ vì interrupt | Không có overload timeout trực tiếp |
| `Future.get(timeout, unit)` | `InterruptedException` | `TimeoutException`; task chưa bị hủy tự động |

**Hết thời gian chờ không đồng nghĩa tác vụ đã ngừng chạy.** Timeout phải kéo theo chính sách hủy, cleanup và báo lỗi phù hợp.

### 14.3. Deadline của toàn workflow

Nếu một request có ngân sách 10 giây, việc đợi semaphore 10 giây rồi đợi latch thêm 10 giây đã có thể vượt thời hạn nghiệp vụ.

Nên dùng một **deadline chung**, tính thời gian còn lại cho từng bước, thay vì cộng nhiều timeout độc lập. Có thể dùng `System.nanoTime()` để đo khoảng thời gian tương đối, `TimeUnit` để chuyển đơn vị và `Future.cancel(true)` khi cần đề nghị hủy.

Không quên rằng `ExecutorService.close()` có thể tiếp tục đợi các tác vụ không hợp tác. Cần quản lý vòng đời executor phù hợp với deadline.

## 15. Những deadlock và lỗi thiết kế dễ gặp

### 15.1. Thread pool không đủ chỗ cho barrier

~~~text
Executor: fixedThreadPool(2)
Task: A, B, C
Barrier: 3 parties

A -> await (đang chiếm worker 1)
B -> await (đang chiếm worker 2)
C -> chờ trong hàng đợi, không có worker rảnh

=> A và B không thể vượt barrier vì C chưa được chạy.
~~~

Đây là dạng **thread-starvation deadlock**. Phải đảm bảo mọi party có khả năng tiến đến điểm chờ, hoặc dùng cấu trúc điều phối khác.

### 15.2. Semaphore và khóa tạo vòng chờ

~~~text
Thread A giữ lock L, rồi chờ semaphore.acquire().
Thread B cần lock L để hoàn tất và trả permit.

=> A đợi permit từ B, B đợi lock do A giữ.
~~~

Tránh chờ permit trong khi vẫn giữ một khóa cản trở task khác trả permit.

### 15.3. Quên countDown hoặc release

Nếu worker bỏ qua `countDown()`, latch không thể tự suy ra worker đã kết thúc. Nếu task không `release()`, semaphore mất dần permit.

Dùng nguyên tắc:

- Mỗi tín hiệu hoàn tất dự kiến phải có đúng một lần `countDown()`, kể cả trường hợp task đã được hủy trước khi chạy do coordinator xử lý.
- Mỗi lần `acquire` thành công phải có đúng một `release` tương ứng, thường trong `finally`.

### 15.4. Dữ liệu chia sẻ vẫn có thể bị race

Barrier tạo một điểm đồng bộ ở cuối phase nhưng không tự làm phép tăng `counter++` trong phase trở nên nguyên tử. Tương tự, semaphore hai permit không đảm bảo cấu trúc dữ liệu mutable chỉ được một worker truy cập.

Dùng `AtomicInteger`, `Lock`, `synchronized`, phân vùng dữ liệu hoặc collector có hợp đồng phù hợp nếu nhiều luồng cùng sửa dữ liệu.

### 15.5. Reset barrier quá sớm

`CyclicBarrier.reset()` khi vẫn có worker chờ sẽ làm các worker đó nhận `BrokenBarrierException`. Nếu coordinator phát luôn công việc vòng mới, một số worker có thể đang ở thế hệ cũ, số khác ở thế hệ mới.

Không reset tùy tiện. Phối hợp dừng toàn bộ vòng cũ hoặc tạo barrier mới.

## 16. Memory consistency của các synchronizer

Các công cụ thuộc `java.util.concurrent` tạo quan hệ **happens-before** theo Java Memory Model:

| Công cụ | Bảo đảm đáng nhớ |
|---|---|
| `CountDownLatch` | Hành động trước `countDown` *happen-before* hành động sau `await` thành công khi count về 0 |
| `Semaphore` | Hành động trước `release` *happen-before* hành động sau `acquire` thành công tương ứng |
| `CyclicBarrier` | Hành động trước `await` *happen-before* barrier action, và action *happen-before* hành động sau `await` thành công ở luồng khác |
| `Phaser` | Các thao tác arrive và đợi phase tạo quan hệ visibility theo hợp đồng của API và gói concurrent |

Điều này giúp các kết quả được ghi ở phase trước có thể được worker khác quan sát đúng khi phase sau bắt đầu.

**Nhưng không có nghĩa**:

- Bất kỳ đối tượng mutable nào cũng thread-safe.
- Mọi `counter++` đều atomic.
- Worker thực thi theo một thứ tự log cố định.
- Tác vụ thất bại được synchronizer tự truyền đến coordinator.
- Một lần `await` trả về thành công chứng minh công việc nghiệp vụ không lỗi.

Phải thiết kế cả **quy tắc sở hữu dữ liệu**, **thời điểm truy cập** và **cách xử lý thất bại**.

## 17. Khi nào nên dùng Future hoặc CompletableFuture thay cho latch?

Nhiều bài toán thực chất là “đợi tác vụ **trả kết quả**”, không chỉ “đợi N tín hiệu”. Khi đã dùng `ExecutorService.submit`, `Future.get()` có thể:

- Đợi tác vụ hoàn thành.
- Nhận giá trị.
- Báo lỗi qua `ExecutionException`.
- Hỗ trợ timeout và yêu cầu hủy.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FuturesExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newFixedThreadPool(2)) {

            Future<Integer> a = executor.submit(() -> 20);
            Future<Integer> b = executor.submit(() -> 22);

            int total = a.get() + b.get();
            System.out.println(total); // 42
        }
    }
}
~~~

Ở đây không cần `CountDownLatch`. Latch hữu ích khi cần tín hiệu tách khỏi kết quả, chẳng hạn nhiều worker chờ start gate hoặc coordinator chờ các sự kiện không phải `Future`.

### 17.1. CompletableFuture.allOf

~~~java
import java.util.concurrent.CompletableFuture;

public class AllOfExample {
    public static void main(String[] args) {
        CompletableFuture<Integer> a =
                CompletableFuture.completedFuture(20);

        CompletableFuture<Integer> b =
                CompletableFuture.completedFuture(22);

        CompletableFuture.allOf(a, b).join();

        System.out.println(a.join() + b.join()); // 42
    }
}
~~~

`allOf` hữu ích khi muốn đợi nhiều future. Nếu một future hoàn thành ngoại lệ, future tổng hợp cũng có thể hoàn thành ngoại lệ theo hợp đồng, nhưng `allOf` **không tự hủy tất cả các future khác**.

### 17.2. Executor, semaphore và barrier có trách nhiệm khác nhau

- Executor quyết định thực thi task và quản lý tài nguyên chạy.
- Semaphore giới hạn số task sử dụng một khu vực/tài nguyên.
- Future truyền kết quả và ngoại lệ.
- CountDownLatch phát tín hiệu phối hợp một lần.
- CyclicBarrier/Phaser tạo các điểm chờ qua nhiều vòng.

Có thể sử dụng nhiều công cụ đồng thời nếu mỗi công cụ thực sự giải quyết một trách nhiệm.

## 18. Ví dụ tổng hợp: giới hạn yêu cầu và thu thập kết quả

Giả sử cần xử lý 20 phần dữ liệu nhưng chỉ cho tối đa bốn công việc dùng một tài nguyên cùng lúc. Sau cùng, coordinator tổng hợp kết quả.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class BoundedJobsDemo {
    public static void main(String[] args) throws Exception {
        Semaphore maxInFlight = new Semaphore(4);

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<Integer>> futures = new ArrayList<>();

            for (int i = 1; i <= 20; i++) {
                int itemId = i;

                Callable<Integer> job = () -> {
                    maxInFlight.acquire();

                    try {
                        // Thay bằng thao tác I/O nghiệp vụ.
                        return itemId * 10;
                    } finally {
                        maxInFlight.release();
                    }
                };

                futures.add(executor.submit(job));
            }

            long total = 0;

            for (Future<Integer> future : futures) {
                total += future.get();
            }

            System.out.println("Tổng = " + total); // 2100
        }
    }
}
~~~

Ở đây:

1. Virtual threads là mô hình thực thi.
2. Semaphore giới hạn mức độ truy cập tài nguyên.
3. Future trả kết quả hoặc lỗi.
4. Không có nhiều phase, nên không cần barrier.
5. Nếu cần mọi worker chờ cùng một tín hiệu khởi động, có thể thêm `CountDownLatch(1)`.

Với dịch vụ thật, cần thêm timeout, retry có giới hạn và rate limiting khi cần. **Semaphore không tự thực hiện giới hạn request theo giây, timeout request hoặc retry.**

## 19. Kiểm thử và quan sát ứng dụng đồng thời

Không nên kết luận đoạn mã concurrency đúng chỉ vì nó chạy một lần mà không ném lỗi.

| Tình huống | Điều cần kiểm tra |
|---|---|
| `CountDownLatch(0)` | `await` trả ngay |
| Ít countDown hơn dự kiến | `await(timeout)` trả `false`, test không treo |
| Task lỗi trước countDown | Được xử lý bằng finally/coordinator, không nuốt lỗi |
| Semaphore chỉ có một permit | Không có hai task cùng ở vùng giới hạn nếu tuân thủ giao thức |
| Thread bị interrupt trước acquire thành công | Không có release dư |
| Semaphore fair | Không kỳ vọng thứ tự log tuyệt đối |
| CyclicBarrier đủ parties | Mỗi vòng mở đúng khi đủ bên |
| Thiếu một party | Timeout/broken, không treo vô hạn |
| Một party bị interrupt | Các party khác biết barrier đã thất bại |
| Phaser deregister một party | Vòng sau không còn chờ party đó |
| Phaser forceTermination | Các bên chờ thoát và nhận biết giá trị phase âm |
| Task bị hủy trước khi chạy | Coordinator không chờ một tín hiệu không thể đến |
| Executor quá nhỏ | Không rơi vào thread-starvation deadlock |

### 19.1. Đừng lấy sleep làm đồng bộ

~~~java
Thread.sleep(100);
// Không chứng minh được task khác đã hoàn thành.
~~~

Máy bận hoặc môi trường CI chậm có thể khiến test thất bại ngẫu nhiên. Hãy đợi đúng sự kiện bằng `CountDownLatch`, `Future.get(timeout)` hoặc công cụ tương đương.

### 19.2. Metric chỉ để theo dõi

- `CountDownLatch.getCount()` là ảnh chụp count.
- `Semaphore.availablePermits()` không giữ chỗ permit.
- `CyclicBarrier.getNumberWaiting()` chủ yếu cho debug và theo dõi.
- `Phaser.getRegisteredParties()`, `getArrivedParties()` và `getUnarrivedParties()` có thể thay đổi khi thread khác hoạt động.

Không thay thế API đồng bộ bằng vòng bận kiểm tra các giá trị trên.

## 20. Bảng lựa chọn nhanh

| Bạn cần… | Nên bắt đầu bằng… | Vì sao |
|---|---|---|
| Mở cổng bắt đầu cho nhiều worker | `CountDownLatch(1)` | Một tín hiệu mở cho nhiều bên |
| Đợi N tác vụ phát tín hiệu kết thúc | `CountDownLatch(N)` | Một lượt đếm hoàn tất |
| Đợi và lấy kết quả/lỗi của tác vụ | `Future.get` hoặc `CompletableFuture.allOf` | Mang thông tin thành công/thất bại |
| Tối đa N tác vụ dùng API ngoài cùng lúc | `Semaphore(N)` | Quản lý permit |
| Nhóm worker cố định gặp nhau qua các vòng | `CyclicBarrier` | Tái sử dụng cùng số parties |
| Worker tham gia từng phase có thể thay đổi | `Phaser` | Đăng ký và deregister |
| Chỉ một thread được sửa dữ liệu chung một lúc | `synchronized` hoặc `Lock` | Mutual exclusion có ownership phù hợp |
| Nhiều I/O chặn độc lập | Executor phù hợp, có thể dùng virtual threads | Điều phối execution, cần giới hạn tài nguyên riêng |
| Deadline và hủy nhiều tác vụ phức tạp | Cơ chế điều phối có timeout/cancellation rõ ràng | Synchronizer đơn lẻ không đủ |

## 21. Bài tập thực hành

### Bài 1: Cổng khởi động

Tạo năm worker cùng dùng `CountDownLatch(1)`. Coordinator nộp năm task rồi phát tín hiệu mở cổng. Tạo một cơ chế đợi các task kết thúc có timeout.

**Câu hỏi:** Vì sao latch không thể reset để mở cổng vòng thứ hai?

### Bài 2: Giới hạn kết nối

Tạo 30 task với `Semaphore(4)`. Dùng `AtomicInteger` để đo số task đang ở vùng giới hạn.

Yêu cầu: không vượt quá bốn, release đúng một lần, không release khi `acquire` bị interrupt trước khi lấy permit.

**Câu hỏi:** Vì sao semaphore không tự giới hạn bốn yêu cầu **mỗi giây**?

### Bài 3: Barrier ba vòng

Tạo bốn worker và một `CyclicBarrier(4)` với action đếm số vòng. Sau đó cố ý làm một worker thất bại trước khi tới barrier.

Yêu cầu: các bên còn lại thoát bằng timeout hoặc lỗi và coordinator biết rằng pipeline thất bại.

**Câu hỏi:** Vì sao không nên gọi `reset` ngay mà không có giao thức khôi phục?

### Bài 4: Phaser với party thay đổi

Tạo phaser có coordinator và hai worker. Một worker chỉ tham gia vòng đầu, sau đó `arriveAndDeregister`. Worker còn lại tiếp tục hai vòng.

Yêu cầu: không arrive hai lần trong cùng một phase, kiểm tra phase âm sau termination, có phương án hủy nếu chờ quá hạn.

**Câu hỏi:** Vì sao timeout từ `awaitAdvanceInterruptibly` không tự làm phaser broken?

## 22. Checklist thiết kế an toàn

- [ ] Đã xác định rõ bài toán là tín hiệu hoàn tất, giới hạn concurrent hay barrier nhiều phase chưa?
- [ ] Count/parties có khớp số tác vụ có khả năng thực sự chạy không?
- [ ] Nếu dùng fixed thread pool, mọi party có đủ khả năng tiến đến barrier chưa?
- [ ] Task có thể lỗi, bị hủy trước khi bắt đầu, hoặc bị interrupt không?
- [ ] Mọi điểm chờ có timeout/deadline hợp lý không?
- [ ] Khi một party lỗi, những party khác được giải phóng và biết thất bại chưa?
- [ ] Mỗi acquire thành công có đúng một release tương ứng không?
- [ ] Có lạm dụng `availablePermits` để quyết định quyền truy cập không?
- [ ] Có xử lý `CyclicBarrier` broken và không reset tùy tiện không?
- [ ] Các thao tác register/deregister phaser được gắn với phase rõ ràng chưa?
- [ ] Có phân biệt memory visibility với atomicity của dữ liệu chia sẻ không?
- [ ] Đã lấy kết quả/ngoại lệ qua `Future` khi cần chưa?
- [ ] Test đã bao phủ timeout, interruption, thiếu party và cancellation chưa?
- [ ] Có tránh giữ lock cản trở task khác trả permit hoặc tiến tới barrier không?
- [ ] Có nhớ virtual threads không giải quyết deadlock logic hay giới hạn tài nguyên không?

## 23. Tóm tắt

- **`CountDownLatch`** là cổng đồng bộ **one-shot**; count giảm về 0 và không reset.
- **`Semaphore`** quản lý permit, thích hợp để giới hạn concurrency; phải release đúng số đã acquire.
- **`CyclicBarrier`** phối hợp số parties cố định qua nhiều vòng; timeout hoặc interruption có thể làm barrier broken.
- **`Phaser`** cho phép số parties thay đổi và tách thao tác **đến** khỏi **chờ**; timeout khi chờ không tự terminate.
- Các synchronizer cung cấp quan hệ **happens-before**, nhưng không tự làm mọi đối tượng mutable trở nên thread-safe.
- **`Future`** và **`CompletableFuture`** thường phù hợp hơn latch nếu nhu cầu chính là lấy kết quả và quan sát lỗi.
- Virtual threads hữu ích trong nhiều bối cảnh I/O chặn nhưng không loại bỏ deadlock, sai lệch count hay giới hạn tài nguyên.
- Luôn thiết kế **deadline, interruption, cancellation, cleanup và khả năng tiến triển** cho cả coordinator và worker.

## Tài liệu tham khảo chính thức

- [CountDownLatch — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Semaphore — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [CyclicBarrier — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Phaser — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Phaser.html)
- [ExecutorService — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Executors — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html)
- [Future — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html)
- [CompletableFuture — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [TimeUnit — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/TimeUnit.html)
- [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/package-summary.html)
