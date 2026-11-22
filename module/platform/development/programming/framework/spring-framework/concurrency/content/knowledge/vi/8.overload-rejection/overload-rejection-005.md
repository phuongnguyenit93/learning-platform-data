# DiscardPolicy, DiscardOldestPolicy và nguy cơ mất công việc

## 1. Vấn đề thực tế: task đã submit nhưng không được thực hiện

Một ứng dụng Spring có thể gửi nhiều công việc vào `ThreadPoolTaskExecutor`: xử lý email, tính báo cáo, làm mới cache, ghi nhận sự kiện hoặc xử lý việc nền từ `@Async`. Khi số task đến nhanh hơn tốc độ thực thi, thread pool cùng hàng đợi có thể **bão hòa**. Lúc đó bộ thực thi cần quyết định điều gì sẽ xảy ra với công việc vừa gửi.

Java `ThreadPoolExecutor` định nghĩa các chính sách từ chối qua `RejectedExecutionHandler`. Hai chính sách rất dễ gây mất dữ liệu nếu không hiểu rõ là:

- **`DiscardPolicy`**: bỏ công việc **mới bị từ chối** một cách âm thầm.
- **`DiscardOldestPolicy`**: khi executor còn hoạt động, loại phần tử ở **đầu hàng đợi đang chờ**, sau đó **thử gửi lại** công việc mới; nếu executor đã shutdown thì bỏ công việc mới.

Cả hai đều có thể khiến code phía gửi **không nhận được exception**, trong khi một task không bao giờ chạy. Đặc biệt, nếu task được gửi bằng `submit(...)`, một `Future` tương ứng có thể **mãi không hoàn thành và cũng không được hủy**. Vì vậy việc lời gọi `execute` hoặc `submit` trả về bình thường **không phải xác nhận nghiệp vụ đã được xử lý**.

> Với công việc phải hoàn tất hoặc phải có dấu vết thất bại (thanh toán, đơn hàng, cập nhật tồn kho, thông báo bắt buộc, tác vụ có người đang đợi Future), **không chọn chính sách bỏ việc âm thầm**. Hãy áp dụng phản ứng quá tải rõ ràng, giới hạn nguồn gửi, theo dõi lỗi và cơ chế lưu việc bền vững khi cần.

Bài học tập trung vào hai policy nêu trên, trong ngữ cảnh **Quá tải và từ chối** của Spring Framework, đồng thời giải thích cách kiểm chứng bằng Java 17 và vận dụng an toàn với `ThreadPoolTaskExecutor`.

## 2. Task bị từ chối khi nào?

### 2.1. Mối quan hệ giữa thread, queue và giới hạn

Một `ThreadPoolExecutor` dùng các tham số quan trọng:

- `corePoolSize`: số worker cốt lõi mà pool hướng tới khi phát sinh task.
- `maximumPoolSize`: ngưỡng tối đa worker.
- `workQueue`: hàng đợi giữ công việc **chưa bắt đầu**.
- `RejectedExecutionHandler`: chính sách xử lý khi executor không thể nhận thêm task.
- Trạng thái vòng đời: đang chạy, shutdown, đang kết thúc, đã kết thúc.

Đường đi khái quát của `execute(task)`:

~~~text
Có task mới
    |
    v
Số worker đang chạy < corePoolSize?
    | có -> cố tạo worker để thực thi task
    | không
    v
Thử đưa task vào workQueue
    | thành công -> task chờ worker
    | thất bại
    v
Còn có thể tạo worker đến maximumPoolSize?
    | có -> thử tạo worker thực thi task
    | không / không thể nhận
    v
RejectedExecutionHandler.rejectedExecution(task, executor)
~~~

Đây là sơ đồ logic giải thích, không thay cho toàn bộ xử lý trạng thái và race trong source code JDK. Chẳng hạn, pool có thể từ chối task vì **đã shutdown**, ngay cả khi hàng đợi chưa đầy. Cần phân biệt tình huống executor bão hòa với tình huống nó không còn chấp nhận công việc do vòng đời.

Với `corePoolSize = maximumPoolSize = 1` và `ArrayBlockingQueue` dung lượng 1:

~~~text
Worker duy nhất             Queue dung lượng 1          Task mới đến
┌──────────────────┐        ┌────────────────┐          ┌───────────┐
│ A đang thực thi  │        │ B đang chờ     │          │ C         │
└──────────────────┘        └────────────────┘          └───────────┘

A đang bận, không tạo thêm worker, queue đang đầy.
=> C bị từ chối và policy được gọi.
~~~

Chúng ta sẽ dùng chính cấu hình này trong ví dụ để tái hiện kết quả **xác định được**, không phụ thuộc may rủi của lập lịch thread.

### 2.2. Hàng đợi quyết định cách bão hòa

| Queue | Ý nghĩa đối với từ chối |
| --- | --- |
| `ArrayBlockingQueue<>(n)` | Bounded FIFO queue, giúp đặt giới hạn pending tasks rõ ràng; có thể đầy |
| `LinkedBlockingQueue<>(n)` | Bounded FIFO khi truyền capacity `n`; có thể đầy |
| `LinkedBlockingQueue<>()` không giới hạn thực tế nhỏ | Có thể giữ số task rất lớn, gây độ trễ/bộ nhớ tăng; `maximumPoolSize` thường ít có cơ hội phát huy |
| `SynchronousQueue` | Không lưu task đang chờ; cần giao ngay cho worker hoặc tạo worker; với pool đã đạt max, dễ từ chối khi tất cả bận |
| `PriorityBlockingQueue` | Thứ tự đầu hàng đợi theo ưu tiên, không nhất thiết theo thời điểm đến; thông thường không có bounded capacity cố định |

Nói `DiscardOldestPolicy` loại công việc "cũ nhất" là **cách gọi theo policy**; thao tác thực tế lấy **phần tử ở đầu queue** bằng `poll()`. Với FIFO queue, đó thường là task chờ lâu nhất. Với queue sắp xếp theo ưu tiên hoặc đặc tính khác, đầu queue **không nhất thiết** là công việc đến đầu tiên.

## 3. DiscardPolicy: bỏ công việc mới mà không báo lỗi

`ThreadPoolExecutor.DiscardPolicy` triển khai `RejectedExecutionHandler` bằng hành vi **không làm gì** khi bị gọi.

~~~java
RejectedExecutionHandler policy =
        new ThreadPoolExecutor.DiscardPolicy();
~~~

Đây là mảnh khai báo (cần import các kiểu từ `java.util.concurrent`). Khi một task bị từ chối:

1. Executor gọi handler.
2. Handler không chạy, không enqueue, không chuyển task đi nơi khác và không ném exception.
3. Lời gọi gửi task có thể trả về bình thường, mặc dù task vừa gửi **không được thực thi**.

Với sơ đồ A/B/C:

~~~text
Worker chạy A
Queue chứa B
submit C -> DiscardPolicy -> C bị bỏ
Sau khi A kết thúc: B được chạy, C không chạy.
~~~

**Các hệ quả nghiêm trọng:**

- **Không có tín hiệu thành công/thất bại rõ ràng tại điểm submit.** Không thể xem việc không bắt được exception là dấu hiệu đã nhận việc.
- **Mất side effect nghiệp vụ.** Nếu task đáng lẽ ghi database, gửi mail hoặc phát event, hiệu ứng đó có thể không xảy ra.
- **Không có log/metric loss mặc định cho mỗi task bị bỏ.** Người vận hành có thể chỉ thấy hệ thống chậm hoặc thiếu kết quả.
- **Với `Future` từ `submit`**, `FutureTask` của công việc bị bỏ thường vẫn ở trạng thái **chưa hoàn thành**: không ai gọi `run()`, `cancel()` hoặc `complete` cho nó.
- **`get()` không timeout có thể chờ vô hạn** nếu không có cơ chế khác hủy Future hoặc luồng chờ không bị interrupt.

`DiscardPolicy` chỉ phù hợp trong trường hợp **được thiết kế rõ ràng để có thể mất task**, không ai chờ task kết thúc, và có phương án quan sát/giới hạn mức bỏ việc. Ví dụ một lần **làm mới dữ liệu cache không quan trọng** mà lần tiếp theo sẽ được đồng bộ lại, với điều kiện nhiệm vụ và hợp đồng dịch vụ thực sự cho phép bỏ qua. Ngay cả khi đó, nên có metric về việc bị bỏ và cần bảo đảm sự nhất quán của cache.

## 4. DiscardOldestPolicy: cứu task mới bằng cách bỏ task đang chờ

`ThreadPoolExecutor.DiscardOldestPolicy` có hành vi về mặt ý tưởng:

~~~java
// Minh họa logic chính; không phải bản sao đầy đủ source JDK.
if (!executor.isShutdown()) {
    executor.getQueue().poll();  // loại đầu hàng đợi, không báo cho chủ Future
    executor.execute(newTask);   // thử thực thi hoặc enqueue lại task mới
}
// Nếu đã shutdown: task mới bị bỏ.
~~~

Với worker chạy A, queue chứa B, task C đến:

~~~text
Trước:
  RUNNING: A
  QUEUED : B
  NEW    : C

C bị từ chối.
DiscardOldestPolicy:
  1. Queue.poll() loại B.
  2. Retry execute(C).

Sau (giả định retry thành công):
  RUNNING: A
  QUEUED : C
  DROPPED: B
~~~

Khi A hoàn thành, C chạy. **B không còn trong queue và sẽ không chạy**, dù B đã được nhận vào hàng đợi ở một thời điểm trước đó.

Cần hiểu chính xác:

- Policy không hủy task đang chạy A; nó **chỉ lấy phần tử đầu trong queue đang đợi**, nếu có.
- Policy **không bảo đảm retry thành công**. Race với các producer khác hoặc trạng thái shutdown có thể làm lần retry lại bị từ chối. JDK cảnh báo việc thử lại có thể tiếp tục lặp.
- Khi executor đã shutdown, policy **bỏ task vừa bị từ chối**, không nhất thiết lấy task nào khỏi queue.
- Nếu dùng một queue **không có phần tử đang chờ**, ví dụ `SynchronousQueue`, không có "oldest waiting task" để lấy. Việc retry có thể tiếp tục thất bại; không dùng policy này với giả định nó luôn tạo được chỗ trống.
- Nếu queue **không theo FIFO** thì `poll()` lấy head theo quy tắc của queue, không phải lúc nào cũng là task có timestamp cũ nhất.
- Nếu task B là `FutureTask` do `submit` tạo, **việc poll khỏi queue không tự động `cancel` Future đó**. Caller giữ Future B có thể chờ mãi.

Đặc biệt nguy hiểm nếu business coi "công việc đã được xếp hàng" là một bảo đảm sẽ được xử lý. Khi task mới đến, policy có thể **hủy ngầm bảo đảm đó** đối với task cũ, mà không gửi notification cho người đã submit.

### 4.1. Tại sao "ưu tiên việc mới hơn" không phải lúc nào cũng đúng?

Giả sử:

- B là lệnh cập nhật trạng thái một đơn hàng.
- C là yêu cầu xuất báo cáo tạm thời.
- Pool đang bão hòa khi C đến.

Nếu dùng `DiscardOldestPolicy`, task B có thể biến mất khỏi queue, dù quan trọng hơn C. Policy **không biết giá trị nghiệp vụ, deadline, loại công việc hay số lần retry**. Nó chỉ thao tác với cấu trúc queue.

Muốn ưu tiên một việc mới, phải thiết kế **quy tắc admission/priority/cancellation có kiểm soát** ở tầng nghiệp vụ. Chẳng hạn, phân loại workload thành pool hoặc hàng đợi riêng, theo dõi trạng thái task và báo rõ khi một job bị thay thế.

## 5. So sánh bốn policy JDK thường gặp

| Policy | Khi pool bão hòa và vẫn đang chạy | Bên submit biết bị từ chối? | Rủi ro chính |
| --- | --- | --- | --- |
| `AbortPolicy` (mặc định của JDK `ThreadPoolExecutor`) | Ném `RejectedExecutionException` | **Có**, nếu caller xử lý exception | Nếu caller bỏ qua lỗi hoặc không retry/lưu việc, nghiệp vụ vẫn mất việc |
| `CallerRunsPolicy` | Caller thực thi task trên chính thread gửi | Thường chạy đồng bộ thay vì bị bỏ | Tăng latency, chặn request/event thread; khi executor đã shutdown chính policy này cũng bỏ task |
| `DiscardPolicy` | Bỏ task **mới** âm thầm | **Không** | Task mới biến mất, Future có thể treo |
| `DiscardOldestPolicy` | Loại phần tử **đầu queue** rồi thử gửi lại task mới | **Không có bảo đảm phản hồi** về task bị loại | Task **đã chờ** biến mất, Future của task cũ có thể treo |

Không có policy nào tự làm công việc bền vững qua process crash. `AbortPolicy` chỉ làm việc từ chối **hiện rõ tại caller**; phía caller còn phải quyết định retry, trả lỗi HTTP, lưu vào queue bền vững hoặc áp dụng backpressure. `CallerRunsPolicy` làm chậm producer trong một số trường hợp nhưng có thể gây vấn đề mới nếu caller là thread nhạy cảm với latency.

## 6. Chương trình Java 17 tái hiện mất việc một cách xác định

Ví dụ này **chạy độc lập bằng Java 17**, không cần Spring/Gradle. Nó khống chế trạng thái pool bằng `CountDownLatch` để một worker đang bận, queue chứa chính xác một task, rồi submit task thứ ba. Nhờ vậy quan sát rõ sự khác nhau của hai policy.

Tạo tệp `RejectionLossDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class RejectionLossDemo {

    public static void main(String[] args) throws Exception {
        runCase("DiscardPolicy",
                new ThreadPoolExecutor.DiscardPolicy());
        runCase("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy());
    }

    private static void runCase(
            String label,
            RejectedExecutionHandler handler) throws Exception {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,                              // corePoolSize
                1,                              // maximumPoolSize
                0L, TimeUnit.MILLISECONDS,       // keepAlive
                new ArrayBlockingQueue<>(1),    // chỉ một task chờ
                handler);

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            // Task A bắt đầu chạy và bị chặn có chủ đích.
            Future<?> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Task B chiếm chỗ duy nhất trong queue.
            Future<String> queued = pool.submit(() -> "queued");

            // Task C đến khi 1 worker bận và queue đầy.
            Future<String> incoming = pool.submit(() -> "incoming");

            // Khi chưa release A, không có worker nào rút B/C khỏi queue.
            System.out.println(label + ": queued in queue=" +
                    pool.getQueue().contains(queued));
            System.out.println(label + ": incoming in queue=" +
                    pool.getQueue().contains(incoming));

            release.countDown();
            running.get(5, TimeUnit.SECONDS);

            Future<String> kept = label.equals("DiscardPolicy")
                    ? queued : incoming;
            Future<String> dropped = label.equals("DiscardPolicy")
                    ? incoming : queued;

            System.out.println(label + ": result=" +
                    kept.get(5, TimeUnit.SECONDS));
            System.out.println(label + ": dropped done=" +
                    dropped.isDone());

            // Cleanup trong demo; hai policy KHÔNG tự hủy Future đã bỏ.
            dropped.cancel(false);
            System.out.println(label + ": dropped cancelled=" +
                    dropped.isCancelled());
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RejectionLossDemo.java
java RejectionLossDemo
~~~

**Stdout chính xác** của chương trình khi hai lần chạy được hoàn tất bình thường:

~~~text
DiscardPolicy: queued in queue=true
DiscardPolicy: incoming in queue=false
DiscardPolicy: result=queued
DiscardPolicy: dropped done=false
DiscardPolicy: dropped cancelled=true
DiscardOldestPolicy: queued in queue=false
DiscardOldestPolicy: incoming in queue=true
DiscardOldestPolicy: result=incoming
DiscardOldestPolicy: dropped done=false
DiscardOldestPolicy: dropped cancelled=true
~~~

Vì sao có thể dự đoán các dòng này?

1. `started.await(...)` giữ main cho đến khi worker bắt đầu A; A chờ `release`.
2. Chỉ có **một** worker và **một** slot queue, vì vậy B ở queue khi C được submit.
3. Với `DiscardPolicy`, B vẫn nằm trong queue; C không vào queue.
4. Với `DiscardOldestPolicy`, B bị `poll()` khỏi queue; C được thêm vào slot trống.
5. Sau khi thả A, task được giữ lại chạy và `Future.get(...)` trả đúng chuỗi `queued` hoặc `incoming`.
6. `dropped.isDone()` là `false` dù task được giữ lại đã hoàn thành: policy không gọi `run` hay `cancel` cho `FutureTask` bị loại.
7. Ví dụ gọi `cancel(false)` **thủ công** để cleanup; đây là thao tác chứng minh rằng Future chỉ chuyển trạng thái cancelled nhờ code ứng dụng, **không nhờ policy**.

Không dùng `dropped.get()` không có timeout trong chương trình này: nó có thể chờ mãi. Với task bất đồng bộ thực, có thể áp dụng `get(timeout, unit)` để giới hạn thời gian chờ, nhưng **timeout không tự khôi phục công việc đã mất**.

### 6.1. Nếu gửi Runnable bằng execute(...) thay vì submit(...)

`execute(Runnable)` không tạo Future trả về cho caller. Với `DiscardPolicy`, lời gọi có thể trả bình thường dù Runnable không chạy; caller không có Future để phát hiện tình trạng ấy. `submit(...)` lại trả một Future nhưng Future có thể không bao giờ được hoàn tất. Vì vậy **không có exception** và **có Future** đều không tương đương với "task chắc chắn được xử lý".

Lưu ý rằng `Future.isDone() == false` ở một thời điểm bất kỳ **không tự chứng minh task bị bỏ**; nó có thể chỉ đang chờ hoặc đang chạy. Ví dụ ở trên tạo điều kiện xác định để biết task đã bị loại nhờ trạng thái worker/queue và policy được dùng.

## 7. Áp dụng vào Spring ThreadPoolTaskExecutor

Spring `ThreadPoolTaskExecutor` bao bọc `ThreadPoolExecutor`, cho phép cấu hình core/max pool, capacity, threadNamePrefix và `RejectedExecutionHandler`. Về giao diện Spring, khi underlying executor **ném** `RejectedExecutionException`, `ThreadPoolTaskExecutor` thường chuyển sang `TaskRejectedException` theo hợp đồng `TaskExecutor`.

Nhưng nếu **handler âm thầm bỏ task và không ném exception**, lớp Spring không thể mặc nhiên biết đã mất công việc chỉ bằng giá trị trả về của handler. Một ứng dụng dùng `@Async` hoặc `submit` có thể không nhận được tín hiệu từ chối ở điểm gọi, trong khi Future/CompletableFuture liên quan không được hoàn thành nếu việc chạy bị bỏ.

Đây là hai cấu hình **chỉ để minh họa rủi ro**, không khuyến nghị dùng cho nghiệp vụ bắt buộc:

~~~java
// Bên trong class @Configuration, có import @Bean,
// ThreadPoolTaskExecutor và ThreadPoolExecutor.
@Bean("lossyExecutor")
public ThreadPoolTaskExecutor lossyExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("lossy-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.DiscardPolicy());
    return executor;
}
~~~

Đổi `DiscardPolicy` thành `DiscardOldestPolicy` sẽ khiến executor có thể bỏ công việc **đang chờ** để nhận công việc mới. Dù đặt bean tên `lossyExecutor`, chỉ những đường gọi thực sự chọn bean ấy mới chịu ảnh hưởng. Ví dụ:

~~~java
// Minh họa trong một Spring bean khác, khi đã bật @EnableAsync.
@Async("lossyExecutor")
public CompletableFuture<String> generateReport() {
    return CompletableFuture.completedFuture("ready");
}
~~~

Chỉ khi lời gọi được Spring proxy chặn và dispatch vào đúng executor thì cấu hình trên mới áp dụng. Tự gọi method trong cùng bean (`this.generateReport()`) có thể bỏ qua cơ chế `@Async` ở chế độ proxy mặc định. Cũng không nên suy ra controller, scheduler, event listener, Spring Batch hay Integration tự động dùng `lossyExecutor`: mỗi điểm tích hợp có cấu hình chọn executor riêng.

### 7.1. Một cấu hình mặc định an toàn hơn

Với phần lớn công việc không chấp nhận mất âm thầm, chọn chiến lược **báo lỗi rõ ràng**:

~~~java
@Bean("importantExecutor")
public ThreadPoolTaskExecutor importantExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("important-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    return executor;
}
~~~

Đây cũng là mảnh code cấu hình Spring, chưa đủ để chạy độc lập. `AbortPolicy` khiến đường submit biết khi pool không chấp nhận task; **không tự thực hiện retry hoặc đưa task vào storage**. Ứng dụng phải có xử lý tương ứng. Đặc biệt khi dùng `@Async`/Future, cần kiểm thử cách lỗi được thể hiện tại ranh giới proxy và caller trong phiên bản/framework đang dùng.

Trong ứng dụng Spring Boot, có thể có TaskExecutor do auto-configuration tạo. Việc tự khai báo nhiều executor có thể thay đổi quy tắc lựa chọn bean mặc định. Nếu công việc quan trọng, **chỉ định qualifier hoặc wiring rõ ràng** thay vì tin một executor bất kỳ sẽ được chọn.

## 8. Ranh giới "accepted", "running", "done" và độ bền công việc

Một lỗi thiết kế phổ biến là gom bốn trạng thái khác nhau thành "đã gửi":

| Trạng thái | Định nghĩa | Có bảo đảm khi execute/submit trả về không? |
| --- | --- | --- |
| **Accepted** | Executor thực sự giữ được task hoặc đang cho chạy | Với policy bỏ âm thầm: **không thể suy ra** từ việc không có exception |
| **Running** | Một worker đã bắt đầu xử lý | Không; task có thể còn trong queue |
| **Completed** | Task kết thúc, kết quả hoặc lỗi đã được ghi nhận | Không; cần kết quả/Future/log/ack phù hợp |
| **Durably recorded** | Công việc đã lưu ở nơi tồn tại qua restart/crash | Không; thread pool memory không phải hàng đợi bền vững |

Hai policy này đặc biệt nguy hiểm khi caller nhận HTTP `202 Accepted` hoặc lưu trạng thái "PROCESSING" ngay sau khi submit nhưng không có ghi nhận đáng tin rằng task đã được tiếp nhận. Một executor có thể im lặng bỏ task hoặc loại task cũ sau đó, khiến người dùng thấy job "đang chạy" mãi.

Nếu ứng dụng thật sự hứa sẽ xử lý công việc, nên **ghi nhận job trong database/outbox hoặc broker có durability**, rồi dùng consumer/worker lấy và xử lý với chiến lược retry, deduplication và trạng thái lỗi rõ ràng. ThreadPoolTaskExecutor có thể là tài nguyên chạy worker, nhưng **không đóng vai trò kho lưu bền vững**.

### 8.1. Vì sao Future không tự giải quyết mất task?

Khi gọi `ExecutorService.submit`, một `RunnableFuture` (thường là `FutureTask`) được tạo và gửi vào executor. Chỉ khi có thread thực thi task, hoặc có người gọi cancel, Future mới đi tới trạng thái kết thúc tương ứng. Nếu policy bỏ task mà không chạy/hủy nó, **Future có thể tồn tại mãi trong trạng thái pending**.

Các hệ quả thực tế:

- `future.get()` không timeout có thể chờ không giới hạn.
- `future.get(3, TimeUnit.SECONDS)` có thể ném `TimeoutException`, nhưng đó là **timeout chờ**, chưa khẳng định nguyên nhân là bị bỏ hay chạy quá lâu.
- `CompletableFuture.join()` cũng có thể chờ vô hạn nếu future không bao giờ hoàn thành.
- `CompletableFuture.orTimeout(...)` làm kết quả tương lai có timeout, nhưng không tự chạy lại hoặc hoàn thành side effect nghiệp vụ.
- Với `DiscardOldestPolicy`, Future của task **đã được queue nhận từ trước** có thể mắc kẹt sau khi task bị thay thế. Nguy cơ này khó quan sát hơn việc từ chối ngay tại lúc submit mới.

Không coi `shutdown()` hay `shutdownNow()` là thao tác sẽ **tự hoàn tất mọi Future** đã bị một handler vứt bỏ. Future bị bỏ khỏi queue trước đó có thể không còn được executor nhìn thấy để xử lý.

## 9. Lựa chọn thay thế và cách thiết kế để không mất việc ngoài ý muốn

### 9.1. Thể hiện lỗi từ chối ngay tại producer

Đối với task không thể bỏ, dùng handler ném lỗi (thường `AbortPolicy`), bắt lỗi tại biên gửi việc và quyết định:

- Trả **429** khi áp dụng hạn mức cho client, hoặc **503** khi dịch vụ đang quá tải, cùng thông tin retry phù hợp nếu là HTTP.
- Retry **có giới hạn** với exponential backoff và jitter, chỉ khi operation có thể retry an toàn.
- Lưu task vào hệ thống bền vững để xử lý lại.
- Áp dụng bounded admission queue, semaphore hoặc rate limit **trước khi** gọi executor để tránh tạo quá nhiều việc.

Đừng retry vô hạn ngay trong request thread khi pool đã bão hòa. Retry không có giới hạn có thể làm tắc chính những thread đang cần để giải tỏa quá tải. Với tác vụ có side effect, cần định nghĩa **idempotency** để tránh thực thi trùng khi caller không biết lần trước đã xử lý đến đâu.

### 9.2. CallerRunsPolicy: backpressure nhưng có hệ quả

`CallerRunsPolicy` cho phép thread đang gọi `execute` tự chạy công việc khi pool bão hòa (nếu executor chưa shutdown). Điều này có thể làm giảm tốc độ producer vì producer bị chặn cho đến khi task xong, là một dạng **backpressure**.

Nhưng nếu caller là HTTP request thread, message listener hoặc scheduler thread, việc làm nặng có thể làm tăng latency, block I/O hoặc khiến lịch trễ. Khi executor đã shutdown, `CallerRunsPolicy` cũng có thể **bỏ** task mới theo hợp đồng của nó. Vì vậy cần đánh giá đường gọi thay vì coi CallerRuns là biện pháp bảo đảm không mất việc trong mọi trạng thái.

### 9.3. Nếu công việc được phép bỏ, phải định nghĩa điều kiện bỏ

Một số workload có thể chấp nhận **lossy execution** như:

- Sự kiện telemetry chỉ cần lấy mẫu và đã được đánh dấu có thể mất.
- Yêu cầu làm mới một snapshot tạm thời mà phiên bản mới nhất sẽ thay thế bản cũ.
- Cập nhật UI preview không quan trọng, khi người dùng chỉ cần kết quả gần nhất.

Ngay cả trường hợp này, **DiscardOldestPolicy không hiểu key hoặc phiên bản dữ liệu**. Bỏ phần tử đầu queue có thể loại một task quan trọng hơn task mới. Nếu muốn "giữ phiên bản mới nhất theo từng key", hãy thiết kế một **coalescing queue/last-value-wins mechanism** có chủ đích, không giả định DiscardOldest cung cấp đúng hợp đồng đó.

Nên định nghĩa mức loss tối đa, cách ghi metric, cách giao tiếp với caller và khả năng phục hồi. Nếu task có người đang chờ Future, khi bỏ phải **hoàn tất Future bằng hủy/lỗi có quan sát được**; chỉ xóa khỏi queue là chưa đủ.

### 9.4. Custom handler khi phải ghi nhận từng lần từ chối

Một ví dụ nhỏ dễ kiểm soát là custom handler **ghi metric và ném lỗi**, không im lặng mất việc. Đoạn sau đặt trong một class cấu hình có bean executor và một `AtomicLong` dùng làm bộ đếm; không phải một ứng dụng Spring độc lập:

~~~java
AtomicLong rejected = new AtomicLong();

ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(2);
executor.setQueueCapacity(50);

executor.setRejectedExecutionHandler((task, pool) -> {
    rejected.incrementAndGet();
    throw new RejectedExecutionException(
            "Important task rejected: executor overloaded or stopped");
});
~~~

Cần import `AtomicLong`, `RejectedExecutionException` và `ThreadPoolTaskExecutor`. Trong ứng dụng thật, dùng metrics registry phù hợp, có phân biệt `shutdown` và `saturation`, logger với tần suất được giới hạn và mã lỗi rõ ràng; không log payload/token/user data nhạy cảm.

Nếu nghiệp vụ thật sự cần loại task chờ và ưu tiên task mới, handler cần **ghi nhận task bị loại, hủy Future nếu có, quyết định retry hợp lý, xử lý trường hợp queue rỗng/shutdown và truyền trạng thái tới caller**. Javadoc của `DiscardOldestPolicy` còn đưa ví dụ kiểm tra task bị poll có phải `Future` để gọi `cancel(false)`. Dù vậy, một handler tự gọi lại `execute` vẫn phải cân nhắc race và khả năng từ chối lặp; đừng sao chép logic thay thế queue vào sản phẩm mà không kiểm thử concurrency và hợp đồng nghiệp vụ.

## 10. Quan sát mất công việc và kiểm thử

### 10.1. Chỉ số vận hành nên có

Bên cạnh số thread active, size queue, execution time và wait time, nên đo:

- **tasks_submitted**: số công việc producer yêu cầu gửi.
- **tasks_accepted**: số công việc thực sự có bằng chứng được tiếp nhận theo hợp đồng của hệ thống.
- **tasks_started/completed/failed**: được ghi ở nơi thực thi hoặc ở hệ thống quản lý job.
- **tasks_rejected/dropped/replaced**: ghi chính xác ở chính sách admission/rejection và khi chủ động thay thế task.
- **task_age / oldest_queue_wait**: giúp nhận ra backlog trước khi queue đầy.
- **Future timeout, cancelled, still pending**: điều tra những công việc không bao giờ có kết quả.

`ThreadPoolExecutor.getCompletedTaskCount()` không thay thế một bộ đếm loss đáng tin cậy; nó thống kê những task worker đã hoàn tất, không tự thông báo rõ mọi Runnable mà policy âm thầm bỏ. Số task "submitted" tính tại producer cũng không đủ để phân biệt accepted với dropped. Thực hiện đo theo đúng ranh giới nghiệp vụ.

### 10.2. Kiểm thử có kiểm soát

Thử nghiệm nên khống chế trạng thái (như `CountDownLatch` ở mục 6), rồi kiểm tra:

1. Task nào ở worker, task nào ở queue, task nào mới đến.
2. Policy đã áp dụng trong trạng thái bão hòa hay shutdown.
3. Task mới hay task cũ bị bỏ.
4. Bên gọi có nhận được exception, Future hủy hay trạng thái thất bại không.
5. Sau shutdown và restart, công việc bắt buộc có được phục hồi không.
6. Dưới nhiều producer đồng thời, có race khi handler tự poll/retry không.

Khi test với `DiscardPolicy` hoặc `DiscardOldestPolicy`, **không dùng `Future.get()` không timeout** cho task có thể bị loại. Hãy giới hạn thời gian, assert rõ trạng thái, cleanup bằng cancel và shutdown để test không treo. Test một lần qua không chứng minh thiết kế an toàn dưới mọi interleaving; kết hợp phân tích semantic và stress test có giới hạn.

## 11. Những lỗi suy luận cần tránh

| Phát biểu dễ nhầm | Điều đúng |
| --- | --- |
| "Không ném RejectedExecutionException thì task đã được nhận." | Handler có thể bỏ task âm thầm; không có exception không phải ACK |
| "DiscardPolicy chỉ giảm tốc độ xử lý khi quá tải." | Nó **bỏ công việc mới**, không tự chờ hoặc retry |
| "DiscardOldestPolicy chỉ bỏ task đang chạy lâu nhất." | Nó `poll()` **đầu queue đang chờ**, không hủy worker đang chạy |
| "DiscardOldestPolicy chắc chắn nhận được task mới." | Nó **retry**, vẫn có thể thất bại/reject lại hoặc executor shutdown |
| "submit trả Future nghĩa là sẽ có kết quả." | Future có thể pending vô thời hạn nếu task bị bỏ mà không hủy |
| "Future.get(timeout) tự chạy lại task đã mất." | Timeout chỉ giới hạn chờ; không phục hồi side effect |
| "Spring @Async luôn báo lỗi nếu pool bỏ việc." | Nếu handler không ném exception, các tích hợp không có tín hiệu rejection rõ ràng |
| "Queue nhỏ cộng max thread lớn thì chắc không bị quá tải." | Nguồn gửi vẫn có thể vượt năng lực xử lý và gây bão hòa |
| "DiscardOldest giữ công việc quan trọng hơn." | Policy không biết ý nghĩa nghiệp vụ, chỉ biết queue head |
| "Một pool trong JVM bảo đảm xử lý qua restart." | In-memory executor không phải job store bền vững |

## 12. Câu hỏi tự kiểm tra

1. Pool có một worker đang chạy A, queue dung lượng một chứa B, task C đến. `DiscardPolicy` bỏ task nào? **C**, tức task mới bị từ chối.
2. Cùng tình huống trên, `DiscardOldestPolicy` thường bỏ task nào? **B** ở đầu queue; sau đó thử gửi lại C.
3. Với `DiscardOldestPolicy`, A đang chạy có bị hủy không? **Không**, policy chỉ thao tác ở queue đang chờ.
4. Vì sao `Future` của B có thể treo sau khi B bị poll? **Vì B không được chạy và policy không gọi `cancel` hay hoàn thành Future.**
5. Nếu queue là `SynchronousQueue` đang không có phần tử chờ, có thể tin `DiscardOldestPolicy` sẽ tạo chỗ trống không? **Không**; không có queued task để poll và retry có thể tiếp tục bị từ chối.
6. `AbortPolicy` có bảo đảm task được xử lý khi bão hòa không? **Không**; nó chỉ làm từ chối hiện thành exception để caller xử lý.
7. Task được submit bằng `@Async` vào một `ThreadPoolTaskExecutor` dùng `DiscardPolicy`. Có thể kết luận Future chắc chắn hoàn tất không? **Không**; một task bị bỏ có thể khiến quá trình chờ kết quả không bao giờ kết thúc.
8. Khi nào có thể chấp nhận bỏ task? **Chỉ khi hợp đồng nghiệp vụ rõ ràng cho phép loss, có quan sát và cơ chế phục hồi/hoàn tất trạng thái người chờ khi cần.**
9. Nếu phải xử lý một payment job dù ứng dụng restart, liệu đổi DiscardPolicy sang CallerRunsPolicy là đủ? **Không**; cần lưu và điều phối công việc bền vững và thiết kế idempotency.
10. Nếu queue là priority queue, task được DiscardOldest lấy ra có chắc đến sớm nhất không? **Không**; head do thứ tự của queue quyết định.

**Kết luận:** `DiscardPolicy` có thể làm biến mất **công việc mới**; `DiscardOldestPolicy` có thể làm biến mất **công việc đã chờ**. Với cả hai, nguy cơ nằm ở việc mất công việc **không có tín hiệu đúng mức**, khiến kết quả thiếu, Future treo và hệ thống tưởng đã nhận việc. Với nghiệp vụ không cho phép mất task, chọn **admission rõ ràng, rejection có thể quan sát, backpressure và lưu công việc bền vững** tùy yêu cầu.

### Tài liệu chính thức

- [Java 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java 17 — ThreadPoolExecutor.DiscardPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html)
- [Java 17 — ThreadPoolExecutor.DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
