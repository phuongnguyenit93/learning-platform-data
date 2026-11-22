# API điều khiển luồng cũ và cách chuyển sang dừng tác vụ có phối hợp

Khi nâng một ứng dụng Java lâu năm, những đoạn mã dùng các API điều khiển luồng cũ thường là rủi ro lớn hơn lỗi biên dịch. Một ứng dụng có thể vẫn chạy nhưng gặp deadlock, mất dữ liệu, bỏ dở giao dịch hoặc rò rỉ tài nguyên khi luồng bị dừng ở một thời điểm bất kỳ. Những vấn đề này dễ xuất hiện ở hệ thống xử lý nền, worker đọc hàng đợi, scheduler, crawler, ứng dụng desktop và server vốn tự quản lý Thread từ nhiều năm trước.

Trong chủ đề **Java Advance Compatibility Migration**, chương **API và công cụ cũ**, bài học này giải thích vì sao các thao tác như Thread.stop, Thread.suspend và Thread.resume không còn phù hợp; cách thay thế bằng **cooperative cancellation** (hủy/dừng tác vụ có phối hợp), interrupt, tín hiệu dừng, Future, ExecutorService và cơ chế shutdown có thời hạn; đồng thời trình bày cách giữ dữ liệu, tài nguyên và hợp đồng vận hành ổn định khi migration.

Mục tiêu không phải là đổi mỗi lời gọi stop thành interrupt. Mục tiêu là biến việc kết thúc tác vụ thành một **giao thức rõ ràng giữa bên yêu cầu dừng và code đang thực thi tác vụ**.

## 1. Phân biệt luồng, tác vụ và vòng đời dịch vụ

Ba khái niệm rất dễ bị trộn lẫn:

- **Thread:** đơn vị thực thi mà JVM lên lịch. Thread có thể là platform thread hoặc virtual thread ở các Java release hỗ trợ.
- **Task:** đơn vị công việc như xử lý một đơn hàng, tải một file, tiêu thụ một message hoặc đồng bộ một batch.
- **Service/worker:** thành phần có vòng đời dài hơn, quản lý nhiều task, thread, connection và tài nguyên.

Dừng một task không nhất thiết phải kết thúc thread đang chạy nó. Ngược lại, dừng thread không bảo đảm task đã hoàn tất cleanup hoặc transaction rollback.

Ví dụ:

~~~text
Shutdown request
        |
        v
Không nhận công việc mới
        |
        v
Đợi công việc đang chạy hoàn tất
        |
        +--> Quá thời hạn? --> Yêu cầu cancel / interrupt
        |                             |
        |                             v
        |                        Cleanup, rollback
        |                             |
        +-----------------------------+
        |
        v
Đóng connection, executor, resource
        |
        v
Báo đã dừng
~~~

Một cơ chế dừng an toàn cần nêu rõ **khi nào không nhận việc mới**, **công việc đang chạy được xử lý thế nào**, **ai yêu cầu hủy**, **task nhận và phản hồi hủy ra sao**, và **khi nào có thể xác nhận service đã dừng**.

## 2. Các API điều khiển Thread cũ và vấn đề an toàn

### 2.1. Thread.stop

Code lịch sử có thể chứa:

~~~java
Thread worker = new Thread(() -> runBatch());
worker.start();

// Mã legacy — không dùng làm cách dừng an toàn
worker.stop();
~~~

Thread.stop đã bị deprecated vì **không an toàn**. Theo cơ chế lịch sử, thao tác dừng bất đồng bộ có thể khiến luồng đang thực hiện công việc bị kết thúc thông qua một dạng lỗi bất thường, làm các monitor đang giữ được giải phóng trong khi trạng thái shared object chưa nhất quán.

Giả sử luồng đang cập nhật hai trường phải luôn khớp nhau:

~~~java
synchronized (account) {
    account.debit(100);
    account.recordTransfer(transferId);
}
~~~

Nếu luồng bị dừng đột ngột giữa hai thao tác, một thread khác có thể thấy trạng thái chỉ cập nhật được một phần. Việc monitor được nhả không làm trạng thái nghiệp vụ tự phục hồi.

Những hậu quả có thể gồm:

- Invariant của object bị phá vỡ.
- Dữ liệu đang ghi ra file bị dở dang.
- Một batch đánh dấu hoàn thành sai.
- Một resource không được đóng theo luồng nghiệp vụ dự kiến.
- Transaction hoặc protocol state không còn đúng.
- Các thread khác đọc được trạng thái nửa chừng.

Tùy phiên bản JDK, những phương thức legacy có thể đã bị vô hiệu hóa hoặc có hành vi khác thời kỳ ban đầu; một số lời gọi có thể ném UnsupportedOperationException. **Không dựa vào việc chúng còn xuất hiện trong API để kết luận chúng phù hợp cho migration.**

### 2.2. Thread.suspend và Thread.resume

Ví dụ legacy:

~~~java
worker.suspend();
performMaintenance();
worker.resume();
~~~

Thread.suspend có thể tạm ngưng luồng **trong khi nó đang giữ monitor/lock**. Nếu thread khác, kể cả thread gọi resume, cần monitor đó để tiếp tục, hệ thống có thể deadlock.

Bên cạnh đó, việc điều khiển một luồng bất kỳ từ bên ngoài không thể xác định chắc luồng đang ở safe point về mặt nghiệp vụ. Đối với nhu cầu pause/resume, cần thiết kế một giao thức tạm dừng có phối hợp, không sử dụng phương thức suspend/resume cũ.

### 2.3. ThreadGroup.stop và các biến thể tương tự

Một số codebase cũ dừng toàn bộ ThreadGroup bằng API điều khiển thread theo nhóm. Rủi ro của việc dừng bất đồng bộ vẫn tồn tại, thậm chí khó khoanh vùng hơn vì nhiều luồng cùng bị tác động.

Không nên thay bằng cách lặp qua ThreadGroup rồi gọi Thread.stop trên từng thread. Cần chuyển sang quản lý **task ownership**, executor lifecycle và cancellation token.

### 2.4. Không nhầm với những API hợp lệ

Thread.interrupt, Thread.join, Thread.sleep và các API concurrency hiện đại không cùng nhóm với stop/suspend/resume. Chúng có mục đích khác nhau. interrupt thường là **tín hiệu yêu cầu hợp tác dừng hoặc đánh thức một thao tác blocking**, không phải cưỡng chế kết thúc execution.

## 3. Vì sao dừng cưỡng bức là sai mô hình?

Dừng cưỡng bức không trả lời được các câu hỏi mà dữ liệu nghiệp vụ cần:

1. Thao tác nào đang thực hiện?
2. Có thể dừng ngay hay phải hoàn thành một đơn vị công việc?
3. Trạng thái đã commit hay chưa?
4. Có phải trả message vào queue hay đánh dấu retry không?
5. Có cần đóng network connection, file, stream hoặc transaction không?
6. Có thread khác đang chờ kết quả không?
7. Ai chịu trách nhiệm xác nhận task đã hoàn tất việc dừng?

Một ví dụ xử lý message:

~~~text
Nhận message
     |
     v
Đọc payload
     |
     v
Ghi database
     |
     v
Commit transaction
     |
     v
Acknowledgement cho broker
~~~

Nếu kết thúc luồng ngay sau khi ghi database nhưng trước acknowledgement, message có thể được gửi lại. Nếu ứng dụng không có idempotency, dữ liệu có thể bị ghi hai lần. Nếu kết thúc trước commit nhưng lại acknowledgement trước, message có thể bị mất.

Vì vậy, **ngữ nghĩa của cancellation phải gắn với ranh giới nghiệp vụ**: hủy trước khi bắt đầu, hủy giữa các đơn vị công việc, rollback một đơn vị chưa commit, hay yêu cầu hoàn tất đơn vị hiện tại trước khi dừng.

## 4. Cooperative cancellation là gì?

Cooperative cancellation là mô hình trong đó:

- Một chủ thể có quyền yêu cầu hủy, ví dụ server, supervisor hoặc người dùng.
- Yêu cầu hủy được truyền đến task qua interrupt, trạng thái hoặc cancellation token.
- Task thường xuyên kiểm tra yêu cầu ở những **điểm an toàn**.
- Task tự quyết định cleanup, rollback hoặc hoàn tất phần việc không thể chia nhỏ.
- Chủ thể yêu cầu dừng đợi trong giới hạn thời gian đã định.
- Kết quả dừng được ghi nhận là completed, cancelled, timed out hoặc failed.

Điểm quan trọng: **hủy là một giao thức, không phải một lệnh giết luồng**.

Một giao thức đơn giản:

~~~text
RUNNING
   |
   | requestCancel()
   v
CANCELLING
   |
   +--> Kiểm tra tín hiệu
   +--> Dừng lấy việc mới
   +--> Hoàn thành/rollback đơn vị hiện tại
   +--> Đóng tài nguyên
   v
CANCELLED / STOPPED
~~~

Ngoài CANCELLED, task có thể kết thúc bình thường thành COMPLETED hoặc thất bại thành FAILED. Một số ứng dụng cần phân biệt hai loại kết thúc này thay vì gom mọi thứ thành “đã dừng”.

### 4.1. Hai tín hiệu thường dùng

**Interrupt:** dùng cơ chế có sẵn của Thread, hữu ích khi task đang sleep, wait, join, dùng BlockingQueue hoặc API interruptible.

**Cờ dừng:** dùng volatile boolean hoặc AtomicBoolean để mô tả intent như stopRequested; hữu ích với vòng lặp CPU-bound hoặc tác vụ cần ngừng nhận công việc mới ở ranh giới rõ ràng.

Hai cơ chế có thể kết hợp. Một cờ truyền ý định của service, còn interrupt giúp đánh thức thread đang chờ.

## 5. Hiểu đúng Thread.interrupt

Lời gọi:

~~~java
worker.interrupt();
~~~

không “giết” worker. Nó đưa ra tín hiệu interruption. Điều xảy ra tiếp theo phụ thuộc trạng thái của thread và code bên trong.

- Nếu thread đang chạy một vòng lặp CPU bình thường, nó phải tự kiểm tra interrupt status hoặc phương thức kiểm tra tương đương.
- Nếu thread đang trong một số thao tác chờ interruptible, nó có thể nhận InterruptedException.
- Nếu thread đang chạy đoạn I/O hoặc thư viện không hỗ trợ interruption, yêu cầu có thể không làm nó dừng ngay.
- Nếu task cố tình bắt và bỏ qua interruption, task có thể tiếp tục chạy.

### 5.1. isInterrupted và interrupted

Hai API có khác biệt quan trọng:

~~~java
boolean flag = Thread.currentThread().isInterrupted();
~~~

isInterrupted **kiểm tra** trạng thái mà không chủ động xóa flag.

Trong khi đó:

~~~java
boolean wasInterrupted = Thread.interrupted();
~~~

Thread.interrupted là phương thức static, kiểm tra interrupt status của **thread hiện tại** và **xóa flag** theo semantics của API.

Không nên dùng Thread.interrupted trong vòng lặp nếu vô tình làm mất thông tin cancellation cần được truyền lên các tầng xử lý khác.

### 5.2. InterruptedException và khôi phục trạng thái

Nhiều blocking API ném InterruptedException khi thread bị interrupt. Với nhiều API, trạng thái interruption được xóa khi exception được ném. Do đó, nếu method không có cách nào truyền InterruptedException lên caller, cách xử lý phổ biến là khôi phục flag:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Khôi phục flag giúp tầng gọi phía trên còn nhận biết được yêu cầu interrupt.

Nhưng không phải lúc nào cũng phải catch để khôi phục ngay. Nếu method có thể khai báo throws InterruptedException, **truyền exception lên** thường sạch hơn:

~~~java
public void waitForWork() throws InterruptedException {
    Thread.sleep(1000);
}
~~~

Bên sở hữu task sẽ quyết định hoàn tất cancellation, cleanup và cách báo trạng thái.

## 6. Ví dụ cơ bản: thay Thread.stop bằng interrupt

Code nguy hiểm kiểu cũ:

~~~java
Thread worker = new Thread(() -> {
    while (true) {
        performWork();
    }
});

worker.start();

// Legacy: không nên dùng
worker.stop();
~~~

Thiết kế phối hợp:

~~~java
public final class PollingWorker implements Runnable {
    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                fetchAndProcessOneItem();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            closeOwnedResources();
        }
    }

    private void fetchAndProcessOneItem() throws InterruptedException {
        // Ví dụ chờ một khoảng giữa các lượt polling.
        Thread.sleep(200);
        // Xử lý một đơn vị công việc, có điểm dừng phù hợp.
    }

    private void closeOwnedResources() {
        // Cleanup tài nguyên do worker sở hữu.
    }
}
~~~

Khởi động và yêu cầu dừng:

~~~java
Thread worker = new Thread(new PollingWorker(), "polling-worker");
worker.start();

// Khi shutdown:
worker.interrupt();
worker.join(5000);

if (worker.isAlive()) {
    System.err.println("Worker chưa dừng sau giới hạn chờ");
}
~~~

Trong ví dụ, join(5000) là một phép chờ có timeout, **không phải lệnh kết thúc thread sau năm giây**. Nếu worker vẫn sống, caller phải có chính sách tiếp theo như theo dõi, đóng resource phù hợp, hoặc báo lỗi shutdown; không quay lại Thread.stop.

### 6.1. Khi nào ví dụ cần bổ sung?

Đoạn mẫu chỉ minh họa interrupt và cleanup. Trong ứng dụng thực tế:

- fetchAndProcessOneItem phải thật sự interruptible hoặc kiểm tra cancellation ở điểm thích hợp.
- Một đơn vị công việc chưa commit phải rollback hoặc có idempotency.
- closeOwnedResources cần xử lý exception có thể xảy ra.
- Thread owner phải kiểm soát việc gọi start, interrupt và join.
- Nếu caller cũng nhận InterruptedException khi join, caller cần thực hiện chính sách cancellation của mình.

## 7. Dừng vòng lặp CPU-bound

Một vòng lặp tính toán không gọi blocking API nên không tự dừng chỉ vì interrupt được gửi.

Ví dụ:

~~~java
public long countMatches(long limit) {
    long matches = 0;

    for (long i = 0; i < limit; i++) {
        if ((i & 1023) == 0 &&
                Thread.currentThread().isInterrupted()) {
            break;
        }

        if (isMatch(i)) {
            matches++;
        }
    }

    return matches;
}
~~~

Ở đây, task kiểm tra interrupt định kỳ thay vì ở mọi phép lặp. Tần suất kiểm tra là đánh đổi giữa overhead và cancellation latency.

Tuy nhiên, việc trả về một kết quả count chưa đầy đủ có thể bị consumer hiểu nhầm là hoàn thành bình thường. Nếu hợp đồng yêu cầu phân biệt, hãy ném CancellationException, trả về một kết quả có trạng thái partial/cancelled, hoặc tách trạng thái cancellation khỏi giá trị kết quả.

Ví dụ với exception:

~~~java
private static void checkCancelled() {
    if (Thread.currentThread().isInterrupted()) {
        throw new java.util.concurrent.CancellationException(
            "Computation was cancelled");
    }
}
~~~

Không dùng CancellationException để thay cho rollback tự động; đây chỉ là cách thông báo trạng thái không hoàn thành.

## 8. Cancellation token với volatile hoặc AtomicBoolean

Interrupt là tín hiệu cấp thread. Khi một công việc sử dụng nhiều helper, hoặc cần biểu đạt chính sách dừng riêng của service, cancellation token là một lựa chọn phù hợp.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean cancelled = new AtomicBoolean();

    public void cancel() {
        cancelled.set(true);
    }

    public boolean isCancelled() {
        return cancelled.get();
    }
}
~~~

Task nhận token:

~~~java
public void processBatch(
        java.util.List<String> items,
        CancellationToken token) {

    for (String item : items) {
        if (token.isCancelled()) {
            return;
        }
        processOne(item);
    }
}
~~~

AtomicBoolean cung cấp visibility và atomic access phù hợp cho flag. Nếu chỉ có một writer và nhiều reader, volatile boolean cũng có thể đủ cho intent dừng đơn giản.

### 8.1. Hạn chế của token đơn thuần

Cờ dừng không tự đánh thức một thread đang ngủ hoặc chờ vô hạn:

~~~java
while (!token.isCancelled()) {
    queue.take(); // Có thể block mãi nếu queue không có dữ liệu.
}
~~~

Trong tình huống đó, có thể kết hợp:

- Cờ stopRequested và Thread.interrupt.
- Poll có timeout được chấp nhận.
- Một signal/sentinel message theo giao thức của queue.
- Đóng resource hoặc đánh thức wait/condition nếu API hỗ trợ.

Không dùng busy-wait liên tục chỉ để kiểm tra cờ, vì có thể gây tiêu thụ CPU cao.

## 9. Ví dụ BlockingQueue: tránh bị kẹt khi shutdown

BlockingQueue.take là operation interruptible. Một worker có thể viết:

~~~java
import java.util.concurrent.BlockingQueue;

public final class QueueWorker implements Runnable {
    private final BlockingQueue<Runnable> queue;

    public QueueWorker(BlockingQueue<Runnable> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                Runnable job = queue.take();
                job.run();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            releaseWorkerResources();
        }
    }

    private void releaseWorkerResources() {
        // Cleanup nếu worker có tài nguyên riêng.
    }
}
~~~

Khi interrupt được gửi trong lúc queue.take đang chờ, nó có thể ném InterruptedException để worker đi tới cleanup.

Nhưng nếu job.run() kéo dài và không hợp tác, worker vẫn không dừng đúng hạn. Queue có khả năng interruptible **không bảo đảm mọi job trong queue đều interruptible**.

### 9.1. Hủy trước khi nhận job và hủy khi đang chạy job

Hai chính sách cần tách:

- **Stop accepting:** Không lấy thêm job từ queue.
- **Cancel in-flight:** Yêu cầu job đang chạy ngừng ở điểm an toàn.

Một service nhận thông điệp từ broker có thể cần hoàn tất và acknowledge job đang chạy, sau đó mới ngừng consume job mới. Không phải lúc nào cũng nên interrupt ngay lập tức.

### 9.2. Poison pill là một lựa chọn, không phải thuốc chữa mọi tình huống

Có hệ thống dùng sentinel object trong queue để yêu cầu worker rời vòng lặp. Cần xác định rõ số worker, số sentinel, bounded capacity, thứ tự xử lý, producer nào còn hoạt động và khả năng queue đầy.

Poison pill có thể hữu ích nếu giao thức queue được kiểm soát; nó không thay thế việc xử lý timeout, thread đang kẹt trong job hoặc transaction chưa hoàn tất.

## 10. Dừng tác vụ quản lý bởi ExecutorService

Khi nhiều task được thực thi cùng nhau, việc tự lưu danh sách Thread và gọi interrupt từng luồng thường phức tạp và dễ sai. ExecutorService giúp tách khái niệm task khỏi thread dùng để chạy task.

Ví dụ:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

ExecutorService executor = Executors.newFixedThreadPool(4);

Future<?> future = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
});
~~~

Để yêu cầu hủy một task:

~~~java
boolean accepted = future.cancel(true);
~~~

Ý nghĩa quan trọng của cancel(true):

- Hệ thống cố hủy task nếu nó chưa hoàn tất.
- Nếu task đang chạy, có thể interrupt thread thực thi task theo chính sách Future.
- Task vẫn phải hợp tác với interruption để dừng nhanh và dọn dẹp tài nguyên.
- Kết quả boolean không nên được hiểu là “toàn bộ cleanup đã hoàn tất”.

Nếu task đang ở đoạn native call, I/O không interruptible hoặc code cố tình bỏ qua flag, nó có thể tiếp tục chạy một thời gian.

### 10.1. cancel(false) khác gì?

cancel(false) yêu cầu hủy mà không chủ động interrupt thread đang thực thi. Điều này hữu ích khi không muốn tác động trực tiếp vào một đơn vị công việc đã bắt đầu, nhưng cũng không bảo đảm task đang chạy sẽ lập tức dừng.

Chính sách dùng true hay false phải dựa vào khả năng idempotency, transaction boundary và tính interruptible của task.

### 10.2. Sau cancellation, lấy kết quả thế nào?

Future.get có thể ném CancellationException đối với một future đã bị hủy. Những lỗi thường gặp khác gồm InterruptedException của thread đang chờ và ExecutionException nếu task thất bại.

Không nên code như thể một task đã cancel sẽ luôn trả về kết quả hoàn chỉnh.

~~~java
try {
    future.get();
} catch (java.util.concurrent.CancellationException e) {
    System.out.println("Task đã được yêu cầu hủy");
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Task thất bại: " + e.getCause());
}
~~~

Nếu caller cần biết cleanup của task đã thực sự xong, cần một cơ chế đồng bộ hoặc trạng thái lifecycle bổ sung phù hợp, thay vì chỉ suy diễn từ future bị đánh dấu canceled.

## 11. Graceful shutdown: shutdown, awaitTermination và shutdownNow

ExecutorService có một bộ API quản lý vòng đời:

| API | Ý nghĩa |
|---|---|
| shutdown() | Không chấp nhận task mới; để các task đã submit tiếp tục xử lý |
| awaitTermination(timeout, unit) | Đợi executor kết thúc trong thời gian giới hạn |
| shutdownNow() | Cố ngừng task đang chạy bằng interruption và trả về các task đang chờ chưa bắt đầu |
| isShutdown() | Executor đã nhận yêu cầu shutdown |
| isTerminated() | Các task đã kết thúc sau shutdown theo điều kiện executor |

Một trình tự phổ biến là:

1. Stop accepting new work.
2. Gọi shutdown.
3. Đợi graceful trong một thời hạn.
4. Nếu hết hạn, yêu cầu hủy mạnh hơn bằng shutdownNow.
5. Đợi thêm trong thời hạn nhỏ.
6. Nếu vẫn chưa dừng, ghi nhận tình trạng và thực hiện chính sách vận hành.

Ví dụ Java:

~~~java
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ShutdownSupport {
    public static void stopExecutor(ExecutorService executor) {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
                List<Runnable> notStarted = executor.shutdownNow();

                System.err.println(
                    "Tasks chưa bắt đầu: " + notStarted.size());

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println(
                        "Một số task vẫn chưa hoàn tất sau yêu cầu hủy");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đoạn này là cấu trúc shutdown minh họa. Thời hạn 20 và 5 giây không phải giá trị khuyến nghị chung; cần chọn theo SLA, thời lượng task, transaction và yêu cầu hệ thống.

### 11.1. shutdownNow không phải Thread.stop

Tên có thể gây hiểu lầm. shutdownNow **cố gắng** kết thúc các tác vụ đang thực thi, chủ yếu bằng interruption trong nhiều ExecutorService implementation. Không có bảo đảm tác vụ không hợp tác sẽ dừng ngay.

Khi task chạy network I/O đặc biệt hoặc vòng lặp không kiểm tra interrupt, executor có thể không đạt trạng thái terminated.

### 11.2. Khi nào dùng shutdown trước, khi nào cancel trước?

- Với dịch vụ giao dịch, thường ưu tiên ngừng nhận việc mới rồi drain in-flight theo thời hạn.
- Với một tác vụ tìm kiếm có thể bỏ kết quả, có thể cancel nhanh khi người dùng hủy.
- Với batch dài, có thể thiết kế checkpoint để tiếp tục sau restart.
- Với thao tác quan trọng cần atomicity, hãy hoàn thành/rollback đơn vị công việc trước khi xác nhận shutdown.

Không nên dùng một logic dừng chung cho mọi loại task mà không mô tả nghĩa vụ của từng nhóm.

## 12. CompletableFuture và sự khác biệt về cancellation

CompletableFuture hỗ trợ cancel, nhưng **không nên giả định cancel(true) sẽ interrupt thread đang chạy supplier** theo cách của FutureTask trong ExecutorService.

Trong implementation chuẩn của CompletableFuture, tham số mayInterruptIfRunning không điều khiển trực tiếp việc interrupt computation đang chạy. Việc future chuyển sang trạng thái cancelled không có nghĩa lambda đang thực thi đã dừng.

Ví dụ:

~~~java
java.util.concurrent.CompletableFuture<String> future =
    java.util.concurrent.CompletableFuture.supplyAsync(() -> {
        return slowOperation();
    });

future.cancel(true);
~~~

slowOperation vẫn có thể tiếp tục chạy. Nếu ứng dụng cần hủy công việc thực sự, phải thiết kế cancellation token, ownership của task/executor hoặc một cơ chế hỗ trợ interruption tương ứng.

Với một chuỗi CompletableFuture, cũng cần xác định hủy có lan tới upstream, downstream và side effect không. Không nên xem trạng thái của một future đơn lẻ là trạng thái toàn bộ workflow.

## 13. I/O và những thao tác không đáp ứng interrupt ngay

Không phải blocking operation nào cũng có cùng semantics interruption. Có API ném InterruptedException; có API liên quan interruptible channel; có API hoặc native library không phản hồi kịp thời.

Một task làm HTTP request, database query hoặc đọc socket có thể cần thêm:

- Connect timeout.
- Read/socket timeout.
- Request deadline.
- Cơ chế cancel/close riêng của client library.
- Đóng resource ở đúng thời điểm.
- Transaction timeout.
- Retry policy và idempotency.

Ví dụ với socket truyền thống:

~~~java
try (java.net.Socket socket = new java.net.Socket()) {
    socket.connect(
        new java.net.InetSocketAddress("example.org", 443),
        3000
    );

    socket.setSoTimeout(5000);
    // Đọc dữ liệu qua socket.getInputStream() trong giới hạn phù hợp.
}
~~~

connect timeout và read timeout có mục đích khác nhau. Cần áp dụng timeout ở cấp protocol/client phù hợp với nghiệp vụ, không coi chúng là thay thế trực tiếp cho interruption.

### 13.1. Đóng resource có thể giúp unblock

Với một số API, đóng socket, channel hoặc stream từ luồng có quyền sở hữu phù hợp có thể đánh thức operation đang block. Nhưng hành vi cụ thể phụ thuộc API và nhà cung cấp; phải xác minh bằng integration test.

Không nên dùng Thread.stop vì một thư viện I/O không hỗ trợ interrupt. Cần xem API cancel/timeout của chính thư viện hoặc cô lập tác vụ trong một tiến trình có thể kiểm soát nếu yêu cầu rất nghiêm ngặt.

### 13.2. Một deadline end-to-end quan trọng hơn nhiều timeout rời rạc

Nếu một request đi qua ba dịch vụ, đặt mỗi lần chờ 30 giây có thể khiến toàn bộ flow kéo dài quá SLA. Nên thiết kế deadline tổng và truyền thời gian còn lại cho từng thao tác.

Cancellation token có thể chứa deadline hoặc được kết hợp với deadline checker. Điều này cho phép task tự từ chối bắt đầu một bước mới khi ngân sách thời gian không còn đủ.

## 14. Giữ invariant, transaction và cleanup

Điểm khó nhất của cooperative cancellation là chọn ranh giới dừng an toàn. Cần quyết định task có thể dừng ngay hay phải hoàn thành một transaction hoặc một đơn vị công việc trước.

Ví dụ:

~~~java
public void processOrder(Order order)
        throws InterruptedException {

    checkInterrupted();

    // Bắt đầu đơn vị công việc có ranh giới giao dịch rõ ràng.
    try {
        reserveInventory(order);
        createPaymentIntent(order);
        commitOrder(order);
    } catch (RuntimeException e) {
        compensateIfNecessary(order);
        throw e;
    }

    checkInterrupted();
}
~~~

Ví dụ là pseudocode về workflow; các method reserveInventory, createPaymentIntent, commitOrder và compensateIfNecessary phải được thiết kế thực tế theo database/external service. Trong distributed systems, compensation không giống một transaction rollback tự động.

### 14.1. Không check cancellation ở điểm làm vỡ invariant

Nếu một transaction phải hoàn thành hai thao tác như một đơn vị atomic, việc check giữa hai bước có thể tạo trạng thái nửa vời. Hãy xác định safe point trước/sau transaction hoặc rollback được nếu cancellation xảy ra giữa chừng.

### 14.2. finally và try-with-resources

Đặt cleanup trong finally hoặc try-with-resources khi phù hợp:

~~~java
public void handleFile(java.nio.file.Path path)
        throws java.io.IOException {

    try (java.io.InputStream input =
            java.nio.file.Files.newInputStream(path)) {
        // Xử lý input.
    }
}
~~~

Trong task có cancellation, code cần bảo đảm resource được đóng ngay cả khi bị InterruptedException hoặc CancellationException. Nếu cleanup có thao tác blocking, phải có chính sách rõ về timeout và interrupt status để tránh kẹt vô hạn trong shutdown.

### 14.3. Không nuốt interruption trong cleanup

Nếu catch InterruptedException rồi chỉ log và tiếp tục toàn bộ vòng lặp, thread mất tín hiệu cancellation.

Code dễ sai:

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException e) {
    System.err.println("Ignored");
}
~~~

Hướng xử lý tốt hơn:

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Nếu method có thể propagate InterruptedException, nên khai báo throws và để owner xử lý ở cấp cao phù hợp.

## 15. Lock, wait và điều kiện đồng bộ

Không phải mọi tình huống chờ lock đều interruptible giống nhau.

### 15.1. Synchronized monitor

Khi một thread đang **chờ giành monitor để vào synchronized**, interrupt không nhất thiết làm nó thoát ngay khỏi trạng thái chờ monitor đó.

Vì vậy, thay Thread.stop bằng interrupt trong một thiết kế khóa bị deadlock không tự giải quyết vấn đề. Cần sửa lock ordering, giảm critical section hoặc chuyển sang primitive có cơ chế chờ interruptible nếu phù hợp.

### 15.2. ReentrantLock.lockInterruptibly

java.util.concurrent.locks.ReentrantLock cung cấp cách chờ lock có thể phản hồi interrupt:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class InventoryGuard {
    private final ReentrantLock lock = new ReentrantLock();

    public void update() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            performCriticalUpdate();
        } finally {
            lock.unlock();
        }
    }

    private void performCriticalUpdate() {
        // Cập nhật dữ liệu trong critical section.
    }
}
~~~

Nếu thread bị interrupt khi đang chờ lockInterruptibly, nó có thể nhận InterruptedException thay vì chờ vô hạn. Lưu ý: sau khi đã giữ lock, code vẫn phải bảo đảm invariant và unlock trong finally.

### 15.3. Condition.await, Object.wait và Thread.join

Các phương thức chờ interruptible thường ném InterruptedException. Dù vậy, thread chờ phải có điều kiện vòng lặp đúng và code đánh thức phù hợp.

Với Condition:

~~~java
lock.lockInterruptibly();
try {
    while (!ready && !cancelled) {
        condition.await();
    }
} finally {
    lock.unlock();
}
~~~

ready, cancelled và condition là state thuộc cùng cơ chế đồng bộ trong ví dụ. Việc kiểm tra điều kiện trong vòng while là quan trọng vì condition wait có thể thức dậy mà điều kiện chưa thỏa.

## 16. Pause/resume có phối hợp thay vì Thread.suspend/resume

Có nghiệp vụ thực sự cần tạm dừng tác vụ rồi tiếp tục: điều tiết tốc độ, pause crawler, tạm dừng tiêu thụ message hoặc bảo trì theo giai đoạn.

Một mô hình an toàn có thể là state machine:

~~~text
RUNNING ----requestPause----> PAUSING
   ^                            |
   |                            | đạt safe point
   |                            v
   +-----requestResume------- PAUSED
   |
   +-----resume/start-----------+

RUNNING / PAUSED ----requestStop----> STOPPING --> STOPPED
~~~

Thread tự chuyển sang PAUSED **sau khi đã rời critical section và hoàn tất đơn vị công việc an toàn**, thay vì bị JVM ngừng ở bất kỳ câu lệnh nào.

Một cách triển khai có thể dùng Lock + Condition hoặc semaphore. Cần đặc biệt chú ý:

- Mọi lần đọc/ghi state đều đồng bộ hoặc có visibility guarantee.
- requestStop đánh thức cả worker đang PAUSED.
- Không gọi chờ Condition khi đang giữ các lock nghiệp vụ khác gây deadlock.
- Resume không được làm mất tín hiệu stop.
- Pause có thể cần timeout/acknowledgement để caller biết worker đã thật sự dừng ở safe point.
- Khi interruption xảy ra, ưu tiên chính sách stop thay vì quay lại PAUSED vô hạn.

Điểm cốt lõi là **pause/resume ở cấp tác vụ**, không suspend/resume ở cấp Thread bất đồng bộ.

## 17. Virtual threads và structured concurrency

Trong những JDK hiện đại, virtual threads cho phép triển khai nhiều tác vụ blocking theo mô hình thread-per-task với chi phí nhẹ hơn ở nhiều workload. Nhưng chúng **không làm thay đổi nguyên tắc cooperative cancellation**.

Ví dụ với Java 21:

~~~java
Thread worker = Thread.startVirtualThread(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doInterruptibleWork();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        cleanup();
    }
});
~~~

Virtual thread cũng cần cleanup, timeout, hợp đồng dừng và khả năng phản hồi interruption. Không nên dùng Thread.stop cho virtual thread hay platform thread.

### 17.1. Structured concurrency

Structured concurrency là một hướng tổ chức tác vụ con theo phạm vi để lifetime và cancellation được quản lý cùng task cha. Một số JDK cung cấp API StructuredTaskScope ở trạng thái preview hoặc đang tiến hóa theo từng release.

Vì API và cú pháp có thể thay đổi giữa các bản JDK, không nên sao chép mã preview giữa các phiên bản một cách máy móc. Trước khi dùng, xác nhận trạng thái tính năng và tài liệu **đúng JDK target**. Điều quan trọng về mô hình là:

- Task cha sở hữu các task con.
- Khi phạm vi kết thúc, lifecycle của tác vụ con được xử lý rõ ràng.
- Failure/cancellation của một task có thể dẫn tới chính sách dừng các task liên quan.
- Không bỏ lại task con chạy vô chủ sau khi caller đã kết thúc.

Những nguyên tắc này vẫn hữu ích ngay cả khi dự án chưa dùng API structured concurrency cụ thể.

## 18. Dừng service theo hai giai đoạn: drain rồi cancel

Một hệ thống server thường không thể dừng toàn bộ công việc ngay tại thời điểm nhận SIGTERM hoặc shutdown request. Phải có thời gian cho những request đã vào hệ thống.

Một chính sách shutdown thực tế:

~~~text
SHUTDOWN_REQUESTED
        |
        v
Mark service not ready
        |
        v
Stop accepting new requests/jobs
        |
        v
Drain in-flight within grace period
        |
     +--+------+
     |         |
  Complete   Timeout
     |         |
     |         v
     |     Interrupt/cancel
     |         |
     |      Cleanup
     +----+----+
          |
          v
Close resources
          |
          v
STOPPED / TIMEOUT_REPORTED
~~~

Nên định nghĩa:

- Grace period tổng.
- Timeout cho từng task.
- Timeout riêng cho database/network.
- Khi nào ngừng readiness nhưng vẫn phục vụ in-flight.
- Ai xử lý request/job chưa hoàn tất.
- Chính sách requeue/retry.
- Deadline của container orchestration/service manager.
- Kết quả cuối cùng được báo cho operator ra sao.

Nếu server có orchestrator như Kubernetes, thời gian shutdown ở JVM phải phù hợp termination grace period của nền tảng; nếu không, JVM có thể bị tiến trình quản lý kết thúc trước khi graceful shutdown hoàn tất.

### 18.1. Không nhận việc mới sau tín hiệu shutdown

Một race phổ biến:

~~~text
Thread A: requestShutdown()
Thread B: submitNewTask()
Thread A: awaitTermination()
~~~

Nếu state chuyển đổi không được đồng bộ, task mới có thể lọt vào sau khi shutdown bắt đầu. ExecutorService từ chối submit sau shutdown theo hợp đồng của nó; ở tầng application cần bảo đảm queue consumer, HTTP handler và scheduler cũng ngừng nhận/đưa việc mới đúng lúc.

## 19. Cơ chế cancellation theo từng nhóm tác vụ

Không có một giải pháp dừng phù hợp cho mọi loại công việc.

| Loại tác vụ | Safe point / phản hồi hủy | Công cụ thường hữu ích |
|---|---|---|
| CPU-bound thuần túy | Kiểm tra flag/interrupt định kỳ | isInterrupted, cancellation token |
| Chờ queue | Thức dậy khi interrupt, hoặc timeout poll | BlockingQueue.take/poll |
| Thread.sleep/wait/join | InterruptedException | interrupt và propagate/restore |
| Xử lý database | Ranh giới transaction, timeout, rollback | Transaction timeout, cancellation API của driver |
| HTTP/network | I/O timeout, cancel request, đóng resource | Client-specific timeout/cancel |
| Xử lý file | Checkpoint giữa chunk, cleanup | try-with-resources, token |
| Batch ETL | Checkpoint giữa record/batch, idempotency | Token, job state, retry |
| Scheduler | Ngừng lập lịch mới, drain task hiện tại | ScheduledExecutorService shutdown policy |
| Plugin | Hợp đồng close/cancel, callback lifecycle | SPI cancellation contract |
| Native/uninterruptible call | Timeout bên ngoài, cô lập tiến trình nếu cần | Process boundary, watchdog |

Bảng chỉ nêu hướng thiết kế. Khả năng phản hồi interrupt của từng API phải kiểm chứng bằng tài liệu và integration test trên JDK/dependency mục tiêu.

## 20. Chuyển từng mẫu mã legacy

### 20.1. Từ stop() trực tiếp

**Trước:**

~~~java
worker.stop();
~~~

**Sau:** truyền quyền sở hữu worker cho một component có requestStop, đặt cờ dừng hoặc gửi interrupt, rồi chờ worker xác nhận shutdown ở safe point. Tránh cho mọi class trong ứng dụng tùy ý gọi interrupt trên thread không do mình sở hữu.

### 20.2. Từ suspend()/resume()

**Trước:**

~~~java
worker.suspend();
worker.resume();
~~~

**Sau:** tạo state PAUSE_REQUESTED/PAUSED và condition. Worker chỉ pause khi không giữ lock quan trọng và có thể cleanup/acknowledge. requestStop phải đánh thức worker đang pause.

### 20.3. Từ vòng lặp while(true) vô hạn

**Trước:**

~~~java
while (true) {
    work();
}
~~~

**Sau:**

~~~java
while (!stopRequested.get() &&
       !Thread.currentThread().isInterrupted()) {
    workOneUnit();
}
~~~

Cần sửa luôn workOneUnit nếu nó có blocking call hoặc giữ transaction quá lâu.

### 20.4. Từ tự quản lý hàng trăm Thread

**Trước:** tự new Thread, lưu danh sách, interrupt từng thread, join thủ công và khó kiểm soát tài nguyên.

**Sau:** dùng ExecutorService hoặc mô hình task scope phù hợp, xác định owner và shutdown policy. Số lượng thread, queue capacity và retry cần được thiết kế theo workload, không phụ thuộc việc “nhiều thread là nhanh hơn”.

### 20.5. Từ CompletableFuture.cancel giả định dừng lambda

**Trước:** gọi cancel(true) và coi supplier đã dừng.

**Sau:** thiết kế token hoặc quản lý Future của task thực thi thực sự; kiểm tra side effect và cleanup, không chỉ trạng thái CompletableFuture.

## 21. Những lỗi migration thường gặp

### “Đổi Thread.stop thành Thread.interrupt là xong”

Không đúng. interrupt chỉ có ý nghĩa khi task nhận tín hiệu, thoát khỏi blocking operation hoặc kiểm tra flag. Một task không hợp tác có thể chạy tiếp.

### “InterruptedException là lỗi bình thường, chỉ cần log”

Không đúng trong nhiều worker loop. Nếu nuốt exception mà không truyền trạng thái/hủy, code có thể tiếp tục chạy trái yêu cầu shutdown.

### “Future.cancel(true) đồng nghĩa task đã cleanup xong”

Không đúng. Cần phân biệt trạng thái future, nỗ lực interruption và lifecycle thật của task.

### “shutdownNow sẽ giết mọi thread”

Không đúng. Nó cố yêu cầu hủy, thường qua interruption, và có thể còn task không đáp ứng.

### “Thread.suspend an toàn nếu sau đó có resume”

Không đúng. Thread có thể giữ lock ở thời điểm bị suspend; code resume có thể bị deadlock hoặc không kịp thực thi.

### “Dùng daemon thread để khỏi cần shutdown”

Daemon thread không bảo đảm hoàn tất công việc hoặc cleanup trước khi JVM thoát. Nó không thay thế lifecycle quản lý tài nguyên.

### “Đóng socket luôn tương đương interrupt”

Không phải mọi I/O và mọi thư viện đều có cùng hành vi. Cần xem hợp đồng API, timeout và quyền sở hữu resource.

### “Thread.interrupted chỉ kiểm tra trạng thái”

Sai. Phương thức static này kiểm tra rồi xóa interrupt status của thread hiện tại. Nếu chỉ muốn quan sát, thường dùng isInterrupted.

### “Task đã hủy thì không còn tác động bên ngoài”

Không đúng. Database, HTTP call hoặc message publish có thể đã commit trước khi cancellation được xử lý. Vì vậy cần idempotency, compensation hoặc giao thức trạng thái rõ ràng.

## 22. Quy trình migration cho codebase có API Thread cũ

### Bước 1 — Khoanh vùng code và ownership

Tìm các usage:

~~~bash
rg -n "Thread[.]stop|[.]stop\(\)|[.]suspend\(\)|[.]resume\(\)" src
~~~

Kết quả chỉ là tìm kiếm văn bản, có thể lẫn stop method của class khác hoặc bỏ sót binary dependency. Cần kiểm tra class thực sự của đối tượng, generated source và thư viện bên thứ ba.

Ghi lại thành phần nào tạo thread, ai sở hữu nó và ai có quyền yêu cầu dừng.

### Bước 2 — Phân loại công việc và safe point

Với từng worker, xác định:

- CPU loop hay blocking?
- Công việc có transaction không?
- Có thể hủy giữa chừng hay cần hoàn tất một đơn vị?
- Có cần requeue hoặc checkpoint?
- Có caller đang chờ kết quả không?
- Timeout và SLA là gì?
- Có shared state và lock nào cần bảo toàn?

### Bước 3 — Thiết kế giao thức hủy

Chọn interrupt, cancellation token, queue signal hoặc API cancel của thư viện tương ứng. Tách rõ:

- stop accepting new work;
- cancel pending tasks;
- cancel running tasks;
- wait for cleanup;
- report final state.

### Bước 4 — Triển khai cleanup và lỗi

Thêm finally/try-with-resources, timeout, transaction handling, exception propagation và logging đủ để thấy task nào đã hủy.

Không đổi tên method rồi giữ nguyên semantics mơ hồ. Nên cập nhật API của service như requestShutdown, awaitStopped hoặc cancelJob để biểu diễn rõ ý định.

### Bước 5 — Thay cơ chế quản lý thread

Khi phù hợp, chuyển sang ExecutorService, task scheduler có lifecycle hoặc mô hình task scope của JDK mục tiêu. Không đổi toàn bộ kiến trúc nếu chưa hiểu ownership và giới hạn tài nguyên.

### Bước 6 — Kiểm thử cancellation

Tạo các tình huống:

- Hủy trước khi task bắt đầu.
- Hủy khi đang tính toán.
- Hủy lúc queue đang chờ.
- Hủy trong network/database wait.
- Hủy khi đang giữ lock hoặc ở sát transaction boundary.
- Hủy đồng thời với hoàn tất.
- Hủy nhiều lần.
- Shutdown khi có task mới được submit.
- Cleanup ném exception.
- Caller chờ kết quả cũng bị interrupt.

Kiểm tra cả trạng thái dữ liệu sau hủy, không chỉ việc thread.isAlive trở thành false.

### Bước 7 — Chạy trên JDK và môi trường đích

Xác minh behavior trên JDK thực tế, framework, driver, container, executor và classloader được triển khai. Mỗi JDK có thể có cải tiến về thread scheduling hoặc interruptibility của một số API; không nên suy diễn từ kết quả trên một bản Java khác.

### Bước 8 — Theo dõi sau triển khai

Theo dõi:

- Thời gian shutdown thực tế.
- Số task bị hủy, thất bại hoặc chưa hoàn thành.
- Resource leak và thread leak.
- Queue backlog.
- Tần suất timeout và retry.
- Deadlock/blocked thread.
- Tỷ lệ dữ liệu cần phục hồi hoặc requeue.
- Những task không đáp ứng cancellation deadline.

## 23. Mẫu tài liệu quyết định shutdown

~~~text
SERVICE / WORKER
  Service name:
  Thread/task owner:
  Runtime JDK:
  Executor/thread model:
  Queue or scheduler:

LEGACY API
  Thread.stop / suspend / resume usage:
  Source location:
  Trigger:
  Reason for historical design:

WORK CONTRACT
  Unit of work:
  Safe cancellation points:
  Transaction boundary:
  Idempotency/retry policy:
  External side effects:

CANCELLATION PROTOCOL
  Who requests cancellation:
  Interrupt / token / queue signal:
  Stop accepting policy:
  In-flight drain policy:
  Pending task policy:
  Timeout / deadline:

CLEANUP
  Owned resources:
  Rollback/compensation:
  Logging and metrics:
  Failure on cleanup:

VALIDATION
  Cancellation before start:
  Cancellation during blocking:
  CPU-bound cancellation:
  Race with completion:
  Repeated shutdown:
  Thread/resource leak:
  Deployment shutdown:
  Rollback plan:
~~~

Một bản ghi tốt phải giúp người vận hành biết **yêu cầu dừng đã được gửi**, **tác vụ đã thực sự kết thúc**, hay **đã hết thời hạn nhưng còn công việc chưa kết thúc**. Ba trạng thái này không thể dùng thay thế cho nhau.

## 24. Tổng kết

Chuyển từ API điều khiển luồng cũ sang dừng tác vụ có phối hợp không phải là một thay đổi cú pháp nhỏ. Đó là việc thay cơ chế “can thiệp bất đồng bộ vào thread” bằng một giao thức quản lý công việc và tài nguyên có chủ đích.

Những nguyên tắc quan trọng nhất:

1. **Không dùng Thread.stop, suspend hoặc resume để quản lý nghiệp vụ.** Chúng không cho phép task bảo toàn invariant và có thể tạo deadlock hoặc trạng thái không nhất quán.
2. **Interrupt là yêu cầu, không phải lệnh giết luồng.** Task phải đáp ứng qua điểm kiểm tra hoặc blocking API interruptible.
3. **Tín hiệu dừng phải đi cùng safe point.** Xác định khi nào được rollback, hoàn thành đơn vị công việc và đóng resource.
4. **Quản lý task bằng owner rõ ràng.** Dùng Future, ExecutorService, token, queue protocol hoặc task scope khi phù hợp.
5. **Graceful trước, escalation có giới hạn sau.** Ngừng nhận việc, drain, yêu cầu hủy, đợi cleanup và báo lỗi nếu timeout.
6. **Bảo vệ dữ liệu và vận hành.** Test transaction, idempotency, race condition, thread/resource leak và thời gian shutdown trên runtime thực tế.
7. **Không đánh đồng trạng thái cancel với task đã dừng.** Cần quan sát kết quả và cleanup thực tế.

Một hệ thống Java được migration tốt có thể yêu cầu dừng tác vụ mà không cần biết luồng đang ở đúng câu lệnh nào. Chính task tự tham gia vào quá trình kết thúc, giữ nguyên tính đúng đắn của trạng thái chia sẻ và cung cấp bằng chứng rõ ràng rằng nó đã hoàn tất, đã hủy hoặc chưa thể dừng trong thời hạn.

