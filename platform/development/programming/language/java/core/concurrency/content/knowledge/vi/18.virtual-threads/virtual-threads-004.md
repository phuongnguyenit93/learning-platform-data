# `Executors.newVirtualThreadPerTaskExecutor()` — một virtual thread cho mỗi tác vụ

`Executors.newVirtualThreadPerTaskExecutor()` là API từ **Java 21** để tạo `ExecutorService` chạy **mỗi tác vụ được gửi vào trên một virtual thread mới**. Đây là lựa chọn hữu ích cho chương trình Java có rất nhiều tác vụ độc lập phải chờ I/O như HTTP, socket hoặc cơ sở dữ liệu. Ta tiếp tục viết code blocking, dễ đọc, trong khi JVM có thể quản lý nhiều virtual thread mà không cần dành một OS thread riêng suốt thời gian chờ của mỗi task.

> **Phạm vi:** Java concurrency nói chung, không phụ thuộc Spring. Mã nguồn dùng Java 21+ và thư viện chuẩn JDK; không cần bật preview feature.

## 1. API thực sự làm gì?

Chữ ký:

~~~java
public static ExecutorService newVirtualThreadPerTaskExecutor()
~~~

Phương thức thuộc lớp `java.util.concurrent.Executors`. Khi gọi `executor.execute(runnable)` hoặc `executor.submit(callable)`, executor tạo và khởi chạy virtual thread riêng cho task đó. Không có hạn mức cố định về số virtual thread mà executor tạo. Một virtual thread hoàn tất task sẽ kết thúc, **không được đưa trở lại pool để tái sử dụng**.

Cần phân biệt:

- **Task:** công việc `Runnable` (không trả giá trị) hoặc `Callable<T>` (trả `T` và được phép ném checked exception).
- **Virtual thread:** một `Thread` nhẹ được JVM lập lịch; mỗi task có virtual thread của riêng mình.
- **Carrier thread:** platform/OS thread tạm chạy virtual thread. Khi virtual thread chờ I/O tương thích, JVM có thể tách nó khỏi carrier để carrier phục vụ tác vụ khác. Không phải thao tác blocking nào cũng giải phóng carrier.
- **ExecutorService:** API gửi task, nhận `Future`, yêu cầu hủy và đóng vòng đời executor; không đồng nghĩa với thread pool có số worker cố định.

~~~text
submit(A) ---> virtual thread A --\
submit(B) ---> virtual thread B ---> JVM scheduler ---> platform carrier threads
submit(C) ---> virtual thread C --/
                      |
             chờ I/O tương thích:
             virtual thread có thể unmount để giải phóng carrier
~~~

Thứ tự gửi task **không bảo đảm** thứ tự chạy hoặc hoàn thành. Mỗi virtual thread cũng **không chiếm một OS thread riêng** suốt đời. Đây là điểm khác biệt lớn so với mô hình mỗi yêu cầu mở một platform thread.

## 2. Ví dụ đầy đủ: ba task độc lập

Lưu đoạn sau vào file `VirtualThreadPerTaskDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadPerTaskDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                final int taskId = id;
                futures.add(executor.submit(() -> {
                    Thread.sleep(100); // Mô phỏng thời gian chờ I/O.
                    return "task " + taskId + ": virtual="
                            + Thread.currentThread().isVirtual();
                }));
            }

            // Tất cả task đã được gửi trước khi lấy kết quả.
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac VirtualThreadPerTaskDemo.java
java VirtualThreadPerTaskDemo
~~~

Stdout:

~~~text
task 1: virtual=true
task 2: virtual=true
task 3: virtual=true
~~~

Vì sao kết quả này ổn định?

1. `submit(Callable<String>)` trả lại `Future<String>`. Mỗi lambda chạy trong virtual thread mới.
2. `Thread.currentThread().isVirtual()` được gọi **bên trong** lambda nên trả về `true`.
3. Ta submit cả ba task trước khi `get()`. Các task có thể thực thi đồng thời; vòng `for` phía dưới chỉ **in kết quả theo thứ tự future**. Thứ tự task chạy và kết thúc thực tế vẫn có thể khác.
4. `Thread.sleep(100)` mô phỏng chờ, không phải benchmark. Chương trình không có cam kết kết thúc sau chính xác 100 ms.
5. `try-with-resources` gọi `ExecutorService.close()` khi rời khối, bảo đảm chờ các task đã submit kết thúc.

**Bẫy:** viết `executor.submit(task).get()` ngay trong một vòng lặp có thể tuần tự hóa việc gửi task, vì caller đợi task trước hoàn thành mới gửi task kế tiếp. Hãy submit nhóm task trước rồi xử lý kết quả khi nghiệp vụ cho phép.

## 3. Các cách gửi task và nhận kết quả

| API | Nhận đầu vào | Kết quả cho caller | Xử lý lỗi |
|---|---|---|---|
| `execute(Runnable)` | `Runnable` không trả dữ liệu | `void` | Exception không được xử lý chạy theo cơ chế uncaught exception của thread |
| `submit(Runnable)` | `Runnable` | `Future<?>`; `get()` thành công trả `null` | `get()` ném `ExecutionException` |
| `submit(Callable<T>)` | `Callable<T>` | `Future<T>`, `get()` trả `T` | `get()` ném `ExecutionException` |
| `invokeAll(tasks)` | Tập `Callable` | Danh sách `Future` theo thứ tự đầu vào | Kiểm tra từng future |
| `invokeAny(tasks)` | Tập `Callable` | Một kết quả thành công | Có thể ném `ExecutionException` nếu không task nào thành công |

`Future.get()` chặn **thread gọi get** cho đến lúc task trả kết quả, bị hủy, lỗi hoặc thread chờ bị interrupt. Exception từ `Callable` được bọc trong `ExecutionException` và có thể lấy bằng `getCause()`. Bỏ hết future đồng nghĩa có thể bỏ sót lỗi task.

Snippet sau giả sử biến `future` là `Future<String>` đã được gửi:

~~~java
try {
    String result = future.get();
    System.out.println(result);
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Task failed: " + e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Caller quyết định dừng hoặc hủy công việc còn lại.
}
~~~

Việc chờ kết quả từng future theo thứ tự không có nghĩa các task đã chạy theo đúng thứ tự đó.

## 4. Vòng đời `ExecutorService` và `close()`

Quy trình phổ biến: tạo executor → gửi công việc → thu `Future` → đóng executor.

- **`close()`:** `ExecutorService` hỗ trợ `AutoCloseable` từ Java 19; `close()` bắt đầu shutdown có trật tự và **đợi toàn bộ task đã gửi kết thúc**. Nếu thread gọi `close()` bị interrupt trong lúc đợi, implementation mặc định cố ngắt các task đang chạy theo cơ chế `shutdownNow()`, tiếp tục đợi rồi phục hồi interrupt trước khi trả về.
- **`shutdown()`:** không chấp nhận task mới, cho phép task đã gửi tiếp tục; lời gọi không tự đợi hoàn tất.
- **`shutdownNow()`:** cố interrupt task đang chạy và trả danh sách task chưa chạy; **không bảo đảm** task dừng tức thì.
- **`awaitTermination(timeout, unit)`:** chờ kết thúc khi quản lý vòng đời thủ công.
- **`RejectedExecutionException`:** có thể xảy ra nếu tiếp tục gửi công việc sau shutdown.

Dùng `try (ExecutorService executor = ...)` cho nhóm tác vụ có vòng đời rõ ràng. Với executor sống lâu theo vòng đời của ứng dụng Java, phải xác định chủ sở hữu và thời điểm shutdown/awaitTermination. `close()` có thể đợi mãi nếu task không kết thúc; đóng executor **không tự đóng** socket, file handle hay connection bị task bỏ quên.

## 5. Timeout, cancellation và interrupt

Cần phân biệt **timeout của `Future.get`**, **timeout của I/O trong task** và **timeout tổng thể của nhóm công việc**. `Future.get(500, MILLISECONDS)` chỉ giới hạn thời gian caller chờ; task thường vẫn chạy sau khi `TimeoutException` xuất hiện. `cancel(true)` yêu cầu interrupt virtual thread chạy task nếu task đã bắt đầu, nhưng interrupt là cơ chế hợp tác, không phải cách kill thread cưỡng bức.

Snippet, giả sử `future` thuộc kiểu `Future<String>`:

~~~java
try {
    String value = future.get(
            500, java.util.concurrent.TimeUnit.MILLISECONDS);
    System.out.println(value);
} catch (java.util.concurrent.TimeoutException e) {
    future.cancel(true);
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Cause: " + e.getCause());
} catch (InterruptedException e) {
    future.cancel(true);
    Thread.currentThread().interrupt();
}
~~~

Bên trong task, code hủy cần xử lý đúng:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // Ví dụ trong thân Runnable.
}
~~~

Đây là snippet minh họa trong một `Runnable`; nếu dùng `Callable<T>` thì phải trả đúng kiểu hoặc ném lại exception. Một số hoạt động I/O không lập tức dừng khi interrupt, vì vậy luôn thiết lập timeout ngay trên HTTP client, JDBC query, socket hoặc API tương ứng và đóng tài nguyên bằng `try-with-resources`/`finally`.

## 6. Khi nào virtual thread giúp hiệu năng?

**I/O-bound:** Nếu chương trình có hàng nghìn request độc lập chủ yếu chờ network hoặc DB, virtual thread giúp biểu diễn mỗi request bằng một thread mà không cần dành OS thread riêng cho suốt thời gian chờ. Ở thao tác blocking được JVM hỗ trợ, virtual thread có thể unmount khỏi carrier; carrier có thể chạy công việc khác. Lợi ích chính là **mức đồng thời của các task đang chờ**, không phải làm dịch vụ HTTP hay cơ sở dữ liệu phản hồi nhanh hơn.

**CPU-bound:** Với mã hóa, tính toán hay vòng lặp nặng, virtual thread không tạo thêm lõi CPU. Một executor có số worker hữu hạn, chẳng hạn `Executors.newFixedThreadPool(n)`, thường hợp hơn để kiểm soát parallelism. Cần đo throughput, độ trễ, CPU, memory và chi phí downstream trên workload thực tế.

| Tính chất | `newFixedThreadPool(n)` | `newVirtualThreadPerTaskExecutor()` |
|---|---|---|
| Thread cho task | Tối đa khoảng `n` platform workers cùng chạy | Mỗi task có virtual thread mới |
| Tái sử dụng thread | Có | Không |
| Khi gửi lượng task lớn | Task thừa thường chờ queue của pool | Không đặt giới hạn cố định số virtual thread |
| Phù hợp | Kiểm soát số worker, CPU-bound | Rất nhiều task blocking I/O độc lập |
| Giới hạn DB/downstream | Vẫn cần | **Vẫn cần** |

Không dùng virtual thread như pool kết nối, không giả định virtual thread nào cũng giải phóng carrier ở mọi thao tác blocking, và không kỳ vọng CPU-bound tự nhanh lên.

## 7. Giới hạn tài nguyên thật bằng `Semaphore`

`newVirtualThreadPerTaskExecutor()` không giới hạn số task: nếu 50.000 task cùng gọi một DB chỉ cho 20 kết nối, virtual thread không làm DB có thêm 49.980 kết nối. Giới hạn phần công việc dùng tài nguyên bên ngoài bằng cơ chế riêng như `Semaphore`.

Ví dụ đầy đủ giới hạn tối đa **hai task** cùng nằm trong phần mô phỏng I/O. Tạo file `BoundedVirtualTasks.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class BoundedVirtualTasks {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int id = 1; id <= 5; id++) {
                final int taskId = id;

                futures.add(executor.submit(() -> {
                    permits.acquire();
                    try {
                        Thread.sleep(100);
                        return "done-" + taskId;
                    } finally {
                        permits.release();
                    }
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac BoundedVirtualTasks.java
java BoundedVirtualTasks
~~~

Stdout:

~~~text
done-1
done-2
done-3
done-4
done-5
~~~

`Semaphore(2)` chỉ cho phép hai task giữ permit đồng thời. `acquire()` nằm **trước** `try/finally` để chỉ task lấy permit thành công mới được `release()`. Nếu `Thread.sleep()` bị interrupt, `finally` vẫn trả permit. Vòng in đọc future theo thứ tự submit nên stdout ổn định, dù thứ tự task thực chạy khác.

**Giới hạn của ví dụ:** semaphore trong lambda chỉ khống chế đoạn làm việc giữ permit. Một lượng virtual thread rất lớn vẫn có thể **tích tụ trong lúc chờ permit**, tiêu thụ bộ nhớ. Với nguồn task liên tục, thêm backpressure **trước khi submit**: bounded input queue, giới hạn số future đang chờ, chia batch hoặc điều phối producer-consumer. Đồng thời quản lý connection pool, rate limit, timeout và chính sách retry.

## 8. Shared state, `ThreadLocal` và pinning

Virtual thread vẫn là `Thread` và tuân thủ **Java Memory Model**. Nó không tự sửa race condition, deadlock, lỗi visibility hay việc cập nhật shared mutable state không an toàn. Dùng dữ liệu bất biến, `AtomicInteger`, lock hoặc concurrent collections khi phù hợp. `Future.get()` giúp chờ và nhận kết quả, không biến toàn bộ chương trình thành thread-safe.

`ThreadLocal` hoạt động với virtual thread, nhưng nếu mỗi virtual thread giữ cache hay object lớn, tạo rất nhiều thread có thể tiêu tốn bộ nhớ đáng kể. Không dựa vào giả định một task khác sẽ được chạy trên lại **cùng virtual thread** hay carrier thread. Thường nên truyền context qua tham số và giữ trạng thái theo tác vụ nhỏ gọn.

**Pinning thay đổi theo JDK:**

- Trên **JDK 21–23**, một virtual thread có thể bị *pinned* vào carrier khi thực hiện blocking trong `synchronized` hoặc trong một số native/foreign call. Nếu chặn lâu và thường xuyên, carrier bị giữ, giảm mức đồng thời. `synchronized` ngắn bảo vệ thao tác trong bộ nhớ thường không đáng lo.
- Với Java 21, Java Flight Recorder (JFR) có sự kiện `jdk.VirtualThreadPinned` giúp quan sát. Chỉ thay cấu trúc đồng bộ bao quanh I/O bằng `ReentrantLock` (kèm `try/finally`) khi xác định đúng điểm nghẽn; không thay mọi `synchronized` vô điều kiện.
- **JDK 24+** cải thiện trường hợp pinning liên quan monitor/`synchronized` nhờ JEP 491. Native/foreign call và một số thao tác chặn khác vẫn cần xem xét. Vì vậy phải nêu rõ phiên bản JDK khi đánh giá pinning.

Cuối cùng, kiểm tra thư viện I/O thực tế, driver JDBC, connection pool, socket, DNS, transaction, thời gian chờ của downstream và profiling. Số virtual thread lớn không chứng minh hệ thống tự mở rộng tốt nếu nút thắt nằm ở tài nguyên ngoài.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Tưởng executor là pool giới hạn bằng CPU cores | Quá nhiều task đồng thời nhắm downstream | Giới hạn tài nguyên và backpressure |
| `submit().get()` ngay trong vòng lặp | Công việc có thể bị tuần tự hóa | Submit trước, thu future sau |
| Không đọc future khi task có thể thất bại | Bỏ sót ngoại lệ | Xem `ExecutionException.getCause()` |
| Nghĩ `get(timeout)` sẽ dừng task | Task vẫn chạy sau timeout | `cancel(true)` và timeout I/O |
| Nuốt `InterruptedException` | Hủy không hiệu quả | Dừng công việc hoặc truyền lại interrupt |
| Quên `close()/shutdown()` | Khó quản lý vòng đời, task tồn đọng | `try-with-resources` hoặc lifecycle rõ ràng |
| Không đồng bộ dữ liệu shared | Race condition | Immutable, atomic, locks, collections concurrent |
| Dùng virtual thread để tăng tốc CPU-bound | Không tăng năng lực CPU | Đo workload, dùng bounded pool khi hợp lý |
| Lưu dữ liệu lớn trong mỗi `ThreadLocal` | Tiêu thụ bộ nhớ | State nhỏ, không giữ cache per-thread lớn |
| Blocking dưới `synchronized` dài trên JDK 21 | Có thể pin carrier | Đo bằng JFR rồi tối ưu điểm cần thiết |

## 10. Câu hỏi tự kiểm tra và thực hành

**Tình huống 1:** Có 500 task, DB cho 20 kết nối. Executor có tự giới hạn số task vào DB ở mức 20 không? **Không.** Phải có giới hạn connection/permit/backpressure tương ứng.

**Tình huống 2:** Task 3 hoàn thành trước task 1. Vòng `for` đọc `Future.get()` theo danh sách 1, 2, 3 có in task 3 trước không? **Không.** Thứ tự in theo thứ tự đọc future; thứ tự thực thi không được bảo đảm.

**Tình huống 3:** `future.get(10, MILLISECONDS)` ném `TimeoutException`. Task đã dừng chưa? **Chưa chắc; thông thường vẫn chạy.** Timeout chỉ chấm dứt thời gian caller đợi. Hủy cần `cancel(true)` và cơ chế xử lý interrupt/timeout I/O.

**Bài tập:** Chỉnh `VirtualThreadPerTaskDemo` để task 2 ném `IllegalStateException`, thử bắt `ExecutionException` và in `getCause()`. Trong `BoundedVirtualTasks`, đổi `Semaphore(2)` sang `Semaphore(1)`, dùng `AtomicInteger` đo số task giữ permit lớn nhất. Giải thích vì sao kết quả thứ tự in vẫn giữ nguyên nhưng thời gian chạy thay đổi.

## 11. Những điểm cần nhớ

1. `newVirtualThreadPerTaskExecutor()` (Java 21+) trả về `ExecutorService` tạo **một virtual thread mới cho mỗi task**, không tái sử dụng virtual thread và không có trần đồng thời cố định.
2. Virtual thread có thể tạm nhường carrier khi chờ thao tác blocking tương thích. Lợi ích chủ yếu ở workload I/O-bound có nhiều tác vụ chờ.
3. `Future` cung cấp giá trị/lỗi và cancellation; `get(timeout)` chỉ giới hạn thời gian đợi của caller.
4. `close()` đợi task đã gửi kết thúc; mỗi task vẫn phải quản lý connection, stream và resource của mình.
5. Phải tự đặt giới hạn downstream, backpressure, timeout, cơ chế interrupt, thread safety và giám sát pinning theo phiên bản JDK.

### Tài liệu chính thức

- Java SE 21 `Executors` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- Java SE 21 `ExecutorService` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java 21 Virtual Threads Guide: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
