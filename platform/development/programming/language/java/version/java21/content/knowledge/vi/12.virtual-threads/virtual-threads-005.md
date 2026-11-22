# Khả năng tương thích với Thread API và mã blocking hiện có

Virtual thread trong Java 21 là một đối tượng **java.lang.Thread**. Vì vậy, phần lớn mã ứng dụng đang dùng Thread, Runnable, ExecutorService, ThreadLocal và các API I/O blocking có thể tiếp tục hoạt động khi tác vụ được chạy trên virtual thread. Điểm cần rà soát nằm ở những giả định gắn với platform thread, chẳng hạn thread pool tái sử dụng worker, ThreadLocal dùng làm cache, daemon/priority và các đoạn blocking giữ monitor.

Virtual thread phù hợp với tác vụ có nhiều thời gian chờ I/O hoặc chờ tài nguyên. Nó giúp tăng khả năng xử lý đồng thời; bản thân nó không làm một phép tính CPU chạy nhanh hơn. Khi chuyển mã hiện có, hãy giữ nguyên logic nghiệp vụ trước, sau đó kiểm tra những nơi dựa vào hành vi riêng của platform thread.

## 1. Virtual thread vẫn là Thread

Virtual thread là một instance của Thread và dùng cùng mô hình lập trình cơ bản. Mã đang gọi **Thread.currentThread()**, **Thread.interrupt()**, **Thread.join()**, **Thread.sleep()** hoặc dùng Runnable vẫn có thể chạy trên virtual thread.

~~~java
class ThreadCompatibility {
    static void handleRequest() throws InterruptedException {
        Thread current = Thread.currentThread();

        System.out.println("Thread: " + current);
        System.out.println("Virtual: " + current.isVirtual());

        Thread.sleep(100);
    }
}
~~~

**Thread.currentThread()** trả về đối tượng Thread đại diện cho virtual thread đang thực thi. Phương thức **isVirtual()** cho phép kiểm tra loại thread khi thực sự cần phân nhánh hành vi. Không nên dùng kiểm tra này để viết hai phiên bản logic nghiệp vụ nếu không có yêu cầu kỹ thuật cụ thể.

Có thể tạo virtual thread bằng Thread Builder:

~~~java
class StartVirtualThread {
    static void startTask(Runnable task) {
        Thread thread = Thread.ofVirtual()
                .name("request-handler")
                .start(task);
    }
}
~~~

Hoặc dùng phương thức tiện ích **Thread.startVirtualThread(task)** khi không cần cấu hình thêm. Các constructor công khai như **new Thread(task)** vẫn tạo platform thread; chúng không tự chuyển sang virtual thread.

Nếu một API hiện có yêu cầu **ThreadFactory**, có thể cung cấp factory tạo virtual thread:

~~~java
import java.util.concurrent.ThreadFactory;

class VirtualThreadFactoryExample {
    static ThreadFactory requestThreads() {
        return Thread.ofVirtual()
                .name("request-", 0)
                .factory();
    }
}
~~~

## 2. Dùng ExecutorService để chạy mã blocking hiện có

Một cách chuyển đổi ít ảnh hưởng đến mã hiện có là giữ API **ExecutorService**, thay executor tạo platform thread bằng **Executors.newVirtualThreadPerTaskExecutor()**. Mỗi tác vụ được submit sẽ chạy trên một virtual thread riêng.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

class VirtualThreadExecutorExample {
    static String loadProfile(String userId) throws InterruptedException {
        // Đại diện cho một lời gọi I/O blocking.
        Thread.sleep(100);
        return "Profile của " + userId;
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> result =
                    executor.submit(() -> loadProfile("user-42"));

            System.out.println(result.get());
        }
    }
}
~~~

Các phương thức quen thuộc như **submit()**, **invokeAll()**, **Future.get()**, **shutdown()** và **awaitTermination()** vẫn thuộc hợp đồng ExecutorService. Vì vậy, mã phụ thuộc vào interface này thường có thể chuyển executor mà không phải viết lại cách submit task.

Executor được tạo bởi **newVirtualThreadPerTaskExecutor()** tạo một virtual thread mới cho mỗi task và không giới hạn số thread được tạo. Đây không phải thread pool tái sử dụng worker. Nếu mã hiện tại ép kiểu executor sang ThreadPoolExecutor, đọc queue nội bộ hoặc dựa vào số lượng worker cố định, phần đó cần được thiết kế lại theo hợp đồng mới.

Không tạo pool để tái sử dụng virtual thread. Mô hình khuyến nghị là tạo một virtual thread cho mỗi tác vụ; hãy giới hạn tài nguyên mà tác vụ sử dụng thay vì giới hạn số virtual thread.

## 3. Blocking I/O thường có thể giữ nguyên cách viết

Virtual thread có thể tạm dừng khi gọi một thao tác blocking được runtime hỗ trợ. Khi đó, virtual thread được tháo khỏi carrier platform thread trong lúc chờ; carrier có thể chạy một virtual thread khác. Khi thao tác hoàn tất, runtime lên lịch để virtual thread tiếp tục.

Điều này cho phép giữ phong cách lập trình tuần tự quen thuộc:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

class BlockingClient {
    static String readResponse(String host, int port) throws IOException {
        try (Socket socket = new Socket(host, port);
             BufferedReader reader = new BufferedReader(
                     new InputStreamReader(
                             socket.getInputStream(),
                             StandardCharsets.UTF_8
                     )
             )) {
            return reader.readLine();
        }
    }
}
~~~

Khi **readLine()** phải chờ dữ liệu từ socket, virtual thread có thể nhường carrier để tác vụ khác tiếp tục. Không cần biến mọi lời gọi blocking thành callback hoặc chuỗi CompletableFuture chỉ để đạt khả năng đồng thời cao.

Nhiều API blocking trong JDK, bao gồm các thao tác socket, được tích hợp để phối hợp với virtual thread. Với thư viện bên thứ ba, driver cơ sở dữ liệu hoặc thư viện gọi native code, cần kiểm tra tài liệu và đo kiểm trên workload thực tế. Một lời gọi được quảng cáo là blocking không tự động có nghĩa nó luôn nhường carrier.

## 4. Interrupt và cancellation vẫn dùng mô hình Thread

Virtual thread hỗ trợ interrupt. Mã đang dùng **Thread.interrupt()**, **Thread.isInterrupted()** và **InterruptedException** có thể tiếp tục dùng. Các phương thức blocking như sleep, join và wait phản ứng với interrupt theo hợp đồng của Thread.

~~~java
class InterruptibleTask {
    static void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                performBlockingStep();
            }
        } catch (InterruptedException e) {
            // Khôi phục trạng thái interrupt trước khi kết thúc.
            Thread.currentThread().interrupt();
        }
    }

    private static void performBlockingStep() throws InterruptedException {
        Thread.sleep(500);
    }
}
~~~

Khi bắt InterruptedException, hãy quyết định rõ tác vụ sẽ kết thúc, thử lại hay truyền trạng thái interrupt cho tầng gọi. Không nuốt exception rồi tiếp tục chạy vô hạn; điều đó làm mất tín hiệu hủy tác vụ.

Với ExecutorService, gọi **Future.cancel(true)** yêu cầu interrupt thread đang thực hiện task. Task chỉ dừng đúng cách nếu các đoạn mã của nó phản hồi interrupt hoặc API blocking đang dùng có hợp đồng hủy phù hợp. Interrupt không bảo đảm dừng tức thời một lời gọi native hoặc thư viện không hỗ trợ hủy.

## 5. ThreadLocal vẫn hoạt động, nhưng cách dùng cache có thể thay đổi

Virtual thread hỗ trợ **ThreadLocal** và **InheritableThreadLocal** như platform thread. Mỗi virtual thread có giá trị thread-local riêng; giá trị từ thread tạo có thể được kế thừa khi tạo thread con nếu cấu hình kế thừa được bật.

Tuy nhiên, mô hình một task một virtual thread làm thay đổi giả định thường gặp trong ứng dụng dùng thread pool. Với pool platform thread, một worker có thể xử lý nhiều task nối tiếp nên ThreadLocal đôi khi được dùng để cache đối tượng đắt tiền. Với virtual thread, mỗi task thường nhận thread mới; cache theo ThreadLocal không được tái sử dụng giữa các task và có thể tạo rất nhiều bản sao.

~~~java
class RequestContext {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    static void handle(String requestId) {
        REQUEST_ID.set(requestId);
        try {
            processRequest();
        } finally {
            REQUEST_ID.remove();
        }
    }

    private static void processRequest() {
        System.out.println(REQUEST_ID.get());
    }
}
~~~

ThreadLocal vẫn hữu ích cho dữ liệu ngữ cảnh gắn với một lần thực thi, chẳng hạn request identifier hoặc thông tin phục vụ logging. Với cache dùng chung, hãy cân nhắc cache có phạm vi ứng dụng, object immutable hoặc cơ chế quản lý tài nguyên chuyên dụng thay vì tạo cache trên mỗi virtual thread.

Nếu không muốn virtual thread kế thừa giá trị InheritableThreadLocal từ thread tạo, Thread Builder cung cấp **inheritInheritableThreadLocals(false)**. Hãy xác định rõ dữ liệu context nào cần truyền qua ranh giới tạo thread và tránh kế thừa những object lớn hoặc tham chiếu không cần thiết.

## 6. Daemon và priority có hành vi cố định

Virtual thread luôn là daemon thread và có priority cố định **Thread.NORM_PRIORITY**. Gọi **setDaemon()** không thể biến virtual thread thành non-daemon; gọi **setPriority()** không thay đổi mức ưu tiên của nó.

Điều này quan trọng với ứng dụng cũ dựa vào một worker non-daemon để giữ JVM sống. Nếu chỉ còn virtual thread đang chạy, chúng không ngăn JVM bắt đầu quá trình shutdown. Hãy quản lý vòng đời tác vụ bằng ExecutorService, Future hoặc cơ chế điều phối phù hợp; đừng dựa vào daemon status của virtual thread để giữ tiến trình.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

class ManagedVirtualTasks {
    static void runTasks() throws InterruptedException {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            executor.submit(() -> doWork());
        } // close() chờ các task đã submit hoàn tất
    }

    private static void doWork() {
        System.out.println(Thread.currentThread().isVirtual());
    }
}
~~~

Thread Builder cho phép đặt tên virtual thread để hỗ trợ log và chẩn đoán. Không dùng priority như một cơ chế điều khiển thứ tự xử lý giữa các virtual thread.

## 7. Lưu ý về synchronized và pinning theo phiên bản JDK

Từ góc nhìn đồng bộ hóa, virtual thread vẫn dùng được **synchronized**, monitor và các API khóa hiện có. Pinning là vấn đề về khả năng nhường carrier trong một số tình huống blocking, không phải lỗi về tính đúng đắn của khóa.

**Nếu chạy trên JDK 21:** khi virtual thread thực hiện thao tác blocking trong lúc đang giữ monitor của một synchronized block hoặc method, virtual thread có thể bị pin vào carrier. Carrier không được giải phóng để chạy virtual thread khác trong thời gian đó. Nếu tình huống này xảy ra thường xuyên và kéo dài, throughput có thể giảm.

~~~java
class LegacyMonitor {
    private final Object lock = new Object();

    void updateAndWait() throws InterruptedException {
        synchronized (lock) {
            // Nếu thao tác này blocking lâu trên JDK 21,
            // virtual thread có thể pin carrier trong khi giữ monitor.
            Thread.sleep(500);
        }
    }
}
~~~

Không cần thay tất cả synchronized bằng ReentrantLock. Với JDK 21, chỉ xem xét thay đổi những vùng vừa giữ monitor vừa thực hiện blocking lâu và thường xuyên, sau khi đo được ảnh hưởng. Các đoạn synchronized ngắn chỉ bảo vệ thao tác trong bộ nhớ thường không phải vấn đề.

**Từ JDK 24:** JEP 491 thay đổi cách runtime quản lý monitor để virtual thread có thể nhường carrier khi blocking trong synchronized. Vì vậy, pinning do giữ monitor không còn là giới hạn như trên JDK 21. Native method và foreign function vẫn có thể pin virtual thread khi runtime không thể tháo nó khỏi carrier.

Khi đọc mã hoặc tài liệu cho module Java 21, hãy ghi rõ phiên bản runtime đang xét. Nếu ứng dụng biên dịch theo Java 21 nhưng chạy bằng JDK 24 hoặc mới hơn, hành vi monitor pinning được quyết định bởi runtime mới hơn, không phải chỉ bởi mức source/target.

## 8. Kiểm tra pinning và hành vi của thư viện

Trên JDK 21, có thể dùng JDK Flight Recorder để quan sát event **jdk.VirtualThreadPinned**. Event này giúp tìm những lần virtual thread bị pin lâu; ngưỡng mặc định được tài liệu JDK 21 mô tả là 20 ms. Cần xem stack trace và tần suất, không chỉ nhìn thấy một event đơn lẻ rồi thay toàn bộ cơ chế khóa.

Khi chuyển một thư viện blocking hiện có, hãy kiểm tra:

1. Thư viện dùng API blocking của JDK hay gọi native/foreign function.
2. Lời gọi có thực sự nhường carrier trên runtime đang triển khai hay không.
3. Có giữ synchronized monitor trong lúc chờ I/O hoặc chờ tài nguyên không, đặc biệt khi chạy JDK 21.
4. Cancellation và interrupt có được thư viện xử lý đúng không.
5. ThreadLocal, context class loader hoặc thread identity có được dùng làm cache hay trạng thái dùng chung không.

Debugger vẫn có thể làm việc với virtual thread. JFR và công cụ chẩn đoán JDK hiện hành có hỗ trợ quan sát virtual thread; hãy dùng công cụ phù hợp với phiên bản runtime triển khai.

## 9. Giới hạn concurrency ở tài nguyên thực

Virtual thread cho phép tạo nhiều tác vụ đồng thời, nhưng không làm tăng vô hạn số kết nối cơ sở dữ liệu, socket, file descriptor hoặc quota của dịch vụ bên ngoài. Executor per-task không giới hạn số task được tạo, vì vậy ứng dụng vẫn phải kiểm soát những tài nguyên có giới hạn.

Có thể dùng **Semaphore** để giới hạn số lời gọi đồng thời tới một dịch vụ:

~~~java
import java.util.concurrent.Semaphore;

class DownstreamLimiter {
    private final Semaphore permits = new Semaphore(20);

    String callService() throws InterruptedException {
        permits.acquire();
        try {
            return performBlockingCall();
        } finally {
            permits.release();
        }
    }

    private String performBlockingCall() throws InterruptedException {
        Thread.sleep(100);
        return "done";
    }
}
~~~

Virtual thread chờ permit có thể nhường carrier. Semaphore giới hạn số task được vào vùng gọi dịch vụ tại cùng thời điểm; nó không giới hạn tổng số virtual thread đã được tạo. Với database, hãy cấu hình connection pool theo năng lực database và để các task chờ connection theo chính sách phù hợp.

Đối với công việc CPU-bound kéo dài, virtual thread không tạo thêm năng lực xử lý CPU. Hãy dùng một executor có parallelism phù hợp với số lõi và đo tải thực tế.

## 10. Checklist khi chuyển mã Thread và blocking sang virtual thread

- [ ] Mã dùng Thread API, Runnable và ExecutorService có thể chạy với virtual thread mà không dựa vào chi tiết riêng của platform thread.
- [ ] Dùng Thread.ofVirtual() hoặc Executors.newVirtualThreadPerTaskExecutor(); new Thread(task) vẫn tạo platform thread.
- [ ] Không ép kiểu executor per-task sang ThreadPoolExecutor hoặc dựa vào worker được tái sử dụng.
- [ ] Kiểm tra interrupt, Future.cancel(true) và cách thư viện phản hồi cancellation.
- [ ] Rà soát ThreadLocal cache vì mỗi task thường có một virtual thread riêng.
- [ ] Không dựa vào daemon status hoặc priority để điều phối virtual thread.
- [ ] Kiểm tra blocking trong synchronized khi chạy JDK 21; phân biệt thay đổi JEP 491 từ JDK 24.
- [ ] Kiểm tra thư viện gọi native/foreign code và hành vi I/O trên runtime thật.
- [ ] Giới hạn kết nối và tài nguyên downstream bằng semaphore, connection pool hoặc rate limiter phù hợp.
- [ ] Dùng virtual thread cho tác vụ chủ yếu chờ; dùng executor có giới hạn phù hợp cho CPU-bound work.

## Tài liệu tham khảo

- [Java SE 21: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 API: Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 API: Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [Java SE 21 API: Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Oracle: Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
