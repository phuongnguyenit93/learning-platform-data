# Phân biệt trạng thái thread và trạng thái nghiệp vụ trong Java

## 1. Vì sao phải phân biệt?

Khi xây dựng một tác vụ bất đồng bộ, ta thường muốn biết cả hai điều:

1. **Thread hiện đang ở trạng thái nào?** Nó chưa khởi động, có thể chạy, đang chờ khóa/điều kiện, hay đã kết thúc?
2. **Công việc nghiệp vụ đang ở trạng thái nào?** Tác vụ đã được tiếp nhận, đang xử lý, thành công, thất bại, bị hủy hay cần chạy lại?

Hai câu hỏi này **không tương đương**.

**Thread state** là trạng thái của luồng thực thi trong Java, được JVM biểu diễn bằng **Thread.State**. Nó phục vụ quan sát vòng đời và chẩn đoán tại thời điểm đọc.

**Business state** (còn gọi là *task/job/workflow status*) là trạng thái do ứng dụng **tự định nghĩa** để biểu diễn tiến độ và kết quả có ý nghĩa với người dùng hoặc hệ thống nghiệp vụ. Ví dụ **PENDING → RUNNING → SUCCEEDED/FAILED**.

Điểm quan trọng nhất: **Thread.State.TERMINATED không đồng nghĩa công việc thành công; Thread.State.WAITING không đồng nghĩa công việc nghiệp vụ đang chờ xử lý; Thread.State.RUNNABLE không đồng nghĩa nghiệp vụ đang RUNNING.**

Bài này nói về **Java concurrency nói chung** và các API trong JDK. Các cơ chế quản lý task, cấu hình scheduler hoặc sự kiện thuộc Spring nằm ở chương riêng.

## 2. Thread.State: sáu trạng thái của JVM

Java cung cấp enum **java.lang.Thread.State** với sáu giá trị:

| Thread.State | JVM mô tả điều gì? | Ví dụ |
| --- | --- | --- |
| **NEW** | Đối tượng Thread đã tạo nhưng chưa gọi start(). | new Thread(task) |
| **RUNNABLE** | Đang thực thi hoặc sẵn sàng được scheduler cấp thời gian CPU. | Mã Java đang chạy hoặc chờ lượt CPU |
| **BLOCKED** | Chờ lấy **monitor lock** để vào synchronized. | Một thread khác đang giữ cùng monitor |
| **WAITING** | Đợi vô thời hạn cho một hành động khác. | Object.wait(), Thread.join(), CountDownLatch.await() không timeout |
| **TIMED_WAITING** | Đợi một khoảng thời gian có hạn. | Thread.sleep(...), join(timeout), await(timeout) |
| **TERMINATED** | Hàm run() của Thread đã kết thúc. | Chạy xong, return, hoặc exception không được xử lý |

Lưu ý chính xác:

- **RUNNABLE** không có nghĩa thread đang dùng CPU ngay lúc đo.
- **BLOCKED** là trạng thái chờ **monitor của synchronized**. Thread đợi **ReentrantLock** hoặc một thao tác I/O có thể được quan sát ở trạng thái khác, tùy API và triển khai; không suy luận rằng mọi kiểu “bị chặn” đều là Thread.State.BLOCKED.
- **WAITING/TIMED_WAITING** không cho biết vì sao task nghiệp vụ chờ; đó chỉ là kiểu chờ trong luồng thực thi.
- **getState()** trả về một **snapshot**, có thể thay đổi ngay sau khi đọc.
- **TERMINATED** nói thread đã dừng, **không cho biết** nó hoàn thành thành công, ném lỗi hay dừng vì yêu cầu hủy.
- Một đối tượng Thread đã TERMINATED **không thể gọi start() lại**; muốn thực thi tiếp phải có Thread mới hoặc cơ chế thực thi tác vụ khác.

Vòng đời phổ biến:

~~~text
NEW --start()--> RUNNABLE --run() kết thúc--> TERMINATED
                    │   ^
                    v   │
           BLOCKED / WAITING / TIMED_WAITING
~~~

Đây là sơ đồ khái quát, không phải máy trạng thái nghiệp vụ. Chẳng hạn, khi một thread trong **run()** đang gọi **sleep()**, trạng thái là TIMED_WAITING dù tác vụ của nó vẫn mang trạng thái nghiệp vụ **RUNNING**.

### Không sử dụng getState() làm giao thức điều phối

Ví dụ sau là **anti-pattern**:

~~~java
// Mã minh họa lỗi: worker là Thread đã được tạo ở nơi khác.
if (worker.getState() == Thread.State.TERMINATED) {
    markJobSucceeded();
}
~~~

Thứ nhất, **markJobSucceeded()** là phương thức giả định của ứng dụng, không phải API JDK. Thứ hai, thread chết có thể do lỗi. Thứ ba, snapshot không thay thế được **join()**, **Future.get()**, latch hoặc sự kiện kết thúc có cơ chế đồng bộ. Nếu muốn biết một thread đã hoàn thành, dùng **join()**; nếu muốn biết **kết quả công việc**, cần ghi nhận và kiểm tra trạng thái/kết quả nghiệp vụ.

## 3. Business state: mô hình do ứng dụng thiết kế

JDK không có enum chung mang tên **BusinessState** hay **JobStatus** phù hợp cho mọi bài toán. Ứng dụng tự đặt trạng thái theo ý nghĩa thực tế.

Một mô hình tối giản cho một job:

~~~text
PENDING ──nhận xử lý──> RUNNING ──hoàn thành──> SUCCEEDED
                          │
                          ├── lỗi ─────────> FAILED
                          └── hủy thành công -> CANCELLED
~~~

Có thể thêm **QUEUED**, **RETRYING**, **TIMED_OUT**, **CANCEL_REQUESTED**, **PAUSED** tùy yêu cầu; đừng tự thêm chỉ vì Thread.State cũng có các trạng thái chờ. Trong ứng dụng thực, cần định nghĩa chính xác khi nào một transition được phép xảy ra.

Ví dụ Java enum để mô hình hóa:

~~~java
enum JobStatus {
    PENDING,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCEL_REQUESTED,
    CANCELLED
}
~~~

Đây là **đoạn mã minh họa**; enum trên chưa có **main()**. Ý nghĩa mỗi trạng thái cần được thống nhất: ví dụ **CANCEL_REQUESTED** chỉ nói có yêu cầu hủy, còn **CANCELLED** nói ứng dụng đã xác nhận công việc dừng theo chính sách hủy.

Điều khác biệt với Thread.State:

- Business state có thể được **lưu xuống cơ sở dữ liệu** để dùng sau khi JVM thoát.
- Business state có thể **tồn tại trước khi tạo thread**, hoặc sau khi một thread đã hoàn tất.
- Một job có thể đi qua nhiều thread trong các giai đoạn khác nhau; một worker thread có thể xử lý nhiều job.
- Business state đại diện cho **đơn vị công việc** và kết quả theo hợp đồng ứng dụng, không phải trạng thái nội bộ của worker.
- **SUCCEEDED**, **FAILED**, **CANCELLED** chỉ đáng tin khi có quy tắc ghi nhận rõ ràng; không suy luận từ trạng thái thread.

## 4. So sánh trực tiếp

| Câu hỏi | Thread state | Business state |
| --- | --- | --- |
| Đối tượng được mô tả | Một **Thread** cụ thể | Một task, job, order, workflow hoặc operation |
| Ai định nghĩa | JDK: enum Thread.State | Ứng dụng: enum, bản ghi, state machine |
| Nguồn quan sát | Thread.getState() | Trường status, event, Future/result hoặc kho lưu trữ |
| Tính ổn định | Snapshot tức thời | Theo transition và chính sách nghiệp vụ |
| Có nghĩa là thành công/thất bại? | Không có trạng thái SUCCESS/FAILED | Có thể có SUCCEEDED/FAILED |
| Có thể tồn tại lâu hơn một thread? | Không, gắn với đối tượng Thread | Có thể |
| Có bắt buộc được lưu bền vững? | Không | Tùy yêu cầu; job lâu dài thường cần persistence |
| Có thay thế synchronization không? | Không | Không; trạng thái chia sẻ vẫn phải an toàn |
| Trạng thái kết thúc | TERMINATED | SUCCEEDED, FAILED, CANCELLED hoặc trạng thái cuối khác |

Một số cặp dễ gây hiểu nhầm:

| Quan sát | Trạng thái nghiệp vụ vẫn có thể là | Vì sao |
| --- | --- | --- |
| Thread **NEW** | PENDING, QUEUED, hoặc chưa gắn job | Business status có thể được tạo từ trước |
| Thread **RUNNABLE** | RUNNING, RETRYING, CANCEL_REQUESTED | Thread có thể đang thực thi logic của nhiều giai đoạn |
| Thread **WAITING** | RUNNING | Task đang chờ phản hồi/điều kiện để tiếp tục bước đang xử lý |
| Thread **TIMED_WAITING** | RUNNING, RETRYING, CANCEL_REQUESTED | Thread đang sleep/backoff/chờ timeout |
| Thread **BLOCKED** | RUNNING | Task đã bắt đầu nhưng đang đợi monitor |
| Thread **TERMINATED** | SUCCEEDED, FAILED, CANCELLED | Worker đã kết thúc bằng nhiều cách khác nhau |

Bảng chỉ nêu **khả năng hợp lệ** theo thiết kế của từng ứng dụng, không có ánh xạ tự động được JDK bảo đảm.

## 5. Ví dụ chạy được: thread đang chờ nhưng job đang RUNNING

Tệp **ThreadAndJobStateDemo.java** (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class ThreadAndJobStateDemo {
    enum JobStatus { PENDING, RUNNING, SUCCEEDED }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<JobStatus> status =
                new AtomicReference<>(JobStatus.PENDING);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            status.set(JobStatus.RUNNING);
            started.countDown();
            try {
                proceed.await();
                status.set(JobStatus.SUCCEEDED);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "job-worker");

        System.out.println("before start: " + status.get());
        worker.start();

        started.await();
        System.out.println("after started signal: " + status.get());

        proceed.countDown();
        worker.join();
        System.out.println("after join: " + status.get());
        System.out.println("thread: " + worker.getState());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ThreadAndJobStateDemo.java
java ThreadAndJobStateDemo
~~~

Stdout (khi không có interrupt từ bên ngoài):

~~~text
before start: PENDING
after started signal: RUNNING
after join: SUCCEEDED
thread: TERMINATED
~~~

**Giải thích:**

1. **status** là nghiệp vụ của job, được ứng dụng lưu độc lập trong **AtomicReference**.
2. Worker chuyển trạng thái job sang RUNNING rồi báo **started.countDown()**. **started.await()** của main đảm bảo main quan sát tín hiệu và cập nhật đã xảy ra trước countDown.
3. Worker đợi **proceed.await()**; trong khoảng chờ nó có thể được quan sát là **WAITING**, nhưng **status vẫn RUNNING**. Ví dụ cố ý không in **worker.getState()** khi đang chạy vì snapshot không có kết quả cố định và có race với việc release latch.
4. Main phát tín hiệu **proceed.countDown()** rồi **join()**. Worker đổi job thành SUCCEEDED trước khi kết thúc; main quan sát kết quả ổn định sau join().
5. Sau khi **join()** không timeout trả về bình thường vì worker đã kết thúc, **getState()** là TERMINATED. Thành công được biểu diễn bởi cập nhật **status**, chứ không được suy ra từ TERMINATED.

Ví dụ dùng latch để thiết lập các mốc rõ ràng, không dùng **Thread.sleep()** để phỏng đoán thread đã chạy đến đâu.

**Giới hạn của ví dụ:** Worker có nhánh bắt InterruptedException để kết thúc hợp tác, nhưng mô hình enum tối giản không có trạng thái CANCELLED/FAILED cho trường hợp đó. Khi thiết kế thực tế, mọi nhánh lỗi và hủy phải cập nhật trạng thái tương ứng. Phần tiếp theo xử lý trường hợp thất bại.

## 6. TERMINATED không có nghĩa SUCCEEDED

Thread có thể kết thúc vì phương thức run() return bình thường, vì exception không được bắt, hoặc vì code chủ động xử lý yêu cầu hủy rồi return. **Thread.State.TERMINATED** giống nhau trong tất cả các tình huống này.

Nếu không bắt exception ở worker, một exception chưa xử lý sẽ được báo cho uncaught exception handler theo cấu hình, nhưng **thread gọi join() không tự nhận lại exception đó**. Vì vậy, nếu chỉ làm:

~~~java
worker.start();
worker.join();
System.out.println("Success");
~~~

Đây là **đoạn minh họa logic sai** nếu dòng Success có nghĩa tác vụ nghiệp vụ thành công. **worker** phải là đối tượng Thread đã được tạo, và đoạn này cần xử lý hoặc khai báo **InterruptedException**. **join()** chỉ xác nhận hoàn tất vòng đời thread (khi trả về do kết thúc), không xác nhận thành công.

### Ví dụ có ghi nhận FAILED riêng

Tệp **BusinessFailureDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class BusinessFailureDemo {
    enum JobStatus { PENDING, RUNNING, SUCCEEDED, FAILED }

    static void process(String input) {
        if (input.isBlank()) {
            throw new IllegalArgumentException("empty input");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<JobStatus> status =
                new AtomicReference<>(JobStatus.PENDING);
        AtomicReference<String> error = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            status.set(JobStatus.RUNNING);
            try {
                process("");
                status.set(JobStatus.SUCCEEDED);
            } catch (RuntimeException ex) {
                error.set(ex.getMessage());
                status.set(JobStatus.FAILED);
            }
        }, "validation-worker");

        worker.start();
        worker.join();

        System.out.println("thread = " + worker.getState());
        System.out.println("job = " + status.get());
        System.out.println("error = " + error.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BusinessFailureDemo.java
java BusinessFailureDemo
~~~

Stdout:

~~~text
thread = TERMINATED
job = FAILED
error = empty input
~~~

**Tại sao kết quả đúng?** Mã nghiệp vụ cố ý ném lỗi khi chuỗi rỗng. Worker bắt lỗi, lưu mô tả và cập nhật FAILED trước khi thoát. **join()** bảo đảm main chờ hết worker và nhìn thấy các ghi trước khi worker kết thúc; **AtomicReference** giúp định nghĩa và chia sẻ trạng thái rõ ràng.

Trong ứng dụng thật, đừng lưu cả thông báo chứa dữ liệu nhạy cảm vào status log công khai. Đặt chính sách rõ ràng cho loại lỗi nào là retryable và có cần phân biệt **FAILED** với **CANCELLED**, **TIMED_OUT** hoặc **PARTIALLY_COMPLETED**.

## 7. Vì sao không ánh xạ 1 thread = 1 job?

Ví dụ đơn giản khi học **new Thread(runnable)** có thể cho cảm giác mỗi công việc có một thread riêng. Điều đó không đúng nói chung:

- **Một thread thực thi nhiều task tuần tự:** executor có pool worker tái sử dụng thread sau từng job. Worker vẫn sống khi job trước đã SUCCEEDED hoặc FAILED.
- **Một job gồm nhiều bước chạy trên nhiều thread:** khi fan-out, callback hoặc pipeline chuyển giai đoạn, không có một Thread.State đơn lẻ đại diện cho toàn bộ job.
- **Job đang QUEUED nhưng chưa có worker chạy:** business state là QUEUED, dù không tồn tại thread riêng của job.
- **Task đang chờ I/O trên một worker:** worker có thể được quan sát ở các trạng thái Java khác nhau, nhưng nghiệp vụ vẫn RUNNING.
- **Job được lưu bền vững và chờ retry:** một worker đã TERMINATED, nhưng job có thể chuyển RETRYING và tiếp tục trên worker khác.

Đừng dùng thread name, thread ID hay Thread.State như khóa nhận dạng duy nhất cho job. Hãy dùng **jobId/correlationId** riêng, liên kết các lần thực thi vào một công việc nghiệp vụ.

### Future là trạng thái tác vụ ở tầng JDK, không phải Thread.State

Trong **java.util.concurrent**, **Future<T>** biểu diễn kết quả có thể đến sau khi gửi tác vụ:

- **isDone()** là true khi computation đã hoàn tất **bình thường, thất bại hoặc bị hủy**.
- **isCancelled()** báo việc hủy Future thành công, nhưng không hứa side effect đã được rollback.
- **get()** trả kết quả khi hoàn thành bình thường; có thể ném **ExecutionException** khi code task lỗi, **CancellationException** khi bị hủy, hoặc **InterruptedException** khi thread đang chờ bị ngắt.
- Nếu dùng **cancel(true)**, cơ chế có thể gửi interrupt đến thread đang thực thi, nhưng task cần hợp tác; **cancel()** không đảm bảo undo trạng thái đã tác động ra ngoài.

Do đó **Future.isDone() = true** chưa đủ để đánh dấu **SUCCEEDED**.

### Ví dụ Future: kết quả công việc khác vòng đời worker

Tệp **FutureOutcomeDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureOutcomeDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = executor.submit(() -> 6 * 7);
            int result = future.get();

            System.out.println("result = " + result);
            System.out.println("future done = " + future.isDone());
            System.out.println("future cancelled = " + future.isCancelled());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FutureOutcomeDemo.java
java FutureOutcomeDemo
~~~

Stdout:

~~~text
result = 42
future done = true
future cancelled = false
~~~

**future.get()** xác nhận tác vụ đã trả giá trị 42 hoặc sẽ ném ngoại lệ tương ứng. Kết quả **không suy ra** worker thread đã chết: với **newSingleThreadExecutor()**, worker có thể sống để nhận job tiếp theo cho đến khi executor được shutdown. Ví dụ gọi shutdown để kết thúc tài nguyên một cách có kiểm soát.

Trong hệ thống nghiệp vụ, bạn vẫn cần quy định **khi nào** ghi SUCCEEDED: sau xử lý tính toán, sau commit cơ sở dữ liệu, sau gửi sự kiện, hay sau cả chuỗi bước. Future completion là tín hiệu tầng thực thi, không tự định nghĩa giao dịch nghiệp vụ.

## 8. Trạng thái nghiệp vụ chia sẻ cần đồng bộ hóa

Vì status có thể được đọc/ghi từ nhiều thread, một biến thông thường như:

~~~java
// Mã minh họa thiếu bảo đảm visibility giữa các thread:
JobStatus status = JobStatus.PENDING;
~~~

chưa đủ nếu nhiều thread đọc/ghi không có quan hệ happens-before. **volatile** bảo đảm visibility và thứ tự phù hợp cho đọc/ghi riêng lẻ, nhưng **không làm chuỗi check-then-set nguyên tử**:

~~~java
// Mã minh họa lỗi khi hai thread cùng chạy:
if (status == JobStatus.PENDING) {
    status = JobStatus.RUNNING;
}
~~~

Hai thread đều có thể đọc PENDING và cùng xử lý một job. Một số cách đúng tùy nhu cầu là:

- **AtomicReference.compareAndSet(expected, updated)** để cập nhật có điều kiện nguyên tử trên một biến trong bộ nhớ.
- **synchronized / Lock** khi cần bảo vệ nhiều trường hoặc một bất biến phức tạp.
- **BlockingQueue, CountDownLatch, Future** để trao tác vụ/tín hiệu/kết quả theo hợp đồng của chúng.
- **Transaction và cập nhật có điều kiện ở kho lưu trữ** khi nhiều process hoặc instance cùng xử lý một job; **AtomicReference chỉ bảo vệ đối tượng trong một JVM**, không thay thế đồng bộ hóa giữa các tiến trình.

### Ví dụ: ngăn hai thread cùng chuyển PENDING → RUNNING

Tệp **JobTransitionDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class JobTransitionDemo {
    enum JobStatus { PENDING, RUNNING, SUCCEEDED }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<JobStatus> status =
                new AtomicReference<>(JobStatus.PENDING);
        AtomicInteger accepted = new AtomicInteger();
        AtomicInteger rejected = new AtomicInteger();

        Runnable requestStart = () -> {
            if (status.compareAndSet(
                    JobStatus.PENDING, JobStatus.RUNNING)) {
                accepted.incrementAndGet();
            } else {
                rejected.incrementAndGet();
            }
        };

        Thread a = new Thread(requestStart, "request-a");
        Thread b = new Thread(requestStart, "request-b");
        a.start();
        b.start();
        a.join();
        b.join();

        if (!status.compareAndSet(
                JobStatus.RUNNING, JobStatus.SUCCEEDED)) {
            throw new IllegalStateException("Unexpected job state");
        }

        System.out.println("accepted = " + accepted.get());
        System.out.println("rejected = " + rejected.get());
        System.out.println("job = " + status.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 JobTransitionDemo.java
java JobTransitionDemo
~~~

Stdout:

~~~text
accepted = 1
rejected = 1
job = SUCCEEDED
~~~

**Một CAS thành công**, còn CAS kia thấy trạng thái đã khác PENDING và từ chối. Vì chỉ in kết quả tổng hợp sau khi đã join cả hai thread nên stdout không phụ thuộc thread a hay b thắng.

Đây là ví dụ về **chuyển trạng thái đúng luật**; chưa thực thi nội dung business thực tế. Trong job thật, chỉ request được chấp nhận mới được tiến hành xử lý; việc chuyển RUNNING → SUCCEEDED phải xảy ra **sau khi** xử lý thành công. Nếu lỗi, cập nhật FAILED; nếu hủy, áp dụng luật hủy riêng.

### Thiết kế luật chuyển trạng thái

Một state machine nên trả lời được:

| Chuyển trạng thái | Khi nào hợp lệ? |
| --- | --- |
| PENDING → RUNNING | Một worker nhận quyền bắt đầu xử lý |
| RUNNING → SUCCEEDED | Các điều kiện thành công thực sự đã hoàn tất |
| RUNNING → FAILED | Có lỗi không thể hoàn tất theo hợp đồng hiện tại |
| RUNNING → CANCEL_REQUESTED | Một tác nhân yêu cầu hủy công việc đang chạy |
| CANCEL_REQUESTED → CANCELLED | Worker/giao thức xác nhận đã dừng theo chính sách |
| FAILED → RETRYING | Có chính sách retry và hạn mức lần thử |
| RETRYING → RUNNING | Một attempt mới được cấp quyền thực thi |

Đây là các ví dụ quy tắc **do ứng dụng đặt ra**, không phải quy tắc bắt buộc của JDK. Nếu retry, cần phân biệt **jobId** (danh tính công việc xuyên nhiều lần thử) với **attemptId** (danh tính từng lượt chạy). Tránh việc completion đến muộn từ một attempt cũ ghi đè trạng thái của attempt mới: dùng version, attempt token hoặc update có điều kiện phù hợp.

## 9. Hủy và timeout: trạng thái kỹ thuật khác quyết định nghiệp vụ

Khi gọi **worker.interrupt()**, ta gửi một yêu cầu ngắt. Điều đó **không tự chứng minh** business state phải là CANCELLED. Worker có thể:

- Chưa quan sát cờ interrupt, hoặc đang ở bước không thể bị interrupt.
- Bắt InterruptedException rồi cleanup và thoát.
- Hoàn thành công việc gần như đồng thời với yêu cầu hủy.
- Đã tạo side effect trước khi hủy, cần rollback/bù trừ theo luật nghiệp vụ.

Một mô hình rõ ràng có thể dùng **CANCEL_REQUESTED** trước, rồi chỉ chuyển **CANCELLED** khi có xác nhận phù hợp. Nếu công việc đã thành công trước yêu cầu hủy, luật chuyển trạng thái có thể từ chối hủy hoặc chỉ ghi nhận yêu cầu đến muộn.

**TIMED_WAITING** không phải **TIMED_OUT**. Thread đang **Thread.sleep(1000)** ở TIMED_WAITING nhưng task chưa chắc quá hạn. Ngược lại, business job có thể đã quá deadline theo policy trong khi worker vẫn RUNNABLE, BLOCKED hoặc đang I/O.

Nếu dùng **Future.get(timeout, unit)**, khi timeout nó ném **TimeoutException** cho **lời gọi chờ**; điều này **không tự dừng** computation và **không tự hủy Future**. Cần chính sách rõ ràng nếu muốn cancel, retry hoặc đánh dấu TIMED_OUT.

### Sơ đồ hai trục trạng thái

~~~text
Trục thực thi (JVM):
Thread NEW -> RUNNABLE <-> WAITING/TIMED_WAITING/BLOCKED -> TERMINATED

Trục nghiệp vụ (do ứng dụng định nghĩa):
Job PENDING -> RUNNING -> SUCCEEDED
                      \-> FAILED
                      \-> CANCEL_REQUESTED -> CANCELLED

Một job có thể đổi thread/attempt; một thread có thể đổi job.
Không có phép biến đổi tự động từ trục JVM sang trục nghiệp vụ.
~~~

Khi cần trạng thái timeout, cancellation hoặc retry có độ tin cậy, hãy cập nhật business state thông qua các bước nhất quán, có guard điều kiện; đừng kiểm tra Thread.State rồi tự động phỏng đoán job outcome.

## 10. Nhớ đúng về happens-before và công bố kết quả

Nếu một worker cập nhật các trường chia sẻ rồi kết thúc, **Thread.join()** trả về do thread kết thúc cung cấp quan hệ *happens-before* từ các hành động của worker đến hành động tiếp theo của thread đã join. Điều này giúp thread gọi đọc kết quả sau khi job hoàn thành.

Ngoài ra:

- **Thread.start()** thiết lập quan hệ happens-before từ các hành động của thread gọi trước start() đến hành động trong thread được khởi động.
- **CountDownLatch.countDown()** cùng **await()** thành công cho phép công bố kết quả trước tín hiệu.
- **AtomicReference** cung cấp các thao tác đọc/ghi/CAS an toàn tương ứng với hợp đồng bộ nhớ của lớp atomic.
- **volatile** và **synchronized** có hợp đồng visibility/happens-before, nhưng cần thiết kế đúng phạm vi dữ liệu được chia sẻ.

Không nên nghĩ **Thread.sleep()**, **Thread.yield()**, hoặc chỉ kiểm tra **getState()** tạo ra quan hệ happens-before cho dữ liệu nghiệp vụ. Quan sát “dường như chạy đúng” qua nhiều lần thử không chứng minh một giao thức race-free.

Mặt khác, **join()** chỉ chờ **thread**. Nếu worker chỉ đặt một task vào queue hoặc kích hoạt bước bất đồng bộ rồi kết thúc, join() của worker ấy không nói toàn bộ job nghiệp vụ đã xong.

## 11. Phân biệt trạng thái quan sát với nguồn sự thật

Một hệ thống thường có ít nhất ba lớp thông tin:

1. **Thread.State**: snapshot kỹ thuật, phù hợp thread dump, chẩn đoán BLOCKED/WAITING và phân tích nghẽn.
2. **Task execution outcome**: giá trị hoặc exception của Future, latch completion, sự kiện từ worker; liên quan một lần chạy cụ thể.
3. **Business state**: kết quả nghiệp vụ chính thức theo hợp đồng (có thể được lưu bền vững), bao gồm retry, cancellation, timeout, xử lý bù trừ.

Khi cần hiển thị cho người dùng, API nên trả về **business state** với **jobId** và thông tin lỗi an toàn; không đưa Thread.State làm trạng thái đơn hàng, xử lý dữ liệu hoặc transaction.

Đối với job chạy lâu hoặc cần sống sót qua restart, **status chỉ nằm trong AtomicReference sẽ mất khi process thoát**. Cần lưu trạng thái theo transaction/định dạng phù hợp và giải quyết tình huống crash giữa “đã làm side effect” và “đã cập nhật trạng thái”. Thiết kế idempotency, transaction boundary và retry có kiểm soát để tránh thực hiện nghiệp vụ trùng lặp. Những vấn đề này độc lập với việc JVM đang báo Thread.State nào.

### Một bảng log hữu ích

Thay vì chỉ log:

~~~text
thread=worker-1 state=RUNNABLE
~~~

hãy cân nhắc log sự kiện ở tầng task, chẳng hạn:

~~~text
jobId=import-842 attempt=2 status=RUNNING step=VALIDATING
jobId=import-842 attempt=2 status=FAILED reason=INVALID_INPUT
~~~

Các dòng trên là **ví dụ cấu trúc log**, không phải kết quả của một chương trình cụ thể. Một log vận hành có thể bổ sung timestamp, worker/thread name và correlationId. Không dùng thứ tự log từ các thread như một chứng cứ tuyệt đối về happens-before khi không có đồng bộ hóa.

## 12. Các lỗi tư duy thường gặp

| Suy luận sai | Cách hiểu đúng |
| --- | --- |
| **Thread.State.RUNNABLE** tức là job đang RUNNING | RUNNABLE chỉ là trạng thái lịch chạy của thread; một thread có thể đang làm nhiều nhiệm vụ khác nhau |
| **Thread.State.WAITING** tức là job nghiệp vụ đang PENDING | Job RUNNING vẫn có thể đợi latch, condition hoặc kết quả I/O |
| **Thread.State.TERMINATED** tức là SUCCEEDED | Thread có thể kết thúc vì exception, hủy hoặc chỉ hoàn tất việc gửi task khác |
| **Thread.sleep()** chứng minh job đã đợi đủ, nên mark SUCCESS | Sleep chỉ tạm dừng thread; không chứng minh side effect hay điều kiện nghiệp vụ |
| **Future.isDone()** tức là SUCCEEDED | Future done bao gồm cả thất bại và hủy |
| **Future.get(timeout)** timeout nghĩa là worker đã dừng | Timeout của caller không tự cancel task đang chạy |
| Interrupt đã gửi nghĩa là job CANCELLED | Interrupt là tín hiệu hợp tác, cancellation cần luật xác nhận |
| Một worker thread tương đương một job | Thread pool tái sử dụng worker; job có thể có nhiều attempt |
| **volatile status** đủ ngăn hai worker cùng nhận job | volatile bảo đảm visibility, không nguyên tử hóa check-then-set |
| **AtomicReference** đủ bảo vệ job trong nhiều JVM | AtomicReference chỉ đồng bộ hóa trong một process; cần cơ chế ở kho dữ liệu |
| Kiểm tra **getState()** trong vòng lặp là một cách chờ chắc chắn | getState() là snapshot; dùng join, Future, latch hoặc giao thức trạng thái có đồng bộ hóa |
| **FAILED** rồi retry nên có thể ghi SUCCESS bất kỳ lúc nào | Cần quản lý version/attempt và transition hợp lệ để tránh kết quả cũ ghi đè |

## 13. Tự kiểm tra

**Câu 1.** Một thread đang chờ **CountDownLatch.await()**. Vì sao công việc vẫn có thể là RUNNING?  
**Trả lời:** Thread đang ở một điểm chờ kỹ thuật để tiếp tục giai đoạn đang chạy. RUNNING là nhãn nghiệp vụ cho toàn bộ giai đoạn, không phải ảnh chụp sử dụng CPU.

**Câu 2.** Worker đã TERMINATED, vậy kết quả nghiệp vụ chắc chắn là gì?  
**Trả lời:** Không xác định chỉ từ Thread.State. Cần biết worker đã trả kết quả, thất bại, bị hủy hay đã giao việc cho giai đoạn khác.

**Câu 3.** Hai thread cùng nhận một job PENDING bằng check-then-set thường có rủi ro gì?  
**Trả lời:** Cả hai có thể đọc PENDING và đều thực thi. Dùng cập nhật có điều kiện nguyên tử như CAS trong một JVM; nếu có nhiều tiến trình phải có điều kiện và transaction ở hệ thống lưu trữ.

**Câu 4.** **Future.isDone() == true** có nghĩa công việc SUCCEEDED không?  
**Trả lời:** Không. Future cũng hoàn tất khi computation lỗi hoặc bị hủy. Kiểm tra kết quả của get() và áp dụng luật nghiệp vụ.

**Câu 5.** **Future.get(1, TimeUnit.SECONDS)** ném TimeoutException có chứng minh worker đã bị dừng?  
**Trả lời:** Không. Đó là việc người chờ đã hết thời gian; computation có thể vẫn chạy.

**Câu 6.** Khi nào nên dùng Thread.getState(), khi nào nên đọc JobStatus?  
**Trả lời:** getState() dùng để quan sát/chẩn đoán vòng đời thread tại một thời điểm; JobStatus dùng để biết tiến độ và kết quả công việc theo hợp đồng ứng dụng.

**Câu 7.** Vì sao trạng thái nghiệp vụ lưu trong bộ nhớ chưa đủ cho job cần chạy lại sau crash?  
**Trả lời:** Trạng thái biến mất cùng JVM, không tự đảm bảo transaction hay tránh xử lý trùng. Cần nơi lưu bền vững, quy tắc transition và idempotency.

## 14. Kết luận

**Thread.State trả lời “luồng thực thi đang thế nào?”; business state trả lời “công việc đã đi đến đâu và kết quả ra sao?”** Hai trạng thái có thể diễn tiến độc lập. Hãy dùng **Thread.getState()** để quan sát/chẩn đoán, dùng **join()/Future/latch** để chờ và thu kết quả thực thi, và dùng **state machine nghiệp vụ** có đồng bộ hóa/transaction tương ứng để xác định trạng thái thực sự của công việc.
