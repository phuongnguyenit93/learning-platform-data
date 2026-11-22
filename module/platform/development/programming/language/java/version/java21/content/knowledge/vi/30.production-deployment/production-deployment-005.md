# Graceful shutdown với executor, HTTP client và tác vụ đang chạy

Graceful shutdown là quá trình dừng một ứng dụng theo thứ tự có kiểm soát: ngừng nhận công việc mới, cho các tác vụ đã tiếp nhận cơ hội hoàn tất, đóng các tài nguyên phụ thuộc và chỉ chuyển sang dừng cưỡng bức khi hết thời gian cho phép. Trên Java 21, `ExecutorService` và `HttpClient` đều có API lifecycle riêng; cần điều phối cả hai vì executor kết thúc không có nghĩa mọi HTTP exchange đã hoàn tất.

Trong phạm vi `JAVA_VERSION_JAVA21`, bài học tập trung vào cách triển khai shutdown production cho ứng dụng Java 21, gồm platform-thread executor, virtual-thread-per-task executor và `java.net.http.HttpClient`. Các API được dùng đều ổn định trong Java 21. Yêu cầu nội dung là chỉ sử dụng kiến thức còn áp dụng hiện nay; vì vậy, ví dụ dựa trên `ExecutorService`, `HttpClient` và interruption hiện hành, không dựa vào cơ chế dừng thread đã lỗi thời.

## Mục tiêu của graceful shutdown

Khi tiến trình nhận tín hiệu dừng từ orchestrator, service manager hoặc người vận hành, ứng dụng thường phải xử lý đồng thời nhiều loại công việc:

- Request inbound đang được xử lý.
- Task đã submit vào `ExecutorService` nhưng chưa chạy hoặc đang chạy.
- HTTP request outbound đang được gửi bằng `HttpClient.send()` hoặc `sendAsync()`.
- Callback bất đồng bộ có thể tiếp tục submit task hoặc gọi dịch vụ khác.
- Tài nguyên cần đóng như response body stream, database connection, file và executor do ứng dụng sở hữu.

Shutdown tốt cần có một deadline tổng thể phù hợp với ngân sách dừng của nền tảng triển khai. Nếu chờ vô hạn, tiến trình có thể bị kill trước khi cleanup hoàn tất. Nếu dừng ngay, request đang xử lý có thể thất bại và side effect ở hệ thống từ xa có thể ở trạng thái không rõ ràng.

Một trình tự phổ biến là:

```text
Nhận tín hiệu dừng
       |
       v
Ngừng nhận request / message mới
       |
       v
Ngừng scheduler và producer tạo task
       |
       v
ExecutorService.shutdown()
       |
       +---- hết thời gian ----> shutdownNow() + interrupt task
       |                              |
       v                              v
Đợi task và workflow hoàn tất <--- chờ trong force window
       |
       v
HttpClient.shutdown()
       |
       +---- hết thời gian ----> HttpClient.shutdownNow()
       |
       v
awaitTermination() / kiểm tra trạng thái
       |
       v
Ghi nhận kết quả và kết thúc tiến trình
```

Thứ tự cụ thể phải xét dependency giữa task và HTTP client. Nếu task đang chạy còn cần gửi HTTP request, không đóng client trước khi ngừng các producer đó. Nếu callback HTTP còn cần executor để xử lý kết quả, phải giữ executor sống đến khi callback hoặc workflow tương ứng hoàn tất.

## Phân biệt lifecycle của ExecutorService và HttpClient

Hai API có tên phương thức tương tự nhưng quản lý hai loại hoạt động khác nhau:

| API | `ExecutorService` | `HttpClient` trong Java 21 |
| --- | --- | --- |
| `shutdown()` | Ngừng nhận task mới; task đã submit tiếp tục được thực thi | Ngừng nhận request mới; exchange đã submit được phép hoàn tất |
| `shutdownNow()` | Cố gắng interrupt task đang chạy và trả về các task chưa bắt đầu | Cố gắng dừng exchange đang hoạt động và ngừng xử lý exchange đang chờ |
| `awaitTermination(...)` | Chờ executor kết thúc trong thời hạn | Chờ client kết thúc trong thời hạn `Duration` |
| `isTerminated()` | Kiểm tra executor đã kết thúc | Kiểm tra client đã kết thúc |
| `close()` | Shutdown có trật tự và chờ task hoàn tất | Shutdown có trật tự và chờ exchange hoàn tất; interruption làm shutdown được nâng cấp theo hợp đồng HttpClient |

`ExecutorService.shutdownNow()` trả về `List<Runnable>` chứa task chưa bắt đầu. Nó không trả danh sách task đang chạy và không bảo đảm task đang chạy sẽ dừng. `HttpClient.shutdownNow()` không trả danh sách task; nó chỉ yêu cầu dừng các exchange theo khả năng của implementation.

`ExecutorService` có `isShutdown()` để biết shutdown đã được khởi tạo. `HttpClient` không cung cấp `isShutdown()`; với client, `isTerminated()` chỉ cho biết client đã kết thúc hoàn toàn. Một client đã nhận `shutdown()` nhưng còn exchange đang chạy vẫn chưa terminated.

## Dừng ingress và các nguồn tạo công việc trước

Lời gọi `executor.shutdown()` không tự ngừng HTTP server, message consumer, scheduler hoặc callback đang chạy ở nơi khác. Những thành phần này có thể tiếp tục submit task và nhận `RejectedExecutionException` sau khi executor đóng.

Khi bắt đầu shutdown:

1. Đánh dấu service đang dừng để health/readiness endpoint không còn báo nhận traffic mới.
2. Ngừng accept request inbound hoặc đưa instance ra khỏi load balancer theo cơ chế của nền tảng.
3. Dừng scheduler, polling loop, message consumer và các producer có thể tạo task mới.
4. Chờ hoặc từ chối các request inbound mới theo chính sách server; chỉ sau đó mới bắt đầu drain executor.
5. Theo dõi số request/task đang xử lý để biết hệ thống đã thật sự ngừng nhận công việc mới.

Không chỉ dựa vào một biến boolean trong application nếu vẫn còn đường submit task từ scheduler hoặc callback. Mọi nguồn tạo công việc cần được đóng hoặc điều phối qua cùng một lifecycle coordinator.

## Dùng shutdown và awaitTermination cho executor

`shutdown()` là lựa chọn đầu tiên khi muốn cho task đã submit hoàn tất:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

ExecutorService workers = Executors.newFixedThreadPool(8);

// Sau khi đã ngừng ingress và mọi producer tạo task mới:
workers.shutdown();

if (!workers.awaitTermination(20, TimeUnit.SECONDS)) {
    workers.shutdownNow();

    if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
        System.err.println("Executor vẫn còn task sau force window");
    }
}
```

`awaitTermination()` chỉ chờ sau khi shutdown đã được gọi. Nó trả `true` nếu executor terminated trước khi hết timeout và `false` nếu hết timeout trước. Nếu thread điều phối bị interrupt, phương thức ném `InterruptedException`.

`shutdownNow()` cố gắng dừng task đang chạy bằng interruption và trả về các task chưa bắt đầu. Task cần hợp tác với interruption thì mới có thể kết thúc đúng cách. Một task đang gọi API không hỗ trợ interrupt hoặc cố tình bỏ qua interrupt có thể tiếp tục chạy sau lời gọi `shutdownNow()`.

## Viết task có thể dừng an toàn

Task dài nên kiểm tra interrupt ở các điểm có thể dừng an toàn và cleanup tài nguyên trong `finally` hoặc try-with-resources:

```java
import java.util.concurrent.atomic.AtomicBoolean;

final class ImportTask implements Runnable {
    private final AtomicBoolean stopped;

    ImportTask(AtomicBoolean stopped) {
        this.stopped = stopped;
    }

    @Override
    public void run() {
        try (var input = openInput(); var output = openOutput()) {
            while (!stopped.get() && !Thread.currentThread().isInterrupted()) {
                var batch = readNextBatch(input);
                if (batch.isEmpty()) {
                    break;
                }
                writeBatch(output, batch);
            }
        } catch (InterruptedException e) {
            // Nếu tầng này không thể propagate exception, khôi phục interrupt status.
            Thread.currentThread().interrupt();
        } catch (IOException e) {
            reportImportFailure(e);
        }
    }

    // Các helper đại diện cho API I/O và nghiệp vụ của ứng dụng.
}
```

Ví dụ giả định helper I/O có thể ném `IOException` hoặc `InterruptedException` phù hợp với chữ ký thật. Trong mã production, nếu phương thức gọi có thể khai báo `InterruptedException`, thường nên propagate exception để tầng trên quyết định dừng. Nếu phải bắt tại ranh giới `Runnable`, hãy khôi phục interrupt status sau khi cleanup.

Không bắt `InterruptedException` rồi bỏ qua. Khi `InterruptedException` được ném, interrupt status thường đã bị clear; nếu không propagate, hãy gọi `Thread.currentThread().interrupt()` để giữ tín hiệu cho tầng trên. Tránh dùng `Thread.stop()` hoặc các cách cưỡng bức dừng thread không an toàn.

## Hủy Future và task chưa bắt đầu

Nếu ứng dụng submit bằng `submit()`, hãy giữ `Future` khi cần hủy task hoặc quan sát kết quả:

```java
Future<?> importFuture = workers.submit(new ImportTask(stopped));

// Khi chính sách shutdown yêu cầu hủy task cụ thể:
boolean cancellationRequested = importFuture.cancel(true);
```

`cancel(true)` yêu cầu interrupt thread đang thực thi task nếu task đã bắt đầu. Nó không bảo đảm task đã cleanup hoặc dừng hoàn toàn khi phương thức trả về. `isCancelled()` và `isDone()` mô tả trạng thái Future; chúng không thay thế việc kiểm tra executor đã terminated hay chưa.

Với task đang xếp hàng, `shutdownNow()` trả các `Runnable` chưa bắt đầu. Nếu chúng là `Future` như các wrapper được tạo bởi `submit()`, ứng dụng có thể đánh dấu chúng cancelled:

```java
import java.util.List;
import java.util.concurrent.Future;

List<Runnable> neverStarted = workers.shutdownNow();
for (Runnable task : neverStarted) {
    if (task instanceof Future<?> future) {
        future.cancel(false);
    }
}
```

Không phải mọi `Runnable` đều là `Future`, đặc biệt với task gửi qua `execute()`. Nếu ứng dụng cần biết chính xác task nào đã bị hủy hoặc chưa chạy, nên duy trì registry task/Future ở tầng ứng dụng và cập nhật trạng thái một cách tường minh.

## Dùng HttpClient để drain HTTP exchange

Java 21 bổ sung lifecycle API cho `HttpClient`. Sau khi mọi thành phần có thể tạo request mới đã được dừng, gọi `shutdown()` để client ngừng nhận request mới và cho exchange đã submit cơ hội hoàn tất:

```java
import java.net.http.HttpClient;
import java.time.Duration;

static boolean stopHttpClient(HttpClient client) throws InterruptedException {
    client.shutdown();

    if (client.awaitTermination(Duration.ofSeconds(10))) {
        return true;
    }

    client.shutdownNow();
    return client.awaitTermination(Duration.ofSeconds(2));
}
```

`awaitTermination(Duration)` trả `true` nếu client terminated trong thời hạn và `false` nếu hết thời gian chờ. Nó có thể ném `InterruptedException` nếu thread điều phối bị interrupt. `shutdownNow()` chỉ là yêu cầu best-effort đối với exchange đang hoạt động; nó không rollback thao tác mà server đã thực hiện.

Đối với request có side effect như thanh toán, tạo đơn hàng hoặc cập nhật dữ liệu, việc client không nhận được response không chứng minh server chưa thực hiện thao tác. Dùng idempotency key, trạng thái nghiệp vụ và cơ chế đối soát để xử lý kết quả không xác định.

## Phân biệt task kết thúc với HTTP exchange kết thúc

Một task executor có thể gọi `sendAsync()` rồi return ngay:

```java
workers.submit(() -> {
    client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
            .thenAccept(this::processResponse);
});
```

Trong ví dụ này, task của `workers` có thể kết thúc ngay sau khi đăng ký callback, trong khi HTTP exchange vẫn đang chạy. Vì vậy:

- `workers.awaitTermination(...) == true` chỉ xác nhận task của executor đã kết thúc.
- Nó không xác nhận các `CompletableFuture` do `HttpClient` tạo đã hoàn tất.
- `client.awaitTermination(...) == true` xác nhận các hoạt động do client quản lý đã kết thúc.
- Nếu callback dùng `thenApplyAsync(..., workers)` hoặc submit task tiếp theo vào executor, executor phải còn hoạt động đến khi callback đó hoàn tất.

Với workflow bất đồng bộ, hãy theo dõi một future đại diện cho toàn bộ workflow thay vì chỉ future của thao tác submit ban đầu. Ví dụ:

```java
CompletableFuture<Result> workflow = client.sendAsync(
                request, HttpResponse.BodyHandlers.ofString())
        .thenApplyAsync(this::parseResponse, workers)
        .thenApplyAsync(this::updateApplicationState, workers);

inFlightWorkflows.add(workflow);
workflow.whenComplete((result, error) -> inFlightWorkflows.remove(workflow));
```

Khi dừng ingress, ngừng tạo workflow mới và chờ registry `inFlightWorkflows` về rỗng trong deadline đã định. Điều này giữ executor sống cho các callback async cần nó. Sau khi các workflow đã hoàn tất hoặc đã được hủy theo chính sách, mới shutdown executor và HttpClient theo dependency thực tế.

Không dùng `CompletableFuture.allOf(...)` trên một snapshot không được đồng bộ nếu vẫn có producer thêm future mới. Registry cần cơ chế đóng nhận việc mới trước khi chụp tập future cần drain.

## Điều phối một deadline tổng thể

Mỗi giai đoạn cần một phần ngân sách shutdown. Dùng `System.nanoTime()` để tính thời gian còn lại vì đây là đồng hồ đơn điệu, không bị thay đổi bởi đồng bộ giờ hệ thống. Không cộng các timeout độc lập mà quên rằng tổng thời gian có thể vượt ngân sách của orchestrator.

Ví dụ dưới đây dành khoảng một phần ba deadline cho graceful drain của executor, một phần ba cho force window của executor, một phần sáu cho graceful drain của HTTP client và phần còn lại cho force window của client. Tỷ lệ này chỉ là chính sách minh họa; điều chỉnh theo SLO và thời gian dừng mà nền tảng cho phép.

```java
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

record ShutdownReport(
        boolean executorTerminated,
        boolean httpClientTerminated,
        int queuedTasksCancelled) {}

static boolean awaitExecutorUntil(ExecutorService executor, long deadlineNanos)
        throws InterruptedException {
    if (executor.isTerminated()) {
        return true;
    }
    long remaining = deadlineNanos - System.nanoTime();
    return remaining > 0
            && executor.awaitTermination(remaining, TimeUnit.NANOSECONDS);
}

static boolean awaitClientUntil(HttpClient client, long deadlineNanos)
        throws InterruptedException {
    if (client.isTerminated()) {
        return true;
    }
    long remaining = deadlineNanos - System.nanoTime();
    return remaining > 0
            && client.awaitTermination(Duration.ofNanos(remaining));
}

static ShutdownReport shutdownRuntime(
        ExecutorService workers, HttpClient client, Duration totalBudget) {
    long started = System.nanoTime();
    long budgetNanos = totalBudget.toNanos();
    long deadline = started + budgetNanos;
    long executorGraceDeadline = started + budgetNanos / 3;
    long executorForceDeadline = started + (budgetNanos / 3) * 2;
    long clientGraceDeadline = started + budgetNanos - budgetNanos / 6;
    int queuedCancelled = 0;

    workers.shutdown();

    try {
        boolean executorStopped = awaitExecutorUntil(
                workers, executorGraceDeadline);

        if (!executorStopped) {
            List<Runnable> neverStarted = workers.shutdownNow();
            for (Runnable task : neverStarted) {
                if (task instanceof Future<?> future && future.cancel(false)) {
                    queuedCancelled++;
                }
            }
            executorStopped = awaitExecutorUntil(workers, executorForceDeadline);
        }

        if (!executorStopped) {
            System.err.println("Executor chưa terminated; HTTP client sẽ ngừng nhận request mới");
        }

        // Chỉ đến đây khi các producer đã được dừng hoặc đã chạm force deadline.
        client.shutdown();
        boolean clientStopped = awaitClientUntil(client, clientGraceDeadline);

        if (!clientStopped) {
            client.shutdownNow();
            clientStopped = awaitClientUntil(client, deadline);
        }

        return new ShutdownReport(
                workers.isTerminated(), client.isTerminated(), queuedCancelled);
    } catch (InterruptedException e) {
        // Người điều phối bị interrupt: yêu cầu dừng cưỡng bức cả hai tài nguyên.
        workers.shutdownNow();
        client.shutdownNow();
        Thread.currentThread().interrupt();

        return new ShutdownReport(
                workers.isTerminated(), client.isTerminated(), queuedCancelled);
    }
}
```

Phương thức trên giả định ingress, scheduler và các producer khác đã được dừng trước khi gọi. Nếu executor vẫn còn task sau force window, client sẽ bắt đầu shutdown và các request mới từ task còn sống có thể bị từ chối; đây là lựa chọn để tôn trọng deadline tổng thể. Kết quả trả về phản ánh trạng thái thực tế tại thời điểm kiểm tra, không tuyên bố tài nguyên đã kết thúc nếu vẫn còn task/exchange.

Trong mã thật, hãy validate `totalBudget` là dương và đủ lớn cho các giai đoạn. Các registry Future đang chạy, workflow bất đồng bộ, callback và các tài nguyên khác cần được quản lý bổ sung theo kiến trúc ứng dụng. Khi thread điều phối bị interrupt, ví dụ lập tức yêu cầu `shutdownNow()` và khôi phục interrupt status; hệ thống giám sát cần ghi nhận nếu tài nguyên chưa terminated.

## Xử lý interruption trong shutdown coordinator

Shutdown coordinator thường chạy trong hook hoặc thread quản lý vòng đời. Nếu thread này bị interrupt trong lúc `awaitTermination()`:

1. Ghi nhận việc shutdown bị gián đoạn.
2. Gọi `shutdownNow()` cho executor và HTTP client theo chính sách force.
3. Không nuốt tín hiệu interrupt; khôi phục interrupt status nếu đã bắt `InterruptedException`.
4. Ghi nhận trạng thái terminated thực tế và cảnh báo nếu còn hoạt động.

Không gọi `Thread.interrupted()` chỉ để xóa cờ interrupt rồi tiếp tục chờ vô hạn. Nếu cần một khoảng cleanup cuối, hãy thiết kế rõ cách xử lý interruption và deadline; đừng làm mất tín hiệu dừng của thread điều phối.

## Try-with-resources và thứ tự đóng tài nguyên

`ExecutorService` và `HttpClient` đều có thể dùng với try-with-resources trong Java 21. Tài nguyên được đóng theo thứ tự ngược với thứ tự khai báo. Nếu executor chứa task sử dụng HTTP client, khai báo client trước và executor sau để executor được đóng trước:

```java
try (HttpClient client = HttpClient.newHttpClient();
     ExecutorService workers = Executors.newFixedThreadPool(8)) {

    workers.submit(() -> callRemoteService(client));
    workers.submit(() -> processAnotherTask());
}
// Đóng ngược thứ tự: workers trước, sau đó client.
```

`ExecutorService.close()` chờ task đã submit hoàn tất. Sau khi workers đóng, `HttpClient.close()` có thể drain những HTTP exchange còn đang hoạt động do task đã gửi trước đó. Nếu task cần callback async chạy trên `workers`, hãy bảo đảm workflow callback hoàn tất trước khi executor đóng.

Nếu truyền một executor do ứng dụng sở hữu vào `HttpClient.Builder.executor(...)`, client có thể dùng executor đó cho các tác vụ bất đồng bộ. Khi ấy phải giữ executor sống cho đến khi client kết thúc; thứ tự đóng cần đảo lại hoặc được điều phối tường minh. Không giả định HttpClient tự quản lý vòng đời mọi executor do ứng dụng cung cấp.

`close()` là cách gọn cho ứng dụng có thể chờ hoàn tất mà không cần deadline riêng. Với production shutdown bị giới hạn thời gian, dùng `shutdown()`, `awaitTermination()` và `shutdownNow()` tường minh để kiểm soát từng giai đoạn. `close()` của `ExecutorService` chờ task hoàn tất; nó không thay thế chính sách timeout. `HttpClient.close()` chờ exchange hoàn tất và có hành vi nâng cấp shutdown khi thread chờ bị interrupt theo hợp đồng của API.

## Virtual-thread-per-task executor

Java 21 có thể tạo executor chạy mỗi task trên một virtual thread:

```java
try (var workers = Executors.newVirtualThreadPerTaskExecutor()) {
    workers.submit(() -> handleRequest());
    workers.submit(() -> refreshCache());
}
```

Executor này vẫn tuân theo hợp đồng `ExecutorService`: `shutdown()` ngừng nhận task mới, `shutdownNow()` yêu cầu interrupt task đang chạy, `awaitTermination()` chờ task kết thúc và `close()` chờ các task hoàn tất. Virtual thread không khiến shutdown trở thành tức thời; task vẫn phải phản hồi interruption và đóng tài nguyên của nó.

Virtual-thread-per-task executor không phải pool có kích thước cố định. Nếu cần giới hạn số kết nối database, số request đến hệ thống ngoài hoặc một tài nguyên hữu hạn, dùng semaphore, connection pool hoặc giới hạn ở tầng dịch vụ. Đừng dùng số lượng virtual thread làm giới hạn concurrency cho tài nguyên bên ngoài.

## Kiểm thử shutdown trước khi triển khai

Một quy trình shutdown cần được kiểm tra như một luồng nghiệp vụ riêng:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Shutdown khi không có task | Executor và client kết thúc nhanh, trạng thái terminated chính xác |
| Có task đang chạy | Task được phép hoàn tất trong graceful window |
| Có task trong queue | Task chưa bắt đầu được xử lý theo chính sách; task bị trả về từ `shutdownNow()` được ghi nhận |
| Task bị interrupt | Task cleanup và không nuốt interruption |
| Có HTTP exchange đang chạy | `HttpClient.shutdown()` cho exchange đã submit cơ hội hoàn tất |
| Gửi HTTP request mới sau shutdown | Client từ chối request mới; lỗi được xử lý đúng |
| Có `sendAsync()` và callback | Theo dõi toàn workflow, không nhầm task submit với exchange hoàn tất |
| Response body dạng stream | Body được đọc hoặc đóng để exchange kết thúc |
| Shutdown coordinator bị interrupt | Cả hai tài nguyên nhận force request và interrupt status được bảo toàn |
| Hết deadline | Log/metric cho biết thành phần nào chưa terminated trước khi nền tảng kill tiến trình |

Ưu tiên test bằng latch hoặc barrier để điều khiển chính xác thời điểm task bắt đầu, request đến server và response được giải phóng. Tránh `Thread.sleep()` để đoán trạng thái. Test integration có thể dùng `HttpServer` trên loopback và cổng động để kiểm tra `HttpClient` mà không phụ thuộc mạng ngoài.

## Quan sát và vận hành trong production

Shutdown cần có log và metric đủ để xác định giai đoạn bị chậm:

- Thời điểm bắt đầu shutdown và thời gian còn lại trong deadline.
- Số request inbound đang xử lý khi ngừng ingress.
- Số task đang chạy, task trong queue và task bị hủy.
- Số workflow/future HTTP đang hoạt động.
- Số exchange còn lại khi gọi `HttpClient.shutdown()`.
- Số lần phải gọi `shutdownNow()` và số thành phần chưa terminated.
- Lý do task bị hủy, timeout hoặc interruption nếu có thể xác định.

Không ghi access token, request body nhạy cảm, private key hoặc dữ liệu cá nhân vào log shutdown. Log nên tập trung vào ID tương quan, loại công việc, thời lượng và trạng thái.

Ngân sách shutdown của ứng dụng phải nhỏ hơn grace period mà nền tảng triển khai cấp. Ví dụ, nếu nền tảng chỉ cho 30 giây trước khi gửi kill signal, đừng thiết kế tổng timeout nội bộ 30 giây cộng thêm thời gian cleanup. Cần dành một khoảng dự phòng để flush log, đóng telemetry và hoàn tất hook cuối cùng.

## Các lỗi thiết kế cần tránh

- **Đóng HttpClient trước executor đang tạo request:** task còn sống sẽ gọi vào client đã shutdown và nhận lỗi ngoài dự kiến.
- **Chỉ chờ executor:** `sendAsync()` có thể tiếp tục sau khi task submit ban đầu đã kết thúc.
- **Chỉ chờ HttpClient:** task application có thể vẫn chạy và tiếp tục tạo request mới nếu ingress/producer chưa dừng.
- **Coi shutdownNow là bảo đảm dừng:** interruption là yêu cầu hợp tác; task có thể không dừng kịp.
- **Nuốt InterruptedException:** làm mất tín hiệu cancellation và kéo dài shutdown.
- **Chờ vô hạn trong hook:** có thể vượt deadline của orchestrator.
- **Không đóng streaming body:** exchange có thể chưa hoàn tất và client không terminated.
- **Nhầm Future cancelled với task đã cleanup:** cần chờ executor termination hoặc trạng thái workflow thực tế.
- **Không theo dõi callback async:** callback có thể cần executor đã bị đóng hoặc tiếp tục submit công việc sau khi service ngừng nhận request.
- **Không phân biệt executor do ứng dụng sở hữu và executor truyền cho HttpClient:** đóng sai thứ tự có thể làm callback hoặc tác vụ nội bộ không thể chạy.

## Quy trình áp dụng cho ứng dụng Java 21

1. **Xác định dependency.** Liệt kê ingress, scheduler, executor, callback, HTTP client và executor do ứng dụng cung cấp.
2. **Thiết lập deadline tổng thể.** Chọn grace window và force window nằm trong ngân sách dừng của nền tảng.
3. **Ngừng nhận công việc mới.** Đưa instance ra khỏi traffic, dừng consumer và scheduler.
4. **Drain workflow đang chạy.** Theo dõi cả task đồng bộ lẫn future/callback bất đồng bộ cần executor.
5. **Shutdown executor.** Gọi `shutdown()`, chờ bằng `awaitTermination()`, sau đó mới `shutdownNow()` nếu hết grace window.
6. **Xử lý task còn lại.** Hủy Future cần thiết, ghi nhận task chưa bắt đầu và chờ force window.
7. **Shutdown HttpClient.** Khi không còn producer hợp lệ, gọi `shutdown()` và chờ exchange trong deadline.
8. **Force HTTP nếu cần.** Gọi `shutdownNow()` khi hết thời gian; không giả định server rollback side effect.
9. **Đóng tài nguyên theo dependency.** Đảm bảo response body, custom executor, telemetry và tài nguyên khác được đóng đúng thứ tự.
10. **Ghi nhận kết quả.** Báo trạng thái terminated thực tế, số task/exchange còn lại và thời gian shutdown.

Graceful shutdown trong Java 21 là một quy trình phối hợp giữa ingress, executor, task, callback và HTTP client. `shutdown()` cho công việc đã nhận cơ hội hoàn tất; `shutdownNow()` yêu cầu dừng sớm; `awaitTermination()` cung cấp điểm chờ có giới hạn. Hãy dừng producer trước, theo dõi toàn bộ workflow bất đồng bộ, đóng tài nguyên theo dependency và dùng một deadline tổng thể để ứng dụng có thể kết thúc an toàn trong giới hạn production.

## Tài liệu tham khảo

- [Oracle Java 21 API: ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java 21 API: HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java 21 API: Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Oracle Java 21 API: Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Oracle Java 21 API: Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
