# Tránh chặn nhầm event-loop khi kết hợp với thư viện bất đồng bộ

Trong ứng dụng Java 21, một thư viện bất đồng bộ thường dùng một hoặc một nhóm nhỏ **event-loop threads** để nhận sự kiện I/O, xử lý callback và chuyển tiếp kết quả. Các thread này cần quay lại scheduler nhanh để tiếp tục phục vụ kết nối khác. Nếu một callback gọi nhầm API blocking như JDBC, đọc file đồng bộ, `Future.get()` hoặc `Thread.sleep()`, event-loop có thể bị giữ lại và làm chậm nhiều request không liên quan.

Nguyên tắc quan trọng là giữ event-loop cho công việc ngắn, không blocking; dùng API bất đồng bộ khi có; và chuyển phần blocking không tránh được sang executor hoặc scheduler riêng có giới hạn. Virtual threads giúp viết mã blocking theo mô hình thread-per-task, nhưng không biến một lời gọi blocking thành non-blocking và không cho phép chặn event-loop.

## 1. Event-loop hoạt động như thế nào?

Event-loop là mô hình thực thi thường gặp trong thư viện mạng và framework bất đồng bộ. Một event-loop thread thường đảm nhiệm việc nhận sự kiện từ socket, gọi handler, chạy callback đã sẵn sàng và gửi dữ liệu đi. Một số framework có nhiều event-loop threads, mỗi thread quản lý một nhóm channel hoặc connection.

Một event-loop thường cần xử lý nhanh rồi quay lại chờ sự kiện tiếp theo:

```text
Event-loop thread:
  nhận event A -> handler A -> trả về scheduler
  nhận event B -> handler B -> trả về scheduler
  nhận event C -> handler C -> trả về scheduler

Nếu handler B blocking:
  nhận event A -> handler A -> trả về scheduler
  nhận event B -> chờ database -------------------->
  event C và các event khác phải chờ event-loop rảnh
```

Một callback blocking có thể ảnh hưởng đến tất cả connection được quản lý bởi cùng event-loop. Nếu framework có một nhóm event-loop, chỉ những connection gắn với thread bị chặn có thể chịu ảnh hưởng trực tiếp, nhưng mức độ vẫn có thể lớn.

Tên và cách cấu hình event-loop phụ thuộc thư viện. Netty dùng `EventLoop`/`EventLoopGroup`; các framework reactive thường dùng scheduler và event-loop nội bộ. Cần đọc tài liệu của đúng framework để biết callback hiện tại chạy trên thread nào và API nào cho phép chuyển scheduler.

## 2. Những thao tác vô tình blocking event-loop

Các thao tác sau cần được xem xét kỹ nếu được gọi bên trong handler hoặc callback của event-loop:

- Gọi JDBC đồng bộ như `Connection`, `PreparedStatement.executeQuery()` hoặc `executeUpdate()`.
- Dùng HTTP client đồng bộ hoặc gọi một SDK chỉ có API blocking.
- Đọc/ghi file bằng API đồng bộ khi file có thể lớn hoặc thiết bị có độ trễ cao.
- Gọi `Future.get()`, `CompletableFuture.join()`, `CountDownLatch.await()`, `Semaphore.acquire()` hoặc chờ queue.
- Dùng `Thread.sleep()` để trì hoãn xử lý hoặc retry.
- Chờ monitor/lock đang bị thread khác giữ trong thời gian dài.
- Gọi native method hoặc thư viện bên ngoài có thể chờ I/O.
- Thực hiện xử lý CPU nặng, nén/giải mã lớn hoặc parse dữ liệu quá lớn ngay trong callback.
- Ghi log hoặc truy cập hệ thống phụ trợ theo cách đồng bộ có thể chờ lâu.

Không phải mọi thao tác tốn CPU đều là blocking I/O, nhưng một tác vụ CPU dài cũng chiếm event-loop và ngăn nó xử lý event khác. Vì vậy, event-loop cần tránh cả blocking wait lẫn công việc đồng bộ quá nặng.

## 3. Không gọi get() hoặc join() để chờ trong callback

Một lỗi phổ biến là gọi API bất đồng bộ rồi lập tức chờ kết quả của nó:

```java
// Không làm như vậy bên trong event-loop callback.
void onRequest(Request request) {
    CompletableFuture<Response> future = remoteClient.sendAsync(request);
    Response response = future.join(); // Chặn event-loop nếu kết quả chưa sẵn sàng.
    writeResponse(response);
}
```

Việc dùng một API có hậu tố `Async` không bảo đảm toàn bộ đoạn code phía sau cũng bất đồng bộ. `join()` vẫn chờ thread gọi cho đến khi future hoàn tất. `get()` cũng chặn và còn yêu cầu xử lý checked exceptions.

Hãy nối tiếp computation bằng các stage:

```java
CompletionStage<Response> responseStage = remoteClient.sendAsync(request);

responseStage.thenAccept(response -> writeResponse(response));
```

Handler đăng ký callback rồi trả quyền điều khiển về event-loop. Khi kết quả sẵn sàng, stage tiếp theo được thực thi theo quy tắc executor của thư viện/future đó. Nếu callback cần thao tác với channel hoặc context có thread affinity, hãy chuyển về executor/event-loop được framework chỉ định trước khi cập nhật trạng thái hoặc gửi response.

## 4. Ưu tiên API bất đồng bộ xuyên suốt chuỗi xử lý

Nếu thư viện cung cấp API bất đồng bộ, hãy giữ kiểu bất đồng bộ xuyên suốt thay vì chuyển sang blocking giữa chừng. Ví dụ với `java.net.http.HttpClient`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletionStage;

HttpClient client = HttpClient.newHttpClient();

CompletionStage<String> fetchText(URI uri) {
    HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

    return client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
            .thenApply(HttpResponse::body);
}
```

`sendAsync(...)` trả về `CompletableFuture` để caller nối tiếp xử lý mà không phải chờ response ngay trong event-loop. `HttpRequest.timeout(...)` đặt timeout cho request HTTP; timeout này là chính sách của HTTP client, không phải một bảo đảm chung cho mọi stage trong pipeline.

Nếu cần gọi thêm một API trả về `CompletionStage`, dùng `thenCompose` để nối stage mà không tạo cấu trúc `CompletionStage<CompletionStage<T>>`:

```java
CompletionStage<Order> loadOrder(String id) {
    return orderClient.fetch(id)
            .thenCompose(order -> inventoryClient.enrich(order));
}
```

`thenApply` phù hợp với phép biến đổi đồng bộ, nhanh trên kết quả. `thenCompose` phù hợp khi phép biến đổi tiếp tục trả về một stage bất đồng bộ khác. Không gọi `get()` hoặc `join()` bên trong lambda chỉ để làm phẳng stage.

## 5. Hiểu callback chạy trên thread nào

Không phải callback nào cũng tự động chạy trên event-loop, và cũng không phải callback nào tự động được chuyển sang worker thread. Với `CompletableFuture`:

- Các phương thức không có hậu tố `Async`, như `thenApply` hoặc `thenAccept`, có thể chạy trên thread hoàn tất stage trước đó hoặc thread gọi đăng ký callback nếu stage đã hoàn tất.
- Các phương thức có hậu tố `Async` nhưng không truyền executor thường dùng `ForkJoinPool.commonPool()` (theo quy tắc của `CompletableFuture`).
- Các phương thức có hậu tố `Async` và truyền executor sẽ gửi callback đến executor đó.

Vì vậy, không giả định `thenApply(...)` luôn chạy trên một worker riêng. Nếu stage trước được hoàn tất ngay trên event-loop, callback có thể chạy trên event-loop. Giữ callback mặc định thật ngắn và không blocking.

Ví dụ chuyển một phép tính CPU nặng sang executor CPU riêng:

```java
CompletionStage<Result> resultStage = responseStage
        .thenApplyAsync(this::expensiveParse, cpuExecutor);
```

Phép tính `expensiveParse` không còn chạy trực tiếp trên thread hoàn tất stage trước đó. Chọn executor phù hợp với workload; đừng mặc định dùng common pool cho blocking I/O hoặc phép tính CPU dài trong một dịch vụ có yêu cầu tài nguyên rõ ràng.

## 6. Offload blocking I/O sang executor riêng có giới hạn

Nếu thư viện chỉ cung cấp API blocking, chuyển lời gọi đó ra khỏi event-loop. Ví dụ, JDBC đồng bộ có thể được gọi bên trong `CompletableFuture.supplyAsync(...)` với executor dành riêng:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadFactory ioThreadFactory =
        Thread.ofPlatform().name("blocking-io-", 0).factory();

ThreadPoolExecutor blockingIoExecutor = new ThreadPoolExecutor(
        16,
        16,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        ioThreadFactory,
        new ThreadPoolExecutor.AbortPolicy());

CompletionStage<Order> loadOrderAsync(String id) {
    try {
        return CompletableFuture.supplyAsync(
                () -> repository.findOrder(id),
                blockingIoExecutor);
    } catch (java.util.concurrent.RejectedExecutionException e) {
        return CompletableFuture.failedFuture(e);
    }
}
```

Khi `loadOrderAsync(...)` được gọi từ event-loop, lời gọi `supplyAsync` chỉ lên lịch công việc và trả stage. `repository.findOrder(id)` chạy trên worker thread của `blockingIoExecutor`, không chạy trên event-loop.

Executor trong ví dụ có số worker cố định và hàng đợi hữu hạn. Khi worker cùng queue đã đầy, `AbortPolicy` từ chối tác vụ bằng `RejectedExecutionException`. Có thể chuyển lỗi này thành response quá tải hoặc retry có giới hạn theo chính sách ứng dụng.

Không dùng `CallerRunsPolicy` cho executor này nếu nó được submit từ event-loop: khi pool và queue đầy, policy đó có thể chạy tác vụ blocking ngay trên thread gọi, tức event-loop lại bị chặn. Hàng đợi không giới hạn cũng nguy hiểm vì tải tăng có thể làm queue và latency tăng mãi, tiêu thụ bộ nhớ.

Executor phải được quản lý theo vòng đời ứng dụng và đóng khi ứng dụng dừng. Kích thước worker và queue cần dựa trên thời gian I/O, giới hạn database, throughput mong muốn và kết quả load test; các số 16 và 200 chỉ là giá trị minh họa.

## 7. Dùng virtual threads khi API chỉ có dạng blocking

Java 21 cung cấp virtual threads chính thức. Chúng hữu ích khi muốn giữ cách viết tuần tự cho tác vụ blocking mà không cần giữ một platform thread cho mỗi lần chờ I/O. Có thể offload một thao tác blocking từ event-loop sang virtual thread và tiếp tục bằng stage:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.CompletionStage;

ExecutorService virtualExecutor = Executors.newVirtualThreadPerTaskExecutor();

CompletionStage<Order> loadOrder(String id) {
    return CompletableFuture.supplyAsync(
            () -> blockingRepository.findOrder(id),
            virtualExecutor);
}
```

`virtualExecutor` là tài nguyên cấp ứng dụng; hãy đóng nó từ lifecycle/shutdown hook của ứng dụng, không đóng ngay sau mỗi request và không gọi `close()` trên event-loop. `ExecutorService.close()` chờ các task đã submit kết thúc, vì vậy việc đóng executor trên event-loop cũng có thể gây blocking.

Event-loop không chờ `loadOrder(...)`; nó nhận lại một stage và tiếp tục xử lý event khác. Virtual thread thực hiện lời gọi blocking. Cách này hữu ích khi thư viện chưa có API bất đồng bộ và thao tác blocking tương thích với virtual threads.

Virtual threads không làm cho JDBC hoặc lời gọi file trở thành non-blocking. Chúng cũng không tăng giới hạn kết nối database, quota HTTP hay dung lượng bộ nhớ. Nếu có nhiều request cùng chờ database, vẫn phải giới hạn concurrency ở tài nguyên thực sự khan hiếm, ví dụ connection pool hoặc semaphore. Đừng gọi `join()` ngay sau khi submit virtual task từ event-loop; làm vậy vẫn chặn event-loop.

Khi một virtual thread đang chờ một API blocking được JVM hỗ trợ, nó thường có thể unmount khỏi carrier. Tuy nhiên, native calls hoặc một số tình huống pinning vẫn có thể giữ carrier; cần xem xét đặc tính thư viện native và phiên bản JDK khi có dấu hiệu nghẽn.

## 8. Giới hạn tài nguyên và backpressure

Offload công việc ra khỏi event-loop không có nghĩa là có thể nhận vô hạn công việc. Nếu request đến nhanh hơn tốc độ database hoặc dịch vụ bên ngoài xử lý, hàng đợi sẽ tăng. Cần có một cơ chế kiểm soát tải:

- Dùng queue hữu hạn và xử lý trường hợp executor từ chối tác vụ.
- Tôn trọng backpressure của framework reactive nếu framework cung cấp.
- Giới hạn số lời gọi đồng thời đến database hoặc dịch vụ ngoài bằng connection pool, semaphore hoặc quota tương ứng.
- Đặt timeout cho từng API I/O và deadline cho toàn bộ request.
- Tránh retry không giới hạn vì retry có thể làm tải lên downstream nặng hơn.
- Theo dõi queue depth, số task đang chạy, thời gian chờ worker, timeout và rejection.

Không đặt semaphore blocking acquire ngay trên event-loop. Nếu cần dùng semaphore để giới hạn tài nguyên, thực hiện việc chờ ở worker/virtual thread hoặc dùng cơ chế async permit phù hợp với framework. Nếu event-loop phải chờ permit bằng `acquire()`, vấn đề blocking ban đầu vẫn còn.

Ví dụ giới hạn lời gọi downstream trong phần blocking worker:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

Semaphore permits = new Semaphore(30);

CompletionStage<Response> callDownstreamAsync(Request request) {
    return CompletableFuture.supplyAsync(() -> {
        boolean acquired = false;
        try {
            if (!permits.tryAcquire(500, TimeUnit.MILLISECONDS)) {
                throw new java.util.concurrent.CompletionException(
                        new java.util.concurrent.TimeoutException("Downstream đang quá tải"));
            }
            acquired = true;
            return blockingClient.call(request);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new java.util.concurrent.CompletionException(e);
        } finally {
            if (acquired) {
                permits.release();
            }
        }
    }, blockingIoExecutor);
}
```

Semaphore ở ví dụ này chờ trên worker thread chứ không phải event-loop. Giá trị 30 cần phù hợp với quota downstream. Trong hệ thống thực tế, nên ưu tiên giới hạn đã có trong connection pool/client nếu chúng đáp ứng cùng mục tiêu để tránh nhiều tầng queue chồng lên nhau.

## 9. Xử lý lỗi, timeout và cancellation trong pipeline

Một pipeline bất đồng bộ cần xác định rõ lỗi được chuyển tiếp như thế nào. `CompletionStage` cho phép xử lý lỗi mà không gọi `get()`:

```java
CompletionStage<Response> responseStage = client.sendAsync(request)
        .thenApply(this::mapResponse)
        .exceptionally(error -> fallbackResponse(error));
```

`exceptionally(...)` tạo kết quả thay thế khi stage trước hoàn tất exceptional. Nếu cần xử lý cả thành công lẫn thất bại, dùng `handle(...)` hoặc `whenComplete(...)` theo mục đích. Không che tất cả lỗi bằng một response thành công giả nếu client cần phân biệt timeout, lỗi nghiệp vụ và lỗi hệ thống.

Đặt timeout ở đúng tầng:

- Cấu hình timeout trong HTTP client, JDBC driver, socket hoặc API I/O đang được gọi.
- Có thể dùng `orTimeout(...)` hoặc `completeOnTimeout(...)` trên `CompletableFuture` để giới hạn thời gian hoàn tất stage.
- Timeout của future không nhất thiết dừng công việc nền hoặc hủy request I/O; kiểm tra hợp đồng cancellation của thư viện.
- Nếu request bị client ngắt kết nối, cân nhắc hủy các stage/tác vụ downstream khi việc hủy an toàn và được hỗ trợ.

Với `Future` nhận từ `ExecutorService.submit(...)`, `cancel(true)` yêu cầu interrupt thread đang chạy task. Thư viện blocking hoặc native không nhất thiết phản hồi interrupt, vì vậy timeout ở API I/O vẫn cần thiết. Với `CompletableFuture`, có giới hạn riêng như sau:

Lưu ý riêng với `CompletableFuture`: `cancel(true)` không bảo đảm interrupt thread đang chạy supplier; tham số `mayInterruptIfRunning` không được dùng để điều khiển việc thực thi trong implementation này. Nếu cần cancellation có khả năng interrupt worker, quản lý tác vụ bằng `Future` trả về từ `ExecutorService.submit(...)` hoặc dùng cơ chế hủy riêng do thư viện I/O cung cấp. Dù vậy, interrupt vẫn chỉ là yêu cầu hợp tác; API I/O cần timeout riêng.

## 10. Giữ đúng thread affinity của framework

Một số đối tượng chỉ được truy cập từ event-loop hoặc executor mà framework chỉ định. Khi offload công việc, không giả định mọi API của channel, session, UI hoặc transaction context đều thread-safe.

Ví dụ với Netty, nếu cần ghi response sau khi xử lý ở worker thread, có thể đưa thao tác ghi về event-loop của channel:

```java
ctx.executor().execute(() -> {
    ctx.writeAndFlush(response);
});
```

Chỉ dùng cách chuyển thread theo API chính thức của framework. Không giữ lock hoặc mutable state dùng chung trong lúc chờ stage nếu có thể tránh; truyền dữ liệu bất biến giữa các stage sẽ dễ quản lý hơn.

Context như transaction, security identity, tracing span hoặc request metadata có thể không tự truyền qua mọi executor. Dùng cơ chế context propagation được framework hoặc thư viện tracing hỗ trợ thay vì giả định `ThreadLocal` sẽ luôn có cùng giá trị trên worker khác. Với virtual threads, mỗi virtual thread có context riêng theo quy tắc thread-local, nhưng việc chuyển từ callback này sang executor khác vẫn cần được thiết kế rõ.

## 11. Ví dụ tổng hợp: event-loop gọi async API và offload JDBC

Giả sử một handler nhận request, gọi một dịch vụ HTTP bất đồng bộ, rồi cần đọc dữ liệu bổ sung từ JDBC đồng bộ. HTTP call được giữ ở dạng async; JDBC được chuyển sang executor blocking riêng:

```java
CompletionStage<ApiResponse> handle(Request request) {
    return httpClient.fetchAsync(request.id())
            .thenCompose(remote ->
                    loadOrderAsync(remote.orderId())
                            .thenApply(order -> combine(remote, order)))
            .thenApply(this::toApiResponse)
            .exceptionally(this::mapFailure);
}
```

Trong thiết kế này:

1. `fetchAsync(...)` trả stage mà không buộc handler chờ response.
2. `loadOrderAsync(...)` submit JDBC blocking call vào `blockingIoExecutor` và trả stage ngay.
3. `thenCompose(...)` nối hai stage mà không gọi `get()` hoặc `join()`.
4. `thenApply(...)` chỉ nên chứa phép biến đổi ngắn. Nếu `combine(...)` hoặc `toApiResponse(...)` nặng CPU, chuyển chúng sang CPU executor bằng `thenApplyAsync(..., cpuExecutor)`.
5. `exceptionally(...)` chuyển lỗi thành kết quả theo hợp đồng API; cần giữ log và phân loại nguyên nhân để quan sát.

Đoạn code là cấu trúc minh họa; `httpClient`, repository và kiểu dữ liệu thuộc ứng dụng. Điểm cốt lõi là không gọi JDBC trực tiếp trong callback event-loop và không chặn để đợi stage hoàn tất.

## 12. Quan sát và chẩn đoán event-loop bị chặn

Khi nghi ngờ event-loop bị blocking, theo dõi cả dấu hiệu trong ứng dụng lẫn tài nguyên bên ngoài:

- Đo thời gian callback/handler chạy trên event-loop; callback dài bất thường là dấu hiệu cần điều tra.
- Theo dõi event-loop lag hoặc thời gian xử lý event nếu framework cung cấp metric.
- Quan sát thread dump để tìm event-loop thread đang ở `SocketRead`, JDBC, file I/O, `Future.get`, `CompletableFuture.join`, `LockSupport.park` hoặc stack trace blocking khác.
- Theo dõi queue depth, thời gian chờ executor, số worker đang bận và số task bị reject.
- Đối chiếu p95/p99 latency, throughput, timeout và error rate.
- Dùng profiler hoặc JFR để tìm callback CPU-bound hoặc blocking path; với native library, cần công cụ quan sát native phù hợp.

Thread dump là ảnh chụp tại một thời điểm. Một dump không thấy blocking không chứng minh callback không bao giờ bị block. Khi vấn đề xuất hiện theo tải, thu thập nhiều mẫu và metric theo thời gian.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi | Vì sao gây vấn đề | Cách xử lý |
|---|---|---|
| Gọi `Future.get()` hoặc `join()` trong event-loop | Thread xử lý event phải chờ kết quả | Nối tiếp bằng `CompletionStage` hoặc chuyển việc chờ sang worker |
| Gọi JDBC/HTTP client đồng bộ trong callback | I/O chờ giữ event-loop | Dùng API async hoặc offload sang executor riêng |
| Dùng `thenApply(...)` cho công việc blocking | Callback có thể chạy trên thread hoàn tất stage, bao gồm event-loop | Dùng `thenApplyAsync(..., executor)` hoặc tách blocking call sang executor |
| Dùng `supplyAsync(...)` mặc định cho blocking I/O | Common pool không được thiết kế như pool chuyên dụng cho I/O blocking | Truyền executor được cấu hình cho workload |
| Dùng `CallerRunsPolicy` trong executor offload | Khi quá tải, task có thể chạy ngay trên event-loop submit task | Dùng chính sách từ chối và xử lý overload ở tầng gọi |
| Dùng queue không giới hạn | Tải tăng làm queue, bộ nhớ và latency tăng | Dùng queue hữu hạn, backpressure và rejection handling |
| Chặn event-loop khi chờ semaphore | Event-loop vẫn bị giữ dù công việc đã được offload một phần | Chờ permit ở worker hoặc dùng API async permit |
| Giả định virtual threads biến JDBC thành async | Virtual thread vẫn thực thi lời gọi blocking | Offload khỏi event-loop và giới hạn connection/resource riêng |
| Cập nhật channel/context từ worker không đúng thread | Framework có thể yêu cầu thread affinity | Chuyển thao tác về event-loop bằng API framework |
| Chỉ đặt timeout trên CompletableFuture | Task hoặc I/O nền có thể tiếp tục chạy | Cấu hình timeout/cancellation tại API I/O và quản lý task lifecycle |

## 14. Checklist trước khi triển khai

- Xác định chính xác thread nào chạy handler và callback của thư viện bất đồng bộ.
- Giữ event-loop callback ngắn; không gọi API blocking, chờ lock lâu hoặc làm CPU work nặng tại đó.
- Ưu tiên API bất đồng bộ và nối tiếp bằng `CompletionStage`/API reactive của framework.
- Kiểm tra callback không có hậu tố `Async` có thể chạy trên thread hoàn tất stage trước đó.
- Truyền executor tường minh cho công việc CPU nặng hoặc blocking.
- Dùng executor blocking có worker/queue giới hạn và chính sách overload không chạy task trên event-loop.
- Cấu hình timeout/cancellation tại HTTP, JDBC, socket hoặc thư viện I/O thực tế.
- Giới hạn tài nguyên downstream và tôn trọng backpressure; không dùng blocking acquire trên event-loop.
- Dùng virtual threads như lựa chọn tổ chức blocking work sau khi offload, không xem chúng là non-blocking I/O.
- Giữ đúng thread affinity và context propagation của framework.
- Theo dõi event-loop lag, queue, throughput, latency, timeout và rejection dưới tải thực tế.

Khi kết hợp thư viện bất đồng bộ với API blocking, điều quan trọng nhất là biết callback đang chạy ở đâu. Giữ event-loop không bị chặn, offload phần blocking sang executor phù hợp có giới hạn, và kiểm soát timeout/backpressure ở tài nguyên thực sự bị giới hạn. Cách tổ chức này giúp ứng dụng Java 21 giữ được lợi ích của I/O bất đồng bộ mà vẫn tích hợp được những thư viện đồng bộ hiện có.
