# Graceful shutdown trong Java Networking: ngừng nhận việc, chờ việc đang chạy và kết thúc có thứ tự

## 1. Vấn đề thực tế và mục tiêu

Một Java HTTP/TCP server đang xử lý các requests, có các worker threads và kết nối đến database, message broker hoặc API khác. Bạn cần **dừng dịch vụ** để triển khai phiên bản mới, thay cấu hình, thu hồi tài nguyên hoặc thoát ứng dụng. Nếu chỉ gọi `System.exit(0)`, đóng mọi socket hoặc `shutdownNow()` ngay, những request đang thực hiện có thể bị cắt giữa chừng. Ngược lại, nếu chỉ chờ mọi thread tự xong mà **vẫn nhận yêu cầu mới**, quá trình dừng có thể kéo dài mãi.

**Graceful shutdown** là quy trình **ngừng tiếp nhận công việc mới trước, cho công việc đã chấp nhận một cơ hội hoàn tất trong thời hạn có giới hạn, rồi giải phóng tài nguyên theo đúng quan hệ phụ thuộc**. Nếu công việc không thể kết thúc trong deadline, hệ thống phải có **forced-shutdown policy** rõ ràng, chứ không đợi vô hạn.

Ba câu hỏi chính của bài:

1. **Ngừng nhận việc mới thế nào?** Dừng listener, đánh dấu service `DRAINING`, cập nhật readiness, từ chối admission hoặc ngừng pull từ queue/broker.
2. **Chờ việc đang chạy ra sao?** Phân biệt request in-flight và request đã xếp hàng; dùng `ExecutorService.shutdown()`, `awaitTermination(...)`, theo dõi active requests/connection và deadline tổng.
3. **Kết thúc có thứ tự thế nào?** Hoàn tất phản hồi/ACK/commit, đóng accepted connections, worker pools, scheduler, database/broker và cuối cùng là telemetry; tránh đóng dependency khi handler vẫn dùng nó.

Tình huống phổ biến: restart một HTTP server, tắt TCP server, rolling deploy một service Java, đóng WebSocket sessions, dừng consumer nhận messages hoặc dừng tác vụ nền. Với mỗi trường hợp, **đơn vị công việc**, **thế nào là hoàn tất** và **khả năng retry** có thể khác nhau.

## 2. Dừng đột ngột khác dừng có thứ tự

~~~text
DỪNG ĐỘT NGỘT
RUNNING
   |
   +--> đóng socket + shutdownNow + exit
          |
          +--> một số request mất phản hồi
          +--> side effect có thể đã xảy ra nhưng client không nhận ACK
          +--> trạng thái in-flight chưa checkpoint
          +--> flush/log chưa hoàn thành

GRACEFUL SHUTDOWN
RUNNING
   |
   v
DRAINING / NOT READY
   |   (không nhận công việc mới)
   v
STOP INGRESS / LISTENER
   |
   v
DRAIN IN-FLIGHT + QUEUED-IF-ALLOWED
   |   (theo tổng deadline)
   +-- hoàn tất --> flush response/ack/checkpoint
   |
   +-- quá hạn ---> cancel/abort best-effort + reconcile later
   |
   v
CLOSE DEPENDENCIES / RESOURCES
   |
   v
STOPPED
~~~

**Không phải bảo đảm zero-data-loss tuyệt đối.** Máy có thể mất điện, process bị kill không chạy hook, client rời mạng giữa commit và response, database chết hoặc deadline drain hết. Graceful shutdown **giảm rủi ro** khi dừng chủ động; muốn dữ liệu bền vững và không xử lý nghiệp vụ trùng/lọt, còn cần **idempotency, transaction, durable queue, retry và recovery**.

### 2.1. Định nghĩa “đang chạy” rất quan trọng

- **Accepted TCP connection:** đã `accept()` nhưng có thể chưa đọc được request nào.
- **Active request:** handler đã bắt đầu xử lý logic nghiệp vụ.
- **Queued task:** đã nhận vào `ExecutorService` nhưng chưa có thread chạy; `shutdown()` vẫn có thể cho queued tasks chạy.
- **Streaming session:** WebSocket/SSE/gRPC stream có thể tồn tại lâu tùy ý; không thể chờ “hoàn thành tự nhiên” mãi nếu server phải dừng.
- **Background task:** job có thể chạy lâu hơn request và cần lưu checkpoint để resume.
- **Durable message:** consumer đã nhận một message nhưng chưa commit/ack; liệu dừng có làm redelivery hay không tùy broker contract.

Vì vậy cần quy định rõ **admission cutoff**, **drain scope**, **max wait** và **forced action**. “Đợi mọi việc xong” không có nghĩa chỉ đợi pool rỗng nếu vẫn còn socket/stream hoặc công việc ở nơi khác.

## 3. Trạng thái và tính bất biến của vòng đời

Một mô hình đơn giản:

~~~text
NEW -> RUNNING -> DRAINING -> STOPPING -> STOPPED
                       |          ^
                       +-- deadline+
~~~

- `RUNNING`: listener/poller nhận công việc mới, health/readiness cho phép routing.
- `DRAINING`: không nhận **tác vụ nghiệp vụ mới**; công việc đã chấp nhận được phép hoàn tất có giới hạn.
- `STOPPING`: dừng/chặn nguồn vào, kết thúc hoặc hủy các tác vụ còn tồn, đóng transports/dependencies.
- `STOPPED`: không còn thread/sockets/pools thuộc service; không thể tái sử dụng một số server object đã dừng.

Trong production, transition nên **đơn điệu**: không tự chuyển `DRAINING -> RUNNING` khi đã đóng listener/pool. Dùng `AtomicBoolean`/`AtomicReference<State>` để tránh hai signals cùng shutdown khiến double close hoặc chồng chéo.

~~~java
enum State { NEW, RUNNING, DRAINING, STOPPING, STOPPED }

AtomicReference<State> state =
        new AtomicReference<>(State.RUNNING);

// Chỉ một chủ thể được quyền bắt đầu drain.
boolean firstShutdown = state.compareAndSet(
        State.RUNNING, State.DRAINING);
~~~

Đây là **đoạn minh họa** trong class đã import `java.util.concurrent.atomic.AtomicReference`, chưa phải chương trình hoàn chỉnh. Một system thực còn cần trạng thái/error nếu shutdown bất thành, nhưng **không được báo “stopped” chỉ vì đã gọi shutdown mà thread vẫn chạy**.

### 3.1. Bất biến giúp kiểm thử

Khi hệ thống vào trạng thái draining:

1. **Không chấp nhận request/business task mới** sau ngưỡng chặn đã định nghĩa; các request đã ở races phải được xử lý theo policy rõ ràng.
2. **Không đóng dependency** trong khi handler đã chấp nhận còn cần dùng nó.
3. **Mọi task đã nhận** phải có outcome: hoàn tất/ack, fail/retry, hủy hoặc lưu checkpoint rõ ràng.
4. **Không chờ vô hạn**; có deadline tổng và cơ chế escalation.
5. Shutdown có thể được gọi nhiều lần nhưng **không làm hỏng** bước đã hoàn tất.

Chỉ kiểm tra `pool.isShutdown()==true` không chứng minh các điều kiện trên, vì `isShutdown` nghĩa là đã yêu cầu ngừng nhận tasks, **không phải tất cả task đã hoàn tất**.

## 4. Bước 1: ngừng nhận công việc mới

### 4.1. TCP server: đóng listening socket trước

Với server dựa trên `ServerSocket`:

~~~java
ServerSocket listener = new ServerSocket(8080);

// Ở shutdown coordinator:
stopping.set(true);
listener.close(); // accept() đang block sẽ ném SocketException.
~~~

Đây là **đoạn minh họa**, cần imports `ServerSocket` và biến `AtomicBoolean stopping`. Theo JDK 17, `ServerSocket.close()` khiến thread đang chặn trong `accept()` nhận `SocketException`; đó có thể là **hành vi bình thường khi shutdown có chủ đích**, không phải một incident cần spam error log.

**Điểm cực quan trọng:** đóng **listening socket** ngăn **TCP connections mới**, nhưng **không tự đóng tất cả Socket đã được accept**. Bạn có thể tiếp tục xử lý những accepted sockets trong drain window. Với từng socket đã accept, cần định nghĩa có cho gửi thêm requests trên kết nối persistent hay không; ứng dụng không tự được lợi nếu cứ đọc mãi một kết nối cũ trong khi đang draining.

### 4.2. Race giữa `accept` và `ExecutorService.execute`

~~~java
while (!stopping.get()) {
    Socket client = listener.accept();

    if (stopping.get()) {
        client.close();
        continue;
    }
    try {
        workers.execute(() -> handle(client));
    } catch (RejectedExecutionException rejected) {
        client.close();
    }
}
~~~

Đây là **fragment minh họa**; logic accept cần bắt `SocketException` của intentional shutdown và `IOException`. Race có thể xảy ra khi một connection được accept **cùng lúc** shutdown bắt đầu; vì vậy **kiểm tra lại stopping sau accept**, rồi xử lý `RejectedExecutionException` nếu pool đóng trong khoảng submit.

Đừng làm ngược thứ tự “`workers.shutdown()` rồi vẫn để listener.accept() nhận tiếp”: request mới có thể được accept nhưng bị reject và client chờ/được reset vô cớ. Cố gắng **dừng ingress trước**, rồi kết thúc queued/running work.

### 4.3. HTTP server và readiness

Ở HTTP load-balanced service, thường phối hợp:

1. Đặt **readiness=false** để load balancer/orchestrator không chọn instance nhận traffic mới.
2. Bắt đầu **drain**: từ chối admission mới theo quy tắc, hạn chế keep-alive/persistent sessions.
3. Dừng HTTP listener/acceptor hoặc gọi API server stop phù hợp sau khi điều phối.
4. Đợi requests in-flight theo deadline; không hủy ngay khi còn đường hoàn tất bình thường.
5. Đóng dependencies và thoát process.

**Readiness không phải một bức tường tức thời.** Có độ trễ cập nhật endpoint tables, các kết nối đã mở hoặc requests đang chuyển tới instance. Nên có **admission guard trong application** và cấu hình proxy drain, không trông chờ chỉ một flag healthcheck.

Trong Kubernetes, khi Pod bị yêu cầu dừng, cần xem **termination grace period, preStop lifecycle và hành vi SIGTERM** của runtime/load balancer. Đây là những cơ chế điều phối hữu ích nhưng **không thay** sự quản lý in-flight tasks của ứng dụng. Một grace period ngắn hơn thời gian drain thực tế sẽ dẫn tới forced termination.

### 4.4. Queue consumer hoặc scheduler: ngừng “pull” trước

Nếu service nhận công việc từ queue/broker, “ngừng nhận” thường là **pause polling**, unsubscribe hoặc stop fetching new messages. Sau đó đợi các messages đã giao cho workers đạt kết quả an toàn. Chỉ commit offset/ACK khi phù hợp với semantics đã thực sự hoàn thành; không ACK trước khi dữ liệu đã lưu rồi shutdown đột ngột.

Với scheduled jobs, phải ngừng lịch phát task mới; còn task đang chạy cần được drain hoặc checkpoint. `ScheduledExecutorService.shutdown()` có semantics và chính sách với delayed/periodic tasks khác thường; phải kiểm tra configuration như `ScheduledThreadPoolExecutor.setContinueExistingPeriodicTasksAfterShutdownPolicy` và `setExecuteExistingDelayedTasksAfterShutdownPolicy` nếu có yêu cầu rõ.

## 5. Bước 2: chờ công việc đang chạy bằng ExecutorService

JDK 17 cung cấp những API chính:

| API | Hành vi | Điều không được suy diễn |
| --- | --- | --- |
| `shutdown()` | **Ngừng nhận tasks mới**, cho tasks đã submit tiếp tục theo executor policy | **Không block** đợi tasks xong |
| `isShutdown()` | Đã có yêu cầu shutdown | Không nói task đã xong |
| `awaitTermination(timeout, unit)` | **Chờ** pool kết thúc sau khi shutdown hoặc đến timeout/interrupt | Chỉ gọi nó **không tự shutdown pool** |
| `isTerminated()` | Pool đã ngừng hoàn toàn sau shutdown, không còn tasks chạy/queued | Không bảo đảm business ACK đã được commit ngoài pool |
| `shutdownNow()` | Cố ngắt tasks đang chạy, không cho queued tasks bắt đầu; trả danh sách tasks chưa bắt đầu | **Không ép** mọi task dừng ngay |
| `Future.cancel(true)` | Yêu cầu hủy một task đang chạy nếu implementation hỗ trợ | Không bảo đảm transactional side effect được rollback |

### 5.1. Trình tự tiêu chuẩn hai pha

~~~java
static boolean drainPool(
        ExecutorService pool,
        long gentleSeconds,
        long forcedSeconds) {

    pool.shutdown(); // Ngừng nhận tasks mới.
    try {
        if (pool.awaitTermination(gentleSeconds, TimeUnit.SECONDS)) {
            return true; // Đã hoàn tất các tasks theo quy tắc pool.
        }

        List<Runnable> neverStarted = pool.shutdownNow();
        // Production: log/requeue/checkpoint neverStarted theo nghiệp vụ.

        return pool.awaitTermination(forcedSeconds, TimeUnit.SECONDS);
    } catch (InterruptedException interrupted) {
        pool.shutdownNow();
        Thread.currentThread().interrupt(); // Giữ tín hiệu interrupt.
        return false;
    }
}
~~~

Đây là **phương thức Java 17 minh họa**, cần imports `java.util.concurrent.*` và `java.util.List`. Nó là mẫu hai pha tương tự hướng dẫn trong JDK `ExecutorService`: **graceful attempt** bằng `shutdown + awaitTermination`, rồi **best-effort forced attempt** bằng `shutdownNow + awaitTermination`.

**Đừng báo thành công quá sớm:** `shutdownNow()` có thể trả về danh sách chưa chạy và những task đang chạy có thể **bỏ qua interrupt**. Hàm trả `false` nếu hết ngân sách chờ hoặc bị interrupt; phải ghi nhận những tasks còn tồn và hành động tiếp theo. Với service có data durability, **“pool đã dừng”** cũng không đồng nghĩa mọi message được database/broker xác nhận.

### 5.2. `shutdown()` vẫn cho queued tasks chạy

Giả sử pool có hai worker threads, hai tác vụ đang chạy và 200 tác vụ đã được xếp queue trước cutoff. `shutdown()` **không loại tất cả 200 tasks**; chúng vẫn có thể được xử lý. Nếu 200 tác vụ tốn một phút, drain window 20 giây không đủ. Đó là lý do **giới hạn queue ngay khi RUNNING**, quản lý admission và timeout mỗi task quan trọng.

Nếu policy chỉ cho phép hoàn tất **tasks đã bắt đầu**, còn queued tasks phải trở lại broker, cần một kiến trúc hỗ trợ **thu hồi/requeue tasks chưa chạy**, không coi `shutdown()` mặc định có semantics đó. `shutdownNow()` trả những `Runnable` chưa bắt đầu nhưng trả về `Runnable` không tự biến thành broker message đã checkpoint; app phải lưu task IDs và trạng thái trong durable store.

### 5.3. Interrupt là một yêu cầu hợp tác

Một worker có thể phản ứng tốt với interrupt:

~~~java
try {
    while (!Thread.currentThread().isInterrupted()) {
        performOneBoundedStep();
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
} finally {
    closeOwnedResources();
}
~~~

Đây là **mã minh họa**, các hàm là helper ứng dụng. Các thao tác chặn trên `BlockingQueue.take()`, `Thread.sleep()` thường phản hồi `InterruptedException`. Nhưng một DB driver, Socket read, native operation hoặc logic CPU loop không check interrupt có thể **không kết thúc ngay**. Với socket truyền thống, cần **đọc có timeout, đóng socket có kiểm soát** hoặc thư viện có deadline/cancel semantics phù hợp.

**Không dùng `Thread.stop()`** làm biện pháp forced shutdown: phương thức này không an toàn đối với invariants/locks. Không cho rằng `shutdownNow()` sẽ “giết thread” hoặc rollback một transaction đã commit.

## 6. Bước 3: đóng tài nguyên theo dependency order

Hãy sắp xếp theo quan hệ **cái nào còn dùng cái nào**. Một thứ tự tham khảo:

~~~text
1. Stop routing/admission/listeners/consumer polling.
2. Await short in-flight critical requests, stop new periodic jobs.
3. Let handlers finish response / persist / ACK; checkpoint resumable jobs.
4. Close accepted client connections and long-lived streams according to policy.
5. Stop worker executors; awaitTermination bounded; escalate if necessary.
6. Close service dependencies after their users stop:
     database pools, outbound HttpClient resources,
     broker producers/consumers, file handles.
7. Flush metrics/traces/logs; stop observability transports.
8. Mark STOPPED; process can exit.
~~~

**Không có một thứ tự đơn giản đúng cho mọi service.** Ví dụ consumer polling phải dừng **trước** workers drain, nhưng broker producer vẫn cần mở cho đến khi workers **publish kết quả cuối cùng**. Database connection pool cũng phải còn mở khi có handlers đang commit. Với producer/consumer cùng một client object, cần xác định khả năng tách close operations.

### 6.1. Vì sao đóng database sớm là lỗi?

~~~text
Thread A: xử lý đặt hàng -> chuẩn bị COMMIT
Thread B: nhận shutdown -> dbPool.close()
Thread A: commit thất bại, client có thể timeout
~~~

Trình tự an toàn hơn:

~~~text
stop intake -> existing orders finalize -> pool terminated
           -> close DB pool -> flush logs/metrics -> stopped
~~~

Nếu một task bất hợp tác, sau deadline không thể bảo đảm hoàn tất an toàn; thay vì giả vờ graceful, phải có recovery (idempotent retry, transaction status check, dead-letter queue) và metrics cụ thể.

### 6.2. TCP listening socket và accepted sockets có lifecycle khác

Đóng `ServerSocket` để dừng `accept()` **không đóng** những `Socket` client đã chấp nhận. Mỗi handler cần `try-with-resources`/`finally` đóng socket của chính nó khi đã gửi ACK hoặc khi timeout/hủy. Nếu muốn forced shutdown sau deadline, quản lý tập **active sockets** để có thể đóng những socket còn block (và tránh leak); chú ý việc close có thể làm worker thấy `SocketException` như một nguyên nhân expected.

### 6.3. Response đã gửi không luôn đồng nghĩa nghiệp vụ xong

Một response `200 OK` có thể đã gửi nhưng database chưa commit nếu code thực hiện thứ tự sai. Với thanh toán/đặt hàng, cần **định nghĩa thời điểm success/ACK**, transaction commit và idempotency. Trong graceful shutdown, không nên phát ACK “done” khi chỉ mới đưa task vào queue volatile rồi hủy queue. Hãy thiết kế kết quả durable trước khi client nhận confirmation, hoặc công khai semantics `202 Accepted` khi có job bền vững đang chạy nền.

## 7. Deadline tổng: không chờ vô hạn khi triển khai

Một bài toán deploy điển hình có **grace period** hữu hạn từ orchestrator. Nếu bạn cấp mỗi bước 30 giây rồi cộng dồn 5 bước, tổng thời gian có thể vượt 30 giây của Pod. Nên tính theo **deadline tuyệt đối**:

~~~text
deadline = shutdownStartedAt + overallBudget

phase A: stop ingress (budget từ deadline)
phase B: drain in-flight (budget còn lại)
phase C: close dependencies (budget còn lại)
phase D: flush telemetry (budget còn lại)
phase E: force if necessary before orchestrator kills process
~~~

### 7.1. Dùng `System.nanoTime()` cho khoảng thời gian tương đối

~~~java
long deadline = System.nanoTime()
        + TimeUnit.SECONDS.toNanos(20);

// Trong bước chờ:
long nanosRemaining = deadline - System.nanoTime();
if (nanosRemaining > 0) {
    terminated = workers.awaitTermination(
            nanosRemaining, TimeUnit.NANOSECONDS);
}
~~~

Đây là **đoạn minh họa**, `workers`/`terminated` là biến đã khai báo. `System.nanoTime()` phục vụ **đo khoảng thời gian** theo mốc đơn điệu, phù hợp hơn `System.currentTimeMillis()` khi đồng hồ hệ thống được điều chỉnh. Cần tránh tràn số khi cộng budget quá lớn; trong thực tế dùng budget hữu hạn, nhỏ.

### 7.2. Khi hết deadline, phải nêu rõ policy

- Đặt service **not ready**, tránh chấp nhận thêm việc.
- Gửi tín hiệu cancellation best-effort, `shutdownNow()`, đóng sockets/blocking I/O nếu cần.
- Không gửi “thành công” cho tác vụ chưa commit.
- Ghi lại IDs/cursors/attempts cần phục hồi, nếu còn thời gian và storage khả dụng.
- Báo metrics: `drain_timeout`, `forced_close`, `unfinished_tasks` và nguyên nhân.
- Nhờ broker/DB/idempotency bù các phần chưa xác định sau khi process khởi động lại.

Không “đợi thêm một chút” liên tục; đó không còn là graceful shutdown có thời hạn. Nếu process bị kill cưỡng bức trước khi flush, bảo đảm lưu trữ phải đến từ **durable design trong lúc RUNNING**, không chỉ dựa vào shutdown hook.

## 8. Ví dụ Java 17+ chạy độc lập: dừng accept, chờ một request và kết thúc workers

Chương trình **GracefulTcpShutdownDemo.java** sau là một TCP line-protocol server rất nhỏ, chỉ bind `127.0.0.1` trên port ngẫu nhiên. Mục đích là chứng minh đúng **thứ tự lifecycle** mà không phụ thuộc Internet hay framework ngoài:

1. Listener nhận một client; worker đọc một dòng `ping`.
2. Worker thông báo đã bắt đầu xử lý bằng `CountDownLatch started`, nhưng **tạm chờ cổng `mayFinish`** (đây là test synchronization, không phải business logic thật).
3. Main tiến hành **stop accepting** bằng `stopping.set(true)` và `listener.close()`; acceptor thoát sau `SocketException` có chủ đích.
4. Main gọi `workers.shutdown()`. Với handler đang chờ latch, `awaitTermination(100ms)` trả `false`: vẫn có việc đang xử lý.
5. Main cho worker hoàn tất bằng `mayFinish.countDown()`; client nhận `ACK:ping`.
6. Main `awaitTermination(5s)` và xác nhận pool kết thúc; cleanup resources.

**Dòng output là xác định theo latches**, không phụ thuộc vào ngẫu nhiên chọn port. Đây là demo về **ngừng nhận connections mới và hoàn thành một request đã nhận**. Nó **không** tự cung cấp HTTP protocol, TLS, authentication, backpressure production hoặc durable transactions.

Lưu thành file **GracefulTcpShutdownDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class GracefulTcpShutdownDemo {
    static final AtomicBoolean stopping = new AtomicBoolean();
    static final CountDownLatch started = new CountDownLatch(1);
    static final CountDownLatch mayFinish = new CountDownLatch(1);
    static final CompletableFuture<Void> handlerDone =
            new CompletableFuture<>();

    static void handle(Socket socket) {
        try (socket;
             BufferedReader input = new BufferedReader(
                     new InputStreamReader(
                             socket.getInputStream(),
                             StandardCharsets.UTF_8));
             BufferedWriter output = new BufferedWriter(
                     new OutputStreamWriter(
                             socket.getOutputStream(),
                             StandardCharsets.UTF_8))) {

            socket.setSoTimeout(3000);
            String request = input.readLine();
            if (!"ping".equals(request)) {
                throw new IOException("Expected ping");
            }
            started.countDown();

            // Chỉ là cổng đồng bộ trong DEMO.
            if (!mayFinish.await(5, TimeUnit.SECONDS)) {
                throw new IOException("Drain deadline exceeded");
            }

            output.write("ACK:" + request);
            output.newLine();
            output.flush();
        } catch (InterruptedException problem) {
            Thread.currentThread().interrupt();
            handlerDone.completeExceptionally(problem);
            return;
        } catch (Exception problem) {
            handlerDone.completeExceptionally(problem);
            return;
        }

        handlerDone.complete(null);
    }

    static void acceptLoop(
            ServerSocket server,
            ExecutorService workers,
            CompletableFuture<Void> acceptDone) {

        try {
            while (!stopping.get()) {
                Socket socket;
                try {
                    socket = server.accept();
                } catch (SocketException closed) {
                    if (!stopping.get()) {
                        throw closed;
                    }
                    break; // Listener đóng có chủ đích.
                }

                // Bảo vệ race: accept vừa xong thì shutdown bắt đầu.
                if (stopping.get()) {
                    socket.close();
                    continue;
                }

                try {
                    workers.execute(() -> handle(socket));
                } catch (RejectedExecutionException rejected) {
                    socket.close(); // Không giữ socket đã bị reject.
                }
            }
            acceptDone.complete(null);
        } catch (IOException problem) {
            acceptDone.completeExceptionally(problem);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);

        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"))) {

            CompletableFuture<Void> acceptDone =
                    new CompletableFuture<>();
            Thread acceptThread = new Thread(
                    () -> acceptLoop(listener, workers, acceptDone),
                    "acceptor");
            acceptThread.start();

            try (Socket client = new Socket(
                         InetAddress.getByName("127.0.0.1"),
                         listener.getLocalPort());
                 BufferedWriter sender = new BufferedWriter(
                         new OutputStreamWriter(
                                 client.getOutputStream(),
                                 StandardCharsets.UTF_8));
                 BufferedReader receiver = new BufferedReader(
                         new InputStreamReader(
                                 client.getInputStream(),
                                 StandardCharsets.UTF_8))) {

                client.setSoTimeout(5000);
                sender.write("ping");
                sender.newLine();
                sender.flush();

                if (!started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Handler did not start");
                }
                System.out.println("in-flight: 1");

                // Bước 1: từ chối connections mới.
                stopping.set(true);
                listener.close();
                acceptDone.get(5, TimeUnit.SECONDS);
                acceptThread.join(5000);
                if (acceptThread.isAlive()) {
                    throw new IllegalStateException(
                            "Accept thread alive");
                }
                System.out.println("accepting: stopped");

                // Bước 2: pool không nhận tasks mới.
                workers.shutdown();

                // Worker đang giữ latch, vì vậy chưa thể terminated.
                boolean early =
                        workers.awaitTermination(
                                100, TimeUnit.MILLISECONDS);
                System.out.println("still processing: " + !early);

                // Bước 3: cho request cũ hoàn tất rồi mới thoát.
                mayFinish.countDown();
                String reply = receiver.readLine();
                if (!"ACK:ping".equals(reply)) {
                    throw new IOException("Bad reply: " + reply);
                }
                handlerDone.get(5, TimeUnit.SECONDS);
                System.out.println("reply: " + reply);

                if (!workers.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Workers did not terminate");
                }
                System.out.println("workers: terminated");
            } finally {
                mayFinish.countDown();
            }
        } finally {
            // Safety cleanup nếu demo gặp lỗi ở giữa.
            stopping.set(true);
            mayFinish.countDown();
            workers.shutdownNow();
            workers.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**, không cần thư viện bên ngoài:

~~~bash
javac -encoding UTF-8 GracefulTcpShutdownDemo.java
java GracefulTcpShutdownDemo
~~~

Stdout đã được kiểm tra bằng JDK 17 JShell:

~~~text
in-flight: 1
accepting: stopped
still processing: true
reply: ACK:ping
workers: terminated
~~~

### 8.1. Diễn giải từng dòng

- **`in-flight: 1`**: một accepted socket đã được worker đọc request `ping` và bắt đầu xử lý. `CountDownLatch` xác nhận trạng thái, thay vì `Thread.sleep(...)` rồi hy vọng worker đã chạy.
- **`accepting: stopped`**: shutdown coordinator đã set flag, đóng listening socket, đợi acceptor kết thúc. Những accepted sockets hiện có không bị đóng chỉ vì listener đóng.
- **`still processing: true`**: `workers.shutdown()` đã gọi nhưng worker vẫn chờ latch; `awaitTermination(100 ms)` trả `false`, chứng minh **shutdown không tự đợi hoặc cắt ngang tác vụ đang chạy**.
- **`reply: ACK:ping`**: sau khi phát `mayFinish`, worker gửi response đúng line protocol, flush và đóng client socket. Client nhận kết quả trước khi hệ thống khẳng định đã drain xong.
- **`workers: terminated`**: worker pool không còn task chạy/queued sau deadline chờ. **Chỉ lúc này** ta có thể khẳng định executor đã terminated.

### 8.2. Vì sao dùng `CompletableFuture` và `CountDownLatch`?

Để output độc lập với tốc độ scheduler. `CountDownLatch started` bảo đảm request **đang được xử lý** trước khi dừng listener; `mayFinish` giữ request mở để test `awaitTermination`; `handlerDone` chuyển lỗi worker sang main thay vì im lặng trong thread pool; `acceptDone` ghi nhận acceptor đã thoát hoặc thất bại.

Trong code production, **không tạo một cặp latch static cho mọi requests**. Hãy dùng lifecycle coordinator, active-task counters, structured concurrency/managed executor khi phù hợp, per-request future và durable job IDs. Latches ở đây là công cụ **kiểm thử thứ tự**, không phải cách làm server thực tế nhiều clients.

### 8.3. Tại sao không gọi `shutdownNow` ngay?

Nếu gọi `shutdownNow()` ngay sau nhận request, nó có thể interrupt worker đang chờ latch. Client sẽ **không nhận ACK**; đây chính là lỗi graceful shutdown muốn tránh. Trong demo, `shutdownNow()` chỉ nằm ở **finally để dọn an toàn khi có exception**, sau đường thành công bình thường pool đã terminated. Với production cần hai pha: `shutdown/await` trước, `shutdownNow/await` sau khi vượt deadline.

### 8.4. Giới hạn của demo

- Đây là line protocol một request, không phải HTTP/1.1/WebSocket/gRPC server.
- Chỉ bind loopback và sử dụng một client; không có TLS/authz, quotas hay nhiều sockets persistent.
- Pool fixed 2 threads có queue **không giới hạn** theo `Executors.newFixedThreadPool`; không dùng nguyên mẫu này khi service tiếp nhận lượng lớn requests không đáng tin.
- `Socket.setSoTimeout(3000)` giới hạn các blocking reads; nó **không là overall request deadline** và không đặt deadline cho mọi outbound write.
- Demo không lưu requests vào durable store; nếu process bị kill cưỡng bức, in-flight task có thể mất.
- Không dùng exception `SocketException` sau listener.close()` làm “mạng sự cố” nếu đó là shutdown có chủ đích; nhưng unexpected `SocketException` khi RUNNING vẫn cần log/cảnh báo.
- `awaitTermination` và `acceptDone.get` đều có timeout để không chờ mãi; khi task/callback lỗi, code phát hiện và báo ra main.

## 9. Nếu đang dùng JDK `HttpServer` thay vì TCP `ServerSocket`?

`com.sun.net.httpserver.HttpServer` cung cấp phương thức `stop(int delay)`. Theo Java 17 API:

> `stop(delay)` đóng listening socket, ngăn server xử lý exchanges mới, rồi **chặn caller** cho tới khi các active exchange handlers hoàn tất **hoặc xấp xỉ `delay` giây đã trôi qua**, tùy điều kiện nào đến trước. Sau đó các TCP connections còn mở bị đóng. Một `HttpServer` đã stop **không thể start lại**.

Ví dụ **đoạn minh họa**:

~~~java
// giả định server đã start và pool là executor do ứng dụng sở hữu
server.stop(10);     // delay là GIÂY, không phải milliseconds.
pool.shutdown();     // pool có lifecycle riêng.
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        pool.awaitTermination(2, TimeUnit.SECONDS);
    }
} catch (InterruptedException interrupted) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây không phải phương thức chạy độc lập; cần biến `server`/`pool` và import `TimeUnit`. Điểm cần ghi nhớ:

1. `HttpServer.stop(delay)` **tự quản lý listening socket/exchanges** của JDK HTTP server; không cần truy cập `ServerSocket` bên trong implementation.
2. `delay` **là số giây chờ tối đa** (sau đó các TCP connections đóng), không phải “sleep cố định” và không phải milliseconds. `stop(0)` có thể cắt exchanges đang chạy ngay.
3. `stop` có thể block thread gọi. Gọi từ shutdown coordinator, **không** từ một handler trong cùng server rồi tạo deadlock chờ handler của chính nó.
4. Nếu dùng `ExecutorService` tự tạo qua `server.setExecutor(pool)`, phải **shutdown pool riêng** khi server đã không còn dispatch công việc, hoặc theo lifecycle đã được thiết kế.
5. `HttpServer.stop` không tự chờ mọi job **bất đồng bộ detached** mà handler đã spawn và đã return trước đó; phải track futures/jobs riêng nếu cần.
6. Nếu server handler có thể xử lý stream vô hạn, `stop(delay)` không thể hứa mọi response hoàn tất trong deadline; sau deadline có thể cắt connection.
7. `HttpServer` đã `stop` không thể gọi `start()` lại; restart cần tạo một instance khác.

### 9.1. HTTP response trong drain window

Một handler đã nhận request nên cố gắng **gửi một response hợp lệ**, đóng `HttpExchange`, output stream và dependency trước deadline. Nếu trả response body với fixed length, phải viết đủ bytes; với chunked cần đóng stream để kết thúc. Đừng trả `200 OK` nếu transaction chưa hoàn tất thực sự theo contract. Nếu service đã DRAINING và còn request đến, có thể trả `503 Service Unavailable` với `Retry-After` phù hợp **trước khi commit**, tùy server/API; không coi mọi trường hợp shutdown đều có thể gửi 503 vì socket có thể đã bị đóng.

### 9.2. HTTP keep-alive và HTTP/2

Một TCP connection HTTP/1.1 keep-alive có thể mang nhiều requests; không được xem “đã accept TCP” đồng nghĩa “cho phép vô hạn requests mới sau cutoff”. Web framework/proxy cần phối hợp drain persistent connections. Với HTTP/2, cơ chế như GOAWAY có thể được implementation hỗ trợ để không nhận streams mới trong khi streams cũ tiếp tục, nhưng **không giả định JDK `HttpServer` đơn giản tự hỗ trợ HTTP/2/GOAWAY**. Cần dựa vào runtime thực tế.

### 9.3. WebSocket/SSE cần policy riêng

WebSocket và SSE là các phiên/stream dài hạn, có thể chạy nhiều giờ. Không thể đơn giản “chờ cho đến khi mọi connection tự đóng” trước deploy. Nên gửi signal application như `server-draining` hoặc WebSocket Close (ví dụ code `1001 Going Away` nếu phù hợp), đặt deadline để client reconnect/subscribe lại; lưu sequence/cursor và durable state cho resume. Với SSE, client có thể cần reconnect tới node khác và dùng event IDs nếu server hỗ trợ. Đóng connection không tự bảo đảm message đã được business ACK.

## 10. Shutdown hook, SIGTERM và thứ tự khi process thoát

Trong Java:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            // Gọi duy nhất một shutdown coordinator idempotent.
            // Không block vô hạn.
            service.requestShutdown();
        }, "shutdown-hook"));
~~~

Đây là **mã minh họa**, `service` đại diện đối tượng ứng dụng có phương thức `requestShutdown`. Shutdown hook thường chạy khi JVM bắt đầu shutdown có thứ tự (ví dụ `System.exit` hoặc tín hiệu termination được xử lý theo cơ chế JVM/OS), nhưng **không đảm bảo chạy khi process bị kill cưỡng bức**, OS crash hoặc `Runtime.halt`.

### 10.1. Nhiều shutdown hooks không có thứ tự tự động

Nếu application, thư viện metrics, database và broker mỗi nơi tự đăng ký một hook, **không có cam kết thứ tự chạy nối tiếp như bạn muốn**. Các hooks có thể chạy đồng thời trong quá trình shutdown. Ví dụ DB pool hook đóng trước khi request handlers của hook khác hoàn tất sẽ gây lỗi. Nên dùng **một lifecycle coordinator** hoặc framework lifecycle quản lý **dependency graph** và termination, không dựa vào may mắn về hook order.

### 10.2. Đừng gọi `System.exit` từ handler để “dừng graceful”

Một HTTP handler gọi `System.exit(0)` ngay khi nhận admin request có thể kết thúc process trong lúc các request khác đang in-flight. Nếu cần endpoint điều khiển, nó nên yêu cầu lifecycle coordinator chuyển sang draining, trả một xác nhận mang semantics rõ, rồi coordinator thực hiện shutdown theo deadline. Bảo vệ admin endpoint bằng authentication/authorization và audit; tránh cho người lạ dừng service.

### 10.3. Signals và orchestrator

- **SIGTERM** thường biểu thị yêu cầu graceful termination trong Unix-like environment; Java shutdown hook có thể được dùng nếu runtime đã cấu hình đúng.
- **SIGKILL** không thể bị xử lý bởi Java hook; không có cleanup logic chạy khi nhận kill cưỡng bức.
- Trong containers, termination grace period là **ngân sách tổng** trước khi có thể bị force kill; phối hợp readiness, load balancer drain và thời gian shutdown nội bộ.
- Không giả định OS/Windows xử lý các signals giống nhau. Kiểm tra môi trường triển khai thật.
- Service phải có **durable recovery** nếu mất điện hoặc kill không có cơ hội shutdown.

## 11. Khả năng chịu lỗi: hoàn tất request không có nghĩa không có trùng lặp

Một tình huống khó:

~~~text
Client --> POST createOrder(id=77) --> Server
Server --> DB COMMIT thành công
Server --> gửi 201 Created
         X process bị kill/mất mạng trước khi client nhận response
Client --> retry POST ?
~~~

Client không biết server đã commit hay chưa. Graceful shutdown có thể cố gắng gửi response, nhưng không tạo bảo đảm **exactly-once từ đầu tới cuối**. Với operations có side effects:

- Dùng **idempotency key** ổn định cho cùng thao tác khi API hỗ trợ.
- Server lưu kết quả đã xử lý gắn request ID/transaction ID.
- Nếu cần, client có endpoint **query status** trước khi retry.
- Database transaction cần atomicity và cleanup đúng.
- Với queue/broker, commit/ACK và side effect phải có consistency strategy (outbox/inbox, idempotent consumer, transaction tùy hệ thống).
- Sau forced shutdown, dữ liệu có thể ở trạng thái “unknown” từ góc nhìn client; phải **reconcile** chứ không tự báo fail hay retry vô hạn.

### 11.1. Message queue: ACK khi nào?

Ví dụ consumer nhận message, thực hiện DB update và ACK broker. Nếu ACK **trước khi** DB commit, crash có thể làm mất công việc. Nếu DB commit **trước khi** ACK rồi crash, broker có thể redeliver và DB update được thực hiện lại. Cần **idempotent handler**, unique constraint và transaction/outbox/inbox theo yêu cầu để chịu được cả hai hướng. Một shutdown tốt cho consumer là stop poll, drain in-flight, commit/ACK những phần đã thành công, rồi close consumer/producer theo contract; không tuyên bố “không mất một message nào” chỉ dựa vào awaitTermination.

### 11.2. Long-running jobs cần checkpoint

Một job kéo dài 2 giờ không thể luôn hoàn tất trong 30 giây shutdown grace period. Nên chia thành checkpoints, lưu offset/phase/task ID và cho worker mới resume an toàn. Khi shutdown, dừng nhận job mới, yêu cầu job hiện tại checkpoint trong deadline, release lease/lock phù hợp. Không giả vờ drain hoàn tất chỉ vì thread được interrupt nhưng job state chưa được lưu.

## 12. Quan sát/metrics: biết mình đã thực sự dừng hay chưa

Một số metrics/logs hữu ích:

| Tín hiệu | Cần theo dõi |
| --- | --- |
| `shutdown_state` | RUNNING / DRAINING / STOPPING / STOPPED |
| `readiness` | 0 ngay khi ngừng nhận công việc |
| `active_requests` / `in_flight_tasks` | Số công việc đang thực sự xử lý |
| `queued_tasks` | Số accepted tasks chờ executor |
| `active_connections` | Socket/WebSocket/SSE đang mở |
| `drain_duration_seconds` | Thời gian từ cutoff tới khi in-flight hoàn tất |
| `forced_shutdown_count` | Số lần cần `shutdownNow` hoặc đóng cứng sockets |
| `unfinished_tasks` | Tasks còn tồn hoặc bị bỏ lại vì deadline |
| `last_acknowledged_id` | Cursor/id giao dịch cuối đã commit theo policy |
| `response_abort_count` | Response mất/truncated khi connection đóng |
| `queue_redeliveries` | Có tăng đột biến sau restart không? |
| `executor_termination_time` | Có thread bất hợp tác khi shutdown không? |

Ghi log sự kiện `shutdown_requested`, `admission_closed`, `drain_started`, `drain_completed`/`drain_timeout` và `dependencies_closed`, kèm deadline còn lại và correlation ID không lộ bí mật. Không log bearer tokens, cookies, body chứa PII hoặc credentials.

### 12.1. Readiness khác liveness

Trong giai đoạn `DRAINING`, service có thể vẫn **sống và chủ động hoàn thành request**, nhưng không nên nhận thêm traffic:

~~~text
/readiness -> FAIL (không route request mới)
/liveness  -> OK   (process chưa bị kẹt; đang drain có chủ ý)
~~~

Nếu đặt liveness fail ngay khi drain bắt đầu, orchestrator có thể restart/kill trước khi các tasks hoàn tất. Cách cấu hình probes cụ thể tùy platform, nhưng **tách mục đích của hai probes** rất quan trọng.

## 13. Các lỗi thường gặp khi dừng server Java

| Sai lầm | Triệu chứng | Sửa thế nào |
| --- | --- | --- |
| `System.exit(0)` ngay khi nhận signal | Request bị cắt giữa chừng | Dùng lifecycle coordinator và deadline |
| `workers.shutdown()` rồi vẫn `accept()` | Accept xong nhưng task bị reject, client có thể treo | Dừng listener/admission trước |
| Gọi `awaitTermination` mà chưa `shutdown` | Pool có thể vẫn nhận việc và không kết thúc | `shutdown` trước, `awaitTermination` sau |
| Nghĩ `shutdown()` đợi xong | DB/metrics đóng khi worker đang chạy | Chờ `awaitTermination`/active count |
| Dùng `shutdownNow()` ngay cho mọi deploy | Đang xử lý mất ACK/response | Hai pha graceful rồi forced |
| Nghĩ `shutdownNow` dừng mọi thread ngay | Worker vẫn block, process không thoát | Interrupt cooperative, close sockets/deadlines |
| Đóng accepted sockets cùng listener | In-flight request bị reset | Đóng listening socket trước; accepted sockets drain |
| Coi intentional `SocketException` từ `accept()` là lỗi hệ thống | Log spam, false alert | Kiểm tra stopping state |
| Không xử lý race accept/submit | Socket leak hoặc rejected tasks | Kiểm tra state và catch rejection, close |
| Queue không giới hạn | Shutdown quá lâu; OOM trước shutdown | Bounded queue/admission từ lúc RUNNING |
| Đóng DB/broker trước khi handlers commit | Giao dịch thất bại, missed ACK | Dựa dependency order |
| Đợi stream/WebSocket vô hạn | Deploy không thể hoàn tất | Drain signal, close deadline, resume |
| Mọi bước được chờ 30s riêng | Tổng 150s vượt grace period | Deadline tổng và budget còn lại |
| Chỉ dựa shutdown hook | SIGKILL/power loss mất dữ liệu | Durable state/idempotency |
| Tưởng hooks chạy tuần tự | DB hook đóng sớm | Một coordinator có thứ tự |
| Trả success ngay khi vào executor queue | Task chưa được durable | ACK sau commit hoặc semantics accepted rõ |
| Không phân biệt timeout client/server | Có thể retry side effect trùng | Idempotency, status lookup và deadline |
| Không shutdown scheduler | Job vẫn tạo task mới khi pool đang drain | Stop periodic triggers trước |
| Đóng log/tracing trước drain | Không có log lỗi cuối | Flush sau handlers, có budget |
| Coi `isShutdown` là `isTerminated` | Báo service stopped sai | Đối chiếu terminated và active resources |
| Test bằng sleep ngẫu nhiên | Flaky/không chứng minh thứ tự | Dùng latch/barrier, mock timers và in-flight counters |
| Tự restart `HttpServer` đã stop | Không hoạt động | Khởi tạo instance server mới |

## 14. Bài tập tình huống có đáp án

### Bài A — Dừng TCP listener nhưng còn client đang xử lý

Service có một worker đang đọc request và một accept thread đang chờ connection mới. Khi deploy, có nên đóng mọi accepted `Socket` ngay không?

**Đáp án:** không nếu muốn graceful drain. Trước tiên ngăn nhận connections mới bằng `listener.close()`, dùng flag để xử lý race; sau đó cho accepted request hiện tại kết thúc trong deadline, trả response rồi đóng socket đó. Khi hết deadline, có thể force close theo policy.

### Bài B — Gọi `shutdown()` rồi đóng database

Code:

~~~java
workers.shutdown();
dbPool.close();
~~~

**Đáp án:** có thể sai. `shutdown()` chỉ ngừng nhận task mới, **không đợi task đang chạy hoặc queued xong**. Nếu chúng vẫn dùng DB, đóng pool sớm tạo lỗi. Cần chờ termination/drain kết quả trước khi đóng dependency.

### Bài C — `shutdownNow()` trả về 12 Runnable

Đội gọi `shutdownNow()` sau deadline và nhận một `List<Runnable>` gồm 12 tasks. Điều đó có nghĩa 12 tasks đã hoàn thành hay chắc chắn sẽ rollback?

**Đáp án:** không. Danh sách mô tả tasks **chưa bắt đầu** bị rút khỏi queue; nó không tự lưu/requeue chúng. Các tasks đã chạy chỉ bị yêu cầu ngắt và có thể vẫn hoạt động. Cần task IDs/durable state để xử lý phần chưa hoàn tất.

### Bài D — HTTP server JDK `stop(10)`

Có một HTTP request mất 30s. Gọi `server.stop(10)` trong shutdown coordinator. Server có đợi đúng 10s rồi chắc chắn request thành công không?

**Đáp án:** không. `stop(10)` chờ đến khi active handlers hoàn tất **hoặc xấp xỉ 10s** (điều kiện nào trước), rồi đóng TCP connections còn lại. Request 30s có thể bị cắt. `delay` là giây và server object không restart được.

### Bài E — Worker không tuân interrupt

Một worker block trong socket read vô hạn. Sau `shutdownNow` pool không kết thúc, `awaitTermination` trả false.

**Đáp án:** không lặp gọi `shutdownNow` vô hạn. Thiết kế từ trước với read timeout/close socket/cancel-aware I/O và bounded work; đến deadline đóng active sockets được theo dõi, ghi nhận forced abort/recovery. `Thread.stop` không phải giải pháp an toàn.

### Bài F — Queue consumer ACK quá sớm

Consumer ACK message ngay sau khi đưa việc vào volatile executor queue; trước khi worker commit DB thì JVM bị kill.

**Đáp án:** có thể mất message vì broker tưởng đã xử lý. ACK theo outcome durable, hoặc thiết kế inbox/outbox/idempotency. Graceful shutdown không cứu được process bị kill không kịp chạy hook.

### Bài G — Rolling deploy và readiness

Ứng dụng đổi trạng thái DRAINING nhưng load balancer vẫn route request mới một vài giây. Có cần cơ chế ở application nữa không?

**Đáp án:** có. Readiness propagation không tức thời; thêm admission guard, config drain của proxy/LB, tính đến persistent connections và request races. Đừng shutdown executor trước khi thật sự dừng ingress.

### Bài H — WebSocket đang mở hàng giờ

Service có 10.000 WebSocket sessions. Mục tiêu shutdown trong 20s. Có thể `awaitTermination` vô hạn cho mọi session đóng tự nhiên không?

**Đáp án:** không. Cần thông báo server draining, Close/redirect/reconnect policy phù hợp, chuyển cursor/subscriptions sang durable store hoặc cho client resubscribe, deadline và forced cleanup có metrics.

### Bài I — Bốn bước, mỗi bước 15s

Pod có grace period 30s, code chờ listener 15s, tasks 15s, DB 15s, tracing 15s.

**Đáp án:** ngân sách cộng dồn tối đa 60s vượt 30s, có thể bị force kill trước khi flush. Dùng **deadline tổng 30s hoặc ngắn hơn có khoảng dự phòng**, mỗi bước dùng **remaining time**.

### Bài J — 200 OK nhưng client không nhận

Server commit order, gửi 200, kết nối đứt khi shutdown; client không nhận response và retry POST.

**Đáp án:** nguy cơ trùng order dù server đã commit. Dùng idempotency key/unique operation ID hoặc query trạng thái; gracefully waiting không tạo exactly-once sau mọi network failures.

### Bài K — Hook theo thứ tự không dự đoán

Framework DB đăng ký shutdown hook riêng; service cũng đăng ký hook để đợi workers. Có thể khẳng định hook service luôn chạy trước DB không?

**Đáp án:** không nên phụ thuộc. JVM không bảo đảm thứ tự tuần tự giữa các hooks; dùng lifecycle coordinator hoặc framework có dependency ordering.

### Bài L — `isShutdown` true và `isTerminated` false

Sau `pool.shutdown()`, quan sát `isShutdown()==true` nhưng `isTerminated()==false`.

**Đáp án:** đây là trạng thái hợp lệ: đã từ chối tasks mới nhưng còn task chạy/queued. Tiếp tục `awaitTermination` có deadline rồi escalate nếu cần, không báo đã STOPPED.

### Bài M — Đóng DB trước broker producer

Workers xử lý event xong sẽ publish kết quả qua broker, sau đó cập nhật DB. Nếu shutdown đóng broker producer trước khi workers drain, lỗi gì?

**Đáp án:** workers không còn nơi publish, các bước nghiệp vụ không hoàn tất. Thứ tự đóng phải bám dependency của công việc cụ thể (có thể publish trước/hoặc sau DB theo contract/outbox), nhưng cả hai tài nguyên phải còn khả dụng đến khi công việc ngừng dùng chúng.

### Bài N — Dùng `Thread.sleep` để tin là đã drain

Sau signal shutdown, main `Thread.sleep(5000)` rồi kill process, không đo active requests.

**Đáp án:** sleep không chứng minh gì về trạng thái tasks; server có thể drain sau 1s hoặc còn request chạy 20s. Dùng futures, `awaitTermination`, active count, sockets/tracing và bounded deadlines.

## 15. Checklist trước khi triển khai graceful shutdown

- [ ] Có trạng thái `RUNNING -> DRAINING -> STOPPING -> STOPPED` rõ ràng và chống shutdown lặp?
- [ ] Readiness đổi **not ready** trước khi yêu cầu route traffic mới ngừng?
- [ ] Đã đóng listener/stop polling/stop scheduler và có admission guard trong ứng dụng?
- [ ] Có xử lý race `accept`/`execute` và `RejectedExecutionException`, không leak socket?
- [ ] Đã xác định drain scope: **running tasks**, **queued tasks**, active streams, delayed jobs?
- [ ] Có **overall deadline** và reserved time cho close/telemetry trước force kill?
- [ ] Dùng `shutdown()` rồi `awaitTermination(...)`, không nhầm `isShutdown` với `isTerminated`?
- [ ] Chỉ `shutdownNow()` sau khi hết grace window và ghi nhận unfinished work?
- [ ] Worker có hỗ trợ interrupt/deadline/cancellation và đóng sockets khi cần?
- [ ] Đã có active sockets/request counters và kết quả handler được quan sát?
- [ ] Đã để DB/broker/HTTP clients còn sống cho tới khi tasks sử dụng xong?
- [ ] Có response/ACK/commit semantics và **idempotency keys** cho requests có side effects?
- [ ] Queue messages ACK/offset commit đúng, durable jobs có checkpoint/recovery?
- [ ] WebSocket/SSE có close/draining signal và reconnect/resubscribe policy?
- [ ] Không dựa hoàn toàn vào shutdown hooks để bảo đảm dữ liệu khi SIGKILL?
- [ ] Đã có metrics/logs: drain duration, active requests, queue size, forced abort, unfinished IDs?
- [ ] Có test service shutdown khi 0, 1 và nhiều requests đang chạy, task fail/interrupt?
- [ ] Đã test rapid repeated termination signals, listener-close race, executor rejection và timeout?
- [ ] Đã test rolling deploy, readiness propagation, proxy keep-alive, pod grace period và slow clients?
- [ ] Sau shutdown, threads/file descriptors/sockets/pools đã kết thúc không còn leak?

**Kết luận:** Trong Java networking, dừng service đúng không phải **“đóng mọi thứ càng nhanh càng tốt”**, mà là **“khóa cửa trước, xử lý hết khách đang phục vụ trong ngân sách có hạn, rồi tắt các hệ thống phụ thuộc theo thứ tự”**. `ServerSocket.close()` ngắt accept nhưng không tự giết accepted sockets; `ExecutorService.shutdown()` ngăn tasks mới nhưng không chờ; `awaitTermination` chờ có hạn; `shutdownNow` chỉ best-effort cancel; `HttpServer.stop(delay)` là cơ chế riêng có thời hạn theo giây. Khả năng phục hồi sau deadline/kill đòi **durable state, idempotency và observable outcomes**, không thể chỉ dựa vào shutdown hook.

## 16. Tài liệu chính thức

- **Oracle Java 17 — ExecutorService:** `shutdown`, `awaitTermination`, `shutdownNow` và mẫu dừng hai pha. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Oracle Java 17 — ServerSocket:** `close()` khiến `accept()` đang block ném `SocketException`. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- **Oracle Java 17 — Socket:** lifecycle/`setSoTimeout` của accepted connections. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- **Oracle Java 17 — HttpServer:** `stop(delay)`, `setExecutor`, `start()`. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- **Oracle Java 17 — ScheduledThreadPoolExecutor:** shutdown policies của delayed/periodic tasks. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
- **Oracle Java 17 — Runtime.addShutdownHook:** lifecycle JVM và giới hạn shutdown hooks. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- **RFC 9110 — HTTP Semantics:** trạng thái 503, retry và response semantics. https://www.rfc-editor.org/rfc/rfc9110

Với một hệ thống thực, hãy đối chiếu thêm tài liệu runtime/proxy/queue/broker và **chạy thử shutdown dưới tải thật**, vì việc client có nhận phản hồi hay server có bảo toàn durable side effects còn phụ thuộc vào toàn bộ đường đi và kiến trúc ứng dụng.