# Luồng nền tảng, nhóm luồng và luồng ảo trong Java (Java 21+)

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **platform thread** (luồng nền tảng), **virtual thread** (luồng ảo) và **`ThreadGroup`** (nhóm luồng), hiểu vì sao nhóm luồng không phải loại luồng thứ ba.
- Tạo, đặt tên, chờ hoàn thành và hủy hợp tác một luồng thông qua `Thread`, `join()`, `interrupt()` hoặc `Future`.
- Giải thích JVM dùng carrier platform threads để thực thi virtual threads và lý do thao tác chờ I/O có thể nhả carrier.
- Dùng `ThreadGroup` đúng phạm vi, không nhầm nó với executor/thread pool hay quota.
- Chọn cách xử lý tải CPU-bound/I/O-bound phù hợp và kiểm tra cách Spring dùng executor.

**Phạm vi phiên bản:** Các ví dụ hoàn chỉnh dùng API **Java 21+**, khi virtual threads trở thành tính năng chính thức theo JEP 444. Pinning do monitor `synchronized` đã được thay đổi từ **Java 24** theo JEP 491; các lưu ý phiên bản được tách riêng ở phần dưới.

## 1. Bản đồ khái niệm: hai loại thread và một cấu trúc nhóm

Một process (tiến trình) JVM có heap chung cho nhiều thread. Mỗi thread có call stack và trạng thái thực thi riêng, nhưng có thể cùng truy cập đối tượng trong heap. Đây là nền tảng của concurrency và cũng là nguồn gốc của race condition, deadlock và nhu cầu đồng bộ hóa.

| Khái niệm | Bản chất | Bên nào lập lịch? | Mục đích |
| --- | --- | --- | --- |
| **Platform thread** | Một đối tượng `java.lang.Thread` gắn với luồng hệ điều hành trong suốt vòng đời | OS lên lịch luồng nền tảng | Chạy các công việc với số lượng luồng OS được kiểm soát |
| **Virtual thread** | Một đối tượng `java.lang.Thread` mà JVM mount lên một platform thread làm carrier khi cần thực thi | JVM lên lịch virtual threads; OS lên lịch carrier | Mở rộng lượng tác vụ đồng thời khi phần lớn thời gian là chờ |
| **`ThreadGroup`** | Đối tượng tổ chức platform threads theo cây nhóm cha–con | **Không lập lịch** | Khả năng nhóm/quan sát mang tính lịch sử; không quản lý task đầy đủ |

**Điểm chính:** Platform thread và virtual thread cùng triển khai giao diện lập trình `Thread`. `ThreadGroup` là đối tượng **gom luồng**, không phải thread, executor, pool hay loại lập lịch thứ ba.

### Vòng đời và trạng thái `Thread.State`

- `NEW`: thread đã được tạo nhưng chưa `start()`.
- `RUNNABLE`: đang chạy hoặc sẵn sàng được chạy theo mô hình trạng thái Java. Không có nghĩa nó chắc chắn đang chiếm CPU ở thời điểm quan sát.
- `BLOCKED`: đang chờ lấy **monitor lock** để vào `synchronized`. Không phải tên chung cho mọi loại chờ I/O.
- `WAITING`: chờ vô thời hạn, ví dụ `join()` không timeout hoặc một số thao tác đợi tín hiệu.
- `TIMED_WAITING`: chờ trong thời hạn, chẳng hạn `Thread.sleep(...)`, `join(timeout)`.
- `TERMINATED`: phương thức thực thi kết thúc. Thread đã kết thúc không thể `start()` lại.

`getState()` trả về snapshot có thể thay đổi ngay lập tức. Không dùng vòng lặp liên tục kiểm tra trạng thái để quyết định luồng nào phải chạy; dùng primitive đồng bộ thích hợp, `Future` hoặc completion notification.

## 2. Platform thread: vòng đời gắn với OS thread

Khi tạo platform thread, JVM dùng một luồng hệ điều hành tương ứng. Hệ điều hành lập lịch chạy, chuyển ngữ cảnh và quản lý stack/tài nguyên của nó. Việc tạo quá nhiều platform threads có thể ngốn bộ nhớ và gặp giới hạn hệ điều hành hoặc JVM. Kích thước và giới hạn chính xác tùy môi trường; không có con số vạn năng.

Ba cách tạo phổ biến:

- `new Thread(runnable, "name")`: cách truyền thống, tạo platform thread.
- `Thread.ofPlatform().name("name").start(runnable)`: builder Java 21 thể hiện rõ ý định.
- `Thread.ofPlatform().factory()`: cung cấp `ThreadFactory` cho thành phần quản lý task.

**`start()` khác `run()`:** `thread.start()` yêu cầu JVM bắt đầu một thread để thực thi `run()`; còn gọi trực tiếp `thread.run()` chỉ chạy phương thức trong **thread hiện tại**. Sau khi gọi `start()`, không thể gọi lại lần thứ hai trên cùng một đối tượng `Thread`.

### Ví dụ 1 — Hai loại thread cùng dùng API `Thread`

Lưu mã vào `ThreadKindsDemo.java`:

~~~java
public class ThreadKindsDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread platform = Thread.ofPlatform()
                .name("platform-demo")
                .start(() -> {
                    Thread current = Thread.currentThread();
                    System.out.println(current.getName()
                            + " | virtual=" + current.isVirtual());
                });
        platform.join();

        Thread virtual = Thread.ofVirtual()
                .name("virtual-demo")
                .start(() -> {
                    Thread current = Thread.currentThread();
                    System.out.println(current.getName()
                            + " | virtual=" + current.isVirtual());
                });
        virtual.join();
    }
}
~~~

Biên dịch và chạy (JDK 21+):

~~~bash
javac ThreadKindsDemo.java
java ThreadKindsDemo
~~~

Kết quả chính xác:

~~~text
platform-demo | virtual=false
virtual-demo | virtual=true
~~~

Ở đây lần `join()` đầu kết thúc trước khi tạo thread thứ hai, nên thứ tự in đã được cố định. Nếu khởi động cả hai rồi mới đợi, các dòng in có thể đảo thứ tự vì lập lịch không xác định.

`join()` đợi **thread cụ thể** kết thúc; `sleep()` chỉ tạm chờ trong thread hiện tại. `sleep()` không tạo quan hệ phối hợp công việc và không tự nhả monitor lock mà thread đang giữ. Đừng dùng `sleep(100)` để “đảm bảo” thread khác đã xong.

### Concurrency và thread safety

Heap chung nghĩa là `counter++` của nhiều thread có thể mất cập nhật, vì đó là chuỗi đọc–tính–ghi, không phải một phép tăng nguyên tử. Dùng `AtomicInteger`, `synchronized`, `Lock` hoặc thiết kế giảm chia sẻ trạng thái theo yêu cầu. `volatile` có tác dụng về visibility và ordering, nhưng không tự biến một chuỗi cập nhật thành nguyên tử. Virtual thread **không chữa được** race condition hay deadlock.

## 3. `ThreadGroup`: cách nhóm luồng kiểu cũ

`java.lang.ThreadGroup` biểu diễn một nhóm có tên và có thể chứa các nhóm con. Các thread group tạo thành cây; nhóm có giới hạn ưu tiên tối đa dành cho các platform threads trong nhóm. API này ra đời từ các phiên bản Java rất sớm, khi việc gom luồng và một số chức năng diagnostic còn dựa trên nhóm. Java SE 21 ghi rõ ứng dụng mới **hiếm khi cần** tạo `ThreadGroup`.

### Ví dụ 2 — Tạo một platform thread trong nhóm

Lưu thành `ThreadGroupDemo.java`:

~~~java
public class ThreadGroupDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadGroup group = new ThreadGroup("workers");

        Thread worker = new Thread(group, () -> {
            Thread current = Thread.currentThread();
            System.out.println(current.getThreadGroup().getName());
        }, "platform-worker");

        worker.start();
        worker.join();
        System.out.println("done");
    }
}
~~~

Chạy:

~~~bash
javac ThreadGroupDemo.java
java ThreadGroupDemo
~~~

Kết quả:

~~~text
workers
done
~~~

Constructor `new Thread(group, runnable, name)` tạo **platform thread** thành viên của `group`. Trong ví dụ, việc đọc tên nhóm được thực hiện khi thread đang sống. Với thread đã kết thúc, `getThreadGroup()` có thể trả về `null`, nên không dùng phương thức này như registry tồn tại mãi.

### Các giới hạn cần nhớ

1. `group.activeCount()` là **ước lượng tức thời** số platform threads còn sống trong nhóm và các nhóm con, **không phải** số task còn xếp hàng hay quota cứng.
2. `group.enumerate(array)` chép các **platform threads** đang sống vào mảng nhưng có race với quá trình thread bắt đầu/kết thúc; nếu mảng nhỏ, kết quả có thể thiếu.
3. `group.interrupt()` là API lịch sử; nó không tự xây dựng cơ chế chờ, timeout, kết quả, hủy có cấu trúc hoặc chính sách xử lý exception.
4. Thread group không phải sandbox hay cơ chế cách ly bảo mật, cũng không điều khiển scheduler của JVM.

Với **virtual thread**, Java runtime cung cấp **một nhóm đặc biệt** khi `getThreadGroup()` được gọi. API tạo virtual thread **không cho gán** `ThreadGroup` tùy chọn; virtual threads **không được tính** bởi `activeCount()`, **không được liệt kê** bởi `enumerate()` và **không bị ngắt** bởi `ThreadGroup.interrupt()`.

Nếu cần nhận task, giới hạn số worker, chờ kết quả và hủy, dùng `ExecutorService`/`Future` hoặc cấu trúc điều phối cấp cao. Nếu cần giới hạn số lời gọi DB/HTTP, đặt giới hạn **ở tài nguyên ấy**, ví dụ connection pool, semaphore hoặc rate limiter. Thread group không thể thay hai vai trò này.

## 4. Virtual thread: nhiều công việc chờ mà không giữ nhiều OS threads

**Virtual threads** được chuẩn hóa từ Java 21 (JEP 444, Project Loom). Chúng đặc biệt hữu ích với mô hình **một task/request một thread**, khi công việc chủ yếu đợi HTTP, JDBC, socket hoặc các thao tác blocking được JVM hỗ trợ.

### Mount, unmount và carrier

Một virtual thread có thể chạy trên carrier platform thread trong một khoảng thời gian, sau đó tạm nhường carrier:

1. Task được khởi tạo dưới dạng virtual thread với đối tượng `Thread` riêng.
2. JVM lên lịch và **mount** virtual thread lên một carrier. OS cấp CPU cho carrier.
3. Khi gặp thao tác blocking có thể unmount, JVM lưu trạng thái tiếp tục của virtual thread và **giải phóng carrier** để nó chạy virtual thread khác.
4. Khi điều kiện chờ đã sẵn sàng, JVM tiếp tục virtual thread, có thể mount lại trên **carrier khác**.

Sơ đồ khái niệm:

~~~text
Virtual A  [CPU] ------- chờ I/O -------- [CPU] --> xong
                   (A unmount)       (A mount lại)
Carrier 1  [A] [Virtual B] [Virtual C] [ ... ]
Carrier 2  [Virtual D] [Virtual E] [ ... ]
~~~

Sơ đồ chỉ diễn đạt sự chia sẻ carrier theo thời gian, không mô phỏng thứ tự lập lịch thực. Bên trong task, `Thread.currentThread()` **vẫn là virtual thread của task**, không phải carrier. Do đó đừng dùng tên carrier làm định danh request.

Số virtual threads có thể lớn hơn rất nhiều số carrier, nhưng chúng **vẫn tốn** bộ nhớ cho task, dữ liệu và stack; hệ thống bên ngoài vẫn có giới hạn file descriptor, kết nối và throughput. Virtual threads chủ yếu giúp **throughput của tải có thời gian chờ**, không trực tiếp giảm latency một truy vấn đơn lẻ hoặc tăng số lõi CPU.

### Tạo virtual thread qua API Java 21

Một số cách thông dụng:

~~~java
Thread direct = Thread.ofVirtual().name("request-1")
        .start(() -> System.out.println(Thread.currentThread().isVirtual()));

Thread simple = Thread.startVirtualThread(() -> {
    System.out.println("a virtual task");
});

ThreadFactory factory = Thread.ofVirtual().name("job-", 0).factory();
~~~

Đoạn này **chỉ minh họa API** (thêm `import java.util.concurrent.ThreadFactory;` vào chương trình chứa nó). Trong chương trình thực tế, cần quản lý kết thúc/hủy và xử lý lỗi của từng task, ví dụ bằng `join()` hoặc `Future`. `Thread.startVirtualThread(runnable)` tạo và bắt đầu virtual thread ngay. Tên của virtual thread có thể rỗng nếu không đặt tường minh.

Virtual threads là **daemon threads**, có độ ưu tiên cố định `Thread.NORM_PRIORITY` và không hỗ trợ cấu hình nhóm tùy chọn. Nếu ứng dụng chỉ còn daemon threads, JVM có thể kết thúc khi một số virtual tasks chưa xong; luôn có chiến lược chờ và quản lý vòng đời.

### Ví dụ 3 — Một virtual thread cho mỗi tác vụ

Lưu thành `VirtualTasksDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualTasksDemo {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> results = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int taskId = i;
                results.add(executor.submit(() -> {
                    Thread.sleep(50); // mô phỏng thời gian chờ
                    return "task-" + taskId
                            + " | virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VirtualTasksDemo.java
java VirtualTasksDemo
~~~

Kết quả:

~~~text
task-1 | virtual=true
task-2 | virtual=true
task-3 | virtual=true
~~~

`newVirtualThreadPerTaskExecutor()` tạo **một virtual thread mới cho mỗi task**; ba task có thể chạy xen kẽ, nhưng `Future.get()` ở vòng lặp thứ hai lấy kết quả theo thứ tự submit, nên stdout đã nêu là xác định. `Thread.sleep(50)` chỉ mô phỏng chờ, **không phải benchmark I/O**. `try-with-resources` đóng executor và đợi task hoàn tất theo hợp đồng `ExecutorService.close()` của Java 21.

**Không pool virtual threads.** Đích thiết kế là tạo thread mới cho task rồi để nó kết thúc. Pool cố định thường dùng để kiểm soát số OS threads trong mô hình platform threads; pool virtual threads lại giới hạn số task một cách gián tiếp, làm phức tạp mô hình và không thay cho bảo vệ tài nguyên. Để chỉ cho phép 20 truy vấn DB đồng thời, dùng **connection pool/semaphore 20 slots**, không tạo virtual thread pool 20 worker.

## 5. Chọn mô hình theo bản chất công việc

| Tình huống | Hướng lựa chọn | Lý do |
| --- | --- | --- |
| Ít tác vụ tính toán dài, tiêu thụ CPU liên tục | Platform thread executor có độ song song kiểm soát | CPU cores giới hạn mức chạy song song thực |
| Nhiều request độc lập, thời gian chờ blocking I/O lớn | Virtual thread per request/task, cộng giới hạn downstream | Carrier có thể phục vụ task khác trong khi một task chờ |
| Cần nhận kết quả/hủy/timeout nhiều task | `ExecutorService`/`Future` và cơ chế hủy phù hợp | Thread group không sở hữu vòng đời task |
| Dịch vụ dùng event loop / Reactive Streams không chặn | Tiếp tục đánh giá trên mô hình non-blocking hiện tại | Virtual threads không tự tăng hiệu quả của pipeline đã không block |
| Backend chỉ cho 20 kết nối DB | Connection pool tối đa theo năng lực backend | 10.000 virtual threads không tạo thêm 10.000 kết nối hợp lệ |

Phân biệt hai phép đo: **throughput** là số task hoàn tất trong một khoảng thời gian; **latency** là thời gian hoàn tất một task. Virtual threads có thể cải thiện throughput của service khi trước đây nhiều OS threads bị giữ trong lúc chờ, nhưng không bảo đảm tăng tốc từng request. Với CPU-bound, nhiều virtual threads hơn **không tạo thêm CPU**.

Khi đánh giá thực tế, đo CPU, heap, GC, p95/p99 latency, throughput, timeout, tỉ lệ lỗi, số task đang chờ và tình trạng connection pool. Một ví dụ `sleep` trên máy cá nhân chỉ giúp học API, không chứng minh hiệu năng production.

## 6. Interruption, hủy hợp tác và bộ nhớ chia sẻ

`Thread.interrupt()` là **tín hiệu yêu cầu dừng**, không phải lệnh giết thread tức thì. Task phải tự kiểm tra cờ interrupted hoặc đi qua những lời gọi nhận interrupt như `sleep()`, `wait()`, `join()` và nhiều thao tác blocking của thư viện. Đây là quy tắc chung cho cả hai loại thread.

Ví dụ đoạn mã **bên trong một `Runnable`**:

~~~java
try {
    Thread.sleep(1_000);
    // tiếp tục công việc
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // khôi phục cờ interrupt
    return; // thoát khỏi tác vụ một cách có chủ đích
}
~~~

Đây là fragment để giải thích xử lý exception, không phải class Java độc lập. Khi `InterruptedException` được ném, cờ interrupted thường đã được xóa; nếu bắt exception ở tầng này và không thể ném tiếp, khôi phục cờ cho tầng cao hơn. Trong phương thức khai báo `throws InterruptedException`, có thể cho exception lan truyền.

Với `Future`, `cancel(true)` yêu cầu interrupt task đang chạy, không bảo đảm dừng ngay một lời gọi native hay I/O không hỗ trợ interruption. Luôn đóng tài nguyên trong `finally`/`try-with-resources`, cấu hình timeout mạng/DB và thiết kế rollback khi bị hủy.

**Happens-before:** Theo Java Memory Model, hành động trước khi gọi `Thread.start()` có quan hệ happens-before với hành động của thread mới; hành động trong thread đã kết thúc có quan hệ happens-before với thread gọi `join()` và nhận biết kết thúc thành công. Nhưng hai thread chạy đồng thời vẫn cần cơ chế đồng bộ đúng đối với trạng thái chia sẻ, chẳng hạn `AtomicInteger` hoặc lock.

## 7. Các giới hạn và bẫy của virtual threads

### 7.1. Pinning theo phiên bản JDK

Virtual thread có thể bị **pinned** vào carrier: khi nó bị chặn, carrier cũng không rảnh để chạy virtual thread khác. Pinning thường tác động khả năng mở rộng dưới tải; bản thân nó không nhất thiết làm kết quả sai.

- **Java 21–23:** thao tác chặn trong vùng `synchronized` hoặc khi có khung chạy native/foreign function có thể pin carrier. Hạn chế giữ monitor qua lời gọi I/O lâu; có thể tách I/O ra khỏi đoạn khóa hoặc cân nhắc `ReentrantLock` với đo đạc phù hợp.
- **Java 24+:** **JEP 491** cho phép xử lý `synchronized` mà không pin carrier như trước. Pinning vẫn có thể phát sinh ở đường native/foreign và những trường hợp thư viện đặc thù. Không suy luận mọi blocking call chắc chắn unmount.

Không thay hàng loạt `synchronized` bằng `ReentrantLock` khi chưa đo. Dù không pin, **lock vẫn tuần tự hóa** truy cập dữ liệu đang được bảo vệ. Phân tích theo JDK và stack của ứng dụng thực.

### 7.2. `ThreadLocal`, logging context và trạng thái request

`ThreadLocal` và `InheritableThreadLocal` hoạt động trên virtual threads, nhưng mỗi task tạo một thread khác nhau, nên dùng `ThreadLocal` để cache tài nguyên lớn theo thread có thể rất tốn bộ nhớ và không mang lại tái sử dụng như platform thread pool. Với MDC, security context hoặc transaction context, cần hiểu cơ chế truyền/cleanup context của framework; tránh cho rằng context được tự động chia sẻ từ carrier. Khi phải tự quản lý, cleanup trong `finally` và `remove()`.

### 7.3. Bảo vệ downstream

Loại bỏ giới hạn về số OS threads có thể làm xuất hiện giới hạn khác sớm hơn: DB connection pool, upstream API, file descriptor, rate limit hoặc hàng đợi. Thiết kế với **timeout, capacity limit, backpressure và retry có kiểm soát** tại ranh giới tài nguyên. Virtual threads không tự áp dụng bất kỳ quota nào.

### 7.4. Theo dõi và chẩn đoán

- `Thread.currentThread().isVirtual()` giúp nhận biết thread đang chạy.
- `ThreadGroup.activeCount()`, `ThreadGroup.enumerate()` và `Thread.getAllStackTraces()` không cho danh sách đầy đủ các virtual threads; tránh dùng để đếm concurrent virtual tasks.
- Trên JVM có hỗ trợ, `jcmd <pid> Thread.dump_to_file -format=json <file>` có thể xuất thread dump dạng JSON; thay `<pid>` và `<file>` bằng thông số thật.
- JDK Flight Recorder (JFR) có sự kiện `jdk.VirtualThreadPinned` để tìm pinning. Trên Java 21 có thể dùng tham số `-Djdk.tracePinnedThreads=full` khi điều tra; ưu tiên công cụ/chỉ dẫn đúng phiên bản đang dùng.

## 8. Liên hệ đến Spring Framework và Spring Boot

Thread Java xuất hiện trong ứng dụng Spring thông qua request-handling, `@Async`, scheduler, listener và executor mà framework sử dụng.

- Với Spring Framework, `@Async` thực hiện công việc qua **executor được cấu hình/chọn**. Annotation không tự chứng minh rằng tác vụ đang chạy trên virtual thread; kiểm tra executor và dùng `Thread.currentThread().isVirtual()` ở điểm thực thi.
- **Spring Boot 3.2+** có hỗ trợ bật virtual threads với **Java 21+** bằng `spring.threads.virtual.enabled=true`. Các thành phần được Boot tự cấu hình và có hỗ trợ sẽ dùng virtual threads tùy phiên bản, nhưng bean `Executor` tùy chỉnh có thể thay đổi lựa chọn executor.
- Virtual threads là daemon; nếu scheduler/task daemon là thành phần giữ vòng đời ứng dụng, cần kiểm tra khả năng JVM thoát. Spring Boot cung cấp `spring.main.keep-alive=true` cho trường hợp thích hợp.
- JDBC/HTTP blocking có thể hưởng lợi nếu workload nhiều chờ, nhưng số kết nối DB và timeout vẫn là ranh giới cứng. Đối với Reactor/WebFlux, không được chặn event loop bừa bãi; virtual threads không tự thay thế thiết kế reactive.

Ví dụ cấu hình **cho ứng dụng Spring Boot hỗ trợ tính năng** trong `application.properties`:

~~~properties
spring.threads.virtual.enabled=true
~~~

Sau khi cấu hình, đo tải và xác minh executor thực tế, đặc biệt khi ứng dụng có custom executor, task scheduler hoặc web server tùy biến. Thuộc tính hợp lệ không đồng nghĩa mọi lời gọi trong ứng dụng đã tự chuyển qua virtual threads.

## 9. Những lỗi thường gặp

1. **Gọi `run()` rồi tưởng có thread mới.** Cần `start()`.
2. **Dùng `sleep()` để đảm bảo thứ tự tác vụ.** Cần `join()`, `Future.get()` hoặc công cụ đồng bộ; `sleep()` cũng không nhả monitor đang giữ.
3. **Coi `ThreadGroup` là thread pool/concurrency limiter.** Nhóm không quản lý hàng đợi task hay quota.
4. **Dùng `ThreadGroup.enumerate()` để đếm virtual threads.** API này bỏ qua virtual threads.
5. **Tin rằng virtual thread làm CPU-bound code nhanh hơn.** Các lõi CPU và thuật toán vẫn là giới hạn.
6. **Tạo virtual thread pool cố định cho mọi tác vụ.** Nên tạo virtual thread mỗi task và giới hạn tài nguyên downstream trực tiếp.
7. **Bỏ qua interruption và timeout.** Hệ thống có thể giữ tài nguyên hoặc để task chờ quá lâu.
8. **Cho rằng pinning của `synchronized` giống nhau trên Java 21 và Java 24+.** JEP 491 đã thay đổi cơ chế.
9. **Giả định `ThreadLocal` trong task virtual tái sử dụng cache như pool platform threads.** Mỗi virtual task dùng thread khác nhau; cần cân nhắc bộ nhớ và cleanup.

## 10. Tự kiểm tra hiểu bài

**Câu 1:** Vì sao `ThreadGroup` không ngang hàng với platform/virtual thread?  
**Đáp án:** Nó là cấu trúc nhóm platform threads, không phải đối tượng thực thi hay scheduler.

**Câu 2:** Một service có hàng nghìn request chờ HTTP phần lớn thời gian nên xem xét gì?  
**Đáp án:** Virtual threads per request/task có thể phù hợp với blocking I/O được JVM hỗ trợ, kèm timeout, giới hạn upstream và đo tải.

**Câu 3:** `RUNNABLE` có nghĩa chắc chắn đang chiếm CPU không?  
**Đáp án:** Không; Java gộp trạng thái sẵn sàng và chạy, việc quan sát chỉ là snapshot.

**Câu 4:** Tại sao virtual threads không làm DB 20 connections phục vụ đồng thời 10.000 truy vấn?  
**Đáp án:** Virtual threads chỉ làm nhẹ chi phí chờ của JVM; connection pool vẫn có đúng tài nguyên cho 20 truy vấn trong cùng một thời điểm.

**Câu 5:** Đã bật `spring.threads.virtual.enabled` nhưng `@Async` vẫn chạy platform thread, kiểm tra gì?  
**Đáp án:** Phiên bản Spring Boot/JDK, executor mà `@Async` chọn, custom `Executor` bean và điểm kiểm chứng `isVirtual()`.

## Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): thiết kế, runtime, API, scalability.
- [Java SE 21 `Thread` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): hành vi và vòng đời của hai loại thread.
- [Java SE 21 `ThreadGroup` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadGroup.html): nhóm luồng và các giới hạn virtual thread.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mount/unmount, blocking, pinning, chẩn đoán.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi từ Java 24.
- [Spring Boot Reference — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads): hỗ trợ và vòng đời trong Spring Boot.
