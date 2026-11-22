# Luồng Java, luồng nền tảng và luồng ảo trong mô hình thực thi JVM

## 1. Mục tiêu và bản đồ khái niệm

Trong Java, `java.lang.Thread` biểu diễn **một luồng thực thi Java** với call stack, trạng thái, danh tính và quy tắc tương tác với Java Memory Model. Tuy nhiên, từ **JDK 21**, đối tượng `Thread` không nhất thiết gắn 1:1 với **một luồng hệ điều hành (OS thread)**: Java có **platform threads** và **virtual threads**. Virtual thread là một luồng Java thực sự, không phải một task callback trá hình, nhưng được HotSpot/JDK **lập lịch lên các platform threads làm carrier** khi cần chạy.

Phân biệt ba mức:

1. **Java thread**: khái niệm lập trình trong `java.lang.Thread`; có `Thread.currentThread()`, stack trace, interrupt, `ThreadLocal`, quyền sở hữu monitor và semantics happens-before.
2. **Platform thread**: một loại `Thread` Java thông thường được JVM nối với **OS thread** theo mô hình 1:1 trong HotSpot; OS scheduler quản lý việc chạy nó trên CPU.
3. **Virtual thread**: một loại `Thread` Java nhẹ, được **JDK scheduler** ánh xạ linh hoạt lên carrier platform threads theo mô hình nhiều virtual threads trên ít platform threads, nhờ cơ chế mount/unmount khi chờ thích hợp.

Sau bài học, bạn sẽ biết cách:
- Tạo, `start`, `join`, `interrupt` platform và virtual threads đúng phiên bản JDK.
- Diễn giải sự khác biệt giữa Java thread, OS thread, carrier, thread pool, executor và task.
- Giải thích vì sao virtual threads phù hợp **nhiều công việc I/O-bound đồng thời**, nhưng không tự làm CPU tính toán nhanh hơn.
- Hiểu sự liên quan giữa blocking APIs, mount/unmount, scheduler, parking, monitor, pinning và thay đổi trong **JDK 24 (JEP 491)**.
- Dùng `ExecutorService` với **một virtual thread mỗi task**, giới hạn kết nối DB/downstream bằng `Semaphore` thay vì pool virtual threads.
- Tránh các lỗi thread safety, shared-state race, `ThreadLocal` footprint, interrupt bị nuốt, blocking native code và resource exhaustion.
- Đọc diagnostics/JFR/thread dumps có ý thức về sự khác nhau giữa Java 17, Java 21 và Java 24+.
- Chạy các chương trình Java 17+ và Java 21+ có đầu ra xác định mà không suy diễn OS-thread mapping không được API cam kết.

## 2. Lịch sử ngắn: Java 17 khác Java 21 và 24 như thế nào?

| JDK | Virtual-thread API và trạng thái | Điểm cần nhớ |
| --- | --- | --- |
| **8–17** | Không có virtual threads chuẩn trong `java.lang.Thread` | `new Thread(...)` tạo platform thread theo HotSpot thông dụng; sử dụng executors/pools để quản lý chi phí |
| **19** | Virtual threads **preview** — **JEP 425** | Yêu cầu cấu hình preview tương ứng khi biên dịch/chạy code dùng preview APIs |
| **20** | Preview lần hai — **JEP 436** | API/chẩn đoán tiếp tục được điều chỉnh; không xem là bản ổn định |
| **21 (LTS)** | Virtual threads **chính thức** — **JEP 444** | Có `Thread.ofVirtual()`, `Thread.startVirtualThread(...)` và `Executors.newVirtualThreadPerTaskExecutor()`; không cần preview |
| **22–23** | Tiếp tục API chính thức | Pinning do `synchronized` + blocking vẫn là điều cần khảo sát trên các bản này |
| **24** | **JEP 491**: đồng bộ monitor không còn gây loại pinning cũ trong trường hợp thông thường | Virtual thread có thể unmount khi blocking trong nhiều vùng `synchronized`; native/foreign constraints vẫn cần lưu ý |
| **25+** | Tiếp tục cải tiến runtime/diagnostics | Kiểm tra đúng vendor/build; không áp quy tắc pinning của JDK 21 cho mọi JDK tương lai |

**Không nhầm** virtual threads (JEP 444) với structured concurrency. `StructuredTaskScope` trải qua các giai đoạn preview/API change trong nhiều release; bài này dùng **Thread và ExecutorService chuẩn ổn định của JDK 21+**, không yêu cầu bật preview để chạy ví dụ.

**Nguồn chính thức:** [JEP 425](https://openjdk.org/jeps/425), [JEP 436](https://openjdk.org/jeps/436), [JEP 444](https://openjdk.org/jeps/444), [JEP 491](https://openjdk.org/jeps/491).

## 3. Platform thread: Java Thread gắn với OS thread

Trên HotSpot, platform thread thường có quan hệ:

~~~text
Java platform Thread object
             |
             | được runtime gắn tới
             v
Operating-system thread
             |
             | OS scheduler
             v
CPU core(s), time slicing, kernel scheduling
~~~

Đặc điểm:
- OS thread có native stack và các cấu trúc quản lý ở hệ điều hành.
- Việc tạo/hủy rất nhiều platform threads có chi phí đáng kể; số lượng đồng thời thường phải hạn chế theo CPU/RAM/OS limits.
- Nếu một platform thread **blocking I/O** hoặc chờ lock, OS thread của nó thường không thể phục vụ request Java khác trong thời gian đó.
- JDK cung cấp `ThreadPoolExecutor` và các factories trong `Executors` để **tái sử dụng platform threads** giữa nhiều tasks.
- Platform thread có thể là **daemon** hoặc **non-daemon**, có priority thuộc phạm vi mà runtime/OS có thể diễn giải; không dùng priority làm phương pháp kiểm soát công bằng hoặc correctness.

Ví dụ mô hình thread pool:

~~~text
10.000 requests chờ I/O
          |
          v
  Blocking request queue
          |
     200 worker platform threads
          |
          v
  Tối đa khoảng 200 tasks được chạy/chờ
  trong các worker ở một thời điểm;
  phần còn lại xếp hàng
~~~

Số 200 chỉ minh họa. Thread pool giúp tránh chi phí tạo OS thread mỗi request, nhưng **không tự giải quyết** giới hạn số request đồng thời khi các worker bị chiếm bởi hoạt động chờ. Nếu I/O latency cao, queue có thể phình và gây tail latency.

### Một JVM luôn chạy nhiều loại threads

Ngoài application platform/virtual threads, HotSpot có thể có GC threads, JIT compiler threads, signal/reference processing, scheduler/carrier threads và các service threads khác. Số OS threads của process không bằng số lần ứng dụng gọi `new Thread`. Các GC/VM internal threads cũng có chi phí CPU/RSS.

## 4. Virtual thread: Java thread không gắn cố định với OS thread

JEP 444 mô tả virtual thread là `java.lang.Thread` **không buộc chặt với một OS thread riêng**. HotSpot/JDK có scheduler riêng, sử dụng các platform threads gọi là **carriers** để chạy virtual threads.

~~~text
Virtual Thread V1  --mount--> Carrier P1 --OS scheduler--> CPU
Virtual Thread V2  --mount--> Carrier P2 --OS scheduler--> CPU
Virtual Thread V3  --WAITING (unmounted, không giữ carrier)
Virtual Thread V4  --WAITING (unmounted, không giữ carrier)
Virtual Thread V5  --RUNNABLE/queued

Một lúc sau:
V1 chờ socket -> unmount khỏi P1
V5 mount lên P1 -> tiếp tục xử lý
V1 I/O sẵn sàng -> được enqueue, có thể mount lên P2
~~~

Sơ đồ khái niệm, **không phải lịch chạy bắt buộc**. Virtual thread có thể sử dụng nhiều carriers khác nhau qua thời gian. Không có API tiêu chuẩn cho phép virtual thread xác định một carrier nhất định để dùng làm identity công việc.

### Mount và unmount

- **Mount:** virtual thread được đặt vào carrier platform thread để thực thi Java code.
- **Unmount:** runtime tạm lưu trạng thái cần thiết để virtual thread dừng ở một thao tác chờ phù hợp, giải phóng carrier cho virtual threads khác.
- **Resume:** khi event/operation hoàn tất, virtual thread được đưa vào scheduler và có thể mount trên carrier khác.

Nhiều I/O operations trong JDK được thiết kế để **đợi theo semantics blocking của Java source**, nhưng nội bộ chuyển sang cơ chế cho phép virtual thread unmount. Người lập trình vẫn viết code tuần tự:

~~~java
String response = httpClient.send(request, responseHandler).body();
~~~

Đây là **snippet minh họa** cần `httpClient`, `request` và `responseHandler` phù hợp. Việc API/blocking có thực sự nhường carrier hay không còn tùy JDK operation, native paths, implementation và phiên bản.

### Virtual threads không phải OS kernel scheduling

JDK scheduler ánh xạ virtual threads tới carriers; **hệ điều hành vẫn lập lịch OS threads lên các CPU cores**. Vì vậy virtual threads không mang lại nhiều CPU cores hơn, không làm network/database xử lý nhanh hơn và không bỏ được giới hạn file descriptors hay connection pools.

### Carrier không phải danh tính thread mà application quan sát

Khi code chạy trong virtual thread:
- `Thread.currentThread()` trả về **virtual thread đang chạy**, không phải carrier.
- `Thread.currentThread().isVirtual()` là **true** (JDK 21+).
- `ThreadLocal` và stack trace thuộc về **logical virtual thread**, không chia sẻ tự động với carrier.
- Virtual thread có thể resume trên carrier khác mà Java logic vẫn là cùng một Thread.

Không nên cache một OS thread ID từ native code rồi giả định nó cố định cho suốt một virtual thread.

## 5. CPU-bound khác I/O-bound: virtual threads không thay định luật tài nguyên

Một service có 1000 requests, mỗi request dành 2 ms để tính toán CPU và 200 ms chờ I/O. Khi có nhiều requests đồng thời, phần chờ có thể được thực hiện hiệu quả bằng virtual threads mà không cần một OS thread bị giữ riêng cho mỗi request. Điều này làm **thread-per-request style** dễ mở rộng hơn.

Nhưng nếu mỗi request chạy 200 ms **thuần CPU**, số công việc CPU đang tiến hành thực tế vẫn bị giới hạn bởi số cores/CPU quota. Một triệu virtual threads có thể chỉ là một triệu tasks cạnh tranh CPU, có thêm scheduling overhead.

Mô hình:

~~~text
I/O-bound requests:
  CPU vài ms -> WAIT I/O lâu -> CPU vài ms
                  |
                  +-- virtual thread unmount, carrier xử lý task khác

CPU-bound requests:
  CPU -> CPU -> CPU -> CPU
  Không có carrier được giải phóng chỉ vì thread là virtual
~~~

**Virtual-thread scheduler không được hứa preempt từng virtual thread sau một timeslice công khai.** Không dựa vào một “1ms quantum” hoặc thứ tự fairness cố định. Thiết kế ứng dụng theo hợp tác với scheduler và blocking APIs thích hợp, tránh các tác vụ CPU rất dài chiếm carriers khi không cần thiết.

### Little's Law là công cụ tư duy, không phải cam kết throughput

Trong một hệ thống ổn định, số tác vụ trung bình đồng thời xấp xỉ **L = λ × W** (throughput × thời gian ở hệ thống). Nếu target 1000 requests/s và mỗi request có latency trung bình 0,2 s, có thể cần khoảng 200 requests cùng hiện diện. Điều này không đồng nghĩa cần đúng 200 OS threads, và cũng không nghĩa chỉ cần 200 connections DB: **thời gian và tài nguyên thực tế** của từng request mới quyết định.

## 6. Java 17+ chạy độc lập: platform threads và join

Trước JDK 21, dùng `new Thread` hoặc `Thread.ofPlatform()`? Phương thức `Thread.ofPlatform()` là API của thế hệ mới, **không được dùng trong bài chạy với Java 17**. Ví dụ tương thích Java 17 dưới đây chỉ dùng `new Thread`.

Tạo file **`PlatformThreads17Demo.java`**:

~~~java
public class PlatformThreads17Demo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counter.increment();
                }
            }, "worker-" + i);
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("threads=" + workers.length);
        System.out.println("total=" + counter.get());
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac --release 17 PlatformThreads17Demo.java
java PlatformThreads17Demo
~~~

**Stdout chính xác** nếu quá trình hoàn tất bình thường:

~~~text
threads=4
total=4000
~~~

Giải thích:
- `start()` yêu cầu một luồng mới chạy `Runnable`; **gọi trực tiếp `run()` không tạo thread mới**.
- Bốn threads đều tăng Counter 1000 lần; `synchronized` ngăn data race trên `value` trong chương trình này.
- `join()` khiến main chờ worker hoàn tất. Thành công từ `join` cũng tạo ra quan hệ happens-before cho những hành động của worker so với thread sau khi join theo Java Memory Model.
- Không dùng `Thread.sleep(...)` để “đợi đủ lâu”: thời gian scheduler không xác định.
- Thread execution order khác nhau giữa runs nhưng **kết quả cuối** vẫn là 4000 nhờ synchronization.

Nếu bỏ `synchronized` và để nhiều threads cùng thực thi `value++`, biểu thức increment gồm nhiều thao tác read/modify/write, có thể làm mất cập nhật. Vấn đề thread safety **không liên quan** việc thread là platform hay virtual.

## 7. Java 21+: tạo platform và virtual thread bằng builder

JDK 21 có cả:
- `Thread.ofPlatform()`: tạo platform thread theo builder.
- `Thread.ofVirtual()`: tạo virtual thread.
- `Thread.startVirtualThread(Runnable)`: tạo và chạy virtual thread trong một lời gọi.
- `Thread.currentThread().isVirtual()`: kiểm tra thread hiện tại.

Tạo file **`ThreadKinds21Demo.java`**:

~~~java
public class ThreadKinds21Demo {
    static String describe(String label) {
        Thread t = Thread.currentThread();
        return label + ": " + t.getName()
                + ", virtual=" + t.isVirtual()
                + ", daemon=" + t.isDaemon();
    }

    public static void main(String[] args)
            throws InterruptedException {
        String[] results = new String[2];

        Thread platform = Thread.ofPlatform()
                .daemon(false)
                .name("platform-1")
                .start(() -> results[0] = describe("platform"));

        Thread virtual = Thread.ofVirtual()
                .name("virtual-1")
                .start(() -> results[1] = describe("virtual"));

        platform.join();
        virtual.join();

        System.out.println(results[0]);
        System.out.println(results[1]);
    }
}
~~~

Biên dịch/chạy bằng JDK **21+**, không phải `javac --release 17`:

~~~bash
javac --release 21 ThreadKinds21Demo.java
java ThreadKinds21Demo
~~~

**Stdout chính xác:**

~~~text
platform: platform-1, virtual=false, daemon=false
virtual: virtual-1, virtual=true, daemon=true
~~~

Các đặc điểm:
- Platform thread trong ví dụ được thiết lập non-daemon tường minh.
- **Virtual threads luôn là daemon threads** theo API JDK 21. Không thể biến chúng thành non-daemon bằng cách gọi `setDaemon(false)`.
- Virtual thread có priority cố định `Thread.NORM_PRIORITY` theo API JDK 21, không thể dùng priority để sắp lịch tác vụ quan trọng hơn.
- Mỗi thread có **tên riêng** trong ví dụ nên output không phụ thuộc default virtual-thread name.
- Thu thập chuỗi vào hai phần tử riêng và chỉ in **sau khi join** loại bỏ tình huống hai threads in xen kẽ, nhờ đó stdout xác định.
- Không in carrier name: nó là implementation detail, có thể thay đổi khi virtual thread unmount/remount.

**Lưu ý:** virtual thread là daemon, nên một ứng dụng chỉ còn các virtual threads đang chạy nhưng main platform thread đã kết thúc có thể **không được giữ sống** chỉ bởi virtual threads. Sử dụng `join()` hoặc lifetime-managed `ExecutorService` trước khi main kết thúc.

## 8. Thread là công việc hay tài nguyên?

Một thread là **nơi thực thi** code; một task là **đơn vị công việc** có thể nộp vào executor.

Trong mô hình truyền thống:

~~~text
Many tasks
   |
   v
ExecutorService thread pool
   |
   +--> reusable platform worker #1
   +--> reusable platform worker #2
   +--> reusable platform worker #3
   ...
~~~

Mục tiêu pooling: reuse **OS/platform threads** tương đối đắt. Với virtual threads, mô hình khuyến nghị là **mỗi task một virtual thread**, không pool các virtual threads:

~~~text
Task 1 --> Virtual Thread 1 ----+
Task 2 --> Virtual Thread 2 ----+--> JDK scheduler --> carrier pool
Task 3 --> Virtual Thread 3 ----+
Task N --> Virtual Thread N ----+
~~~

`Executors.newVirtualThreadPerTaskExecutor()` tạo **một virtual thread mới cho mỗi task được submit**. Nó không giống fixed thread pool với N virtual workers tái sử dụng. Task hoàn tất thì virtual thread cũng hoàn tất.

### Vì sao không pool virtual threads?

Virtual thread thường rẻ hơn platform thread đáng kể về chi phí tạo và stack tài nguyên lúc chờ. Pool virtual threads sẽ đặt **một giới hạn nhân tạo** lên số tasks, làm mất phần lớn lợi ích cho request-per-thread style mà không giúp quản lý tài nguyên downstream một cách tách bạch.

Thay vì giới hạn **số virtual threads**, giới hạn **số đồng thời được sử dụng tài nguyên khan hiếm**:
- Connection pool của database.
- API downstream quotas.
- Số file descriptors/sockets.
- Concurrent writes đến một service.
- Heap/request buffers.
- CPU-bound parallelism.

Sử dụng `Semaphore` hoặc queue/backpressure theo tài nguyên, không tạo fixed virtual-thread pool như biện pháp mặc định.

## 9. Java 21+: ExecutorService một virtual thread mỗi task

Tạo file **`VirtualExecutor21Demo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualExecutor21Demo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 0; i < 5; i++) {
                final int id = i;
                futures.add(executor.submit(() -> {
                    Thread.sleep(10);
                    return "task=" + id
                            + ", virtual="
                            + Thread.currentThread().isVirtual();
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Biên dịch/chạy JDK 21+:

~~~bash
javac --release 21 VirtualExecutor21Demo.java
java VirtualExecutor21Demo
~~~

**Stdout chính xác:**

~~~text
task=0, virtual=true
task=1, virtual=true
task=2, virtual=true
task=3, virtual=true
task=4, virtual=true
~~~

Mặc dù tasks có thể hoàn tất **không theo thứ tự 0→4**, vòng in duyệt `Future` trong danh sách theo thứ tự submit; vì vậy output ổn định. `Thread.sleep(10)` có thể khiến virtual thread unmount trong runtime hỗ trợ, nhưng **mỗi task không được hứa mất đúng 10 ms**, và demo không phải benchmark thông lượng.

Các lưu ý:
- `Future.get()` có thể ném `ExecutionException` nếu task fail; cần xử lý trong ứng dụng thật.
- `try-with-resources` gọi `ExecutorService.close()` để chờ quản lý kết thúc tasks theo contract.
- Việc dùng executor không tự áp timeout/cancellation cho I/O bất tận. Dùng deadlines, `Future.cancel(true)`, interrupt-aware APIs hoặc cơ chế scope thích hợp.
- Với request server, một executor-per-request thường **không cần thiết**; nên quản lý executor lifecycle ở mức phù hợp với application.

## 10. Java 21+: giới hạn downstream bằng Semaphore

Giả sử ứng dụng muốn chạy nhiều virtual threads để đợi I/O, nhưng dịch vụ downstream chỉ cho **hai** hoạt động đồng thời. Không phải giới hạn scheduler của JVM xuống hai carriers; hãy bảo vệ chính tài nguyên đó.

Tạo file **`VirtualSemaphore21Demo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualSemaphore21Demo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Boolean>> futures = new ArrayList<>();

            for (int i = 0; i < 6; i++) {
                futures.add(executor.submit(() -> {
                    permits.acquire();
                    try {
                        int current = active.incrementAndGet();
                        peak.accumulateAndGet(current, Math::max);
                        Thread.sleep(20);
                        return Thread.currentThread().isVirtual();
                    } finally {
                        active.decrementAndGet();
                        permits.release();
                    }
                }));
            }

            int completed = 0;
            boolean allVirtual = true;
            for (Future<Boolean> future : futures) {
                allVirtual &= future.get();
                completed++;
            }

            System.out.println("completed=" + completed);
            System.out.println("allVirtual=" + allVirtual);
            System.out.println("bounded=" + (peak.get() <= 2));
            System.out.println("activeAfter=" + active.get());
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 21 VirtualSemaphore21Demo.java
java VirtualSemaphore21Demo
~~~

**Stdout chính xác:**

~~~text
completed=6
allVirtual=true
bounded=true
activeAfter=0
~~~

Giải thích:
- Có 6 virtual tasks nhưng **tối đa hai** tasks được vào protected section cùng lúc.
- `Semaphore.acquire()` chờ permit; khi virtual thread có thể park/unmount, carrier được dùng cho task khác.
- `try/finally` đảm bảo permit được release dù phần xử lý trong protected section thất bại sau khi acquire thành công.
- `peak` có thể bằng 1 hoặc 2 tùy scheduling; bài chỉ in **bất biến đúng** `peak <= 2`, không đoán nó sẽ bằng chính xác 2.
- Demo giới hạn concurrency, **không làm database tự đáp ứng vô hạn requests**. Trong thực tế nên có timeout/backpressure thay vì để hàng trăm nghìn virtual tasks đợi permit và giữ buffers mãi mãi.

**Điểm tổng quát:** “virtual threads rẻ” khác với “mọi tài nguyên được chúng truy cập đều vô hạn”.

## 11. Thread lifecycle: start, wait, join, interrupt

Các platform/virtual threads đều là Java threads và tuân những semantics cơ bản của `Thread`.

Một sơ đồ khái niệm:

~~~text
NEW
 |
 | start()
 v
RUNNABLE ---------------------+
 |                           |
 +--> WAITING / TIMED_WAITING|
 |       (join, sleep, park, |
 |        blocking operations)|
 |                           |
 +--> BLOCKED (monitor) -----+
 |
 | run() hoàn tất hoặc ném exception uncaught
 v
TERMINATED
~~~

**Thread.State** là trạng thái ở mức Java, không phải một bản sao từng trạng thái scheduler/kernel. `RUNNABLE` có thể bao gồm thread **đang chạy hoặc chờ CPU**; `WAITING` không nói chính xác carrier nào đang bị giữ. Không suy ra pinning chỉ từ `getState()`.

### `start()` khác `run()`

~~~java
Thread t = new Thread(() -> System.out.println("running"));
t.run();   // thực hiện Runnable trên thread hiện tại
// t.start(); // dòng khác: yêu cầu thread riêng
~~~

Đây là snippet minh họa. Nếu gọi `run()` trực tiếp, object Thread mới không chuyển sang started state. Nếu sau đó gọi `start()` một lần, nó sẽ chạy Runnable trong thread mới **lần nữa**. Nếu gọi `start()` hai lần trên cùng một Thread object, lần thứ hai ném `IllegalThreadStateException`.

### `join()` và happens-before

Các writes hoàn tất trong worker trước khi nó kết thúc được thread gọi `join()` quan sát theo happens-before rules sau khi join thành công. Điều này giúp lấy kết quả từ `String[] results` của ví dụ ThreadKinds mà không cần biến từng element thành `volatile`, với điều kiện main thực sự join trước khi đọc và không còn writer khác chạy đồng thời.

### `interrupt()` là tín hiệu hợp tác

Nó không phải “kill thread lập tức”. Một virtual hoặc platform thread bị interrupt:
- Nếu đang chờ qua một số interruptible APIs, API có thể ném `InterruptedException`.
- Code thường nên cleanup, dừng task, hoặc khôi phục interrupt flag nếu không thể truyền exception lên.
- Thread làm tính toán CPU không tự dừng chỉ vì interrupt flag bật nếu code không kiểm tra/cancellation không được propagate.

### Java 21+ demo interrupt

Tạo file **`VirtualInterrupt21Demo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class VirtualInterrupt21Demo {
    public static void main(String[] args) throws Exception {
        AtomicReference<String> result =
                new AtomicReference<>("not-completed");

        Thread worker = Thread.ofVirtual().start(() -> {
            try {
                Thread.sleep(100_000);
                result.set("finished");
            } catch (InterruptedException ex) {
                result.set("interrupted");
                Thread.currentThread().interrupt();
            }
        });

        worker.interrupt();
        worker.join();

        System.out.println("result=" + result.get());
    }
}
~~~

Chạy:

~~~bash
javac --release 21 VirtualInterrupt21Demo.java
java VirtualInterrupt21Demo
~~~

**Stdout chính xác:**

~~~text
result=interrupted
~~~

Trong điều kiện chương trình bình thường, `interrupt()` được gửi gần ngay sau `start()`. Dù worker chưa vào `sleep` hoặc đã vào rồi, khi `sleep` kiểm tra interrupt nó sẽ bị đánh thức/throw, nên branch `catch` gán "interrupted". Không dùng timer để đo việc interrupt “nhanh” bao nhiêu.

## 12. Blocking I/O và pinning: cần phân biệt JDK 21 với JDK 24+

### JDK 21–23: blocking dưới monitor có thể pin carrier

Một tình huống đơn giản:

~~~java
synchronized (lock) {
    socketReadBlocking();
}
~~~

Đây là snippet minh họa cần `lock` và `socketReadBlocking()` thích hợp. Trên JDK 21–23, một virtual thread chạy blocking operation trong vùng `synchronized` có thể **bị pin** vào carrier platform thread. Nếu virtual thread chờ I/O lâu trong khi pinned, **carrier cũng bị chiếm**, giảm khả năng chạy những virtual threads khác.

~~~text
JDK 21-23:
Virtual thread giữ monitor
     |
Blocking I/O trong synchronized
     |
Virtual thread có thể PINNED
     |
Carrier/OS thread bị giữ trong lúc chờ
     |
Giảm khả năng mở rộng khi có nhiều tác vụ như vậy
~~~

Pinning không làm kết quả chương trình Java sai; nó chủ yếu gây vấn đề **throughput/CPU carrier availability**. Không phải mọi `synchronized` block ngắn là vấn đề. Nếu chỉ bảo vệ vài instructions trong memory, thay toàn bộ locks một cách máy móc có thể làm code phức tạp mà không tăng hiệu năng.

### JDK 24+: JEP 491 cải thiện synchronized

**JEP 491: Synchronize Virtual Threads without Pinning** được phát hành trong JDK 24. HotSpot có thể cho virtual threads **unmount ngay cả khi đang giữ monitor hoặc chờ vào monitor**, trong những trường hợp supported, nên **không còn cần đổi `synchronized` sang `ReentrantLock` chỉ để tránh loại pinning monitor cũ**.

Tuy nhiên:
- Pinning hoặc capture của carrier vẫn có thể xảy ra với **native methods/foreign function calls** và một số đường tương tác VM/OS.
- Những I/O operations không phải tất cả đều có cùng khả năng unmount; hành vi phụ thuộc API, OS và JDK.
- Đo pinning trên build thực tế, không kết luận từ cú pháp `synchronized` mà không biết runtime version.

**Một bài học về migration:** lời khuyên “phải thay synchronized bằng ReentrantLock trên virtual threads” có thể đúng khi xử lý blocking hotspots trên **JDK 21**, nhưng đã lỗi thời nếu tuyên bố đó là quy tắc bắt buộc cho **JDK 24+**.

### Native/foreign pinning

Nếu virtual thread gọi native code/JNI/FFM và bị blocking theo con đường không thể unmount, carrier có thể bị pin. JNI critical operations còn có các quy tắc riêng về object references/critical sections. Không giải quyết bằng cách đổi một monitor Java rồi cho rằng native path cũng đã không pin.

### ReentrantLock có vai trò gì?

`java.util.concurrent.locks.ReentrantLock` là một primitive lock có API tryLock, timed acquisition, fairness options, condition variables và thường hoạt động với virtual-thread parking thích hợp. Nó có lợi khi chính semantics đó cần thiết; không tự động nhanh hơn `synchronized` cho mọi workload.

## 13. Carrier scheduler và parallelism

JEP 444 mô tả implementation scheduler dựa trên **work-stealing ForkJoinPool**, phân biệt với `ForkJoinPool.commonPool()`. Scheduler sử dụng platform threads để chạy virtual threads.

Một số system properties HotSpot/JDK có liên quan:

| Property | Vai trò | Lưu ý |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism` | Điều chỉnh target parallelism của scheduler | Mặc định thường gắn với số available processors được JVM nhận diện |
| `jdk.virtualThreadScheduler.maxPoolSize` | Giới hạn max số platform threads scheduler dùng trong một số tình huống compensation | Không dùng nó làm số virtual threads có thể tạo |
| `jdk.tracePinnedThreads` | Hỗ trợ trace pinning trên JDK 21–23 | Hành vi đã thay đổi/không còn hữu ích như cũ sau JEP 491; ưu tiên JFR trên JDK mới |

Ví dụ tùy chỉnh (chỉ khi đã đo):

~~~bash
java -Djdk.virtualThreadScheduler.parallelism=4 MyApp
~~~

Đây là **mẫu lệnh**, cần có class `MyApp` hợp lệ. Nó không tạo ra thêm bốn CPU cores và không đảm bảo chỉ có đúng bốn platform threads trong toàn JVM. GC threads/JIT threads và các đường compensation có thể thêm OS threads.

**Thông thường không nên chỉnh scheduler properties sớm.** Nếu service tắc nghẽn ở DB pool, tăng carrier parallelism sẽ không làm DB có thêm kết nối; còn có thể gây CPU contention. Nếu workload rất CPU-bound, tăng virtual-thread count không thay thế việc quản lý số tác vụ có thể chạy hữu ích cùng lúc.

### Thread.yield() không phải phương pháp chia scheduler công bằng

`Thread.yield()` chỉ là một **gợi ý**; không hứa thread sẽ unmount/remount, nhường một timeslice cụ thể hay một thread khác sẽ chạy ngay. Không dựa vào nó để giải quyết deadlock, starvation hoặc scheduling fairness.

## 14. Stack, heap và chi phí tài nguyên

Platform thread có native stack gắn với OS thread; việc tạo rất nhiều platform threads có thể tiêu hao **virtual address space, native memory và OS scheduling resources**.

Virtual thread có **stack state được JVM quản lý linh hoạt**, khi unmount trạng thái có thể nằm trong các **stack chunk objects** của heap. Nhờ đó nhiều virtual threads đang chờ không yêu cầu mỗi thread giữ một native stack độc lập tương đương platform thread. Tuy nhiên “virtual thread rẻ” **không nghĩa miễn phí**.

Mỗi virtual thread vẫn có:
- Java Thread object và các cấu trúc trạng thái.
- Những stack frames/stack chunks còn sống.
- Captured lambdas, task objects, Futures/executor metadata.
- References tới buffers, request payloads, transactions hoặc connections.
- `ThreadLocal` entries/values của chính virtual thread khi được sử dụng.
- Queuing/timeouts/cancellation bookkeeping.

Một triệu virtual threads chờ mà mỗi task giữ 10 KiB payload có thể giữ **rất nhiều GiB** cho payloads, chưa kể stack/task overhead. Kinh phí memory và số file descriptors/connections vẫn phải được tính.

### ThreadLocal: API vẫn hoạt động, mô hình dùng có thể không phù hợp

JEP 444 bảo đảm virtual threads trong JDK 21 có thể dùng `ThreadLocal`. Tuy nhiên:
- Một `ThreadLocal` có value lớn trên **mỗi** virtual thread sẽ nhân footprint theo số threads.
- Pattern “mỗi worker platform thread có một expensive cache/reusable connection” không còn hợp lý nếu mỗi task được chạy trên **virtual thread ngắn hạn**.
- `ThreadLocal` thuộc **logical virtual thread**, không theo carrier khi thread chuyển mount.
- Dọn thread-local references khi task kết thúc hoặc khi scope không còn cần. Không dùng ThreadLocal như global request cache vô giới hạn.

Cần phân biệt **context propagation** với **resource pooling**. Request ID có thể gắn theo task/thread context phù hợp, nhưng JDBC connection vẫn nên lấy từ **connection pool riêng** có giới hạn.

## 15. Synchronization và Java Memory Model không đổi

Virtual threads **không tự loại bỏ data races**. Những vấn đề vốn có vẫn tồn tại:
- `x++` không nguyên tử.
- `HashMap`/`ArrayList` thông thường không tự thread-safe cho concurrent mutations.
- `volatile` bảo đảm một số quan hệ ordering/visibility, không biến compound increments thành atomic.
- `synchronized` và `Lock` bảo vệ critical sections theo semantics.
- `AtomicInteger`/`LongAdder` có những trade-offs phù hợp update patterns.
- `ExecutorService` không bảo đảm toàn bộ tasks sẽ hoàn thành trước main nếu application bỏ executor lifecycle/cancellation.

Ví dụ:

~~~java
// Snippet: counter dùng chung cần atomicity.
AtomicInteger count = new AtomicInteger();
Runnable job = count::incrementAndGet;
~~~

Đây là code minh họa, cần `import java.util.concurrent.atomic.AtomicInteger;`. Cho dù job chạy trên 100 platform threads hay 100 virtual threads, `AtomicInteger` giúp bảo đảm atomic increments.

### Happens-before tiêu biểu

- Những actions trước khi gọi `Thread.start()` **happens-before** các actions trong thread được start.
- Các actions trong thread **happens-before** một thread khác phát hiện nó đã terminate bằng `join()` thành công.
- Một `volatile write` happens-before một `volatile read` tương ứng sau đó trong synchronization order.
- Monitor unlock happens-before lock tiếp theo trên cùng monitor.
- `ExecutorService/Future` còn có các memory consistency effects theo contract API.

Các quy tắc này áp dụng ở mức **Java Memory Model**, không tùy thuộc thread chạy trên carrier P1 hay P2.

## 16. Deadlock, starvation và quá tải

Virtual threads không chữa deadlock:
- Task A giữ Lock1 rồi chờ Lock2.
- Task B giữ Lock2 rồi chờ Lock1.
- Số virtual threads lớn đến đâu cũng không phá được circular wait.

Virtual threads cũng không tự:
- Tăng số database connections tối đa.
- Tăng throughput của API downstream.
- Tránh transactional locks hoặc DB deadlocks.
- Tránh backpressure/queues không giới hạn.
- Giúp blocking native/unsupported I/O paths nhường OS carrier.
- Tăng CPU cores cho compute-intensive tasks.

**Rủi ro mới:** vì tạo virtual threads rất dễ, ứng dụng có thể nhận **quá nhiều requests/tasks cùng một lúc**, làm exhaustion ở DB, socket limits, heap buffer, external rate limit hoặc semaphore wait queue. Luôn gắn concurrency policy với **downstream capacity và latency SLO**.

### Một ví dụ sai về giới hạn concurrency

~~~java
// Anti-pattern minh họa:
// Executors.newFixedThreadPool(20) vô tình áp trần
// số request chờ I/O xuống 20 worker platform threads.
//
// Không nên tạo "pool 20 virtual threads" để giả lập
// chính giới hạn đó nếu mục tiêu là tối đa hóa khả năng chờ I/O.
~~~

Trong ứng dụng production, có thể cần **request admission control** và bounded queue để giới hạn tổng số request đang được xử lý, kể cả khi sử dụng virtual threads. Semaphore chỉ giải quyết từng tài nguyên cụ thể, không phải chính sách bảo vệ mọi loại overload.

## 17. I/O nào thường nhường carrier, I/O nào cần đo?

| Operation / tình huống | Kỳ vọng chung | Caveat |
| --- | --- | --- |
| `Thread.sleep(...)` trong virtual thread | Có thể unmount/nhường carrier | Không hứa thời gian wake chính xác |
| `BlockingQueue.take()` | Thường park virtual thread, nhường carrier | Kiểm tra đường API/JDK cụ thể |
| `LockSupport.park()` | Có virtual-thread support | Không đồng nghĩa OS thread bị park |
| `Socket`/một số `java.net` blocking I/O | JDK triển khai để virtual thread có thể chờ mà không giữ carrier | Driver/native paths khác cần kiểm chứng |
| `Future.get()` chờ task | Có thể dùng parking phù hợp | Nếu task deadlock, chờ vẫn có thể vô hạn |
| `synchronized` + blocking, JDK 21–23 | Có nguy cơ pin carrier | Di chuyển long blocking khỏi monitor nếu là hotspot |
| `synchronized` + blocking, JDK 24+ | Monitor-related pinning được cải thiện theo JEP 491 | Native/OS limitations khác vẫn còn |
| JNI/FFM native operation chờ | Có thể giữ/pin carrier | Phụ thuộc native call path, không thay chỉ bằng `ReentrantLock` |
| CPU loop dài | Dùng carrier khi tính toán | Không tự tạo thêm CPU capacity |

**Không áp dụng công thức “mọi blocking operation đều unmount”**. Các APIs/versions/hardware/OS implementation khác nhau. Nếu đổi JDK hoặc JDBC driver, đo lại I/O/thread behavior trên target runtime.

## 18. Quan sát virtual threads bằng JFR và jcmd

### JFR events

Java Flight Recorder có các events liên quan virtual threads, tùy version và recording configuration:
- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd`: lifecycle events; thường **không bật mặc định** vì số lượng virtual threads có thể rất lớn.
- `jdk.VirtualThreadPinned`: phát hiện trường hợp virtual thread pin carrier lâu theo threshold được cấu hình.
- `jdk.VirtualThreadSubmitFailed`: vấn đề khi runtime submit/start/unpark virtual thread vào scheduler.
- Các events CPU, allocations, thread park và GC có thể hỗ trợ diễn giải nếu được bật/thu đủ dữ liệu.

Một ứng dụng có virtual threads rất ngắn hạn có thể tạo hàng triệu lifecycle events; bật hết `Start/End` trên production có thể gây overhead. Dùng JFR profiles và chọn events theo câu hỏi điều tra.

### Lệnh chẩn đoán

Từ JDK hỗ trợ, chạy với **PID thật** của Java process:

~~~bash
jcmd PID Thread.dump_to_file -format=json virtual-threads.json
jcmd PID JFR.start name=VThreads settings=profile duration=60s filename=vthreads.jfr
jcmd PID JFR.check
~~~

Cú pháp `PID` ở trên là **placeholder**, phải thay bằng process ID. Command availability, options và shape file có thể khác nhau theo JDK build; dùng `jcmd PID help` để xác nhận. Thread dumps truyền thống có thể không liệt kê mọi virtual thread theo cách bạn quen từ platform threads; format JSON qua lệnh chuyên dụng giúp quan sát virtual threads tốt hơn trên JDK hỗ trợ.

### JDK 21–23 pinning diagnostics

Có thể thử:

~~~bash
java -Djdk.tracePinnedThreads=full MyApp
~~~

Đây là ví dụ có class `MyApp` hợp lệ, chủ yếu hữu ích trên JDK 21–23 cho monitor/native pinning. Với JDK 24+, JEP 491 đã giải quyết loại monitor pinning cũ và thuộc tính này không còn là công cụ đáng dựa vào như trước; ưu tiên **JFR jdk.VirtualThreadPinned** và logging/profiling thích hợp.

**Đừng đọc JFR event count = số requests bị ảnh hưởng.** Một request có thể có nhiều blocking operations; event sampling/threshold làm một số tình huống không được ghi, và pinning không tự đồng nghĩa SLO violation.

## 19. Thread dumps và metrics: số thread đo được chưa chắc đúng mục tiêu

Platform-thread-oriented management APIs, OS tools và thread counts thường **không phản ánh trực tiếp số virtual threads**.

Ví dụ:
- OS utility đếm Linux threads/Windows threads của process chủ yếu nhìn **OS/platform threads**.
- Virtual thread count có thể lớn hơn rất nhiều mà OS thread count không tăng tương ứng.
- `ThreadMXBean` truyền thống tập trung platform threads; không suy ra JVM chỉ có từng ấy logical Java threads.
- Virtual-thread dumps/observability APIs giúp nhìn logical stacks, nhưng xuất file rất lớn có thể tạo overhead.

**Mục tiêu vận hành** không nên là “số virtual threads càng lớn càng tốt” mà là:
- completed requests/s;
- p95/p99 end-to-end latency;
- CPU quota, throttling, RSS, heap occupancy;
- DB connection usage và wait times;
- runnable/blocked/parked task profile;
- pinned events/carrier availability trên JDK liên quan;
- error/timeout/cancellation rate.

Nếu p99 tăng, kết hợp event timeline với tracing, downstream pool metrics và GC/JIT/OS signals. Không mặc định mọi latency spike là pinning.

## 20. So sánh platform thread pools và virtual-thread-per-task

| Thuộc tính | Platform thread / pool | Virtual thread per task |
| --- | --- | --- |
| Quan hệ với OS | 1:1 theo HotSpot thông dụng | N:M qua carriers theo JDK scheduler |
| Tạo thread | Tương đối tốn, thường dùng pool | Nhẹ hơn, tạo mới cho mỗi task |
| Stack | Native thread stack là tài nguyên đáng kể | Stack state được JVM quản lý linh hoạt, có stack chunks trong heap khi unmount |
| Blocking I/O | Worker OS thread thường bị giữ | Nhiều JDK blocking APIs có thể unmount và nhường carrier |
| CPU-bound | Chạy trên OS cores | Vẫn chạy trên OS cores/carriers, không tăng CPU vật lý |
| Tác dụng với thread-per-request | Pool có thể giới hạn số requests đồng thời | Cho phép nhiều tasks chờ mà không cần OS thread riêng |
| Synchronization | `synchronized`, `Lock`, atomic APIs | **Cùng Java Memory Model/locking semantics** |
| ThreadLocal | Thường tái sử dụng theo pool worker | Mỗi virtual thread có context riêng, có thể rất nhiều values |
| Tuning chủ yếu | Pool size, queue, rejection, native stacks | Downstream capacity, task admission, heap footprint, pinning/GC |
| Tình huống phù hợp | CPU-bound fixed workers, legacy libraries hoặc resource control cụ thể | High-concurrency blocking I/O, request-per-task, dễ giữ call stacks/try-catch |
| Nguy cơ | Worker starvation, OS thread exhaustion | Resource overload, pinning/native paths, memory giữ bởi tasks |

**Không chọn virtual threads chỉ vì “số threads nhiều hơn”**. Nếu đang dùng asynchronous non-blocking pipeline hoạt động tốt, chuyển sang virtual threads có thể đơn giản hóa code, nhưng lợi ích CPU/latency/throughput cần được đo. Đừng thay một reactive framework production chỉ từ kết quả toy benchmark.

## 21. Mô hình request-per-thread và mã dễ hiểu hơn callback

Một controller có thể thực hiện:

~~~java
Response handle(Request request) throws Exception {
    User user = users.load(request.userId());
    Price price = pricingService.quote(user);
    auditService.record(request, price);
    return new Response(user, price);
}
~~~

Đây là **pseudo-code minh họa**, cần các class/services phù hợp, không phải program độc lập. Nếu `users.load` và `pricingService.quote` là các blocking operations virtual-thread-friendly, **một virtual thread per request** có thể chờ tự nhiên qua các lời gọi tuần tự mà không giữ carrier suốt thời gian I/O. Bạn vẫn nhận được:
- try/catch/finally truyền thống;
- Java call stack thể hiện chuỗi công việc;
- structured control flow bằng loops/conditions;
- debugger/stack traces gắn với logical thread.

Nhưng lưu ý:
- Một request tuần tự có ba I/O calls vẫn phải đợi thời gian thực hiện của chúng. Virtual threads **không tự song song hóa** những thao tác phụ thuộc nhau.
- Nếu muốn chạy đồng thời nhiều I/O calls độc lập, vẫn cần API orchestration như futures hoặc cấu trúc concurrent khác.
- JDBC driver/HTTP client/file I/O library phải được kiểm tra tương thích và behavior phù hợp.
- Transactions/connections/locks giữ quá lâu vẫn là vấn đề nghiệp vụ.

## 22. Interrupt, timeout, cancellation và shutdown

Trong server có hàng nghìn virtual threads, quản lý lifetime quan trọng hơn chi phí gọi `Thread.ofVirtual()`.

### Sử dụng deadline

Một request không nên block vô hạn khi downstream chết. Sử dụng:
- timeouts của network client và database driver;
- `Future.get(timeout, unit)` khi thích hợp;
- cancellation/`interrupt()` theo contract từng API;
- admission control/backpressure;
- executor shutdown và chờ tasks kết thúc có kiểm soát.

### Ưu tiên không nuốt interrupt

Anti-pattern:

~~~java
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Không làm gì: mất cancellation signal.
}
~~~

Đây là snippet minh họa. Nếu không thể khai báo `throws InterruptedException` cho caller, thường nên cleanup rồi **khôi phục interrupt status** qua `Thread.currentThread().interrupt()`, hoặc kết thúc task đúng ngữ cảnh.

### Không dùng Thread.stop()

`Thread.stop()` là thao tác không an toàn/đã bị loại bỏ khả năng sử dụng ở nhiều API modes hiện đại, không phải cách hủy task đáng tin cậy. Hãy dùng cancellation hợp tác và resource cleanup trong `finally`.

### Virtual threads là daemon, main lifecycle rất quan trọng

Nếu main chỉ gọi `Thread.startVirtualThread(...)` rồi return, chương trình có thể chấm dứt trước khi virtual thread hoàn thành, vì virtual threads luôn daemon. Cần `join()`, `Future.get()` hoặc executor lifecycle để bảo đảm hoàn tất công việc mong muốn.

## 23. Common pitfalls khi chuyển từ thread pool sang virtual threads

| Sai lầm | Hệ quả và cách sửa |
| --- | --- |
| Đổi fixed pool sang triệu virtual threads nhưng DB pool chỉ có 20 connections | Chuyển nút thắt sang connection acquisition/queue; giới hạn bằng semaphore/pool và timeout |
| Pool virtual threads để “tiết kiệm thread” | Giảm concurrency không liên quan tài nguyên thật; dùng virtual-thread-per-task |
| Cho rằng virtual threads làm compute-heavy task nhanh gấp N | CPU cores/CPU quota không tăng; đo workload CPU |
| Dùng `ThreadLocal` để giữ buffer lớn cho mọi request | Tăng per-task heap footprint; xem lại resource sharing/pooling |
| Coi `Thread.currentThread()` là carrier | Đó là logical virtual Thread, không phải OS thread identity |
| Lưu OS thread ID rồi coi cố định sau blocking | Virtual thread có thể resume trên carrier khác |
| Thấy `synchronized` trên JDK 21–23 và bỏ qua pinning | Long blocking trong monitor có thể giữ carrier, cần profiling |
| Luôn thay `synchronized` bằng `ReentrantLock` trên JDK 24+ | JEP 491 xử lý monitor pinning thông thường; thay khóa phải dựa semantics |
| Tin rằng mọi blocking I/O nhường carrier | Native/foreign và một số OS/filesystem operations có exceptions |
| Không join các virtual threads daemon trước khi main kết thúc | Tasks có thể chưa hoàn tất |
| Dùng `Thread.sleep` để đợi result đã “chắc xong” | Race; dùng `join`/`Future.get`/latch |
| Không xử lý `InterruptedException` | Mất cancellation, tasks sống quá lâu |
| Chia sẻ HashMap/ArrayList và tăng `++` không đồng bộ | Data races/lost updates dù thread là virtual |
| Xem OS thread count là số virtual threads | Metrics chủ yếu phản ánh platform/OS threads |
| Xem benchmark “10.000 sleep tasks nhanh” là bằng chứng DB chịu được 10.000 queries | Downstream limits hoàn toàn khác |
| Phát triển code virtual thread rồi build `--release 17` | API chỉ chính thức từ JDK 21; build JDK 21+ |

## 24. Checklist triển khai production

1. **Xác định workload:** CPU-bound, I/O-bound, tỷ lệ waiting và peak concurrency.
2. **Chọn JDK:** ưu tiên release có virtual threads chuẩn (JDK 21+); nếu `synchronized`-related pinning quan trọng, thử **JDK 24+** trên target vendor/build.
3. **Giữ API tuần tự rõ ràng:** dùng virtual thread per task cho logic blocking, không rewrite thành callback chỉ để tiết kiệm OS threads.
4. **Đo tài nguyên khan hiếm:** DB connections, sockets, downstream QPS, heap buffers, connection wait times.
5. **Có admission control:** semaphore, bounded queue, rate limit và per-request deadline khi cần.
6. **Kiểm tra cancellation:** interrupt được propagate/restore, cleanup resources, executor shutdown.
7. **Audit ThreadLocal:** tránh expensive values per virtual thread; context không phụ thuộc carrier affinity.
8. **Audit blocking/native calls:** tìm pinning/long carrier occupancy trên đúng JDK.
9. **Quan sát bằng JFR/thread dumps:** bật event có chủ đích, tránh thu vô hạn mỗi task start/end.
10. **Load test có giới hạn thực:** throughput, p95/p99, CPU quota, RSS, GC, connection pool wait, errors.
11. **Canary rollout:** theo dõi regression và có rollback plan.
12. **Không bỏ qua security/context:** audit request identity, thread-scoped data và lifetime để tránh leak giữa tasks.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Java virtual thread có phải một OS thread mới cho mỗi `Thread.ofVirtual().start(...)` không?

**Đáp án:** Không. Virtual thread là Java Thread được JVM/JDK scheduler mount lên carrier platform thread khi chạy, có thể unmount khi chờ.

**Câu 2.** `Thread.currentThread()` trả gì khi đang chạy trên virtual thread?

**Đáp án:** Virtual thread hiện tại, không trả carrier.

**Câu 3.** Platform thread có thể resume trên OS thread khác bất kỳ như virtual thread không?

**Đáp án:** Theo HotSpot thông thường, platform thread gắn 1:1 với một OS thread, dù OS thread có thể chạy trên nhiều CPU cores qua OS scheduler.

**Câu 4.** Virtual thread có làm một vòng tính toán CPU 10 giây thành một giây trên cùng số cores không?

**Đáp án:** Không. Nó có ích cho concurrency khi blocking, không làm tăng số CPU cores.

**Câu 5.** Virtual threads có chính thức trong Java 17 không?

**Đáp án:** Không. JDK 19/20 có preview, còn JDK 21 mới final theo JEP 444.

**Câu 6.** Virtual threads có phải daemon không?

**Đáp án:** Có, theo Thread API JDK 21, nên cần join/executor lifecycle để không mất task khi main kết thúc.

**Câu 7.** `Executors.newVirtualThreadPerTaskExecutor()` tái sử dụng 10 virtual workers phải không?

**Đáp án:** Không. Nó tạo một virtual thread mới cho mỗi task được submit.

**Câu 8.** Nếu DB chỉ có 10 connections thì nên giới hạn số virtual threads còn đúng 10 không?

**Đáp án:** Không nhất thiết. Giới hạn số operations **dùng DB** qua pool/semaphore; các tasks khác vẫn có thể làm việc/chờ tài nguyên khác.

**Câu 9.** `ThreadLocal` của virtual thread có bị đổi khi chuyển carrier không?

**Đáp án:** Không. Nó thuộc logical virtual thread; carrier's ThreadLocal không phải của virtual thread.

**Câu 10.** `value++` được nhiều virtual threads thực hiện đồng thời có an toàn không?

**Đáp án:** Không. Cần synchronized/atomic/locking theo yêu cầu.

**Câu 11.** Tại sao JDK 21 pinning trong `synchronized` đáng chú ý?

**Đáp án:** Blocking trong monitor có thể giữ carrier OS thread, giảm khả năng mở rộng.

**Câu 12.** JDK 24 có còn yêu cầu thay mọi `synchronized` bằng `ReentrantLock` không?

**Đáp án:** Không. JEP 491 giải quyết monitor-related pinning thông thường; vẫn phải xét native/foreign và tính đúng của synchronization.

**Câu 13.** OS thread count trong task manager có tương đương số virtual threads không?

**Đáp án:** Không. Nhiều virtual threads dùng số carriers giới hạn, nên count của OS khác logical threads.

**Câu 14.** `Thread.interrupt()` có “giết” một virtual thread ngay lập tức không?

**Đáp án:** Không. Nó là tín hiệu hợp tác, có thể làm interruptible blocking API throw hoặc được code kiểm tra.

**Câu 15.** Có được coi `Thread.sleep(10)` là đúng 10 ms và chứng minh scheduler fairness không?

**Đáp án:** Không. Thời gian wake/OS scheduling không được đảm bảo chính xác.

**Câu 16.** Một request thread giữ 1 MiB buffer, có 50.000 requests chờ: có “free” vì dùng virtual threads không?

**Đáp án:** Không. Riêng payloads đã có thể chiếm khoảng 50.000 MiB nếu chúng thực sự còn reachable, chưa tính stacks/metadata.

**Câu 17.** Tool nào giúp điều tra virtual thread pinning?

**Đáp án:** JFR event `jdk.VirtualThreadPinned` và diagnostics phù hợp JDK; trên JDK 21–23 có thể dùng `-Djdk.tracePinnedThreads`. Phải gắn events với latency/CPU thực tế.

**Câu 18.** Vì sao một chương trình in result sau `join()` ổn định dù thread scheduling không cố định?

**Đáp án:** Main chỉ đọc sau khi workers hoàn tất; happens-before từ thread termination/join bảo đảm visibility của kết quả được ghi đúng, nếu không có concurrent conflicting writer khác.

## 26. Sơ đồ tổng kết

~~~text
           JAVA CONCURRENCY PROGRAMMING
                      |
               java.lang.Thread
                      |
              +-------+-------+
              |               |
        PLATFORM THREAD    VIRTUAL THREAD
        HotSpot ~1:1 OS    JDK scheduler M:N
              |               |
          OS Thread       Mount trên CARRIER
              |               |
         OS scheduler     OS platform thread
              |               |
              +-------+-------+
                      |
                    CPU
                      |
           BLOCKING / WAITING?
              |               |
       Platform worker     Virtual thread có thể
       thường bị chiếm     unmount và nhường carrier
                              |
                      JDK 21-23: chú ý
                      pinning dưới synchronized
                              |
                      JDK 24+: JEP 491
                      cải thiện monitor pinning
                              |
                    NATIVE / OS EXCEPTIONS
                              |
                  CAPACITY / CORRECTNESS
              DB pools + Semaphores + timeouts
              JMM + interrupts + joins
              JFR + diagnostics + load testing

Virtual threads giúp tăng khả năng đồng thời cho I/O-bound
nhưng không tạo CPU, RAM hay downstream capacity mới.
~~~

**Kết luận:** cả platform và virtual threads đều là **Java threads thực sự**, chịu cùng các nguyên tắc thread safety và Java Memory Model. Platform threads thường nối trực tiếp với OS threads; virtual threads cho phép nhiều Java task đang chờ I/O dùng chung lượng carriers nhỏ hơn và tiếp tục code tuần tự. Virtual threads phù hợp **thread-per-request cho I/O-bound workloads**; hiệu năng và độ tin cậy vẫn phụ thuộc CPU, heap, native I/O, connection limits, monitoring và cách xử lý cancellation. Đặc biệt, **JDK 21 pinning dưới monitor** và **JDK 24+ JEP 491** phải được diễn giải theo **đúng phiên bản**, không trộn thành một quy tắc bất biến.

## Tài liệu tham khảo chính thức

- [JEP 425 — Virtual Threads (Preview), JDK 19](https://openjdk.org/jeps/425).
- [JEP 436 — Virtual Threads (Second Preview), JDK 20](https://openjdk.org/jeps/436).
- [JEP 444 — Virtual Threads, JDK 21](https://openjdk.org/jeps/444).
- [JEP 491 — Synchronize Virtual Threads without Pinning, JDK 24](https://openjdk.org/jeps/491).
- [Java SE 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html).
- [Java SE 21 — Executors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html).
- [Java SE 21 — ExecutorService API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- [Java SE 21 — Semaphore API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).
- [Java SE 21 — Java Core Libraries: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).
- [JLS Java SE 21 — §17 Threads and Locks / Java Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html).
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 24 — Significant Changes (JEP 491)](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html).
