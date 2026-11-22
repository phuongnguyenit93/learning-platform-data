# Thread pool, ExecutorService và công việc đang chờ xử lý

Trong ứng dụng Java, thread pool giúp giới hạn số luồng, tái sử dụng worker và điều phối công việc bất đồng bộ. API thường dùng để quản lý pool là Executor, ExecutorService, ThreadPoolExecutor và ScheduledExecutorService.

Khi ứng dụng sử dụng CRaC (Coordinated Restore at Checkpoint), thread pool cần được xem như một phần của vòng đời ứng dụng. Checkpoint có thể lưu trạng thái heap và tiến trình, nhưng việc một ExecutorService, queue hoặc Future còn tồn tại sau restore không tự chứng minh rằng worker, task, dependency và trạng thái nghiệp vụ vẫn sẵn sàng để tiếp tục.

Trước checkpoint, ứng dụng cần quyết định rõ công việc mới có được nhận hay không, công việc đang chạy sẽ hoàn tất thế nào và công việc đang chờ được giữ lại ở đâu. Sau restore, ứng dụng phải tạo hoặc phục hồi executor phù hợp, đưa các task còn hợp lệ vào xử lý và chỉ nhận traffic khi worker cùng dependency đã sẵn sàng.

## 1. Thread pool và ExecutorService là gì?

Thread pool là nhóm worker thread được quản lý để thực thi nhiều task. Thay vì tạo một thread mới cho từng request, ứng dụng gửi task vào executor. Executor quyết định task chạy trên worker nào và vào thời điểm nào.

Java cung cấp các abstraction chính:

- `Executor`: interface cơ bản nhận một Runnable để thực thi.
- `ExecutorService`: mở rộng Executor, hỗ trợ submit, Future, quản lý shutdown và chờ kết thúc.
- `ThreadPoolExecutor`: implementation phổ biến, quản lý core threads, maximum threads và work queue.
- `ScheduledExecutorService`: thực thi task sau một khoảng trễ hoặc theo lịch.
- `ForkJoinPool`: pool hướng đến chia nhỏ công việc và work stealing.
- Executor tạo virtual thread: tạo virtual thread cho mỗi task thay vì duy trì một pool cố định các platform thread.

Ví dụ đơn giản:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);

executor.submit(() -> {
    processOrder();
});
~~~

Ứng dụng gửi task bằng submit. Executor có thể đưa task vào queue nếu chưa có worker rảnh hoặc tạo thêm worker theo cấu hình. Task chỉ bắt đầu chạy khi được một worker nhận.

### 1.1. Các trạng thái của một task

Một task thường trải qua các trạng thái sau:

1. Được tạo bởi ứng dụng.
2. Được gửi vào executor.
3. Đang chờ trong queue.
4. Được worker lấy ra và thực thi.
5. Hoàn tất thành công, thất bại hoặc bị hủy.

Không phải task nào cũng đi qua tất cả trạng thái. Ví dụ, task có thể bị từ chối trước khi vào queue hoặc bị hủy khi vẫn đang chờ.

| Trạng thái | Ý nghĩa | Cần quan tâm khi checkpoint |
|---|---|---|
| Created | Đã tạo nhưng chưa submit | Có được submit sau restore không? |
| Queued | Đã submit, đang chờ worker | Lưu ở đâu và có còn hợp lệ không? |
| Running | Worker đang thực thi | Có thể hoàn tất an toàn trước checkpoint không? |
| Completed | Đã kết thúc | Kết quả đã được ghi nhận bền vững chưa? |
| Failed | Task kết thúc với lỗi | Có cần retry và retry có an toàn không? |
| Cancelled | Task đã bị hủy | Caller và hệ thống có nhận biết trạng thái hủy không? |
| Rejected | Executor không nhận task | Có cơ chế backpressure hoặc retry không? |

### 1.2. ExecutorService không phải một hàng đợi nghiệp vụ

Work queue của executor chủ yếu là cơ chế điều phối trong tiến trình. Nó không tự cung cấp các bảo đảm như durable storage, exactly-once processing hoặc phục hồi nghiệp vụ sau sự cố.

Nếu một task đại diện cho công việc quan trọng, chẳng hạn xử lý thanh toán hoặc gửi hóa đơn, ứng dụng cần một nguồn dữ liệu có thể khôi phục để biết công việc đó còn phải làm hay đã hoàn tất. Queue nội bộ của ThreadPoolExecutor không nên là nơi duy nhất lưu trạng thái nghiệp vụ quan trọng.

## 2. Vì sao thread pool cần được phối hợp với CRaC?

CRaC lưu trạng thái tiến trình tại một thời điểm. Thread pool có thể chứa nhiều trạng thái đồng thời:

- Worker đang chạy một Runnable.
- Worker đang chờ task trong BlockingQueue.
- Một task đang giữ lock hoặc transaction.
- Một Future đang được caller chờ kết quả.
- Một scheduler đang chờ thời điểm kích hoạt.
- Một worker đang sử dụng database connection hoặc HTTP client.
- Một task đang chờ phản hồi từ dịch vụ bên ngoài.

Trong thời gian checkpoint, tài nguyên bên ngoài và thời gian thực vẫn tiếp tục thay đổi. Database có thể failover, token có thể hết hạn, broker có thể rebalance, task có deadline có thể đã quá hạn. Một Runnable còn trong heap có thể chứa tham chiếu đến client đã đóng hoặc dữ liệu đã cũ.

Do đó, trước khi checkpoint, ứng dụng phải đưa hoạt động bất đồng bộ về trạng thái có thể quản lý. Sau restore, ứng dụng phải khôi phục executor và công việc theo chính sách đã chọn.

~~~mermaid
flowchart TD
    A["Ứng dụng đang nhận task"] --> B["Yêu cầu checkpoint"]
    B --> C["Ngừng submit task mới"]
    C --> D["Xử lý task đang chạy"]
    D --> E["Quyết định với task đang chờ"]
    E --> F["Dừng hoặc đóng executor"]
    F --> G["CRaC tạo checkpoint"]
    G --> H["Restore tiến trình"]
    H --> I["Tạo executor mới hoặc phục hồi pool"]
    I --> J["Khôi phục task còn hợp lệ"]
    J --> K["Mở lại admission và worker"]
~~~

Đây là mô hình điều phối tổng quát. Chi tiết triển khai phụ thuộc vào loại executor, thư viện, JDK CRaC và cách ứng dụng lưu công việc.

## 3. Phân biệt task đang chạy và task đang chờ

Hai nhóm này cần chính sách khác nhau.

### 3.1. Task đang chạy

Task đang chạy có thể:

- Thực hiện transaction trong database.
- Gọi API từ xa.
- Ghi file.
- Gửi message.
- Giữ lock.
- Thay đổi trạng thái nghiệp vụ.
- Chờ một Future khác.

Nếu checkpoint diễn ra giữa thao tác, sau restore task có thể tiếp tục trong khi dependency bên ngoài đã thay đổi. Một thao tác gửi request có thể đã được server thực hiện dù caller chưa nhận response. Nếu task được chạy lại, kết quả có thể bị lặp.

Chiến lược thường dùng là ngừng nhận công việc mới, đợi task đang chạy hoàn tất trong thời gian giới hạn và lưu kết quả theo cơ chế nghiệp vụ. Nếu task không thể kết thúc, ứng dụng cần có chính sách hủy hoặc dừng checkpoint.

Không nên giả định mọi task có thể bị interrupt an toàn. Interrupt chỉ là tín hiệu; task phải kiểm tra trạng thái interrupt hoặc sử dụng API có hỗ trợ interrupt. Một task đang chờ I/O không nhất thiết kết thúc ngay khi thread bị interrupt.

### 3.2. Task đang chờ trong queue

Task đang chờ chưa được worker thực thi. Có ba hướng xử lý phổ biến:

1. **Drain queue:** ngừng nhận task mới và cho worker hoàn thành tất cả task đang chờ trước checkpoint.
2. **Giữ công việc ở nguồn bền vững:** dừng consumer hoặc producer nội bộ, để job còn chờ ở broker hoặc database; sau restore tạo executor và tiếp tục lấy job.
3. **Lưu mô tả công việc:** chuyển task đang chờ thành command descriptor hoặc job ID có thể lưu bền vững; sau restore tạo lại Runnable từ descriptor rồi submit vào executor mới.

Không nên mặc định rằng giữ một Runnable trong queue là đủ. Runnable có thể capture một connection, request context, transaction, thread-local hoặc object mutable. Các tham chiếu đó có thể không hợp lệ sau restore.

### 3.3. Vì sao nên lưu mô tả công việc thay vì Runnable?

Một Runnable là đối tượng thực thi trong tiến trình. Nó có thể giữ nhiều tham chiếu đến trạng thái runtime. Một command descriptor mô tả công việc bằng dữ liệu rõ ràng, ví dụ:

~~~java
public record GenerateInvoiceCommand(
        String invoiceId,
        String customerId,
        int attempt
) {}
~~~

Sau restore, ứng dụng có thể đọc descriptor, tải trạng thái mới nhất và tạo task mới:

~~~java
GenerateInvoiceCommand command = jobStore.nextCommand();

executor.submit(() -> invoiceService.generate(command));
~~~

Cách này giúp task được tạo lại bằng dependency mới, cấu hình hiện tại và dữ liệu nghiệp vụ đã được kiểm tra. Descriptor cần chứa đủ thông tin để xác định công việc, nhưng không nên chứa secret hoặc tham chiếu đến tài nguyên runtime.

## 4. Các phương thức shutdown của ExecutorService

ExecutorService cung cấp các phương thức shutdown với ngữ nghĩa khác nhau. Hiểu đúng các phương thức này rất quan trọng khi chuẩn bị checkpoint.

### 4.1. shutdown()

~~~java
executor.shutdown();
~~~

shutdown() ngừng nhận task mới nhưng cho phép các task đã submit tiếp tục chạy. Phương thức này không đợi tất cả task hoàn tất.

Sau khi gọi shutdown():

- Task mới thường bị từ chối.
- Task đã nằm trong queue vẫn được thực thi.
- Task đang chạy tiếp tục cho đến khi hoàn tất, trừ khi task tự kết thúc hoặc bị tác động theo cơ chế khác.
- Executor sẽ chuyển sang trạng thái terminated khi mọi task đã hoàn tất và pool dừng.

Điểm quan trọng: một ExecutorService đã shutdown không thể được khởi động lại. Sau restore, nếu ứng dụng cần tiếp tục xử lý, hãy tạo một executor mới hoặc dùng cơ chế quản lý vòng đời do thư viện hỗ trợ.

### 4.2. awaitTermination()

~~~java
boolean terminated = executor.awaitTermination(
        30,
        TimeUnit.SECONDS
);
~~~

awaitTermination() chờ executor kết thúc sau khi đã yêu cầu shutdown. Phương thức trả về true nếu executor terminated trong thời gian chờ, false nếu timeout xảy ra.

Nó không tự gọi shutdown() và không tự hủy task. Vì vậy, thứ tự thường dùng là:

1. Ngừng admission.
2. Gọi shutdown().
3. Gọi awaitTermination() với timeout.
4. Nếu timeout, thực hiện chính sách xử lý tiếp theo.

Không nên chờ vô hạn trong callback CRaC. Một task bị treo có thể khiến quá trình checkpoint không thể tiếp tục.

### 4.3. shutdownNow()

~~~java
List<Runnable> notStarted = executor.shutdownNow();
~~~

shutdownNow() cố gắng dừng executor ngay lập tức:

- Không nhận task mới.
- Cố gắng interrupt các worker đang chạy.
- Trả về danh sách task chưa bắt đầu thực thi, nếu implementation có thể lấy chúng khỏi queue.
- Không bảo đảm task đang chạy sẽ dừng ngay.

Task cần hợp tác với cơ chế interrupt. Nếu Runnable bỏ qua interrupt hoặc đang thực hiện một thao tác không thể ngắt, worker vẫn có thể tiếp tục chạy.

Danh sách trả về có thể hữu ích để ứng dụng xử lý task chưa bắt đầu. Tuy nhiên, không nên giả định mọi ExecutorService đều cung cấp cùng khả năng quan sát hoặc khôi phục queue nội bộ. Với ThreadPoolExecutor, queue có thể truy cập thông qua API cụ thể; với các executor khác, chi tiết có thể khác.

### 4.4. So sánh ba phương thức

| Phương thức | Ngừng nhận task mới | Task đã chờ | Task đang chạy | Chờ kết thúc? |
|---|---|---|---|---|
| shutdown() | Có | Tiếp tục được thực thi | Tiếp tục chạy | Không |
| awaitTermination() | Không tự làm | Không tự thay đổi | Không tự interrupt | Có, đến timeout |
| shutdownNow() | Có | Cố gắng lấy ra và trả về task chưa bắt đầu | Cố gắng interrupt | Không |

Một mẫu shutdown thông thường:

~~~java
executor.shutdown();

if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    List<Runnable> notStarted = executor.shutdownNow();

    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException(
            "Executor did not terminate within the deadline"
        );
    }

    // Ứng dụng cần quyết định cách xử lý notStarted.
}
~~~

Đoạn mã là mẫu minh họa cho quá trình shutdown. Trong callback CRaC, ứng dụng còn phải phối hợp admission gate, trạng thái task và việc lưu công việc chưa hoàn tất. Không nên tự động bỏ các phần tử trong notStarted nếu chúng đại diện cho công việc nghiệp vụ chưa được xử lý.

## 5. ExecutorService sau khi shutdown có thể dùng lại không?

Không. Theo hợp đồng của ExecutorService, sau khi shutdown hoặc shutdownNow, executor không nhận task mới. Một ThreadPoolExecutor đã shutdown sẽ không thể được restart bằng cách gọi một phương thức resume chung.

Nếu ứng dụng đóng executor trong beforeCheckpoint(), sau restore cần tạo executor mới:

~~~java
private ExecutorService createExecutor() {
    return new ThreadPoolExecutor(
        4,
        8,
        60,
        TimeUnit.SECONDS,
        new LinkedBlockingQueue<>(500),
        new ThreadPoolExecutor.AbortPolicy()
    );
}
~~~

Sau restore:

~~~java
executor = createExecutor();
~~~

Đây là cách dễ hiểu và dễ kiểm soát cho một pool do ứng dụng sở hữu. Nếu executor được framework hoặc thư viện quản lý, hãy dùng lifecycle integration của framework để tránh tạo một pool trùng lặp hoặc bỏ qua quản lý tài nguyên.

## 6. Chọn chính sách cho công việc đang chờ

Không có một chính sách phù hợp cho mọi ứng dụng. Hãy chọn theo bản chất công việc.

### 6.1. Chính sách A: drain toàn bộ công việc

Ứng dụng ngừng nhận task mới và đợi tất cả task đã nhận hoàn tất. Khi queue và số task đang chạy đều về 0, executor được shutdown và checkpoint tiếp tục.

Phù hợp khi:

- Số lượng task chờ không lớn.
- Task có thời gian thực thi giới hạn.
- Task có thể hoàn tất trước deadline checkpoint.
- Việc đợi không làm ảnh hưởng SLA của hệ thống.

Ưu điểm là trạng thái sau restore đơn giản: không còn task nội bộ nào cần submit lại. Nhược điểm là thời gian checkpoint phụ thuộc vào task lâu nhất còn lại.

Cần theo dõi cả số task đang chạy và số task đang chờ. Chỉ đợi worker rảnh không đủ nếu queue vẫn còn task chưa được thực thi.

### 6.2. Chính sách B: để công việc ở hàng đợi bền vững

Với hệ thống xử lý job từ Kafka, RabbitMQ, database queue hoặc dịch vụ job bên ngoài, nguồn công việc có thể tồn tại độc lập với JVM.

Trước checkpoint:

1. Dừng consumer nhận message mới.
2. Hoàn tất hoặc xử lý message đang được giao.
3. Commit offset hoặc ack theo semantics của broker.
4. Đóng consumer và executor.
5. Để các message chưa được nhận tiếp tục nằm ở broker.

Sau restore:

1. Tạo executor mới.
2. Kết nối lại broker.
3. Đăng ký consumer hoặc subscription.
4. Bắt đầu nhận message.
5. Xử lý message theo cơ chế ack, retry và idempotency.

Cách này thường phù hợp với hệ thống có queue bền vững. Tuy nhiên, cần hiểu rõ thời điểm ack/commit. Nếu ack trước khi công việc hoàn tất, job có thể bị mất. Nếu ack sau khi hoàn tất nhưng phản hồi ack bị mất, job có thể được giao lại.

### 6.3. Chính sách C: lưu mô tả task để submit lại

Nếu công việc đang chờ nằm trong bộ nhớ và cần tiếp tục sau restore, hãy lưu một biểu diễn có thể tái tạo, chẳng hạn job ID, command record hoặc trạng thái workflow.

Trước checkpoint:

- Ngừng submit mới.
- Chuyển các task chờ thành descriptor.
- Lưu descriptor vào nơi bền vững hoặc một cấu trúc trạng thái được ứng dụng quản lý rõ ràng.
- Đảm bảo task đang chạy đã hoàn tất hoặc có checkpoint nghiệp vụ riêng.
- Shutdown executor.

Sau restore:

- Tạo executor mới.
- Đọc descriptor còn pending.
- Kiểm tra task đã được xử lý hay chưa.
- Tạo Runnable mới bằng dependency hiện tại.
- Submit lại và cập nhật trạng thái.

### 6.4. Không nên snapshot Runnable một cách tùy tiện

Runnable có thể capture:

- JDBC Connection hoặc transaction.
- HTTP client và socket.
- Security context hoặc token.
- Request/response object.
- ThreadLocal.
- Lock hoặc mutable object.
- Tham chiếu đến bean đã đóng hoặc executor cũ.

Giữ nguyên object Runnable trong heap không làm cho những dependency đó tự trở nên hợp lệ. Hãy lưu dữ liệu mô tả công việc và tạo lại Runnable sau restore.

## 7. Theo dõi số task đang chạy và đang chờ

Một ứng dụng cần biết khi nào có thể checkpoint an toàn. Thông tin hữu ích gồm:

- Số task đã được nhận nhưng chưa hoàn tất.
- Số task đang chạy.
- Số task đang chờ.
- Số task bị từ chối.
- Số task bị hủy.
- Thời gian task lâu nhất đã chạy.
- Số task có deadline đã quá hạn.

Với ThreadPoolExecutor, có thể đọc một số metric:

~~~java
ThreadPoolExecutor pool = (ThreadPoolExecutor) executor;

int active = pool.getActiveCount();
int queued = pool.getQueue().size();
long completed = pool.getCompletedTaskCount();
long total = pool.getTaskCount();
~~~

Các giá trị này hữu ích cho monitoring, nhưng không phải một snapshot nhất quán để ra quyết định checkpoint nếu task vẫn được submit đồng thời. Hãy đóng admission trước, rồi mới đợi các counter và queue đạt điều kiện mong muốn.

Một WorkTracker ở tầng ứng dụng có thể đếm công việc đã được nhận và chưa hoàn tất. Khi task kết thúc, tracker giảm counter trong finally block. Checkpoint coordinator có thể đợi counter về 0 bằng Condition, CountDownLatch hoặc cơ chế tương đương.

~~~java
public final class TrackedTask implements Runnable {

    private final Runnable delegate;
    private final WorkTracker tracker;

    public TrackedTask(Runnable delegate, WorkTracker tracker) {
        this.delegate = delegate;
        this.tracker = tracker;
    }

    @Override
    public void run() {
        try {
            delegate.run();
        } finally {
            tracker.completed();
        }
    }
}
~~~

Đây chỉ là một phần minh họa. Khi submit thất bại hoặc task bị hủy trước khi chạy, tracker cũng phải được cập nhật. Nếu chỉ giảm counter trong run(), task bị từ chối hoặc bị loại khỏi queue có thể khiến counter không bao giờ về 0.

## 8. Tích hợp executor với CRaC Resource

Một cách tổ chức là tạo resource quản lý vòng đời của executor. Resource này phối hợp với admission gate và task tracker.

Các bước:

1. Đăng ký resource trong quá trình khởi tạo ứng dụng.
2. Trong beforeCheckpoint(), ngừng submit task mới.
3. Chờ công việc đang chạy và đang chờ đạt chính sách đã chọn.
4. Shutdown executor.
5. Xác nhận executor đã terminated.
6. Sau restore, tạo executor mới.
7. Gắn executor mới với dispatcher và mở admission.

Ví dụ dưới đây giả định ứng dụng đã có WorkCoordinator để kiểm soát submit và chờ mọi task được nhận hoàn tất. Các interface này là abstraction của ứng dụng, không phải API của CRaC.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExecutorCheckpointResource implements Resource {

    private final WorkCoordinator coordinator;
    private final Supplier<ExecutorService> executorFactory;
    private final long timeoutSeconds;

    private volatile ExecutorService executor;

    public ExecutorCheckpointResource(
            WorkCoordinator coordinator,
            Supplier<ExecutorService> executorFactory,
            long timeoutSeconds) {

        this.coordinator = coordinator;
        this.executorFactory = executorFactory;
        this.timeoutSeconds = timeoutSeconds;
        this.executor = executorFactory.get();

        coordinator.attach(executor);
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        coordinator.stopAccepting();

        // Chờ cả task đang chạy và task đã được nhận hoàn tất.
        coordinator.awaitAllWork(timeoutSeconds, TimeUnit.SECONDS);

        ExecutorService oldExecutor = executor;
        oldExecutor.shutdown();

        if (!oldExecutor.awaitTermination(
                timeoutSeconds, TimeUnit.SECONDS)) {
            oldExecutor.shutdownNow();

            if (!oldExecutor.awaitTermination(
                    timeoutSeconds, TimeUnit.SECONDS)) {
                coordinator.markUnavailable();
                throw new IllegalStateException(
                    "Executor did not terminate before checkpoint"
                );
            }
        }

        executor = null;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        ExecutorService restoredExecutor = executorFactory.get();

        executor = restoredExecutor;
        coordinator.attach(restoredExecutor);
        coordinator.resumeAccepting();
    }
}
~~~

Trong ví dụ:

- WorkCoordinator ngừng admission và đợi công việc đã nhận hoàn tất.
- Executor cũ được shutdown sau khi công việc đã drain.
- Nếu không kết thúc trong thời gian cho phép, ứng dụng yêu cầu interrupt và tiếp tục chờ có giới hạn.
- Sau restore, executor mới được tạo và gắn lại vào coordinator.
- Admission chỉ mở sau khi executor mới được cài đặt.

Đây là cấu trúc minh họa, không phải một implementation hoàn chỉnh có thể sao chép mà không điều chỉnh. Trong production, cần xác định cách phục hồi nếu callback thất bại sau khi executor cũ đã shutdown. Vì ExecutorService đã shutdown không thể mở lại, ứng dụng phải tạo executor thay thế sau khi pool cũ thực sự dừng, hoặc giữ hệ thống ở trạng thái unavailable nếu worker cũ chưa kết thúc.

Nếu ứng dụng cần giữ task pending thay vì drain, hãy thay WorkCoordinator bằng một cơ chế lưu descriptor hoặc để job ở nguồn queue bền vững. Không submit lại một Runnable nếu chưa xác định lần thực thi trước có thể đã tạo tác dụng phụ.

## 9. Xử lý lỗi và timeout trong vòng đời executor

### 9.1. Task không kết thúc trước timeout

Một task có thể bị treo do:

- Chờ dịch vụ bên ngoài.
- Deadlock.
- Chờ lock bị giữ.
- I/O không có timeout.
- Bỏ qua interrupt.
- Chờ Future khác không bao giờ hoàn tất.

Không nên checkpoint một pool vẫn còn worker thực hiện thao tác không an toàn. Hãy đặt timeout cho I/O và các thao tác chờ, đồng thời thiết kế task có khả năng hủy hợp tác.

Nếu task không kết thúc, có thể hủy checkpoint và giữ ứng dụng ở trạng thái không sẵn sàng trong khi xử lý. Đừng giả định shutdownNow() sẽ cưỡng bức dừng mọi thread.

### 9.2. Task bị interrupt

Task nên kiểm tra interrupt và dọn dẹp tài nguyên trong finally. Ví dụ:

~~~java
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doOneUnitOfWork();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        releaseTaskResources();
    }
}
~~~

Nếu bắt InterruptedException, thường cần khôi phục interrupt flag khi không thể truyền exception ra ngoài. Không nên nuốt interrupt rồi tiếp tục vòng lặp vô hạn.

### 9.3. Task thất bại khi drain

Task thất bại không nhất thiết có nghĩa checkpoint phải thất bại. Điều đó phụ thuộc vào loại công việc và chính sách nghiệp vụ.

- Với task phụ trợ có thể bỏ qua, ghi nhận lỗi và tiếp tục theo chính sách.
- Với task quan trọng, cần ghi trạng thái failed hoặc retryable vào nơi bền vững.
- Với task có kết quả chưa xác định, cần truy vấn trạng thái từ hệ thống đích hoặc dùng idempotency key trước khi chạy lại.

### 9.4. Callback chuẩn bị thất bại

Nếu beforeCheckpoint() đã dừng admission và shutdown executor rồi một bước sau đó thất bại, ứng dụng có thể không còn pool để tiếp tục xử lý. Cần có thiết kế phục hồi rõ ràng.

Có thể dùng một coordinator có các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> QUIESCING: checkpoint requested
    QUIESCING --> DRAINED: no pending or active work
    DRAINED --> EXECUTOR_STOPPED: shutdown completed
    EXECUTOR_STOPPED --> CHECKPOINTING: callback returns
    CHECKPOINTING --> RESTORING: process restored
    RESTORING --> RUNNING: new executor attached
    QUIESCING --> RECOVERING: drain failed
    DRAINED --> RECOVERING: shutdown failed
    RECOVERING --> RUNNING: replacement pool ready
    RECOVERING --> UNAVAILABLE: recovery failed
~~~

Lưu ý CRaC Resource có callback trước checkpoint và sau restore; không nên giả định có một callback afterCheckpoint tự động đảo ngược mọi thay đổi nếu checkpoint bị hủy. Nếu cần phục hồi khi yêu cầu checkpoint thất bại, hãy xử lý lỗi tại tầng coordinator gọi yêu cầu checkpoint hoặc có một quy trình phục hồi độc lập. Không mở admission khi executor chưa sẵn sàng.

## 10. ScheduledExecutorService và task có thời hạn

ScheduledExecutorService hỗ trợ:

- schedule(): chạy một lần sau delay.
- scheduleAtFixedRate(): chạy lặp theo chu kỳ cố định.
- scheduleWithFixedDelay(): chạy lặp với khoảng nghỉ sau khi lần trước hoàn tất.

Các task theo lịch có thêm vấn đề về thời gian. Một task được lên lịch chạy sau 10 phút có thể đã đến hạn trong thời gian tiến trình bị checkpoint. Một lịch định kỳ có thể bỏ lỡ nhiều lần chạy. Delay queue và ScheduledFuture còn trong heap không tự giải quyết chính sách nghiệp vụ cho các lần chạy bị bỏ lỡ.

Hãy quyết định rõ:

- Task quá hạn có chạy ngay sau restore không?
- Những lần chạy định kỳ bị bỏ lỡ có được gộp thành một lần không?
- Có cần bỏ qua các lần chạy cũ và tính lịch tiếp theo?
- Deadline dựa trên wall-clock time hay monotonic elapsed time?
- Task có thể được thực hiện hai lần nếu trạng thái lịch được khôi phục và scheduler cũng đọc lại lịch từ database không?

Với lịch nghiệp vụ quan trọng, thường nên lưu lịch và trạng thái thực thi ở nơi bền vững. Sau restore, scheduler mới đọc lịch hiện hành và xác định công việc đến hạn. Tránh chỉ dựa vào đối tượng ScheduledFuture được lưu trong heap.

## 11. ForkJoinPool, common pool và virtual threads

### 11.1. ForkJoinPool

ForkJoinPool sử dụng work-stealing: worker có thể lấy task từ queue của worker khác khi rảnh. Cơ chế này phù hợp với công việc có thể chia nhỏ thành các subtask.

Khi dùng CRaC, cần lưu ý:

- Task có thể đang ở giữa quá trình fork/join.
- Worker có thể đang chờ hoặc lấy task từ queue nội bộ.
- Một task có thể phụ thuộc vào tài nguyên bên ngoài.
- Việc dừng và tạo lại pool cần tuân theo lifecycle của implementation.

Không nên giả định có thể snapshot queue nội bộ rồi tự submit lại từng ForkJoinTask. Nếu dùng pool riêng, hãy kiểm tra cách quản lý vòng đời của JDK và thư viện. Với công việc nghiệp vụ, nên giữ trạng thái công việc ở tầng ứng dụng để có thể tái tạo task.

### 11.2. ForkJoinPool.commonPool()

Common pool là pool dùng chung của JVM và được nhiều API sử dụng, ví dụ một số thao tác CompletableFuture và parallel stream.

Không nên shutdown common pool chỉ để chuẩn bị checkpoint cho một component. Pool này có thể đang được code khác sử dụng. Thay vào đó:

- Không đưa công việc nghiệp vụ dài hạn vào common pool nếu cần quản lý vòng đời riêng.
- Dùng executor riêng cho công việc cần pause, drain hoặc recreate.
- Kiểm tra các API bất đồng bộ đang dùng implicit default executor.
- Tránh phụ thuộc vào trạng thái nội bộ của common pool nếu ứng dụng cần kiểm soát chính xác việc phục hồi.

### 11.3. Virtual threads

Virtual thread giảm chi phí tạo thread và phù hợp với nhiều workload I/O-bound. Java có thể tạo executor bằng Executors.newVirtualThreadPerTaskExecutor().

Tuy nhiên, virtual threads không loại bỏ bài toán lifecycle:

- Task vẫn có thể đang thực hiện I/O.
- Task vẫn có thể giữ transaction hoặc tham chiếu đến client.
- Task vẫn có thể bị checkpoint khi đang ở trạng thái cần phối hợp.
- Công việc có thể bị trùng hoặc hết hạn trong thời gian restore.
- Ứng dụng vẫn cần dừng admission và xác định trạng thái pending work.

Executor tạo virtual thread vẫn là một ExecutorService. Hãy quản lý shutdown và task completion theo API của JDK đang dùng. Không nên suy luận rằng vì virtual thread nhẹ nên có thể bỏ qua drain hoặc quản lý công việc.

### 11.4. Không trộn lẫn executor sở hữu riêng và executor dùng chung

Một component không nên shutdown một executor mà nó không sở hữu. Ví dụ, nếu một framework truyền vào executor dùng chung, việc gọi shutdown() từ CRaC resource của component có thể làm hỏng các component khác.

Hãy xác định ownership:

| Executor | Ai quản lý vòng đời? | Hành động trước checkpoint |
|---|---|---|
| Pool riêng của service | Service hoặc lifecycle manager | Có thể pause/drain/shutdown và tạo lại |
| Pool do framework quản lý | Framework | Dùng lifecycle integration của framework |
| Common pool | JVM | Không shutdown theo vòng đời một component |
| Executor do request tạo tạm | Scope của request | Đóng khi request kết thúc |
| Executor của thư viện | Thư viện hoặc owner được chỉ định | Theo tài liệu của thư viện |

## 12. Future và CompletableFuture đang chờ

Future đại diện cho kết quả của một task. Caller có thể đang gọi get() hoặc join() để chờ kết quả.

Khi checkpoint, cần xem xét cả producer lẫn caller:

- Task tạo ra Future có thể đang chờ trong queue.
- Task có thể đang chạy và chưa hoàn tất.
- Caller có thể đang block trên Future.get().
- CompletableFuture có thể được hoàn tất bởi một thread khác hoặc một callback bất đồng bộ.
- Callback continuation có thể được submit vào một executor mặc định hoặc executor dùng chung.

Một Future còn tồn tại trong heap không chứng minh task sẽ tiếp tục đúng cách sau restore. Nếu executor cũ đã shutdown, continuation có thể bị từ chối khi submit. Nếu thao tác bên ngoài đã hoàn tất nhưng Future chưa được đánh dấu hoàn tất trước checkpoint, ứng dụng cần đối chiếu trạng thái từ hệ thống đích.

Với workflow quan trọng, nên lưu trạng thái nghiệp vụ hoặc correlation ID để khôi phục quá trình, thay vì chỉ dựa vào Future trong bộ nhớ.

Ví dụ, thay vì chỉ giữ Future cho một báo cáo, lưu report ID và trạng thái PENDING/COMPLETED trong job store. Sau restore, ứng dụng kiểm tra trạng thái và tạo lại task nếu cần.

## 13. Backpressure và giới hạn queue

Một thread pool có queue không giới hạn có thể tích tụ nhiều task khi tốc độ submit cao hơn tốc độ xử lý. Khi checkpoint, số task pending lớn làm thời gian drain kéo dài và tăng lượng trạng thái cần quản lý.

Nên cân nhắc:

- Queue có giới hạn.
- Rejection policy phù hợp.
- Backpressure tại API hoặc consumer.
- Giới hạn số task đang chạy.
- Theo dõi queue depth và task age.
- Không nhận thêm task khi instance chuẩn bị checkpoint.

ThreadPoolExecutor có các rejection policy như AbortPolicy, CallerRunsPolicy, DiscardPolicy và DiscardOldestPolicy. Mỗi policy có tác động khác nhau:

| Policy | Hành vi | Điểm cần chú ý |
|---|---|---|
| AbortPolicy | Ném RejectedExecutionException | Caller phải xử lý việc không nhận task |
| CallerRunsPolicy | Thread submit chạy task | Có thể làm tăng latency và thay đổi concurrency |
| DiscardPolicy | Bỏ task mới | Chỉ phù hợp nếu việc bỏ task được cho phép |
| DiscardOldestPolicy | Bỏ task cũ nhất trong queue rồi thử submit | Có thể làm mất công việc đang chờ |

Với công việc nghiệp vụ, không nên âm thầm bỏ task nếu chưa có cơ chế lưu trạng thái và thông báo. Rejection cần được xem như một kết quả rõ ràng mà caller có thể xử lý.

## 14. Quy trình triển khai thực tế

Một quy trình quản lý thread pool với CRaC có thể được tổ chức như sau.

### Trước checkpoint

1. Chuyển readiness sang NOT_READY.
2. Dừng nhận request hoặc job mới.
3. Ngừng consumer và scheduler tạo task mới.
4. Đợi task đang chạy hoàn tất trong thời gian giới hạn.
5. Xử lý task pending theo chính sách drain, durable queue hoặc descriptor.
6. Shutdown executor riêng của ứng dụng.
7. Xác nhận worker đã kết thúc và không còn task cần xử lý trong pool.
8. Để CRaC tiếp tục lưu checkpoint.

### Sau restore

1. Khởi tạo dependency cần thiết như database, HTTP client và broker.
2. Tạo executor mới hoặc gọi lifecycle integration được hỗ trợ.
3. Gắn executor mới vào dispatcher.
4. Đọc job descriptor hoặc tiếp tục consumer từ nguồn bền vững.
5. Submit lại các công việc còn hợp lệ.
6. Khởi động scheduler và consumer.
7. Chuyển readiness sang READY.

Thứ tự giữa các thành phần phải dựa trên dependency. Ví dụ, executor không nên nhận task gọi database trước khi database pool sẵn sàng.

## 15. Quan sát và kiểm thử

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| Active thread count | Số worker đang chạy task |
| Queue depth | Số task đang chờ |
| Outstanding work | Tổng công việc đã nhận nhưng chưa hoàn tất |
| Task duration | Phát hiện task kéo dài |
| Rejected task count | Theo dõi backpressure |
| Cancelled task count | Theo dõi task bị hủy |
| Executor termination time | Đo thời gian shutdown |
| Executor recreation time | Đo thời gian tạo pool sau restore |
| Pending job count | Theo dõi công việc chưa xử lý |
| Task retry count | Phát hiện lỗi hoặc xử lý lặp |

Nên kiểm thử:

1. Checkpoint khi pool rảnh.
2. Checkpoint khi có task đang chạy.
3. Checkpoint khi queue có nhiều task chờ.
4. Task đang chạy bị timeout hoặc không phản hồi interrupt.
5. Task gọi database khi database failover.
6. Task gửi message nhưng response hoặc ack bị mất.
7. Task có deadline đã quá hạn khi restore.
8. Executor shutdown thành công và được tạo lại sau restore.
9. Callback thất bại sau khi admission đã dừng.
10. Task được submit trong lúc checkpoint preparation.
11. Executor dùng chung bị một component cố shutdown.
12. Restore khi nguồn queue bền vững vẫn chứa job pending.

Mục tiêu là chứng minh không mất công việc, không thực hiện lặp ngoài chính sách, không nhận task khi executor chưa sẵn sàng và không để checkpoint chờ vô hạn.

## 16. Checklist thiết kế thread pool cho CRaC

### Admission và task lifecycle

- [ ] Có cơ chế ngừng submit task mới.
- [ ] Theo dõi được số task đang chạy và đang chờ.
- [ ] Task có timeout và xử lý interrupt phù hợp.
- [ ] Có chính sách rõ ràng cho task pending.
- [ ] Công việc quan trọng có trạng thái bền vững hoặc descriptor có thể tái tạo.

### Executor lifecycle

- [ ] Xác định rõ executor do ai sở hữu.
- [ ] Không shutdown executor dùng chung của framework hoặc common pool.
- [ ] Dùng shutdown và awaitTermination theo timeout.
- [ ] Chỉ dùng shutdownNow khi có chính sách xử lý task bị interrupt và task chưa bắt đầu.
- [ ] Không cố tái sử dụng ExecutorService đã shutdown.
- [ ] Tạo executor mới sau restore hoặc dùng integration được hỗ trợ.

### Restore và tính nhất quán

- [ ] Dependency sẵn sàng trước khi executor nhận task.
- [ ] Job pending được khôi phục từ nguồn có thể tin cậy.
- [ ] Task retry có cơ chế idempotency khi cần.
- [ ] Future và continuation được quản lý rõ ràng.
- [ ] Scheduler tính lại deadline và lịch sau restore.
- [ ] Readiness chỉ chuyển sang READY sau khi worker và dependency sẵn sàng.

### Quan sát và vận hành

- [ ] Có metric cho active count, queue depth và outstanding work.
- [ ] Có log cho từng bước checkpoint và restore.
- [ ] Có timeout cho drain và shutdown.
- [ ] Có quy trình xử lý khi callback thất bại.
- [ ] Đã kiểm thử task bị treo, pending queue lớn và lỗi kết nối sau restore.

## 17. Câu hỏi thường gặp

### Có thể giữ nguyên ThreadPoolExecutor qua checkpoint không?

Điều đó phụ thuộc vào JDK, cơ chế checkpoint/restore, trạng thái worker và thư viện. Không nên giả định mọi executor đều có thể được giữ lại an toàn. Với pool do ứng dụng sở hữu, một chiến lược dễ kiểm soát là ngừng admission, drain công việc, shutdown pool trước checkpoint và tạo pool mới sau restore.

### shutdown() có xóa task đang chờ không?

Không. shutdown() ngừng nhận task mới nhưng cho phép task đã submit tiếp tục thực thi. Muốn biết khi nào pool kết thúc, cần gọi awaitTermination() với timeout.

### shutdownNow() có bảo đảm dừng mọi task ngay lập tức không?

Không. Phương thức này cố gắng interrupt worker và trả về task chưa bắt đầu. Task phải hợp tác với interrupt; I/O hoặc code không kiểm tra interrupt có thể tiếp tục chạy.

### Có thể restart ExecutorService sau khi shutdown không?

Không. Một executor đã shutdown không nhận task mới. Hãy tạo một instance executor mới hoặc dùng lifecycle API của framework hỗ trợ việc tái khởi tạo.

### Task đang chờ trong queue có được lưu cùng checkpoint không?

Nếu object queue và task thuộc trạng thái heap được checkpoint, chúng có thể xuất hiện trong trạng thái được khôi phục. Tuy nhiên, điều đó không chứng minh task còn hợp lệ hoặc executor có thể tiếp tục xử lý an toàn. Hãy thiết kế chính sách pending work rõ ràng và không dựa vào Runnable tùy ý để bảo đảm công việc nghiệp vụ.

### Có nên dùng shutdownNow() trong beforeCheckpoint() không?

Chỉ khi ứng dụng có chính sách rõ ràng cho task đang chạy bị interrupt và task chưa bắt đầu được trả về. Nếu có thể, hãy dừng admission và drain công việc một cách có trật tự trước. shutdownNow() không thay thế quy trình lưu hoặc khôi phục job.

### Virtual thread có cần xử lý trước checkpoint không?

Có. Virtual thread giảm chi phí tạo thread nhưng task vẫn có thể đang giữ transaction, chờ I/O hoặc thực hiện thao tác nghiệp vụ. Vẫn cần ngừng admission, xử lý task đang chạy và khôi phục công việc pending theo chính sách.

### Có nên dùng common pool cho công việc cần quản lý CRaC không?

Thường không nên nếu ứng dụng cần kiểm soát chặt chẽ việc pause, drain và recreate. Common pool được chia sẻ trong JVM. Hãy cân nhắc executor riêng cho workload cần lifecycle độc lập.

### Làm thế nào tránh xử lý trùng task sau restore?

Lưu trạng thái công việc ở nguồn bền vững, dùng job ID hoặc idempotency key, cập nhật trạng thái hoàn tất một cách nhất quán và xác định rõ thời điểm ack/commit. Không retry một thao tác có kết quả chưa xác định nếu chưa kiểm tra trạng thái hoặc có cơ chế chống trùng.

## Kết luận

Thread pool và ExecutorService là thành phần điều phối công việc trong tiến trình. Khi dùng CRaC, ứng dụng cần quản lý cả worker đang chạy, task đang chờ, Future, scheduler và nguồn công việc bên ngoài. Việc object executor hoặc queue còn tồn tại sau restore không tự bảo đảm task có thể tiếp tục đúng cách.

Một quy trình dễ kiểm soát là ngừng admission, drain công việc hoặc giữ pending job ở nguồn bền vững, shutdown executor riêng trước checkpoint, rồi tạo executor mới và khôi phục task còn hợp lệ sau restore. Kết hợp timeout, idempotency, backpressure, readiness và metric giúp ứng dụng tránh mất hoặc lặp công việc khi checkpoint và restore.
