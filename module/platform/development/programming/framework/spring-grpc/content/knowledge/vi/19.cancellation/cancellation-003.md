# Context cancellation trong handler

Khi client hủy một RPC hoặc deadline hết hạn, gRPC Java đánh dấu ngữ cảnh của lời gọi phía server là đã bị hủy. Handler có thể quan sát trạng thái này qua `io.grpc.Context`. Nếu handler chỉ chuyển công việc sang executor rồi tiếp tục xử lý như bình thường, worker có thể vẫn truy vấn database, gọi dịch vụ khác hoặc tạo dữ liệu dù caller đã ngừng chờ.

**Context cancellation trong handler** là cách truyền tín hiệu kết thúc của RPC tới các bước xử lý bên trong server. Bài học thuộc chương **Cancellation** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring từ hợp đồng Protocol Buffers và mã Java sinh ra, hỗ trợ unary/streaming RPC, metadata, deadline, status, interceptor, TLS, kiểm thử và giám sát. Trọng tâm ở đây là lấy context của RPC, quan sát cancellation/deadline, truyền context qua executor và dừng công việc phụ thuộc một cách an toàn.

## 1. Context của RPC là gì?

`io.grpc.Context` là cơ chế mang thông tin theo luồng thực thi của một RPC, gồm deadline, cancellation và các giá trị được gắn vào context. Khi gRPC gọi một server handler, context tương ứng với RPC đó được đặt làm context hiện tại trong lúc handler chạy.

```java
import io.grpc.Context;

Context rpcContext = Context.current();
boolean cancelled = rpcContext.isCancelled();
```

`Context.current()` lấy context đang gắn với luồng hiện tại. Trong server handler, đó thường là context của RPC hiện tại. `isCancelled()` cho biết context đã bị hủy; `cancellationCause()` cung cấp nguyên nhân nếu có; `getDeadline()` cho biết deadline gắn với context, nếu RPC có deadline.

Context giúp handler nhận biết vòng đời RPC mà không cần truyền một cờ cancellation qua mọi hàm. Tuy nhiên, context **không tự động dừng mọi công việc**. Một JDBC query, HTTP request hoặc tác vụ trong executor chỉ dừng khi API tương ứng hỗ trợ timeout/cancel hoặc code ứng dụng chủ động kiểm tra và phản ứng với tín hiệu.

## 2. Kiểm tra cancellation và deadline trong handler

Một handler đồng bộ có thể kiểm tra context ở các điểm an toàn trước khi bắt đầu công việc tốn tài nguyên và trước khi gửi kết quả:

```java
@Override
public void getReport(
        ReportRequest request,
        StreamObserver<ReportReply> responseObserver) {

    Context rpcContext = Context.current();

    if (rpcContext.isCancelled()) {
        return;
    }

    Report report = reportService.load(request.getReportId());

    if (rpcContext.isCancelled()) {
        return;
    }

    responseObserver.onNext(toReply(report));
    responseObserver.onCompleted();
}
```

Đoạn mã minh họa nguyên tắc kiểm tra; `reportService.load(...)` phải có giới hạn thời gian hoặc cơ chế hủy riêng nếu có thể block lâu. Việc kiểm tra `isCancelled()` trước và sau lời gọi chỉ giảm công việc thừa, không thể ngăn cancellation xảy ra ngay sau lần kiểm tra cuối. Transport sẽ xử lý call đã đóng; server vẫn phải đảm bảo tài nguyên được giải phóng.

Deadline cũng có thể được đọc từ context:

```java
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Deadline deadline = rpcContext.getDeadline();
if (deadline != null) {
    long remainingMillis = deadline.timeRemaining(TimeUnit.MILLISECONDS);
    if (remainingMillis <= 0) {
        return;
    }
    // Dùng remainingMillis để giới hạn bước xử lý tiếp theo.
}
```

Không có deadline nghĩa là `getDeadline()` trả `null`; đừng giả định mọi client đều đặt timeout. Ở hệ thống có yêu cầu thời gian rõ ràng, nên quy định deadline ở client và kiểm tra phần thời gian còn lại trước các bước xử lý quan trọng.

## 3. Đăng ký listener để nhận cancellation ngay khi xảy ra

Polling `isCancelled()` chỉ phát hiện cancellation ở lần kiểm tra tiếp theo. Khi handler cần báo cho worker đang chờ hoặc đang chạy, có thể đăng ký `Context.CancellationListener`:

```java
Context rpcContext = Context.current();
AtomicBoolean cancelled = new AtomicBoolean(rpcContext.isCancelled());

Context.CancellationListener listener = ignored ->
        cancelled.set(true);

rpcContext.addListener(listener, Runnable::run);
try {
    performWork(cancelled);
} finally {
    rpcContext.removeListener(listener);
}
```

Listener được gọi khi context bị hủy. Trong ví dụ, callback chỉ đặt cờ atomic để báo cho phần công việc đang chạy. `Runnable::run` thực thi callback ngay trên luồng phát thông báo; vì vậy listener phải **nhanh và không blocking**. Nếu cần gọi database, chờ lock hoặc thực hiện cleanup dài, hãy chuyển tín hiệu sang worker/executor thích hợp.

Luôn gỡ listener bằng `removeListener(...)` khi công việc kết thúc để không giữ tham chiếu không cần thiết. Cũng nên kiểm tra `isCancelled()` trước và sau đăng ký nếu logic có race giữa lúc lấy context và lúc listener được cài đặt. Context có thể đã bị hủy trước khi handler bắt đầu thực hiện bước tiếp theo.

## 4. Truyền Context sang executor

Một lỗi thường gặp là lấy `Context.current()` trong handler rồi submit lambda vào `ExecutorService`, sau đó gọi `Context.current()` bên trong worker và mong nhận được context của RPC ban đầu. **Context không tự động được gắn vào mọi thread do ứng dụng tạo.** Thread pool có thể tái sử dụng thread cho nhiều request; nếu không propagate context đúng cách, worker có thể thấy context gốc khác hoặc context mặc định.

Hãy capture context khi còn ở handler và bọc tác vụ bằng `rpcContext.wrap(...)`:

```java
Context rpcContext = Context.current();

workers.execute(rpcContext.wrap(() -> {
    if (rpcContext.isCancelled()) {
        return;
    }

    processReport(request);
}));
```

`wrap(Runnable)` gắn context đã capture trong lúc tác vụ chạy, rồi khôi phục context trước đó khi tác vụ kết thúc. Với `Callable`, gRPC Java cũng cung cấp cách wrap tương ứng. Có thể dùng `rpcContext.fixedContextExecutor(executor)` khi muốn mọi task qua executor đó chạy trong cùng context đã capture.

Không giữ `Context.current()` trong một field singleton của Spring service. Context thuộc một RPC; lưu nó vào field dùng chung có thể làm lẫn request đồng thời và giữ tham chiếu quá lâu. Hãy capture thành biến cục bộ trong handler rồi truyền vào đúng tác vụ có vòng đời gắn với RPC đó.

## 5. Kết hợp Context cancellation với `Future.cancel(true)`

Khi worker có thể chạy lâu, chỉ đặt cờ cancellation chưa đủ nếu worker đang block. Có thể đăng ký listener để hủy `Future`, đồng thời kiểm tra lại sau khi task được submit để xử lý race:

```java
Context rpcContext = Context.current();
AtomicBoolean cancelled = new AtomicBoolean(rpcContext.isCancelled());
AtomicReference<Future<?>> taskRef = new AtomicReference<>();

Context.CancellationListener listener = ignored -> {
    cancelled.set(true);
    Future<?> task = taskRef.get();
    if (task != null) {
        task.cancel(true);
    }
};

rpcContext.addListener(listener, Runnable::run);

try {
    Future<?> task = workers.submit(rpcContext.wrap(() -> {
        try {
            if (cancelled.get() || rpcContext.isCancelled()) {
                return;
            }

            String report = reportService.generate(request);

            if (cancelled.get() || rpcContext.isCancelled()
                    || Thread.currentThread().isInterrupted()) {
                return;
            }

            responseObserver.onNext(toReply(report));
            responseObserver.onCompleted();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (Exception failure) {
            if (!cancelled.get() && !rpcContext.isCancelled()) {
                responseObserver.onError(Status.INTERNAL
                        .withDescription("Không thể tạo báo cáo")
                        .withCause(failure)
                        .asRuntimeException());
            }
        } finally {
            rpcContext.removeListener(listener);
        }
    }));

    taskRef.set(task);
    // Cancellation có thể tới trước khi taskRef được gán.
    if (cancelled.get() || rpcContext.isCancelled()) {
        task.cancel(true);
    }
} catch (RejectedExecutionException rejected) {
    rpcContext.removeListener(listener);
    if (!rpcContext.isCancelled()) {
        responseObserver.onError(Status.RESOURCE_EXHAUSTED
                .withDescription("Server không nhận thêm tác vụ")
                .withCause(rejected)
                .asRuntimeException());
    }
}
```

Đoạn mã cần các biến `workers`, `request`, `reportService`, `responseObserver` và hàm `toReply(...)` từ handler. `Future.cancel(true)` gửi interrupt tới worker nếu task đang chạy; nó không đảm bảo dừng được thư viện I/O không hỗ trợ interrupt. Các API database/HTTP cần có query timeout hoặc cancellation riêng.

Race được xử lý theo hai hướng: listener hủy task nếu `taskRef` đã có; nếu cancellation đến trước khi `taskRef.set(task)`, cờ `cancelled` được kiểm tra lại sau khi submit và task bị hủy ngay. Worker gỡ listener trong `finally`. Nếu executor từ chối task, handler gỡ listener và trả status phù hợp khi call chưa bị hủy.

## 6. Truyền deadline và cancellation tới dependency khác

Nếu handler gọi một gRPC service khác, có thể dùng deadline còn lại từ context hiện tại để giới hạn downstream RPC:

```java
Deadline deadline = rpcContext.getDeadline();
InventoryGrpc.InventoryBlockingStub callStub = inventoryStub;

if (deadline != null) {
    long remainingNanos = deadline.timeRemaining(TimeUnit.NANOSECONDS);
    if (remainingNanos <= 0 || rpcContext.isCancelled()) {
        return;
    }
    callStub = callStub.withDeadlineAfter(
            remainingNanos, TimeUnit.NANOSECONDS);
}

StockReply stock = callStub.getStock(stockRequest);
```

Đoạn này minh họa truyền **ngân sách còn lại**, thay vì cấp lại timeout đầy đủ cho mỗi hop. Nếu không có deadline, hệ thống cần một default policy riêng để tránh downstream RPC chờ vô hạn. Khi worker bị interrupt do cancellation, cần đảm bảo lời gọi downstream cũng được kết thúc; với blocking stub, dùng deadline hữu hạn và thiết kế cơ chế cancellation phù hợp với call/transport. Với async downstream stub, giữ call handle để hủy đúng RPC khi context bị hủy.

Context propagation giúp các tầng đọc cùng trạng thái deadline/cancellation, nhưng không tự động làm mọi thư viện bên ngoài gRPC dừng. JDBC, HTTP client, message consumer và SDK cần API cancellation riêng. Không gọi `Thread.stop()` để ép dừng công việc.

## 7. Cancellation trong streaming handler

Với server-streaming hoặc bidirectional-streaming, context tồn tại trong suốt RPC. Khi client hủy stream, handler phải dừng producer, đóng subscription và giải phóng buffer/cursor. Có thể kết hợp `Context.CancellationListener` với `ServerCallStreamObserver` để kiểm tra call state và điều tiết việc gửi message.

```java
Context rpcContext = Context.current();
ServerCallStreamObserver<PriceUpdate> call =
        (ServerCallStreamObserver<PriceUpdate>) responseObserver;
AtomicBoolean stopped = new AtomicBoolean(rpcContext.isCancelled());
AtomicReference<Subscription> subscriptionRef = new AtomicReference<>();
AtomicReference<Context.CancellationListener> listenerRef = new AtomicReference<>();

Runnable cleanup = () -> {
    stopped.set(true);
    Subscription subscription = subscriptionRef.getAndSet(null);
    if (subscription != null) {
        subscription.close();
    }
    Context.CancellationListener registered = listenerRef.get();
    if (registered != null) {
        rpcContext.removeListener(registered);
    }
};
Context.CancellationListener listener = ignored -> cleanup.run();
listenerRef.set(listener);
rpcContext.addListener(listener, Runnable::run);

if (!stopped.get() && !call.isCancelled()) {
    Subscription subscription = priceFeed.subscribe(symbol, update -> {
        if (!stopped.get() && !call.isCancelled()) {
            responseObserver.onNext(toProto(update));
        }
    });
    subscriptionRef.set(subscription);

    // Xử lý cancellation xảy ra trong lúc subscribe đang tạo handle.
    if (stopped.get() || call.isCancelled()) {
        cleanup.run();
    }
}
```

`Subscription` là handle do `priceFeed` của ứng dụng cung cấp. Handler được đăng ký trước khi bắt đầu subscribe; nếu cancellation xảy ra trước khi handle được lưu, cờ `stopped` sẽ được kiểm tra lại ngay sau khi subscription được tạo và handle sẽ được đóng. `getAndSet(null)` làm cho thao tác lấy handle chỉ thành công ở một nhánh, tránh đóng cùng subscription nhiều lần. Khi nguồn dữ liệu kết thúc bình thường, owner cũng phải gọi `cleanup.run()` rồi `responseObserver.onCompleted()`; nếu stream lỗi, cleanup trước khi kết thúc bằng `onError(...)`. Cần tuân thủ contract thread-safety của `priceFeed` và không để callback `onNext` chạy đồng thời từ nhiều thread nếu observer không được thiết kế cho việc đó.

Ví dụ trên minh họa cancellation và cleanup; nó chưa triển khai đầy đủ flow control. Trong production, nếu producer có thể nhanh hơn client, cần dùng `call.isReady()` cùng `setOnReadyHandler(...)` và một hàng đợi có giới hạn để chỉ gửi khi call sẵn sàng. Không chỉ bỏ message khi `isReady()` trả `false`, vì như vậy có thể làm mất dữ liệu. Readiness khác với `isCancelled()`: stream có thể chưa bị hủy nhưng hiện tại chưa sẵn sàng nhận thêm message. Cancellation kết thúc toàn bộ call; readiness/backpressure điều tiết tốc độ khi call còn hoạt động.

## 8. Cleanup và các giới hạn của cancellation

Một cancellation listener nên chỉ phát tín hiệu dừng nhanh. Công việc cleanup dài nên được giao cho worker hoặc API sở hữu tài nguyên. Một số ví dụ:

| Tài nguyên/công việc | Cách phản ứng |
| --- | --- |
| Executor task | Lưu `Future`, đặt cờ và yêu cầu interrupt. |
| JDBC query | Đặt query timeout; dùng `Statement.cancel()` nếu driver hỗ trợ; đóng cursor/result set. |
| HTTP call tới dependency | Giữ call handle và gọi cancel theo API của HTTP client. |
| Subscription | Hủy đăng ký và ngừng producer. |
| File/stream/buffer | Đóng tài nguyên trong `finally` hoặc `try-with-resources`. |

Cleanup cần idempotent vì có thể được kích hoạt bởi nhiều đường kết thúc: cancellation listener, `finally`, lỗi xử lý hoặc shutdown server. Chỉ đóng tài nguyên mà handler/worker sở hữu; không đóng executor hoặc connection pool dùng chung chỉ vì một RPC bị hủy.

Cancellation là tín hiệu best-effort. Client có thể mất mạng đột ngột; server có thể nhận biết trễ. Nếu side effect đã commit, cancellation không rollback. Các operation ghi cần idempotency key hoặc cơ chế xác định trạng thái để tránh tạo dữ liệu trùng khi caller thử lại vì không nhận được response.

## 9. Kiểm thử Context cancellation

Kiểm thử nên xác minh cả ba điểm: handler lấy đúng context của RPC, listener được gọi khi client cancel, và worker/tài nguyên thực sự dừng. Với gRPC in-process server, một test có thể dùng latch:

```java
CountDownLatch handlerStarted = new CountDownLatch(1);
CountDownLatch contextCancelled = new CountDownLatch(1);

GreeterGrpc.GreeterImplBase service = new GreeterGrpc.GreeterImplBase() {
    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {
        Context rpcContext = Context.current();
        Context.CancellationListener listener = ignored ->
                contextCancelled.countDown();
        rpcContext.addListener(listener, Runnable::run);
        handlerStarted.countDown();
    }
};
```

Khởi chạy server và channel in-process với service trên. Client gọi bằng async stub và triển khai `ClientResponseObserver.beforeStart(...)` để giữ `ClientCallStreamObserver`; sau khi `handlerStarted.await(...)` thành công, client gọi `cancel(...)` và test chờ `contextCancelled.await(...)`. Trong fixture hoàn chỉnh, gỡ listener khi handler kết thúc và đóng channel/server trong `finally`.

Các ca cần bổ sung:

1. Client cancel khi worker đang chạy; xác minh listener đặt cờ và worker dừng.
2. Deadline hết hạn; xác minh context chuyển sang cancelled và downstream work nhận ngân sách còn lại.
3. Cancellation xảy ra trước khi task handle được lưu; xác minh race được xử lý.
4. Executor từ chối task; xác minh listener được gỡ và server trả status phù hợp.
5. Streaming producer bị hủy; xác minh subscription được đóng và không còn message mới.
6. Handler hoàn tất bình thường; xác minh listener được gỡ và không giữ tham chiếu sau RPC.

In-process test xác minh cơ chế gRPC/context nhưng không thay thế integration test qua TCP/TLS, proxy hoặc ingress. Kiểm thử mạng thật hữu ích để quan sát độ trễ phát hiện peer disconnect và đảm bảo cleanup vẫn an toàn khi kết nối bị mất.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Worker không thấy cancellation | Chỉ đọc `Context.current()` trong thread pool mà không propagate context. | Capture context trong handler và dùng `rpcContext.wrap(...)`. |
| Context bị giữ trong field singleton | Dùng chung context giữa các RPC đồng thời. | Giữ context ở biến cục bộ theo handler/task. |
| Listener không được gọi hoặc tài nguyên không dừng | Không đăng ký listener hoặc listener chỉ log. | Đặt cờ và nối tới task/resource cancellation. |
| Handler chặn trong cancellation callback | Listener làm I/O hoặc chờ worker kết thúc. | Callback chỉ phát tín hiệu nhanh; cleanup ở worker. |
| `Future.cancel(true)` nhưng query vẫn chạy | Driver/API không phản ứng với interrupt. | Dùng timeout/cancel API riêng của dependency. |
| Downstream RPC có thời gian chờ dài hơn request gốc | Cấp lại timeout ban đầu thay vì deadline còn lại. | Tính `timeRemaining(...)` và truyền xuống. |
| Listener giữ tham chiếu sau khi RPC kết thúc | Quên `removeListener(...)`. | Gỡ listener trong cleanup của handler/task. |
| Cancellation bị coi là rollback | Server có thể đã commit side effect. | Dùng idempotency và kiểm tra trạng thái nghiệp vụ. |

## 11. Bài tập thực hành

1. Trong server handler, lấy `Context.current()`, ghi nhận `isCancelled()` và `getDeadline()`; kiểm tra hành vi khi client đặt deadline ngắn.
2. Đăng ký `Context.CancellationListener` để đặt cờ; hủy client RPC và xác minh listener được gọi.
3. Chuyển công việc sang `ExecutorService` bằng `rpcContext.wrap(...)`; chứng minh worker nhận đúng context của RPC.
4. Kết nối listener với `Future.cancel(true)` và kiểm tra race khi cancellation tới trước lúc task handle được lưu.
5. Gọi downstream gRPC bằng thời gian còn lại của deadline; xác minh downstream không tiếp tục chạy quá ngân sách của RPC gốc.
6. Tạo server-streaming producer, hủy subscription khi context bị hủy và kiểm tra cleanup/backpressure.
7. Viết in-process test cho cancellation, deadline, executor rejection và hoàn tất bình thường; xác minh listener luôn được gỡ.

Sau bài này, bạn cần biết lấy context của RPC trong handler, đọc cancellation/deadline, đăng ký listener, truyền context sang executor và nối tín hiệu hủy tới worker hoặc I/O bên dưới. `Context` cung cấp trạng thái và propagation; ứng dụng vẫn phải chủ động dừng công việc và cleanup. Làm đúng điều đó giúp Spring gRPC server tránh xử lý thừa, giải phóng tài nguyên và giữ độ tin cậy khi client hủy RPC hoặc deadline hết hạn.
