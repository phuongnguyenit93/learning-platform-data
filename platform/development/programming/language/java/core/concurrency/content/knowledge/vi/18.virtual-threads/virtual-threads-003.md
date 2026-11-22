# Tạo luồng bằng `Thread.ofVirtual()` và `Thread.startVirtualThread()` trong Java

## 1. Mục tiêu và điều kiện chạy

**Virtual thread (luồng ảo)** là một `java.lang.Thread` do Java runtime quản lý và lập lịch, thay vì gắn cố định với một luồng hệ điều hành trong suốt vòng đời. Virtual thread phù hợp cho lượng lớn công việc **chờ I/O**: truy vấn cơ sở dữ liệu, gọi HTTP, đọc/ghi socket, chờ phản hồi từ dịch vụ khác. Mục tiêu là giữ phong cách lập trình tuần tự dễ đọc mà vẫn hỗ trợ nhiều tác vụ đồng thời đang chờ.

Bài này tập trung vào hai cách tạo và khởi chạy virtual thread trong **Java thuần**:

- `Thread.startVirtualThread(Runnable task)`: tạo **và khởi chạy ngay** một virtual thread bằng lời gọi ngắn.
- `Thread.ofVirtual()`: lấy `Thread.Builder.OfVirtual` để cấu hình tên, trình xử lý lỗi, tạo thread chưa chạy, khởi chạy thread hoặc tạo `ThreadFactory`.

**Yêu cầu:** JDK **21 trở lên**; virtual threads trở thành tính năng chính thức từ Java 21 (JEP 444). Ví dụ bên dưới biên dịch với `javac` và chạy với `java` mà không cần `--enable-preview`. Trong JDK 19–20, virtual threads là tính năng preview nên điều kiện và API sử dụng khác.

Kiểm tra môi trường:

~~~bash
java -version
javac -version
~~~

Không nên đánh đồng virtual thread với việc làm CPU chạy nhanh hơn. Chúng giúp mở rộng **số tác vụ đồng thời đang đợi**, không làm tăng số lõi CPU.

## 2. Hai API cốt lõi

### 2.1. `Thread.startVirtualThread(Runnable)` — tạo và chạy ngay

Chữ ký API:

~~~java
public static Thread startVirtualThread(Runnable task)
~~~

- Nhận một `Runnable`, chạy nội dung `run()` trên **virtual thread mới**.
- Trả về đối tượng `Thread` **đã được start**; công việc có thể chạy trước hoặc sau thời điểm lời gọi trả về.
- Muốn đợi hoàn tất, gọi `join()`. Muốn yêu cầu dừng khi đang chờ hoặc đang xử lý, gọi `interrupt()` và thiết kế tác vụ biết hợp tác với interrupt.
- Không có tùy chọn đặt tên trực tiếp trong lời gọi này; khi cần cấu hình, dùng builder.

Ví dụ độc lập, lưu thành **`StartVirtualThreadDemo.java`**:

~~~java
public class StartVirtualThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.startVirtualThread(() -> {
            System.out.println(
                    "Đang chạy trên virtual thread: "
                            + Thread.currentThread().isVirtual());
        });

        worker.join();
        System.out.println("Đã kết thúc: " + !worker.isAlive());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StartVirtualThreadDemo.java
java StartVirtualThreadDemo
~~~

Kết quả chính xác:

~~~text
Đang chạy trên virtual thread: true
Đã kết thúc: true
~~~

`Thread.currentThread()` trả về **virtual thread đang thực thi** mã, và `isVirtual()` cho biết loại thread. `join()` buộc luồng `main` chờ cho worker kết thúc, nên thứ tự hai dòng kết quả là xác định. Virtual thread mặc định là **daemon thread**, vì vậy với chương trình ngắn cần đợi hoặc quản lý vòng đời rõ ràng; không nên trông chờ JVM giữ chương trình sống chỉ vì một virtual thread vẫn đang chạy.

### 2.2. `Thread.ofVirtual()` — builder có thể cấu hình

`Thread.ofVirtual()` **không tự tạo hoặc start thread**. Nó trả về một builder:

~~~java
Thread.Builder.OfVirtual builder = Thread.ofVirtual();
~~~

Các thao tác quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `builder.start(task)` | Tạo và start virtual thread, trả về `Thread` đã chạy |
| `builder.unstarted(task)` | Tạo virtual thread ở trạng thái `NEW`; cần gọi `thread.start()` |
| `builder.name("ten")` | Đặt tên xác định cho thread tạo từ builder |
| `builder.name("prefix-", 1)` | Đặt tiền tố và bộ đếm tên, ví dụ `prefix-1`, `prefix-2` |
| `builder.uncaughtExceptionHandler(handler)` | Xử lý ngoại lệ không bắt được của thread |
| `builder.inheritInheritableThreadLocals(false)` | Không kế thừa các giá trị `InheritableThreadLocal` từ thread tạo |
| `builder.factory()` | Tạo `ThreadFactory` có cấu hình tương ứng |

Ví dụ độc lập, lưu thành **`VirtualThreadBuilderDemo.java`**:

~~~java
public class VirtualThreadBuilderDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-report")
                .unstarted(() -> System.out.println(
                        "Tên worker: " + Thread.currentThread().getName()));

        System.out.println("Trước start: " + worker.getState());
        worker.start();
        worker.join();
        System.out.println("Sau join: " + worker.getState());
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadBuilderDemo.java
java VirtualThreadBuilderDemo
~~~

Kết quả chính xác:

~~~text
Trước start: NEW
Tên worker: vt-report
Sau join: TERMINATED
~~~

Đối chiếu ba cách viết:

~~~java
Runnable job = () -> System.out.println("Hello");

// A: ngắn nhất, tạo và chạy ngay
Thread a = Thread.startVirtualThread(job);

// B: tạo và chạy ngay, có thể cấu hình thêm trên builder
Thread b = Thread.ofVirtual().name("vt-b").start(job);

// C: tạo trước, chủ động quyết định thời điểm start
Thread c = Thread.ofVirtual().name("vt-c").unstarted(job);
c.start();

a.join();
b.join();
c.join();
~~~

Đoạn trên là **mảnh mã đặt bên trong phương thức có khả năng ném `InterruptedException`**, không phải toàn bộ tệp Java. Ba dòng `Hello` có thể xuất hiện theo thứ tự bất kỳ; gọi `start()` **không** đồng nghĩa chạy xong công việc trước khi thực hiện lệnh tiếp theo.

**Quy tắc lifecycle:** một đối tượng `Thread` chỉ được `start()` **một lần**. Gọi `start()` lại (kể cả sau khi thread đã kết thúc) gây `IllegalThreadStateException`. Gọi `run()` trực tiếp không thay thế `start()`; với virtual thread, `Thread.run()` trực tiếp không thực thi tác vụ được gắn vào thread theo cách mong đợi.

## 3. Chọn cách nào cho từng tình huống?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Chạy nhanh một `Runnable` rồi `join()` | `Thread.startVirtualThread(task)` |
| Đặt tên hoặc handler cho một worker | `Thread.ofVirtual().name(...).start(task)` |
| Tạo thread trước nhưng chủ động start sau | `Thread.ofVirtual().unstarted(task)` rồi `start()` |
| Tạo nhiều worker cùng quy ước tên | `Thread.ofVirtual().name(prefix, start).factory()` |
| Chạy rất nhiều tác vụ độc lập, cần `Future`/kết quả | `Executors.newVirtualThreadPerTaskExecutor()` |

`Thread.startVirtualThread(task)` tương đương về mặt tạo/start cơ bản với `Thread.ofVirtual().start(task)`. Sự khác biệt hữu ích là **builder có thể cấu hình** trước khi tạo thread. Không cần builder chỉ để dùng virtual threads.

Khi sử dụng `Thread.Builder.OfVirtual` để tạo nhiều thread, không nên chia sẻ một builder có thể thay đổi giữa các luồng một cách tùy tiện: builder **không được bảo đảm thread-safe**. Với nhiều tác vụ, `ThreadFactory` hoặc `ExecutorService` thường đơn giản hơn.

## 4. `ThreadFactory` và tạo nhiều virtual thread có tên

`factory()` trả về `java.util.concurrent.ThreadFactory`; gọi `newThread(task)` sẽ tạo một virtual thread **chưa start**. Đây là điểm khác với `builder.start(task)`.

Ví dụ độc lập, lưu thành **`VirtualThreadFactoryDemo.java`**:

~~~java
import java.util.concurrent.ThreadFactory;

public class VirtualThreadFactoryDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadFactory factory = Thread.ofVirtual()
                .name("vt-worker-", 1)
                .factory();

        Thread first = factory.newThread(() -> {});
        Thread second = factory.newThread(() -> {});

        System.out.println(first.getName());
        System.out.println(second.getName());
        System.out.println("Chưa chạy: " + (first.getState() == Thread.State.NEW));

        first.start();
        second.start();
        first.join();
        second.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadFactoryDemo.java
java VirtualThreadFactoryDemo
~~~

Kết quả chính xác:

~~~text
vt-worker-1
vt-worker-2
Chưa chạy: true
~~~

`factory.newThread(...)` tạo thread theo cấu hình factory; chính người gọi chịu trách nhiệm `start()` nếu dùng factory trực tiếp. Một factory cũng có thể được truyền cho API nhận `ThreadFactory`, miễn là API đó phù hợp với mô hình tạo thread theo tác vụ.

## 5. Chạy nhiều tác vụ chờ I/O: mô hình một virtual thread cho mỗi tác vụ

Hai API ở đề bài thích hợp để nắm rõ cơ chế tạo thread. Khi chương trình cần trả về kết quả, thu gom lỗi và quản lý vòng đời của **nhiều tác vụ**, Java 21 còn cung cấp `Executors.newVirtualThreadPerTaskExecutor()`. Executor này tạo **một virtual thread mới cho mỗi tác vụ được submit**; không phải pool tái sử dụng virtual thread.

Ví dụ độc lập, lưu thành **`VirtualThreadTasksDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadTasksDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int taskId = i; // mỗi lambda giữ một bản sao riêng
                futures.add(executor.submit(() -> {
                    Thread.sleep(100); // mô phỏng thao tác chờ I/O
                    return "Task " + taskId
                            + ": virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadTasksDemo.java
java VirtualThreadTasksDemo
~~~

Kết quả chính xác:

~~~text
Task 1: virtual=true
Task 2: virtual=true
Task 3: virtual=true
~~~

Điểm cần hiểu:

1. Ba tác vụ có thể chạy **đồng thời**; `Thread.sleep(100)` là giả lập việc chờ, không chứng minh hiệu suất thực tế.
2. Vòng `get()` đọc `Future` theo **thứ tự submit**, vì vậy thứ tự in ra được xác định ngay cả khi thời điểm hoàn thành khác nhau. Nếu tác vụ ném lỗi, `Future.get()` báo `ExecutionException` với nguyên nhân gốc.
3. `try-with-resources` gọi `ExecutorService.close()`, đợi các tác vụ hoàn tất khi thoát scope; không bỏ quên vòng đời các worker.
4. Không nên biến mỗi virtual thread thành một worker tồn tại mãi để nhận nhiều nhiệm vụ. Mô hình được khuyến nghị là **tạo virtual thread mới cho mỗi tác vụ**, và chỉ giới hạn truy cập tài nguyên thực sự khan hiếm.

Ví dụ giới hạn truy cập dịch vụ chỉ cho phép hai yêu cầu đồng thời bằng `Semaphore` (mảnh mã bên trong lớp/phương thức thích hợp):

~~~java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(2);

Runnable job = () -> {
    try {
        permits.acquire();
        try {
            // Thực hiện thao tác I/O giới hạn song song ở đây.
        } finally {
            permits.release();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
};

Thread worker = Thread.startVirtualThread(job);
~~~

Semaphore là cách giới hạn số thao tác I/O đối với một tài nguyên; không cần lập một “virtual-thread pool” chỉ để khống chế concurrency. Ví dụ này có placeholder **diễn giải** trong comment thay vì một thao tác I/O thực và không có stdout cố định.

## 6. Cơ chế chạy và điểm khác với platform thread

Một `Thread` platform truyền thống thường ánh xạ với thread của hệ điều hành; số lượng lớn tạo ra chi phí stack và scheduling đáng kể. Với virtual threads, Java runtime lập lịch rất nhiều virtual thread lên một tập platform thread tương đối nhỏ gọi là **carrier threads**.

Khi một virtual thread đang thực thi, nó có thể được **mount** lên carrier. Khi gặp thao tác chờ được runtime hỗ trợ, ví dụ `Thread.sleep` và nhiều thao tác blocking I/O trong JDK, virtual thread có thể **unmount** để carrier chạy công việc khác. Khi sẵn sàng, virtual thread được lên lịch chạy tiếp, có thể trên carrier khác. Do đó **không** được dựa vào danh tính carrier hoặc giả định mỗi virtual thread có một OS thread riêng.

### Khác biệt về mục đích

| Khía cạnh | Platform thread | Virtual thread |
| --- | --- | --- |
| Tài nguyên tạo thread | Tương đối đắt | Rẻ hơn đáng kể cho nhiều tác vụ |
| Scheduling chủ yếu | Hệ điều hành | Java runtime lập lịch lên carrier |
| Nhiều tác vụ bị chặn I/O | Cần nhiều OS threads, dễ tốn tài nguyên | Thường mở rộng tốt hơn |
| Tác vụ CPU-bound kéo dài | Phù hợp nếu dùng số worker hợp lý | Không tự làm CPU tính toán nhanh hơn |
| API điều khiển | `start`, `join`, `interrupt`... | Dùng chính các API `Thread` quen thuộc |

**Lưu ý theo phiên bản về pinning:** trên JDK **21–23**, virtual thread có thể bị *pinned* vào carrier khi thực hiện thao tác chặn trong vùng `synchronized` hoặc khi chạy native/foreign code, làm giảm khả năng mở rộng. **JDK 24** triển khai JEP 491 để xử lý phần lớn trường hợp pinning liên quan đến `synchronized`. Các thao tác native/foreign và trường hợp chặn không hỗ trợ vẫn cần được đo đạc thực tế. Không nên áp dụng máy móc lời khuyên “thay hết `synchronized` bằng `ReentrantLock`” cho mọi phiên bản.

## 7. Vòng đời, lỗi và hủy công việc

### 7.1. `join()` và daemon

`start()` chỉ lên lịch công việc, không chờ kết quả. `join()` chờ thread được chỉ định kết thúc; phương thức có thể ném `InterruptedException` nếu **thread đang chờ** bị interrupt. Virtual thread là daemon thread: khi không còn non-daemon thread nào giữ JVM sống, virtual thread chưa xong có thể không kịp hoàn tất. Với công việc cần hoàn thành, dùng `join()`, `Future.get()` hoặc một cơ chế quản lý vòng đời tương đương.

Không lạm dụng `join()` **ngay sau từng lần start** trong một vòng lặp nếu muốn các tác vụ chạy đồng thời:

~~~java
// Tuần tự hóa công việc (không có lợi khi đang chờ I/O):
for (Runnable task : tasks) {
    Thread.startVirtualThread(task).join();
}

// Khởi chạy trước, sau đó chờ tất cả:
List<Thread> workers = new ArrayList<>();
for (Runnable task : tasks) {
    workers.add(Thread.startVirtualThread(task));
}
for (Thread worker : workers) {
    worker.join();
}
~~~

Đây là đoạn **mã minh họa**: đặt trong phương thức có `tasks` và import `java.util.List`, `java.util.ArrayList`, đồng thời xử lý `InterruptedException`. Trong hệ thống lớn, executor thường thích hợp hơn để quản lý nhiều tác vụ.

### 7.2. `interrupt()` là yêu cầu hủy hợp tác

`interrupt()` **không** cưỡng bức dừng bytecode đang chạy. Nhiều thao tác chờ như `Thread.sleep` sẽ ném `InterruptedException`, thường đồng thời xóa cờ interrupt; khi không thể xử lý trọn yêu cầu hủy, ta khôi phục cờ với `Thread.currentThread().interrupt()`.

Ví dụ độc lập, lưu thành **`VirtualThreadInterruptDemo.java`**:

~~~java
public class VirtualThreadInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().name("vt-sleeper").start(() -> {
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                System.out.println("Worker nhận yêu cầu interrupt");
                Thread.currentThread().interrupt();
            }
        });

        worker.interrupt();
        worker.join();
        System.out.println("Worker đã dừng");
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadInterruptDemo.java
java VirtualThreadInterruptDemo
~~~

Kết quả chính xác:

~~~text
Worker nhận yêu cầu interrupt
Worker đã dừng
~~~

Vì `interrupt()` được gửi gần như ngay sau `start()`, worker có thể chưa kịp gọi `sleep()`; ngay cả vậy, `sleep()` kiểm tra cờ interrupt và ném ngoại lệ. Không sử dụng `Thread.stop()` để dừng cưỡng bức.

### 7.3. Ngoại lệ trong `Runnable`

Một ngoại lệ không bắt được trong `Runnable` kết thúc virtual thread; `join()` **không tự ném lại** ngoại lệ đó cho caller. Có thể cấu hình `uncaughtExceptionHandler` khi dùng builder, hoặc dùng `Callable` và `Future` nếu caller cần nhận kết quả/lỗi.

Ví dụ độc lập, lưu thành **`VirtualThreadErrorDemo.java`**:

~~~java
public class VirtualThreadErrorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-validate")
                .uncaughtExceptionHandler((thread, error) ->
                        System.out.println(thread.getName()
                                + " báo lỗi: " + error.getMessage()))
                .start(() -> {
                    throw new IllegalStateException("Dữ liệu không hợp lệ");
                });

        worker.join();
        System.out.println("Đã join");
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadErrorDemo.java
java VirtualThreadErrorDemo
~~~

Kết quả chính xác:

~~~text
vt-validate báo lỗi: Dữ liệu không hợp lệ
Đã join
~~~

Handler chỉ được gọi khi có **uncaught exception**; nếu tác vụ tự `catch` ngoại lệ thì handler không chạy. Với executor, ngoại lệ trong tác vụ `submit` thường được ghi vào `Future` và đọc qua `get()`.

## 8. Những hiểu nhầm và lỗi phổ biến

1. **“`Thread.ofVirtual()` đã tạo thread.”** Chưa đúng: đó là builder. Gọi `start(task)` hoặc `unstarted(task)` mới tạo thread.
2. **“`unstarted(task)` tự chạy.”** Sai: thread đang ở `NEW`. Phải gọi `start()` đúng một lần.
3. **“`startVirtualThread(task)` chạy xong trước khi trả về.”** Sai: hàm tạo và start; worker chạy bất đồng bộ với caller.
4. **“Có thể `start()` một `Thread` nhiều lần.”** Sai: gọi lần hai ném `IllegalThreadStateException`.
5. **“Virtual thread làm vòng lặp CPU-bound nhanh hơn.”** Không mặc định; tài nguyên CPU không tăng. Đo throughput và latency của workload thực.
6. **“Virtual threads không chiếm bộ nhớ.”** Sai: stack và trạng thái vẫn tiêu thụ bộ nhớ; tạo quá nhiều tác vụ giữ `ThreadLocal` hoặc dữ liệu lớn sẽ gây áp lực heap/GC.
7. **“Virtual thread cần pool như OS thread.”** Thường không cần. Khởi tạo một thread cho một tác vụ, giới hạn số kết nối hoặc request tới tài nguyên bằng semaphore/connection pool khi cần.
8. **“Dùng `synchronized` luôn khiến virtual thread bị pinned.”** Phụ thuộc phiên bản JDK và vị trí blocking; JDK 24 cải thiện rõ rệt cho monitor, nhưng native/foreign blocking vẫn đáng xem xét.
9. **“`join()` chuyển ngoại lệ từ worker về main.”** Sai: `join()` chỉ đợi. Muốn thu kết quả/lỗi, dùng `Future` hoặc cơ chế truyền lỗi rõ ràng.
10. **“Mọi lời gọi blocking I/O đều tự động hiệu quả với virtual threads.”** Không bảo đảm với từng thư viện/native API; cần thử nghiệm, giám sát, áp dụng timeout, và kiểm tra giới hạn hệ thống.

## 9. Checklist khi áp dụng

- Dùng JDK 21+; chọn `Thread.startVirtualThread` cho tác vụ đơn giản hoặc `Thread.ofVirtual` khi cần tên, handler, tạo chưa chạy hay factory.
- Mỗi tác vụ có điểm kết thúc, timeout/hủy hợp tác và xử lý lỗi; xác định ai sẽ `join`/`close`/lấy `Future`.
- Dùng virtual threads cho workload phần lớn chờ I/O; giữ giới hạn hợp lý cho database connections, socket và các dịch vụ downstream.
- Khi đo hiệu năng, phân biệt throughput, latency, CPU, heap, số connection và các tình huống pinning. Không kết luận từ việc tạo nhiều thread hay `sleep` giả lập.
- Đặt tên worker có ý nghĩa và dùng công cụ quan sát (thread dump/JFR) khi cần xác định trạng thái chờ; nhớ rằng virtual thread mặc định có tên rỗng nếu không đặt.
- Dựa vào semantics của `Thread` (start một lần, interrupt hợp tác, join chờ), đồng thời lưu ý cơ chế carrier có thể khác theo phiên bản JDK.

### Tài liệu chính thức để tra cứu

- [Java SE 21 — `Thread`, `ofVirtual()` và `startVirtualThread()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html).
- [Java SE 21 — `Thread.Builder.OfVirtual`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html).
- [JEP 444 — Virtual Threads (Java 21)](https://openjdk.org/jeps/444).
- [JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491).
