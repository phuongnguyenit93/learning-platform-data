# Phân biệt luồng kích hoạt lịch với luồng thực thi công việc

Trong Spring Framework, **TaskScheduler** quyết định *khi nào* một công việc được kích hoạt theo thời gian; **TaskExecutor** thường được dùng để quyết định *ở đâu và bằng những worker nào* công việc được xử lý. Tuy nhiên, **việc dùng TaskScheduler hoặc @Scheduled không mặc nhiên tạo ra hai nhóm luồng tách biệt**. Với **ThreadPoolTaskScheduler**, chính các thread trong scheduler pool thực thi Runnable đã được lập lịch. Nếu Runnable đó chứa logic nghiệp vụ kéo dài, scheduler thread sẽ bận với công việc ấy và những callback lịch khác có thể bị trễ.

Bài **“Phân biệt luồng kích hoạt lịch với luồng thực thi công việc”** thuộc nhóm **TaskScheduler** của module **Spring Framework - concurrency**. Mục tiêu là hiểu ba ranh giới: **tính toán thời điểm kích hoạt**, **chạy callback được lập lịch**, và **thực thi phần việc nghiệp vụ**. Ba phần này có thể nằm trên cùng thread hoặc được chủ động tách qua TaskExecutor.

Sau bài này, bạn có thể:

- Giải thích ThreadPoolTaskScheduler thực sự chạy Runnable trên thread nào, và khi nào một TaskExecutor riêng mới tham gia.
- Phân biệt **fixedRate**, **fixedDelay** và **cron** khi callback thực thi trực tiếp hoặc chỉ gửi việc.
- Thiết kế **scheduler nhẹ + worker pool hữu hạn** mà không mất kiểm soát backlog, trùng lặp hoặc quyền sở hữu kết quả.
- Đọc đúng các chỉ số **scheduler lag, callback duration, executor queue wait, worker duration**.
- Kiểm thử bằng Java 17 sử dụng CountDownLatch thay vì dựa vào Thread.sleep, đồng thời cấu hình Spring với @EnableScheduling, @Scheduled, ThreadPoolTaskScheduler và ThreadPoolTaskExecutor.

## 1. Từ “trigger thread” dễ gây nhầm lẫn như thế nào?

Khi nói “luồng kích hoạt lịch”, người ta thường muốn chỉ thành phần chịu trách nhiệm nhận biết rằng **đã tới thời điểm** của một lịch chạy. Nhưng trong Java và Spring, không phải mọi implementation đều có một thread chỉ chuyên đánh chuông và một thread khác luôn chạy tác vụ.

Hãy phân biệt các thuật ngữ:

| Thành phần | Vai trò | Có bắt buộc là thread riêng không? |
| --- | --- | --- |
| **Trigger** | Quy tắc xác định thời điểm tiếp theo: fixed rate, fixed delay, cron hoặc Trigger tùy biến | **Không**. Trigger là quy tắc/lớp tính thời điểm, không đồng nghĩa với một worker thread riêng |
| **Scheduler** | Giữ lịch, phát hiện callback nào đã tới hạn và tổ chức thực thi callback | Có thread/resource thực thi theo implementation |
| **Scheduled callback** | Runnable hoặc method được scheduler gọi khi đến hạn | **Có thể chạy ngay trên scheduler thread** |
| **Business job** | Công việc thật: truy vấn DB, gọi HTTP, xuất báo cáo, tính toán | Có thể chạy trong scheduled callback hoặc worker khác |
| **TaskExecutor** | Nhận Runnable/Callable và quản lý cách thực thi công việc được gửi vào | Có thể là pool, executor trực tiếp hoặc implementation khác |
| **Worker pool** | Các thread thực thi business job nếu ứng dụng chủ động giao việc | **Không tự xuất hiện** khi chỉ bật @Scheduled |

Hai mô hình cốt lõi:

**Mô hình A — callback làm việc trực tiếp:**

~~~text
Clock / Trigger
    |
    v
ThreadPoolTaskScheduler
    |
    +-- scheduler-thread-1
            |
            +-- scheduledMethod()
                    |
                    +-- gọi DB
                    +-- xuất báo cáo 20 giây
                    +-- gửi email
            |
            +-- chỉ rảnh để xử lý callback tiếp theo khi method thoát
~~~

**Mô hình B — callback giao việc cho worker:**

~~~text
Clock / Trigger
    |
    v
ThreadPoolTaskScheduler
    |
    +-- scheduler-thread-1
            |
            +-- scheduledMethod()
                    |
                    +-- TaskExecutor.execute(job)
                    +-- return nhanh
                              |
                              v
                     ThreadPoolTaskExecutor
                              |
                              +-- worker-1 --> business job
                              +-- worker-2 --> business job
                              +-- queue nếu chưa có worker rảnh
~~~

Trong mô hình B, scheduler rảnh sớm hơn để xử lý những lịch khác, **nhưng business job không tự hoàn tất khi callback trả về**. Việc giao việc còn có thể bị **rejected**, và nếu không kiểm soát, lần kích hoạt sau có thể tạo công việc mới khi job trước vẫn chạy.

## 2. TaskScheduler là một abstraction, không phải lời hứa về kiến trúc thread

Spring cung cấp interface **org.springframework.scheduling.TaskScheduler** với các thao tác như:

~~~java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);

ScheduledFuture<?> schedule(Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);
~~~

Đây là **chữ ký rút gọn để giải thích** từ API Spring, không phải file Java độc lập. Interface còn có overload nhận thời điểm bắt đầu và clock.

**TaskScheduler trả lời:** khi nào Runnable sẽ được scheduler tổ chức thực thi, hoặc dựa theo trigger để hẹn lần chạy tiếp theo. Interface **không buộc** tất cả implementation phải có một thread trigger riêng và một pool thực thi riêng.

### Các implementation cần phân biệt

**ThreadPoolTaskScheduler**: wrapper của một **ScheduledExecutorService/ScheduledThreadPoolExecutor**, cho phép cấu hình scheduler pool và lifecycle. **Task execution happens on the scheduler thread(s)** theo Javadoc. Mặc định pool size thường là **1** nếu không cấu hình lại, nhưng ứng dụng có thể tùy chỉnh.

**ConcurrentTaskScheduler**: adapter cho một **ScheduledExecutorService** đã có. Thread model được quyết định bởi underlying scheduler; đừng suy ra có TaskExecutor độc lập.

**SimpleAsyncTaskScheduler** (Spring Framework từ 6.1): dùng **một scheduler thread** và tạo thread mới cho nhiều lượt thực thi được kích hoạt. Nó phù hợp với mô hình dùng **virtual threads trên Java 21** khi cấu hình tương ứng; **riêng fixed-delay tasks của implementation này chạy trên một scheduler thread**, nên cần chú ý nếu tác vụ kéo dài. Không đánh đồng SimpleAsyncTaskScheduler với ThreadPoolTaskScheduler.

**DefaultManagedTaskScheduler**: tích hợp với scheduler do application server quản lý. Quy tắc cấp thread và lifecycle phụ thuộc môi trường.

**Quartz**: bộ lập lịch có kiến trúc, chính sách persistence/cluster và worker management riêng; không tự mặc định mọi chi tiết của Quartz giống TaskScheduler tích hợp trong JVM.

Bài này dùng **ThreadPoolTaskScheduler** làm ví dụ chính vì đây là lựa chọn phổ biến trong Spring và thể hiện rõ sự khác nhau giữa **scheduler thread trực tiếp làm việc** với **callback chủ động delegate**.

## 3. Vì sao ThreadPoolTaskScheduler không có worker pool riêng mặc định?

ThreadPoolTaskScheduler bọc **ScheduledExecutorService** ở tầng Java. Khi một ScheduledThreadPoolExecutor thực thi một Runnable đã tới hạn, **một thread của scheduled pool** gọi phương thức run của Runnable đó.

~~~text
ThreadPoolTaskScheduler(poolSize = 1)

Scheduler queue:
  [A due] [B due] [C due in 1 second]
       |
       v
scheduler-1:
  run A ------------------------> A returns
                                 |
                                 v
                              run B --> B returns
                                         |
                                         v
                                      run C
~~~

Nếu A là tác vụ I/O chặn 30 giây, B có thể bị trễ **ngay cả khi B theo lịch phải chạy vài giây trước**. Chỉnh **@Scheduled(fixedRate=...)** trên B không tạo ra thread độc lập cho nó.

Một scheduler pool có kích thước lớn hơn 1 cho phép các **callback khác nhau** đồng thời được chạy, trong giới hạn số thread. Nhưng đây vẫn là **pool của chính scheduler**. Chỉ tăng poolSize không tự tạo ranh giới tài nguyên giữa *lập lịch* và *thực thi business job*.

### Nên tăng poolSize hay tách executor?

| Hiện tượng | Tăng scheduler poolSize | Tách callback và worker pool |
| --- | --- | --- |
| Nhiều callback độc lập chặn nhau | Có thể giảm sự chờ lẫn nhau | Thường giảm chờ nếu callback gửi việc nhanh |
| Business job nặng/đợi I/O | Vẫn chiếm scheduler thread nếu làm trực tiếp | Business job tiêu thụ worker, không giữ scheduler |
| Cần giới hạn business concurrency | Có thể giới hạn gián tiếp bằng scheduler size | Cấu hình được worker/core/max/queue và cơ chế kiểm soát riêng |
| Muốn theo dõi trễ lịch và thời gian job tách biệt | Khó hơn nếu một callback làm cả hai | Dễ đo riêng scheduler delay và execution delay |
| Cần không trùng lặp job | Không tự bảo đảm ở mọi cách tổ chức | Vẫn phải thiết kế single-flight/lock/idempotency |
| Cần tránh backlog lớn | Scheduler vẫn có queue/callback được hẹn | Worker queue cũng phải bounded và có overload policy |

**Không phải mọi scheduled callback đều phải delegate.** Nếu công việc chỉ cập nhật một counter hoặc làm việc không chặn, rất ngắn, chạy trực tiếp trên scheduler thread có thể là hợp lý. Tách executor có chi phí context switching, thêm queue, thêm trạng thái và xử lý rejection.

## 4. Fixed rate, fixed delay và cron: đo thời gian của cái gì?

Điểm then chốt là **lịch đo thời gian dựa trên việc chạy callback của scheduler**, không nhất thiết dựa trên business job được delegate.

### 4.1 Fixed delay

**@Scheduled(fixedDelay = 5000)**: một lượt gọi method hoàn tất, sau đó chờ khoảng **5 giây** rồi mới kích hoạt lượt kế tiếp.

~~~text
Chạy trực tiếp:
t=00 start job A ----(8 giây)---- t=08 finish
                              + 5 giây
t=13 start job B

Delegate qua executor:
t=00 callback A --> gửi worker job A --> return rất nhanh
                    |
                    +-- job A chạy 8 giây trong worker

t~05 callback B --> gửi worker job B
                    (dù job A có thể đã/đang chạy)
~~~

Trong mô hình delegate, **fixedDelay** dựa trên **thời điểm callback A trả về**, chứ không tự đợi công việc trong worker hoàn tất. Vì vậy, nói “fixedDelay chắc chắn không làm hai business jobs chồng lấn” là **sai** khi scheduled method chỉ gửi việc bất đồng bộ.

### 4.2 Fixed rate

**@Scheduled(fixedRate = 5000)**: các lần chạy được hẹn theo chu kỳ xấp xỉ **5 giây giữa các thời điểm bắt đầu theo lịch**.

~~~text
t=00  t=05  t=10  t=15 ...  (mốc dự kiến)
  |     |     |     |
  v     v     v     v
callback attempts
~~~

Nếu một lượt **chạy trực tiếp** lâu hơn period, các lần chạy sau có thể bị trễ; không có phép màu bắt buộc một tác vụ duy nhất phải chạy hai lần đồng thời. Với ScheduledThreadPoolExecutor, **các lần thực thi liên tiếp của cùng periodic task không overlap**, dù scheduler có nhiều worker threads; khi việc trước lâu hơn chu kỳ, lần sau có thể bắt đầu muộn.

Nhưng nếu callback fixed-rate **chỉ submit công việc rồi return**, hai business jobs do các lần callback khác nhau tạo ra **có thể chạy chồng lấn** trong worker pool. Scheduler chỉ thấy callback đã kết thúc nhanh.

**Fixed rate không phải cam kết “đúng mili giây”**. Độ trễ, tải hệ thống, GC, scheduler queue, saturation, thời gian chuyển thread và khả năng tiến triển của worker ảnh hưởng thời điểm thực.

### 4.3 Cron trigger

**@Scheduled(cron = "0 */5 * * * *", zone = "UTC")** thường dùng biểu thức cron Spring gồm **6 trường** (giây, phút, giờ, ngày trong tháng, tháng, thứ) để định thời điểm lịch.

Cron không đồng nghĩa “cứ tới mốc phút là scheduler bắt buộc mở một worker mới”. Đối với TaskScheduler dựa trên Trigger, **tính thời điểm tiếp theo có thể phụ thuộc thông tin lần chạy trước** thông qua TriggerContext.

Trong cách dùng CronTrigger thông thường của Spring, lịch có thể sử dụng lần hoàn tất trước để tính mốc tiếp theo; các mốc bị bỏ lỡ không nhất thiết được chạy bù. Những tùy chọn cron fixed/lenient execution mới và phiên bản khác nhau có semantics riêng, nên phải đọc API thực tế nếu nghiệp vụ yêu cầu **catch-up/misfire**.

Khi callback chỉ delegate, scheduler coi việc **gửi thành công** là callback hoàn tất, không chờ job trong executor. Cron có thể tiếp tục kích hoạt trong khi job trước chưa xong.

Với lịch theo múi giờ, cần xem **zone**, chuyển đổi DST, ngày nghỉ và hợp đồng nghiệp vụ. Không lấy log của UTC làm bằng chứng lịch giờ địa phương đúng nếu cron được đánh giá theo zone khác.

### Bảng tóm tắt

| Kiểu lịch | Callback làm việc trực tiếp | Callback chỉ delegate vào executor |
| --- | --- | --- |
| **fixedDelay** | Khoảng delay tính sau khi phần việc trong callback hoàn tất | Khoảng delay tính sau khi **submit callback** kết thúc, không sau job |
| **fixedRate** | Các mốc cố định; callback cùng periodic task trong ScheduledThreadPoolExecutor không overlap | Các lần **submit** theo mốc; worker jobs có thể overlap |
| **cron** | Kích hoạt theo lịch/TriggerContext của callback | Lịch không tự biết trạng thái business job ở worker |
| **schedule(Runnable, Instant)** | Chạy một lần ở thời điểm tới hạn | Gửi một lần, future của scheduler không đại diện kết thúc job delegate |

Điểm chung: **schedule là cơ chế kích hoạt; hoàn thành công việc nghiệp vụ là một trạng thái riêng nếu có delegation**.

## 5. Ví dụ Java 17 chạy được: trực tiếp chặn scheduler và delegate không chặn

Chương trình **DirectVsDelegatedSchedulerDemo.java** có hai phần, dùng **ScheduledExecutorService** và **ExecutorService** thuần Java, không cần Spring. Nó chứng minh:

- Với **scheduler một thread**, callback A đang chờ làm callback B chưa thể chạy.
- Khi callback A **gửi công việc cho worker rồi trả về**, callback B chạy được **trong khi worker vẫn bận**.
- Không có vòng chờ theo thời gian ngẫu nhiên; **CountDownLatch** đặt đúng thời điểm, **Future.get(timeout)** giới hạn chờ, và tên thread được đặt bằng ThreadFactory.

Lưu thành **DirectVsDelegatedSchedulerDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class DirectVsDelegatedSchedulerDemo {
    private static void direct() throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor(
                        r -> new Thread(r, "scheduler-thread"));

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);

        try {
            ScheduledFuture<?> first = scheduler.schedule(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, 0, TimeUnit.MILLISECONDS);

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First callback chưa chạy");
            }

            ScheduledFuture<?> second = scheduler.schedule(
                    () -> secondRan.set(true),
                    0, TimeUnit.MILLISECONDS);

            // First vẫn giữ thread; second không thể được gọi.
            boolean blocked = !second.isDone() && !secondRan.get();

            releaseFirst.countDown();
            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            System.out.println("Direct: callback thứ hai bị chặn: "
                    + blocked);
            System.out.println("Direct: callback thứ hai đã chạy: "
                    + secondRan.get());
        } finally {
            releaseFirst.countDown();
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler chưa kết thúc");
            }
        }
    }

    private static void delegated() throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor(
                        r -> new Thread(r, "scheduler-thread"));
        ExecutorService workers = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "worker-thread"));

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        CountDownLatch workerFinished = new CountDownLatch(1);

        AtomicReference<String> triggerThread = new AtomicReference<>();
        AtomicReference<String> jobThread = new AtomicReference<>();
        AtomicBoolean secondRan = new AtomicBoolean(false);

        try {
            ScheduledFuture<?> first = scheduler.schedule(() -> {
                triggerThread.set(Thread.currentThread().getName());
                workers.execute(() -> {
                    jobThread.set(Thread.currentThread().getName());
                    workerStarted.countDown();
                    try {
                        releaseWorker.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        workerFinished.countDown();
                    }
                });
            }, 0, TimeUnit.MILLISECONDS);

            first.get(5, TimeUnit.SECONDS);

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa bắt đầu");
            }

            ScheduledFuture<?> second = scheduler.schedule(
                    () -> secondRan.set(true),
                    0, TimeUnit.MILLISECONDS);

            // Scheduler có thể xử lý callback thứ hai dù worker
            // vẫn đang đợi releaseWorker.
            second.get(5, TimeUnit.SECONDS);
            boolean ranWhileWorkerBusy =
                    secondRan.get() && workerFinished.getCount() == 1;

            releaseWorker.countDown();

            if (!workerFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa hoàn tất");
            }

            System.out.println("Delegated: callback trên scheduler-thread: "
                    + "scheduler-thread".equals(triggerThread.get()));
            System.out.println("Delegated: job trên worker-thread: "
                    + "worker-thread".equals(jobThread.get()));
            System.out.println("Delegated: callback hai khi worker bận: "
                    + ranWhileWorkerBusy);
            System.out.println("Delegated: worker đã hoàn tất: "
                    + (workerFinished.getCount() == 0));
        } finally {
            releaseWorker.countDown();
            scheduler.shutdownNow();
            workers.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)
                    || !workers.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor chưa kết thúc");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        direct();
        delegated();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 DirectVsDelegatedSchedulerDemo.java
java DirectVsDelegatedSchedulerDemo
~~~

**Stdout** khi môi trường cho các thread khởi động và hoàn tất trong các thời hạn 5 giây:

~~~text
Direct: callback thứ hai bị chặn: true
Direct: callback thứ hai đã chạy: true
Delegated: callback trên scheduler-thread: true
Delegated: job trên worker-thread: true
Delegated: callback hai khi worker bận: true
Delegated: worker đã hoàn tất: true
~~~

**Vì sao các kết luận không dựa vào may rủi của scheduler?**

1. Ở **direct**, main đợi firstStarted nên chắc chắn callback A đã chạy và đang giữ scheduler thread trong await(). A không thể kết thúc cho đến khi main mở releaseFirst. Vì chỉ có một scheduler thread, B chưa thể được gọi khi main kiểm tra blocked.
2. Sau khi mở latch, main chờ cả hai ScheduledFuture bằng get(timeout) để xác nhận B đã chạy.
3. Ở **delegated**, callback A trả về sau khi workers.execute tiếp nhận job. first.get(timeout) hoàn tất trước khi main gửi callback B.
4. Main đợi workerStarted, tức là worker thực sự bắt đầu và đang chờ releaseWorker. Callback B vẫn được scheduler thread xử lý và Future của B hoàn tất; lúc ấy workerFinished chưa đếm xuống.
5. Main mở releaseWorker để job thoát, rồi mới in kết quả. Tên thread được định nghĩa tường minh nên so sánh mang ý nghĩa thực tế.
6. finally mở latch và shutdown cả hai executor để tránh giữ thread nền sau chương trình.

**Giới hạn:** ví dụ chứng minh sự khác nhau giữa callback trực tiếp và delegation, không phải mô phỏng cron hay benchmark tải. Cấu hình một worker để quan sát ranh giới, không có nghĩa một worker là lựa chọn mặc định tối ưu cho production.

## 6. ScheduledFuture biểu thị sự hoàn tất của cái gì?

Đối với một lần **scheduler.schedule(runnable, instant)** hoặc ScheduledExecutorService.schedule(...), một **ScheduledFuture** có thể cho biết callback được scheduler chạy xong, lỗi hoặc hủy.

Nếu callback là:

~~~java
scheduler.schedule(() -> workerExecutor.execute(
        () -> generateReport()), startTime);
~~~

Đây là **đoạn minh họa** với scheduler, workerExecutor, startTime, generateReport đã tồn tại.

**ScheduledFuture hoàn tất khi Runnable gửi việc kết thúc**, không chờ generateReport hoàn thành, trừ khi chính callback block để chờ worker. Khi dùng delegate, cần một **Future/CompletableFuture hoặc trạng thái job riêng** để theo dõi kết quả thực sự.

Hai handle không nên bị nhập làm một:

~~~text
ScheduledFuture of callback
      |
      +-- callback gửi việc: DONE
                  |
                  +-- business Future: RUNNING --> SUCCESS / FAILURE
~~~

Nếu gọi **cancel(true)** trên ScheduledFuture của một periodic callback, bạn yêu cầu hủy lịch/callback tương ứng theo hợp đồng. Điều đó **không mặc nhiên cancel** mọi job đã được submit vào workerExecutor trước đó.

Nếu gọi **cancel(true)** trên Future do TaskExecutor.submit trả về, bạn đang yêu cầu hủy **worker job**, nhưng việc ngắt vẫn mang tính hợp tác tùy Future implementation. Với CompletableFuture của JDK, **cancel(true) không tự interrupt supplier**. Chọn đúng handle và đúng lifecycle.

### Repeating ScheduledFuture

Với **scheduleAtFixedRate** hoặc **scheduleWithFixedDelay**, Future đại diện cho **chuỗi lặp**. Trong JDK ScheduledExecutorService, get() của Future lặp thường **không trả về bình thường khi lịch tiếp tục vô hạn**; nó chỉ kết thúc do hủy hoặc lỗi. Không gọi recurringFuture.get() trong một thread rồi kỳ vọng mỗi tick cho một kết quả business mới.

Thay vào đó, quan sát:
- Số lần callback bắt đầu/hoàn tất.
- Số lần submit worker được chấp nhận/rejected.
- Future hoặc trạng thái riêng của từng job.
- Cancellation của lịch và các job đang chạy như hai quyết định khác nhau.

## 7. Một định luật vận hành: callback trả về sớm không phải job đã xong

Một lỗi rất thường gặp trong code review:

~~~java
@Scheduled(fixedDelay = 5000)
public void exportData() {
    executor.execute(() -> reallyExportData());
}
~~~

Đây là **đoạn minh họa trong bean Spring có executor và reallyExportData**. Method exportData có thể return ngay sau khi executor nhận task. **FixedDelay 5 giây** không chờ reallyExportData hoàn thành.

Điều này ảnh hưởng tới:

- **Khả năng overlap** giữa các business jobs.
- **Thông báo thành công**: callback trả về không chứng minh tác vụ đã chạy.
- **Theo dõi lỗi**: exception trong worker không tự quay lại stack của scheduled callback.
- **Cancellation**: hủy lịch không hủy các job đã nhận.
- **Time budget**: chờ trong worker queue có thể khiến công việc chạy sau deadline.
- **Bảo đảm không mất job**: executor in-memory không phải durable queue.

Nếu logic nghiệp vụ cần “mỗi lượt chỉ bắt đầu khi lượt trước đã hoàn thành”, thì **scheduleWithFixedDelay cho callback delegate không tự bảo đảm điều này**. Cần một cơ chế quản lý trạng thái in-flight hoặc một scheduler/job system hiểu business completion.

## 8. Cấu hình Spring: hai pool tách biệt, một cho lịch và một cho công việc

Giải pháp phổ biến là dùng **ThreadPoolTaskScheduler** để giữ lịch và **ThreadPoolTaskExecutor** để chạy công việc nặng.

Các snippet sau thuộc một ứng dụng **Spring Framework 6.x, Java 17+ có spring-context**, không phải chương trình javac thuần. Mỗi khối là một file riêng. Các thông số chỉ minh họa, không phải sizing production.

**SchedulingPoolsConfig.java**:

~~~java
package example.scheduler;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableScheduling
public class SchedulingPoolsConfig {

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("trigger-");
        return scheduler;
    }

    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
~~~

**ReportProcessor.java**:

~~~java
package example.scheduler;

import org.springframework.stereotype.Service;

@Service
public class ReportProcessor {

    public void process(String jobId) {
        // Thực hiện công việc nghiệp vụ thật:
        // kiểm tra deadline và quyền, gọi dependency có timeout,
        // quản lý transaction và ghi kết quả theo jobId.
        System.out.println("Processing job: " + jobId);
    }
}
~~~

**ReportTrigger.java**:

~~~java
package example.scheduler;

import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class ReportTrigger {
    private final ThreadPoolTaskExecutor executor;
    private final ReportProcessor processor;

    public ReportTrigger(
            @Qualifier("jobExecutor") ThreadPoolTaskExecutor executor,
            ReportProcessor processor) {
        this.executor = executor;
        this.processor = processor;
    }

    @Scheduled(fixedDelay = 5_000)
    public void trigger() {
        String jobId = UUID.randomUUID().toString();

        try {
            // Callback scheduler chỉ làm việc gửi task ngắn gọn.
            executor.execute(() -> processor.process(jobId));
        } catch (TaskRejectedException rejected) {
            // Ghi metric và log có ngữ cảnh; quy định rõ
            // phải bỏ, lưu lại hay retry một job chưa nhận.
            System.err.println("Job rejected: " + jobId);
        }
    }
}
~~~

**Phân tích cấu hình:**

1. **@EnableScheduling** đăng ký bộ xử lý @Scheduled trong context. Bean tên **taskScheduler** được dùng làm scheduler phù hợp theo cấu hình Spring thông thường.
2. **@Scheduled(fixedDelay = 5_000)** khiến **ReportTrigger.trigger()** được gọi theo lịch. Với ThreadPoolTaskScheduler đang dùng, callback chạy trong pool có tên tiền tố **trigger-**.
3. Trong callback, **jobExecutor.execute(...)** gửi phần việc thật vào pool **job-**; khi được nhận, callback return mà không chờ processor.process.
4. **ThreadPoolTaskExecutor** có queue hữu hạn (16) và số worker trong ví dụ giới hạn từ 2 tới 4. Khi bão hòa, submit có thể bị từ chối; **TaskRejectedException** cần chính sách ứng dụng rõ ràng.
5. **ReportProcessor.process** được gọi trong worker của jobExecutor. Nó không cần @Async riêng vì **việc dispatch đã được thực hiện tường minh ở executor.execute**.
6. Bởi callback có thể kết thúc rất nhanh, những lần gọi trigger tiếp theo có thể tạo thêm job, **kể cả khi job trước còn chạy**.
7. Cấu hình trên **không cung cấp distributed lock** và không bảo đảm mỗi job chỉ chạy một lần trong nhiều application instances.

**Lưu ý về dependency:** những file này cần đặt đúng package và được Spring component scan/đăng ký vào ApplicationContext. Ví dụ ReportProcessor chỉ in jobId để thấy đường đi; production phải xử lý kết quả, bảo mật, lỗi và lưu job theo yêu cầu.

### Khi nào giữ logic trực tiếp trong @Scheduled?

Nếu công việc đơn giản:

~~~java
@Scheduled(fixedRate = 10_000)
public void refreshInMemoryCounter() {
    counter.incrementAndGet();
}
~~~

Đây là **đoạn minh họa** với counter là AtomicLong/AtomicInteger. Callback ngắn, không block, có thể chạy trực tiếp trên scheduler pool. Không cần tạo một worker queue khác chỉ để tăng counter.

Nếu refreshInMemoryCounter bắt đầu gọi API ngoài, chờ DB hoặc đọc file lớn, cần đánh giá lại độ dài callback và ảnh hưởng các lịch khác trước khi quyết định tách worker.

## 9. @Scheduled kết hợp @Async: hai interceptor, hai ranh giới

Có thể gặp mã:

~~~java
@Scheduled(fixedRate = 1_000)
@Async("jobExecutor")
public void work() {
    runHeavyJob();
}
~~~

Đây là **đoạn minh họa**. Cách kết hợp hai annotation phụ thuộc cấu hình **@EnableScheduling, @EnableAsync, proxy advice** và đường gọi. Không nên lấy việc source có cả hai annotation làm bằng chứng **lịch và công việc đã tách đúng thread** trong mọi runtime.

Một phương án rõ ràng, dễ test hơn là **hai bean khác nhau**:

~~~java
@Component
class ScheduledStarter {
    private final AsyncWorker worker;

    ScheduledStarter(AsyncWorker worker) {
        this.worker = worker;
    }

    @Scheduled(fixedRate = 1_000)
    public void tick() {
        worker.executeAsync(); // Lời gọi đi qua bean Spring khác.
    }
}
~~~

~~~java
@Service
class AsyncWorker {
    @Async("jobExecutor")
    public void executeAsync() {
        // Công việc thực sự; cần xử lý lỗi của void @Async.
    }
}
~~~

Đây là **hai snippet Spring minh họa**, cần import Component, Service, Scheduled, Async, @EnableScheduling và **@EnableAsync** cùng executor bean. Khi gọi qua Spring-managed proxy, **@Async** dispatch method body vào executor. Với @Async void, lỗi trong worker **không tự ném trở lại caller đã return**; có thể cần AsyncUncaughtExceptionHandler, metrics và hợp đồng job riêng.

So sánh hai cách tách:

| Cách làm | Điểm dispatch | Điểm cần chú ý |
| --- | --- | --- |
| **@Scheduled → executor.execute(Runnable)** | Trong callback, trực tiếp qua TaskExecutor | Có thể bắt rejection tại execute, chủ động nhận/trả Future nếu dùng submit |
| **@Scheduled bean → @Async worker bean** | Spring proxy của worker | Phải bật @EnableAsync, gọi qua proxy và chọn executor đúng; tránh self-invocation |
| **@Scheduled và @Async trên cùng method** | Tùy advisor/proxy integration | Cần integration test chứng minh đường gọi, thread và lifecycle thực sự |
| **@Scheduled làm việc trực tiếp** | Không có dispatch bổ sung | Business logic chiếm scheduler thread trong toàn thời gian thực thi |

**Không double-dispatch** nếu không có chủ đích: một method đã được @Async chuyển vào worker rồi lại gọi supplyAsync vào commonPool có thể khiến công việc chạy ở pool thứ ba, gây khó phân định giới hạn tài nguyên và propagation context.

## 10. Có tự động overlap nếu scheduler poolSize lớn hơn 1 không?

Không thể trả lời “có” cho mọi trường hợp. Cần xem **đơn vị lặp** và **đường thực thi**.

- Với **một periodic Runnable** được đăng ký bằng **ScheduledThreadPoolExecutor.scheduleAtFixedRate / scheduleWithFixedDelay**, **các lượt thực thi của chính Runnable đó không overlap** theo hợp đồng JDK; nếu một lần lâu hơn period, lần sau có thể trễ.
- Với **nhiều lịch độc lập** (hai @Scheduled methods, hai schedule() khác nhau, hai khai báo @Scheduled trên cùng method), callback có thể chạy song song khi scheduler có nhiều worker và lịch đến hạn.
- Với một **callback periodic chỉ submit job** sang worker, các callback không overlap **không đồng nghĩa các business jobs không overlap**. Chúng là những Runnable khác nhau ở worker pool.
- Với **nhiều application instances**, cùng biểu thức cron có thể tạo các lượt business job đồng thời ở mỗi instance, bất kể mỗi instance chỉ có một scheduler thread.

### Ví dụ tình huống

~~~text
@Scheduled(fixedRate = 1 second)
scheduler poolSize=1, worker poolSize=2

t=0: callback A -> submit job A -> callback A returns
                         |
                         +-- worker-1 runs 5 seconds
t=1: callback B -> submit job B -> callback B returns
                         |
                         +-- worker-2 runs 5 seconds
t=2: callback C -> submits job C -> queued
...
~~~

Ở đây **callback lịch không nhất thiết chồng lấn**, nhưng **business job A và B chồng lấn**. Nếu nghiệp vụ là xuất báo cáo độc lập theo từng khoảng, điều này có thể chấp nhận. Nếu nghiệp vụ là cập nhật một bảng tổng hợp không thể chạy hai lượt cùng lúc, cần một **single-flight guard** hoặc cơ chế khóa bền vững.

## 11. Giới hạn business concurrency: single-flight guard

Để không tạo một business job thứ hai khi job trước còn chạy, có thể dùng **AtomicBoolean inFlight**:

~~~java
package example.scheduler;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class NonOverlappingReportTrigger {
    private final AtomicBoolean inFlight = new AtomicBoolean(false);
    private final ThreadPoolTaskExecutor executor;
    private final ReportProcessor processor;

    public NonOverlappingReportTrigger(
            @Qualifier("jobExecutor") ThreadPoolTaskExecutor executor,
            ReportProcessor processor) {
        this.executor = executor;
        this.processor = processor;
    }

    @Scheduled(fixedRate = 1_000)
    public void tick() {
        if (!inFlight.compareAndSet(false, true)) {
            // Task trước chưa kết thúc; lượt này được bỏ theo policy.
            return;
        }

        try {
            executor.execute(() -> {
                try {
                    processor.process("single-flight-report");
                } finally {
                    inFlight.set(false);
                }
            });
        } catch (TaskRejectedException rejected) {
            // Task chưa được nhận; không giữ cờ mãi mãi.
            inFlight.set(false);
            throw rejected;
        }
    }
}
~~~

Đây là **một file Spring trong package example.scheduler**, dựa trên ReportProcessor và bean jobExecutor ở mục trước. Với default **AbortPolicy** và ThreadPoolTaskExecutor, TaskRejectedException biểu thị việc gửi task không thành công; nhánh catch reset guard.

**Invariant cần hiểu:**

1. Khi inFlight=false, callback có thể giành quyền bằng compareAndSet.
2. Từ lúc giành quyền đến lúc worker finally reset, callback khác thấy inFlight=true và bỏ qua lượt mới.
3. Nếu worker chưa chạy vì đang chờ queue, cờ **vẫn true**; điều đó thường đúng nếu muốn tính toàn bộ thời gian “job in-flight” gồm cả queue wait.
4. Nếu task không được nhận và ném TaskRejectedException, callback reset cờ để những lần sau còn thử lại.
5. Nếu process ném exception, finally của worker vẫn reset cờ.

**Giới hạn rất quan trọng:**

- AtomicBoolean chỉ bảo vệ **một instance trong một JVM**, không ngăn nhiều pod/instance chạy cùng job.
- Nếu process bị kill khi job đang chạy, trạng thái in-memory mất; không có durable recovery.
- Nếu handler dùng **DiscardPolicy** và âm thầm bỏ task, callback có thể đã set inFlight=true nhưng worker không bao giờ chạy finally; cờ bị kẹt. Dùng rejection policy **tường minh**, có quan sát.
- Nếu dùng **CallerRunsPolicy**, worker lambda có thể thực thi ngay trên scheduler thread khi executor bão hòa; lúc ấy callback không còn nhẹ. Chọn policy theo ảnh hưởng lên lịch.
- Nếu có một cơ chế khác có thể gửi cùng business job ngoài scheduler, guard chỉ bảo vệ những đường gửi đi qua cùng instance này.
- Nếu cần *không bỏ lượt* mà phải xử lý lần lượt mọi sự kiện, single-flight kiểu skip **không phù hợp**; cần queue bền vững hoặc coalescing theo hợp đồng dữ liệu.

**Một lịch không overlap** và **một job không overlap** là hai tính chất khác nhau. AtomicBoolean là ví dụ cách xây tính chất thứ hai trong process.

## 12. Cần lưu mọi lượt hay chỉ cần trạng thái mới nhất?

Tách scheduler khỏi worker có thể tạo ra **một job mới ở mỗi tick**, trong khi workload xử lý lâu hơn chu kỳ. Nếu cứ gửi thêm task vào queue, **queue wait tăng không giới hạn** hoặc mất kiểm soát bộ nhớ.

Chọn chính sách theo nhu cầu nghiệp vụ:

| Yêu cầu | Cách tiếp cận có thể phù hợp |
| --- | --- |
| Quét trạng thái hiện tại; nếu lượt trước còn chạy thì không cần lượt mới | **Single-flight + skip/coalesce** |
| Mỗi lượt đại diện cho sự kiện phải xử lý đúng một lần | **Durable queue/event log, idempotency và acknowledgement** |
| Chỉ được có một job đang chạy trên toàn cluster | **Distributed lock/lease** có fencing hoặc job coordinator |
| Nhiều báo cáo độc lập, có giới hạn tải | **Bounded worker pool + bounded queue + overload policy** |
| Muốn fixed delay từ **business completion** | Lập lịch lượt tiếp theo **sau khi Future/job thật kết thúc**, hoặc dùng cơ chế điều phối hiểu vòng đời job |
| Có deadline chặt | **Queue wait + execution + downstream timeout** chung một time budget |

**Không tăng queueCapacity vô hạn** để che giấu worker chậm. Hàng đợi dài khiến công việc được tiếp nhận nhưng chỉ bắt đầu sau nhiều chu kỳ, khi dữ liệu/credential đã cũ.

### “Delay tính từ job hoàn tất” nên làm thế nào?

Nếu business semantics yêu cầu **nghỉ 10 giây sau khi xuất báo cáo hoàn tất**, việc giữ callback scheduler đồng bộ đến hết job có thể đúng về thời gian nhưng chiếm scheduler thread. Một kiến trúc tách biệt có thể:

1. Scheduled callback khởi động job A trên worker.
2. Khi worker A hoàn tất, ghi nhận success/failure/cancel.
3. Từ completion đó, yêu cầu TaskScheduler **schedule** một callback tiếp theo tại **Instant.now().plus(delay)**.
4. Không tạo lịch periodic cố định song song; để một coordinator duy trì chính xác **một lượt hẹn tiếp theo**.
5. Xử lý shutdown, rejection và lỗi schedule mới; nếu tính bền vững quan trọng, lưu trạng thái hẹn trong job store.

Cách này yêu cầu quản lý state, nhưng phản ánh đúng **completion của business job**, không nhầm với completion của callback.

## 13. Executor bão hòa: nếu callback không block thì backlog đi đâu?

Giả sử scheduler tick mỗi giây và job mất 10 giây. Nếu worker xử lý ít việc hơn tốc độ submit, hệ thống có thể chuyển điểm nghẽn **từ scheduler thread sang worker queue**:

~~~text
Trigger callbacks: 1 job / second
            |
            v
Bounded TaskExecutor:
    2 workers, queue capacity 8
            |
            +-- workers bận
            +-- queue đầy dần
            +-- TaskRejectedException khi không nhận thêm
~~~

Vì callback gửi nhanh rồi return, dashboard có thể báo **scheduler callback duration rất nhỏ** trong khi công việc thực sự bị trễ hoặc bị từ chối.

Các chính sách cần biết:

- **AbortPolicy**: từ chối tường minh; Spring ThreadPoolTaskExecutor biểu diễn theo hợp đồng TaskRejectedException. Dễ đo số lượt không được nhận.
- **CallerRunsPolicy**: khi executor bão hòa và chưa shutdown, callback có thể **tự thực thi business job trên scheduler thread**. Đây là cơ chế backpressure nhưng **xóa ranh giới tách thread trong trường hợp quá tải**; scheduler có thể bắt đầu trễ những lịch khác.
- **DiscardPolicy**: có thể im lặng bỏ việc, khiến callback tưởng đã submit thành công. Không phù hợp nếu job bắt buộc được thực thi hoặc guard chờ worker finally.
- **DiscardOldestPolicy**: có thể bỏ một task đã nằm chờ rồi thử nhận task mới, ảnh hưởng tính nhất quán và Future của task cũ.

**Không thể bảo đảm “scheduler luôn không bao giờ block”** nếu dùng CallerRuns, blocking rejection handler, queue.put chờ chỗ hoặc logic callback tự thực hiện I/O. Kiến trúc tách biệt chỉ có tác dụng khi **đường giao việc cũng có giới hạn thời gian và chính sách quá tải rõ**.

### Khi submit bị reject, nên làm gì?

Điều đó tùy nghiệp vụ:

1. Nếu lượt tick là **best-effort quét dữ liệu hiện tại**, có thể ghi metrics, log ngắn và bỏ lượt theo policy.
2. Nếu tick đánh dấu công việc **không được phép mất**, cần ghi một job record/queue bền vững trước khi xác nhận tiếp nhận.
3. Nếu dự định retry, dùng **backoff hữu hạn, jitter, deadline** và idempotency. Đừng ngủ 30 giây ngay trong scheduler callback để “chờ pool có chỗ” khi có các lịch khác cần được kích hoạt.
4. Nếu executor đang **shutdown**, retry vào chính executor đó không giúp nó nhận thêm task.
5. Nếu business job có side effect, xác định trạng thái đã nhận, đang chạy, thành công, thất bại, cần retry, cancelled tách biệt.

**Scheduling không đồng nghĩa durability.** Một cron trong process dừng hoạt động khi process không chạy; task trong RAM có thể mất khi ứng dụng restart. Lịch định kỳ yêu cầu đảm bảo không mất lượt phải có cơ chế lưu/checkpoint khác.

## 14. Sự khác nhau giữa queue của scheduler và queue của worker

Trong mô hình hai pool có ít nhất **hai nơi chờ**:

~~~text
Trigger time -> scheduler delayed queue
                     |
                     v
             scheduled callback
                     |
                     v
            TaskExecutor work queue
                     |
                     v
               active worker
~~~

**Scheduler queue** lưu nhiệm vụ đã hẹn tới hạn hoặc chờ tới hạn. **Worker queue** lưu công việc đã được executor chấp nhận nhưng chưa có worker rảnh. Hai queue không thay thế nhau.

Ví dụ một callback đến hạn nhưng scheduler thread vẫn đang bận, dù worker pool rảnh, sẽ tạo **scheduler lag**. Ngược lại, callback chạy đúng giờ và gửi việc thành công, nhưng worker queue có 10 tác vụ, sẽ tạo **execution queue wait**.

Do vậy, khi điều tra “job chạy muộn”, phải phân biệt:

- **Trigger lag** = actual callback start − scheduled fire time.
- **Dispatch latency** = thời gian callback tính/submit vào executor.
- **Queue wait** = worker actual start − accepted/submitted time.
- **Execution duration** = worker completion − worker start.
- **End-to-end latency** = job completion − mốc nghiệp vụ bắt đầu cần xử lý.

**Đừng đo chung tất cả thời gian vào một nhãn “scheduler took 12 seconds”**; nó che nguyên nhân cần chỉnh. TriggerContext có thông tin lastScheduledExecution, lastActualExecution và lastCompletion cho một số kiểu trigger, nhưng đó vẫn nói về **callback do scheduler quản lý**, không tự biết completion của job delegate.

## 15. @Scheduled được gọi trên bao nhiêu instance?

Nếu một ứng dụng Spring chạy **3 pods**, mỗi pod có:

~~~java
@Scheduled(cron = "0 0 * * * *", zone = "UTC")
public void hourly() { /* ... */ }
~~~

thì thông thường **mỗi instance đều có scheduler riêng** và mỗi instance có thể chạy callback ở mốc giờ đó. @Scheduled của Spring **không tự biến thành cluster singleton**.

~~~text
pod-A: scheduler -> hourly() -> job A
pod-B: scheduler -> hourly() -> job B
pod-C: scheduler -> hourly() -> job C
~~~

Ngay cả khi mỗi pod dùng poolSize=1 và AtomicBoolean local, vẫn có ba job có thể cùng tác động lên database chung.

Nếu nghiệp vụ chỉ cho một job toàn hệ thống:

- Sử dụng distributed lease/lock được thiết kế đúng, kèm TTL và **fencing token** nếu cần ngăn writer cũ tiếp tục.
- Hoặc đưa lịch vào một **orchestrator/job scheduler** tập trung có state và leadership.
- Hoặc biến thao tác thành **idempotent** và xử lý cạnh tranh ở database với uniqueness/version constraints.
- Với workflow quan trọng, lưu **job identity và trạng thái** để hồi phục sau restart, tránh xem callback duy nhất như một bằng chứng thực thi thành công.

**Một scheduler thread duy nhất** chỉ có nghĩa một thread trong **một JVM/process**, không có ý nghĩa “một công việc duy nhất trên toàn cluster”.

## 16. Khi callback lỗi, lịch có còn chạy nữa không?

Cần phân biệt **JDK ScheduledExecutorService trực tiếp** với **Spring ThreadPoolTaskScheduler và ErrorHandler được cấu hình**.

Ở JDK ScheduledExecutorService:

- Với **scheduleAtFixedRate/scheduleWithFixedDelay**, nếu một lượt thực thi Runnable ném exception không được xử lý, các lượt tiếp theo của chính periodic task có thể bị **suppress** theo hợp đồng JDK.
- Future của chuỗi có thể hoàn tất ngoại lệ.
- Một ScheduledFuture của periodic task không phải dòng kết quả nghiệp vụ cho từng tick.

Trong Spring, ThreadPoolTaskScheduler có cơ chế **ErrorHandler** cho scheduled tasks; hành vi log/suppress/propagate phụ thuộc cấu hình và kiểu tác vụ. Không giả định ngoại lệ từ @Scheduled luôn dừng vĩnh viễn lịch hoặc luôn tự retry an toàn.

Khi callback chỉ gọi **executor.execute(...)**:

- Lỗi **submit/rejection** có thể xuất hiện ngay trong callback và được ErrorHandler của scheduler nhìn thấy.
- Lỗi **business job** xuất hiện sau đó trong worker và **không tự quay về stack** của callback đã return.
- Nếu dùng **ExecutorService.submit(Callable)**, lỗi thường được lưu vào Future và cần được quan sát bằng get, callback hoặc job status.
- Nếu dùng **CompletableFuture** hoặc @Async, cần xử lý **exceptional completion** hoặc handler phù hợp; không được coi không có log là không có lỗi.

Một chính sách tốt là ghi riêng **scheduler.callback.failure**, **executor.rejected**, **job.failed** và **job.completed** thay vì trộn vào một metric “cron failed”.

## 17. Khi nào nên dùng @Async, khi nào nên dùng execute/submit?

| Nhu cầu | Hướng triển khai |
| --- | --- |
| Chỉ muốn trigger gọi worker đơn giản | @Scheduled → TaskExecutor.execute |
| Muốn handle kết quả và cancel theo job | TaskExecutor.submit hoặc API trả Future/CompletableFuture có quản lý |
| Muốn gọi async method theo business service | @Scheduled trên bean A → @Async trên bean B qua Spring proxy |
| Muốn chỉ chọn executor theo tên | @Async("jobExecutor") hoặc inject đúng TaskExecutor |
| Muốn transaction/method security trong worker | Gọi service bean Spring khác qua proxy tại worker boundary, với context/transaction phù hợp |
| Muốn công việc dài chạy bền vững | Durable job engine/queue và state, không chỉ @Scheduled + in-memory executor |

**@Async cần proxy** trong chế độ Spring AOP phổ biến: bean phải được Spring quản lý, @EnableAsync bật và lời gọi phải đi qua proxy; self-invocation như this.asyncMethod() trong cùng bean có thể bỏ qua advice. Khi dùng TaskExecutor.execute tường minh, ranh giới chuyển worker được tạo **ngay ở execute**, không phụ thuộc @Async.

Nếu job có **@Transactional**, ranh giới transaction ở request/scheduler thread **không tự truyền** sang worker. Nên đặt transaction trên một service method được worker gọi qua proxy, hoặc quản lý transaction tại worker theo contract. Đừng giữ EntityManager/request-scoped bean sang thread khác.

## 18. Ngữ cảnh bảo mật, MDC và dữ liệu đầu vào

Scheduler callback và worker có thể chạy trên **hai thread khác nhau**, nên cần kiểm soát data/context propagation:

- **Dữ liệu business:** chụp immutable command/DTO khi callback tạo job, truyền qua parameter; không đặt ID job của từng lượt vào mutable instance field singleton.
- **MDC/tracing:** cần TaskDecorator hoặc propagation mechanism phù hợp; tự động truyền toàn bộ ThreadLocal không được bảo đảm.
- **SecurityContext:** cần Spring Security wrapper như DelegatingSecurityContextAsyncTaskExecutor hoặc chính sách service identity/authorization phù hợp. Một cron chạy không có HTTP user hiện tại, nên đừng tự nhận nó có principal của request gần nhất.
- **Transaction:** thiết lập transaction ở worker nếu logic cần, không coi transaction của callback sống xuyên thread.
- **Deadline:** chụp deadline vào job data, tính cả queue wait và thời gian chạy; nếu job bắt đầu quá muộn có thể phải bỏ trước khi tác động dữ liệu.
- **Resource ownership:** file/stream/connection mở ở callback có thể không hợp lệ khi worker thực thi sau đó; truyền ID/lifecycle handle bền vững khi phù hợp.

Trong cron chạy nền, thường nên dùng **service account với quyền tối thiểu** hoặc một job identity được quản lý, thay vì lấy SecurityContext của một người dùng bất kỳ từ ThreadLocal của pool.

## 19. Shutdown và cancellation: hai pool, hai vòng đời

Khi ứng dụng dừng, cả **scheduler** và **worker executor** đều cần có chiến lược lifecycle.

Trong mô hình direct:

~~~text
scheduler owns scheduled callback AND business work
    |
    +-- shutdown/cancel callback có thể tác động trực tiếp
        tới task đang thực thi theo implementation
~~~

Trong mô hình delegated:

~~~text
scheduler: ngừng kích hoạt callback mới
    |
    +-- worker executor vẫn có task đang chạy hoặc chờ
    |
    +-- phải đóng/đợi worker theo policy riêng
~~~

Những tình huống cần xử lý:

1. **Dừng nhận lịch mới** trước khi đóng worker executor để callback không tiếp tục submit vào pool đã shutdown.
2. **Đợi các job đã nhận** hoàn tất trong thời hạn phù hợp, hoặc yêu cầu hủy/cancel và ghi trạng thái nếu phải dừng.
3. **Đừng tin ScheduledFuture.cancel(...) sẽ hủy cả worker jobs đã được submit**.
4. Nếu worker đang có I/O chặn, việc ngắt thread là best effort; cần downstream timeout.
5. Nếu task đã nằm trong queue, cleanup trong body task có thể chưa từng chạy; tài nguyên tạo trước submit cần owner riêng.
6. Nếu job không được phép mất qua restart, chỉ dùng in-memory executors là chưa đủ; phải lưu job bền vững.

Spring có lifecycle hỗ trợ graceful shutdown đối với các executor/scheduler tương ứng; các thuộc tính cụ thể thay đổi theo implementation và phiên bản. Cần test shutdown trong deployment thật, không chỉ gọi close context trên test nhanh rồi giả định mọi job đã xong.

## 20. Monitoring đúng hai tầng: trigger và worker

Có ít nhất hai nhóm metric cần tách rõ.

### Nhóm A — scheduler

- **Scheduled fire count**: số lần callback theo lịch thực sự được kích hoạt.
- **Scheduler lag**: thời điểm callback thực tế bắt đầu so với mốc dự kiến.
- **Callback duration**: thời gian chạy chính callback.
- **Callback failure**: exception xảy ra trước khi callback return.
- **Scheduler active threads và delayed queue depth**, khi implementation có API/metrics đáng tin.
- **Drift theo cron zone** và lịch chuyển DST nếu có ảnh hưởng.

### Nhóm B — worker

- **Submission attempts/accepted/rejected**: bao nhiêu lần scheduler cố giao việc và kết quả ra sao.
- **Task queue wait**: từ khi accepted đến khi worker bắt đầu chạy.
- **Active worker threads**, worker pool size, max threads, queue size/capacity.
- **Business job duration, success, failure, cancelled**, deadline miss.
- **In-flight job count** và số lần skip/coalesce do single-flight guard.
- **Downstream resource saturation**, như DB connections, HTTP client limits hoặc CPU.

Khi dùng **queueCapacity=0** với ThreadPoolTaskExecutor, queue được tổ chức bằng **SynchronousQueue** không có buffer; queueSize có thể luôn bằng 0 ngay cả khi executor bão hòa và reject. Đừng coi queueSize=0 là bằng chứng worker rảnh.

Một dashboard tốt cho tình huống “cron đúng giờ nhưng report cập nhật chậm” sẽ so sánh:
- Callback bắt đầu đúng lịch?
- Submit accepted hay rejected?
- Worker bắt đầu sau bao lâu?
- Job hoàn tất hay fail?
- Có hơn một job cùng loại đang in-flight?
- Một pod hay nhiều pods đang cùng xử lý?

Nếu chỉ log **"@Scheduled fired"**, bạn chưa chứng minh công việc nghiệp vụ đã bắt đầu, càng chưa chứng minh nó hoàn tất.

## 21. Test ThreadPoolTaskScheduler trong Spring mà không phụ thuộc đồng hồ thực

Một integration test với Spring nên kiểm tra **cấu hình và đường chạy**, không kỳ vọng cron xảy ra đúng một mili giây trên CI.

Cách kiểm tra:

1. Tạo ThreadPoolTaskScheduler với prefix **trigger-** và ThreadPoolTaskExecutor prefix **job-**.
2. Dùng method được scheduling hoặc gọi TaskScheduler.schedule(Runnable, Instant.now()) trong test.
3. Trong callback, ghi thread identity/name, gửi việc sang executor.
4. Ở worker, ghi thread identity/name rồi chờ **CountDownLatch release**.
5. Trong khi worker đang chờ, schedule callback thứ hai và assert callback này vẫn chạy trong thời hạn.
6. Mở release; chờ worker-finished latch rồi đối chiếu kết quả.
7. Đóng ApplicationContext; đảm bảo không giữ worker vô hạn sau test.

Với **@Scheduled** thực tế, có thể dùng fixedDelay lớn và điều phối bằng latch, hoặc tách logic trigger thành method có thể gọi thủ công để test chính sách submit. Lịch theo cron không nên được test bằng cách ngủ tới phút tiếp theo nếu chỉ cần xác minh logic.

### Test overlap theo business contract

Nếu job không được chạy đồng thời:

1. Worker A đặt **inFlight=true** rồi chờ latch.
2. Trigger tick B xảy ra khi A chưa hoàn tất.
3. Xác minh B bị **skip/coalesce** hoặc được xếp hàng theo chính sách.
4. Mở latch để A hoàn tất và guard được reset.
5. Trigger tick C, xác minh một job mới được chấp nhận.
6. Nếu guard dùng AtomicBoolean, chạy test nhiều callbacks đồng thời để kiểm chứng **compareAndSet**, không dùng cờ boolean thường không đồng bộ.

### Test overload

- Cấu hình pool với worker và queue nhỏ.
- Giữ workers bằng latch để bão hòa.
- Gọi callback submit và xác minh chính sách **TaskRejectedException**, metric và việc reset guard.
- Nếu policy là CallerRunsPolicy, xác minh callback có thể chạy business task trong chính scheduler thread và đo tác động tới lịch tiếp theo.
- Đừng dùng DiscardPolicy rồi chỉ assert callback không ném exception; task có thể đã mất.

## 22. Những nhầm lẫn phổ biến

**“TaskScheduler có nghĩa Spring luôn dùng một trigger thread riêng và một executor xử lý riêng.”** Sai. ThreadPoolTaskScheduler thực thi scheduled Runnable ngay trên scheduler thread(s).

**“@Scheduled làm business job luôn chạy trên thread background riêng biệt.”** Không đủ chính xác. Method được gọi bởi scheduler thread; việc có worker pool khác phụ thuộc implementation hoặc code delegate.

**“Tăng scheduler poolSize từ 1 lên 10 là tách được trách nhiệm trigger và worker.”** Sai. Những thread đó vẫn thuộc scheduler; nó chỉ cho phép nhiều callback cùng thực thi.

**“FixedDelay=5 giây chắc chắn hai business jobs không overlap.”** Sai nếu scheduled callback chỉ submit job rồi return. Delay tính từ callback completion.

**“FixedRate sẽ chạy một periodic Runnable cùng lúc trên 2 worker nếu period quá ngắn.”** Không đúng với ScheduledThreadPoolExecutor cho cùng một periodic task; các lượt của task đó không overlap. Tuy nhiên, công việc được delegate từ các lượt callback có thể overlap.

**“CronTrigger luôn chạy bù tất cả mốc bị lỡ.”** Không thể khẳng định. Cron trigger semantics có biến thể và phụ thuộc completion/lịch sử; cần xem version/API và chính sách nghiệp vụ.

**“ScheduledFuture của callback delegate chứng minh business job đã hoàn thành.”** Sai. Nó chỉ phản ánh callback được scheduler quản lý; Future của worker hoặc job status mới mô tả việc nghiệp vụ.

**“Hủy ScheduledFuture sẽ hủy mọi Future của worker đã tạo từ callback.”** Sai. Các handle này độc lập trừ khi ứng dụng chủ động nối cancellation.

**“@Scheduled có @Async trong source chắc chắn chạy đúng pool.”** Không được đảm bảo nếu thiếu @EnableAsync, đường gọi qua proxy hoặc cấu hình executor. Test runtime.

**“Callback return nghĩa là đã xử lý xong và có thể trả success.”** Sai khi callback chỉ submit.

**“Scheduler không block thì hệ thống không overload.”** Sai. Backlog có thể chuyển sang worker queue, downstream connections hoặc CPU.

**“CallerRunsPolicy luôn giữ scheduler không bận.”** Sai. Khi worker pool bão hòa, scheduler callback có thể bị buộc chạy công việc ngay trên scheduler thread.

**“Một AtomicBoolean đảm bảo toàn cluster chỉ có một job.”** Sai. Nó chỉ bảo vệ một object instance/JVM.

**“Cứ thêm Thread.sleep ở callback là worker có thời gian xử lý.”** Không phải backpressure an toàn; ngủ giữ scheduler thread và không nêu rõ lifecycle/in-flight.

**“Không có exception trong @Scheduled nghĩa là job đã thành công.”** Sai khi lỗi phát sinh sau đó ở worker.

**“Tôi có một lịch cron nên job không thể chạy trùng.”** Sai khi có nhiều pods, nhiều trigger registrations hoặc business job delegate.

**“Trong cron có user đang đăng nhập gần nhất để mang SecurityContext sang worker.”** Sai. Lịch nền không tự có HTTP principal của request khác; cần identity và authorization riêng.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** ThreadPoolTaskScheduler poolSize=1 có callback A chặn 20 giây. Callback B tới hạn trong lúc A đang chạy. B có được chạy ngay không?

**Đáp án:** Không được bảo đảm; với một scheduler thread đang bị giữ, B thường phải đợi A kết thúc. Cần giảm thời gian callback hoặc tăng pool/tách worker nếu phù hợp.

**Câu 2.** Callback @Scheduled chỉ gọi jobExecutor.execute(...) rồi return. Job chạy 30 giây, @Scheduled(fixedDelay=5_000). Lượt thứ hai phải đợi 30 giây không?

**Đáp án:** Không. FixedDelay được tính sau khi **callback gửi việc** hoàn tất, nên lượt kế tiếp có thể tới trong khi job trước vẫn chạy.

**Câu 3.** Một ScheduledThreadPoolExecutor có 4 threads và một Runnable được scheduleAtFixedRate mỗi giây; mỗi run mất 5 giây. Những lần chạy của cùng periodic Runnable có overlap không?

**Đáp án:** Không theo hợp đồng JDK; các lần kế tiếp có thể bắt đầu trễ. Các Runnable khác vẫn có thể chạy song song trên các worker còn lại.

**Câu 4.** Nếu callback periodic gửi hai job độc lập tới pool 2 workers, hai job đó có overlap không?

**Đáp án:** Có thể. Không overlap của callback periodic không đồng nghĩa không overlap của jobs đã delegate.

**Câu 5.** TaskScheduler.schedule trả ScheduledFuture xong rồi, nhưng job do callback submit vẫn đang chạy. Có phải bug của scheduler không?

**Đáp án:** Không. Future của scheduler chỉ đại diện callback; cần worker Future/job status để theo dõi kết quả nghiệp vụ.

**Câu 6.** Tại sao tăng scheduler poolSize có thể không phải giải pháp tốt khi công việc là blocking DB call?

**Đáp án:** Vì các DB calls vẫn chiếm scheduler threads và cạnh tranh downstream connections. Tách worker với giới hạn, queue và timeout thường dễ vận hành hơn.

**Câu 7.** Khi worker pool bão hòa với CallerRunsPolicy, callback @Scheduled có thể làm công việc nặng không?

**Đáp án:** Có. CallerRuns có thể thực thi Runnable trên chính scheduler thread đang gọi execute; kiến trúc tách thread tạm thời không còn.

**Câu 8.** Làm cách nào để không có hai business jobs chạy cùng lúc trong một JVM, dù callback cứ được trigger?

**Đáp án:** Dùng single-flight guard (như AtomicBoolean.compareAndSet) với reset trong worker finally và trong nhánh submit rejected; hoặc một cơ chế điều phối khác đúng contract.

**Câu 9.** Guard AtomicBoolean trong một pod có ngăn pod khác chạy cùng job không?

**Đáp án:** Không. Cần cơ chế cluster-wide như distributed lease/lock, job coordinator hoặc idempotency/constraints tại storage.

**Câu 10.** FixedDelay có thể đo từ khi business job hoàn tất khi callback đã delegate không?

**Đáp án:** Không tự động. Muốn như vậy phải điều phối lịch sau completion thật hoặc giữ callback cho tới completion, với đánh đổi scheduler thread bị chiếm.

**Câu 11.** Ứng dụng báo scheduler callback duration 2ms nhưng báo cáo đến muộn 2 phút. Có thể xảy ra không?

**Đáp án:** Có. Callback chỉ submit nhanh nhưng job chờ 2 phút trong worker queue hoặc downstream bị nghẽn.

**Câu 12.** Hủy recurring ScheduledFuture có tự hủy toàn bộ jobs đã submit qua executor từ những tick trước không?

**Đáp án:** Không mặc nhiên. Cần quản lý cancellation từng job.

**Câu 13.** Nếu @Scheduled method ném exception, mọi implementation đều chắc chắn dừng lịch vĩnh viễn không?

**Đáp án:** Không. JDK periodic tasks có semantics suppress sau uncaught exception; Spring scheduler có ErrorHandler và cấu hình khác. Kiểm tra implementation thực tế.

**Câu 14.** @Scheduled trên ba instance Spring nghĩa là chỉ một callback toàn hệ thống chạy đúng giờ không?

**Đáp án:** Không. Mỗi instance có scheduler riêng nếu không có điều phối cluster.

**Câu 15.** SimpleAsyncTaskScheduler giống ThreadPoolTaskScheduler trong mọi trường hợp chứ?

**Đáp án:** Không. SimpleAsyncTaskScheduler có scheduler thread và chiến lược tạo thread khác; Spring lưu ý fixed-delay tasks của loại này hoạt động trên scheduler thread, trong khi ThreadPoolTaskScheduler thực thi callback trên chính các scheduler threads.

## 24. Checklist triển khai

- [ ] Xác định **TaskScheduler implementation thực tế**, không chỉ interface.
- [ ] Đối với **ThreadPoolTaskScheduler**, nhớ callback chạy trên scheduler threads.
- [ ] Chỉ định kích thước scheduler pool theo số và độ dài callback.
- [ ] Quyết định callback thực hiện nghiệp vụ trực tiếp hay **delegate** vào TaskExecutor.
- [ ] Nếu delegate, tạo **worker pool hữu hạn và queue có giới hạn**, có rejection policy.
- [ ] Phân biệt **callback completion** với **business job completion**.
- [ ] Đánh giá fixedRate/fixedDelay/cron theo **thời gian thực sự của callback**, không giả định chờ worker.
- [ ] Nếu business job không được overlap, triển khai single-flight/lock hoặc job coordinator phù hợp.
- [ ] Nếu job phải được xử lý đủ mọi lượt, không dùng skip/coalesce mà không có chủ đích.
- [ ] Kiểm soát overload khi worker bị bão hòa, đặc biệt CallerRuns/Discard.
- [ ] Có metrics scheduler lag, callback duration, worker queue wait, active jobs, failures/rejections.
- [ ] Tách cancellation lịch và cancellation những jobs đã được submit.
- [ ] Xác định trình tự shutdown scheduler rồi worker và deadline cleanup.
- [ ] Nếu nhiều pods, thiết kế distributed coordination hoặc idempotency.
- [ ] Nếu có @Async, bảo đảm lời gọi qua Spring proxy và executor đúng tên.
- [ ] Không để business state mutable của từng lượt trong singleton bean.
- [ ] Dùng transaction, security identity và tracing phù hợp cho worker thread.
- [ ] Kiểm thử có latch/Future.get(timeout), tránh timing giả bằng sleep.
- [ ] Với job quan trọng, lưu trạng thái bền vững và cân nhắc job scheduler/queue chuyên dụng.

## Kết luận

**TaskScheduler điều phối thời điểm được phép kích hoạt; Runnable/callback đã được hẹn sẽ thực thi theo mô hình thread của implementation.** Đặc biệt, **ThreadPoolTaskScheduler chạy callback trên scheduler threads**, chứ không tự chuyển business logic sang một TaskExecutor khác. Nếu callback làm việc nặng trực tiếp, nó giữ scheduler thread; nếu callback giao việc sang worker pool, scheduler có thể rảnh sớm nhưng cần theo dõi trạng thái, lỗi, backlog, overlap và cancellation của business job riêng.

Để thiết kế concurrency có thể giải thích được, hãy đặt rõ **scheduler thread cho việc kích hoạt ngắn gọn** và **worker pool cho xử lý tài nguyên nặng** khi thực sự cần tách biệt, đồng thời không đánh đồng fixedDelay/callback completion với business completion. Sự tách biệt này giúp đo đúng scheduler lag so với queue wait, lựa chọn overload policy phù hợp, tránh chạy trùng trong cluster và không kết luận thành công chỉ vì một callback đã gửi xong task.

**Tài liệu tham khảo chính thức:**

- Spring Framework: [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — TaskScheduler, @Scheduled, ThreadPoolTaskScheduler, SimpleAsyncTaskScheduler và Trigger.
- Spring Javadoc: [ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html) và [ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
- Spring Javadoc: [TaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html), [@Scheduled](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html), [CronTrigger](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronTrigger.html).
- Java SE 17: [ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html), [ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html), [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
