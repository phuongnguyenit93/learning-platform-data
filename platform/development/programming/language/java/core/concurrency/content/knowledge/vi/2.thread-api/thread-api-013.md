# Thread.Builder: tạo platform thread, virtual thread và ThreadFactory theo cấu hình

## 1. Mục tiêu học tập và yêu cầu phiên bản

Thread.Builder là API chuẩn trong **Java 21+** giúp cấu hình và khởi tạo thread theo một cách thống nhất, dễ đọc: chọn **platform thread** hoặc **virtual thread**, đặt tên, quyết định có khởi động ngay không, và tạo ThreadFactory dùng lại cấu hình trong các executor.

Sau bài học, bạn có thể:

- Phân biệt Thread.ofPlatform() và Thread.ofVirtual(), cùng chi phí và trường hợp sử dụng của chúng.
- Dùng start(Runnable), unstarted(Runnable), factory() đúng vòng đời; biết chính xác lúc nào thread được khởi động.
- Cấu hình tên, kế thừa InheritableThreadLocal, uncaught exception handler và các thuộc tính riêng của platform thread.
- Cung cấp ThreadFactory cho ExecutorService mà không nhầm thread factory với chính sách lập lịch, giới hạn concurrency hoặc queue.
- Viết ứng dụng Java 21+ chạy được, chờ thread kết thúc đúng cách và xác định các giới hạn khi vận hành.

**Phạm vi:** Java SE/JVM concurrency, không bàn tới framework. **Điều kiện:** dùng JDK 21 hoặc mới hơn cho toàn bộ ví dụ; JDK 17 không hỗ trợ các API này. Virtual threads từng trải qua giai đoạn preview ở các bản JDK trước, nhưng phiên bản chính thức là Java 21.

## 2. Mô hình tư duy: builder → thread hoặc factory

Thread.Builder là một **interface**, có hai nhánh chuyên biệt:

~~~text
Thread.ofPlatform() → Thread.Builder.OfPlatform
                     ├─ start(task)     → platform thread đã start
                     ├─ unstarted(task) → platform thread ở NEW
                     └─ factory()      → ThreadFactory tạo platform thread

Thread.ofVirtual()  → Thread.Builder.OfVirtual
                     ├─ start(task)     → virtual thread đã start
                     ├─ unstarted(task) → virtual thread ở NEW
                     └─ factory()      → ThreadFactory tạo virtual thread
~~~

Thread.Builder không tự chạy một Runnable và không đại diện cho một thread đang sống. Nó là **bộ cấu hình để tạo ra các Thread riêng biệt**. Mỗi Thread có nhiệm vụ và vòng đời độc lập. Builder có thể cấu hình tên, handler và một số thuộc tính trước khi tạo Thread.

Ba cách kết thúc quá trình xây dựng:

| Lời gọi | Kết quả | Thread bắt đầu chạy chưa? | Sử dụng khi |
|---|---|---|---|
| builder.start(task) | Thread mới | Đã gọi start() để yêu cầu lịch chạy | Cần khởi tạo và chạy ngay. |
| builder.unstarted(task) | Thread mới | Chưa; trạng thái NEW | Muốn giữ tham chiếu, sắp xếp thứ tự khởi động rồi tự gọi start(). |
| builder.factory() | ThreadFactory | Chưa tạo thread nào chỉ bởi factory() | Muốn tái sử dụng cấu hình khi tạo nhiều thread hoặc đưa cho executor. |
| factory.newThread(task) | Thread mới chưa start | Chưa; caller hoặc executor sẽ start | Dùng factory theo hợp đồng java.util.concurrent.ThreadFactory. |

Ví dụ ngắn:

~~~java
Thread platform = Thread.ofPlatform()
        .name("report-worker")
        .unstarted(() -> System.out.println("work"));

System.out.println(platform.getState()); // NEW
platform.start();                         // mới bắt đầu chạy
platform.join();                          // đợi kết thúc
~~~

Trong ví dụ, chỉ lệnh xuất NEW được thực thi trước khi start() được gọi. Với code chạy trên nhiều thread, thứ tự các lệnh in giữa các thread có thể thay đổi: start() **không đồng nghĩa** Runnable đã hoàn tất trước khi lời gọi start() trả về. Để phụ thuộc vào kết quả, dùng join(), Future.get() hoặc cơ chế đồng bộ phù hợp.

## 3. Platform thread và virtual thread: cùng API, khác mô hình thực thi

**Platform thread** thường được JVM ánh xạ tới một native thread của hệ điều hành. Nó dùng native stack và scheduler hệ điều hành; số thread lớn có chi phí bộ nhớ, tạo/hủy và lập lịch.

**Virtual thread** được JVM lập lịch trên các platform carrier threads. Trong nhiều thao tác I/O chặn mà JDK hỗ trợ, virtual thread có thể tạm ngừng và nhường carrier cho việc khác. Nó thích hợp khi cần rất nhiều tác vụ đồng thời dành phần lớn thời gian **chờ I/O**. Virtual thread vẫn dùng Java Thread object, có stack logic và dữ liệu liên quan; không phải hoàn toàn miễn phí.

| Tiêu chí | Thread.ofPlatform() | Thread.ofVirtual() |
|---|---|---|
| Loại thread | Platform | Virtual |
| Gắn với native OS thread | Thông thường một platform thread có native thread tương ứng | Nhiều virtual threads chia sẻ các carrier platform threads theo lịch JVM |
| Chi phí số lượng lớn | Cao hơn do native thread/stack/scheduler | Thường thấp hơn cho nhiều tác vụ chờ, vẫn có giới hạn tài nguyên |
| Daemon | Tùy cấu hình hoặc thừa kế khi tạo | Luôn là daemon; không cấu hình được thành non-daemon |
| Priority tùy chỉnh | Có thể cấu hình, nhưng hiệu lực còn phụ thuộc JVM/OS | Priority cố định, không có API builder để chỉnh |
| ThreadGroup tùy chỉnh | Có thể cấu hình | Không có tùy chọn builder để gán group |
| Stack size gợi ý | Có thể dùng stackSize(long), phụ thuộc nền tảng | Không có stackSize trên OfVirtual |
| Trường hợp nổi bật | Công việc CPU có concurrency hữu hạn; pool worker có kiểm soát | Nhiều công việc blocking I/O cần mô hình mã tuần tự dễ đọc |

**Đừng đồng nhất virtual thread với chạy song song trên CPU.** Trên máy có P CPU hiệu dụng, hàng nghìn virtual threads không biến P thành hàng nghìn lõi. Với tác vụ CPU-bound dài, nhu cầu CPU vẫn là giới hạn và không nên mặc định virtual threads sẽ làm tác vụ nhanh hơn.

Thread.currentThread() trong mã chạy trên virtual thread trả về **virtual thread hiện tại**, không phải đối tượng carrier. Vì thế tên, ThreadLocal và trạng thái nên gắn với virtual thread logic của tác vụ, không suy đoán về một carrier cụ thể.

## 4. Cấu hình dùng chung trên hai builder

Cả OfPlatform và OfVirtual đều cung cấp các phương thức chung:

### 4.1. name(String) và name(String prefix, long start)

- name("job-runner") gán cùng một tên cố định cho mỗi Thread được builder tạo; tên **không bắt buộc duy nhất**.
- name("job-", 0) sinh tên lần lượt job-0, job-1, ... theo bộ đếm bắt đầu từ số không âm. Mỗi lần builder tạo Thread sẽ dùng và tăng bộ đếm.
- Khi gọi factory(), factory nhận trạng thái cấu hình và bản sao bộ đếm tại thời điểm tạo; các thread tạo bằng factory có chuỗi tên của factory đó. Không mặc định mọi factory có chung bộ đếm toàn ứng dụng.

Tên giúp phân biệt vai trò khi log, debug và theo dõi thread dump; nó không phải cơ chế tạo định danh bảo mật hoặc bảo đảm thứ tự thực thi.

### 4.2. inheritInheritableThreadLocals(boolean)

Điều khiển việc một thread mới **thừa hưởng giá trị ban đầu của InheritableThreadLocal** từ thread đang tạo nó. Giá trị mặc định là true; cấu hình false thường hữu ích khi muốn tránh vô tình mang ngữ cảnh của tác vụ cha sang thread con:

~~~java
ThreadFactory factory = Thread.ofVirtual()
        .name("isolated-", 0)
        .inheritInheritableThreadLocals(false)
        .factory();
~~~

Đây **không phải** công tắc tắt toàn bộ ThreadLocal. Tác vụ vẫn có thể tự đặt ThreadLocal; dữ liệu nên được xóa trong finally khi hết phạm vi sử dụng. Cũng không nên dùng InheritableThreadLocal làm cơ chế truyền ngữ cảnh nghiệp vụ tùy tiện qua các executor: thời điểm tạo thread, caller của factory và cơ chế tái sử dụng worker ảnh hưởng đến giá trị thừa kế. Khi cần dữ liệu cho một task, truyền qua tham số/đối tượng ngữ cảnh rõ ràng sẽ dễ kiểm soát hơn.

### 4.3. uncaughtExceptionHandler(handler)

Cấu hình cách tiếp nhận Throwable **không được xử lý** khiến Thread kết thúc bất thường:

~~~java
Thread t = Thread.ofPlatform()
        .name("reporter")
        .uncaughtExceptionHandler((thread, failure) ->
                System.err.println(thread.getName() + ": " + failure))
        .start(() -> {
            throw new IllegalStateException("failed");
        });
t.join();
~~~

Đoạn này là **mã minh họa đặt trong một phương thức có thể ném InterruptedException**, không phải chương trình Java độc lập. Handler không biến tác vụ lỗi thành thành công; nó hỗ trợ logging, cảnh báo và xử lý lỗi cuối cùng. Lưu ý khác biệt với ExecutorService.submit(...): nhiều executor **bắt ngoại lệ vào Future**, vì vậy lỗi thường xuất hiện khi gọi Future.get() dưới dạng ExecutionException thay vì truyền vào uncaught exception handler của Thread. Với tác vụ quan trọng, caller vẫn cần xử lý kết quả và lỗi của Future.

## 5. Cấu hình dành riêng cho platform thread

Chỉ Thread.Builder.OfPlatform có các tùy chọn sau:

| Tùy chọn | Ý nghĩa | Cảnh báo thực tế |
|---|---|---|
| daemon(boolean), daemon() | Quyết định trạng thái daemon; daemon() tương đương true | Daemon không giữ JVM sống khi mọi non-daemon threads đã kết thúc. |
| priority(int) | Chỉ định mức ưu tiên từ Thread.MIN_PRIORITY tới Thread.MAX_PRIORITY | Không bảo đảm thời gian chạy hay fairness; hiệu lực phụ thuộc hệ điều hành và giới hạn ThreadGroup. |
| group(ThreadGroup) | Gắn platform thread vào ThreadGroup | ThreadGroup là cơ chế cũ; không dùng làm giới hạn tài nguyên hoặc ranh giới bảo mật. |
| stackSize(long) | Gợi ý kích thước stack native khi tạo platform thread | JVM/OS có thể bỏ qua hoặc hiệu chỉnh; giá trị âm không hợp lệ, 0 có nghĩa bỏ qua gợi ý. |

Nếu không đặt daemon/priority/group, platform thread có thể thừa kế giá trị từ thread tạo ra nó theo quy tắc của Thread API. Vì vậy, để xác định rõ hành vi cho worker đặc biệt, hãy thiết lập thuộc tính quan trọng thay vì dựa vào ngữ cảnh không kiểm soát.

Ví dụ:

~~~java
Thread.Builder.OfPlatform builder = Thread.ofPlatform()
        .name("file-worker-", 0)
        .daemon(false)
        .priority(Thread.NORM_PRIORITY)
        .inheritInheritableThreadLocals(false);

Thread first = builder.unstarted(() -> performWork());
~~~

Đây là **đoạn trích minh họa**: performWork() là hàm giả định của ứng dụng, không phải ví dụ biên dịch độc lập. Cần gọi first.start() để chạy.

**stackSize không phải bảo đảm tài nguyên.** Đó là gợi ý về cỡ stack, không hứa JVM sẽ cấp đúng số byte và cũng không trực tiếp cho biết mức RAM vật lý đang dùng. Kích thước quá nhỏ có thể dẫn đến StackOverflowError khi stack sâu; quá lớn có thể giảm số native threads khả dụng. Không đặt giá trị chỉ dựa vào cảm tính.

### Virtual thread không có daemon(false), priority(...), group(...), stackSize(...)

Dùng các phương thức này trên kết quả Thread.ofVirtual() sẽ **không biên dịch**, vì OfVirtual không công bố chúng. Virtual threads luôn daemon và có mức ưu tiên cố định. Nếu muốn thiết lập số lượng tác vụ, deadline, giới hạn kết nối hoặc điều kiện thoát ứng dụng, hãy dùng cơ chế quản lý tác vụ, executor và đồng bộ, thay vì cố thay đổi các thuộc tính platform-only.

## 6. Ví dụ độc lập 1: tạo platform/virtual thread từ hai factory

Đây là chương trình Java 21+ đầy đủ, thể hiện cấu hình, name counter, newThread chưa start, start, join và cách nhận diện thread.

Lưu tệp **ThreadBuilderBasics.java**:

~~~java
import java.util.concurrent.ThreadFactory;

public class ThreadBuilderBasics {
    public static void main(String[] args) throws InterruptedException {
        ThreadFactory platformFactory = Thread.ofPlatform()
                .name("platform-worker-", 1)
                .daemon(false)
                .priority(Thread.NORM_PRIORITY)
                .inheritInheritableThreadLocals(false)
                .factory();

        ThreadFactory virtualFactory = Thread.ofVirtual()
                .name("virtual-task-", 1)
                .inheritInheritableThreadLocals(false)
                .factory();

        Thread p = platformFactory.newThread(() -> {});
        Thread v = virtualFactory.newThread(() -> {});
        System.out.println("before=" + p.getState() + "," + v.getState());

        p.start();
        v.start();
        p.join();
        v.join();

        System.out.println("platform=" + p.getName()
                + ", virtual=" + p.isVirtual()
                + ", daemon=" + p.isDaemon());
        System.out.println("virtual=" + v.getName()
                + ", virtual=" + v.isVirtual()
                + ", daemon=" + v.isDaemon());
        System.out.println("after=" + p.getState() + "," + v.getState());
    }
}
~~~

Biên dịch và chạy bằng JDK 21+:

~~~bash
javac --release 21 ThreadBuilderBasics.java
java ThreadBuilderBasics
~~~

Kết quả chính xác cho ví dụ:

~~~text
before=NEW,NEW
platform=platform-worker-1, virtual=false, daemon=false
virtual=virtual-task-1, virtual=true, daemon=true
after=TERMINATED,TERMINATED
~~~

**Phân tích kết quả:**

1. factory.newThread(...) tạo hai Thread ở trạng thái NEW; Runnable rỗng chưa chạy.
2. Tên được tạo từ tiền tố và bộ đếm bắt đầu từ 1, riêng biệt cho mỗi factory.
3. p.start() và v.start() bắt đầu hai đường thực thi. Không giả định thứ tự hai task vì việc lập lịch có thể thay đổi.
4. join() đợi cả hai hoàn tất rồi mới đọc trạng thái sau cùng; kết quả TERMINATED là ổn định.
5. isVirtual() xác định loại thread; isDaemon() cho thấy sự khác biệt platform/virtual. Platform được đặt daemon(false); virtual vốn luôn là daemon.

Lệnh javac --release 21 yêu cầu compiler hỗ trợ release 21 (JDK 21 trở lên); với JDK 17 sẽ báo không nhận API hoặc release. Bạn có thể thay Runnable rỗng bằng tác vụ thật nhưng cần tránh phụ thuộc vào thứ tự in console giữa các thread.

## 7. ThreadFactory làm gì, và không làm gì?

ThreadFactory là functional interface với một phương thức chính:

~~~java
Thread newThread(Runnable runnable);
~~~

Theo hợp đồng, newThread trả về **Thread chưa start**; đối tượng gọi factory (hoặc executor) chịu trách nhiệm khởi động. factory() từ Thread.Builder tạo một ThreadFactory phù hợp với cấu hình hiện tại. Factory do builder tạo **an toàn khi nhiều thread cùng gọi newThread**; bản thân Thread.Builder **không thread-safe**, không nên chia sẻ để các luồng khác nhau vừa chỉnh cấu hình vừa tạo thread.

Ví dụ dùng với một platform thread pool cố định:

~~~java
ThreadFactory workerFactory = Thread.ofPlatform()
        .name("cpu-worker-", 0)
        .daemon(false)
        .factory();

java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(4, workerFactory);

// Tác vụ thật do ứng dụng submit/execute; cần shutdown và chờ kết thúc.
~~~

Đây là **đoạn tích hợp vào phương thức**, không phải chương trình độc lập. Executor quyết định **bao nhiêu worker**, cách lấy việc và khi nào start worker; factory quyết định **cách tạo từng Thread**. newFixedThreadPool(4, ...) giới hạn số worker nhưng mặc định dùng **queue không giới hạn**; nó không tự bảo vệ ứng dụng khỏi vô số tác vụ chờ. Với tải cần backpressure, cân nhắc ThreadPoolExecutor có bounded queue, timeout và rejection policy rõ ràng.

Điểm dễ nhầm: tạo virtual ThreadFactory **không tự biến một fixed thread pool thành executor với một virtual thread cho từng task**. Fixed pool vẫn dùng một tập worker hữu hạn theo cơ chế executor đó; mỗi worker lấy nhiều task nối tiếp. Nếu muốn một virtual thread riêng cho mỗi task, dùng Executors.newVirtualThreadPerTaskExecutor() hoặc Executors.newThreadPerTaskExecutor(virtualFactory).

### Lựa chọn executor phù hợp

| Mục tiêu | Kết hợp hợp lý | Điều cần tự kiểm soát |
|---|---|---|
| Tối đa vài platform workers tái sử dụng | newFixedThreadPool(n, platformFactory) hoặc ThreadPoolExecutor | Queue, chính sách quá tải, timeout, shutdown. |
| Một virtual thread trên mỗi task, mặc định | Executors.newVirtualThreadPerTaskExecutor() | Số task nhận vào, tài nguyên downstream và hủy. |
| Một virtual thread trên mỗi task, tên/handler tùy chỉnh | Executors.newThreadPerTaskExecutor(Thread.ofVirtual().name("task-", 0).factory()) | Thread-per-task **không có trần số thread** riêng; cần giới hạn tài nguyên. |
| Tự kiểm soát vòng đời một ít Thread | builder.start(...) / unstarted(...), join() | Bắt đầu, kết thúc và xử lý lỗi thủ công. |

**Không sử dụng Executors.newThreadPerTaskExecutor(platformFactory) vô hạn** cho tải lớn khi chưa hiểu chi phí native thread. API này tạo thread mới cho mỗi task, không tái sử dụng như fixed pool và không có giới hạn thread nội tại.

## 8. Ví dụ độc lập 2: virtual ThreadFactory + executor + Semaphore

Một virtual thread cho mỗi tác vụ không có nghĩa hệ thống bên dưới chịu được vô hạn tác vụ đồng thời. Ví dụ dùng Semaphore cho phép nhiều virtual threads được tạo nhưng chỉ **hai tác vụ** vào một đoạn mô phỏng tài nguyên giới hạn cùng lúc.

Lưu tệp **VirtualFactoryExecutor.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadFactory;

public class VirtualFactoryExecutor {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual()
                .name("io-task-", 0)
                .inheritInheritableThreadLocals(false)
                .factory();
        Semaphore limit = new Semaphore(2);

        try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
            List<Future<String>> results = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                final int id = i;
                results.add(executor.submit(() -> {
                    limit.acquire();
                    try {
                        Thread.sleep(20);
                        return "completed-" + id;
                    } finally {
                        limit.release();
                    }
                }));
            }
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac --release 21 VirtualFactoryExecutor.java
java VirtualFactoryExecutor
~~~

Kết quả:

~~~text
completed-0
completed-1
completed-2
completed-3
~~~

**Vì sao output có thứ tự cố định?** Công việc thực thi có thể hoàn thành không theo thứ tự, nhưng chương trình lưu Future theo thứ tự submit và in kết quả bằng vòng lặp qua danh sách đó. Future.get() chờ task tương ứng hoàn tất, không dựa vào thời điểm kết quả được xử lý.

**Vì sao finally đặt sau acquire()?** Thread chỉ release permit sau khi acquire() thành công. Nếu bị interrupt trong lúc đợi acquire(), ngoại lệ được ném trước khi vào try/finally nên không giải phóng permit của người khác. Sau khi đã lấy permit, sleep() có thể bị interrupt; finally vẫn chạy để trả permit.

**Vì sao try-with-resources?** Từ Java 21, ExecutorService có thể đóng bằng try-with-resources; close() thực hiện shutdown có trật tự và chờ tác vụ hoàn tất. Đối với ứng dụng có thời hạn nghiêm ngặt, có thể cần chính sách timeout, cancel và shutdown phù hợp thay vì để chờ vô hạn.

**Giới hạn của ví dụ:** Semaphore đặt trần truy cập tài nguyên mô phỏng, **không** giới hạn số virtual threads được executor tạo hay số task nhận vào. Một ứng dụng thật vẫn cần cơ chế bounded admission/backpressure, deadline, giới hạn connection, memory và queue upstream. Thread.sleep(20) dùng để minh họa chờ; không phải benchmark tốc độ hoặc chứng minh lợi thế hiệu năng.

## 9. Cấu hình và quản lý lỗi trong ứng dụng thật

### 9.1. Tạo task và quản lý vòng đời

- Nếu tự dùng builder.start(...), luôn giữ tham chiếu cần thiết để join() hoặc dùng cơ chế phối hợp nếu tiến trình phải chờ kết quả.
- Virtual thread là daemon: JVM có thể bắt đầu kết thúc khi không còn non-daemon threads; việc tạo virtual threads **không đủ** để bảo đảm tác vụ quan trọng hoàn thành trước khi process thoát.
- Nếu dùng executor, bảo đảm shutdown/close, đợi task hoặc áp chính sách cancellation khi quá thời hạn.
- Không start() một Thread lần thứ hai: Thread đã khởi động, dù hoàn thành, không thể được tái khởi động và sẽ ném IllegalThreadStateException. Có thể tạo **Thread mới từ cùng factory**.

### 9.2. Hủy và interrupt

Thread.interrupt() không cưỡng bức giết task tại mọi thời điểm. Nhiều API blocking phản ứng bằng InterruptedException, nhưng tác vụ phải hợp tác kiểm tra và thoát đúng cách. Trong đoạn bắt InterruptedException mà chưa thể ném tiếp, thường nên gọi Thread.currentThread().interrupt() để khôi phục cờ rồi kết thúc tác vụ hoặc trao quyền quyết định cho caller.

Với ExecutorService.submit(...), lỗi tác vụ được đóng gói trong Future; Future.get() có thể ném ExecutionException. Future.cancel(true) yêu cầu interrupt khi có thể, không chứng minh resource đã được giải phóng hoặc tác vụ đã đạt trạng thái nghiệp vụ thành công.

### 9.3. Handler không thay thế xử lý lỗi nghiệp vụ

uncaughtExceptionHandler dùng cho lỗi không được xử lý ở Thread top-level. Nó không phải cơ chế retry, không tự ghi rollback và không thay thế Future.get(). Nếu handler tự ném lỗi, runtime không bảo đảm cung cấp xử lý bổ sung theo ý bạn. Giữ handler đơn giản, tránh thêm tác vụ rủi ro trong handler.

### 9.4. Ngữ cảnh thread và dữ liệu

InheritableThreadLocal mặc định có thể truyền dữ liệu vào thread con; trong pool, worker có thể được tạo tại thời điểm khác xa lúc submit. Với virtual thread-per-task, số thread lớn khiến dữ liệu trong ThreadLocal có thể tăng chi phí bộ nhớ. Không dùng ThreadLocal để cache đối tượng lớn cho mỗi virtual thread; tránh mang dữ liệu nhạy cảm hoặc mutable state không kiểm soát giữa các task. Truyền tham số rõ ràng, giới hạn vòng đời và cleanup trong finally khi cần.

## 10. Những hiểu nhầm thường gặp

**“Thread.Builder tương tự một ExecutorService.”** Sai. Builder mô tả **một cách tạo Thread**; executor quyết định **nhận task, queue, lập lịch giao việc, shutdown**. ThreadFactory cũng chỉ có trách nhiệm tạo Thread, không tự quản lý hàng đợi.

**“factory.newThread(task) sẽ chạy task ngay.”** Sai. Nó trả Thread chưa start. Nếu tự sử dụng, phải gọi start(); nếu giao cho executor, chính executor quản lý việc start.

**“Có thể đổi daemon, priority hay stackSize của virtual thread qua builder.”** Sai. Các API đó chỉ có trên OfPlatform. Virtual thread luôn daemon, có priority cố định, và không cung cấp tuỳ chỉnh native stack qua builder.

**“name("worker") tạo tên duy nhất cho mọi thread.”** Sai. Nó cố định tên. Muốn có chuỗi tên, dùng name("worker-", start).

**“Builder có thể dùng từ nhiều luồng một cách tự do.”** Sai. Thread.Builder không thread-safe; ThreadFactory do builder.factory() tạo là thread-safe. Hãy hoàn thiện cấu hình và chia sẻ factory, tránh concurrent mutation của builder.

**“Tạo hàng triệu virtual threads luôn an toàn.”** Sai. Mỗi task vẫn mang bộ nhớ, đối tượng, tham chiếu và có thể giữ connection, mutex, file descriptor hay gọi service khác. Cần giới hạn tải vào và tài nguyên đắt tiền theo mức thật sự.

**“Virtual threads tạo nhiều CPU hơn.”** Sai. Chúng giúp khai thác thời gian chờ blocking I/O, không tăng năng lực phần cứng. Với tác vụ tính toán nặng, giới hạn song song có kiểm soát vẫn quan trọng.

**“Không cần biết hiện tượng pinning hoặc blocking.”** Không chính xác. Khả năng JVM nhường carrier khi virtual thread chặn phụ thuộc loại thao tác và phiên bản JDK; native calls, native/foreign code hoặc cơ chế đồng bộ trong một số JDK có thể cản trở unmount. Ví dụ, vấn đề pinning liên quan synchronized đã được cải thiện đáng kể ở JDK mới hơn so với JDK 21. Phải quan sát và thử đúng bản runtime đang triển khai, không áp kết luận cho mọi version.

**“ThreadMXBean.getThreadCount() là tổng số platform + virtual threads.”** Sai trong Java 21: java.lang.management.ThreadMXBean theo dõi **platform threads**, không đếm virtual threads. Nếu số thread trong hệ thống tăng chủ yếu vì virtual threads, số liệu từ MXBean sẽ không phản ánh hết số tác vụ đang chạy.

**“Tăng thread priority sửa được vấn đề throughput.”** Không có bảo đảm. Lập lịch còn phụ thuộc tải, OS, CPU, waiting, locks và quota container. Priority không phải công cụ thay thế đo đạc.

## 11. Quan sát và gỡ lỗi

Kiểm tra vấn đề theo thứ tự từ biểu hiện đến nguyên nhân:

| Triệu chứng | Cần quan sát | Hướng xử lý |
|---|---|---|
| Không thấy tác vụ chạy | Thread ở NEW? Có gọi start() không? Executor đã shutdown chưa? | Phân biệt unstarted/newThread với start; kiểm tra lifecycle. |
| Thread tên trùng nhau | Dùng name(String) hay name(prefix, start)? | Đặt tên theo chuỗi tăng và phân loại vai trò tác vụ. |
| Process thoát khi task chưa xong | Chỉ còn daemon/virtual threads? | Join/Future.get/close executor, thiết kế shutdown đúng. |
| Số platform threads hoặc native memory tăng | Có tạo OS thread per-task? Pool/queue cấu hình thế nào? | Giới hạn worker, reusing pool, đo native stack/OS limits. |
| Virtual tasks tạo nhiều nhưng latency tăng | Backend, connection pool, semaphore, queue, timeout | Đặt giới hạn tài nguyên downstream và backpressure. |
| Lỗi bị “mất” | Dùng submit() nhưng không đọc Future? | Đọc Future.get(), ghi nhận lỗi từ task; handler không thay thế. |
| ThreadLocal giữ dữ liệu ngoài ý muốn | Pool reuse, inheritable values, cleanup | Truyền context tường minh, remove() đúng scope. |

Để chẩn đoán thực tế, đặt tên worker/virtual task có ý nghĩa, dùng Java Flight Recorder (JFR) và các công cụ thread dump phù hợp với **phiên bản JDK**. Quan sát song song CPU, memory, context switches, task count, queue depth, downstream latency và cancellation. Với platform threads, ThreadMXBean hoặc OS thread tools có ích; với virtual threads, dùng thêm công cụ quan sát hỗ trợ virtual-thread events/dumps vì nhiều phép đếm thread cổ điển chỉ phản ánh platform threads.

Không chạy phép đo hàng triệu thread trên máy không có giới hạn tài nguyên thử nghiệm: hiệu năng bị chi phối bởi cả workload, CPU, native memory, heap, kết nối và thời gian chờ. Ví dụ chạy được trong bài chứng minh ngữ nghĩa API, **không** tự nó so sánh tốc độ platform và virtual threads.

## 12. Sơ đồ quyết định và checklist

~~~text
Cần tạo Thread Java 21+?
  │
  ├─ Một ít công việc, tự quản lý vòng đời
  │      └─ Thread.ofPlatform()/ofVirtual()
  │           → cấu hình → start(...) hoặc unstarted(...).start()
  │           → join()/xử lý lỗi
  │
  └─ Nhiều tác vụ và cần quản lý kết quả/đóng tài nguyên
         │
         ├─ CPU-bound hoặc cần giới hạn số worker native
         │      └─ platform ThreadFactory + executor có số worker/queue hợp lý
         │
         └─ Chủ yếu blocking I/O, nhiều tác vụ đồng thời
                └─ virtual ThreadFactory + thread-per-task executor
                     + giới hạn tài nguyên downstream, timeout, backpressure
~~~

Trước khi áp dụng vào ứng dụng thật, xác nhận:

1. Đã dùng JDK 21+ và hiểu sự khác nhau giữa builder.start, builder.unstarted, factory.newThread.
2. Đã chọn đúng kiểu thread cho workload và xác định rõ ai start, ai join, ai đóng executor.
3. Đã đặt tên mô tả vai trò và không coi name là ID duy nhất.
4. Đã dùng đúng tùy chọn: daemon/priority/group/stackSize dành cho platform; virtual không tùy biến các thuộc tính đó.
5. Đã cân nhắc thừa kế InheritableThreadLocal, xử lý uncaught exception, Future lỗi và interrupt.
6. Đã giới hạn kết nối/tài nguyên đắt tiền, quyết định mức nhận task và chính sách khi quá tải.
7. Đã đo đúng runtime/OS đang dùng, tránh đánh giá virtual concurrency bằng riêng MXBean platform-thread metrics.

## 13. Tài liệu API gốc để tra cứu

- Thread.Builder (Java 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html
- Thread.Builder.OfPlatform: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfPlatform.html
- Thread.Builder.OfVirtual: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html
- ThreadFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html
- Executors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- ThreadMXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html

**Điểm cần nhớ:** Thread.Builder làm rõ **loại thread và cấu hình tạo thread**; start()/unstarted()/factory() làm rõ **thời điểm và cách khởi tạo**. ThreadFactory chuyển cấu hình vào hạ tầng quản lý task nhưng không thay thế executor, giới hạn concurrency, xử lý lỗi hay shutdown. Platform thread và virtual thread chia sẻ nhiều API Thread, song có đặc tính tài nguyên và lựa chọn vận hành khác nhau.
