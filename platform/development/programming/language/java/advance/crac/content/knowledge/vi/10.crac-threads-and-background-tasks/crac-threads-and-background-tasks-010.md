# Luồng không phải daemon và nguy cơ JVM kết thúc trước khi tạo ảnh

Trong một ứng dụng Java dùng CRaC, tiến trình JVM phải còn tồn tại tại thời điểm hệ thống yêu cầu tạo checkpoint. Nếu JVM đã bắt đầu shutdown, công cụ quản trị không còn một tiến trình đang hoạt động để yêu cầu checkpoint. Một lỗi thường gặp là ứng dụng khởi động tác vụ nền trên daemon thread, sau đó main thread kết thúc. Khi không còn thread không phải daemon nào đang chạy, JVM có thể bắt đầu shutdown dù daemon thread vẫn còn công việc.

Java phân loại thread thành hai nhóm: **daemon thread** và **non-daemon thread**. Non-daemon thread có thể giữ JVM sống khi main thread đã kết thúc. Daemon thread hỗ trợ công việc nền và không ngăn JVM kết thúc. Đây là thuộc tính về vòng đời tiến trình, không phải mức độ ưu tiên, quyền truy cập hay độ tin cậy của công việc.

Đối với CRaC, cần thiết kế vòng đời ứng dụng có chủ đích: tiến trình phải ở trạng thái sống và sẵn sàng nhận yêu cầu checkpoint; các worker phải được điều phối về trạng thái an toàn trước checkpoint; sau restore, những worker đã tạm dừng phải được tiếp tục hoặc tạo lại theo đúng lifecycle. Chỉ đặt một thread thành non-daemon không tự bảo đảm checkpoint thành công, nhưng dùng daemon thread không đúng chỗ có thể khiến JVM thoát trước khi ảnh được tạo.

## 1. JVM kết thúc khi nào?

Thông thường, phương thức main() chạy trên main thread. Main thread là non-daemon. Khi main() kết thúc, main thread kết thúc. Nếu vẫn còn ít nhất một thread non-daemon đang sống, JVM thường tiếp tục chạy. Khi tất cả thread non-daemon đã kết thúc, JVM bắt đầu quá trình shutdown; các daemon thread còn lại không giữ tiến trình sống.

Ví dụ:

~~~java
public class DaemonExitExample {
    public static void main(String[] args) {
        Thread background = new Thread(() -> {
            while (true) {
                System.out.println("Background work");
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "background-worker");

        background.setDaemon(true);
        background.start();

        System.out.println("main is returning");
    }
}
~~~

Sau khi main() trả về, nếu không còn non-daemon thread nào khác, JVM bắt đầu shutdown. Daemon thread có thể bị kết thúc khi JVM dừng; chương trình không được bảo đảm rằng vòng lặp của nó sẽ hoàn tất, finally sẽ chạy đầy đủ hoặc dữ liệu đang đệm sẽ được flush.

Nếu bỏ dòng setDaemon(true), thread mới được tạo từ main thread thường kế thừa trạng thái non-daemon của thread tạo ra nó. Khi đó, background-worker có thể giữ JVM sống sau khi main() kết thúc, miễn là worker vẫn còn chạy.

Điều quan trọng là thread non-daemon chỉ ngăn JVM kết thúc tự nhiên khi nó còn sống. Nếu worker hoàn thành hoặc thoát do lỗi trước khi yêu cầu checkpoint đến, JVM vẫn có thể shutdown. Nếu ứng dụng gọi System.exit(), Runtime.exit(), bị dừng bởi môi trường triển khai hoặc gặp một điều kiện shutdown khác, non-daemon thread cũng không bảo đảm tiến trình tiếp tục tồn tại.

## 2. Daemon thread và non-daemon thread

### 2.1. Non-daemon thread

Non-daemon thread là thread tham gia giữ JVM sống. Đây thường là lựa chọn phù hợp cho công việc mà ứng dụng cần tiếp tục tồn tại để hoàn thành, chẳng hạn:

- Thread phục vụ request hoặc kết nối của server.
- Worker xử lý hàng đợi mà ứng dụng chịu trách nhiệm bảo đảm hoàn tất.
- Scheduler chạy các tác vụ nền bắt buộc.
- Thread điều phối vòng đời ứng dụng và chờ tín hiệu dừng.
- Thành phần giám sát hoặc điều phối mà việc dừng nó đồng nghĩa ứng dụng không còn phục vụ được.

Một non-daemon thread đang chờ trên queue hoặc đang chờ tín hiệu vẫn có thể giữ JVM sống. Vì thế, một executor tạo worker non-daemon có thể khiến chương trình không thoát dù không còn task đang chạy.

### 2.2. Daemon thread

Daemon thread là thread hỗ trợ, không được dùng làm lý do duy nhất để JVM tiếp tục sống. Ví dụ thường gặp gồm một số thread dọn dẹp, giám sát hoặc tác vụ có thể bỏ qua khi tiến trình kết thúc.

Daemon thread phù hợp khi:

- Công việc chỉ có giá trị trong lúc ứng dụng đang phục vụ.
- Công việc có thể được tạo lại từ nguồn dữ liệu bền vững.
- Việc kết thúc đột ngột khi JVM shutdown không làm mất dữ liệu nghiệp vụ.
- Ứng dụng có một thành phần non-daemon khác quản lý vòng đời tiến trình.

Không nên đánh dấu daemon cho worker đang giữ công việc chưa lưu bền vững, đang xử lý thông điệp chưa acknowledgment hoặc đang ghi dữ liệu quan trọng. Khi JVM shutdown, daemon thread không được bảo đảm có thời gian hoàn tất.

### 2.3. So sánh

| Đặc điểm | Non-daemon | Daemon |
|---|---|---|
| Có giữ JVM sống khi main thread kết thúc? | Có, nếu thread vẫn còn sống và JVM chưa bị yêu cầu shutdown rõ ràng | Không |
| Có thể bị bỏ dở khi JVM kết thúc? | Có thể bị dừng khi shutdown hoàn tất; cần cơ chế graceful shutdown | Có thể bị kết thúc mà không hoàn tất công việc |
| Thường dùng cho | Server, worker bắt buộc, lifecycle thread | Công việc hỗ trợ, có thể tái tạo hoặc bỏ qua |
| Có bảo đảm checkpoint thành công? | Không | Không |
| Có cần quản lý shutdown? | Có, để không giữ JVM sống vô hạn | Có, để không mất công việc hoặc tài nguyên |

Daemon không có nghĩa là thread chạy ở mức ưu tiên thấp. Non-daemon cũng không có nghĩa là thread được ưu tiên CPU cao hơn. Thuộc tính này chỉ ảnh hưởng tới quy tắc JVM xác định thời điểm bắt đầu shutdown tự nhiên.

## 3. Cách đặt daemon status

Với Thread thông thường, có thể đặt trạng thái bằng setDaemon(boolean). Phải gọi trước start():

~~~java
Thread worker = new Thread(() -> processJobs(), "job-worker");
worker.setDaemon(false);
worker.start();
~~~

Nếu gọi setDaemon() sau start(), Java ném IllegalThreadStateException. Không thể thay đổi daemon status của một thread đang chạy.

Thread mới mặc định kế thừa daemon status từ thread tạo ra nó. Vì vậy, một thread được tạo từ daemon thread có thể cũng là daemon nếu không đặt lại trạng thái. Nếu daemon status có ý nghĩa với vòng đời ứng dụng, hãy cấu hình tường minh thay vì dựa vào thread cha.

Ví dụ:

~~~java
Thread parent = new Thread(() -> {
    Thread child = new Thread(() -> runBackgroundTask());
    // Child kế thừa daemon status của parent.
    child.start();
}, "parent-worker");

parent.setDaemon(true);
parent.start();
~~~

Trong ví dụ này, child được tạo bên trong daemon parent nên mặc định cũng là daemon. Nếu child phải giữ JVM sống, cần đặt child.setDaemon(false) trước khi start().

Một số factory có chính sách riêng. Chẳng hạn, Executors.defaultThreadFactory() tạo worker non-daemon. Vì thế, không nên suy luận daemon status chỉ từ thread tạo executor; hãy kiểm tra thread factory đang dùng hoặc cấu hình tường minh.

## 4. Vì sao daemon thread có thể làm JVM thoát trước checkpoint?

Quy trình checkpoint cần một JVM đang tồn tại. Tùy cách triển khai, yêu cầu checkpoint có thể được gửi từ công cụ quản trị, script, bộ điều phối hoặc chính ứng dụng. Dù điểm kích hoạt ở đâu, nếu JVM đã shutdown thì yêu cầu không còn một tiến trình mục tiêu đang chạy để xử lý.

Một tình huống dễ gặp:

1. main() khởi tạo một worker daemon.
2. Worker bắt đầu xử lý tác vụ nền.
3. main() trả về.
4. Không còn non-daemon thread nào khác.
5. JVM bắt đầu shutdown và daemon worker có thể bị kết thúc.
6. Công cụ tạo checkpoint chạy sau đó nhưng tiến trình đã biến mất.

Sơ đồ:

~~~mermaid
flowchart TD
    A[JVM khởi động] --> B[main tạo daemon worker]
    B --> C[worker bắt đầu chạy]
    C --> D[main kết thúc]
    D --> E{Còn non-daemon thread?}
    E -->|Không| F[JVM bắt đầu shutdown]
    F --> G[Daemon worker bị kết thúc]
    G --> H[Không còn JVM để checkpoint]
    E -->|Có| I[JVM tiếp tục tồn tại]
    I --> J[Có thể nhận yêu cầu checkpoint]
~~~

Vấn đề không nằm ở việc daemon thread không thể được checkpoint. Vấn đề là daemon thread không giữ tiến trình sống. Nếu ứng dụng không có thành phần non-daemon phù hợp hoặc main thread không chờ lifecycle, JVM có thể kết thúc trước khi quy trình tạo ảnh được gọi.

### 4.1. Một ví dụ lỗi

~~~java
public final class EarlyExitApp {
    public static void main(String[] args) {
        Thread preparation = new Thread(() -> {
            prepareApplicationState();
            System.out.println("Preparation finished");
        }, "checkpoint-preparation");

        preparation.setDaemon(true);
        preparation.start();
        // main kết thúc ngay sau khi start worker.
    }

    private static void prepareApplicationState() {
        try {
            Thread.sleep(10_000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Nếu không có thread non-daemon nào khác, JVM có thể bắt đầu shutdown ngay sau khi main() kết thúc. Worker có thể không hoàn thành prepareApplicationState(). Nếu quy trình tạo checkpoint dự kiến chạy sau khi ứng dụng chuẩn bị xong, nó sẽ không còn tiến trình để thao tác.

### 4.2. Worker non-daemon cũng có thể kết thúc quá sớm

Chuyển worker sang non-daemon chỉ giúp JVM tiếp tục chạy trong khi worker còn sống. Nếu worker chỉ thực hiện một lần chuẩn bị rồi thoát, và main thread đã kết thúc, JVM vẫn có thể shutdown ngay sau đó.

Ví dụ:

~~~java
Thread preparation = new Thread(() -> {
    prepareApplicationState();
}, "one-shot-preparation");

preparation.setDaemon(false);
preparation.start();
// Khi preparation kết thúc, JVM có thể shutdown nếu không còn non-daemon thread.
~~~

Nếu cần giữ JVM sống sau bước chuẩn bị, ứng dụng phải có một lifecycle thread, server thread hoặc cơ chế chờ tín hiệu checkpoint/dừng. Không nên xem một tác vụ ngắn hạn là cơ chế giữ tiến trình tồn tại.

## 5. Thread trong Executor và các API bất đồng bộ

Không phải mọi worker đều được tạo bằng new Thread() trực tiếp. Các API concurrency có thể chọn daemon policy khác nhau.

### 5.1. Executors.newSingleThreadExecutor và thread pool

Các factory phổ biến như newSingleThreadExecutor(), newFixedThreadPool() và newScheduledThreadPool() mặc định sử dụng Executors.defaultThreadFactory(). Worker được tạo bởi factory mặc định là non-daemon.

Điều đó có nghĩa một executor có thể giữ JVM sống ngay cả khi main() đã kết thúc:

~~~java
ExecutorService executor =
        Executors.newSingleThreadExecutor();

executor.submit(() -> {
    System.out.println("Background task");
});

// Không gọi executor.shutdown().
// Worker non-daemon có thể tiếp tục sống và giữ JVM tồn tại.
~~~

Thread pool có thể giữ worker chờ task mới trong queue. Nếu ứng dụng không gọi shutdown() hoặc không có cơ chế quản lý lifecycle tương đương, JVM có thể không kết thúc tự nhiên. Trong môi trường CRaC, điều này có thể giúp JVM vẫn tồn tại để nhận checkpoint, nhưng cũng có thể khiến shutdown hoặc checkpoint bị treo nếu executor không được dừng đúng cách.

### 5.2. ScheduledExecutorService

ScheduledExecutorService tạo worker theo thread factory. Với factory mặc định, worker là non-daemon. Một lịch chạy định kỳ có thể giữ JVM sống lâu dài:

~~~java
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(1);

scheduler.scheduleAtFixedRate(
        () -> refreshCache(),
        0,
        30,
        TimeUnit.SECONDS
);
~~~

Nếu scheduler phải tiếp tục sau restore, hãy quản lý nó như một resource. Trước checkpoint, dừng lịch nhận task mới và xử lý task đang chạy theo chính sách. Sau restore, đăng ký lại lịch phù hợp với thời gian hiện tại. Không nên giả định các lần chạy bị bỏ lỡ trong lúc JVM dừng sẽ tự động được thực thi đúng như mong muốn.

### 5.3. CompletableFuture và common pool

Các lời gọi bất đồng bộ không truyền Executor, ví dụ CompletableFuture.runAsync(task), thường dùng ForkJoinPool.commonPool() khi môi trường có thể sử dụng pool này. Worker của common pool thường là daemon thread. Do đó, việc chỉ gửi một CompletableFuture không bảo đảm JVM sẽ sống cho tới khi task hoàn tất.

Ví dụ:

~~~java
public static void main(String[] args) {
    CompletableFuture.runAsync(() -> {
        performPreparation();
    });
    // Không có await/join và không có non-daemon lifecycle thread.
}
~~~

Nếu main() kết thúc và không còn non-daemon thread khác, JVM có thể shutdown trước khi future hoàn tất. Nếu kết quả của tác vụ là bắt buộc, hãy chờ bằng join()/get() hoặc dùng một executor có lifecycle được quản lý:

~~~java
CompletableFuture<Void> preparation =
        CompletableFuture.runAsync(
                () -> performPreparation(),
                managedExecutor
        );

preparation.join();
~~~

Việc join chỉ bảo đảm main thread chờ tác vụ đó hoàn thành. Nó không giữ ứng dụng sống sau khi tác vụ kết thúc. Nếu cần tiếp tục chờ checkpoint, ứng dụng phải tiếp tục ở trạng thái phục vụ hoặc chờ tín hiệu theo lifecycle riêng.

### 5.4. Virtual thread

Virtual thread trong các JDK hỗ trợ virtual threads là daemon thread. Chúng không giữ JVM sống khi tất cả non-daemon thread đã kết thúc. Một ứng dụng tạo virtual thread để thực hiện công việc nền rồi để main() trả về có thể gặp cùng rủi ro: tác vụ chưa xong nhưng JVM đã bắt đầu shutdown.

Virtual thread phù hợp để tổ chức nhiều tác vụ đồng thời, nhưng vòng đời ứng dụng vẫn cần được quản lý bởi main thread, server hoặc một thành phần non-daemon khác. Đừng dùng số lượng virtual thread đang tồn tại làm bằng chứng rằng JVM sẽ tiếp tục sống.

### 5.5. Bảng so sánh nhanh

| Cách tạo công việc | Daemon status thường gặp | Điều cần lưu ý |
|---|---|---|
| new Thread() từ main thread | Kế thừa non-daemon của main | Đặt tường minh nếu thread được tạo từ nhiều ngữ cảnh |
| Executors.newSingleThreadExecutor() | Worker mặc định non-daemon | Gọi shutdown và quản lý lifecycle |
| Executors.newFixedThreadPool() | Worker mặc định non-daemon | Pool có thể giữ JVM sống khi rảnh |
| Executors.newScheduledThreadPool() | Worker mặc định non-daemon | Hủy lịch và tính lại thời gian sau restore |
| CompletableFuture.runAsync() không truyền executor | Thường dùng common pool với daemon worker | Dùng join/get hoặc executor được quản lý nếu công việc bắt buộc |
| ForkJoinPool.commonPool() | Worker mặc định daemon | Không dùng nó làm cơ chế giữ JVM sống |
| Thread.ofVirtual().start() | Virtual thread là daemon | Cần lifecycle thread khác giữ ứng dụng sống |

Daemon policy có thể khác khi ứng dụng cung cấp ThreadFactory tùy chỉnh hoặc thư viện tạo thread riêng. Hãy xác minh chính sách của JDK và thư viện thực tế thay vì chỉ dựa vào tên API.

## 6. Giữ JVM sống bằng lifecycle rõ ràng

Ứng dụng cần tồn tại để nhận checkpoint phải có một cơ chế vòng đời rõ ràng. Những cách thường dùng:

- Main thread tiếp tục chờ trong vòng đời server.
- Framework ứng dụng giữ main thread trong trạng thái chạy cho tới khi nhận tín hiệu dừng.
- Server hoặc listener có non-daemon thread phục vụ kết nối.
- Một lifecycle coordinator chờ trạng thái dừng hoặc lệnh quản trị.
- Một worker non-daemon chạy liên tục nếu chính worker đó là thành phần phục vụ bắt buộc.

Không nên tạo một thread rỗng chỉ để giữ JVM sống mà không có trách nhiệm lifecycle. Một thread như vậy có thể khiến ứng dụng không thoát khi cần, che giấu lỗi shutdown và làm checkpoint bị treo do nó không được điều phối.

### 6.1. Main thread chờ lifecycle

Ví dụ dưới đây mô tả một ứng dụng có lifecycle coordinator. Thành phần quản trị gọi requestStop() khi cần dừng ứng dụng; main thread chờ tín hiệu đó và sau đó đóng executor:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LongLivedApplication implements AutoCloseable {
    private final CountDownLatch stopRequested = new CountDownLatch(1);
    private final AtomicBoolean running = new AtomicBoolean(true);
    private final BlockingQueue<Runnable> jobs = new LinkedBlockingQueue<>();
    private final ExecutorService worker =
            Executors.newSingleThreadExecutor(r -> {
                Thread thread = new Thread(r, "business-worker");
                thread.setDaemon(false);
                return thread;
            });

    public void start() {
        worker.submit(this::runWorker);
    }

    public void awaitStopRequest() throws InterruptedException {
        stopRequested.await();
    }

    // Được gọi bởi lifecycle manager hoặc endpoint quản trị.
    public synchronized void requestStop() {
        running.set(false);
        stopRequested.countDown();
    }

    public synchronized void submit(Runnable job) {
        if (!running.get()) {
            throw new IllegalStateException("Application is stopping");
        }
        jobs.add(job);
    }

    private void runWorker() {
        while ((running.get() || !jobs.isEmpty())
                && !Thread.currentThread().isInterrupted()) {
            try {
                Runnable job = jobs.poll(1, TimeUnit.SECONDS);
                if (job != null) {
                    job.run();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    @Override
    public void close() throws InterruptedException {
        requestStop();
        worker.shutdown();
        if (!worker.awaitTermination(30, TimeUnit.SECONDS)) {
            worker.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try (LongLivedApplication app = new LongLivedApplication()) {
            app.start();
            app.awaitStopRequest();
        }
    }
}
~~~

Trong ví dụ, main thread chờ stopRequested. Vì main thread là non-daemon, JVM vẫn tồn tại ngay cả khi worker tạm thời không có công việc. Executor worker cũng được đặt non-daemon tường minh. Lifecycle manager chịu trách nhiệm gửi yêu cầu dừng và ứng dụng đóng executor có giới hạn thời gian.

Đây là ví dụ cấu trúc, chưa phải một cơ chế xử lý tín hiệu hệ điều hành hoàn chỉnh. Trong ứng dụng server thực tế, framework hoặc container thường đã có lifecycle coordinator, endpoint quản trị và cơ chế graceful shutdown. Hãy tích hợp vào lifecycle có sẵn thay vì tạo thêm một latch không có đường giải phóng.

### 6.2. Dùng server lifecycle

Với ứng dụng web, main thread thường không cần tự viết vòng lặp vô hạn. Server framework sẽ quản lý acceptor, event loop và lifecycle của ứng dụng. Hãy bảo đảm tiến trình được giữ sống bởi cơ chế server chính thức và chỉ dừng khi có lệnh shutdown hợp lệ.

Nếu framework chạy tác vụ nền bằng daemon thread, điều đó không nhất thiết là lỗi khi server chính vẫn có non-daemon thread hoặc main thread được giữ trong lifecycle. Ngược lại, nếu server đã dừng mà chỉ còn daemon task, JVM có thể kết thúc và không còn khả năng nhận checkpoint.

### 6.3. Không dùng shutdown hook làm cơ chế giữ sống

Shutdown hook được gọi sau khi JVM đã bắt đầu shutdown. Hook phù hợp để thực hiện một số công việc cleanup có giới hạn thời gian, nhưng nó không phải cơ chế giữ JVM sống để chờ checkpoint.

Không nên giả định rằng:

- Có shutdown hook nghĩa là JVM sẽ chờ checkpoint.
- Hook có thể ngăn JVM shutdown chỉ bằng cách chờ vô hạn.
- Một hook luôn có đủ thời gian để flush mọi dữ liệu.
- Việc hook chạy đồng nghĩa ảnh checkpoint đã được tạo.

Nếu ứng dụng cần checkpoint theo yêu cầu quản trị, hãy giữ JVM sống trong lifecycle bình thường và thực hiện checkpoint trước khi quy trình shutdown bắt đầu. Shutdown hook chỉ nên hỗ trợ graceful cleanup theo thiết kế của ứng dụng.

## 7. Phối hợp thread với CRaC Resource

Giữ JVM sống là điều kiện cần để nhận checkpoint, nhưng worker đang chạy cũng phải ở trạng thái phù hợp khi checkpoint được thực hiện. Một background thread có thể đang:

- Chờ trên BlockingQueue.
- Đọc hoặc ghi socket.
- Giữ transaction database.
- Giữ lock trong ứng dụng.
- Thực hiện thao tác native hoặc I/O.
- Chờ timer hoặc scheduler.
- Xử lý message nhưng chưa acknowledgment.

CRaC không tự hiểu ý nghĩa nghiệp vụ của những thao tác này. Ứng dụng cần phối hợp worker bằng resource callback hoặc integration được thư viện hỗ trợ.

### 7.1. Trước checkpoint: quiesce và drain

Callback beforeCheckpoint() nên đưa worker về trạng thái an toàn:

1. Ngừng nhận task mới hoặc tạm dừng nguồn phát task.
2. Đánh dấu ứng dụng đang quiescing để các producer không tiếp tục đẩy công việc mới.
3. Chờ các task đang chạy hoàn tất trong thời hạn đã định.
4. Commit hoặc rollback transaction theo quy tắc nghiệp vụ.
5. Xác nhận message đã xử lý bền vững trước acknowledgment.
6. Đóng hoặc giải phóng tài nguyên bên ngoài mà worker đang sử dụng.
7. Đưa worker về trạng thái idle hoặc dừng hẳn nếu thư viện yêu cầu.

Không nên chỉ gọi Thread.sleep() một khoảng thời gian cố định rồi giả định worker đã dừng. Hãy dùng cơ chế đồng bộ như condition, latch, semaphore, queue sentinel hoặc API shutdown/awaitTermination của executor để xác nhận trạng thái thực tế.

### 7.2. Sau restore: resume hoặc tạo lại worker

Callback afterRestore() có thể:

- Khôi phục kết nối và dependency trước.
- Tạo lại scheduler hoặc consumer nếu chúng đã được dừng.
- Đọc lại lịch tác vụ từ nguồn dữ liệu có thẩm quyền.
- Bỏ qua hoặc tính lại các lần chạy bị lỡ theo chính sách nghiệp vụ.
- Khởi động worker sau khi dependency đã sẵn sàng.
- Mở readiness sau khi các thành phần bắt buộc đã hoạt động.

Không khởi động worker trước khi connection pool, broker client hoặc tài nguyên nền tảng sẵn sàng. Nếu callback của nhiều resource có phụ thuộc, thứ tự đăng ký và thứ tự callback cần được thiết kế phù hợp.

### 7.3. Dừng và tạo lại executor

Một số executor không phù hợp để tiếp tục sử dụng sau khi đã shutdown. Nếu callback trước checkpoint gọi shutdown() và executor chuyển sang trạng thái terminated, callback sau restore không thể đơn giản gọi submit() để dùng lại executor đó. Khi đó, resource nên tạo executor mới và lưu tham chiếu mới.

Ví dụ khái niệm:

~~~java
public final class WorkerResource implements Resource {
    private ExecutorService executor;

    private void startWorker() {
        executor = Executors.newSingleThreadExecutor();
        executor.submit(this::runLoop);
    }

    private void stopWorker() throws InterruptedException {
        ExecutorService current = executor;
        executor = null;
        if (current == null) {
            return;
        }

        current.shutdown();
        if (!current.awaitTermination(20, TimeUnit.SECONDS)) {
            current.shutdownNow();
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopWorker();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        startWorker();
    }
}
~~~

Đây là pseudocode về lifecycle; một triển khai đầy đủ phải khai báo imports, constructor đăng ký resource, xử lý trạng thái khởi tạo và đảm bảo runLoop có cơ chế dừng. Cần xác định worker nên được tạm dừng rồi tiếp tục hay dừng và tạo lại. Không thể dùng một mẫu duy nhất cho mọi executor, scheduler và framework.

## 8. Rủi ro khi non-daemon thread không được quản lý

Non-daemon thread giúp JVM không kết thúc quá sớm, nhưng nếu không có shutdown policy, nó có thể tạo ra vấn đề ngược lại.

### 8.1. JVM không thoát sau khi ứng dụng đã hoàn tất

Một executor mặc định có thể giữ worker non-daemon chờ task mới. Nếu main() kết thúc nhưng executor chưa shutdown, JVM vẫn tồn tại. Điều này có thể khiến container không kết thúc, deployment rollout bị treo hoặc script quản trị chờ mãi.

Giải pháp:

- Gọi shutdown() khi ứng dụng dừng.
- Dùng awaitTermination() với timeout.
- Chỉ gọi shutdownNow() khi chính sách cho phép ngắt task.
- Bảo đảm task phản hồi interrupt và không chặn vô hạn ở I/O.
- Đăng ký executor vào lifecycle manager hoặc CRaC Resource phù hợp.

### 8.2. Checkpoint bị trì hoãn vì worker không đạt trạng thái an toàn

Worker non-daemon có thể đang xử lý transaction hoặc chờ I/O lâu. Nếu callback checkpoint chờ worker hoàn tất mà không có timeout, quá trình checkpoint có thể không bao giờ tiến triển.

Hãy đặt deadline cho drain, log rõ worker nào chưa dừng và quyết định có hủy checkpoint hay không. Không nên checkpoint trong lúc một transaction hoặc thao tác ghi quan trọng đang ở trạng thái không xác định.

### 8.3. Worker sống nhưng không còn hữu ích

Một thread có thể còn sống nhưng đã mất kết nối, mất lease hoặc giữ dữ liệu cũ. Non-daemon status chỉ nói rằng thread có thể giữ JVM sống; nó không chứng minh thread khỏe mạnh hay có thể xử lý công việc.

Sau restore, cần kiểm tra dependency và trạng thái nghiệp vụ. Nếu worker giữ distributed lock hoặc lease, phải đăng ký lại và xác minh quyền sở hữu trước khi ghi. Nếu worker dùng cache, cần làm mới dữ liệu có thể đã cũ.

### 8.4. Worker bị block trong native call hoặc I/O

Một worker đang chờ thư viện native hoặc I/O có thể cần xử lý đặc biệt trước checkpoint. Khả năng checkpoint trạng thái thread và tài nguyên native phụ thuộc runtime, nền tảng và thư viện. Không nên giả định mọi điểm chờ đều có thể được khôi phục an toàn.

Hãy kiểm tra khả năng tương thích CRaC của thư viện, dùng timeout cho I/O, và thiết kế callback để dừng hoặc tái tạo phần tài nguyên không thể tiếp tục. Nếu không thể đưa worker về trạng thái an toàn, quy trình nên báo lỗi checkpoint thay vì âm thầm tiếp tục.

## 9. Những tình huống dễ nhầm lẫn

| Tình huống | Kết quả có thể xảy ra | Cách thiết kế |
|---|---|---|
| Main thread kết thúc, chỉ còn daemon worker | JVM bắt đầu shutdown; worker có thể bị dừng trước checkpoint | Giữ lifecycle chính bằng main/server non-daemon thread |
| Main thread kết thúc, worker non-daemon vẫn chạy | JVM tiếp tục tồn tại khi worker còn sống | Bảo đảm worker có shutdown policy và trạng thái an toàn |
| Worker non-daemon hoàn tất trước yêu cầu checkpoint | JVM có thể shutdown nếu không còn non-daemon thread khác | Dùng lifecycle coordinator hoặc server thread tồn tại lâu dài |
| CompletableFuture chạy trên common pool | Worker thường là daemon; tác vụ có thể bị bỏ dở khi JVM shutdown | Chờ kết quả hoặc truyền executor được quản lý |
| Scheduled executor chưa shutdown | Worker non-daemon có thể giữ JVM sống vô hạn | Hủy lịch và đóng scheduler trong lifecycle |
| Virtual thread là công việc nền duy nhất | Virtual thread là daemon nên không giữ JVM sống | Giữ main thread hoặc server lifecycle sống |
| Non-daemon worker đang giữ transaction | JVM sống nhưng checkpoint có thể không an toàn | Drain và hoàn tất/rollback transaction |
| Worker đã bị shutdown trước checkpoint | Tiến trình có thể còn sống nhưng worker không còn hoạt động | Tạo lại worker theo callback sau restore nếu cần |
| Shutdown hook đang chạy | JVM đã bước vào shutdown sequence | Thực hiện checkpoint trước khi shutdown, không dựa vào hook để giữ JVM |

## 10. Quy trình vận hành cho ứng dụng CRaC có tác vụ nền

Một quy trình thực tế có thể chia thành các giai đoạn:

### Khởi động

1. Khởi tạo cấu hình và các dependency cần thiết.
2. Tạo executor, scheduler và consumer với daemon policy có chủ đích.
3. Đăng ký Resource quản lý worker hoặc tài nguyên cần callback.
4. Khởi động worker sau khi dependency sẵn sàng.
5. Giữ main thread hoặc server lifecycle sống để tiến trình có thể nhận checkpoint.
6. Chỉ mở readiness sau khi ứng dụng sẵn sàng.

### Trước checkpoint

1. Đưa ứng dụng sang trạng thái quiescing.
2. Ngừng nhận request và task mới.
3. Drain worker và queue; hoàn tất hoặc rollback transaction.
4. Dừng scheduler hoặc tạm dừng consumer theo chính sách.
5. Đóng tài nguyên bên ngoài và xác nhận worker ở trạng thái an toàn.
6. Cho phép runtime tiếp tục tạo checkpoint khi các resource đã hoàn tất callback.

### Sau restore

1. Tạo lại kết nối và dependency.
2. Làm mới token, session, lease và dữ liệu có thời hạn.
3. Khởi tạo lại executor hoặc scheduler đã shutdown.
4. Đăng ký lại consumer hoặc subscription.
5. Tính lại lịch tác vụ dựa trên thời gian hiện tại.
6. Chuyển ứng dụng về trạng thái phục vụ và mở readiness.

Luồng:

~~~mermaid
flowchart TD
    A[JVM khởi động] --> B[Khởi tạo dependency]
    B --> C[Tạo và đăng ký worker Resource]
    C --> D[Start worker và server lifecycle]
    D --> E[JVM duy trì trạng thái sống]
    E --> F[Nhận yêu cầu checkpoint]
    F --> G[Quiesce và drain task]
    G --> H[Đóng hoặc pause worker resource]
    H --> I[CRaC tạo checkpoint]
    I --> J[Restore JVM]
    J --> K[Tạo lại dependency]
    K --> L[Resume hoặc tạo worker mới]
    L --> M[Readiness và tiếp tục phục vụ]
~~~

## 11. Kiểm thử nguy cơ JVM thoát trước checkpoint

Hãy kiểm thử cả daemon policy lẫn lifecycle của ứng dụng. Một số kịch bản hữu ích:

- Chạy ứng dụng với main() kết thúc ngay sau khi tạo daemon worker; xác nhận tiến trình kết thúc khi không còn non-daemon thread.
- Chạy với worker non-daemon; xác nhận JVM còn sống sau khi main() kết thúc và kết thúc đúng khi worker được dừng.
- Tạo executor mặc định, gửi một task ngắn rồi không shutdown; quan sát worker có giữ tiến trình sống sau khi task hoàn tất không.
- Dùng CompletableFuture.runAsync() trên common pool mà không join; xác nhận tác vụ không phải cơ chế giữ JVM sống.
- Tạo virtual thread làm công việc nền duy nhất; xác nhận main/server lifecycle vẫn phải giữ tiến trình.
- Gửi yêu cầu checkpoint trong lúc worker đang chờ queue, đang chạy task và đang chờ I/O.
- Gửi checkpoint khi worker đang giữ transaction; xác minh callback drain hoặc báo lỗi theo chính sách.
- Restore và xác minh worker được tạo lại hoặc tiếp tục đúng một lần, không tạo consumer hay scheduler trùng.
- Gửi tín hiệu shutdown bình thường và xác minh executor được đóng trong thời hạn.
- Cho worker gặp exception không mong đợi; xác minh lifecycle manager phát hiện việc worker kết thúc và ứng dụng không âm thầm mất khả năng phục vụ.

Khi kiểm thử, ghi lại thread name, daemon status, trạng thái executor, thời điểm main() kết thúc, thời điểm JVM shutdown và thời điểm yêu cầu checkpoint. Không chỉ nhìn vào log của worker vì daemon thread có thể bị dừng trước khi kịp ghi dòng cuối.

## 12. Nguyên tắc thiết kế

- Main thread kết thúc không có nghĩa JVM phải kết thúc ngay nếu vẫn còn non-daemon thread.
- Daemon thread không giữ JVM sống; không giao công việc duy nhất cần hoàn tất trước checkpoint cho daemon worker.
- Non-daemon thread chỉ giữ JVM sống khi nó còn chạy và chưa có lệnh shutdown rõ ràng.
- Đặt daemon status trước khi gọi start().
- Kiểm tra ThreadFactory của executor và thư viện; không suy đoán từ tên API.
- Nhớ rằng virtual thread là daemon và common pool thường dùng daemon worker.
- Giữ JVM sống bằng lifecycle server hoặc coordinator có ý nghĩa, không tạo thread vô hạn chỉ để giữ tiến trình.
- Quản lý executor, scheduler và worker bằng shutdown/awaitTermination có timeout.
- Trước checkpoint, quiesce và drain công việc; không dựa vào sleep cố định.
- Sau restore, tạo lại dependency và worker theo thứ tự; tính lại lịch và trạng thái có thời hạn.
- Kiểm thử cả trường hợp JVM thoát tự nhiên, shutdown rõ ràng và worker kết thúc bất ngờ.

CRaC cần một JVM đang tồn tại để nhận và hoàn tất yêu cầu checkpoint. Daemon thread không thể giữ JVM sống khi main và mọi non-daemon thread đã kết thúc. Non-daemon thread có thể giữ tiến trình hoạt động, nhưng phải được quản lý để không khiến ứng dụng treo khi shutdown. Thiết kế tốt kết hợp lifecycle chính rõ ràng, worker có daemon policy phù hợp, callback CRaC để pause hoặc tái tạo tác vụ, và cơ chế graceful shutdown có giới hạn thời gian.
