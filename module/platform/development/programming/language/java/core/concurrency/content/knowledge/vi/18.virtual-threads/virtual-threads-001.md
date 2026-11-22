# Virtual thread trong Java 21 và mục tiêu thiết kế

**Virtual thread** là một loại `java.lang.Thread` được Java runtime quản lý để nhiều tác vụ đang chờ I/O có thể tồn tại đồng thời với ít luồng hệ điều hành hơn. Java 21 đưa virtual threads thành tính năng chính thức qua **JEP 444 (Project Loom)**; không cần bật preview. Đây là nền tảng *concurrency thuần Java*, độc lập với các framework.

Sau bài học, người đọc có thể giải thích vì sao virtual threads ra đời, phân biệt chúng với platform threads, mô tả cơ chế mount/unmount và pinning trong JDK 21, sử dụng API chuẩn, giới hạn tài nguyên và đánh giá đúng hiệu quả.

## 1. Bài toán: nhiều tác vụ chờ nhưng OS threads có hạn

Trong mô hình **thread-per-request**, mỗi yêu cầu được giao cho một platform thread. Một yêu cầu thường chỉ dùng CPU trong thời gian ngắn, phần lớn thời gian còn lại chờ truy vấn dữ liệu, socket hoặc dịch vụ bên ngoài. Platform thread vốn gắn với một OS thread trong vòng đời nên giữ tài nguyên trong cả khoảng chờ. Tạo hàng nghìn OS threads làm tăng chi phí stack, scheduling và chuyển ngữ cảnh; dùng thread pool cố định thì các yêu cầu vượt kích thước pool phải xếp hàng, kể cả khi các worker đang chỉ chờ I/O.

Có thể xử lý vấn đề bằng callback hay `CompletableFuture`, nhưng luồng điều khiển, propagation của exception và việc debug đôi khi khó theo dõi hơn code tuần tự. Virtual threads giúp viết thao tác blocking theo cú pháp đơn giản mà JVM có thể giải phóng carrier trong các khoảng chờ tương thích.

```text
Tác vụ A: chạy Java → chờ I/O ──────────→ chạy tiếp → hoàn thành
Tác vụ B:      chạy Java → chờ I/O ─→ chạy tiếp → hoàn thành
Tác vụ C:           chạy Java → chờ I/O ────→ chạy tiếp
               ^ carrier có thể phục vụ tác vụ sẵn sàng khác
```

Mục tiêu thiết kế của virtual threads gồm:

1. **Tăng khả năng mở rộng của concurrency I/O-bound:** nhiều tác vụ chờ độc lập không buộc số OS threads tăng tương ứng.
2. **Duy trì mô hình dễ đọc:** mỗi tác vụ có một `Thread`, dùng code tuần tự, `try/catch`, call stack và công cụ debugging chuẩn.
3. **Giảm nhu cầu pool các luồng đắt đỏ:** virtual thread đủ nhẹ để đại diện cho *một tác vụ* thay vì là worker tái sử dụng.
4. **Tận dụng API Java quen thuộc:** `Runnable`, `Callable`, `Thread`, `ExecutorService`, `Future` và các công cụ quan sát của JDK vẫn có ích.

**Không có phép màu về tốc độ CPU:** virtual threads chủ yếu cho phép tăng *throughput* khi có nhiều tác vụ đang chờ. Chúng không tự làm một request ít latency hơn, không làm một phép tính CPU nhanh hơn và không tạo thêm lõi CPU.

## 2. Phân biệt platform thread và virtual thread

| Tiêu chí | Platform thread | Virtual thread trên JDK 21 |
|---|---|---|
| Kiểu trong Java | `java.lang.Thread` | Vẫn là `java.lang.Thread` |
| Quan hệ với OS thread | Thường gắn một OS thread cho cả vòng đời | Được mount lên carrier OS thread khi cần chạy |
| Lập lịch | OS lập lịch platform thread | JVM lập lịch virtual thread, OS lập lịch carrier |
| Khi chờ I/O tương thích | OS thread thường tiếp tục bị chiếm | JVM có thể unmount virtual thread, tái sử dụng carrier |
| Chi phí khi có nhiều tác vụ đợi | Lớn hơn | Thường nhỏ hơn đáng kể |
| Mẫu sử dụng | Hữu hạn OS threads hoặc thread pool | Virtual thread mới cho mỗi tác vụ |
| Phù hợp điển hình | Công việc CPU, số luồng hữu hạn hoặc API đặc thù | Nhiều tác vụ blocking I/O độc lập |
| Giới hạn | OS threads, bộ nhớ, CPU | Vẫn có giới hạn heap, sockets, kết nối, CPU, pinning |

Ba thuật ngữ dễ nhầm:

- **Concurrency:** nhiều tác vụ có tiến trình xử lý chồng lên nhau; chúng có thể luân phiên trên một CPU.
- **Parallelism:** nhiều tác vụ thực sự chạy cùng một thời điểm trên các lõi CPU khác nhau.
- **Throughput vs. latency:** số tác vụ hoàn thành trên đơn vị thời gian vs. thời gian một tác vụ hoàn thành. Virtual threads hướng đến throughput ở workload chờ I/O; tăng concurrency không đồng nghĩa latency của từng I/O giảm.

Một hệ thống có 10.000 virtual threads đang chờ network không nhất thiết cần 10.000 OS threads. Nhưng nó vẫn có thể cần nhiều socket, buffer và bộ nhớ tương ứng; số connection của database hay quota API hoàn toàn không được “ảo hóa”.

## 3. Cơ chế carrier, mount, unmount và reschedule

Virtual thread vẫn cần CPU thực, tức vẫn phải chạy trên một **carrier** là platform thread. JVM quản lý việc gắn (*mount*) và tách (*unmount*) virtual thread khỏi carrier:

```text
 Virtual thread A ──┐
 Virtual thread B ──┤    JVM virtual-thread scheduler
 Virtual thread C ──┼──────────────┐
 ...                │              v
 Virtual thread N ──┘       Carrier OS threads
                                │
                                v
                          OS scheduler → CPU
```

1. **Mount:** một virtual thread sẵn sàng chạy được gắn lên carrier; code của nó chạy như Java code thông thường.
2. **Blocking tương thích:** khi tác vụ chờ socket, `Thread.sleep` hoặc một số cơ chế đồng bộ hỗ trợ park, JVM có thể lưu trạng thái tác vụ, unmount nó và trả carrier cho virtual thread khác.
3. **Ready/resume:** khi điều kiện chờ hoàn tất, tác vụ được đưa vào hàng đợi để chạy tiếp; JVM có thể mount nó lên carrier khác.

Bên trong tác vụ, `Thread.currentThread()` trả về **virtual thread của tác vụ**, không trả về carrier. Không nên thiết kế logic phụ thuộc carrier nào đã chạy tác vụ hay thứ tự scheduler chọn các virtual threads.

Với JDK 21, triển khai HotSpot thường dùng một `ForkJoinPool` riêng để lập lịch carrier; mặc định mức parallelism liên quan số bộ xử lý khả dụng, có thuộc tính triển khai `jdk.virtualThreadScheduler.parallelism`. Đây là số carrier hoạt động mục tiêu, **không** là giới hạn tổng số virtual threads. Không chỉnh thuộc tính này theo số lượng requests một cách tùy tiện.

**Giới hạn quan trọng:** không phải mọi thao tác “blocking” đều giải phóng carrier. Một số file I/O trên JDK 21, lời gọi native và blocking trong lúc pinned có thể giữ OS thread. Hiệu quả thực tế phụ thuộc loại I/O, phiên bản JDK và thư viện.

## 4. API `Thread` trong Java 21

Các API chính:

- `Thread.ofVirtual().start(Runnable)`: tạo và bắt đầu virtual thread.
- `Thread.ofVirtual().name("...").start(Runnable)`: đặt tên để quan sát.
- `Thread.startVirtualThread(Runnable)`: factory tĩnh viết ngắn.
- `Thread.currentThread().isVirtual()`: kiểm tra thread hiện tại có phải virtual không.
- `Thread.join()`: chờ tác vụ kết thúc.

Ví dụ **độc lập, chạy bằng JDK 21**; lưu thành `VirtualThreadHello.java`:

```java
public class VirtualThreadHello {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-demo")
                .start(() -> {
                    Thread current = Thread.currentThread();
                    System.out.println("virtual=" + current.isVirtual());
                    System.out.println("name=" + current.getName());
                });
        worker.join();
    }
}
```

Biên dịch và chạy:

```bash
javac VirtualThreadHello.java
java VirtualThreadHello
```

Đầu ra xác định:

```text
virtual=true
name=vt-demo
```

`join()` giữ main sống đến khi virtual thread kết thúc. Điều này quan trọng vì **virtual threads là daemon threads**, không tự giữ JVM sống khi tất cả non-daemon threads đã kết thúc. Mặc định virtual thread không có tên; đặt tên có chủ đích giúp tìm dấu vết.

Một cú pháp tương đương:

```java
Thread worker = Thread.startVirtualThread(() -> doWork());
worker.join();
```

Đây chỉ là ví dụ minh họa API, `doWork()` là phương thức giả định chứ đoạn mã không phải chương trình độc lập.

## 5. Một virtual thread cho mỗi tác vụ bằng `ExecutorService`

`Executors.newVirtualThreadPerTaskExecutor()` tạo executor mà **mỗi tác vụ được giao có một virtual thread mới**, không tái sử dụng một pool virtual threads cố định. `Future` trả về giúp xử lý kết quả/lỗi và đợi các tác vụ.

Ví dụ lưu thành `VirtualThreadTasks.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadTasks {
    public static void main(String[] args) throws Exception {
        List<Future<String>> results = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 1; i <= 3; i++) {
                int taskId = i;
                results.add(executor.submit(() -> {
                    Thread.sleep(100); // Mô phỏng chờ, không phải network I/O.
                    return "task " + taskId
                            + ": virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            // Đọc Future theo thứ tự submit, dù hoàn thành có thể khác thứ tự.
            for (Future<String> future : results) {
                System.out.println(future.get());
            }
        }
    }
}
```

```bash
javac VirtualThreadTasks.java
java VirtualThreadTasks
```

Kết quả:

```text
task 1: virtual=true
task 2: virtual=true
task 3: virtual=true
```

`Thread.sleep(100)` giúp quan sát kiểu chờ; ví dụ này không chứng minh tốc độ hay tính năng I/O của driver. `Future.get()` đợi và nhận kết quả, ném `ExecutionException` nếu code tác vụ thất bại. `try-with-resources` dùng `ExecutorService.close()` để chờ kết thúc theo hợp đồng API; không cần tự kết hợp shutdown thủ công trong ví dụ đơn giản. Với Java 21, mã này không yêu cầu cờ `--enable-preview`.

### Vì sao không pool virtual threads?

Thread pool truyền thống hữu ích khi cần **giới hạn số OS threads đắt đỏ**. Với virtual threads, nên tạo một thread cho mỗi tác vụ và để JVM lập lịch. Pool cố định virtual threads có thể vô tình tạo hàng chờ dù các thread pool worker chỉ đang chờ I/O.

Điều đó **không cho phép gửi vô hạn tác vụ**. Phải quản lý riêng các giới hạn của tài nguyên: connection pool, quota API, RAM, socket, tốc độ tiếp nhận và số tác vụ chờ. Dùng `Semaphore`, bounded queue, timeout, backpressure hoặc giới hạn kết nối để bảo vệ đúng tài nguyên.

## 6. Ví dụ giới hạn một tài nguyên có công suất hữu hạn

Giả sử có 12 tác vụ chờ sử dụng dịch vụ bên ngoài, nhưng hệ thống chỉ cho phép tối đa 3 lượt truy cập cùng lúc. Vẫn có thể tạo 12 virtual threads và dùng `Semaphore` giới hạn **vùng sử dụng tài nguyên**, không giới hạn bằng số thread của một pool.

Lưu thành `VirtualThreadLimit.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadLimit {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(3);
        AtomicInteger completed = new AtomicInteger();
        List<Future<?>> futures = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 12; i++) {
                futures.add(executor.submit(() -> {
                    permits.acquire();
                    try {
                        Thread.sleep(50); // Giả lập I/O sử dụng tài nguyên.
                        completed.incrementAndGet();
                    } finally {
                        permits.release();
                    }
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.println("completed=" + completed.get());
    }
}
```

```bash
javac VirtualThreadLimit.java
java VirtualThreadLimit
```

Kết quả xác định:

```text
completed=12
```

Có 12 tác vụ được giao, nhưng chỉ tối đa 3 tác vụ nằm giữa `acquire()` và `release()` cùng lúc. Tác vụ khác chờ giấy phép. `finally` đảm bảo hoàn trả permit sau khi acquire thành công, ngay cả khi phần việc trong `try` bị ngắt hoặc báo lỗi. `AtomicInteger` cập nhật an toàn từ nhiều threads. Trong hệ thống thật, chọn số permits theo kết nối, quota hoặc khả năng của dịch vụ; cấu hình quá cao vẫn có thể làm quá tải nguồn lực bên dưới.

## 7. Pinning: giới hạn rất quan trọng trên **JDK 21**

**Pinning** nghĩa là virtual thread bị giữ trên carrier, không thể unmount khi nó phải chờ. Trong JDK 21, hai trường hợp chính:

1. Code virtual thread đang thực thi trong `synchronized` block/method và gặp blocking.
2. Code đang thực thi native method hoặc foreign function khiến JVM không thể unmount.

Đoạn dưới đây *chỉ minh họa*, các biến/hàm không được định nghĩa để biên dịch độc lập:

```java
synchronized (sharedLock) {
    blockingRemoteCall(); // Blocking lâu ở đây có thể pin carrier (JDK 21).
}
```

**Pinning không trực tiếp làm sai kết quả hoặc đồng nghĩa deadlock.** Tác động là hiệu suất: nếu nhiều virtual threads bị pin lâu, số carrier rảnh ít đi, làm giảm khả năng phục vụ tác vụ mới. `synchronized` cực ngắn bảo vệ một phép gán hoặc cập nhật bộ nhớ thường không đáng lo. Rủi ro là **blocking I/O dài và thường xuyên** trong vùng synchronized.

Ưu tiên thiết kế là chụp trạng thái dưới khóa, thả khóa, gọi I/O ngoài khóa, rồi cập nhật trạng thái đúng cách. Nếu thực sự cần giữ khóa qua lời gọi blocking và không thể thay đổi mô hình, `java.util.concurrent.locks.ReentrantLock` có thể tránh pinning do intrinsic monitor trên JDK 21:

```java
lock.lock();
try {
    blockingRemoteCall();
} finally {
    lock.unlock();
}
```

Đây cũng là mã minh họa chưa độc lập: `lock` và `blockingRemoteCall()` cần được định nghĩa. **ReentrantLock không xóa tranh chấp khóa**; các tác vụ dùng cùng một khóa vẫn có thể chờ nhau. Không thay mọi `synchronized` bằng `ReentrantLock` nếu không có dấu hiệu pinning ảnh hưởng tới hệ thống.

**Phân biệt phiên bản:** hạn chế pinning do `synchronized` là đặc trưng của **JDK 21–23**; **JDK 24** đã thay đổi cơ chế này qua JEP 491. Bài học và ví dụ về pinning ở đây chủ đích mô tả **Java 21**.

## 8. Các giới hạn và bẫy thường gặp

**CPU-bound:** Công việc tính toán liên tục, nén dữ liệu hoặc chạy thuật toán nặng vẫn bị giới hạn bởi số lõi và CPU time. Tạo vô số virtual threads cho bài toán CPU thuần không tăng tốc phép tính; có thể làm overhead tăng. Hãy đo và dùng mức parallelism phù hợp.

**Blocking không hỗ trợ unmount:** Đừng suy luận rằng chỉ vì API blocking thì JVM sẽ giải phóng carrier. Kiểm tra thư viện, JDBC driver, native calls, file I/O và dấu hiệu pinning trên phiên bản JDK thật.

**ThreadLocal:** Virtual threads hỗ trợ `ThreadLocal` và `InheritableThreadLocal`; tuy nhiên một ứng dụng có thể tạo lượng rất lớn threads. Nếu mỗi thread lưu buffer hoặc cache lớn trong `ThreadLocal`, tổng bộ nhớ sẽ tăng mạnh. Tránh dùng thread-local để giữ tài nguyên đắt đỏ cho từng tác vụ và gọi `remove()` ở `finally` khi phải tự quản lý giá trị.

**Cancellation và timeout:** `Future.cancel(true)` yêu cầu interrupt tác vụ đang chạy; hiệu quả phụ thuộc code/thư viện có đáp ứng interrupt hay không. `Future.get(timeout, unit)` ném `TimeoutException` khi hết giờ chờ nhưng **không tự hủy tác vụ**. Thiết kế timeout cả ở tầng I/O và điểm chờ; xử lý ngắt phù hợp với hợp đồng chương trình.

**Daemon lifecycle:** Virtual threads không giữ JVM sống. `join()`, quản lý bằng `ExecutorService` hoặc một cơ chế đợi rõ ràng giúp tránh thoát sớm khi công việc chưa xong.

**Một `Thread` không thể start lại:** Mỗi virtual thread là một `Thread` thật; không gọi `start()` lần hai. Tác vụ mới dùng virtual thread mới.

**Giới hạn thực tế:** Nhiều virtual threads vẫn tiêu thụ stack frames, object, bộ nhớ giữ bởi tác vụ, sockets và tài nguyên ngoài. Chặn tải ở điểm nhận nếu số request có thể vượt năng lực phục vụ; virtual threads không thay thế rate limiting hoặc backpressure.

## 9. Đo đạc và chẩn đoán trên Java 21

Nên so sánh cùng workload trước và sau khi đổi executor: **throughput**, p95/p99 latency, CPU, heap, số request đang chờ, connection pool và lỗi timeout. Một demo chỉ gọi `sleep` không phải benchmark đại diện cho production.

Công cụ JDK 21:

- **JFR:** sự kiện `jdk.VirtualThreadPinned` để phát hiện pinning; cấu hình mặc định báo pinning trên ngưỡng khoảng 20 ms. `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` có thể bật khi cần (mặc định thường tắt), cùng `jdk.VirtualThreadSubmitFailed`.
- **Trace pinning:** chạy ứng dụng với `-Djdk.tracePinnedThreads=full` hoặc `short` trong JDK 21 để xem stack liên quan đến pinning; cân nhắc dung lượng log.
- **Thread dump:** `jcmd <PID> Thread.dump_to_file -format=json threads.json` giúp quan sát cả virtual và platform threads; dạng dump này không phải một snapshot đồng bộ tuyệt đối.

Các lệnh dưới đây cần thay PID bằng tiến trình thực, còn file JFR phải được ghi trước:

```bash
jcmd 12345 Thread.dump_to_file -format=json threads.json
jfr print --events jdk.VirtualThreadPinned recording.jfr
```

Khi thấy throughput thấp, hãy kiểm tra CPU có quá tải không, connection pool có hết không, virtual threads có bị pin bởi `synchronized`/native không, hay thực chất dịch vụ bên ngoài đang chậm. Chỉ chỉnh scheduler song song sau khi có bằng chứng rõ ràng; không xem nó như nút điều chỉnh “số virtual threads tối đa”.

## 10. Quy tắc chọn và áp dụng

**Nên chọn virtual threads** cho nhiều tác vụ độc lập có tỷ lệ chờ network I/O, JDBC hoặc dịch vụ ngoài cao; đặc biệt khi muốn code tuần tự dễ debug và thư viện blocking được JVM hỗ trợ tốt.

**Không kỳ vọng lợi ích đáng kể** nếu nút thắt là CPU, tranh chấp chung một khóa, giới hạn kết nối, bộ nhớ, database yếu hoặc API bên ngoài có quota thấp. Phải giải quyết nút thắt thực và xác nhận bằng đo đạc.

Quy trình gợi ý:

1. Phân loại tác vụ: bao nhiêu CPU, bao nhiêu thời gian blocking I/O?
2. Dùng một virtual thread cho một tác vụ phù hợp; quản lý kết quả và vòng đời.
3. Giới hạn đúng các tài nguyên khan hiếm (`Semaphore`, connection pool, quota, timeout).
4. Xác minh tương thích thư viện, pinning và hành vi interruption/shutdown.
5. Đo hiệu năng và mức sử dụng tài nguyên trong điều kiện gần thực tế.

**Tư duy cốt lõi:** virtual threads giúp *concurrency có nhiều khoảng chờ* trở nên rẻ và dễ viết hơn; chúng không thay thế việc thiết kế giới hạn tài nguyên, tính đúng đắn của đồng bộ hoặc năng lực CPU.

### Câu hỏi tự kiểm tra

1. Vì sao 10.000 tác vụ cùng chờ socket không nhất thiết cần 10.000 OS threads?
2. `Thread.currentThread()` gọi trong virtual thread trả về virtual thread hay carrier?
3. Sự khác nhau giữa tăng throughput và giảm latency của một request là gì?
4. Tại sao `synchronized` bao quanh network I/O lâu là một vấn đề trên JDK 21?
5. Một database chỉ cho phép 8 connections: nên giới hạn số virtual threads hay số thao tác dùng connection đồng thời?
6. `Future.get(timeout, unit)` hết hạn có tự hủy tác vụ không?

**Đáp án gợi ý:** (1) JVM unmount các virtual threads đang chờ I/O tương thích và tái sử dụng carrier; (2) virtual thread; (3) số việc hoàn thành trên thời gian và thời gian một việc; (4) carrier bị pin khi blocking; (5) lượt sử dụng tài nguyên/connection; (6) không, muốn hủy phải yêu cầu rõ ràng.

### Nguồn chính thức

- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 — `Thread` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 — `Executors` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)