# Thiết kế stop/shutdown cho lịch chạy định kỳ trong Java

## 1. Vấn đề: dừng một lịch không đồng nghĩa dừng công việc đang chạy

Trong Java Concurrency, **ScheduledExecutorService** cho phép lập lịch tác vụ một lần hoặc lặp lại theo chu kỳ. Hai phương thức thường gặp là **scheduleAtFixedRate(...)** và **scheduleWithFixedDelay(...)**; cả hai trả về **ScheduledFuture<?>**, đại diện cho lịch chạy định kỳ.

Một thành phần định kỳ như bộ thu thập metric, kiểm tra trạng thái, đồng bộ dữ liệu hoặc tác vụ bảo trì cần được thiết kế vòng đời rõ ràng. Khi ứng dụng dừng, có thể cần:

1. **Không kích hoạt lượt mới** sau khi nhận yêu cầu stop.
2. **Cho lượt đang chạy hoàn tất** nếu còn trong thời hạn cho phép.
3. **Đề nghị ngắt lượt đang chạy** nếu quá thời hạn hoặc cần dừng nhanh.
4. **Chờ tài nguyên thực sự kết thúc** và báo lại trạng thái shutdown.
5. **Đảm bảo khởi động/dừng nhiều lần không tạo lịch trùng** hoặc dùng executor đã shutdown.

Đây là các yêu cầu khác nhau. **ScheduledFuture.cancel(...)** tác động đến lịch của một tác vụ; **executor.shutdown()/shutdownNow()** tác động đến executor; **awaitTermination(...)** đợi executor kết thúc. Muốn bảo đảm an toàn phải phối hợp chúng và thiết kế tác vụ hợp tác với tín hiệu dừng.

Bài học chỉ dùng các API lập lịch và đồng bộ thuộc thư viện chuẩn Java, không gắn với vòng đời của framework.

## 2. Hiểu đúng scheduleAtFixedRate và scheduleWithFixedDelay

| API | Cách xác định thời điểm chạy tiếp | Lưu ý khi dừng |
|---|---|---|
| **scheduleAtFixedRate(task, initialDelay, period, unit)** | Mốc dự kiến: bắt đầu + k × period | Nếu một lần chạy lâu hơn period, lần sau có thể bắt đầu muộn; không chạy chồng các lần của **chính lịch đó** |
| **scheduleWithFixedDelay(task, initialDelay, delay, unit)** | Lần sau bắt đầu sau khi lần trước **kết thúc** rồi chờ delay | Dễ kiểm soát khoảng nghỉ giữa các lượt; cũng không chạy chồng các lần của **chính lịch đó** |

Cả hai phương thức trả về một **ScheduledFuture** của **cả chuỗi định kỳ**, không phải một Future riêng cho từng lần chạy. Future của lịch đang tiếp tục bình thường thường có **isDone() == false** ngay cả khi nhiều lượt đã hoàn tất. Đừng gọi **get()** không thời hạn để “lấy kết quả của lượt vừa chạy”: lời gọi có thể chờ đến khi toàn bộ lịch kết thúc vì bị hủy hoặc do lỗi.

Nếu một lượt chạy định kỳ ném ngoại lệ ra khỏi Runnable, **những lần chạy tiếp theo bị ngăn lại** theo hợp đồng ScheduledExecutorService. Vì thế log, metrics và quy tắc xử lý exception trong Runnable là một phần của thiết kế stop/shutdown: lịch ngừng do lỗi không tương đương với stop có chủ đích.

Đặc biệt, **không có hai lần thực thi của cùng một periodic task chạy đồng thời** trong ScheduledThreadPoolExecutor; tuy nhiên hai task định kỳ **khác nhau** có thể song song nếu executor có nhiều worker. Một lượt chạy quá lâu làm lịch fixed-rate bị trễ, nhưng không tạo lượt thứ hai chồng lên chính lượt đó.

## 3. Bốn cơ chế cần phân biệt

| API | Phạm vi | Tác động chính |
|---|---|---|
| **ScheduledFuture.cancel(false)** | Một lịch/tác vụ | Nếu hủy thành công, ngăn các lần chạy sau, **không yêu cầu interrupt** lượt đang chạy |
| **ScheduledFuture.cancel(true)** | Một lịch/tác vụ | Nếu hủy thành công, có thể yêu cầu **interrupt** thread đang chạy; không bảo đảm task dừng ngay |
| **ExecutorService.shutdown()** | Cả executor | Từ chối tác vụ mới và thực hiện shutdown có trật tự theo chính sách của executor |
| **ExecutorService.shutdownNow()** | Cả executor | Cố gắng dừng tác vụ đang chạy bằng interrupt, ngăn xử lý tác vụ đang đợi và trả danh sách tác vụ chưa khởi chạy |
| **ExecutorService.awaitTermination(timeout, unit)** | Cả executor | Chặn thread gọi để đợi toàn bộ executor kết thúc hoặc hết hạn; trả về boolean |

**shutdown() không phải awaitTermination().** shutdown phát tín hiệu bắt đầu dừng rồi trả về; worker có thể vẫn đang chạy. Gọi **isShutdown()** chỉ cho biết executor đã nhận shutdown. **isTerminated()** mới cho biết nó đã kết thúc tất cả tác vụ sau shutdown. **awaitTermination() == false** nghĩa là đã hết thời hạn đợi mà executor chưa kết thúc; không có nghĩa thao tác shutdown “không được chấp nhận”.

**shutdownNow() cũng không phải “kill thread”.** Java interruption là cơ chế hợp tác. Tác vụ đang tính toán không kiểm tra interrupt, chờ trên I/O không phản hồi interrupt hoặc mắc ở thư viện ngoài vẫn có thể tiếp tục. Không được cam kết mọi task hay side effect đã chấm dứt chỉ vì shutdownNow() đã trả về.

**cancel() và kết quả thực thi:** Future được hủy thành công sẽ báo **isCancelled() == true**, **isDone() == true**, và **get()** ném CancellationException. Tuy vậy một lượt đang chạy có thể vẫn tiếp tục khi đã gọi cancel(false), nên trạng thái Future không phải xác nhận lượt xử lý bên trong đã thực sự thoát.

## 4. Chính sách riêng của ScheduledThreadPoolExecutor

**ScheduledThreadPoolExecutor** là implementation linh hoạt của ScheduledExecutorService. Nó có các chính sách quan trọng trong shutdown:

| Chính sách | Mặc định | Ý nghĩa |
|---|---|---|
| **getContinueExistingPeriodicTasksAfterShutdownPolicy()** | **false** | Các lượt định kỳ hiện có **không tiếp tục** sau shutdown() mặc định |
| **getExecuteExistingDelayedTasksAfterShutdownPolicy()** | **true** | Tác vụ delayed **một lần** đã xếp lịch được tiếp tục sau shutdown() mặc định |
| **getRemoveOnCancelPolicy()** | **false** | Task bị cancel có thể còn trong delay queue đến khi đến hạn theo cách dọn mặc định |

Điều này tạo khác biệt quan trọng: gọi **shutdown()** trên ScheduledThreadPoolExecutor mặc định dừng các chuỗi định kỳ, nhưng **các tác vụ một lần đã đặt lịch rất xa trong tương lai có thể vẫn khiến executor chưa terminate**. Nếu muốn lúc shutdown không chạy các one-shot delayed task chưa tới hạn, chủ sở hữu executor có thể thiết lập:

~~~java
scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
~~~

Khi có nhiều lịch hủy sớm, cân nhắc:

~~~java
scheduler.setRemoveOnCancelPolicy(true);
~~~

Thiết lập này giúp loại bỏ task bị cancel khỏi queue sớm hơn, tránh giữ tham chiếu lâu không cần thiết; không làm cho shutdownNow trở thành cơ chế ngắt cưỡng bức. Hai dòng trên là **mã minh họa** trong phạm vi biến scheduler kiểu ScheduledThreadPoolExecutor, không phải chương trình độc lập.

**Không bật** setContinueExistingPeriodicTasksAfterShutdownPolicy(true) nếu mục tiêu là dừng tất cả lịch định kỳ lúc shutdown. Chính sách true có thể giữ các periodic task tiếp tục thực thi sau shutdown, khiến executor không kết thúc theo cách mong muốn. Nếu dùng true vì một nghiệp vụ đặc biệt, phải có thao tác cancel rõ ràng và kiểm tra termination.

**Phạm vi:** các phương thức điều chỉnh chính sách trên thuộc **ScheduledThreadPoolExecutor**, không phải hợp đồng chung của mọi triển khai ScheduledExecutorService. Nếu được truyền một ScheduledExecutorService bất kỳ, chỉ dựa vào các phương thức của interface hoặc xác định rõ implementation đang sở hữu.

## 5. Trình tự graceful stop khuyến nghị

Với một component **sở hữu riêng** một ScheduledThreadPoolExecutor và một hoặc vài lịch định kỳ, trình tự tiêu biểu là:

1. **Chặn yêu cầu start/schedule mới.** Đánh dấu trạng thái STOPPING với đồng bộ phù hợp để thread khác không tạo thêm lịch trong khi đang dừng.
2. **Lưu handle ScheduledFuture khi bắt đầu**, rồi **cancel(false)** để ngăn lượt mới mà không chủ động interrupt lượt đang chạy.
3. **Gọi shutdown()** lên executor mà component sở hữu. Nếu executor dùng chung, **không tự shutdown** tài nguyên do thành phần khác quản lý: chỉ cancel các lịch thuộc quyền sở hữu của mình.
4. **awaitTermination** với thời gian có hạn, từ một thread điều phối bên ngoài worker đang chạy. Kiểm tra kết quả trả về.
5. Nếu quá hạn và chính sách cho phép, gọi **shutdownNow()** để đề nghị interrupt, sau đó chờ thêm một thời hạn có hạn.
6. **Xử lý InterruptedException** ở thread điều phối: thường gọi shutdownNow() theo chính sách của hệ thống, khôi phục interrupt flag rồi trả/lan truyền trạng thái ngắt.
7. **Đóng tài nguyên phụ thuộc** sau khi đã bảo đảm các task không còn sử dụng chúng, hoặc có quy ước dừng an toàn nếu tác vụ không phản hồi interrupt.

Không đóng HTTP client, file hoặc connection pool **trước** khi lượt đang chạy ngừng sử dụng nếu điều đó khiến tác vụ lỗi giữa chừng. Mặt khác, nếu I/O có thể chờ vô thời hạn, cần timeout ở tầng I/O và cơ chế giải phóng độc lập; chỉ chờ executor chưa đủ.

### Bất biến cần giữ

- Sau khi STOPPING, không một lời gọi **start()** cạnh tranh nào được chấp nhận.
- Với mỗi lịch định kỳ, chỉ có **một** ScheduledFuture handle có hiệu lực trong một vòng đời.
- **stop()** phải idempotent hoặc nêu rõ hợp đồng cho lần gọi lặp lại.
- Một executor đã shutdown **không thể sử dụng để schedule lại**: thường tạo một instance service/executor mới cho vòng đời mới.
- Tránh giữ lock dài trong lúc awaitTermination: task đang chạy có thể cần lock đó để thoát, gây deadlock.
- Không đợi awaitTermination ngay **bên trong chính worker** mà executor đang chờ kết thúc.

## 6. Ví dụ Java 17: stop êm, để lượt đang chạy kết thúc

Ví dụ cố ý dùng **CountDownLatch** để kiểm soát thời điểm: worker bắt đầu một lượt rồi đợi, main gọi **cancel(false)** khi lượt đó chưa xong, mở khóa cho nó hoàn tất, gọi shutdown() và đợi executor kết thúc. Đặt delay giữa các lượt bằng 1 ngày chỉ để ví dụ luôn quan sát **một lượt**; đây không phải chu kỳ được đề xuất cho ứng dụng thực.

Lưu tệp **GracefulPeriodicStopDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class GracefulPeriodicStopDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger runs = new AtomicInteger();

        try {
            ScheduledFuture<?> periodic = scheduler.scheduleWithFixedDelay(
                    () -> {
                        runs.incrementAndGet();
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                        }
                    },
                    0, 1, TimeUnit.DAYS
            );

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            // Lượt hiện tại còn đang đợi release.
            boolean cancelled = periodic.cancel(false);
            release.countDown();
            scheduler.shutdown();
            boolean terminated = scheduler.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("cancel accepted=" + cancelled);
            System.out.println("runs=" + runs.get());
            System.out.println("future cancelled=" + periodic.isCancelled());
            System.out.println("executor terminated=" + terminated);
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac GracefulPeriodicStopDemo.java
java GracefulPeriodicStopDemo
~~~

Đầu ra kỳ vọng trong điều kiện máy có khả năng thực thi bình thường và hoàn tất trong thời hạn 5 giây:

~~~text
cancel accepted=true
runs=1
future cancelled=true
executor terminated=true
~~~

**Vì sao kiểm chứng được?** Latch started bảo đảm lượt đầu đã vào thân Runnable, còn latch release khiến lượt đó chưa kết thúc trước khi cancel(false). Cancel thành công chuyển Future sang canceled, nhưng **không chủ động ngắt** worker. Sau release, worker hoàn tất; shutdown và awaitTermination chờ toàn bộ executor ngừng. Trong finally, shutdownNow() là lớp phòng vệ khi đường đi thông thường không hoàn tất; nó không xóa kết quả stop êm đã quan sát.

**Quan trọng:** không dùng Thread.sleep(...) và hy vọng main “kịp cancel” trước worker. Cách đó phụ thuộc timing và dễ tạo ví dụ kết quả không ổn định.

## 7. Ví dụ Java 17: quá hạn graceful shutdown rồi đề nghị interrupt

Nếu một lượt đang chạy không hợp tác kết thúc trong khoảng grace period, chương trình cần có chính sách chuyển cấp. Ví dụ này dùng latch để giữ worker đợi; shutdown() không interrupt worker, nên awaitTermination trong thời hạn ngắn sẽ trả false. Sau đó shutdownNow() gửi interrupt, cho worker thoát khỏi CountDownLatch.await().

Lưu **EscalatingShutdownDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class EscalatingShutdownDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocker = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
                    () -> {
                        started.countDown();
                        try {
                            blocker.await();
                        } catch (InterruptedException interrupted) {
                            sawInterrupt.set(true);
                            Thread.currentThread().interrupt();
                        }
                    },
                    0, 1, TimeUnit.DAYS
            );

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            periodic.cancel(false);
            scheduler.shutdown();
            boolean graceful = scheduler.awaitTermination(30, TimeUnit.MILLISECONDS);

            if (!graceful) {
                scheduler.shutdownNow();
            }
            boolean terminated = scheduler.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("graceful=" + graceful);
            System.out.println("interrupt seen=" + sawInterrupt.get());
            System.out.println("terminated=" + terminated);
        } finally {
            blocker.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac EscalatingShutdownDemo.java
java EscalatingShutdownDemo
~~~

Trong điều kiện JDK/scheduler đáp ứng và không vượt quá thời hạn 5 giây:

~~~text
graceful=false
interrupt seen=true
terminated=true
~~~

**Giải thích:** cancel(false) dừng lịch nhưng worker đang chờ latch vẫn chưa xong. shutdown() từ chối task mới và bắt đầu dừng executor; grace period 30 ms hết trong khi worker vẫn bị chặn, vì vậy graceful=false. shutdownNow() thử interrupt, khiến CountDownLatch.await() ném InterruptedException. Worker ghi nhận tín hiệu, khôi phục interrupt flag và thoát; executor mới có thể terminate.

Lớp phòng vệ finally đảm bảo không giữ latch mãi nếu có exception. Trong một hệ thống thực, **shutdownNow có thể không khiến task thoát**, nên sau awaitTermination vẫn phải kiểm tra boolean. Nếu terminated=false, cần báo trạng thái stop không hoàn tất, ghi metric/alert, áp timeout cho I/O hoặc thực hiện quy trình phục hồi tương ứng.

## 8. Mẫu quản lý vòng đời có tính idempotent

Trong ứng dụng, yêu cầu stop có thể đến từ nhiều đường đi hoặc cùng lúc với start. Một mẫu đơn giản là **đồng bộ phần chuyển trạng thái**, còn việc chờ task thực thi phải làm **ngoài khóa**. Ví dụ dưới đây tạo executor một lần; stop nhiều lần không gọi schedule lại và không chờ trong synchronized block.

Lưu **PeriodicLifecycleDemo.java**:

~~~java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PeriodicLifecycleDemo {
    private final ScheduledThreadPoolExecutor scheduler =
            new ScheduledThreadPoolExecutor(1);

    private ScheduledFuture<?> periodic;
    private boolean stopping;

    public synchronized void start() {
        if (stopping || periodic != null) {
            throw new IllegalStateException("Already started or stopping");
        }
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        periodic = scheduler.scheduleWithFixedDelay(
                () -> System.out.println("tick"),
                1, 1, TimeUnit.DAYS
        );
    }

    public boolean stop(long timeout, TimeUnit unit)
            throws InterruptedException {
        synchronized (this) {
            if (!stopping) {
                stopping = true;
                if (periodic != null) {
                    periodic.cancel(false);
                }
                scheduler.shutdown();
            }
        }

        if (scheduler.awaitTermination(timeout, unit)) {
            return true;
        }
        scheduler.shutdownNow();
        return scheduler.awaitTermination(timeout, unit);
    }

    public static void main(String[] args) throws InterruptedException {
        PeriodicLifecycleDemo service = new PeriodicLifecycleDemo();
        service.start();
        boolean stopped = service.stop(5, TimeUnit.SECONDS);
        System.out.println("stopped=" + stopped);
    }
}
~~~

Chạy:

~~~bash
javac PeriodicLifecycleDemo.java
java PeriodicLifecycleDemo
~~~

Đầu ra bình thường:

~~~text
stopped=true
~~~

Chương trình đặt initialDelay một ngày nên không có "tick" trước lúc stop. start() và phần chuyển sang STOPPING đồng bộ trên cùng monitor; việc awaitTermination xảy ra ngoài monitor. Lời gọi stop lần hai không lặp lại bước cancel/shutdown nhưng vẫn có thể chờ executor. **Lưu ý:** nếu hai caller cùng vào stop lúc grace period đang hết, cả hai có thể thử shutdownNow; để có một coordinator duy nhất cho toàn bộ pha chờ, dùng state machine và một completion signal riêng. Ở quy mô lớn, cần xác định rõ ai sở hữu quyền dừng, deadline tuyệt đối, cách thu lỗi và cách báo trạng thái.

Với xử lý InterruptedException trong stop, tầng điều phối thường gọi shutdownNow theo chính sách và **khôi phục interrupt flag** nếu không truyền ngoại lệ lên. Ví dụ trên cố ý khai báo **throws InterruptedException** để bên gọi quyết định; nó không che giấu việc caller bị interrupt.

### Trường hợp executor dùng chung

Nếu executor được chia sẻ giữa nhiều component, **component không sở hữu executor chỉ nên cancel ScheduledFuture của chính mình**. Nếu tự gọi shutdown(), nó có thể làm ngừng lịch và task của các bên khác. Chủ sở hữu executor tập trung có trách nhiệm cuối cùng với shutdown và awaitTermination. Khi service cần bảo đảm không nhận thêm việc, cần đồng bộ stop/start ngay trong service thay vì chỉ trông đợi vào trạng thái của executor.

## 9. Viết Runnable phản hồi tín hiệu dừng

Việc hủy Future hoặc interrupt worker không tự động kết thúc mọi mã Java. Hãy xây dựng công việc theo hướng hợp tác:

- **Kiểm tra trạng thái stop/interrupted** tại các điểm an toàn trước bước xử lý dài hoặc giữa các batch.
- **Dùng timeout I/O có hạn**, vì nhiều lời gọi I/O có thể không phản hồi Thread.interrupt() như mong muốn.
- **Không nuốt InterruptedException** rồi tiếp tục vòng lặp như không có yêu cầu dừng; thường khôi phục interrupt flag và thoát sớm hoặc truyền ngoại lệ.
- **Dọn dẹp trong finally / try-with-resources** cho tài nguyên của riêng lượt chạy; tránh giữ lock trong lúc chờ I/O lâu.
- **Không mở thêm tác vụ vô hạn** vào executor khác khi đã STOPPING; cần cancel/await cả các task con nếu muốn báo stop hoàn tất thực sự.
- **Giữ nghiệp vụ nhất quán:** cancel không rollback gửi HTTP, ghi file, transaction hay publish event đã xảy ra. Với retry, dùng idempotency và/hoặc giao dịch/compensation phù hợp.

Ví dụ pseudo-code cho một lượt có xử lý dữ liệu theo batch:

~~~java
void runBatch() {
    for (Batch batch : inputBatches) {
        if (stopping.get() || Thread.currentThread().isInterrupted()) {
            return;
        }
        processOneBatchWithTimeout(batch);
    }
}
~~~

Đây là **đoạn minh họa, không phải chương trình biên dịch độc lập**: stopping là AtomicBoolean do component sở hữu, inputBatches và processOneBatchWithTimeout là logic nghiệp vụ giả định. Điểm chính là kiểm tra stop tại ranh giới batch, không ngắt dữ liệu đang ghi giữa chừng khi chưa thiết kế được cách phục hồi.

### Nếu task bị lỗi và dừng lịch ngoài ý muốn

Với một Runnable được scheduleAtFixedRate/scheduleWithFixedDelay, exception không được bắt sẽ làm ngừng những lần chạy sau. Có thể chủ động catch, log và xác định lỗi nào được phép retry; tuy nhiên **không nuốt tất cả lỗi rồi chạy vô hạn**. Nên có ngưỡng lỗi liên tiếp, backoff, trạng thái sức khỏe và cách báo lịch đã hỏng. Cần phân biệt rõ: stopped do yêu cầu quản lý, canceled, và failed do lỗi.

## 10. Quyết định thời gian chờ và xử lý quá hạn

Một chính sách shutdown phải trả lời ba câu hỏi: **cho task hiện tại thêm bao lâu**, **khi hết hạn thì làm gì**, và **nếu đã gửi interrupt mà task vẫn chưa thoát thì sao**.

Ví dụ về thứ tự:

~~~text
RUNNING
   |
   | yêu cầu stop
   v
STOPPING: không nhận lịch mới
   |
   | cancel(false) các periodic future, shutdown()
   v
WAIT_GRACEFUL -- awaitTermination -> terminated=true --> STOPPED
   |
   | timeout (false)
   v
ESCALATE: shutdownNow(), log/metrics
   |
   | awaitTermination thêm, có hạn
   +---- terminated=true --> STOPPED
   |
   +---- terminated=false --> STOP_INCOMPLETE
                                (cần cảnh báo/khôi phục)
~~~

Không nên định nghĩa trạng thái **STOPPED** chỉ bằng isShutdown hoặc isCancelled. Nếu worker vẫn còn trong đoạn I/O/blocking, stop chưa hoàn tất theo tiêu chí giải phóng tài nguyên. Hãy định nghĩa mức độ bảo đảm mà service cam kết: “đã từ chối tác vụ mới”, “đã đề nghị hủy”, hay “đã hết worker và có thể giải phóng mọi phụ thuộc”. Các trạng thái này có thể cách nhau đáng kể về thời gian.

**Deadline tổng** cũng khác với hai lần awaitTermination cùng một timeout: nếu mỗi lần chờ 5 giây, tổng thời gian có thể khoảng 10 giây. Khi hệ thống chỉ cho phép 5 giây toàn bộ, phải tính **thời gian còn lại** theo một deadline monotonic (ví dụ System.nanoTime) trước từng lần đợi, tránh vô tình vượt ngân sách thời gian.

Nếu một luồng khác gọi stop lần nữa khi lần đầu đang đợi, cần tránh race về ai là người escalate và ai nhận kết quả. Một coordinator hoặc completion future cho lifecycle thường rõ ràng hơn nhiều caller tự chờ rồi tự can thiệp.

## 11. Kiểm thử hành vi shutdown bằng tình huống có kiểm soát

Đừng chỉ gọi Thread.sleep rồi hy vọng task đã bắt đầu. CountDownLatch, Semaphore và các công cụ đồng bộ giúp tạo các mốc rõ ràng: task **đã vào thân**, **đang bị giữ**, **được phép thoát**, **đã nhận interrupt**. Từ đó có thể kiểm chứng cả trạng thái Future và trạng thái executor.

| Tình huống | Điều cần kiểm chứng |
|---|---|
| Stop trước lượt đầu tiên | Không có lượt mới; executor terminate theo chính sách |
| Stop khi một lượt đang chạy | cancel(false) ngăn lượt tiếp, lượt đang chạy được hoàn tất |
| Stop khi lượt không đáp ứng | Grace period hết, shutdownNow được thử, chưa được báo thành công nếu executor còn worker |
| Gọi stop hai lần | Không schedule lại, không ném lỗi bất ngờ nếu hợp đồng idempotent |
| Race giữa start và stop | Sau STOPPING không có future mới được chấp nhận |
| Task ném exception | Lượt tiếp theo bị suppress; lỗi được báo/ghi nhận |
| Có delayed one-shot task | Kiểm tra policy về tiếp tục thực thi sau shutdown |
| Phụ thuộc I/O không phản hồi interrupt | Deadline và cảnh báo không bị bỏ qua |
| Caller của stop bị interrupt | Bảo toàn/lan truyền tín hiệu, tránh chờ vô hạn |
| Executor dùng chung | Stop một component không shutdown lịch của component khác |

Có thể theo dõi các chỉ số: số periodic task đang active, thời gian mỗi lượt, lần chạy cuối và kết quả, số lần failure, thời điểm stop được yêu cầu, thời gian chờ shutdown, số lần escalation và cờ executor isTerminated(). Với ScheduledThreadPoolExecutor có thể theo dõi thêm **getQueue().size()** và **getActiveCount()**; đừng coi queue size là số lượt chạy định kỳ đã được lưu trữ trong tương lai hoặc là thước đo duy nhất cho sức khỏe hệ thống.

## 12. Những lỗi thiết kế thường gặp

1. **Chỉ gọi cancel(false) rồi coi việc dừng đã xong.** Future canceled nhưng lượt hiện tại có thể vẫn đang xử lý; cần đồng bộ và xác nhận termination nếu sở hữu executor.
2. **Chỉ gọi shutdown() rồi nghĩ mọi thứ kết thúc tức thì.** shutdown không chờ; one-shot delayed có thể còn tồn tại theo policy mặc định.
3. **Dùng shutdownNow() như lệnh kill bắt buộc.** Interrupt là cooperative; phải xử lý khi không đáp ứng.
4. **Gọi awaitTermination ngay trong periodic Runnable của chính executor.** Worker tự chờ executor mà nó phải thoát để executor terminate, dẫn tới deadlock/timeout.
5. **Không lưu ScheduledFuture.** Khó cancel riêng từng lịch hoặc quản lý component chia sẻ executor.
6. **Quên stop/start concurrency.** Hai lệnh start có thể tạo hai lịch trùng; stop cạnh tranh với start có thể để lọt lịch mới.
7. **Bật continueExistingPeriodicTasksAfterShutdownPolicy(true) mà không có cancel.** Executor có thể tiếp tục chạy định kỳ sau shutdown và không terminate.
8. **Coi isDone() của periodic Future là kết quả từng lượt.** Lịch định kỳ vẫn đang chạy bình thường thường chưa done.
9. **Nuốt InterruptedException hoặc đóng connection trước khi task thoát.** Kéo dài shutdown hoặc làm hỏng dữ liệu đang xử lý.
10. **Khởi động lại cùng executor đã shutdown.** schedule(...) bị từ chối; muốn restart nên tạo vòng đời và executor mới.

## 13. Checklist thiết kế trước khi đưa vào sử dụng

- Ai sở hữu ScheduledExecutorService? Có được phép shutdown executor hay chỉ cancel lịch của mình?
- Lịch chạy theo fixed-rate hay fixed-delay? Có khả năng một lượt lâu hơn khoảng cách mong muốn không?
- Có lưu ScheduledFuture của từng lịch? Stop có chặn được mọi schedule mới không?
- Khi stop, cần hoàn tất lượt đang chạy hay được phép interrupt? Bước nào an toàn để ngừng?
- Đã đặt timeout cho database/network/file I/O và quản lý task con chưa?
- shutdown policy đối với **periodic** và **one-shot delayed** đã đúng chưa?
- Có grace period, escalation, deadline tổng và trạng thái STOP_INCOMPLETE nếu không terminate chưa?
- start/stop/stop lặp lại có đồng bộ và tránh deadlock không?
- Có kiểm thử stop giữa lượt, task lỗi, delayed task và I/O không phản hồi interrupt không?
- Metrics/log có phân biệt “đã yêu cầu stop”, “Future canceled” và “executor terminated” không?

**Ghi nhớ:** một stop/shutdown đáng tin cậy cần kiểm soát **lịch tương lai**, **công việc đang chạy** và **vòng đời executor** một cách riêng biệt. Với Java ScheduledExecutorService, kết hợp **cancel(false)** cho graceful stop, **shutdown() + awaitTermination()** để chờ kết thúc, và **shutdownNow()** như bước escalation có giới hạn; luôn chuẩn bị phương án cho task không hợp tác với interrupt.
