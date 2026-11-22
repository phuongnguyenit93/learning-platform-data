# Luồng daemon, non-daemon và điều kiện JVM tiếp tục tồn tại trong Spring Boot

## 1. Bài toán: main đã kết thúc nhưng process Java còn chạy — hoặc thoát quá sớm

Một ứng dụng Spring Boot có thể in thông báo đã khởi động xong, hoàn tất `ApplicationRunner` và trả quyền điều khiển khỏi `SpringApplication.run(...)`, nhưng JVM vẫn tồn tại. Ngược lại, một ứng dụng chỉ chạy tác vụ bất đồng bộ có thể thoát ngay sau startup dù job đang chờ chạy. Nguyên nhân thường không nằm ở tên method `main`, mà ở **những thread nào còn sống và thread nào được đánh dấu daemon**.

Trong Java, ngoài các trường hợp chương trình gọi dừng JVM hoặc bị môi trường bên ngoài kết thúc, quy tắc quan trọng là:

> JVM tiếp tục tồn tại khi còn ít nhất một Java **non-daemon thread đang sống**; nếu chỉ còn daemon threads, JVM có thể tiến vào quá trình shutdown bình thường.

Một thread đang `sleep`, `WAITING`, `BLOCKED` hay đợi I/O vẫn là thread **đang sống** nếu nó chưa kết thúc. Chỉ khi nó kết thúc thực sự mới thôi giữ JVM theo quy tắc non-daemon. Ngược lại, daemon thread vẫn có thể đang chạy mã Java nhưng **không tự giữ JVM tồn tại** khi mọi non-daemon thread đã kết thúc.

Các khái niệm dễ nhầm cần tách:

| Khái niệm | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| `main(String[] args)` | Điểm vào quen thuộc của chương trình | `main` trả về không nhất thiết JVM dừng ngay |
| Non-daemon thread | Thread vẫn được tính khi JVM xác định điều kiện kết thúc bình thường | Không đồng nghĩa thread đang hoạt động CPU |
| Daemon thread | Thread không ngăn JVM kết thúc khi chỉ còn daemon | Không được bảo đảm chạy hết `finally`/ghi file khi shutdown |
| `Thread.isAlive()` | Thread đã start và chưa kết thúc | Không cho biết thread có đang thực hiện công việc hữu ích |
| `Thread.isDaemon()` | Cờ daemon của một `Thread` | Không đồng nghĩa độ ưu tiên, OS service hay background process |
| `System.exit(int)` | Yêu cầu bắt đầu quá trình JVM shutdown | Không giống việc tự nhiên hết non-daemon threads |
| `SpringApplication.run(...)` | Khởi tạo và khởi chạy Spring context | Không phải một lời gọi luôn block cho đến khi process đóng |
| `spring.main.keep-alive` | Tùy chọn Boot giữ ứng dụng sống dù không còn non-daemon threads khác | Không thay thế resource management và graceful shutdown |

Điều này đặc biệt quan trọng với ba loại ứng dụng: **CLI/batch**, **ứng dụng web**, và **ứng dụng chạy scheduler/async tasks**. Các loại này đều dùng JVM, nhưng những thành phần hạ tầng tạo thread và chính sách vòng đời có thể khác nhau.

## 2. Chính xác khi nào Java Virtual Machine kết thúc?

Theo hợp đồng của `java.lang.Thread` và `Runtime`, hai trường hợp thông dụng dẫn đến shutdown JVM là:

1. **Kết thúc bình thường:** những non-daemon threads cuối cùng đã kết thúc, trong khi thread daemon còn hay không còn đều không ngăn shutdown.
2. **Yêu cầu thoát:** code gọi `System.exit(status)`, tương đương đường `Runtime.exit(status)`, hoặc tác nhân ngoài yêu cầu dừng theo cách JVM/runtime xử lý.

Còn có những tình huống khác như `Runtime.halt(status)`, process bị hệ điều hành kill cưỡng bức, lỗi JVM nghiêm trọng hoặc giới hạn container. `Runtime.halt` khác `System.exit`: nó chấm dứt JVM một cách cưỡng bức, **không chạy shutdown hooks theo cách bình thường**.

~~~mermaid
flowchart TD
  A["JVM bắt đầu, main thread thường là non-daemon"] --> B["main tạo hoặc kích hoạt nhiều threads"]
  B --> C["main trả về"]
  C --> D{"Còn non-daemon thread sống?"}
  D -->|"Có"| E["JVM tiếp tục thực thi"]
  E --> D
  D -->|"Không"| F["JVM khởi động shutdown bình thường"]
  F --> G["Shutdown hooks, dọn runtime phù hợp"]
  G --> H["JVM process kết thúc"]
  E --> I["System.exit / signal / stop từ ngoài"]
  I --> F
~~~

**Hình chỉ mô tả đường shutdown thông thường.** Một `System.exit` có thể bắt đầu shutdown dù non-daemon thread đang hoạt động; shutdown hooks không nhất thiết hoàn thành khi process bị kill cưỡng bức. Trạng thái JVM còn phụ thuộc native/JVM runtime và hệ điều hành, nên quy tắc non-daemon là nền tảng để phân tích, không phải lời hứa rằng mọi crash đều chạy cleanup.

### “Thread sống” bao gồm WAITING và TIMED_WAITING

Ví dụ một worker non-daemon có code:

~~~java
while (true) {
    Thread.sleep(1000);
}
~~~

Đây là **snippet** (method cần khai báo/handle `InterruptedException`). Nó có thể không làm gì ngoài ngủ, nhưng vẫn giữ JVM chạy vì nó chưa kết thúc. Nếu một worker khác đợi `CountDownLatch.await()` vô hạn và là non-daemon, tác động giữ process cũng tương tự.

Ngược lại, một daemon worker bận chạy vòng lặp không bảo đảm JVM giữ nó sống khi `main` và những non-daemon threads khác đã hết.

### NEW không giống ALIVE

Một `Thread` object vừa được khởi tạo bằng `new Thread(...)` nhưng chưa gọi `start()` không phải một thread đang sống theo `Thread.isAlive()`. Vì thế việc giữ hàng chục object `Thread` chưa start trong list **không tự** làm JVM sống mãi. Cờ daemon có thể được cấu hình trên object trước khi bắt đầu thread.

## 3. API cốt lõi của Thread

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| `new Thread(Runnable, name)` | Tạo platform thread object mới trong Java 17 | Chưa thực thi `run()` nếu chưa `start()` |
| `setDaemon(true)` | Đánh dấu daemon | Phải gọi **trước** `start()` |
| `setDaemon(false)` | Đánh dấu non-daemon | Tương tự, phải gọi khi thread chưa sống |
| `isDaemon()` | Đọc cờ daemon | Không tự cho biết trạng thái alive |
| `isAlive()` | Thread đã start và chưa kết thúc | Bao gồm thread đang sleep, waiting, blocked |
| `start()` | Yêu cầu JVM lên lịch thực thi thread | Gọi lại trên cùng thread sẽ lỗi `IllegalThreadStateException` |
| `join()` | Caller chờ một thread kết thúc | Không thay đổi daemon flag của thread được join |
| `interrupt()` | Gửi tín hiệu ngắt hợp tác | Không phải “kill thread” cưỡng bức |
| `Thread.currentThread()` | Lấy thread hiện đang chạy code | Để log tên/cờ daemon/trạng thái |
| `Thread.getState()` | Đọc trạng thái quan sát ở thời điểm gọi | Snapshot có thể thay đổi ngay sau đó |

### Cờ daemon được kế thừa

Một platform thread mới được tạo bởi `new Thread(...)` thông thường **kế thừa cờ daemon của thread tạo ra nó**, trừ khi code thay đổi cờ hoặc dùng `ThreadFactory`/API khác chủ động chọn giá trị. Thread `main` thông thường là non-daemon, nên:

~~~java
Thread worker = new Thread(() -> {
    System.out.println(Thread.currentThread().isDaemon());
});
worker.start();
~~~

Khi code trên được chạy từ `main` non-daemon mà không có thay đổi khác, dòng in là `false`. Nhưng nếu tạo thread bên trong daemon thread, giá trị mặc định có thể là `true`. Do đó **đừng mặc định mọi `new Thread` luôn non-daemon**, và đừng xem kết quả phụ thuộc môi trường là một yêu cầu bất biến của Java.

### setDaemon phải được gọi trước start

~~~java
Thread worker = new Thread(task, "data-loader");
worker.setDaemon(true);
worker.start();
~~~

`task` là `Runnable` do code bên ngoài định nghĩa, nên đoạn này là snippet. Nếu gọi `worker.setDaemon(false)` khi thread vẫn đang sống, Java ném `IllegalThreadStateException`. Không thể sửa tính daemon của một thread đang chạy để “giải cứu” process sắp thoát. Hãy cấu hình trước khi start, hoặc tạo thread mới với chính sách khác.

### Daemon không phải thread ưu tiên thấp

`isDaemon()` không đo priority và không làm thread bị hệ điều hành ưu tiên thấp hơn. Daemon và non-daemon đều có thể dùng CPU, truy cập lock, gọi network, mở file hoặc phát event. Sự khác nhau trọng tâm là **thread có giữ điều kiện sống của JVM hay không**; các chính sách scheduler, priority hoặc concurrency là vấn đề riêng.

## 4. Ví dụ Java 17 chạy độc lập: daemon kết thúc theo JVM, non-daemon giữ JVM

Ví dụ dưới đây **không cần Spring Boot**, giúp nhìn rõ quy tắc JVM trước khi đặt nó vào ứng dụng web hoặc scheduler. Chương trình dùng `CountDownLatch` để thứ tự các dòng output không phụ thuộc vào đua lịch CPU.

Tạo file **`DaemonThreadLab.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class DaemonThreadLab {

    public static void main(String[] args)
            throws InterruptedException {

        boolean daemon = args.length > 0
                && args[0].equals("daemon");

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            System.out.println("worker daemon="
                    + Thread.currentThread().isDaemon());
            started.countDown();

            try {
                if (daemon) {
                    // Cố tình chờ mãi để minh họa daemon
                    // không giữ JVM khi main kết thúc.
                    new CountDownLatch(1).await();
                } else {
                    // Chỉ kết thúc sau khi main đã in thông báo.
                    release.await();
                    System.out.println("worker completed");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "lab-worker");

        worker.setDaemon(daemon);
        worker.start();

        started.await();
        System.out.println("main reached end");

        if (!daemon) {
            release.countDown();
        }
    }
}
~~~

Biên dịch bằng Java 17+:

~~~bash
javac -encoding UTF-8 DaemonThreadLab.java
~~~

Chạy **daemon**:

~~~bash
java DaemonThreadLab daemon
~~~

Output của hai lời gọi `println` được đồng bộ bằng latch:

~~~text
worker daemon=true
main reached end
~~~

Thread daemon tiếp tục đợi một latch không được release. Khi `main` trả về và không còn non-daemon thread khác, JVM có thể shutdown bình thường ngay cả khi worker daemon chưa đi hết method `run()`. Chương trình sẽ **không** in `worker completed` trong nhánh này, vì dòng đó chỉ nằm trong nhánh non-daemon.

Chạy **non-daemon**:

~~~bash
java DaemonThreadLab user
~~~

Output:

~~~text
worker daemon=false
main reached end
worker completed
~~~

Thread non-daemon chỉ thoát sau khi nhận `release.countDown()`; dòng cuối buộc xuất hiện trước khi JVM có thể kết thúc tự nhiên theo điều kiện hết non-daemon. `main reached end` là thông báo do code in trước cuối method; không dùng riêng nó làm phép đo timestamp chính xác thread main đã chết.

### Vì sao dùng CountDownLatch?

Không có latch, scheduler có thể khiến log worker in trước hoặc sau log main, làm bài test dễ tưởng thứ tự log chính là quy luật thread liveness. Latch tạo quan hệ happens-before cho những mốc cần so sánh, giúp output ví dụ xác định. Nó **không phải** cơ chế bật/tắt daemon.

**Không đưa daemon chờ vô hạn này vào production.** Nó chỉ phục vụ học tập để chứng minh JVM có thể thoát trước khi tác vụ daemon kết thúc. Một tác vụ production phải có điều kiện kết thúc rõ và kế hoạch shutdown.

## 5. Ví dụ Java 17: kiểm chứng IllegalThreadStateException khi đổi cờ quá muộn

Tạo file **`DaemonFlagRules.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class DaemonFlagRules {

    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread thread = new Thread(() -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "flag-demo");

        thread.setDaemon(true);
        System.out.println("configured=" + thread.isDaemon());

        thread.start();
        ready.await();

        try {
            thread.setDaemon(false);
            System.out.println("unexpected");
        } catch (IllegalThreadStateException e) {
            System.out.println("change while alive rejected");
        }

        release.countDown();
        thread.join();

        System.out.println("joined");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 DaemonFlagRules.java
java DaemonFlagRules
~~~

Output:

~~~text
configured=true
change while alive rejected
joined
~~~

`ready.await()` bảo đảm thread đã vào phần chờ chưa được release khi `setDaemon(false)` được gọi, nên có thể tin cậy rằng thread còn sống. `thread.join()` được gọi từ `main` để chờ daemon hoàn tất, cho thấy **caller non-daemon có thể chọn chờ daemon**, nhưng daemon tự nó không giữ JVM. Nếu bỏ `join` và để `main` kết thúc sớm, không có bảo đảm daemon kịp hoàn tất.

### Khi muốn chờ một tác vụ daemon thì làm thế nào?

Có thể dùng `join`, `Future.get` hoặc cơ chế đồng bộ thích hợp **trong một non-daemon thread vẫn còn sống**. Khi main gọi `join`, main vẫn sống trong thời gian đợi, nên JVM chưa tự hết non-daemon. Tuy nhiên, chờ vô hạn có thể khiến chương trình treo; hãy thiết kế timeout và cancellation.

## 6. Main, System.exit, shutdown hooks và Runtime.halt

### main trả về không phải System.exit

~~~java
public static void main(String[] args) {
    startSomeBackgroundWork();
    System.out.println("main returned");
}
~~~

Đây là snippet, `startSomeBackgroundWork()` phải được định nghĩa. JVM có thể tiếp tục chạy nếu background work đã tạo một non-daemon thread vẫn sống. Spring Boot web server có thể khiến tiến trình tiếp tục chạy dù method `main` đã qua `SpringApplication.run(...)`.

### System.exit không đợi mọi worker hoàn tất

~~~java
System.exit(0);
~~~

Dù còn non-daemon threads, lời gọi `System.exit` bắt đầu thủ tục JVM shutdown. Trong đường shutdown bình thường, shutdown hooks đã đăng ký được khởi chạy; chúng có thể dọn resources hoặc đóng context, nhưng **không có nghĩa mọi tác vụ đang chạy sẽ được tự động hoàn tất**.

Không dùng `System.exit(0)` như cách mặc định để “chữa” một process bị treo vì quên đóng executor. Nó có thể làm mất dữ liệu đang ghi, tạo kết thúc đột ngột và che nguyên nhân vòng đời tài nguyên.

### Shutdown hook có giữ JVM sống không?

Một shutdown hook được đăng ký qua:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> System.out.println("shutdown hook")));
~~~

**Chỉ đăng ký hook không làm hook bắt đầu chạy ngay**, nên không biến nó thành một worker non-daemon đang sống để giữ JVM. JVM kích hoạt hooks khi bắt đầu shutdown theo cơ chế hỗ trợ. Hooks chạy đồng thời; không nên giả định thứ tự gọi hoặc giao cho hook một nhiệm vụ remote I/O vô hạn.

Hook có thể không chạy khi `Runtime.halt(...)`, process bị `SIGKILL`, container bị kill cưỡng bức hoặc JVM crash. Nếu cần bảo toàn dữ liệu, nên chủ động commit/flush ở các điểm nghiệp vụ đúng, không chỉ dựa vào shutdown hook.

### Đóng Spring context khác dừng mọi thread tùy biến

`ConfigurableApplicationContext.close()` kích hoạt lifecycle stop/destroy của bean do Spring quản lý, nhưng không tự tìm và interrupt mọi `new Thread(...)` mà developer đã tạo bên ngoài cơ chế quản lý. Một non-daemon thread tự tạo quên dừng có thể giữ process tồn tại **sau khi context đóng**.

Để kết thúc sạch, quản lý worker bằng executor/bean lifecycle phù hợp; gọi `shutdown`/`interrupt` có kiểm soát, chờ một khoảng hợp lý và ghi nhận failure nếu có.

## 7. Thread pools: vì sao task xong mà JVM vẫn không thoát?

Trong thực tế, nhiều ứng dụng không tạo `new Thread` trực tiếp mà sử dụng `ExecutorService`, `ScheduledExecutorService`, Spring `TaskExecutor` hoặc scheduler. Thread pool có thể giữ **non-daemon worker threads** sống để nhận thêm tác vụ, kể cả khi queue không còn việc. Nếu quên đóng pool, JVM có thể tiếp tục chạy vô thời hạn.

### Executors.defaultThreadFactory và non-daemon

Trong Java SE, default thread factory của `Executors` tạo worker thread **non-daemon**. Với `Executors.newSingleThreadExecutor()`, pool worker thông thường có thể tồn tại chờ tác vụ mới. Vì vậy việc task đã hoàn thành **không đủ** để kết luận JVM có thể thoát.

Tạo file **`ExecutorShutdownLab.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ExecutorShutdownLab {

    public static void main(String[] args)
            throws Exception {

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<Integer> result = executor.submit(() -> {
                System.out.println("pool daemon="
                        + Thread.currentThread().isDaemon());
                return 42;
            });

            System.out.println("result=" + result.get());
        } finally {
            executor.shutdown();

            if (!executor.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        System.out.println("executor closed");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ExecutorShutdownLab.java
java ExecutorShutdownLab
~~~

Output với default thread factory của Java 17:

~~~text
pool daemon=false
result=42
executor closed
~~~

`result.get()` đợi task hoàn tất; `shutdown()` báo pool không nhận việc mới; `awaitTermination(...)` đợi pool dừng. Điều này khác nhau: **Future hoàn tất** không có nghĩa **executor đã shutdown**.

Nếu bỏ `shutdown()` trong ví dụ với `newSingleThreadExecutor()`, worker non-daemon có thể tiếp tục chờ job và giữ JVM chạy. Không khắc phục bằng cách luôn chuyển thread sang daemon; hãy **quản lý lifecycle của pool**.

### ThreadFactory tùy biến

Một custom `ThreadFactory` có thể tạo threads daemon hoặc non-daemon:

~~~java
ThreadFactory factory = task -> {
    Thread t = new Thread(task, "custom-worker");
    t.setDaemon(true);
    return t;
};
~~~

Đây là snippet cần import `java.util.concurrent.ThreadFactory`. Tạo daemon pool có thể hợp lý cho công việc phụ trợ chấp nhận bị bỏ dở, nhưng **không** phù hợp cho tác vụ bắt buộc ghi dữ liệu xong. Pool daemon vẫn cần đóng để giải phóng resource và chạy cleanup có chủ đích; daemon không phải cơ chế resource management.

### Scheduled executor và waiting worker

Một `ScheduledExecutorService` đang chờ lần chạy tiếp theo có thể giữ non-daemon thread sống. Ngược lại, nếu scheduler thread daemon, nó không giữ JVM sống chỉ vì có lịch `fixedRate`/`fixedDelay` đã đăng ký. Đó là lý do mọi ứng dụng timer/scheduler phải kiểm tra chính sách thread thực tế, thay vì đoán từ tên API.

## 8. Spring Boot: SpringApplication.run trở về có nghĩa ứng dụng đã kết thúc chưa?

Không. Trong Spring Boot, `SpringApplication.run(...)` thường tạo `ApplicationContext`, refresh context, phát các sự kiện vòng đời và chạy `ApplicationRunner`/`CommandLineRunner`. Nếu hoàn tất thành công, method `run(...)` trả về `ConfigurableApplicationContext` cho caller; từ đó **các thread còn sống** và các cơ chế keep-alive quyết định process có tiếp tục hay không.

~~~mermaid
flowchart TD
  A["main()"] --> B["SpringApplication.run(...)"]
  B --> C["Refresh context, tạo bean"]
  C --> D["ApplicationStartedEvent"]
  D --> E["Runner tasks"]
  E --> F["ApplicationReadyEvent"]
  F --> G["run trả về"]
  G --> H{"Còn non-daemon / keep-alive?"}
  H -->|"Có"| I["JVM tiếp tục"]
  H -->|"Không"| J["JVM shutdown"]
~~~

Đây là sơ đồ logic giản lược; Boot còn phát `AvailabilityChangeEvent` cho liveness/readiness vào các mốc liên quan. Một runner ném exception có thể khiến startup thất bại trước khi `run` trả về thành công.

### Spring Boot CLI/batch app

Với dự án chỉ có `spring-boot-starter`, không có web server hoặc worker non-daemon kéo dài, chương trình thường **tự kết thúc sau startup**. Một `ApplicationRunner` thực hiện tác vụ đồng bộ rồi return thường phù hợp cho batch CLI: khi xong việc, không cần giữ JVM mãi.

### Spring Boot web app

Với `spring-boot-starter-web` hoặc web runtime tương ứng, embedded server và các thành phần hạ tầng có thể tạo những thread giữ tiến trình sống sau khi `main`/`run` trả về. Vì vậy “main in xong nhưng service vẫn nghe HTTP” là hiện tượng bình thường.

Không nên khái quát “web server luôn tạo đúng N non-daemon threads”: Tomcat, Jetty, Undertow, Netty, virtual threads, tùy chọn server và các phiên bản có thể khác. Hãy quan sát thread dump và cấu hình thực tế.

### Background runner, @Async, @Scheduled

- `ApplicationRunner` chạy đồng bộ trên đường startup mặc định cho đến khi method `run(...)` hoàn tất. Nếu nó **spawn** worker rồi return, Boot không tự đợi worker đó xong chỉ vì nó được tạo trong runner.
- `@Async` gọi các tác vụ qua executor đã cấu hình, thường do `@EnableAsync` kích hoạt; tình trạng daemon phụ thuộc loại executor/thread factory. Không nên kết luận mọi `@Async` sẽ giữ app sống.
- `@Scheduled` cần scheduling được bật (ví dụ `@EnableScheduling`) và phụ thuộc scheduler đang sử dụng. Một lịch chạy không phải một lời hứa rằng luôn tồn tại non-daemon thread giữ JVM.
- `CompletableFuture.runAsync(...)` có thể dùng common pool hoặc một executor khác. Đừng dựa vào daemon flag không được kiểm soát để bảo đảm kết quả background task hoàn tất trước khi app thoát.

Một số executor/scheduler Spring Boot auto-configure khác nhau tùy có virtual threads hay không. Cần kiểm tra `spring.threads.virtual.enabled`, bean `TaskExecutor`/`TaskScheduler`, `ThreadFactory` và scope/lifecycle của từng pool.

## 9. Ví dụ Spring Boot 3.5.16 Java 17+ chạy được: ứng dụng CLI với hai chế độ thread

Dự án này dùng **Spring Boot 3.5.16**, Java 17+, Maven và starter cơ bản. Nó được thiết kế có **thứ tự stdout xác định cho những dòng do code viết**, để minh họa JVM có thoát ngay với daemon worker và đợi công việc non-daemon.

Cấu trúc:

~~~text
thread-lifetime-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/lifetime/
    │   └── ThreadLifetimeApplication.java
    └── resources/application.yaml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>thread-lifetime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### File src/main/resources/application.yaml

~~~yaml
spring:
  main:
    web-application-type: none
    banner-mode: "off"
    keep-alive: false
~~~

`web-application-type: none` giữ thí nghiệm ở chế độ CLI, không phụ thuộc web server. `keep-alive: false` là mặc định của Boot 3.5 nhưng được ghi rõ để minh họa; có thể override bằng CLI khi thí nghiệm.

### File src/main/java/com/example/lifetime/ThreadLifetimeApplication.java

~~~java
package com.example.lifetime;

import java.util.concurrent.CountDownLatch;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ThreadLifetimeApplication {

    private static final CountDownLatch AFTER_RUN =
            new CountDownLatch(1);

    public static void main(String[] args) {
        SpringApplication.run(ThreadLifetimeApplication.class, args);

        System.out.println("MAIN_AFTER_RUN");
        AFTER_RUN.countDown();
    }

    @Bean
    ApplicationRunner spawnTask() {
        return args -> {
            boolean daemon = args.containsOption("daemon-task");
            CountDownLatch announced = new CountDownLatch(1);

            Thread worker = new Thread(() -> {
                System.out.println("TASK_DAEMON="
                        + Thread.currentThread().isDaemon());
                announced.countDown();

                try {
                    if (daemon) {
                        // Chờ mãi: chỉ dùng làm lab minh họa.
                        new CountDownLatch(1).await();
                    } else {
                        // Chờ cho main đã in MAIN_AFTER_RUN.
                        AFTER_RUN.await();
                        System.out.println("TASK_FINISHED");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "demo-task");

            worker.setDaemon(daemon);
            worker.start();

            announced.await();
            System.out.println("RUNNER_RETURNED");
        };
    }
}
~~~

**Phân tích code:**
1. `SpringApplication.run` hoàn thành startup/runner trước khi in `MAIN_AFTER_RUN`.
2. Runner tạo một thread, set cờ daemon **trước** `start()` và dùng latch để đợi thread in trạng thái.
3. Nếu truyền `--daemon-task`, thread chờ mãi trong nhánh daemon, nhưng không tự giữ JVM khi main kết thúc.
4. Nếu không có flag, thread non-daemon đợi `AFTER_RUN`, chỉ in `TASK_FINISHED` sau khi main đã in dòng `MAIN_AFTER_RUN`; JVM không kết thúc tự nhiên trước khi thread này hoàn tất.
5. `CountDownLatch` là cơ chế đồng bộ thứ tự output; nó không làm thread trở thành daemon hay non-daemon.
6. Ví dụ cố ý tạo daemon bị block mãi để chứng minh semantics; **không dùng kỹ thuật này trong production**.

### Biên dịch và chạy

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar
~~~

Các dòng do code ví dụ in ra, theo thứ tự có kiểm soát:

~~~text
TASK_DAEMON=false
RUNNER_RETURNED
MAIN_AFTER_RUN
TASK_FINISHED
~~~

Framework có thể in log startup khác; đừng so sánh toàn bộ stdout với khối trên.

Chạy nhánh daemon:

~~~bash
java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar --daemon-task
~~~

Các dòng do code ví dụ in:

~~~text
TASK_DAEMON=true
RUNNER_RETURNED
MAIN_AFTER_RUN
~~~

Dù daemon thread vẫn đang đợi latch vô hạn, CLI application có thể kết thúc bình thường sau khi main trả về vì nó không còn non-daemon thread nào khác trong cấu hình minh họa này.

### Một thay đổi làm JVM không thoát dù worker là daemon

Spring Boot 3.5 có property `spring.main.keep-alive`. Khi bật:

~~~bash
java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar \
  --daemon-task \
  --spring.main.keep-alive=true
~~~

Boot giữ ứng dụng sống ngay cả khi chỉ còn daemon threads. Đoạn này sẽ không tự thoát vì worker chờ mãi **và** Boot keep-alive; hãy dừng bằng Ctrl+C hay tín hiệu shutdown thích hợp. Không hiểu `keep-alive=true` là cách bảo đảm daemon task hoàn tất: worker vẫn đang block và không được phép dựa vào việc process sống lâu để thay cho cancellation.

Để thực nghiệm có thời hạn trên Linux với GNU `timeout`:

~~~bash
timeout 5s java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar \
  --daemon-task \
  --spring.main.keep-alive=true
~~~

Khi process không tự kết thúc trước hạn, `timeout` gửi tín hiệu dừng theo chính sách của nó; exit status mặc định thường là **124** khi timeout thật sự xảy ra. Kết quả này phụ thuộc môi trường và thời gian startup, nên không coi chính xác 5 giây hay status 124 là một output Java được bảo đảm trong mọi tình huống. Trên PowerShell/cmd, dùng một dòng lệnh và dừng process thủ công thay vì dùng `timeout` của GNU.

### Kết luận từ demo

Cùng một JAR, ba chế độ tạo ba chính sách vòng đời:

| Cấu hình | Worker | Có thể tự thoát khi main xong? |
| --- | --- | --- |
| Không flag, `keep-alive=false` | Non-daemon, hoàn tất sau tín hiệu của main | Chỉ sau khi worker kết thúc |
| `--daemon-task`, `keep-alive=false` | Daemon đợi vô hạn | Có, khi không còn non-daemon khác |
| `--daemon-task --spring.main.keep-alive=true` | Daemon đợi vô hạn và Boot giữ sống | Không tự thoát theo điều kiện hết non-daemon thông thường |

Đây là minh họa một CLI app **không có web server hoặc thành phần non-daemon phụ trợ nào khác**. Trong dự án thật, thread library, executor, logging pipeline, database driver và các integration có thể tạo thread khác; cần đo thực tế.

## 10. Virtual threads Java 21+ — điểm rất quan trọng khi dùng Spring Boot

Các ví dụ `new Thread(...)` ở trên dùng **platform threads** và chạy được trên Java 17. Từ **Java 21**, Java cung cấp **virtual threads**: những Java threads được JVM quản lý nhẹ hơn, phù hợp với nhiều tác vụ chờ I/O.

**Điểm quyết định đối với chủ đề này: virtual threads luôn là daemon threads.** Chúng không giữ JVM sống chỉ vì còn virtual task. Đây là hành vi được Oracle và Spring Boot ghi rõ, không phải một mẹo không chính thức.

### Ví dụ Java 21 độc lập

File **`VirtualThreadDaemon.java`** — chỉ compile bằng Java 21+:

~~~java
public final class VirtualThreadDaemon {

    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = Thread.ofVirtual()
                .name("vt-demo")
                .start(() -> {
                    System.out.println("virtual="
                            + Thread.currentThread().isVirtual());
                    System.out.println("daemon="
                            + Thread.currentThread().isDaemon());
                });

        worker.join();
    }
}
~~~

Chạy bằng JDK 21+:

~~~bash
javac VirtualThreadDaemon.java
java VirtualThreadDaemon
~~~

Output:

~~~text
virtual=true
daemon=true
~~~

`join()` ở main để chờ virtual worker in cả hai dòng; điều này không làm virtual thread trở thành non-daemon. Nếu bỏ `join` và main thoát rất nhanh, virtual thread có thể bị shutdown trước khi in xong.

Không sao chép `Thread.ofVirtual()` vào project khóa Java 17: API đó **không có trong Java 17**. Cũng không thể chuyển một virtual thread thành non-daemon để giải quyết bài toán keep-alive; hãy dùng cơ chế quản lý vòng đời ứng dụng phù hợp.

### Spring Boot và cờ virtual threads

Trong Spring Boot 3.5, nếu chạy trên Java 21+, có thể bật:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Spring Boot tài liệu hóa rằng khi bật virtual threads, cơ chế auto-configured task execution/scheduling có thể dùng virtual threads. Ví dụ với `@Scheduled`, scheduler dùng virtual thread trong cấu hình hỗ trợ nên các thread đó **không tự giữ JVM chạy**. Vì vậy Boot khuyến nghị `spring.main.keep-alive=true` nếu ứng dụng cần duy trì process để các tác vụ đó tiếp tục được thực thi.

Đừng hiểu `spring.threads.virtual.enabled=true` làm **tất cả** thread trong process thành virtual; JVM vẫn có platform/carrier threads và nhiều thư viện có thể tự tạo platform threads. Và đừng hiểu virtual threads làm code chạy nhanh hơn ở mọi workload; mục tiêu chính là hỗ trợ đồng thời nhiều tác vụ chờ I/O với overhead thấp hơn, không phải tăng tốc CPU-bound computation.

### Scheduled app với virtual threads

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration
@EnableScheduling
class ScheduleConfiguration {

    @Scheduled(fixedDelay = 5000)
    void tick() {
        System.out.println("SCHEDULE_TICK");
    }
}
~~~

Đây là class minh họa phải nằm trong package scan và có Spring scheduling infrastructure tương ứng. Nếu ứng dụng chỉ có lịch định kỳ, không có web server giữ sống và dùng scheduler dựa trên daemon virtual threads, nó có thể thoát sau startup nếu không bật `spring.main.keep-alive=true`. Việc đăng ký `@Scheduled` **không tự là cam kết process tồn tại vô hạn**.

**Bẫy cấu hình:** khi dùng virtual threads, các property cấu hình kích thước thread pool truyền thống có thể không còn tác dụng cho executor/scheduler auto-configured theo loại mới. Xem chính xác phiên bản Boot và loại bean được tạo trước khi tune `spring.task.execution.pool.*` hoặc `spring.task.scheduling.pool.*`.

## 11. @Async, CompletableFuture và background tasks có giữ JVM sống không?

### Spring @Async

`@Async` thường sử dụng một `Executor`/`TaskExecutor` của Spring. Nó không tự mang cờ “giữ ứng dụng sống” độc lập với executor được cấu hình.

~~~java
@Async
public CompletableFuture<Void> sendNotification() {
    // logic...
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là snippet cần Spring `@Async`, `@EnableAsync` hoặc cơ chế async tương ứng, import `CompletableFuture` và method nằm trong bean thích hợp. Caller nhận một future không có nghĩa JVM tự chờ future xong trước khi tắt. Cần biết executor chạy bằng daemon platform thread, non-daemon platform thread hay virtual thread và cần xử lý lỗi/cancellation như thế nào.

Nếu dùng `@Async` để làm **tác vụ phải hoàn tất trước khi ứng dụng ready**, việc chạy bất đồng bộ rồi return khỏi startup hook có thể là thiết kế sai. Hãy đợi future bằng timeout có kiểm soát trong một startup orchestration hoặc dùng workflow khác phù hợp; không chỉ dựa vào non-daemon để “may mắn giữ JVM”.

### CompletableFuture không phải cơ chế lifecycle

~~~java
CompletableFuture<Void> task =
        CompletableFuture.runAsync(() -> doWork());
~~~

Snippet này cần `CompletableFuture` và method `doWork()`. Theo default, async task có thể dùng common ForkJoinPool, nơi thread factory/daemon behavior phụ thuộc môi trường và cấu hình; trong một số điều kiện runtime còn có fallback khác. Không gắn logic correctness với giả định chung rằng “commonPool luôn giữ JVM sống” hoặc “luôn là daemon trong mọi case”.

Để có kiểm soát, cung cấp executor rõ ràng, theo dõi `Future`, và đóng executor khi ứng dụng kết thúc. Nếu là Spring-managed component, tích hợp vào bean lifecycle.

### Task hoàn tất và thread pool hoàn tất là hai chuyện

- `Future.isDone() == true`: riêng task đó đã hoàn tất, thất bại hoặc bị cancel.
- `ExecutorService.isShutdown() == true`: pool đã nhận yêu cầu shutdown, chưa chắc mọi task xong.
- `ExecutorService.isTerminated() == true`: pool đã kết thúc sau shutdown.
- `Thread.isAlive() == true`: một thread vẫn đang sống, có thể không còn task hữu ích.
- `ApplicationReadyEvent`: Spring Boot đạt một mốc startup, không xác nhận tất cả background futures đã xong.

Phân biệt những trạng thái này tránh lỗi “job xong rồi mà process còn chạy” hoặc “app ready nhưng chưa xử lý xong backlog”.

## 12. Graceful shutdown: dừng đúng, không dựa vào daemon để mất việc

Chuyển toàn bộ worker sang daemon không phải giải pháp an toàn cho process treo. Một daemon có thể bị JVM shutdown khi đang:
- ghi file hoặc commit transaction;
- gửi message và chờ acknowledgment;
- cập nhật cache hoặc checkpoint;
- giữ khóa hoặc connection;
- flush log/telemetry.

Khi JVM dừng vì chỉ còn daemon, không có bảo đảm daemon nhận được một lần interrupt hoặc chạy hết `finally`. Vì vậy công việc quan trọng nên có lifecycle có kiểm soát, lưu tiến độ bền vững và xử lý cancellation.

### Sử dụng @PreDestroy trong Spring Boot 3.x

Ví dụ bean quản lý worker riêng:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class ManagedWorker {

    private Thread worker;

    @PostConstruct
    void start() {
        worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    doOneUnitOfWork();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }, "managed-worker");
        worker.setDaemon(false);
        worker.start();
    }

    private void doOneUnitOfWork()
            throws InterruptedException {
        Thread.sleep(1000);
    }

    @PreDestroy
    void stop() {
        if (worker == null) {
            return;
        }
        worker.interrupt();

        try {
            worker.join(3000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đây là một bean **minh họa có thể đặt trong ứng dụng Spring Boot 3.x**, dùng `jakarta.annotation`. Nó có một vòng làm việc giả bằng `Thread.sleep`, không làm xử lý nghiệp vụ thật. Khi context đóng, Spring gọi `@PreDestroy`, gửi interrupt rồi đợi tối đa ba giây. Nếu worker bỏ qua interrupt hoặc I/O bị block không thể ngắt, cần chính sách timeouts/metrics và cleanup mạnh hơn; `join(3000)` không tự giết thread nếu nó vẫn sống sau timeout.

**Không nên tạo rất nhiều raw threads như ví dụ đơn giản này trong production.** Hãy ưu tiên `TaskExecutor`/`TaskScheduler` hoặc `ExecutorService` được quản lý với lifecycle, giới hạn concurrency và queue thích hợp.

### Managed executor

Với pool, lifecycle điển hình:

~~~java
executor.shutdown();

if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
    executor.shutdownNow();
}
~~~

Đây là snippet Java cần `ExecutorService`, `TimeUnit` và method xử lý `InterruptedException`. `shutdownNow` cũng chỉ cố gắng interrupt các task và trả về task đang chờ; nó không cưỡng bức một task không hợp tác phải thoát. Với ứng dụng xử lý dữ liệu quan trọng, kết hợp idempotency, checkpoint và retry sau restart.

### SmartLifecycle và shutdown phase

Spring hỗ trợ `SmartLifecycle` cho component cần điều phối start/stop theo phase; executor/scheduler auto-configured cũng có quản lý lifecycle tùy loại. Dùng đúng abstraction khi component phụ thuộc vào thứ tự đóng resource. Không tự chạy `System.exit` từ bean chỉ vì không biết cách dừng worker.

## 13. Các công cụ chẩn đoán JVM còn sống vì thread nào

Khi application log báo ready hoặc context đã close nhưng process chưa thoát, trước tiên xác nhận có **non-daemon threads nào còn sống** và chúng đang ở state gì.

### JDK tools

Trên máy có JDK và quyền attach:

~~~bash
jcmd PID Thread.print
~~~

hoặc:

~~~bash
jstack PID
~~~

Thay `PID` bằng process id thật. Thread dump thường cho thấy tên, daemon marker khi có, stack trace và trạng thái `RUNNABLE`/`WAITING`/`TIMED_WAITING`. Đọc stack để tìm worker đang chờ `BlockingQueue.take`, `CountDownLatch.await`, `ThreadPoolExecutor.getTask`, network I/O hoặc deadlock. Không kết luận ngay một thread daemon duy nhất là nguyên nhân giữ JVM; nguyên nhân thường là một thread **non-daemon** còn sống.

### Quan sát process từ hệ điều hành

Trên Linux:

~~~bash
ps -ef | grep java
ps -L -p PID -o pid,tid,stat,comm
~~~

Lệnh `ps -L` hiển thị những OS threads được hệ điều hành theo dõi, **không phải một danh sách đầy đủ mọi virtual thread của Java 21+**. Khi dùng virtual threads, cần công cụ hỗ trợ virtual thread như những lệnh `jcmd`/JFR tương ứng với phiên bản JDK.

### Ghi thông tin thread từ chính Java

~~~java
Thread current = Thread.currentThread();

System.out.println("threadName=" + current.getName());
System.out.println("daemon=" + current.isDaemon());
System.out.println("alive=" + current.isAlive());
System.out.println("state=" + current.getState());
~~~

Đây là snippet bên trong một method. Nó chỉ cho biết thông tin thread đang chạy code này, không phải kết luận cho toàn process. Có thể quan sát thread snapshots bằng `Thread.getAllStackTraces()` khi chẩn đoán, nhưng snapshot có thể thiếu thread sinh/diệt đồng thời và không được dùng như cơ chế điều phối sản xuất.

### Khi cần tìm pool bị quên shutdown

Các dấu hiệu hữu ích:
1. Log cho biết business job đã hoàn tất, nhưng `java -jar` không trở về prompt.
2. Thread dump còn `pool-1-thread-1` hoặc worker tên custom đang `WAITING` trong pool queue.
3. `ExecutorService` đã nhận task nhưng chưa `shutdown`.
4. Sau khi thêm shutdown đúng thời điểm, process kết thúc tự nhiên.
5. Nếu đã close context nhưng vẫn có thread custom ngoài container, cần thêm cleanup cho đúng bean/service đó.

Đừng gọi `System.exit` để giấu thread leak trước khi xác định nguyên nhân. Một process đóng được “bằng ép buộc” vẫn có thể gây thất thoát công việc và hỏng dữ liệu.

## 14. Bảng tình huống và lựa chọn đúng

| Triệu chứng | Nguyên nhân khả dĩ | Việc nên kiểm tra hoặc sửa |
| --- | --- | --- |
| `main` trả về nhưng process không thoát | Còn non-daemon thread hoặc keep-alive | Thread dump, executor, scheduler, `spring.main.keep-alive` |
| CLI app thoát trước khi daemon task ghi xong | Không còn non-daemon threads | Chờ task có chủ đích, dùng executor/lifecycle thích hợp |
| Bật virtual threads, `@Scheduled` không chạy lượt sau | Scheduler chỉ có daemon virtual thread, JVM tự thoát | `spring.main.keep-alive=true` và kiểm tra Java 21+ |
| Executor task đã xong nhưng Java vẫn chạy | Pool worker non-daemon chờ việc tiếp | `shutdown` / `awaitTermination` |
| Đổi `setDaemon(false)` trên thread đang chạy bị lỗi | `IllegalThreadStateException` | Cấu hình trước `start`, chọn ThreadFactory đúng |
| Worker đang sleep vẫn giữ process | Sleep không làm thread chết | Có tín hiệu stop/interrupt và vòng xử lý ngắt |
| Bean `@PreDestroy` chạy nhưng JVM còn | Thread custom ngoài lifecycle, bỏ qua interrupt | Theo dõi/join worker, stop pool rõ ràng |
| Web server vẫn phục vụ sau log “Started” | Infrastructure threads giữ JVM | Đây thường là đúng hành vi, kiểm tra server lifecycle |
| `ApplicationReadyEvent` đã phát nhưng job background còn chạy | Ready không tự chờ task spawn | Điều phối readiness hoặc đợi task nếu là điều kiện startup |
| Daemon thread log không đủ các dòng cuối | JVM thoát trước khi daemon hoàn tất | Không giao việc bắt buộc cho daemon không được chờ |
| Kubernetes stop nhưng job mất dữ liệu | Shutdown grace period ngắn, task không hợp tác | Timeout/cancellation/checkpoint, terminationGracePeriodSeconds |
| `System.exit` làm process biến mất dù còn non-daemon | Explicit JVM shutdown | Chỉ dùng ở boundary thích hợp, dọn resource trước |

## 15. Trình tự xử lý khi Spring Boot “không thoát” hoặc “thoát sớm”

### Trường hợp A — Không thoát sau khi job đã xong

1. Xác định loại ứng dụng: web, CLI, scheduled worker hay message consumer.
2. Kiểm tra `SpringApplication.run` đã hoàn thành và context có còn mở không.
3. Kiểm tra `spring.main.keep-alive`, đặc biệt nếu Java 21+ dùng virtual threads.
4. Lấy thread dump lúc job nghiệp vụ được báo hoàn tất.
5. Tìm non-daemon thread còn sống, executor/scheduler nào tạo và vì sao nó chưa dừng.
6. Thêm shutdown/interrupt/join ở lifecycle đúng, không đổi mọi thread thành daemon.
7. Chạy lại và kiểm tra process tự thoát, dữ liệu đã flush/commit và exit code đúng.

### Trường hợp B — Thoát trước khi task chạy xong

1. Xem task thuộc `@Async`, `CompletableFuture`, `@Scheduled`, raw `Thread` hay virtual thread.
2. Kiểm tra daemon flag hoặc ThreadFactory/Executor đang dùng; đừng suy từ tên method.
3. Xác định task có bắt buộc hoàn tất trước khi process/traffic kết thúc hay không.
4. Nếu bắt buộc: dùng `Future.get`/`join` ở một orchestration có timeout, hoặc workflow durable queue/checkpoint.
5. Nếu là long-running scheduler: quản lý application keep-alive/lifecycle, không chỉ spawn daemon.
6. Tạo test shutdown: gửi signal, quan sát cancel và dọn resource, xác nhận không mất job bắt buộc.

### Trường hợp C — Sau bật spring.threads.virtual.enabled=true thấy process tự thoát

1. Xác minh **JDK thực tế là Java 21+** và Spring Boot version hỗ trợ property.
2. Kiểm tra các bean scheduler/executor đã chuyển sang virtual thread implementation chưa.
3. Kiểm tra có còn platform non-daemon thread phục vụ web server hay không; **không tự giả định**.
4. Thử `spring.main.keep-alive=true` theo hướng dẫn Boot cho ứng dụng phải chạy lâu.
5. Dừng process có kiểm soát và kiểm tra shutdown hooks/context cleanup.
6. Rà soát pinning, concurrency và executor configuration nếu thay đổi hiệu năng, không chỉ lifecycle.

## 16. Một số anti-pattern cần tránh

**Anti-pattern 1 — Dùng daemon để “dập” process treo.**  
Nếu thread chưa được shutdown đúng, đổi nó thành daemon chỉ làm JVM có thể thoát khi task còn dở. Hậu quả có thể là mất dữ liệu hoặc release resource không sạch.

**Anti-pattern 2 — Dùng System.exit trong @PostConstruct hoặc @EventListener để tự sửa vòng đời.**  
Điều này có thể ngắt context đang khởi tạo, gây khó debug và bỏ qua đường xử lý lỗi/health. Thay bằng exception startup có ý nghĩa, lifecycle và shutdown theo chủ đích.

**Anti-pattern 3 — Cho rằng @Scheduled tự giữ JVM.**  
Đặc biệt sai khi scheduler dùng virtual threads. Spring Boot khuyến nghị bật keep-alive khi ứng dụng phụ thuộc vào những daemon workers.

**Anti-pattern 4 — Chỉ nhìn thread state RUNNABLE mới coi là đang sống.**  
Non-daemon `WAITING` vẫn giữ JVM; daemon `RUNNABLE` không giữ JVM khi không có non-daemon khác.

**Anti-pattern 5 — Chỉ đóng ApplicationContext rồi bỏ quên custom executor.**  
Spring không thể tự quản lý thứ nó không sở hữu; raw thread và pool tạo ngoài container cần cleanup rõ ràng.

**Anti-pattern 6 — Nghĩ System.exit bảo đảm tất cả finally được gọi.**  
Shutdown hooks có giới hạn và đường dừng cưỡng bức bỏ qua. Dữ liệu quan trọng phải bảo vệ bằng transaction, checkpoint, idempotency và quản lý task.

**Anti-pattern 7 — Đánh đồng daemon với detached/background process của OS.**  
Daemon flag thuộc `java.lang.Thread`. Nó không biến thread thành service riêng, không tạo một process mới, và không tự giúp process khởi động cùng hệ điều hành.

## 17. Checklist thiết kế thread và task cho Spring Boot

- Đọc rõ loại app (CLI/web/scheduler/consumer) và mục tiêu vòng đời.
- Nếu tạo platform `Thread`, xác định cờ daemon **trước `start()`**; không thay trên live thread.
- Không giao công việc cần hoàn tất cho daemon thread mà không có orchestration/await hợp lý.
- Quản lý `ExecutorService` với `shutdown`, `awaitTermination` và interruption/timeouts.
- Với Spring beans, tích hợp `@PreDestroy`/`SmartLifecycle`/managed task infrastructure.
- Kiểm tra event startup: `ApplicationReadyEvent` không đồng nghĩa mọi background task tự tạo đã xong.
- Với Java 21+ và virtual threads, nhớ virtual threads là daemon; cân nhắc `spring.main.keep-alive=true` cho ứng dụng chạy dài.
- Kiểm tra task executor/scheduler thực tế; đừng suy thread daemon từ tên `@Async` hoặc `@Scheduled`.
- Giữ shutdown graceful: dừng nhận việc mới, hoàn tất hoặc cancel task, flush/checkpoint, đóng pool/context.
- Test hai hướng: **process không thoát khi còn công việc bắt buộc**, và **process thoát sạch khi công việc hoàn thành**.
- Khi process bất thường, lấy thread dump trước khi thêm `System.exit` hay đổi toàn bộ ThreadFactory.
- Dùng Java 17 cho các ví dụ platform thread; dùng Java 21+ cho `Thread.ofVirtual()`.
- Không dựa vào output giữa nhiều threads khi thiếu đồng bộ; dùng latch để có ví dụ xác định.
- Khi chạy trong container, kiểm tra grace period, signal handling và mức tải thực tế trước khi triển khai.

## 18. Câu hỏi tự kiểm tra

**1. Khi main kết thúc, JVM có bắt buộc thoát không?**  
Không. Nếu còn non-daemon threads sống, JVM thông thường tiếp tục chạy.

**2. Một non-daemon thread đang WAITING có giữ JVM sống không?**  
Có. Nó vẫn là một live non-daemon thread.

**3. Daemon thread có được bảo đảm chạy hết finally trước JVM shutdown không?**  
Không. JVM có thể kết thúc khi chỉ còn daemon threads mà không đợi chúng hoàn thành.

**4. Khi nào được gọi Thread.setDaemon(true)?**  
Trước khi thread được start. Gọi trên thread đang sống có thể ném `IllegalThreadStateException`.

**5. Daemon khác thread priority như thế nào?**  
Daemon ảnh hưởng điều kiện kết thúc JVM; priority ảnh hưởng gợi ý lịch chạy, là khía cạnh khác.

**6. Thread mới thường thừa hưởng daemon flag từ đâu?**  
Từ thread tạo ra nó, trừ khi ThreadFactory/API code thay đổi.

**7. Gọi join trên một daemon thread có thể giữ process sống không?**  
Có, nếu caller là non-daemon thread đang chờ; chính caller còn sống giữ JVM chứ không phải daemon chuyển loại.

**8. Một executor task hoàn tất có đồng nghĩa pool đã dừng không?**  
Không. Pool có thể còn non-daemon worker đợi tác vụ mới; phải shutdown.

**9. Tại sao SpringApplication.run return mà web server vẫn chạy?**  
Web server và infrastructure có thể còn threads sống giữ process, độc lập với việc method main đã đi qua run.

**10. @Scheduled với virtual threads có tự giữ JVM sống không?**  
Không được bảo đảm. Virtual threads luôn daemon, nên Spring Boot khuyến nghị `spring.main.keep-alive=true` khi cần.

**11. Có thể dùng Thread.ofVirtual() trên Java 17 không?**  
Không. API virtual threads chính thức cần Java 21+.

**12. spring.main.keep-alive=true có hoàn tất mọi background task không?**  
Không. Nó giữ ứng dụng sống, không tự đồng bộ, timeout hay kiểm soát kết quả job.

**13. System.exit có đợi mọi non-daemon worker xong rồi mới shutdown không?**  
Không. Nó khởi động đường shutdown dù worker còn đang sống; cleanup phải được thiết kế riêng.

**14. Làm sao tìm nguyên nhân JVM không thoát?**  
Lấy thread dump bằng `jcmd PID Thread.print`/`jstack PID`, tìm live non-daemon thread, pool đang chờ và resource chưa đóng.

**15. Nếu Spring context đóng nhưng raw Thread do chính bạn tạo vẫn sống, JVM có thể còn chạy không?**  
Có, nếu thread đó non-daemon. Context close không tự interrupt mọi thread ngoài lifecycle quản lý.

## 19. Tài liệu chính thức để đối chiếu theo phiên bản

- [Oracle Java SE 17 — Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): daemon inheritance, `setDaemon`, `isDaemon`, `isAlive` và điều kiện JVM kết thúc.
- [Oracle Java SE 17 — Runtime API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt` và shutdown hooks.
- [Oracle Java SE 17 — Executors API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): default thread factory, thread pools.
- [Oracle Java SE 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `awaitTermination` và `isTerminated`.
- [Spring Boot 3.5 — SpringApplication / Virtual Threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): daemon virtual threads và `spring.main.keep-alive`.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured executors/schedulers và cấu hình virtual threads.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.main.keep-alive=false` theo mặc định.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual/platform threads, daemon semantics, `Thread.ofVirtual()`.
- [Oracle JDK 17 — jcmd tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print` và chẩn đoán JVM.

**Kết luận:** câu hỏi “JVM có còn chạy không?” phải được trả lời từ **vòng đời thật của non-daemon threads và chính sách shutdown/keep-alive**, không phải từ việc `main` đã return, tên `@Async` hay sự tồn tại của một lịch `@Scheduled`. Với các tác vụ quan trọng, hãy kết hợp thread policy, lifecycle resource, timeout/cancellation và quan sát thực tế để vừa không thoát sớm vừa không treo mãi.