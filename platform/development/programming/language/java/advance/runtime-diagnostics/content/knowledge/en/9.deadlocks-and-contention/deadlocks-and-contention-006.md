# 9.6 Thread pool bão hòa, hàng đợi tăng và tác vụ phụ thuộc lẫn nhau

> **Java Advance – runtime-diagnostics** · **9. Treo và tranh chấp**

## 1. Bài toán: service còn sống nhưng công việc không hoàn tất

Một Java service có thể vẫn đáp ứng health check, JVM không báo out-of-memory, CPU thậm chí thấp, nhưng request ngày càng chậm hoặc timeout. Thread dump cho thấy rất nhiều workers ở *WAITING*, queue của executor tăng liên tục và completed-task rate gần như đứng yên.

Một khả năng đặc biệt nguy hiểm là **thread pool starvation do tác vụ phụ thuộc lẫn nhau**: tác vụ cha đã chiếm worker, lại gửi tác vụ con vào **chính pool đó**, sau đó gọi *Future.get()* hoặc *CompletableFuture.join()* để chờ. Nếu tất cả workers đều bận chờ những tác vụ con đang nằm trong queue, **không còn worker để chạy tác vụ con**. Hệ thống có công việc chờ thực thi, nhưng không có năng lực thực thi dành cho công việc mở khóa tiến trình.

Tình huống ấy cần phân biệt với **bão hòa thông thường** khi tốc độ nhận công việc vượt tốc độ xử lý, và với **contention** khi một tài nguyên bên ngoài (database connection, monitor, lock, semaphore, network) khiến thời gian chiếm worker tăng.

**Bài học này tập trung vào ba hiện tượng liên kết nhau:**

1. **Pool saturation:** workers đạt giới hạn concurrency; tác vụ mới phải chờ, bị từ chối hoặc được xử lý theo rejection policy.
2. **Queue buildup:** backlog tăng vì lượng công việc đến lớn hơn khả năng hoàn tất, hoặc workers bị giữ quá lâu.
3. **Task dependency starvation:** tasks đang giữ workers chờ tasks khác chưa thể được chạy, thường có phụ thuộc vòng hoặc phụ thuộc vào cùng nguồn thực thi hữu hạn.

Mục tiêu là biết **cơ chế**, đọc **bằng chứng runtime**, phân biệt **nguyên nhân** và áp dụng **biện pháp giảm tải/tách phụ thuộc** có kiểm soát — thay vì chỉ tăng số thread hoặc queue size.

### Sau bài học, bạn cần làm được

- Giải thích *corePoolSize*, *maximumPoolSize*, *workQueue* và *RejectedExecutionHandler* tác động đến thứ tự **tạo thread → xếp hàng → mở rộng → từ chối**.
- Đọc các chỉ số *poolSize*, *activeCount*, *queue size*, *taskCount*, *completedTaskCount* và biết giới hạn độ chính xác của chúng.
- Nhận diện chuỗi “worker giữ chỗ → submit child → chờ child → child nằm trong queue”.
- Phân biệt queue tăng vì lưu lượng cao, dependency chậm, retry amplification, lock contention hay phụ thuộc tác vụ tự gây starvation.
- Hiểu vì sao có *Future.get(timeout)* không đồng nghĩa child đã được hủy; vì sao *thread dump không báo deadlock* chưa loại trừ starvation.
- Biết chọn **bounded queue, rejection/backpressure, concurrency limits, timeouts/deadlines, task composition** và kiến trúc pool hợp lý.
- Chạy được ví dụ Java 17+ tái hiện **nested-task starvation có timeout** và **rejection khi pool + queue đầy**, không tạo deadlock vô hạn.
- Viết một kết luận incident dựa trên **queue/completion metrics + thread dumps + tracing**, không chỉ dựa vào một dòng stack.

## 2. Mô hình cơ bản: producers, executor, workers và queue

~~~text
                      +----------------------------------+
Request / message     | ThreadPoolExecutor               |
producer(s)           |                                  |
  -- submit() ------> |  [workQueue: pending tasks]       |
                      |         |                        |
                      |         v                        |
                      |  worker-1  worker-2 ... worker-N  |
                      |       |        |          |       |
                      |       +------ results ---+       |
                      +------------+---------------------+
                                   |
                       completed / failed / timeout

Nếu cả workers và queue không nhận được việc mới:
submit / execute --> RejectedExecutionHandler
~~~

Một **worker active** nghĩa là nó đang đảm nhận một task theo định nghĩa executor; worker đó có thể đang dùng CPU, đang blocked ở I/O, đang đợi monitor, đang park ở Future, hoặc đang chờ tài nguyên khác. **Active count không phải CPU utilization**.

**Work queue** giữ những task **đã được chấp nhận nhưng chưa bắt đầu chạy**. Nó không nhất thiết chứa request objects theo cùng 1:1 với HTTP requests: một request có thể tạo nhiều tasks, và một task có thể xử lý nhiều bản ghi. Vì vậy *queue.size()* chỉ có ý nghĩa trong phạm vi **đúng executor instance và kiểu task**.

### Ba thời gian thường bị trộn lẫn

\[
T_{\text{end-to-end}} \approx T_{\text{admission}} +
T_{\text{queue wait}} + T_{\text{execution}} +
T_{\text{downstream/response}}
\]

Đây là **mô hình phân rã khái niệm**, không phải các hạng luôn đo độc lập không chồng lấn. Ví dụ *execution* có thể bao gồm thời gian chờ downstream, và HTTP thread có thể chờ kết quả executor ở chỗ khác.

- **Queue wait:** từ lúc task được chấp nhận vào executor đến khi một worker thực sự bắt đầu chạy.
- **Task execution/occupancy:** từ khi worker lấy task đến lúc task hoàn tất, kể cả những khoảng *get()/join()/I/O* khiến worker không tạo ra tiến triển.
- **Response latency:** độ trễ cảm nhận của caller; có thể gồm nhiều queues, hops, retries và deadlines.

Nếu endpoint có p99 tăng, phải xác định tăng ở **queue wait** hay **task processing**, và task processing chậm vì CPU, network hay dependency starvation.

## 3. ThreadPoolExecutor quyết định khi nào xếp hàng?

Với *ThreadPoolExecutor* điển hình trên Java 17, khi *execute()* nhận task mới:

1. Nếu số worker đang có **ít hơn corePoolSize**, executor ưu tiên khởi tạo worker cho task mới.
2. Khi đã có ít nhất **corePoolSize** workers, executor **ưu tiên offer task vào queue** nếu queue chấp nhận.
3. Nếu queue **không nhận được task** (ví dụ queue bounded đã đầy), executor mới thử tăng worker đến **maximumPoolSize**.
4. Nếu không xếp hàng được và không tạo thêm worker, executor gọi **RejectedExecutionHandler**; executor đang shutdown cũng có thể từ chối.

**Bảng ví dụ:** cấu hình *core=2, max=5, queue capacity=3*, tất cả tasks đều giữ workers đủ lâu; đây là chuỗi minh họa chấp nhận theo từng lần submit, không là số đo production.

| Task mới | Đang có workers | Queue trước khi nộp | Hành vi có thể theo thuật toán |
| --- | --- | --- | --- |
| 1 | 0 | 0 | Tạo worker 1 |
| 2 | 1 | 0 | Tạo worker 2 |
| 3 | 2 | 0 | Đưa vào queue |
| 4 | 2 | 1 | Đưa vào queue |
| 5 | 2 | 2 | Đưa vào queue |
| 6 | 2 | 3 (đầy) | Thử tạo worker 3 |
| 7 | 3 | 3 | Thử tạo worker 4 |
| 8 | 4 | 3 | Thử tạo worker 5 |
| 9 | 5 (max) | 3 (đầy) | Rejection policy |

**Điểm dễ nhầm:** *maxPoolSize* không có nghĩa executor sẽ tăng đến max ngay khi hai core workers bận. Với queue còn chỗ, task mới **được xếp hàng trước**; max chỉ phát huy khi offer vào queue thất bại.

### 3.1 Queue không giới hạn và hiệu ứng maximumPoolSize bị vô hiệu

~~~java
// Mảnh mã minh họa, không phải chương trình độc lập.
java.util.concurrent.ExecutorService executor =
        java.util.concurrent.Executors.newFixedThreadPool(8);
~~~

Theo hợp đồng Java SE 17, *newFixedThreadPool(8)* dùng **tám workers tối đa** và **shared unbounded queue**. Nếu arrival rate duy trì cao hơn service rate, queue có thể tăng rất lớn và chiếm bộ nhớ. Executor **không** tự “mở thêm đến 100 threads” chỉ vì queue dài.

Với *ThreadPoolExecutor* tự cấu hình cùng queue không giới hạn, việc tăng *maximumPoolSize* thường **không làm pool tăng vượt core** khi queue tiếp tục nhận tasks. Đây là nguyên nhân thường gặp của câu “đã nâng maxPoolSize mà p99 vẫn tăng”.

*Unbounded* ở API nghĩa là **không có giới hạn nhỏ do bạn áp đặt**, chứ không có nghĩa bộ nhớ là vô hạn. Queue có thể dẫn đến **OOM/GC pressure**, caller timeout hoặc latency cực lớn trước khi xuất hiện một rejection rõ ràng.

### 3.2 Queue bounded và thread budget

Với *ArrayBlockingQueue<>(capacity)*, queue có số chỗ hữu hạn. Khi queue đầy, executor có thể tăng workers đến maximumPoolSize; khi cả hai giới hạn đều đạt, policy quyết định làm gì với task tiếp theo.

Đây là **capacity boundary**, không phải phép sửa mọi bug. Một queue bounded giúp hệ thống báo overload sớm hơn, nhưng nếu policy từ chối mà phía caller retry vô hạn, tổng áp lực vẫn có thể tăng. Cần **admission control, rejection visibility, retry budgets và backpressure** đồng bộ.

### 3.3 SynchronousQueue: handoff trực tiếp

*SynchronousQueue* không lưu backlog theo kiểu queue có capacity > 0: mỗi lần chuyển task cần một consumer sẵn sàng nhận. Với *ThreadPoolExecutor*, direct handoff có thể khiến pool mở worker nhanh hơn (cho đến max) hoặc reject khi không có worker và không thể mở rộng.

Nó có thể tránh một số kiểu “task chờ child nằm sâu trong queue”, nhưng **không tự triệt tiêu phụ thuộc vòng**. Nếu tất cả workers tối đa đều bị parent tasks chiếm, child vẫn có thể bị từ chối; nếu max quá lớn, chi phí OS threads và memory tăng. Hãy cân bằng handoff với giới hạn concurrency và hành vi overload.

## 4. Hai nguyên nhân lớn của queue tăng

### 4.1 Arrival rate lớn hơn service rate

Gọi:

- \(\lambda\) là số **tasks/giây đến** một executor.
- \(\mu\) là số **tasks/giây hoàn tất** từ executor tại điều kiện/tải cụ thể.
- \(Q\) là số tasks đang chờ trong queue.

Trong một cửa sổ chưa bị tác động bởi rejection/cancel và task sizes tương đối đồng nhất:

\[
\Delta Q \approx (\lambda - \mu) \cdot \Delta t
\]

Nếu \(\lambda \gt \mu\) kéo dài, backlog có xu hướng tăng. Nếu queue bounded, kết quả cuối có thể là **rejection**, chứ không phải queue tăng mãi.

**Ví dụ minh họa:** một pool hoàn tất trung bình khoảng 20 tasks/s nhưng nhận 50 tasks/s, trong 10 giây có thể tích lũy thêm khoảng 300 queued tasks (nếu đủ capacity và không có các hiệu ứng khác). Đây là ước tính để suy luận, không phải mô hình bảo đảm với mọi arrival/task distribution.

Đừng nhầm *request rate* với *task arrival rate*: một request tạo 5 fan-out subtasks thì \(\lambda_{\text{tasks}}\) có thể cao hơn đáng kể so với \(\lambda_{\text{requests}}\).

### 4.2 Workers bị giữ lâu vì chờ I/O, lock hoặc task khác

Ngay cả khi arrival rate **không tăng**, throughput vẫn có thể tụt mạnh nếu task duration tăng:

- Downstream API/database chậm; worker giữ chỗ trong blocking call.
- Hết database connections, semaphore permits hoặc rate-limit tokens.
- Lock contention: nhiều tasks đang chờ một monitor hoặc ReentrantLock.
- Retry loop; mỗi task tự lặp lại nhiều lần thay vì giải phóng worker.
- **Nested dependency:** parent task đang chiếm worker rồi *get()/join()* chờ child ở cùng queue.

Dấu hiệu “CPU thấp nhưng activeCount cao, queue tăng, completed/s thấp” thường khiến ta kiểm tra **blocking/park/resource waits** trước khi nâng CPU allocation. CPU thấp **không chứng minh** deadlock, vì service có thể chỉ đang chờ downstream bình thường nhưng chậm.

## 5. Little's Law: dùng cho suy luận đúng phạm vi

Ở **hệ ổn định** với định nghĩa rõ arrival/completion và cùng phạm vi đo:

\[
L \approx \lambda W
\]

Trong đó \(L\) là số phần việc trung bình trong hệ, \(\lambda\) là throughput trung bình và \(W\) là thời gian trung bình lưu lại. Với **riêng queue**, có thể dùng \(L_q \approx \lambda W_q\) khi điều kiện ổn định và phạm vi phù hợp.

**Không sử dụng máy móc trong lúc queue đang tăng vô hạn.** Little's Law là quan hệ dài hạn của hệ ổn định, không phải “đường thẳng” dự báo chính xác cho mọi spike.

Ví dụ, nếu trung bình 200 queued tasks và throughput ổn định 100 tasks/s, queue wait trung bình có thể xấp xỉ 2 s **nếu** các giả định phù hợp. Với retry amplification, task size rất biến thiên, dropping/rejections, nhiều queue nối tiếp hoặc autoscale, cần xem lại mô hình trước khi chia hai số.

## 6. Tác vụ phụ thuộc lẫn nhau: cơ chế starvation tự gây ra

Hãy xét pool **một worker**, một queue, hai tác vụ:

~~~text
          SINGLE-WORKER EXECUTOR
         +----------------------+
         | worker-1             |
         |  chạy Parent         |
         |    submit Child -----+--> queue: [Child]
         |    child.get()       |         |
         |    chờ Child xong    |         |
         |                      |         |
         +----------------------+         |
                  ^                       |
                  +--- Child cần worker ---+
~~~

Parent giữ worker duy nhất rồi chờ Child. Child đã được nhận vào queue nhưng **không thể chạy** cho đến khi worker rảnh. Worker sẽ không rảnh cho đến khi Parent dừng chờ hoặc kết thúc. Nếu *get()* không timeout và không có cơ chế khác giải phóng worker, đây là **starvation do dependency** có thể kéo dài vô hạn.

### 6.1 Điều kiện đủ thường gặp

- Executor có concurrency hữu hạn \(N\).
- Có \(N\) parent tasks cùng lúc **giữ đủ N workers**.
- Mỗi parent submit child hoặc continuation cần thực thi **bởi chính executor đó**.
- Parent dùng blocking wait để đợi child xong.
- Những child tasks nằm trong queue hoặc không thể được accepted vì pool đã saturated.
- Không có timeout/cancellation/callback nào làm parent nhả worker.

Nếu đủ các điều kiện trên, **không worker nào còn chỗ chạy child**, dù CPU có thể gần 0%.

### 6.2 Vì sao không nhất thiết là Java monitor deadlock?

*ThreadMXBean.findDeadlockedThreads()* tìm các kiểu deadlock trên **object monitors hoặc ownable synchronizers** trong phạm vi API hỗ trợ. Dependency giữa *Future.get()*, task queues và executor workers có thể không tạo một monitor lock cycle được detector nhận diện.

Do đó, thread dump có thể chỉ hiện worker ở *FutureTask.get()*, *CompletableFuture.join()* hoặc *LockSupport.park()*, trong khi lệnh deadlock detector báo “không tìm thấy”. Điều đó **không loại trừ** thread-pool starvation.

Nên nói rõ:

- **Java-level monitor deadlock:** khóa A/B chờ nhau theo chu trình.
- **Thread-pool dependency starvation / task deadlock:** các tasks chờ kết quả của tasks không thể được schedule vì mọi workers bị giữ.
- **Livelock/retry loop:** có hoạt động hoặc state thay đổi nhưng không đạt kết quả nghiệp vụ.

Chúng có thể cùng gây service treo nhưng **quan hệ nhân quả khác nhau**.

### 6.3 Biến thể nhiều workers

Nếu pool có 4 workers và 4 parent tasks đều submit child rồi chờ, sự cố cũng có thể xảy ra:

~~~text
worker-1: Parent A -> waits Child A
worker-2: Parent B -> waits Child B
worker-3: Parent C -> waits Child C
worker-4: Parent D -> waits Child D

queue: Child A, Child B, Child C, Child D
runnable workers available: 0
~~~

Queue length tăng không do “thiếu traffic xử lý” mà do **worker ownership và dependency graph sai**. Nếu maxThreads được tăng tạm thời, có thể Child nào đó chạy và giải phóng Parent, nhưng **đó không chứng minh cấu trúc code an toàn**: tải cao hơn vẫn có thể đạt ngưỡng mới và lặp lại.

### 6.4 Không đồng nhất tất cả Future.get() với lỗi

*Nhiều* tác vụ chờ một Future hoàn toàn hợp lệ khi Future được một **hệ khác có tiến triển độc lập** hoàn tất, ví dụ I/O callback trên event loop khác. Câu hỏi chính là:

> “Tác vụ đang được chờ **cần chính nguồn lực mà caller đang giữ** để có thể hoàn tất hay không?”

Nếu không, blocking wait vẫn có thể gây throughput thấp vì chiếm worker, nhưng không phải trường hợp dependency starvation vòng kín. Cần xem **executor topology, task submission path và completion ownership**, không dựa chỉ vào top stack frame.

## 7. Queue tăng vì nested fan-out: một request có thể thành nhiều tasks

Nếu một request cha tạo ra 10 subtasks và chờ tất cả, hệ thống có thể chuyển từ \(R\) requests/s thành khoảng \(10R\) subtasks/s trên executor dùng chung. Khi downstream chậm, parent giữ workers lâu hơn, còn child bị xếp hàng. Đây là **dependency + amplification**:

~~~text
incoming requests (λr)
       |
       v
parent tasks (occupy workers)
       |
       +--> child 1 \
       +--> child 2  > shared executor queue
       +--> child 3 /
       |
       +--> wait all children (workers not released)
~~~

Nếu mỗi parent gọi *invokeAll*, *Future.get*, *join* hoặc đồng bộ bằng latch, không có bảo đảm mọi child được schedule đúng lúc. *invokeAll()* không tự loại bỏ nguy cơ starvation nếu gọi trong task của pool hữu hạn dùng lại chính pool.

**Dấu hiệu thường thấy:**

- Active workers ≈ pool size/max.
- Many worker stacks at *FutureTask.get*, *CompletableFuture.join* hoặc *CountDownLatch.await*.
- Queue contains tasks whose parent tasks are currently waiting.
- Completed-task count gần đứng; queue wait age tăng.
- HTTP latency và timeouts tăng trong khi CPU có thể không tăng.

Một điểm cần kiểm tra là **queue chứa loại task nào**. Nếu queue toàn database result callbacks/child computations mà worker đang chờ, cấu trúc phụ thuộc rất đáng ngờ. Nếu queue chỉ chứa request mới và workers đang blocked tại network call, nguyên nhân có thể khác.

## 8. Ví dụ Java 17+ độc lập: nested wait và bounded rejection

Bài lab có **hai phép thử có đồng bộ rõ ràng** và **không tạo treo vô hạn**:

1. **Nested task dependency:** pool một worker, queue capacity một; parent submit child vào queue rồi đợi child *150 ms*. Vì parent đang giữ worker, child chưa thể chạy, nên parent timeout. Khi parent rời worker, child mới chạy và counter tăng.
2. **Bounded queue saturation:** một worker bị giữ bởi latch, task thứ hai chờ trong queue, task thứ ba bị *AbortPolicy* từ chối. Khi thả latch, hai task đã accepted hoàn tất.

Chương trình không cần thư viện ngoài JDK. Nó sử dụng *CountDownLatch* để không phụ thuộc vào việc ngủ một khoảng ngắn rồi hy vọng workers đã đạt trạng thái mong muốn. Các chờ trong main có timeout và *finally* có cleanup.

Tạo file **PoolSaturationLab.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public final class PoolSaturationLab {
    public static void main(String[] args) throws Exception {
        nestedDependency();
        boundedRejection();
    }

    private static ThreadPoolExecutor oneWorkerOneSlot() {
        return new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());
    }

    private static void nestedDependency() throws Exception {
        ThreadPoolExecutor pool = oneWorkerOneSlot();
        CountDownLatch childQueued = new CountDownLatch(1);
        CountDownLatch allowWait = new CountDownLatch(1);
        AtomicInteger childRan = new AtomicInteger();
        try {
            Future<String> parent = pool.submit(() -> {
                Future<?> child = pool.submit(childRan::incrementAndGet);
                childQueued.countDown();
                if (!allowWait.await(5, TimeUnit.SECONDS)) {
                    return "GATE_TIMEOUT";
                }
                try {
                    child.get(150, TimeUnit.MILLISECONDS);
                    return "UNEXPECTED";
                } catch (TimeoutException expected) {
                    return "TIMED_OUT";
                }
            });
            if (!childQueued.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Child was not queued");
            }
            System.out.println("nested.workers=" + pool.getPoolSize());
            System.out.println("nested.queued=" + pool.getQueue().size());
            System.out.println("nested.childBefore=" + childRan.get());
            allowWait.countDown();
            System.out.println("nested.parentWait=" + parent.get(5, TimeUnit.SECONDS));
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool failed to terminate");
            }
            System.out.println("nested.childAfter=" + childRan.get());
        } finally {
            allowWait.countDown();
            pool.shutdownNow();
        }
    }

    private static void boundedRejection() throws Exception {
        ThreadPoolExecutor pool = oneWorkerOneSlot();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();
        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    completed.incrementAndGet();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            pool.execute(completed::incrementAndGet);
            boolean rejected = false;
            try {
                pool.execute(completed::incrementAndGet);
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            System.out.println("bounded.workers=" + pool.getPoolSize());
            System.out.println("bounded.queued=" + pool.getQueue().size());
            System.out.println("bounded.rejected=" + rejected);
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool failed to terminate");
            }
            System.out.println("bounded.completed=" + completed.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy trên **JDK 17+**:

~~~bash
javac -encoding UTF-8 PoolSaturationLab.java
java PoolSaturationLab
~~~

**Chín dòng stdout đã được kiểm thử với chương trình trên JDK:**

~~~text
nested.workers=1
nested.queued=1
nested.childBefore=0
nested.parentWait=TIMED_OUT
nested.childAfter=1
bounded.workers=1
bounded.queued=1
bounded.rejected=true
bounded.completed=2
~~~

**Giải thích chính xác:**

- *nested.workers=1*: executor có đúng một worker.
- *nested.queued=1*: child đã được accept vào queue nhưng chưa có worker chạy.
- *nested.childBefore=0*: child chưa chạy vì worker đang thuộc parent.
- *nested.parentWait=TIMED_OUT*: chờ child thất bại do không có executor capacity, không phải vì child ném exception.
- *nested.childAfter=1*: khi parent đã kết thúc, worker lấy child và chạy — minh họa **timeout chờ không đồng nghĩa cancel child**.
- *bounded.queued=1*: task thứ hai đã vào queue một chỗ.
- *bounded.rejected=true*: task thứ ba bị policy từ chối, vì cả worker và queue đều bão hòa.
- *bounded.completed=2*: hai tasks đã được nhận kết thúc sau khi gate được thả; task bị reject không được thực thi.

**Lưu ý về tính chính xác:** chương trình có các latch tạo điều kiện xác định thứ tự trong lab; stdout trên đây được kiểm thử thực tế. Nếu môi trường thiếu CPU nghiêm trọng, các timeout bảo vệ của lab có thể làm nó ném exception, thay vì in đủ chín dòng; do đó đây không phải lời cam kết stdout trên mọi OS/JVM/scheduler.

### 8.1 Vì sao ví dụ không dùng Future.get() vô thời hạn?

Nếu parent dùng *child.get()* không timeout trong pool một worker, chương trình có thể treo không giới hạn. Đó là bug mà bài học **muốn nhận diện**, không nên yêu cầu người học chạy một demo dễ mắc kẹt.

Bài lab dùng *get(150, MILLISECONDS)* để giải phóng parent và cho child chạy sau đó. Timeout giúp phép thử tự kết thúc, **không sửa nguyên nhân kiến trúc**: với một workload thật, timeout vẫn gây request failure, retry, queue buildup và downstream work muộn.

### 8.2 Vì sao child vẫn chạy sau khi parent timeout?

*Future.get(timeout, unit)* chỉ giới hạn **thời gian chờ của caller**; nó không hủy computation. Để thử hủy cần một quyết định riêng, ví dụ *child.cancel(true)* khi logic cho phép và có cleanup/idempotency thích hợp. Nhưng *cancel(true)* chỉ cố gắng interrupt khi task đang chạy; không bảo đảm việc thực thi dừng ngay, nhất là với code không hợp tác với interruption.

Trong lab, child đã được accepted nên sau khi parent nhả worker nó hoàn thành bình thường. Đây là bằng chứng vì sao một request đã timeout **vẫn có thể gây tải hậu kỳ** nếu task không bị hủy hoặc downstream call chưa dừng.

### 8.3 Vì sao không gọi đây là monitor deadlock?

Worker cha không chờ *synchronized* monitor theo chu trình A/B. Nó chờ Future trong khi child không được schedule. Vì vậy không kỳ vọng *findDeadlockedThreads()* nhất thiết phát hiện. Cách sửa thường nằm ở **dependency/task architecture**, không phải điều chỉnh Java monitor lock order.

### 8.4 Vì sao queue capacity một giúp thấy lỗi rõ?

Bounded queue khiến backlog giới hạn. Khi cả worker và queue đã đầy, *AbortPolicy* trả **RejectedExecutionException** rõ ràng thay vì nhận mãi tasks rồi tăng memory/timeouts. Nhưng rejection là **một tín hiệu overload phải xử lý**, không phải thành công của service. Ở hệ thống thực cần HTTP/gRPC/message-level failure response, retries có ngân sách và quan sát rejection rate.

## 9. Ba kiểu queue và bốn rejection policies

### 9.1 Queue strategy có hệ quả trực tiếp

| Queue | Cơ chế | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| **LinkedBlockingQueue** không truyền capacity | Nhận queue items với giới hạn rất lớn theo implementation | Hấp thụ burst ngắn, cấu hình đơn giản | Queue growth và memory pressure; maximumPoolSize không giúp mở rộng như nhiều người nghĩ |
| **ArrayBlockingQueue** bounded | Hàng đợi hữu hạn | Backpressure/rejection rõ, giới hạn số tasks pending | Cần chọn capacity và xử lý khi đầy; latency vẫn cao nếu queue quá lớn |
| **SynchronousQueue** | Direct handoff, không giữ backlog | Buộc quyết định “giao ngay/tạo worker/reject” | Max threads quá cao dễ resource exhaustion; max hữu hạn dễ reject khi burst |
| **PriorityBlockingQueue** | Priority ordering, về bản chất thường không bounded nếu dùng làm TPE workQueue | Ưu tiên công việc theo comparator | Starvation của priority thấp, queue growth, task wrappers phức tạp |
| **Delayed work queue** của ScheduledThreadPoolExecutor | Giữ tasks theo thời gian kích hoạt | Scheduling có thời gian | Không phải queue để tự giới hạn mọi scheduled tasks; blocking scheduled tasks vẫn có thể giữ workers |

**Không có một queue đúng cho mọi workload.** Phải xét CPU-bound vs blocking I/O, task duration distribution, workload priority, deadline, memory budget và chính sách overload. Bất kỳ thiết kế nào không bound toàn bộ số công việc in flight từ bên ngoài cuối cùng đều có thể chuyển áp lực sang một queue/tầng khác.

### 9.2 Các chính sách từ chối

| Chính sách | Khi pool không nhận task | Điều cần cân nhắc |
| --- | --- | --- |
| **AbortPolicy** (mặc định) | Ném *RejectedExecutionException* | Fail fast rõ ràng; caller phải chuyển thành phản hồi/metric đúng |
| **CallerRunsPolicy** | Caller tự chạy task nếu executor chưa shutdown | Có thể giảm producer rate nhưng **block caller**, rất nguy hiểm trên event loop/request thread hoặc khi caller đang giữ lock |
| **DiscardPolicy** | Lặng lẽ bỏ task | Rất nguy hiểm với task có Future hoặc business outcome; có thể làm người chờ mãi |
| **DiscardOldestPolicy** | Bỏ task ở đầu queue rồi thử nộp task mới | Có thể làm tasks cũ biến mất; cần xử lý cancellation/notification; hiếm khi phù hợp |

**CallerRunsPolicy** không phải thuốc chữa chung. Nếu caller là một worker của pool khác, công việc bị đẩy sang chính worker ấy, có thể làm cả chain chậm. Nếu caller là event-loop thread, synchronous task chạy tại đó có thể chặn xử lý I/O. Nếu caller giữ lock, task chạy inline có thể gây nested lock contention. Chỉ chọn sau khi hiểu **caller context** và tác động backpressure mong muốn.

**DiscardPolicy** hoặc *DiscardOldestPolicy* có thể phá hợp đồng Future/task completion. Nếu code chờ một child bị drop mà không biết, việc chờ có thể trở thành vô hạn nếu thiếu timeout/cancel. Vì thế đừng dùng drop âm thầm cho request quan trọng.

### 9.3 Khi nào rejection là dấu hiệu tốt?

Rejection rõ là **bằng chứng hệ thống đã vượt capacity được cấu hình**, giúp điều khiển tải thay vì tích lũy vô hạn. Nhưng “tốt” chỉ khi toàn bộ đường xử lý có semantics rõ:

- Thống kê rejection count theo **pool và loại task**.
- Trả phản hồi quá tải theo giao thức (thường 429/503 hoặc loại lỗi phù hợp; không mã hóa mọi lỗi thành 200).
- Thực hiện retry có **backoff/jitter và tổng deadline**, không retry tức thời vô hạn.
- Đảm bảo idempotency hoặc deduplication cho các thao tác có side effects.
- Không nuốt *RejectedExecutionException* rồi để Future/request bị treo.
- Có tín hiệu cho caller biết task **chưa được accept**, tránh hiểu nhầm nó sẽ chạy sau.

## 10. Thread dump sẽ trông như thế nào?

Một incident của nested task dependency có thể cho các đoạn **minh họa**:

~~~text
"checkout-worker-1" #31
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.FutureTask.awaitDone(...)
    at java.util.concurrent.FutureTask.get(...)
    at com.example.Checkout.enrichOrder(Checkout.java:117)

"checkout-worker-2" #32
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.CompletableFuture$Signaller.block(...)
    at java.util.concurrent.CompletableFuture.join(...)
    at com.example.Checkout.fetchRecommendations(Checkout.java:88)
~~~

Các frame và formatting khác nhau theo JDK/VM; các dòng trên không phải log thật. Một worker ở *WAITING* có thể chờ công việc hợp lệ. **Dấu nguy hiểm** xuất hiện khi:

1. Workers đã dùng gần hết pool concurrency.
2. Nhiều workers chờ Future/Join trên code path gắn với child tasks.
3. Child tasks được submit vào **chính executor đã đầy workers**, nằm trong queue.
4. Completed/s hoặc business progress dừng, queue age/depth tăng.
5. Hình thái lặp qua nhiều snapshots trong cùng JVM instance.

Khi đó giả thuyết nested starvation có bằng chứng đáng kể. Nếu worker WAITING ở *BlockingQueue.take()* của pool và queue depth bằng 0, đó thường là **idle worker chờ việc**, một tình huống khác hoàn toàn.

### 10.1 Phân biệt WAITING, TIMED_WAITING, BLOCKED và RUNNABLE

| State trong dump | Gợi ý | Không được suy ra |
| --- | --- | --- |
| WAITING | *Future.get()*, *join()*, *park()*, *queue.take()* | Tất cả WAITING đều bị treo |
| TIMED_WAITING | Timed wait, sleep, backoff, Future.get(timeout) | Timeout đã xảy ra |
| BLOCKED | Đợi **object monitor** để vào synchronized | Mọi ReentrantLock/queue wait đều BLOCKED |
| RUNNABLE | Java runnable hoặc một số đường native/I/O | Thread đang dùng 100% CPU |

Java Thread.State không cung cấp duration của state. Chụp hai dumps cách nhau 5 giây mà cùng top frame **không chứng minh** thread chờ liên tục chính xác 5 giây; có thể rời frame và quay lại. Cần JFR monitor/park events, task logs, queue wait timing và completion counters.

### 10.2 Không có deadlock report chưa loại trừ starvation

ThreadMXBean deadlock detector có phạm vi Java locks nhất định. Nếu nhiều parent tasks đợi Futures không thể chạy, có thể **không có monitor cycle** để detector tìm. Hãy phân tích **dependency graph ở cấp task** và executor ownership, không dùng “no deadlocks found” làm kết luận duy nhất.

## 11. Các chỉ số cần quan sát trên ThreadPoolExecutor

*ThreadPoolExecutor* cung cấp các thống kê cơ bản; nhiều method ghi rõ kết quả **xấp xỉ**, vì worker/queue thay đổi song song với lúc đọc. Không dùng chúng như một ảnh nguyên tử toàn pool.

| Chỉ số Java | Ý nghĩa | Bẫy |
| --- | --- | --- |
| *getCorePoolSize()* | Ngưỡng core cấu hình | Không phải số worker luôn chạy tại mọi thời điểm |
| *getMaximumPoolSize()* | Worker limit cấu hình | Không chứng minh pool đã mở đến max |
| *getPoolSize()* | Số worker hiện có | Không phải số đang tiêu CPU |
| *getActiveCount()* | Số workers **đang xử lý task**, ước lượng | Active task có thể chờ I/O/Future |
| *getQueue().size()* | Số tasks chờ trong queue tại lúc đọc | Snapshot thay đổi; không phải pending HTTP requests |
| *getTaskCount()* | Tổng tasks được schedule, **ước lượng** | Có thể bao gồm tasks đang chờ/chạy, cần biết semantics và restart |
| *getCompletedTaskCount()* | Tổng tasks đã kết thúc thực thi, **ước lượng** | Không đồng nghĩa business success; task thất bại cũng có thể là completed execution |
| *getLargestPoolSize()* | High-water mark số workers từng tồn tại đồng thời | Không phải mức hiện tại |
| *getRejectedExecutionHandler()* | Policy xử lý overload | Không trực tiếp trả rejection count |
| *isShutdown()/isTerminating()/isTerminated()* | Lifecycle của executor | Queue có thể chưa cạn khi shutdown bắt đầu |

**Quan trọng:** API không có method chuẩn *getQueueWaitP99()* hoặc *getRejectedCount()*; muốn các metric đó, cần tự instrument hoặc dùng monitoring của framework/infrastructure có hợp đồng đúng.

### 11.1 Công thức nhìn xu hướng

Một bảng thời gian với cửa sổ 10 giây có thể gồm:

~~~text
time       active/max   queueDepth   completedTotal   rejectedTotal
12:00:00       8/8          20             1000              0
12:00:10       8/8         220             1001              0
12:00:20       8/8         420             1001              0
~~~

Các số **giả định** này gợi ý pool gần như không hoàn thành tasks dù backlog tăng rất nhanh. Nhưng chúng **chưa đủ** chỉ ra nguyên nhân nested dependency; có thể tất cả workers chờ một DB đang chậm, lock X hoặc network call.

Để phân biệt, phải nhìn thread dumps/trace của workers và metrics của downstream/queue:

- *Completed delta ≈ 0* gợi ý thiếu tiến triển ở cấp executor.
- *Queue depth tăng* gợi ý arrival vẫn tiếp tục.
- *Active=max* nghĩa workers đã nhận công việc, không đồng nghĩa CPU chạm 100%.
- *Rejection=0* có thể chỉ vì queue unbounded và task vẫn được accept; đó không phải bằng chứng capacity còn tốt.

### 11.2 Queue wait age quan trọng hơn chỉ queue length

Một queue dài 100 có thể xử lý rất nhanh nếu throughput lớn; một queue chỉ dài 5 vẫn gây latency nghiêm trọng nếu mỗi task đợi hàng phút. Muốn biết thực sự đợi lâu, đo **tuổi task trong queue**:

~~~text
task accepted at t0
worker begins task at t1
queueWait = t1 - t0
~~~

Chú ý *System.nanoTime()* dùng cho elapsed time **trong cùng JVM**, tránh lệch wall clock; timestamps trong log/traces dùng time basis nhất quán và UTC. Nếu xếp hàng qua message broker, cần tách broker wait, network transfer và executor wait.

Một instrumentation tối thiểu phải quyết định rõ:
- Tính queue wait từ **submit called** hay từ **accepted into queue**?
- Tasks bị rejected được đo như thế nào?
- Nếu *CallerRunsPolicy* chạy inline, execution location khác pool worker.
- Cancellation trước khi bắt đầu có được đếm không?
- Histogram phân biệt loại task, priority, pool và instance không?

Không nên tạo metric label theo từng requestId: cardinality cao dễ quá tải hệ metrics.

### 11.3 Mảnh mã monitoring (không phải chương trình độc lập)

~~~java
// Chạy bên trong service có biến ThreadPoolExecutor pool sẵn.
int workers = pool.getPoolSize();
int active = pool.getActiveCount();       // approximate
int waiting = pool.getQueue().size();     // snapshot
long scheduled = pool.getTaskCount();     // approximate
long finished = pool.getCompletedTaskCount(); // approximate

// Export gauges/counters với pool ID và JVM instance.
// Không coi finished == businessSuccess.
~~~

Nếu chỉ giữ reference *ExecutorService* do framework trả về, không phải lúc nào cast sang ThreadPoolExecutor cũng hợp lệ; một số wrapper cố ý ẩn implementation. Dùng monitoring API tương ứng của framework hoặc instrument ở admission/worker hooks theo hợp đồng.

## 12. Tìm bằng chứng nested dependency từ code và runtime

Thread dump cho thấy *FutureTask.get()* nhưng không ghi “child task của parent đang ở queue”. Cần ghép nhiều nguồn.

### 12.1 Từ call stack đến nơi submit child

1. Tìm frame ứng dụng ngay dưới *Future.get()*, *CompletableFuture.join()*, *CountDownLatch.await()*.
2. Đọc code của frame đó: parent tạo *Future* ở đâu? Child chạy trên executor nào?
3. Đối chiếu pool names/config (HTTP, IO, CPU, async, commonPool).
4. Child có thể hoàn tất từ callback ngoài pool hay buộc dùng same executor?
5. Nếu same pool, xác định số parents đang giữ workers và số child tasks pending.
6. Xem timeout/cancellation: parent có nhả worker không? Child có còn tồn tại sau timeout không?
7. Kiểm tra per-task trace/counter nếu có để xác lập dependency graph.

**Không đủ bằng chứng khi chỉ có tên pool:** *CompletableFuture.supplyAsync()* không truyền executor có default executor riêng (thường ForkJoinPool.commonPool theo JDK), trong khi *supplyAsync(..., pool)* dùng executor được chỉ định. Điều tra cụ thể từng lời gọi và version, không mặc định mọi CompletableFuture chạy trong pool ứng dụng.

### 12.2 Dependency graph theo task

~~~text
Parent A (worker A)
   |
   +-- waits Child B (queued in same executor)
                       |
                       +-- waits Child C (also queued)
                                          |
                                          +-- depends on resource R
~~~

Có thể có phụ thuộc tuyến tính **không tạo vòng logic giữa task IDs**, nhưng vẫn bị starvation vì **tài nguyên thực thi hữu hạn**. Vòng xuất hiện ở đồ thị **“task giữ worker → cần child → child cần worker”**.

Vì vậy điều tra phải hỏi **ai giữ workers trong thời gian đợi**, không chỉ có cycle ở object locks hay không.

### 12.3 Executor topology theo request

Một request có thể đi qua:

~~~text
HTTP worker pool
      |
      v
business executor
      |
      +-- blocking database I/O
      |
      +-- submits async enrichment to same executor
            |
            +-- dependent callback in another executor
~~~

Bản đồ cần chỉ rõ:
- Pool nào thực thi parent và child.
- Có bao nhiêu worker/queue slots tại mỗi pool.
- Các waits là synchronous/blocking hay asynchronous.
- Callback hoàn tất chạy trên thread nào.
- Deadlines và cancellation propagation đến đâu.
- Admission load, retries và fan-out hệ số bao nhiêu.

Nếu cả HTTP pool và business executor bị giữ bởi các chuỗi chờ đồng thời, chỉ tăng pool business có thể khiến downstream DB quá tải hơn. Cần xem **tổng concurrency budget**.

## 13. Timeout, cancellation và completion semantics

### 13.1 Timeout chờ Future không giải phóng mọi tài nguyên

~~~java
// Mảnh mã minh họa, giả định future và deadline đã có.
try {
    return future.get(500, java.util.concurrent.TimeUnit.MILLISECONDS);
} catch (java.util.concurrent.TimeoutException ex) {
    future.cancel(true); // yêu cầu hủy khi nghiệp vụ cho phép
    throw ex;
}
~~~

Đây **không** phải công thức dùng y nguyên cho mọi task:

- *get(timeout)* chỉ giới hạn thời gian caller đợi.
- *cancel(true)* cố gắng interrupt task khi được phép, không bảo đảm dừng ngay.
- Một tác vụ thực hiện side effect đã bắt đầu có thể vẫn hoàn tất ở downstream.
- Cần idempotency/deduplication và compensation nếu nghiệp vụ đòi hỏi.
- Nếu task chưa bắt đầu, cancellation có thể ngăn nó chạy, nhưng task wrapper/queue cleanup tùy executor.
- Nếu nhiều tầng retry sau timeout, các tasks cũ có thể tiếp tục và cộng dồn tải.

Cũng phải phân biệt: *Future.isDone()* bao gồm **success, exceptional completion và cancellation**, không đồng nghĩa business success.

### 13.2 End-to-end deadline khác per-call timeout

Nếu request chỉ có 1 giây trước deadline, không nên mỗi dependency tự chờ 1 giây, rồi retry thêm 1 giây ở các tầng khác. Thiết kế cần **deadline budget truyền xuyên chuỗi**:

~~~text
Request budget 1000 ms
  -> validation 50 ms
  -> queue wait <= 100 ms (policy)
  -> downstream <= remaining budget
  -> response writing within remaining budget
~~~

Các số là minh họa. Khi task chưa bắt đầu mà deadline đã hết, thường nên **từ chối/cancel trước** thay vì chạy công việc hết giá trị sau đó. Điều này cần được thực hiện theo hợp đồng của framework và nghiệp vụ.

### 13.3 Không sử dụng shutdownNow như “reset pool” tùy tiện

*shutdownNow()* cố dừng active tasks bằng interruption và trả về những tasks chưa bắt đầu; nó **không** hard-kill an toàn mọi công việc. Trong production nó có thể bỏ dở transactions, làm mất queued work và gây trạng thái không nhất quán. Chỉ dùng theo quy trình shutdown/recovery đã được thiết kế, có compensating actions và ownership rõ.

## 14. Những cách giảm nguy cơ nested starvation

### 14.1 Ưu tiên **composition không blocking** thay vì submit rồi chờ trên worker

Với CompletableFuture, có thể dùng *thenCompose* để diễn tả phụ thuộc mà không chiếm một worker chỉ để chờ một child Future:

~~~java
// Mảnh mã minh họa; service có ioExecutor được quản lý.
// fetchData() và enrich() là các phương thức nghiệp vụ có sẵn.
java.util.concurrent.CompletableFuture<Result> result =
    java.util.concurrent.CompletableFuture
        .supplyAsync(() -> fetchData(), ioExecutor)
        .thenCompose(data -> java.util.concurrent.CompletableFuture
            .supplyAsync(() -> enrich(data), ioExecutor));

// Bên trong một worker của chính ioExecutor, tránh result.join().
// Trả về CompletionStage cho caller hỗ trợ async.
~~~

*thenCompose* tạo một **dependent stage**; nó không tự blocking chờ child như gọi *join()* trong một worker. Nhưng child vẫn cần executor capacity để chạy, và flow phải xử lý **exception, cancellation, timeouts và result backpressure**. Nếu downstream API chỉ cung cấp blocking I/O, các leaf operations vẫn chiếm thread trong thời gian gọi.

**Lưu ý:** code trên chỉ là mảnh code, không chạy độc lập vì *Result/fetchData/enrich/ioExecutor* thuộc ứng dụng giả định. Không mặc định “có CompletableFuture” là nonblocking nếu ở cuối vẫn gọi *join()* trong worker của cùng executor.

### 14.2 Tách pools theo loại công việc, không theo cảm tính

Tách CPU-intensive, blocking I/O, scheduler/coordination và dependency callbacks **có thể** giảm tình trạng một nhóm tasks chiếm hết workers của nhóm khác. Tuy nhiên tách pool chỉ hữu ích khi:

- Mỗi pool có **concurrency/queue budget** và admission policy.
- Phụ thuộc không tạo vòng ngược qua các pools.
- Chi phí threads/heap/native memory/OS scheduling được tính tổng.
- Downstream thực sự chịu được mức concurrency được mở.
- Có metrics và test kiểm chứng **không chuyển starvation sang pool khác**.

Một phương án đơn giản là parent coordinator không chiếm một worker để chờ; nó trả future/continuation. Child sử dụng một pool có capacity được quản lý, và kết quả được compose khi hoàn tất.

### 14.3 Chạy leaf work đồng bộ khi phù hợp, tránh “async giả”

Nếu parent và child đều là công việc ngắn, thuần CPU và không cần concurrency thực, đôi khi **gọi child trực tiếp** trong parent đơn giản và an toàn hơn submit cùng pool rồi wait. Nhưng phải cân nhắc tail latency và modularity, không biến việc gọi blocking dài thành inline work trên event loop.

### 14.4 Hạn chế fan-out và outstanding tasks

Với mỗi request tạo 100 subtasks, chỉ tăng workers có thể làm downstream quá tải. Cần giới hạn:
- Số subtasks đồng thời theo request/tenant.
- Tổng in-flight tasks trên instance.
- Outstanding downstream requests/DB connections.
- Queue capacity.
- Retry attempts và thời gian còn lại.
- Batch size/chunking và deadline.

Giới hạn phải được áp ở **admission**, không chỉ “sau khi task đã được xếp hàng”. Nếu một request đã gửi 100 tasks rồi bạn mới kiểm tra queue length, hệ thống có thể đã vượt ngân sách.

## 15. Vì sao “tăng thread” hoặc “tăng queue” thường phản tác dụng?

### 15.1 Tăng maximumPoolSize trong unbounded queue có thể không làm gì

Như cơ chế ở mục 3, khi queue vẫn nhận task, ThreadPoolExecutor ưu tiên queue hơn tăng workers. Nếu queue không bounded, việc chỉnh maximumPoolSize từ 20 lên 200 có thể không làm xuất hiện worker thứ 21.

**Khắc phục cần xác minh cấu hình thực tế**, không suy từ biến tên *max* trong config. Kiểm tra *corePoolSize, maxPoolSize, workQueue* và runtime poolSize.

### 15.2 Tăng corePoolSize có thể đưa nghẽn sang downstream

Nếu workers bị giữ bởi DB pool 10 connections, tăng Java pool từ 20 lên 200 có thể tạo thêm 180 threads **chờ cùng 10 connections**, tốn native memory và OS context switching, chưa tăng throughput DB.

Không nâng concurrency theo phản xạ khi CPU thấp. Hãy xác định **bottleneck resource** và service-time breakdown trước.

### 15.3 Tăng queue size có thể che lỗi, tăng p99 và memory

Queue 1000 có thể “mượt” hơn queue 100 với một burst ngắn, nhưng khi hệ liên tục quá tải, queue 10000 chỉ tích lũy lâu hơn trước khi reject; nhiều requests trong queue có thể đã hết deadline trước khi chạy.

Một queue rất lớn còn giữ references tới payload/context, gây heap pressure, GC activity và thậm chí OOM. Queue size lớn không phải là throughput capacity.

### 15.4 Scale out cũng cần giới hạn

Thêm instances có thể tăng tổng throughput **nếu công việc có thể phân phối và downstream chịu tải**. Nhưng nếu mọi instance cùng tạo nested dependency starvation, bạn đang nhân bản bug. Nếu downstream là shared DB với giới hạn connections, scale out không đúng giới hạn có thể làm nghẽn chung tệ hơn.

## 16. Hướng điều tra incident: từ metric tới nguyên nhân

### Bước 1 — Khóa đúng pool và JVM instance

Ghi service/version, pod/host, JVM start time/PID, pool name, cấu hình core/max/queue/policy, loại tasks và khoảng thời gian incident. Không gộp queue metric của pod A với thread dump của pod B rồi suy nguyên nhân.

Nếu service có **nhiều executors**, phải biết cái nào làm gì. Thread pool HTTP worker, DB driver callbacks, Kafka consumer, scheduler, ForkJoinPool.commonPool và custom business pool có lifecycle khác nhau.

### Bước 2 — Xác minh có bão hòa thực sự không

Quan sát chuỗi nhiều mẫu:
- *activeCount/poolSize* có gần giới hạn?
- Queue size/age có tăng?
- Completed delta/s có giảm?
- Rejected delta/s có tăng?
- Task execution time hay queue wait time tăng?
- CPU/GC/heap/DB connection pool cho tín hiệu gì?

Chỉ một snapshot *activeCount=max* không chứng minh overload: pool có thể bận hợp lệ nhưng vẫn hoàn tất tasks nhanh, queue rỗng và latency đạt SLA.

### Bước 3 — Lấy thread dump có kiểm soát

Với HotSpot, khi có quyền và đúng namespace:

~~~bash
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l > pool-thread-01.txt
~~~

PID *12345* chỉ là ví dụ; phải thay bằng JVM đã xác minh. *-l* dùng lấy ownable synchronizer info trên các builds hỗ trợ; kiểm tra *help Thread.print* của JVM đích.

Nếu incident đang kéo dài và overhead cho phép, có thể lấy một vài dumps **cách nhau một khoảng có đánh dấu UTC**. Không lặp dày hoặc mặc định một dump là toàn bộ lịch sử. Công cụ có thể tạo output lớn và ảnh hưởng JVM; cần lưu trữ được bảo vệ.

### Bước 4 — Đọc workers ở đâu

Phân loại:
- CPU-bound code thực sự?
- Native I/O/network read?
- *FutureTask.get/CompletableFuture.join*?
- *BlockingQueue.take* (idle)?
- *ReentrantLock/Condition/monitor*?
- *CountDownLatch.await/Semaphore.acquire*?
- *Thread.sleep* (backoff/retry)?
- JVM GC/safepoint/JIT helper threads?

Không gọi tất cả WAITING là deadlock. Chỉ workers có **đúng task dependency và queue pending** mới ủng hộ starvation do pool.

### Bước 5 — Lần theo child work và completion ownership

Từ frame nghiệp vụ của worker, tìm:
- Lệnh submit child ở đâu?
- Executor của child có cùng với parent không?
- Khi nào child được chạy và ai hoàn tất future?
- Có một queue/future do chính parent chờ không?
- Có timeout/cancellation và task cleanup không?
- Có queue item bị rejected/drop nhưng Future không hoàn tất không?

Nếu không xác định được child nằm trong queue nào, kết luận chỉ nên ở mức **giả thuyết task dependency starvation**, chưa nên ghi root cause.

### Bước 6 — Đối chiếu nguồn lực khác

- Nếu workers blocked ở JDBC connection acquisition, xem DB pool active/pending, slow queries, connection leak, DB server.
- Nếu blocked ở synchronized, xem lock owner và JFR monitor events.
- Nếu RUNNABLE và CPU cao, xem per-thread CPU deltas/profiler.
- Nếu GC pauses dài, xem GC Unified Logging/JFR.
- Nếu queue dài do sudden burst, đối chiếu arrival rate và configured capacity.
- Nếu retries trùng spike, xem retry count, deadlines và downstream errors.

### Bước 7 — Giảm tải trước khi tăng capacity

Tùy quyền vận hành:
- Cắt/reduce incoming load có kiểm soát, rate limit/admission.
- Dừng retry storm, khống chế fan-out.
- Trả overload nhanh thay vì tích lũy task quá hạn.
- Giới hạn concurrency theo dependency.
- Kiểm tra tách pool/async composition tại điểm nested wait.
- Không tự dùng *shutdownNow()* hoặc kill JVM nếu chưa đánh giá side effects.

### Bước 8 — Kiểm chứng trước–sau

Sau thay đổi, theo dõi:
- Queue wait p95/p99 và queue depth/oldest task age.
- Completed rate, **business success rate** và rejection/timeout rates.
- CPU, heap/GC, threads, downstream latency và connection pools.
- Lock/parking patterns trong dumps/JFR khi cần.
- Dải tải và thời điểm thay đổi để tránh kết luận nhầm do traffic tự giảm.

Một fix tốt cải thiện tiến triển **không chỉ trên một pool**, đồng thời không làm rớt việc hoặc làm quá tải dependency khác.

## 17. Bảng phân biệt nguyên nhân theo bằng chứng

| Triệu chứng | Khả năng | Bằng chứng cần thêm |
| --- | --- | --- |
| active=max, queue tăng, CPU thấp; workers at Future.get | Nested task wait hoặc downstream Future chậm | Child executor ownership, child queue, completion source |
| active=max, queue tăng, CPU cao; stacks ở parsing/computation | CPU bottleneck | Per-thread CPU delta/JFR profiler, CPU limits |
| active=max, queue tăng; JDBC getConnection waits | DB connection-pool bottleneck | DB pool active/waiters, query latency, leaked connections |
| active=max, queue tăng; workers BLOCKED cùng monitor | Lock contention | Monitor owner + JFR durations + critical section |
| active=max, queue tăng; network read | Slow dependency | Trace spans, socket timeout, remote errors |
| queue gần full và rejected tăng | Bounded capacity reached | Arrival/service rate, retry policy và error handling |
| queue tăng nhưng active thấp hơn core | Worker creation/rejection/config issue, executor shutdown, submit mismatch | ThreadFactory, lifecycle, exact executor instance |
| queue=0 và active thấp, nhưng service chậm | Bottleneck ở trước/sau pool | HTTP acceptor, broker lag, DB, GC, downstream |
| completed task count tăng nhưng success rate giảm | Tasks kết thúc nhưng lỗi/reject/timeout | Business outcomes, exceptions, retry semantics |
| thread dump không có cycle nhưng request treo | Không loại trừ task dependency starvation | Executor/task graph, queue pending, futures |
| sau deploy max tăng nhưng workers không tăng | Unbounded queue hoặc pool chưa cần mở rộng | Core/max/queue config & runtime threads |
| HTTP timeout nhưng queue vẫn đầy tasks cũ | Deadline/cancel không được propagate | Task ages, cancel behavior, client retries |

## 18. Tình huống phân tích chuyên sâu

### 18.1 Checkout bị kẹt vì nested enrichment task

**Bối cảnh giả định:** *checkoutPool* có core=max=8, queue unbounded. Mỗi checkout task gửi một enrichment subtask vào cùng pool, rồi gọi *Future.get()*.

**Quan sát:**
- Tám parent tasks chiếm hết tám workers.
- Child tasks xếp hàng; queue size tăng.
- Workers có frames tại *FutureTask.get*.
- CompletedTaskCount gần như không tăng.
- CPU thấp vì workers đang chờ.

**Giả thuyết mạnh:** parent–child dependency starvation. Xác nhận bằng code submission và executor identity, không chỉ đọc stack.

**Sửa thiết kế:** không blocking wait trong cùng executor; compose asynchronous hoặc chạy child inline khi phù hợp; nếu tách pool cần concurrency budget tổng và deadline propagation. Chỉ nâng max từ 8 lên 16 có thể tạm giảm nhưng không bảo đảm hết lỗi.

### 18.2 Queue unbounded che overload trước khi OOM

**Bối cảnh giả định:** 4 CPU workers, mỗi task mất trung bình 200 ms khi tải ổn định (tối đa lý thuyết khoảng 20 tasks/s với phân phối lý tưởng); arrival tăng lên 100 tasks/s, producer vẫn submit vào queue không bounded.

**Quan sát:** queue depth tăng nhanh, heap used/GC activity tăng, latency p99 tăng trước khi CPU/JVM mất ổn định.

**Chẩn đoán:** offered load vượt capacity lâu dài; không cần nested dependencies để giải thích.

**Giảm tải:** bounded admission, backpressure/rejection, giảm fan-out, scale đúng công suất nếu downstream cho phép, xem batch/algorithm và task service time. Tăng queue size chỉ kéo dài thời gian trước khi quá tải rõ.

### 18.3 Thread pool nhiều workers nhưng DB chỉ có vài connections

**Bối cảnh:** 80 Java workers chạy request nhưng DB pool chỉ có 10 connections, queries chậm.

**Quan sát:** threads WAITING ở connection acquisition, executor active cao, CPU Java thấp, queue tăng. DB connection pool pending tăng.

**Nguyên nhân có thể:** downstream/DB capacity, connection leak hoặc slow queries; **không** mặc định Java thread pool quá ít.

**Giải pháp cần xác minh:** giảm concurrency các truy vấn, tối ưu queries/pool policy, đặt timeout/connection leak detection, tách admission; không tăng Java workers lên 500 khi DB chỉ xử lý được 10 query đồng thời.

### 18.4 Retry amplification sau khi timeout

**Bối cảnh:** request timeout ở 1 s, nhưng child task tiếp tục chạy 3 s. Client retry hai lần, tạo ba groups of tasks trên pool.

**Quan sát:** queue age tăng, app error rate tăng, rejected count bắt đầu tăng, downstream QPS vượt client QPS.

**Vấn đề:** timeout caller không tự cancel work; retry không có budget khiến nhiều tasks không còn giá trị vẫn dùng capacity.

**Giải pháp:** end-to-end deadlines, cancellation khi an toàn, idempotency, retry/backoff/jitter, limit concurrent downstream calls, tránh chạy task đã hết deadline.

### 18.5 Scheduled executor chậm vì task dài

**Bối cảnh:** một scheduled pool nhỏ thực thi các jobs định kỳ. Một job chờ I/O 2 phút; các jobs đến giờ tiếp theo bị trễ.

**Quan sát:** scheduled task delays tăng; worker còn bận; queue có nhiều future scheduled tasks.

**Chẩn đoán:** blocking task giữ scheduler capacity. Không mặc định là nested task deadlock.

**Thiết kế:** tách scheduling/dispatch khỏi blocking execution hoặc phân bổ workers đúng workload, đồng thời bảo đảm không tạo queue vô hạn khi downstream chậm.

### 18.6 CompletableFuture chạy không cùng executor như dự đoán

**Bối cảnh:** một lập trình viên nghĩ *supplyAsync()* sẽ chạy trên *businessPool*, nhưng không truyền Executor; lúc incident thấy tasks trên *ForkJoinPool.commonPool*.

**Giải thích:** theo Java 17 API, các async methods không truyền executor thường dùng default async execution facility của CompletableFuture, thông thường commonPool khi đủ parallelism. Vì vậy cần kiểm tra call site và actual executor, không đoán từ tên biến *businessPool*.

**Hành động:** explicit executor khi cần cách ly/giới hạn, và composition không blocking; xác minh fork/join semantics nếu có blocking dependencies.

### 18.7 Java virtual threads trên JDK 21+

Virtual threads có thể làm cho I/O-bound blocking code tiêu thụ ít OS threads hơn trong nhiều tình huống, nhưng chúng **không nâng capacity của DB/HTTP downstream** và không sửa phụ thuộc vòng giữa tasks/callbacks. Nếu một tác vụ giữ semaphore, DB connection hoặc external rate limit rồi chờ task khác cần cùng tài nguyên, starvation vẫn có thể xảy ra.

Khi dùng virtual threads:
- Xác định rõ executor và resource admission đang giới hạn ở đâu.
- Đừng dùng số OS carrier threads để suy ra số in-flight requests.
- Dùng virtual-thread-aware diagnostics/JFR tùy JDK.
- Không giữ lock/connection/semaphore trong khi đợi một dependent task cần chính tài nguyên đó.
- Dùng concurrency limits rõ thay vì dựa vào việc tạo nhiều virtual threads như “unbounded capacity”.

Đây là góc nhìn mở rộng; ví dụ Java 17 ở mục 8 dùng **platform threads**.

## 19. Kiểm thử khả năng chịu tải và failure injection

Một thay đổi pool/queue phải được kiểm thử trong điều kiện có thể gây lỗi, không chỉ chạy với một request.

### 19.1 Ma trận thử nghiệm tối thiểu

| Kịch bản | Kích thích | Điều cần đo |
| --- | --- | --- |
| Baseline | Load thấp, dependency bình thường | Throughput, p99, active, queue, completed |
| Burst | Tăng arrivals ngắn | Queue peak, recover time, rejection, p99 |
| Sustained overload | Arrivals > service capacity | Backpressure, ổn định memory, fail-fast |
| Downstream slowness | Chèn 200–2000 ms latency | Worker occupancy, queue age, timeouts |
| Nested task dependency | Parent waits child on same pool | Có starvation/rejection? Không treo vô hạn |
| Cancellation | Caller timeout, child queued/running | Child có dừng? side effects có được xử lý? |
| Retry storm | Dependency trả lỗi/timeout | Retry budget, amplification, downstream QPS |
| Worker failure | Task ném unchecked exception | Completed vs business success, capacity recovery |
| Shutdown | graceful shutdown khi có pending work | Task draining, rejection, data consistency |
| JVM restart/scale | Instance thay thế | Counter resets, pool identity, pending task semantics |

**Điều kiện dừng thử tải:** chặn khi error budget, heap/native memory, CPU, disk hoặc downstream giới hạn theo hợp đồng; đừng cố gây OOM để chứng minh bounded queue có ích.

### 19.2 Các assertion đúng

- Queue bounded không vượt capacity đã cấu hình (theo semantics của queue).
- Khi overload, policy có kết quả quan sát được: rejection count/response, không silent drop.
- Với nested-wait test, không để process treo vô hạn.
- Sau giải pháp, completed/business success tiến triển và queue drain trong điều kiện tải dự kiến.
- Timeout không gây tải “ma” vượt budget vì child tiếp tục chạy vô hạn.
- Không mất tasks khi shutdown/restart ngoài hợp đồng ứng dụng.
- Không suy ra CPU/GC/latency từ một lần đọc *getActiveCount()*.

### 19.3 Chú ý test tính ngẫu nhiên

Không kiểm chứng concurrency bằng *Thread.sleep(10)* rồi assert queue size ngay lập tức: scheduling có thể khiến test flaky. Ưu tiên **CountDownLatch, Phaser, barrier hoặc futures có timeout** để đồng bộ những bước cần xác định. Ví dụ ở mục 8 dùng latch để giữ worker khi main lấy queue size, rồi mới thả gate.

Không biến timeout dài trong test thành cách “chắc chắn” scheduler đã hoàn thành. Test nên có guard/time budget và cleanup trong finally.

## 20. Alerting và dashboard: cảnh báo cần đánh vào triệu chứng đúng

### 20.1 Các metric cần có

- **active workers / pool max** theo pool instance.
- **queue depth** và **oldest queued task age** nếu instrument được.
- **task accepted/s**, **task started/s**, **task completed/s** theo outcome.
- **rejection rate** theo policy và caller.
- **queue wait p50/p95/p99** và **execution duration p50/p95/p99**.
- **end-to-end request latency p95/p99** và error/timeout rates.
- **downstream concurrency/queue/latency**, DB pool active/waiters, rate-limit status.
- **CPU, process threads, heap/GC pause**, để phát hiện bottlenecks song hành.

### 20.2 Một vài tín hiệu kết hợp hữu ích

- **Queue tăng + completed/s gần 0 + active=max**: có nguy cơ thiếu tiến triển; cần nhìn worker stacks và downstream.
- **Queue tăng + completed/s cao nhưng arrivals còn cao hơn**: arrival > capacity; cần admission/scale/optimizations.
- **Queue rỗng + active thấp nhưng p99 cao**: điều tra trước/sau executor, không tự kết luận queue là thủ phạm.
- **Rejected tăng + error response thấp bất thường**: có thể exception bị nuốt hoặc policy silent drop.
- **Process CPU thấp + active=max + Future waits**: ưu tiên task dependency hoặc blocking.
- **Process CPU cao + active=max + computation frames**: ưu tiên CPU hotspot, kiểm tra profiler.

**Không cảnh báo chỉ dựa vào một giá trị tuyệt đối** như *queueDepth > 100* áp cho mọi service. Nên xét throughput, service time, deadlines, queue age, tỷ lệ saturation và error budget theo workload.

### 20.3 Tách task completion và business completion

*getCompletedTaskCount()* là số task **kết thúc thực thi trong executor** theo thống kê xấp xỉ, không xác nhận thành công nghiệp vụ. Một task có thể hoàn tất bằng cách ném exception, ghi lỗi hoặc trả timeout result.

Ví dụ dashboard:
- *executor.completedTasks/s* tăng nhưng
- *checkout.successRequests/s* giảm và
- *checkout.errors/s* tăng.

Đó không phải hệ khỏe. Hãy instrument **business outcomes** riêng và theo dõi child tasks vẫn chạy sau caller deadline.

## 21. Các lỗi tư duy lặp lại

| Suy luận sai | Thực tế | Cách xác minh |
| --- | --- | --- |
| “maxPoolSize=100 nên lúc cần sẽ có 100 workers” | Queue còn chỗ khiến TPE ưu tiên xếp hàng, không mở ngay tới max | Đọc core/max/queue và runtime poolSize |
| “CPU thấp nghĩa pool rảnh” | Workers có thể WAITING/BLOCKED và giữ slots | activeCount + thread dumps |
| “Queue dài chứng minh deadlock” | Arrival > service capacity cũng gây queue tăng | Arrival/completed rates và stacks |
| “Không có Java deadlock thì không starvation” | Future dependency có thể không tạo monitor cycle | Task/executor graph |
| “Tăng max threads sửa nested dependencies” | Có thể chỉ dời ngưỡng; dependency design vẫn sai | Load test ở concurrency lớn hơn |
| “Tăng queue size giải quyết p99” | Queue wait và memory có thể tăng | Queue age, deadline, heap/GC |
| “Future.get(timeout) tự cancel child” | Chỉ dừng chờ của caller | Child outcome/cancel state |
| “cancel(true) luôn dừng ngay side effects” | Interruption có tính hợp tác, downstream có thể vẫn chạy | Idempotency, transport cancellation |
| “completed tasks là successful requests” | Task có thể kết thúc bằng lỗi | Business outcome metrics |
| “CallerRunsPolicy luôn an toàn” | Có thể block event loop/caller đang giữ lock | Caller execution context và latency |
| “DiscardPolicy tránh overload không tác dụng phụ” | Có thể làm mất task/Future không bao giờ complete | Rejection handler semantics |
| “Queue length 0 = không có backlog anywhere” | Có thể có queue ở HTTP/DB/broker tầng khác | End-to-end queues |
| “active=8 nghĩa CPU đang dùng 8 cores” | Active worker có thể blocked | OS/JFR CPU |
| “Hai thread dumps cùng WAITING nghĩa treo liên tục” | Worker có thể wake/run/park giữa hai mẫu | Completion counters/JFR |
| “Một pool phục hồi nghĩa toàn hệ phục hồi” | Downstream/other pool có thể đang quá tải | End-to-end latency/error budget |
| “Virtual threads chữa bão hòa database” | DB concurrency vẫn hữu hạn | Resource budget và downstream metrics |

## 22. Câu hỏi tự kiểm tra và đáp án

### Bài 1 — Vì sao maximumPoolSize không phát huy?

TPE có *core=4, max=40*, dùng *LinkedBlockingQueue* không bounded. Bốn workers bận, queue đã có 1000 tasks.

**Đáp án:** Khi queue vẫn nhận task, executor ưu tiên xếp hàng chứ không tăng workers vượt core. *max=40* gần như không tác động trong chế độ queue này. Muốn giải quyết cần đánh giá workload, queue capacity, concurrency và admission policy; không chỉnh mù một tham số.

### Bài 2 — Pool starvation một worker

Parent đang chạy trên pool một worker, submit Child vào cùng pool, rồi gọi *child.get()* không timeout.

**Đáp án:** Parent giữ worker duy nhất, Child nằm trong queue nên không thể chạy. Parent chờ Child, tạo vòng phụ thuộc tài nguyên thực thi; có thể treo vô hạn dù không có Java monitor deadlock.

### Bài 3 — Chỉ cần tăng workers?

Cấu hình 4 workers và 4 parents đều chờ children ở cùng pool. Đề xuất tăng max lên 8.

**Đáp án:** Có thể tạm giúp một số children chạy nếu executor thực sự tạo thêm workers. Nhưng ở tải cao hơn có thể có 8 parents cùng chờ. Giải pháp bền vững là phá blocking dependency/đổi composition, giới hạn fan-out hoặc thiết kế pool cách ly đúng budget.

### Bài 4 — Rejection có chắc là bug?

Bounded queue capacity=100, max worker=10. Task tiếp theo bị *RejectedExecutionException* trong peak traffic.

**Đáp án:** Rejection là kết quả có thể được thiết kế khi vượt capacity. Bug nằm ở việc **không xử lý** overload: nuốt lỗi, retry vô hạn, trả 200 hoặc để request treo. Cần fail-fast/response đúng và telemetry.

### Bài 5 — Active workers và CPU

Metric báo activeCount=32/32, CPU khoảng 10%, queue tăng.

**Đáp án:** Workers có thể đang chờ I/O, lock, Future hoặc resource pool. Active không phải đang dùng CPU. Điều tra thread dumps, dependency spans và downstream metrics trước khi tăng CPU.

### Bài 6 — 500 tasks trong queue nghĩa chờ bao lâu?

Queue có 500 tasks, completed rate hiện 100 tasks/s.

**Đáp án:** Không thể nói chính xác từ một snapshot; trong hệ ổn định với cùng loại task và FIFO, có thể ước lượng queue wait ở mức vài giây, nhưng cần queue age/timing, arrival variability, prioritization và cancellation để tính đáng tin.

### Bài 7 — Sau caller timeout, child vẫn chạy

*Future.get(100 ms)* ném TimeoutException. Một giây sau, database vẫn nhận write từ task child.

**Đáp án:** Hợp lệ theo semantics: timeout chỉ giới hạn chờ, không tự hủy computation. Phải quyết định cancellation, idempotency, retry policy và deadline propagation; không giả định work đã biến mất.

### Bài 8 — DiscardPolicy với Future

Hệ thống dùng DiscardPolicy trong một pool saturated, code gọi *submit()* rồi *future.get()*.

**Đáp án:** Task có thể bị drop âm thầm mà Future không được hoàn thành, dẫn đến chờ vô hạn. Nên dùng policy thể hiện rejection rõ, hoặc custom handler báo outcome/cancel theo hợp đồng nghiệp vụ.

### Bài 9 — Cùng WAITING trong hai dumps

Worker-1 WAITING tại *queue.take()* ở t0 và t5; completed count toàn service tăng 200.

**Đáp án:** Service có tiến triển, nhưng **không thể khẳng định riêng worker-1** xử lý 200 tasks. Nếu không có per-worker/task evidence, chỉ kết luận được trong phạm vi counter.

### Bài 10 — CPU-bound và I/O-bound

Hai executor đều có 8 workers; một chạy CPU computation, một chạy blocking HTTP calls.

**Đáp án:** Chiến lược sizing khác nhau: CPU-bound chịu ảnh hưởng cores/scheduling; blocking I/O có thể cần concurrency khác nhưng phải giới hạn theo downstream capacity, memory và deadlines. Không lấy cùng công thức số threads cho cả hai.

### Bài 11 — Bước xác định nghi vấn nested starvation

Thread dump thấy mọi workers ở Future.get; queue đang tăng.

**Đáp án:** Chưa đủ kết luận. Phải tìm **child executor** của Futures, xác minh children đang chờ đúng pool đã bị parents giữ, và không có completion source độc lập. Đây là bằng chứng để phân biệt với Future do downstream service chậm.

### Bài 12 — CallerRunsPolicy

Caller là một Netty event-loop thread. Khi executor saturated, policy chạy một job blocking 2 giây trên caller.

**Đáp án:** Event loop có thể bị chặn 2 giây, làm trễ các kết nối khác. CallerRunsPolicy chỉ thích hợp khi caller có thể chịu execution inline và đáp ứng policy. Cần đánh giá thread type trước.

### Bài 13 — Restart pool để xử lý queue

SRE muốn gọi *shutdownNow()* trên production executor chứa payment tasks để “xóa backlog”.

**Đáp án:** Nguy hiểm: active tasks có thể bị interrupt, queued tasks chưa bắt đầu bị trả về/bỏ lại, transactions có thể mất hoặc side effects không rõ. Cần quy trình quiesce, drain/cancel có thể audit, idempotency và lựa chọn recovery đã phê duyệt.

### Bài 14 — Task count tăng mà request success không tăng

*completedTaskCount* tăng 500/s nhưng HTTP success/s gần 0.

**Đáp án:** Một task hoàn thành thực thi không nhất thiết có business success. Có thể tasks kết thúc với error, timeout, drop hoặc retry. Cần business outcome metrics và failure logs.

## 23. Checklist kiểm tra trước khi kết luận incident

### 23.1 Xác định phạm vi

- [ ] Service/version, JVM PID/start time, host/pod và đúng executor pool.
- [ ] corePoolSize/maxPoolSize/queue type/capacity/rejection policy xác minh từ runtime/config.
- [ ] Tách task arrival rate khỏi incoming request rate, có tính fan-out.
- [ ] Đối chiếu cùng thời điểm/instance trên metrics, dumps và traces.

### 23.2 Xác nhận bão hòa hay starvation

- [ ] Pool active/poolSize hiện tại; xem độ chính xác approximate.
- [ ] Queue depth **và queue wait age**, không chỉ một số snapshot.
- [ ] Submitted/accepted/started/completed/rejected theo thời gian.
- [ ] Business success/failed/timeouts và downstream latency.
- [ ] Worker stack: Future/Join vs I/O/lock vs CPU-bound.
- [ ] Child executor và completion ownership: có circular capacity dependency không?
- [ ] Per-pool/per-dependency concurrency limit và retry count.
- [ ] JVM CPU, heap, GC, native thread count và connection pools.

### 23.3 Chọn biện pháp an toàn

- [ ] Có thể giảm admission/fan-out/retry storm trước không?
- [ ] Queue bounded và overload response có đúng semantics/idempotency không?
- [ ] Có thể composition không blocking thay vì parent giữ worker để chờ child không?
- [ ] Tách pools có thực sự phá dependency và không vượt downstream budget không?
- [ ] Timeout/deadline/cancellation propagation và cleanup có hợp đồng rõ?
- [ ] Không dùng silent discard hoặc shutdownNow tùy tiện.
- [ ] Load test/failure injection đã chứng minh queue drain, task progress và p99 phục hồi?

### 23.4 Viết báo cáo dựa trên bằng chứng

Phân biệt:
- **Quan sát:** “8/8 workers active, queue depth 420, completed delta≈0 trong 20s.”
- **Giả thuyết:** “Nested child tasks đang bị starvation vì parent tasks giữ toàn bộ workers.”
- **Kiểm chứng:** “Tìm executor đích của child, queue content/trace, worker stacks, lệnh submit + get, JFR và metrics.”
- **Kết luận:** chỉ khi đã có code/runtime evidence chứng minh dependency path, không lấy “WAITING” làm root cause.
- **Giới hạn:** counters gần đúng, snapshots không liên tục, cancellation/rejection có thể thay đổi dữ liệu.

Mẫu kết luận có thể dùng trong incident:

> Trên JVM checkout-pod-4 lúc 10:12–10:13 UTC, executor enrichment có core=max=8 và queue không bounded. Metrics cùng instance cho thấy active≈8, queue depth tăng 40→680, completed-task delta gần 0. Ba thread dumps ghi nhiều worker ở FutureTask.get trong method enrichOrder. Code path xác nhận các Future chờ children được submit vào **chính enrichment executor**, trong khi các parent giữ toàn bộ workers. Đây là bằng chứng mạnh của task-dependency starvation; kế hoạch sửa là loại blocking wait trong cùng pool, áp admission/fan-out limits, kiểm thử timeout/cancellation và quan sát queue wait/response errors sau rollout.

Tất cả số và danh tính ở đoạn mẫu là **giả định**. Không dùng chúng như dữ liệu incident thật.

## 24. Tài liệu Java chính thức

- **Java SE 17 – ThreadPoolExecutor**, core/max/queue/rejection, *getQueue*, *getActiveCount*, *getCompletedTaskCount*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **Java SE 17 – Executors**, *newFixedThreadPool* và các executor factories: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html
- **Java SE 17 – Future**, *get(timeout)* và cancellation semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **Java SE 17 – CompletableFuture**, *join*, *thenCompose* và async executor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Java SE 17 – ArrayBlockingQueue**, queue capacity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **Java SE 17 – ThreadMXBean**, ThreadInfo/deadlock detection: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Oracle JDK 21 – jcmd**, Thread.print options và tác động chẩn đoán: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **OpenJDK JEP 444 – Virtual Threads** (góc nhìn JDK 21+): https://openjdk.org/jeps/444

Hãy dùng JavaDoc **đúng version/vendor** của JVM đang chạy; các executor wrappers, framework pools, queue metrics và công cụ thread dump có thể khác implementation.

## Ghi nhớ

**Pool saturation** là workers/queue đạt giới hạn, **queue buildup** là công việc đến nhanh hơn khả năng hoàn tất hoặc workers bị giữ lâu, còn **task dependency starvation** là công việc cần chạy lại phụ thuộc vào các workers đang bị chính parent tasks chiếm giữ. Ba điều này có thể cộng hưởng.

Để chẩn đoán đúng, đừng chỉ nhìn số threads hoặc queue. Hãy ghép **pool configuration → arrival/completion/queue-wait metrics → worker stacks → child executor/dependency graph → downstream CPU/I/O/lock evidence**. Cách giải quyết bền vững thường là **phá blocking dependency, giới hạn admission và fan-out, có deadline/cancellation rõ, backpressure và overload policy có quan sát**, không phải tăng maxPoolSize hoặc kéo dài queue vô điều kiện.